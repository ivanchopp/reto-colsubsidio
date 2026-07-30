"""Pruebas unitarias rapidas para app/scoring.py (la calculadora de
viabilidad). Cubren las reglas de negocio documentadas en el modulo:
umbral VIS/No VIS, tiers de estabilidad laboral, penalizacion por
desempleo, regla 90/10, bono/penalizacion de hogar monoparental joven,
umbral de historial crediticio en No VIS, penalizacion por reporte en
datacredito, y el blending con peers de perfil similar y con similitud
vectorial contra centroides.

No dependen del Excel real (ver fixtures `sin_peers` y `vectorial_neutro`
en conftest.py). Con ambas senales externas fijas (sin peers, vectorial
estubeado en 50.0), el score final de cualquier escenario sin peer-match
es 0.8 * score_de_reglas + 10 (0.6 reglas + 0.2 que le vuelve al no haber
peers, mas 0.2 * 50 del piso vectorial) — de ahi salen los numeros de
abajo.
"""
import pandas as pd
import pytest

from app import config, data_store, scoring


# ---------------------------------------------------------------------
# _midpoint_rango_salarial
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "rango, esperado",
    [
        ("de 4.000.000 - 5.000.000", 4_500_000.0),
        ("De 1.000.000 - 1.500.000", 1_250_000.0),
        ("", 0.0),
        ("sin dato", 0.0),
        ("4000000", 0.0),  # sin rango (falta el "-"), no se puede promediar
    ],
)
def test_midpoint_rango_salarial(rango, esperado):
    assert scoring._midpoint_rango_salarial(rango) == esperado


# ---------------------------------------------------------------------
# _employer_tier
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "estado, contrato, tier_esperado",
    [
        ("Empleado", "Indefinido", "Tier 1"),
        ("Empleado", "Fijo", "Tier 2"),
        ("Empleado", "Obra y labor", "Tier 3"),
        ("Independiente", "N/A", "Tier 3"),
        ("Desempleado", "N/A", "Tier 3"),
    ],
)
def test_employer_tier(estado, contrato, tier_esperado):
    usuario = {"Estado laboral": estado, "Tipo de contrato": contrato}
    assert scoring._employer_tier(usuario) == tier_esperado


# ---------------------------------------------------------------------
# calcular_score: reglas de negocio principales
# ---------------------------------------------------------------------

def test_no_vis_saturado_afiliado_tier1_es_caliente(make_usuario):
    usuario = make_usuario(
        **{"Rango salarial": "de 9.000.000 - 10.000.000"}  # 6.67 SMLV -> No VIS, satura el techo (6.0)
    )
    resultado = scoring.calcular_score(usuario)

    assert resultado.project_segment == "No VIS"
    assert resultado.score == pytest.approx(78.4)
    assert resultado.segmento_lead == "CALIENTE"


def test_no_vis_no_afiliado_tier3_es_tibio(make_usuario):
    usuario = make_usuario(
        **{
            "Rango salarial": "de 9.000.000 - 10.000.000",
            "Estado laboral": "Independiente",
            "Tipo de contrato": "N/A",
            "Afiliado a colsubsidio": "No",
        }
    )
    resultado = scoring.calcular_score(usuario)

    assert resultado.project_segment == "No VIS"
    assert resultado.score == pytest.approx(48.1)
    assert resultado.segmento_lead == "TIBIO"
    assert any("regla 90/10" in r for r in resultado.razones)


def test_desempleado_penaliza_fuerte_y_cae_a_frio(make_usuario):
    usuario = make_usuario(**{"Estado laboral": "Desempleado", "Tipo de contrato": "N/A"})
    resultado = scoring.calcular_score(usuario)

    # 3.16 SMLV satura el techo VIS (3.1) -> base 40; Tier 3 x0.85 = 34;
    # desempleado x0.15 = 5.1; blend 0.8*5.1 + 10 = 14.1
    assert resultado.score == pytest.approx(14.1)
    assert resultado.segmento_lead == "FRIO"
    assert any("Sin empleo activo" in r for r in resultado.razones)


def test_vis_no_afiliado_regla_90_10(make_usuario):
    usuario = make_usuario(**{"Afiliado a colsubsidio": "No"})
    resultado = scoring.calcular_score(usuario)

    assert resultado.project_segment == "VIS"
    # base 40; Tier 1 x1.15 = 46; no afiliado en VIS x0.2 = 9.2;
    # blend 0.8*9.2 + 10 = 17.4
    assert resultado.score == pytest.approx(17.4)
    assert any("regla 90/10" in r for r in resultado.razones)


