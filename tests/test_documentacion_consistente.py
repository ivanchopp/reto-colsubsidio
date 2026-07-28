"""SOBRE MI/MIEMPRESA.md dice explicitamente: 'si el codigo y este archivo se
contradicen, gana el codigo y hay que corregir este archivo'. El problema es
que nada obligaba a corregirlo -- ya paso una vez con SYSTEMPROMPT.md (spec
obsoleta que nadie actualizo) y estuvo a punto de volver a pasar con los
umbrales al recalibrar el scoring.

Este test no valida prosa: compara los numeros de negocio que el documento
cita textualmente (pesos del blend, multiplicadores de la regla 90/10,
umbrales, cupo regulatorio) contra las constantes con nombre que los
producen. Si alguien cambia una constante y olvida actualizar el .md, esto
falla en CI en vez de quedar como una desincronizacion silenciosa.

No cubre la 'Distribucion actual' de la seccion 6 (12,0% CALIENTE / 38,0%
TIBIO / 49,9% FRIO): esos numeros salen de correr el motor sobre la base real
completa (ver scripts/calibrar_scoring.py y tests/test_distribucion_scoring.py),
no de una constante fija -- compararlos aqui duplicaria ese test de
integracion en un test que se supone rapido y sin DB.
"""
from app import config, leads_store, scoring


def _miempresa() -> str:
    """Texto de MIEMPRESA.md con saltos de linea colapsados a un espacio: el
    markdown envuelve parrafos a ~80 columnas, asi que una frase que se busca
    completa puede quedar partida en dos lineas sin que eso sea una
    desincronizacion real."""
    ruta = config.BASE_DIR / "SOBRE MI" / "MIEMPRESA.md"
    return " ".join(ruta.read_text(encoding="utf-8").split())


def _coma(valor: float) -> str:
    """Formato numerico del documento: coma decimal, sin ceros de mas
    (0.6 -> '0,6', 52.6 -> '52,6')."""
    texto = f"{valor:g}"
    return texto.replace(".", ",")


# ---------------------------------------------------------------------
# Seccion 6: pesos del blend y minimo de peers
# ---------------------------------------------------------------------

def test_peso_reglas_documentado():
    assert f"Reglas | {_coma(scoring.PESO_REGLAS)} |" in _miempresa()


def test_peso_peers_documentado():
    assert f"Peers | {_coma(scoring.PESO_PEERS)} |" in _miempresa()


def test_peso_vectorial_documentado():
    assert f"Vectorial | {_coma(scoring.PESO_VECTORIAL)} |" in _miempresa()


def test_minimo_de_peers_documentado():
    assert f"menos de {scoring.MIN_PEERS_PARA_BLEND} peers" in _miempresa()


# ---------------------------------------------------------------------
# Seccion 6: regla 90/10 (penalizacion individual)
# ---------------------------------------------------------------------

def test_multiplicador_no_afiliado_vis_documentado():
    assert (
        f"multiplica su score de reglas por {_coma(scoring.MULT_NO_AFILIADO_VIS)}"
        in _miempresa()
    )


def test_multiplicador_no_afiliado_no_vis_documentado():
    assert f"en No VIS por {_coma(scoring.MULT_NO_AFILIADO_NO_VIS)}" in _miempresa()


def test_bono_afiliado_no_vis_documentado():
    assert f"el bono de +{scoring.BONO_AFILIADO_NO_VIS:.0f}" in _miempresa()


# ---------------------------------------------------------------------
# Seccion 6: umbrales de corte
# ---------------------------------------------------------------------

def test_umbral_caliente_documentado():
    assert f"CALIENTE desde {_coma(config.UMBRAL_CALIENTE)}" in _miempresa()


def test_umbral_tibio_documentado():
    assert f"TIBIO desde {_coma(config.UMBRAL_TIBIO)}" in _miempresa()


def test_porcentaje_objetivo_caliente_documentado():
    assert f"{config.PCT_OBJETIVO_CALIENTE:.0%} superior de la" in _miempresa()


# ---------------------------------------------------------------------
# Seccion 7: cupo regulatorio 90/10 (agregado, distinto de la penalizacion
# individual de la seccion 6)
# ---------------------------------------------------------------------

def test_cupo_maximo_no_afiliados_documentado():
    assert f"contra el {leads_store.PCT_MAXIMO_NO_AFILIADOS:.0%} permitido" in _miempresa()
