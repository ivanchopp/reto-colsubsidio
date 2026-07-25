"""Pruebas de leads_store.calcular_stats -- funcion pura (no toca la base
de datos), asi que no necesita fixtures de Supabase."""
from app import leads_store


def test_calcular_stats_vacio():
    assert leads_store.calcular_stats([]) == {"total": 0, "por_segmento": {}}


def test_calcular_stats_mezcla_de_segmentos():
    leads = [
        {"segmento_lead": "CALIENTE"},
        {"segmento_lead": "CALIENTE"},
        {"segmento_lead": "TIBIO"},
        {"segmento_lead": "FRIO"},
        {"segmento_lead": "FRIO"},
        {"segmento_lead": "FRIO"},
    ]
    stats = leads_store.calcular_stats(leads)
    assert stats == {
        "total": 6,
        "por_segmento": {"CALIENTE": 2, "TIBIO": 1, "FRIO": 3},
    }


def test_calcular_stats_agrupa_score_none_como_sin_datos():
    leads = [{"segmento_lead": None}, {"segmento_lead": None}, {"segmento_lead": "CALIENTE"}]
    stats = leads_store.calcular_stats(leads)
    assert stats == {"total": 3, "por_segmento": {"SIN_DATOS": 2, "CALIENTE": 1}}
