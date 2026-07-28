"""Reason codes: un identificador estable por cada regla que afecta el
score, en paralelo al texto en espanol de 'razones' (ver ResultadoScoring
y el bloque RC_* en app/scoring.py).

Dos cosas se prueban aca: el invariante estructural (misma longitud y orden
que razones, siempre), y que las reglas de negocio concretas disparan el
codigo esperado -- lo mismo que ya cubre tests/test_scoring.py con texto
libre, pero contra un identificador que no se rompe si alguien reformula
una frase.
"""
import pandas as pd
import pytest

from app import data_store, scoring, subsidios


def _misma_longitud_y_orden(resultado: scoring.ResultadoScoring) -> bool:
    return len(resultado.razones) == len(resultado.codigos_razones)


# ---------------------------------------------------------------------
# Invariante estructural: razones y codigos_razones siempre van de la mano
# ---------------------------------------------------------------------

def test_calcular_score_produce_un_codigo_por_cada_razon(make_usuario):
    resultado = scoring.calcular_score(make_usuario())
    assert _misma_longitud_y_orden(resultado)
    assert all(codigo.startswith("RC_") for codigo in resultado.codigos_razones)


def test_calcular_score_no_registrado_sin_datos_produce_un_codigo_por_razon():
    resultado = scoring.calcular_score_no_registrado()
    assert _misma_longitud_y_orden(resultado)


def test_calcular_score_no_registrado_con_datos_produce_un_codigo_por_razon():
    resultado = scoring.calcular_score_no_registrado(
        {"situacion_laboral": "empleado_formal", "ingresos_mensuales_aprox": 6_000_000}
    )
    assert _misma_longitud_y_orden(resultado)


def test_calcular_score_no_registrado_con_supuesto_de_ingreso_produce_un_codigo_por_razon():
    resultado = scoring.calcular_score_no_registrado({"situacion_laboral": "empleado_formal"})
    assert _misma_longitud_y_orden(resultado)
    assert scoring.RC_SUPUESTO_INGRESO in resultado.codigos_razones


# ---------------------------------------------------------------------
# Reglas de negocio concretas -- mismos escenarios de test_scoring.py,
# ahora verificados por codigo en vez de por substring de texto
# ---------------------------------------------------------------------

def test_vis_no_afiliado_dispara_rc_no_afiliado_vis(make_usuario):
    resultado = scoring.calcular_score(make_usuario(**{"Afiliado a colsubsidio": "No"}))
    assert scoring.RC_NO_AFILIADO_VIS in resultado.codigos_razones


def test_no_vis_no_afiliado_dispara_rc_no_afiliado_no_vis(make_usuario):
    usuario = make_usuario(
        **{
            "Rango salarial": "de 9.000.000 - 10.000.000",
            "Afiliado a colsubsidio": "No",
        }
    )
    resultado = scoring.calcular_score(usuario)
    assert scoring.RC_NO_AFILIADO_NO_VIS in resultado.codigos_razones
    assert scoring.RC_AFILIADO_NO_VIS not in resultado.codigos_razones


def test_no_vis_afiliado_dispara_rc_afiliado_no_vis(make_usuario):
    usuario = make_usuario(**{"Rango salarial": "de 9.000.000 - 10.000.000"})
    resultado = scoring.calcular_score(usuario)
    assert scoring.RC_AFILIADO_NO_VIS in resultado.codigos_razones


def test_desempleado_dispara_rc_desempleo(make_usuario):
    usuario = make_usuario(**{"Estado laboral": "Desempleado", "Tipo de contrato": "N/A"})
    resultado = scoring.calcular_score(usuario)
    assert scoring.RC_DESEMPLEO in resultado.codigos_razones


def test_monoparental_afiliado_y_no_afiliado_disparan_codigos_distintos(make_usuario):
    afiliado = scoring.calcular_score(make_usuario(), family_structure="Monoparental Joven")
    no_afiliado = scoring.calcular_score(
        make_usuario(**{"Afiliado a colsubsidio": "No"}), family_structure="Monoparental Joven"
    )

    assert scoring.RC_MONOPARENTAL_AFILIADO in afiliado.codigos_razones
    assert scoring.RC_MONOPARENTAL_NO_AFILIADO not in afiliado.codigos_razones

    assert scoring.RC_MONOPARENTAL_NO_AFILIADO in no_afiliado.codigos_razones
    assert scoring.RC_MONOPARENTAL_AFILIADO not in no_afiliado.codigos_razones


