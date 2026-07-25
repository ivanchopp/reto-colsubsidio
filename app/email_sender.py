"""Envio real por SMTP usando las credenciales del archivo .env. Se dispara
automaticamente al finalizar una conversacion (ver main.py) y tambien se
puede reintentar manualmente desde el panel de pruebas."""
import smtplib
from email.mime.text import MIMEText

from app import config

# Sin esto, una conexion SMTP que se queda colgada (ej. el puerto bloqueado
# por el proveedor de hosting, o el host SMTP sin responder) bloquea el
# socket indefinidamente -- y como el envio de correo ocurre de forma
# sincrona dentro de la misma peticion que responde al chat (ver main.py),
# el usuario ve el chat "trabado" varios minutos esperando una respuesta
# que en realidad ya estaba lista, solo que el request seguia colgado en el
# envio del correo. Con timeout, si falla, falla rapido y el chat responde
# igual de rapido.
SMTP_TIMEOUT_SEGUNDOS = 10


def enviar_resumen_asesor(asunto: str, cuerpo: str) -> tuple[bool, str]:
    if not (config.SMTP_USER and config.SMTP_PASSWORD and config.ASESOR_EMAIL_DESTINO):
        return False, "Faltan credenciales SMTP o el correo destino en el archivo .env"

    mensaje = MIMEText(cuerpo, "plain", "utf-8")
    mensaje["Subject"] = asunto
    mensaje["From"] = config.SMTP_USER
    mensaje["To"] = config.ASESOR_EMAIL_DESTINO

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=SMTP_TIMEOUT_SEGUNDOS) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.SMTP_USER, [config.ASESOR_EMAIL_DESTINO], mensaje.as_string())
        return True, f"Correo enviado a {config.ASESOR_EMAIL_DESTINO}"
    except Exception as exc:
        return False, f"Error enviando correo: {exc}"
