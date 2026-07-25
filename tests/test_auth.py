"""Pruebas de auth.verificar_asesor -- se llama directo con credenciales
armadas a mano, sin levantar un servidor HTTP real."""
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from app import auth, config


def test_falla_cerrado_sin_password_configurada(monkeypatch):
    monkeypatch.setattr(config, "ASESOR_PASSWORD", "")
    credenciales = HTTPBasicCredentials(username="asesor", password="lo que sea")

    with pytest.raises(HTTPException) as exc:
        auth.verificar_asesor(credenciales)
    assert exc.value.status_code == 500


def test_password_correcta_no_lanza(monkeypatch):
    monkeypatch.setattr(config, "ASESOR_PASSWORD", "clave-correcta")
    credenciales = HTTPBasicCredentials(username="asesor", password="clave-correcta")

    assert auth.verificar_asesor(credenciales) == "asesor"


def test_password_incorrecta_lanza_401(monkeypatch):
    monkeypatch.setattr(config, "ASESOR_PASSWORD", "clave-correcta")
    credenciales = HTTPBasicCredentials(username="asesor", password="clave-mala")

    with pytest.raises(HTTPException) as exc:
        auth.verificar_asesor(credenciales)
    assert exc.value.status_code == 401


def test_usuario_incorrecto_lanza_401(monkeypatch):
    monkeypatch.setattr(config, "ASESOR_PASSWORD", "clave-correcta")
    credenciales = HTTPBasicCredentials(username="otro-usuario", password="clave-correcta")

    with pytest.raises(HTTPException) as exc:
        auth.verificar_asesor(credenciales)
    assert exc.value.status_code == 401