def test_credito_insuficiente_no_vis_dispara_su_codigo(make_usuario):
    usuario = make_usuario(
        **{
            "Rango salarial": "de 9.000.000 - 10.000.000",
            "Reportado en data crédito": "Reportado",
        }
    )
    resultado = scoring.calcular_score(usuario)
    assert scoring.RC_CREDITO_INSUFICIENTE_NO_VIS in resultado.codigos_razones


def test_reportado_datacredito_dispara_su_codigo(make_usuario):
    resultado = scoring.calcular_score(make_usuario(**{"Reportado en data crédito": "Reportado"}))
    assert scoring.RC_REPORTADO_DATACREDITO in resultado.codigos_razones


def test_peers_suficientes_disparan_rc_peers_similares(make_usuario, monkeypatch):
    peers = pd.DataFrame(
        {"Estado de vivienda propia": ["Con vivienda propia", "Con vivienda propia", "Rechazado"]}
    )
    monkeypatch.setattr(data_store, "peers_con_perfil_similar", lambda usuario: peers)

    resultado = scoring.calcular_score(make_usuario())
    assert scoring.RC_PEERS_SIMILARES in resultado.codigos_razones


def test_pocos_peers_no_disparan_rc_peers_similares(make_usuario):
    resultado = scoring.calcular_score(make_usuario())  # sin_peers (fixture autouse)
    assert scoring.RC_PEERS_SIMILARES not in resultado.codigos_razones


def test_subsidios_elegibles_disparan_su_codigo(make_usuario, monkeypatch):
    subsidio = subsidios.Subsidio(nombre="Mi Casa Ya", requisito_salarial_texto="De 0 a 4 SMMLV")
    monkeypatch.setattr(subsidios, "evaluar_subsidios", lambda usuario: [subsidio])

    resultado = scoring.calcular_score(make_usuario())
    assert scoring.RC_SUBSIDIOS_ELEGIBLES in resultado.codigos_razones


def test_ahorro_verificado_y_declarado_son_mutuamente_excluyentes(make_usuario):
    from app import config

    verificado = scoring.calcular_score(
        make_usuario(ahorros=config.AHORRO_VERIFICADO_TECHO_COP),
        datos_declarados={"ahorro_cuota_inicial": True},
    )
    assert scoring.RC_AHORRO_VERIFICADO in verificado.codigos_razones
    assert scoring.RC_AHORRO_DECLARADO not in verificado.codigos_razones

    declarado = scoring.calcular_score(
        make_usuario(), datos_declarados={"ahorro_cuota_inicial": True}
    )
    assert scoring.RC_AHORRO_DECLARADO in declarado.codigos_razones
    assert scoring.RC_AHORRO_VERIFICADO not in declarado.codigos_razones


# ---------------------------------------------------------------------
# Leads sin registro
# ---------------------------------------------------------------------

def test_sin_datos_declarados_produce_los_tres_codigos_en_orden():
    resultado = scoring.calcular_score_no_registrado()
    assert resultado.codigos_razones == [
        scoring.RC_NO_ENCONTRADO_EN_SISTEMA,
        scoring.RC_SIN_DATOS_DECLARADOS,
        scoring.RC_PENALIZACION_FIJA_NO_REGISTRADO,
    ]


def test_con_datos_declarados_empieza_y_termina_con_los_codigos_esperados():
    resultado = scoring.calcular_score_no_registrado(
        {"situacion_laboral": "empleado_formal", "ingresos_mensuales_aprox": 6_000_000}
    )
    assert resultado.codigos_razones[0] == scoring.RC_NO_ENCONTRADO_EN_SISTEMA
    assert resultado.codigos_razones[-1] == scoring.RC_FACTOR_CONFIANZA_DECLARADO
    assert scoring.RC_INGRESO_BASE in resultado.codigos_razones
