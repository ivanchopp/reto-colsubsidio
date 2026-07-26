import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import (
    auth, conversation, data_store, email_sender, extraccion, handoff,
    leads_store, nutricion, scoring,
)

ZONA_BOGOTA = ZoneInfo("America/Bogota")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Asesor Digital de Vivienda Colsubsidio - Demo")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def no_cache(request, call_next):
    """Sin esto, algunos navegadores (sobre todo moviles, que "congelan" la
    pestana en vez de recargarla) siguen mostrando index.html/app.js/style.css
    viejos despues de un deploy nuevo, aunque el servidor ya tenga el cambio.
    no-cache obliga a revalidar con el servidor (ETag) en cada carga."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache"
    return response


class IniciarRequest(BaseModel):
    telefono: str
    # canal de entrada del lead; el frontend lo toma del parametro ?origen=
    # de la URL de la pauta. Se normaliza en leads_store.normalizar_origen.
    origen: str | None = None


class MensajeRequest(BaseModel):
    session_id: str
    texto: str


class FinalizarRequest(BaseModel):
    motivo: str = "manual"


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/proyectos")
def proyectos():
    catalogo = data_store.cargar_catalogo()
    return [
        {
            "nombre": p["nombre_proyecto"],
            "ciudad": p["ciudad"],
            "segmento": p["segmento_poblacional"],
            "categoria": p.get("categoria_dominante", ""),
            "amenities": p.get("amenities", [])[:4],
            "brochure_url": p.get("brochure_url", ""),
        }
        for p in catalogo
    ]


@app.post("/api/iniciar")
def iniciar(req: IniciarRequest):
    sesion, mensaje = conversation.iniciar_sesion(
        req.telefono, leads_store.normalizar_origen(req.origen)
    )
    _guardar_lead(sesion)
    return {"session_id": sesion.id, "mensaje": mensaje, "usuario_encontrado": sesion.usuario is not None}


@app.get("/api/sesion/{session_id}")
def estado_sesion(session_id: str):
    """Estado de presentacion para el cliente web.

    No expone scoring, datos personales ni reglas internas: solo los datos
    necesarios para que la interfaz pueda representar el avance de la charla.
    """
    sesion = conversation.obtener_sesion(session_id)
    if sesion is None:
        raise HTTPException(404, "Sesion no encontrada")
    recomendacion = None
    if sesion.recomendacion:
        proyecto = sesion.recomendacion.proyecto
        recomendacion = {
            "nombre": proyecto.get("nombre_proyecto", "Tu proyecto recomendado"),
            "ciudad": proyecto.get("ciudad", ""),
            "categoria": proyecto.get("categoria_dominante", ""),
            "amenities": proyecto.get("amenities", [])[:3],
            "brochure_url": proyecto.get("brochure_url", ""),
        }
    return {
        "fase": sesion.fase,
        "tema_actual": sesion.tema_actual,
        "respuestas_aspiracionales": len(sesion.respuestas_aspiracionales),
        "finalizada": sesion.finalizada,
        "interaccion_cerrada": sesion.interaccion_cerrada,
        "recomendacion": recomendacion,
        # lo que la charla aporto al perfil. Se expone el conteo y las lineas
        # legibles, nunca el score ni el segmento: el usuario no debe ver su
        # calificacion (ver SOBRE MI/SOBREMI.md, lineas rojas).
        "datos_declarados": len(sesion.datos_declarados),
        "datos_declarados_legibles": extraccion.resumir_para_asesor(sesion.datos_declarados),
    }


def _enviar_correo_asesor(sesion: conversation.Sesion) -> dict:
    resumen_dict = handoff.construir_resumen(sesion)
    asunto, cuerpo = handoff.formatear_email(resumen_dict)
    ok, detalle = email_sender.enviar_resumen_asesor(asunto, cuerpo)
    if ok:
        sesion.enviado_al_asesor = True
    else:
        # sin esto, un fallo de SMTP en produccion (credenciales, host
        # bloqueado, timeout) no deja ningun rastro -- queda solo en la
        # respuesta HTTP, que nadie revisa despues del hecho. Con logging
        # queda visible en los logs de Render.
        logging.error("Fallo el envio de correo al asesor para la sesion %s: %s", sesion.id, detalle)
    return {"enviado": ok, "detalle": detalle, "asunto": asunto, "cuerpo": cuerpo}


def _lead_payload(sesion: conversation.Sesion) -> dict:
    """Traduce una Sesion en memoria al shape que espera leads_store.upsert_lead.
    Vive aqui (no en conversation.py) para que ese modulo siga sin conocer
    nada de la base de datos -- conversation.py es logica de conversacion
    pura, la persistencia es un detalle de la capa HTTP."""
    usuario = sesion.usuario or {}
    resultado = sesion.resultado_scoring
    documento = usuario.get("Documento")
    return {
        "session_id": sesion.id,
        "telefono": sesion.telefono,
        "nombre": usuario.get("Nombre") or sesion.datos_declarados_no_registrado,
        "ciudad": usuario.get("Ciudad"),
        "usuario_registrado": sesion.usuario is not None,
        "documento": int(documento) if documento not in (None, "") else None,
        "score": resultado.score if resultado else None,
        "segmento_lead": resultado.segmento_lead if resultado else None,
        "project_segment": resultado.project_segment if resultado else None,
        "razones": resultado.razones if resultado else None,
        "peer_stats": resultado.peer_stats if resultado else None,
        "subsidios_elegibles": (
            [{"nombre": s.nombre, "requisito_salarial_texto": s.requisito_salarial_texto}
             for s in resultado.subsidios_elegibles]
            if resultado else None
        ),
        "contribuciones": resultado.contribuciones if resultado else None,
        "fase": sesion.fase,
        "finalizada": sesion.finalizada,
        "interaccion_cerrada": sesion.interaccion_cerrada,
        "enviado_al_asesor": sesion.enviado_al_asesor,
        "origen": sesion.origen,
        # afiliacion verificada contra la base. None para un no registrado:
        # no es "no afiliado", es "no se sabe", y el cupo 90/10 lo trata
        # distinto (ver leads_store._es_afiliado)
        "afiliado": (
            str(usuario.get("Afiliado a colsubsidio", "")).strip().lower() == "si"
            if sesion.usuario
            else None
        ),
        "bloqueantes": (
            nutricion.detectar_bloqueantes(
                usuario or scoring._perfil_desde_declarados(sesion.datos_declarados),
                resultado,
                sesion.datos_declarados,
            )
            if resultado
            else None
        ),
        "datos_declarados": sesion.datos_declarados or None,
    }


def _guardar_lead(sesion: conversation.Sesion) -> None:
    try:
        leads_store.upsert_lead(**_lead_payload(sesion))
    except Exception:
        # nunca tumbar el chat del usuario final por un problema de
        # persistencia del panel del asesor (ej. Supabase caido/lento)
        logging.exception("No se pudo guardar el lead %s en Supabase", sesion.id)


@app.post("/api/mensaje")
def mensaje(req: MensajeRequest):
    sesion = conversation.obtener_sesion(req.session_id)
    if sesion is None:
        raise HTTPException(404, "Sesion no encontrada")
    respuesta = conversation.procesar_mensaje(sesion, req.texto)

    envio_asesor = None
    if sesion.interaccion_cerrada and not sesion.enviado_al_asesor:
        # ojo: se dispara con interaccion_cerrada, NO con finalizada -- un
        # usuario registrado puede seguir preguntando despues de recibir la
        # recomendacion (ver conversation.py), y el correo no debe salir
        # hasta que la interaccion de verdad termine
        envio_asesor = _enviar_correo_asesor(sesion)

    _guardar_lead(sesion)
    return {"mensaje": respuesta, "finalizada": sesion.finalizada, "envio_asesor": envio_asesor}


@app.post("/api/finalizar/{session_id}")
def finalizar(session_id: str, req: FinalizarRequest):
    """Cierre explicito de la conversacion: boton 'Finalizar' en el chat o
    inactividad de 3 minutos del lado del cliente (ver static/app.js).
    Reusa el mismo mecanismo de envio automatico de correo al asesor que el
    cierre natural en /api/mensaje."""
    sesion = conversation.obtener_sesion(session_id)
    if sesion is None:
        raise HTTPException(404, "Sesion no encontrada")
    respuesta = conversation.finalizar_sesion(sesion, req.motivo)

    envio_asesor = None
    if sesion.interaccion_cerrada and not sesion.enviado_al_asesor:
        envio_asesor = _enviar_correo_asesor(sesion)

    _guardar_lead(sesion)
    return {"mensaje": respuesta, "finalizada": sesion.finalizada, "envio_asesor": envio_asesor}


@app.get("/api/resumen/{session_id}")
def resumen(session_id: str):
    sesion = conversation.obtener_sesion(session_id)
    if sesion is None:
        raise HTTPException(404, "Sesion no encontrada")
    resumen_dict = handoff.construir_resumen(sesion)
    asunto, cuerpo = handoff.formatear_email(resumen_dict)
    return {"asunto": asunto, "cuerpo": cuerpo, "enviado_al_asesor": sesion.enviado_al_asesor}


@app.post("/api/enviar-asesor/{session_id}")
def enviar_asesor(session_id: str):
    """Reenvio manual -- normalmente el correo ya se envio solo cuando la
    interaccion realmente se cierra (ver interaccion_cerrada en /api/mensaje
    y /api/finalizar). Esto sirve para reintentar si el envio automatico
    fallo (ej. problema de red o SMTP)."""
    sesion = conversation.obtener_sesion(session_id)
    if sesion is None:
        raise HTTPException(404, "Sesion no encontrada")
    return _enviar_correo_asesor(sesion)


# ---------------------------------------------------------------------
# Panel del asesor comercial -- protegido con contrasena compartida
# (ver app/auth.py). Nada de lo de arriba (chat del cliente) pasa por aqui.
# ---------------------------------------------------------------------

@app.get("/asesor")
def asesor_page(_: str = Depends(auth.verificar_asesor)):
    return FileResponse(STATIC_DIR / "asesor.html")


@app.get("/api/asesor/leads/hoy")
def asesor_leads_hoy(_: str = Depends(auth.verificar_asesor)):
    leads = leads_store.listar_leads_hoy()
    return [
        {
            "session_id": lead["session_id"],
            "nombre": lead["nombre"] or "Sin nombre",
            "telefono": lead["telefono"],
            "ciudad": lead["ciudad"],
            "usuario_registrado": lead["usuario_registrado"],
            "score": lead["score"],
            "segmento_lead": lead["segmento_lead"],
            "fase": lead["fase"],
            "finalizada": lead["finalizada"],
            "interaccion_cerrada": lead["interaccion_cerrada"],
            "origen": lead.get("origen"),
            "afiliado": lead.get("afiliado"),
            "bloqueantes": lead.get("bloqueantes") or [],
            "hora": lead["creado_en"].astimezone(ZONA_BOGOTA).strftime("%H:%M"),
        }
        for lead in leads
    ]


@app.get("/api/asesor/resumen-dia")
def asesor_resumen_dia(_: str = Depends(auth.verificar_asesor)):
    """Vista agregada del dia: cupo 90/10 y calidad por canal.

    Son las dos cosas que un lead individual no puede responder. La regla
    90/10 es una cuota sobre el total, no un descuento por persona, y la
    comparacion de canales es lo que permite decidir donde recortar pauta.
    """
    return leads_store.calcular_stats(leads_store.listar_leads_hoy())


@app.get("/api/asesor/leads/{session_id}")
def asesor_lead_detalle(session_id: str, _: str = Depends(auth.verificar_asesor)):
    sesion = conversation.obtener_sesion(session_id)

    if sesion is not None:
        # sesion todavia viva en memoria: es la fuente mas fresca (incluye
        # el transcript completo, que no se persiste en la base de datos)
        resultado = sesion.resultado_scoring
        usuario = sesion.usuario or {}
        return {
            "session_id": sesion.id,
            "telefono": sesion.telefono,
            "nombre": usuario.get("Nombre") or sesion.datos_declarados_no_registrado or "Sin nombre",
            "ciudad": usuario.get("Ciudad"),
            "usuario_registrado": sesion.usuario is not None,
            "fase": sesion.fase,
            "finalizada": sesion.finalizada,
            "interaccion_cerrada": sesion.interaccion_cerrada,
            "enviado_al_asesor": sesion.enviado_al_asesor,
            "scoring": (
                {
                    "score": resultado.score,
                    "segmento_lead": resultado.segmento_lead,
                    "project_segment": resultado.project_segment,
                    "razones": resultado.razones,
                    "peer_stats": resultado.peer_stats,
                    "subsidios_elegibles": [
                        {"nombre": s.nombre, "requisito_salarial_texto": s.requisito_salarial_texto}
                        for s in resultado.subsidios_elegibles
                    ],
                    "contribuciones": resultado.contribuciones,
                    "bloqueantes": nutricion.detectar_bloqueantes(
                        usuario or scoring._perfil_desde_declarados(sesion.datos_declarados),
                        resultado,
                        sesion.datos_declarados,
                    ),
                }
                if resultado else None
            ),
            "chat_disponible": True,
            "historial": sesion.historial,
            "chat_mensaje": None,
        }

    lead = leads_store.obtener_lead(session_id)
    if lead is None:
        raise HTTPException(404, "Lead no encontrado")

    return {
        "session_id": lead["session_id"],
        "telefono": lead["telefono"],
        "nombre": lead["nombre"] or "Sin nombre",
        "ciudad": lead["ciudad"],
        "usuario_registrado": lead["usuario_registrado"],
        "fase": lead["fase"],
        "finalizada": lead["finalizada"],
        "interaccion_cerrada": lead["interaccion_cerrada"],
        "enviado_al_asesor": lead["enviado_al_asesor"],
        "scoring": (
            {
                "score": lead["score"],
                "segmento_lead": lead["segmento_lead"],
                "project_segment": lead["project_segment"],
                "razones": lead["razones"],
                "peer_stats": lead["peer_stats"],
                "subsidios_elegibles": lead["subsidios_elegibles"],
                "contribuciones": lead["contribuciones"],
            }
            if lead["score"] is not None else None
        ),
        "chat_disponible": False,
        "historial": None,
        "chat_mensaje": (
            "El servidor se reinicio o la sesion ya no esta en memoria; "
            "el transcript de esta conversacion no esta disponible."
        ),
    }
