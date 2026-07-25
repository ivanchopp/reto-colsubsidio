"""Pruebas unitarias para app/subsidios.py (elegibilidad a subsidios de
vivienda). Usan un DataFrame de subsidios pequeno y controlado en vez del
Excel real, para no romperse si alguien edita
RECURSOS/Subsidios Vivienda Colombia.xlsx.
"""
import pandas as pd
import pytest

from app import data_store, subsidios


def _subsidios_fake():
    return pd.DataFrame(
        [
            {
                "Subsidio": "Cajas de Compensación Familiar (Compra)",
                "Requisitos Salariales (SMMLV)": "De 0 a 4 SMMLV",
                "¿Permite Subsidios Anteriores?": "No",
                "¿Permite Tener Vivienda Propia?": "No",
                "¿Situación Laboral es Riesgo?": "si",
            },
            {
                "Subsidio": "Generación FNA (Jóvenes 18-28)",
                "Requisitos Salariales (SMMLV)": "Hasta 4 SMMLV (postulación conjunta)",
                "¿Permite Subsidios Anteriores?": "No",
                "¿Permite Tener Vivienda Propia?": "No",
                "¿Situación Laboral es Riesgo?": "si",
            },
            {
                "Subsidio": "Semillero de Propietarios (Opción a Compra)",
                "Requisitos Salariales (SMMLV)": "Inferiores a 2 SMMLV",
                "¿Permite Subsidios Anteriores?": "No",
                "¿Permite Tener Vivienda Propia?": "No",
                "¿Situación Laboral es Riesgo?": "no",
            },
            {
                "Subsidio": "Mi Casa en Bogotá - Oferta Preferente",
                "Requisitos Salariales (SMMLV)": "Hasta 4 SMMLV",
                "¿Permite Subsidios Anteriores?": "No",
                "¿Permite Tener Vivienda Propia?": "No",
                "¿Situación Laboral es Riesgo?": "-",
            },
            {
                "Subsidio": "VIVA Mi Casa (Antioquia)",
                "Requisitos Salariales (SMMLV)": "Hasta 4 SMMLV",
                "¿Permite Subsidios Anteriores?": "Sí",
                "¿Permite Tener Vivienda Propia?": "No",
                "¿Situación Laboral es Riesgo?": "-",
            },
            {
                "Subsidio": "La Casa Milagro (texto no numerico)",
                "Requisitos Salariales (SMMLV)": "Depende de la reglamentación (Tasa del 2% EA)",
                "¿Permite Subsidios Anteriores?": "No",
                "¿Permite Tener Vivienda Propia?": "No",
                "¿Situación Laboral es Riesgo?": "-",
            },
        ]
    )


@pytest.fixture(autouse=True)
def subsidios_fake(monkeypatch):
    monkeypatch.setattr(data_store, "cargar_subsidios", lambda: _subsidios_fake())


def _usuario(**overrides):
    base = {
        "Rango salarial": "de 1.750.905 - 3.501.810",  # ~1.8 SMLV
        "Estado laboral": "Empleado",
        "Tipo de contrato": "Indefinido",
        "Afiliado a colsubsidio": "Si",
        "Ha pedido subsidios": "No",
        "Estado de vivienda propia": "Sin vivienda",
        "Ciudad": "Bogotá",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------
# _parsear_rango_smlv
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("De 0 a 4 SMMLV", (0.0, 4.0)),
        ("Hasta 4 SMMLV (postulación conjunta)", (0.0, 4.0)),
        ("Inferiores a 2 SMMLV", (0.0, 2.0)),
        ("Depende de la reglamentación (Tasa del 2% EA)", None),
    ],
)
def test_parsear_rango_smlv(texto, esperado):
    assert subsidios._parsear_rango_smlv(texto) == esperado


# ---------------------------------------------------------------------
# evaluar_subsidios: reglas principales
# ---------------------------------------------------------------------

def test_perfil_ideal_aplica_a_varios_subsidios():
    # ~1.8 SMLV, sin vivienda, sin subsidio previo, tier 1, en Bogota
    elegibles = subsidios.evaluar_subsidios(_usuario())
    nombres = {s.nombre for s in elegibles}
    assert "Semillero de Propietarios (Opción a Compra)" in nombres
    assert "Mi Casa en Bogotá - Oferta Preferente" in nombres
    assert "La Casa Milagro (texto no numerico)" not in nombres  # requisito no numerico, se omite


