"""Proteccion simple del panel del asesor comercial: una contrasena
compartida (HTTP Basic Auth), no un sistema de usuarios. Suficiente para un
equipo comercial pequeno; si mas adelante cada asesor necesita su propio
login, esto habria que reemplazarlo por algo mas robusto."""
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app import config

security = HTTPBasic()


def verificar_asesor(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    if not config.ASESOR_PASSWORD:
        # falla cerrado: sin contrasena configurada, el panel queda
        # inaccesible -- nunca "abierto por accidente" en produccion
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "ASESOR_PASSWORD no esta configurada: el panel del asesor esta deshabilitado.",
        )
    usuario_ok = secrets.compare_digest(credentials.username, "asesor")
    password_ok = secrets.compare_digest(credentials.password, config.ASESOR_PASSWORD)
    if not (usuario_ok and password_ok):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Credenciales invalidas",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
