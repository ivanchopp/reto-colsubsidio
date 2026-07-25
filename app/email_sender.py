"""Envio real por SMTP, disparado por un clic manual en el panel de la demo
(nunca automatico), usando las credenciales del archivo .env."""
import smtplib
from email.mime.text import MIMEText

from app import config


def enviar_resumen_asesor(asunto: str, cuerpo: str) -> tuple[bool, str]:
    if not (config.SMTP_USER and config.SMTP_PASSWORD and config.ASESOR_EMAIL_DESTINO):
        return False, "Faltan credenciales SMTP o el correo destino en el archivo .env"

    mensaje = MIMEText(cuerpo, "plain", "utf-8")
    mensaje["Subject"] = asunto
    mensaje["From"] = config.SMTP_USER
    mensaje["To"] = config.ASESOR_EMAIL_DESTINO

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.SMTP_USER, [config.ASESOR_EMAIL_DESTINO], mensaje.as_string())
        return True, f"Correo enviado a {config.ASESOR_EMAIL_DESTINO}"
    except Exception as exc:
        return False, f"Error enviando correo: {exc}"
