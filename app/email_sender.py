"""Envio real por SMTP usando las credenciales del archivo .env. Se dispara
automaticamente al finalizar una conversacion (ver main.py) y tambien se
puede reintentar manualmente desde el panel de pruebas."""
import smtplib
import socket
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


def _conectar_forzando_ipv4(host: str, port: int, timeout: int) -> smtplib.SMTP:
    """smtp.gmail.com (y muchos hosts SMTP) publican tanto direccion IPv4
    como IPv6. Muchas plataformas de contenedores (Render incluida) no
    tienen salida IPv6 configurada: si la resolucion DNS devuelve primero
    el registro AAAA, smtplib intenta conectar por ahi y falla con
    '[Errno 101] Network is unreachable', aunque la ruta IPv4 si funcione
    (por eso local funciona bien y en Render no).

    Se fuerza la resolucion a solo IPv4 mientras se abre la conexion. El
    hostname original (config.SMTP_HOST) se sigue pasando tal cual al
    constructor de SMTP, asi que la verificacion del certificado TLS en
    starttls() (que usa ese hostname para SNI) no se ve afectada -- solo se
    filtra que direcciones prueba el socket subyacente."""
    getaddrinfo_original = socket.getaddrinfo

    def _solo_ipv4(host_, port_, family=0, type_=0, proto=0, flags=0):
        return getaddrinfo_original(host_, port_, socket.AF_INET, type_, proto, flags)

    socket.getaddrinfo = _solo_ipv4
    try:
        return smtplib.SMTP(host, port, timeout=timeout)
    finally:
        socket.getaddrinfo = getaddrinfo_original


def enviar_resumen_asesor(asunto: str, cuerpo: str) -> tuple[bool, str]:
    if not (config.SMTP_USER and config.SMTP_PASSWORD and config.ASESOR_EMAIL_DESTINO):
        return False, "Faltan credenciales SMTP o el correo destino en el archivo .env"

    mensaje = MIMEText(cuerpo, "plain", "utf-8")
    mensaje["Subject"] = asunto
    mensaje["From"] = config.SMTP_USER
    mensaje["To"] = config.ASESOR_EMAIL_DESTINO

    try:
        with _conectar_forzando_ipv4(config.SMTP_HOST, config.SMTP_PORT, SMTP_TIMEOUT_SEGUNDOS) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.SMTP_USER, [config.ASESOR_EMAIL_DESTINO], mensaje.as_string())
        return True, f"Correo enviado a {config.ASESOR_EMAIL_DESTINO}"
    except Exception as exc:
        return False, f"Error enviando correo: {exc}"
