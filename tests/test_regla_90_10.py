"""Pruebas dedicadas a la regla 90/10 (penalizacion a leads no afiliados a
Colsubsidio) en app/scoring.py. Complementan test_scoring.py verificando el
coeficiente exacto de la penalizacion en cada segmento, no solo que el score
"baja", y que el texto de la razon aparece unicamente cuando corresponde.

Recordatorio de la regla, tal como esta implementada:
  - VIS:    si no afiliado -> score_reglas *= 0.2  (penalizacion severa, casi excluyente)
  - No VIS: si no afiliado -> score_reglas *= 0.8  (mas leve; ademas pierde el bono de +5)

El score final que devuelve calcular_score() no es score_reglas puro: se
blendea con similitud vectorial (peso 0.2, aqui estubeada a 50.0 via el
fixture autouse `vectorial_neutro`) y con peer-matching si hay >=3 peers
(aqui no los hay, via `sin_peers`). Con esas dos senales fijas, el blend
final es predecible: score_final = 0.8 * score_reglas + 10. Las pruebas de
coeficiente exacto verifican el 0.2/0.8 componiendo esa formula conocida,
en vez de comparar contra el score final en crudo.
"""
import pytest

from app import scoring

RAZON_90_10 = "regla 90/10"
PESO_REGLAS_SIN_PEERS = 0.8  # 0.6 base + 0.2 que le vuelve al no haber peers
PISO_VECTORIAL = 0.2 * 50.0  # peso vectorial * stub neutro de vectorial_neutro


def _blend_esperado(score_reglas: float) -> float:
    return PESO_REGLAS_SIN_PEERS * score_reglas + PISO_VECTORIAL


def _score_reglas_puro(usuario: dict) -> tuple[float, str]:
    """Replica a mano el score de reglas (antes del blend con peers/vectorial),
    para poder verificar el coeficiente exacto sin acoplarse a otros numeros
    magicos del modulo."""
    ingreso = scoring._midpoint_rango_salarial(usuario["Rango salarial"])
    ingreso_smlv = ingreso / scoring.config.SMLV_COP
    segmento = "VIS" if ingreso_smlv <= scoring.SEGMENTO_INCOME_THRESHOLD_SMLV else "No VIS"
    peso = 0.4 if segmento == "VIS" else 0.7
    techo = scoring.SEGMENTO_INCOME_THRESHOLD_SMLV if segmento == "VIS" else 6.0
    base = peso * min(ingreso_smlv / techo, 1.0) * 100
    tier = scoring._employer_tier(usuario)
    return base * scoring.EMPLOYER_TIER_MULTIPLIER[tier], segmento


# ---------------------------------------------------------------------
# Coeficiente exacto de la penalizacion
# ---------------------------------------------------------------------

def test_regla_90_10_vis_penaliza_multiplicando_por_0_2(make_usuario):
    afiliado = make_usuario(**{"Rango salarial": "de 2.000.000 - 3.000.000"})
    no_afiliado = make_usuario(**{"Rango salarial": "de 2.000.000 - 3.000.000", "Afiliado a colsubsidio": "No"})

    x, segmento = _score_reglas_puro(afiliado)
    assert segmento == "VIS"

    resultado_afiliado = scoring.calcular_score(afiliado)
    resultado_no_afiliado = scoring.calcular_score(no_afiliado)

    # afiliado no recibe la penalizacion: su score de reglas es x tal cual
    assert resultado_afiliado.score == pytest.approx(_blend_esperado(x), abs=0.1)
    # no afiliado: score de reglas queda multiplicado por 0.2
    assert resultado_no_afiliado.score == pytest.approx(_blend_esperado(x * 0.2), abs=0.1)


