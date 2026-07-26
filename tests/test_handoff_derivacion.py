import pytest
from app import handoff, scoring


@pytest.mark.parametrize("segmento, esperado", [
    ("CALIENTE", True), ("TIBIO", True), ("FRIO", False),
])
def test_solo_se_derivan_caliente_y_tibio(make_usuario, segmento, esperado):
    r = scoring.calcular_score(make_usuario())
    r.segmento_lead = segmento
    assert handoff.debe_derivar_al_asesor(r) is esperado


def test_sin_scoring_no_se_deriva():
    assert handoff.debe_derivar_al_asesor(None) is False
