"""Pruebas de las funciones puras de leads_store (no tocan la base de datos,
asi que no necesitan fixtures de Supabase): estadisticas del dia, cupo
regulatorio 90/10, calidad por canal y normalizacion del origen."""
import pytest

from app import leads_store


def _lead(segmento=None, *, registrado=True, afiliado=None, origen=None):
    return {
        "segmento_lead": segmento,
        "usuario_registrado": registrado,
        "afiliado": afiliado,
        "origen": origen,
    }


# ---------------------------------------------------------------------
# calcular_stats
# ---------------------------------------------------------------------

def test_calcular_stats_vacio():
    stats = leads_store.calcular_stats([])
    assert stats["total"] == 0
    assert stats["por_segmento"] == {}
    assert stats["cuota_90_10"]["derivables"] == 0


def test_calcular_stats_mezcla_de_segmentos():
    leads = [_lead(s) for s in ("CALIENTE", "CALIENTE", "TIBIO", "FRIO", "FRIO", "FRIO")]
    stats = leads_store.calcular_stats(leads)

    assert stats["total"] == 6
    assert stats["por_segmento"] == {"CALIENTE": 2, "TIBIO": 1, "FRIO": 3}


def test_calcular_stats_agrupa_segmento_none_como_sin_datos():
    leads = [_lead(None), _lead(None), _lead("CALIENTE")]
    stats = leads_store.calcular_stats(leads)

    assert stats["por_segmento"] == {"SIN_DATOS": 2, "CALIENTE": 1}


# ---------------------------------------------------------------------
# Cupo regulatorio 90/10
# ---------------------------------------------------------------------

def test_cuota_solo_cuenta_los_derivables():
    """Un no afiliado FRIO no consume cupo: nunca llega al asesor."""
    leads = [
        _lead("CALIENTE", afiliado=True),
        _lead("FRIO", afiliado=False),
        _lead("TIBIO", afiliado=False),
    ]
    cuota = leads_store.calcular_cuota_90_10(leads)

    assert cuota["derivables"] == 1
    assert cuota["no_afiliados"] == 0


def test_cuota_marca_excedido_cuando_pasa_del_10_por_ciento():
    # 10 derivables -> cupo de 1 no afiliado; hay 2
    leads = [_lead("CALIENTE", afiliado=True) for _ in range(8)]
    leads += [_lead("CALIENTE", afiliado=False) for _ in range(2)]
    cuota = leads_store.calcular_cuota_90_10(leads)

    assert cuota["derivables"] == 10
    assert cuota["cupo_no_afiliados"] == 1
    assert cuota["no_afiliados"] == 2
    assert cuota["excedido"] is True
    assert cuota["cupo_disponible"] == 0


def test_cuota_dentro_del_limite_no_marca_excedido():
    leads = [_lead("CALIENTE", afiliado=True) for _ in range(19)]
    leads.append(_lead("CALIENTE", afiliado=False))
    cuota = leads_store.calcular_cuota_90_10(leads)

    assert cuota["cupo_no_afiliados"] == 2
    assert cuota["no_afiliados"] == 1
    assert cuota["excedido"] is False
    assert cuota["cupo_disponible"] == 1


def test_lead_sin_registro_no_cuenta_como_afiliado():
    """No se puede verificar su afiliacion; frente a una cuota regulatoria el
    criterio conservador es no asumirla."""
    cuota = leads_store.calcular_cuota_90_10(
        [_lead("CALIENTE", registrado=False, afiliado=None)]
    )
    assert cuota["no_afiliados"] == 1


def test_cuota_sin_derivables_no_divide_por_cero():
    cuota = leads_store.calcular_cuota_90_10([_lead("FRIO", afiliado=True)])
    assert cuota["derivables"] == 0
    assert cuota["pct_no_afiliados"] == 0.0
    assert cuota["excedido"] is False


# ---------------------------------------------------------------------
# Calidad por canal
# ---------------------------------------------------------------------

def test_calidad_por_origen_calcula_porcentaje_de_calientes():
    leads = [
        _lead("CALIENTE", origen="organico"),
        _lead("FRIO", origen="organico"),
        _lead("FRIO", origen="meta"),
        _lead("FRIO", origen="meta"),
        _lead("FRIO", origen="meta"),
        _lead("CALIENTE", origen="meta"),
    ]
    por_origen = {o["origen"]: o for o in leads_store.calcular_calidad_por_origen(leads)}

    assert por_origen["organico"]["pct_calientes"] == 50.0
    assert por_origen["meta"]["pct_calientes"] == 25.0


def test_calidad_por_origen_ordena_por_volumen():
    leads = [_lead("FRIO", origen="meta") for _ in range(3)]
    leads.append(_lead("FRIO", origen="google"))
    orden = [o["origen"] for o in leads_store.calcular_calidad_por_origen(leads)]

    assert orden[0] == "meta"


def test_calidad_por_origen_agrupa_los_sin_origen():
    leads = [{"segmento_lead": "FRIO"}, {"segmento_lead": "FRIO", "origen": None}]
    por_origen = leads_store.calcular_calidad_por_origen(leads)

    assert len(por_origen) == 1
    assert por_origen[0]["origen"] == "desconocido"


# ---------------------------------------------------------------------
# normalizar_origen
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("meta", "meta"),
        ("  Google  ", "google"),
        ("WHATSAPP", "whatsapp"),
        ("contact_center", "contact_center"),
        (None, "organico"),
        ("", "organico"),
        ("tiktok", "organico"),        # canal desconocido, no se guarda texto libre
        ("'; drop table leads--", "organico"),
    ],
)
def test_normalizar_origen(entrada, esperado):
    assert leads_store.normalizar_origen(entrada) == esperado


def test_cupo_se_redondea_en_volumenes_bajos():
    """Con 8 derivables el 10% es 0.8: truncar daria cupo 0 y cualquier no
    afiliado marcaria 'excedido'. Se redondea a 1."""
    leads = [_lead("CALIENTE", afiliado=True) for _ in range(7)]
    leads.append(_lead("CALIENTE", afiliado=False))
    cuota = leads_store.calcular_cuota_90_10(leads)

    assert cuota["cupo_no_afiliados"] == 1
    assert cuota["excedido"] is False