def test_regla_90_10_no_vis_penaliza_multiplicando_por_0_8(make_usuario):
    afiliado = make_usuario(**{"Rango salarial": "de 9.000.000 - 10.000.000"})
    no_afiliado = make_usuario(**{"Rango salarial": "de 9.000.000 - 10.000.000", "Afiliado a colsubsidio": "No"})

    x, segmento = _score_reglas_puro(afiliado)
    assert segmento == "No VIS"

    resultado_afiliado = scoring.calcular_score(afiliado)
    resultado_no_afiliado = scoring.calcular_score(no_afiliado)

    # el afiliado ademas recibe el bono de +5 (no forma parte de la regla 90/10)
    assert resultado_afiliado.score == pytest.approx(_blend_esperado(x + 5), abs=0.1)
    # no afiliado: pierde el bono de +5 y su score de reglas queda multiplicado por 0.8
    assert resultado_no_afiliado.score == pytest.approx(_blend_esperado(x * 0.8), abs=0.1)


# ---------------------------------------------------------------------
# Monotonicidad: a igualdad de todo lo demas, no afiliado nunca debe
# puntuar mejor que afiliado, en ningun segmento ni nivel de ingreso.
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "rango_salarial",
    [
        "de 0 - 1.750.905",
        "de 1.750.905 - 3.501.810",
        "de 3.501.810 - 5.252.715",
        "de 5.252.715 - 7.003.620",
        "de 9.000.000 - 10.000.000",
    ],
)
def test_afiliado_nunca_puntua_peor_que_no_afiliado(make_usuario, rango_salarial):
    afiliado = make_usuario(**{"Rango salarial": rango_salarial})
    no_afiliado = make_usuario(**{"Rango salarial": rango_salarial, "Afiliado a colsubsidio": "No"})

    score_afiliado = scoring.calcular_score(afiliado).score
    score_no_afiliado = scoring.calcular_score(no_afiliado).score

    assert score_afiliado >= score_no_afiliado


# ---------------------------------------------------------------------
# Trazabilidad: la razon debe aparecer solo cuando se aplico la penalizacion
# ---------------------------------------------------------------------

def test_razon_90_10_aparece_solo_para_no_afiliado(make_usuario):
    afiliado = make_usuario()
    no_afiliado = make_usuario(**{"Afiliado a colsubsidio": "No"})

    razones_afiliado = " | ".join(scoring.calcular_score(afiliado).razones)
    razones_no_afiliado = " | ".join(scoring.calcular_score(no_afiliado).razones)

    assert RAZON_90_10 not in razones_afiliado
    assert RAZON_90_10 in razones_no_afiliado


def test_razon_90_10_aparece_en_no_vis_no_afiliado(make_usuario):
    no_afiliado = make_usuario(
        **{"Rango salarial": "de 9.000.000 - 10.000.000", "Afiliado a colsubsidio": "No"}
    )
    resultado = scoring.calcular_score(no_afiliado)
    assert any(RAZON_90_10 in r for r in resultado.razones)


# ---------------------------------------------------------------------
# Caso combinado: no afiliado + historial crediticio insuficiente en No VIS.
# El score de reglas queda anulado (0) por credito antes de que la
# penalizacion 90/10 pueda aplicar sobre el; no debe quedar negativo, y el
# unico valor positivo que sobrevive es el piso del blend vectorial.
# ---------------------------------------------------------------------

def test_no_afiliado_con_credito_insuficiente_score_de_reglas_queda_en_cero(make_usuario):
    usuario = make_usuario(
        **{
            "Rango salarial": "de 9.000.000 - 10.000.000",
            "Afiliado a colsubsidio": "No",
            "Reportado en data crédito": "Reportado",
        }
    )
    resultado = scoring.calcular_score(usuario)

    # score de reglas = 0 (anulado por credito); el score final es solo el
    # piso que aporta el blend con el stub vectorial neutro (0.8*0 + 10)
    assert resultado.score == pytest.approx(_blend_esperado(0.0), abs=0.1)
    assert resultado.segmento_lead == "FRIO"
    assert any("score anulado" in r for r in resultado.razones)
    assert any(RAZON_90_10 in r for r in resultado.razones)
