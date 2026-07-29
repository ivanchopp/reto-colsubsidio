"""Deteccion de conflictos entre lo declarado en la conversacion y los datos
verificados de la base (app/scoring._detectar_conflictos).

Puramente informativo: un conflicto se agrega a razones/codigos_razones y a
ResultadoScoring.conflictos, pero nunca cambia el score -- puede ser un dato
de base desactualizado o una extraccion del LLM incorrecta, y en ambos casos
lo que corresponde es que un asesor lo revise, no que el sistema decida por
su cuenta cual fuente tiene razon.
"""
import pytest

from app import config, scoring


# ---------------------------------------------------------------------
# situacion_laboral vs Estado laboral
# ---------------------------------------------------------------------

def test_situacion_laboral_declarada_contradice_la_base(make_usuario):
    usuario = make_usuario(**{"Estado laboral": "Desempleado", "Tipo de contrato": "N/A"})
    resultado = scoring.calcular_score(usuario, datos_declarados={"situacion_laboral": "empleado_formal"})

    campos = [c["campo"] for c in resultado.conflictos]
    assert "situacion_laboral" in campos
    assert scoring.RC_CONFLICTO_SITUACION_LABORAL in resultado.codigos_razones


def test_situacion_laboral_declarada_coincide_con_la_base_no_es_conflicto(make_usuario):
    usuario = make_usuario()  # Empleado / Indefinido (default de la fixture)
    resultado = scoring.calcular_score(usuario, datos_declarados={"situacion_laboral": "empleado_formal"})
    assert resultado.conflictos == []


def test_sin_situacion_laboral_declarada_no_hay_conflicto_que_marcar(make_usuario):
    usuario = make_usuario(**{"Estado laboral": "Desempleado", "Tipo de contrato": "N/A"})
    resultado = scoring.calcular_score(usuario)  # sin datos_declarados
    assert resultado.conflictos == []


# ---------------------------------------------------------------------
# ingresos_mensuales_aprox vs Rango salarial
# ---------------------------------------------------------------------

def test_ingreso_declarado_muy_fuera_del_rango_de_la_base_es_conflicto(make_usuario):
    usuario = make_usuario(**{"Rango salarial": "de 4.000.000 - 5.000.000"})
    resultado = scoring.calcular_score(
        usuario, datos_declarados={"ingresos_mensuales_aprox": 12_000_000}
    )
    campos = [c["campo"] for c in resultado.conflictos]
    assert "ingresos_mensuales_aprox" in campos
    assert scoring.RC_CONFLICTO_INGRESO in resultado.codigos_razones


def test_ingreso_declarado_dentro_del_rango_no_es_conflicto(make_usuario):
    usuario = make_usuario(**{"Rango salarial": "de 4.000.000 - 5.000.000"})
    resultado = scoring.calcular_score(
        usuario, datos_declarados={"ingresos_mensuales_aprox": 4_500_000}
    )
    assert resultado.conflictos == []


def test_ingreso_declarado_cerca_del_borde_no_es_conflicto(make_usuario):
    """El rango es un bucket, no un numero exacto: un poco por fuera del
    borde no deberia dispararlo (ver TOLERANCIA_INGRESO_DECLARADO_PCT)."""
    usuario = make_usuario(**{"Rango salarial": "de 4.000.000 - 5.000.000"})
    resultado = scoring.calcular_score(
        usuario, datos_declarados={"ingresos_mensuales_aprox": 5_200_000}
    )
    assert resultado.conflictos == []


# ---------------------------------------------------------------------
# ahorro_cuota_inicial (declarado) vs ahorros (verificado en la base)
# ---------------------------------------------------------------------

def test_declara_ahorro_pero_la_base_muestra_casi_nada_es_conflicto(make_usuario):
    usuario = make_usuario(ahorros=100_000)
    resultado = scoring.calcular_score(usuario, datos_declarados={"ahorro_cuota_inicial": True})

    campos = [c["campo"] for c in resultado.conflictos]
    assert "ahorro_cuota_inicial" in campos
    assert scoring.RC_CONFLICTO_AHORRO in resultado.codigos_razones