def test_vis_monoparental_joven_afiliado_suma_20(make_usuario):
    usuario = make_usuario()
    resultado = scoring.calcular_score(usuario, family_structure="Monoparental Joven")

    # base 40; Tier 1 x1.15 = 46; monoparental joven afiliado +20 = 66;
    # blend 0.8*66 + 10 = 62.8
    assert resultado.score == pytest.approx(62.8)
    assert resultado.segmento_lead == "CALIENTE"


def test_vis_monoparental_joven_no_afiliado_resta_30_y_score_de_reglas_no_baja_de_cero(make_usuario):
    usuario = make_usuario(**{"Afiliado a colsubsidio": "No"})
    resultado = scoring.calcular_score(usuario, family_structure="Monoparental Joven")

    # el -30 deja el score de reglas clampeado en 0; el score final que
    # queda es solo el piso del blend con el stub vectorial neutro (0.8*0+10)
    assert resultado.score == pytest.approx(10.0)
    assert resultado.segmento_lead == "FRIO"


def test_no_vis_credit_score_insuficiente_anula_score(make_usuario):
    usuario = make_usuario(
        **{
            "Rango salarial": "de 9.000.000 - 10.000.000",
            "Reportado en data crédito": "Reportado",
        }
    )
    resultado = scoring.calcular_score(usuario)

    assert resultado.project_segment == "No VIS"
    assert resultado.score == pytest.approx(10.0)
    assert any("score anulado" in r for r in resultado.razones)


def test_reportado_datacredito_penaliza_tambien_en_vis(make_usuario):
    usuario = make_usuario(**{"Reportado en data crédito": "Reportado"})
    resultado = scoring.calcular_score(usuario)

    # base 40; Tier 1 x1.15 = 46; reportado x0.10 = 4.6;
    # blend 0.8*4.6 + 10 = 13.7
    assert resultado.score == pytest.approx(13.7)
    assert any("casi eliminatoria" in r for r in resultado.razones)


# ---------------------------------------------------------------------
# calcular_score: blending con peers de perfil similar
# ---------------------------------------------------------------------

def test_peer_blend_con_4_peers_encoge_la_tasa_y_el_peso(make_usuario, monkeypatch):
    peers = pd.DataFrame(
        {
            "Estado de vivienda propia": [
                "Con vivienda propia",
                "Con vivienda propia",
                "Desistido",
                "Rechazado",
            ]
        }
    )
    monkeypatch.setattr(data_store, "peers_con_perfil_similar", lambda usuario: peers)

    usuario = make_usuario(**{"Rango salarial": "de 9.000.000 - 10.000.000"})  # score de reglas puro: 85.5
    resultado = scoring.calcular_score(usuario)

    # shrinkage n/(n+10) con n=4 peers, tasa observada 50.0%, base 26.0% (via
    # el fixture tasa_base_fija): confianza = 4/14 = 0.2857; tasa ajustada =
    # 0.2857*50 + 0.7143*26 = 32.857; lift = 32.857/26*50 = 63.187.
    # peso_peers_efectivo = 0.2*0.2857 = 0.05714; el resto (0.14286) vuelve a
    # reglas: pesos = {reglas: 0.74286, peers: 0.05714, vectorial: 0.2}.
    # 0.74286*85.5 + 0.05714*63.187 + 0.2*50.0(stub vectorial) = 77.1
    assert resultado.score == pytest.approx(77.1, abs=0.1)
    assert resultado.peer_stats["total_peers"] == 4
    assert resultado.peer_stats["pct_con_vivienda_propia"] == 50.0
    assert resultado.peer_stats["confianza"] == pytest.approx(4 / 14, abs=0.001)


