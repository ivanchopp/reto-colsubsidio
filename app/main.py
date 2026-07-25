from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import conversation, data_store, email_sender, handoff

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
        }
        for p in catalogo
    ]


@app.post("/api/iniciar")
def iniciar(req: IniciarRequest):
    sesion, mensaje = conversation.iniciar_sesion(req.telefono)
    return {"session_id": sesion.id, "mensaje": mensaje, "usuario_encontrado": sesion.usuario is not None}


def _enviar_correo_asesor(sesion: conversation.Sesion) -> dict:
    resumen_dict = handoff.construir_resumen(sesion)
    asunto, cuerpo = handoff.formatear_email(resumen_dict)
    ok, detalle = email_sender.enviar_resumen_asesor(asunto, cuerpo)
    if ok:
        sesion.enviado_al_asesor = True
    return {"enviado": ok, "detalle": detalle, "asunto": asunto, "cuerpo": cuerpo}


@app.post("/api/mensaje")
def mensaje(req: MensajeRequest):
    sesion = conversation.obtener_sesion(req.session_id)
    if sesion is None:
        raise HTTPException(404, "Sesion no encontrada")
    respuesta = conversation.procesar_mensaje(sesion, req.texto)

    envio_asesor = None
    if sesion.finalizada and not sesion.enviado_al_asesor:
        # la conversacion acaba de cerrar: se notifica al asesor automaticamente,
        # sin esperar un clic manual
        envio_asesor = _enviar_correo_asesor(sesion)

    return {"mensaje": respuesta, "finalizada": sesion.finalizada, "envio_asesor": envio_asesor}


@app.post("/api/finalizar/{session_id}")
def finalizar(session_id: str, req: FinalizarRequest):
    """Cierre explicito de la conversacion: boton 'Finalizar' en el chat o
    inactividad de 5 minutos del lado del cliente (ver static/app.js).
    Reusa el mismo mecanismo de envio automatico de correo al asesor que el
    cierre natural en /api/mensaje."""
    sesion = conversation.obtener_sesion(session_id)
    if sesion is None:
        raise HTTPException(404, "Sesion no encontrada")
    respuesta = conversation.finalizar_sesion(sesion, req.motivo)

    envio_asesor = None
    if sesion.finalizada and not sesion.enviado_al_asesor:
        envio_asesor = _enviar_correo_asesor(sesion)

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
    """Reenvio manual -- normalmente el correo ya se envio solo al finalizar
    la conversacion (ver /api/mensaje). Esto sirve para reintentar si el
    envio automatico fallo (ej. problema de red o SMTP)."""
    sesion = conversation.obtener_sesion(session_id)
    if sesion is None:
        raise HTTPException(404, "Sesion no encontrada")
    return _enviar_correo_asesor(sesion)
