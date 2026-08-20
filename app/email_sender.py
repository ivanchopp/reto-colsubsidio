"""Envio real de correo al asesor via la API HTTP de Resend
(https://resend.com/docs/api-reference/emails/send-email). Se dispara
automaticamente al finalizar una conversacion (ver main.py) y tambien se
puede reintentar manualmente desde el panel de pruebas.

Antes usaba SMTP directo (smtp.gmail.com): funcionaba en local, pero en
produccion (Render, plan gratuito) toda conexion a los puertos SMTP
(25/465/587) se queda colgada hasta el timeout -- Render bloquea ese trafico
saliente desde septiembre de 2025 para prevenir spam. Una API HTTP viaja por
el puerto 443 (HTTPS), que nunca se bloquea, y de paso evita manejar
TLS/autenticacion SMTP a mano. No se agrega una libreria nueva: es una sola
llamada POST con json, alcanza con urllib (stdlib).
"""
import json
import urllib.error
import urllib.request

from app import config

RESEND_ENDPOINT = "https://api.resend.com/emails"

# Mismo criterio que el timeout SMTP que reemplaza: sin esto, una API que no
# responde bloquea el chat del usuario (el envio de correo ocurre de forma
# sincrona dentro de la misma peticion, ver main.py) mucho mas de lo que
# deberia tardar una llamada HTTP normal.
HTTP_TIMEOUT_SEGUNDOS = 10


def enviar_resumen_asesor(asunto: str, cuerpo: str) -> tuple[bool, str]:
    faltantes = [
        nombre
        for nombre, valor in (
            ("RESEND_API_KEY", config.RESEND_API_KEY),
            ("EMAIL_FROM", config.EMAIL_FROM),
            ("ASESOR_EMAIL_DESTINO", config.ASESOR_EMAIL_DESTINO),
        )
        if not valor
    ]
    if faltantes:
        return False, f"Falta configurar en el archivo .env: {', '.join(faltantes)}"

    payload = json.dumps(
        {
            "from": config.EMAIL_FROM,
            "to": [config.ASESOR_EMAIL_DESTINO],
            "subject": asunto,
            "text": cuerpo,
        }
    ).encode("utf-8")

    peticion = urllib.request.Request(
        RESEND_ENDPOINT,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {config.RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(peticion, timeout=HTTP_TIMEOUT_SEGUNDOS) as respuesta:
            respuesta.read()
        return True, f"Correo enviado a {config.ASESOR_EMAIL_DESTINO}"
    except urllib.error.HTTPError as exc:
        # Resend devuelve el motivo del rechazo en el cuerpo (ej. dominio no
        # verificado, remitente invalido, API key revocada) -- se incluye en
        # el detalle en vez de solo el codigo, para no tener que adivinar.
        detalle_api = exc.read().decode("utf-8", errors="replace")
        return False, f"Error enviando correo ({exc.code}): {detalle_api}"
    except urllib.error.URLError as exc:
        return False, f"Error enviando correo: {exc.reason}"
