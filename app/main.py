import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import auth, conversation, data_store, email_sender, handoff, leads_store

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
    sesion, mensaje = conversation.iniciar_sesion(req.telefono)
    _guardar_lead(sesion)
    return {"session_id": sesion.id, "mensaje": mensaje, "usuario_encontrado": sesion.usuario is not None}


def _enviar_correo_asesor(sesion: conversation.Sesion) -> dict:
    resumen_dict = handoff.construir_resumen(sesion)
    asunto, cuerpo = handoff.formatear_email(resumen_dict)
    ok, detalle = email_sender.enviar_resumen_asesor(asunto, cuerpo)
    if ok:
        sesion.enviado_al_asesor = True
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
            "hora": lead["creado_en"].astimezone(ZONA_BOGOTA).strftime("%H:%M"),
        }
        for lead in leads
    ]


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
