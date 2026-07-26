"""Tests de la deteccion de evasion en app/conversation.py.

El caso que motiva estos tests: "no" es una respuesta legitima a "¿ya vienes
ahorrando?", pero se clasificaba como evasion. Eso descartaba el dato, no
capturaba ahorro_cuota_inicial=False y ademas le sumaba un intento de evasion
a alguien que si habia contestado.
"""
import pytest

from app import conversation

TEMA_AHORRO = "si ya viene ahorrando o tiene cesantias pensando en la cuota inicial"
TEMA_ASPIRACIONAL = "que suenos o planes tiene con este paso de comprar vivienda"
TEMA_EMPRESA = "en que empresa trabaja actualmente o a que se dedica hoy"


@pytest.mark.parametrize("respuesta", ["no", "No", "NO", "nada"])
def test_negativa_corta_no_es_evasion_en_pregunta_de_si_o_no(respuesta):
    assert conversation._es_evasion(respuesta, TEMA_AHORRO) is False


@pytest.mark.parametrize("respuesta", ["no", "nada", "ninguno", "paso"])
def test_negativa_corta_si_es_evasion_en_pregunta_abierta(respuesta):
    """A "¿que suenos tienes?", un "no" seco sigue siendo evasion."""
    assert conversation._es_evasion(respuesta, TEMA_ASPIRACIONAL) is True


@pytest.mark.parametrize(
    "respuesta",
    ["no quiero responder", "prefiero no decir", "no es tu asunto", "es confidencial"],
)
def test_las_frases_de_evasion_lo_son_en_cualquier_tema(respuesta):
    assert conversation._es_evasion(respuesta, TEMA_AHORRO) is True
    assert conversation._es_evasion(respuesta, TEMA_ASPIRACIONAL) is True


def test_la_pregunta_de_empresa_no_se_responde_por_si_o_no():
    """Su campo (situacion_laboral) no es booleano: un "no" ahi no aporta."""
    assert conversation._es_evasion("no", TEMA_EMPRESA) is True


def test_sin_tema_mantiene_el_comportamiento_estricto():
    assert conversation._es_evasion("no") is True


def test_una_respuesta_normal_nunca_es_evasion():
    assert conversation._es_evasion("tengo unas cesantias guardadas", TEMA_AHORRO) is False