def test_declara_no_tener_ahorro_pero_la_base_muestra_bastante_es_conflicto(make_usuario):
    usuario = make_usuario(ahorros=8_000_000)
    resultado = scoring.calcular_score(usuario, datos_declarados={"ahorro_cuota_inicial": False})

    campos = [c["campo"] for c in resultado.conflictos]
    assert "ahorro_cuota_inicial" in campos


def test_ahorro_en_zona_neutra_no_es_conflicto_en_ningun_sentido(make_usuario):
    usuario = make_usuario(ahorros=1_500_000)  # entre los dos umbrales
    con_true = scoring.calcular_score(usuario, datos_declarados={"ahorro_cuota_inicial": True})
    con_false = scoring.calcular_score(usuario, datos_declarados={"ahorro_cuota_inicial": False})

    assert con_true.conflictos == []
    assert con_false.conflictos == []


def test_sin_ahorros_verificados_en_la_base_no_hay_con_que_comparar(make_usuario):
    usuario = make_usuario()  # sin columna "ahorros"
    resultado = scoring.calcular_score(usuario, datos_declarados={"ahorro_cuota_inicial": True})
    assert resultado.conflictos == []


# ---------------------------------------------------------------------
# tiene_vivienda vs Estado de vivienda propia
# ---------------------------------------------------------------------

def test_declara_no_tener_vivienda_pero_la_base_dice_que_si_es_conflicto(make_usuario):
    usuario = make_usuario(**{"Estado de vivienda propia": "Con vivienda propia"})
    resultado = scoring.calcular_score(usuario, datos_declarados={"tiene_vivienda": False})

    campos = [c["campo"] for c in resultado.conflictos]
    assert "tiene_vivienda" in campos
    assert scoring.RC_CONFLICTO_VIVIENDA in resultado.codigos_razones


def test_declara_tener_vivienda_pero_la_base_dice_que_no_es_conflicto(make_usuario):
    usuario = make_usuario(**{"Estado de vivienda propia": "Sin vivienda"})
    resultado = scoring.calcular_score(usuario, datos_declarados={"tiene_vivienda": True})

    campos = [c["campo"] for c in resultado.conflictos]
    assert "tiene_vivienda" in campos


def test_valores_ambiguos_de_vivienda_en_la_base_no_disparan_conflicto(make_usuario):
    """Desistido/Rechazado describen el desenlace de un proceso pasado, no si
    hoy tiene vivienda -- comparar contra eso daria falsos positivos."""
    usuario = make_usuario(**{"Estado de vivienda propia": "Desistido"})
    con_true = scoring.calcular_score(usuario, datos_declarados={"tiene_vivienda": True})
    con_false = scoring.calcular_score(usuario, datos_declarados={"tiene_vivienda": False})

    assert con_true.conflictos == []
    assert con_false.conflictos == []


# ---------------------------------------------------------------------
# Los conflictos son informativos: nunca cambian el score
# ---------------------------------------------------------------------

def test_un_conflicto_no_cambia_el_score(make_usuario):
    usuario = make_usuario(**{"Estado laboral": "Desempleado", "Tipo de contrato": "N/A"})
    sin_declarar = scoring.calcular_score(usuario)
    con_conflicto = scoring.calcular_score(
        usuario, datos_declarados={"situacion_laboral": "empleado_formal"}
    )
    assert con_conflicto.score == sin_declarar.score


def test_conflictos_quedan_en_razones_y_codigos_en_el_mismo_orden(make_usuario):
    usuario = make_usuario(**{"Estado laboral": "Desempleado", "Tipo de contrato": "N/A"})
    resultado = scoring.calcular_score(
        usuario, datos_declarados={"situacion_laboral": "empleado_formal"}
    )
    assert len(resultado.razones) == len(resultado.codigos_razones)
    assert resultado.codigos_razones[0] == scoring.RC_CONFLICTO_SITUACION_LABORAL


# ---------------------------------------------------------------------
# Un lead sin registro nunca puede tener conflictos: no hay con que comparar
# ---------------------------------------------------------------------

def test_calcular_score_no_registrado_nunca_tiene_conflictos():
    resultado = scoring.calcular_score_no_registrado(
        {"situacion_laboral": "empleado_formal", "ingresos_mensuales_aprox": 6_000_000}
    )
    assert resultado.conflictos == []


def test_calcular_score_no_registrado_sin_datos_tampoco_tiene_conflictos():
    assert scoring.calcular_score_no_registrado().conflictos == []