def test_ingreso_fuera_de_rango_no_aplica():
    usuario = _usuario(**{"Rango salarial": "de 9.000.000 - 10.000.000"})  # ~6.7 SMLV
    elegibles = subsidios.evaluar_subsidios(usuario)
    assert elegibles == []


def test_ya_tuvo_subsidio_excluye_los_que_no_permiten_subsidio_previo():
    usuario = _usuario(**{"Ha pedido subsidios": "Si", "Ciudad": "Medellín"})
    elegibles = subsidios.evaluar_subsidios(usuario)
    nombres = {s.nombre for s in elegibles}
    assert "Semillero de Propietarios (Opción a Compra)" not in nombres
    # VIVA Mi Casa SI permite subsidio anterior
    assert "VIVA Mi Casa (Antioquia)" in nombres


def test_tener_vivienda_propia_excluye_todos_los_que_no_lo_permiten():
    usuario = _usuario(**{"Estado de vivienda propia": "Con vivienda propia"})
    elegibles = subsidios.evaluar_subsidios(usuario)
    assert elegibles == []


def test_situacion_laboral_riesgo_excluye_subsidios_sensibles_a_eso():
    usuario = _usuario(**{"Estado laboral": "Independiente", "Tipo de contrato": "N/A"})  # Tier 3
    elegibles = subsidios.evaluar_subsidios(usuario)
    nombres = {s.nombre for s in elegibles}
    assert "Cajas de Compensación Familiar (Compra)" not in nombres  # riesgo = si
    assert "Semillero de Propietarios (Opción a Compra)" in nombres  # riesgo = no, no se afecta


# ---------------------------------------------------------------------
# Filtros regionales
# ---------------------------------------------------------------------

def test_mi_casa_bogota_no_aplica_fuera_de_bogota():
    usuario = _usuario(**{"Ciudad": "Cali"})
    elegibles = subsidios.evaluar_subsidios(usuario)
    nombres = {s.nombre for s in elegibles}
    assert "Mi Casa en Bogotá - Oferta Preferente" not in nombres


def test_viva_mi_casa_solo_antioquia():
    usuario_medellin = _usuario(**{"Ciudad": "Medellín"})
    usuario_bogota = _usuario(**{"Ciudad": "Bogotá"})
    nombres_medellin = {s.nombre for s in subsidios.evaluar_subsidios(usuario_medellin)}
    nombres_bogota = {s.nombre for s in subsidios.evaluar_subsidios(usuario_bogota)}
    assert "VIVA Mi Casa (Antioquia)" in nombres_medellin
    assert "VIVA Mi Casa (Antioquia)" not in nombres_bogota


# ---------------------------------------------------------------------
# Filtro de edad (Generacion FNA) -- sin columna Edad en el usuario
# ---------------------------------------------------------------------

def test_generacion_fna_sin_dato_de_edad_se_excluye():
    usuario = _usuario()  # sin clave "Edad"
    elegibles = subsidios.evaluar_subsidios(usuario)
    nombres = {s.nombre for s in elegibles}
    assert "Generación FNA (Jóvenes 18-28)" not in nombres


def test_generacion_fna_dentro_de_rango_de_edad_aplica():
    usuario = _usuario(**{"Edad": 24})
    elegibles = subsidios.evaluar_subsidios(usuario)
    nombres = {s.nombre for s in elegibles}
    assert "Generación FNA (Jóvenes 18-28)" in nombres


def test_generacion_fna_fuera_de_rango_de_edad_no_aplica():
    usuario = _usuario(**{"Edad": 35})
    elegibles = subsidios.evaluar_subsidios(usuario)
    nombres = {s.nombre for s in elegibles}
    assert "Generación FNA (Jóvenes 18-28)" not in nombres


# ---------------------------------------------------------------------
# calcular_bonus_score
# ---------------------------------------------------------------------

def test_bonus_score_escala_con_cantidad_de_subsidios():
    elegibles = subsidios.evaluar_subsidios(_usuario())
    assert len(elegibles) >= 2
    assert subsidios.calcular_bonus_score(elegibles) == pytest.approx(
        min(subsidios.BONUS_MAXIMO, subsidios.BONUS_POR_SUBSIDIO * len(elegibles))
    )


def test_bonus_score_cero_sin_subsidios():
    assert subsidios.calcular_bonus_score([]) == 0.0


def test_bonus_score_no_supera_el_maximo():
    muchos = [subsidios.Subsidio(nombre=f"S{i}", requisito_salarial_texto="") for i in range(10)]
    assert subsidios.calcular_bonus_score(muchos) == subsidios.BONUS_MAXIMO