def test_peer_blend_con_pocos_peers_pesa_menos_que_con_muchos(make_usuario, monkeypatch):
    """El shrinkage es gradual, no un corte binario: menos peers deberia
    pesar menos en el blend que mas peers, sin caer necesariamente a cero."""
    usuario = make_usuario(**{"Rango salarial": "de 9.000.000 - 10.000.000"})

    peers_pocos = pd.DataFrame({"Estado de vivienda propia": ["Con vivienda propia", "Rechazado"]})
    monkeypatch.setattr(data_store, "peers_con_perfil_similar", lambda usuario: peers_pocos)
    con_2_peers = scoring.calcular_score(usuario)

    peers_muchos = pd.DataFrame(
        {"Estado de vivienda propia": ["Con vivienda propia"] * 20 + ["Rechazado"] * 20}
    )
    monkeypatch.setattr(data_store, "peers_con_perfil_similar", lambda usuario: peers_muchos)
    con_40_peers = scoring.calcular_score(usuario)

    assert con_2_peers.peer_stats["confianza"] < con_40_peers.peer_stats["confianza"]
    contribucion_2 = next(c for c in con_2_peers.contribuciones if c["categoria"] == "peers")
    contribucion_40 = next(c for c in con_40_peers.contribuciones if c["categoria"] == "peers")
    assert contribucion_2["peso"] < contribucion_40["peso"]


# ---------------------------------------------------------------------
# _tasa_peers_con_shrinkage: la formula de shrinkage en aislamiento
# ---------------------------------------------------------------------

def test_shrinkage_sin_peers_da_exactamente_la_tasa_base(monkeypatch):
    monkeypatch.setattr(data_store, "tasa_base_conversion", lambda: 26.0)
    assert scoring._tasa_peers_con_shrinkage(conversion_peers=90.0, total_peers=0) == 26.0


def test_shrinkage_con_muchos_peers_se_acerca_a_la_tasa_observada(monkeypatch):
    monkeypatch.setattr(data_store, "tasa_base_conversion", lambda: 26.0)
    tasa = scoring._tasa_peers_con_shrinkage(conversion_peers=90.0, total_peers=10_000)
    assert tasa == pytest.approx(90.0, abs=0.1)


def test_shrinkage_a_mitad_del_pseudo_conteo_es_el_promedio_simple(monkeypatch):
    """Con n == PSEUDO_CONTEO_PEERS, la formula n/(n+k) da exactamente 0.5:
    la tasa ajustada es el punto medio entre lo observado y la base."""
    monkeypatch.setattr(data_store, "tasa_base_conversion", lambda: 26.0)
    tasa = scoring._tasa_peers_con_shrinkage(
        conversion_peers=90.0, total_peers=scoring.PSEUDO_CONTEO_PEERS
    )
    assert tasa == pytest.approx((90.0 + 26.0) / 2)


def test_sin_peers_todo_el_peso_de_esa_senal_vuelve_a_reglas(make_usuario):
    usuario = make_usuario(**{"Rango salarial": "de 9.000.000 - 10.000.000"})  # score de reglas puro: 85.5
    resultado = scoring.calcular_score(usuario)  # sin_peers (fixture autouse): 0 peers

    # confianza 0 -> peso_peers_efectivo 0 -> todo PESO_PEERS vuelve a reglas:
    # 0.8*85.5 + 0.2*50.0(stub vectorial) = 78.4
    assert resultado.score == pytest.approx(78.4)
    assert resultado.peer_stats["total_peers"] == 0
    assert resultado.peer_stats["confianza"] == 0.0
    assert not any(c["categoria"] == "peers" for c in resultado.contribuciones)


# ---------------------------------------------------------------------
# calcular_score_no_registrado: penalizacion fija para leads sin registro
# ---------------------------------------------------------------------

def test_calcular_score_no_registrado_es_penalizacion_fija_y_fria():
    resultado = scoring.calcular_score_no_registrado()

    assert resultado.score == scoring.SCORE_NO_REGISTRADO
    assert resultado.segmento_lead == "FRIO"
    assert resultado.subsidios_elegibles == []
    assert len(resultado.razones) >= 1


# ---------------------------------------------------------------------
# scoring_version: auditoria de con que configuracion salio un score
# ---------------------------------------------------------------------

def test_calcular_score_incluye_la_version_de_configuracion_vigente(make_usuario):
    resultado = scoring.calcular_score(make_usuario())
    assert resultado.scoring_version == config.SCORING_VERSION


def test_calcular_score_no_registrado_incluye_la_version_de_configuracion_vigente():
    con_datos = scoring.calcular_score_no_registrado(
        {"situacion_laboral": "empleado_formal", "ingresos_mensuales_aprox": 6_000_000}
    )
    sin_datos = scoring.calcular_score_no_registrado()

    assert con_datos.scoring_version == config.SCORING_VERSION
    assert sin_datos.scoring_version == config.SCORING_VERSION
