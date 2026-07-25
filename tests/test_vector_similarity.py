"""Pruebas unitarias para app/vector_similarity.py (similitud coseno contra
centroides historicos). Aisladas del Excel real: se mockea
data_store.cargar_usuarios con un dataset pequeno y controlado, y se limpia
el cache de calcular_centroides antes de cada test (esta decorado con
lru_cache, asi que sin limpiarlo un test contaminaria a los siguientes).
"""
import pandas as pd
import pytest

from app import data_store, vector_similarity as vs


@pytest.fixture(autouse=True)
def limpiar_cache_centroides():
    vs.calcular_centroides.cache_clear()
    yield
    vs.calcular_centroides.cache_clear()


def _usuario(**overrides):
    base = {
        "Rango salarial": "de 4.000.000 - 5.000.000",
        "Estado laboral": "Empleado",
        "Tipo de contrato": "Indefinido",
        "Afiliado a colsubsidio": "Si",
        "Reportado en data crédito": "No reportado",
        "Fecha de inicio de labores": pd.Timestamp.now() - pd.Timedelta(days=365 * 5),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------
# vectorizar_usuario
# ---------------------------------------------------------------------

def test_vectorizar_usuario_devuelve_5_features_entre_0_y_1():
    vector = vs.vectorizar_usuario(_usuario())
    assert vector.shape == (5,)
    assert all(0.0 <= x <= 1.0 for x in vector)


def test_vectorizar_usuario_afiliado_vs_no_afiliado_solo_cambia_esa_feature():
    afiliado = vs.vectorizar_usuario(_usuario())
    no_afiliado = vs.vectorizar_usuario(_usuario(**{"Afiliado a colsubsidio": "No"}))

    # indice 2 = afiliado_norm
    assert afiliado[2] == 1.0
    assert no_afiliado[2] == 0.0
    # el resto de features no deberia moverse
    assert afiliado[0] == no_afiliado[0]
    assert afiliado[1] == no_afiliado[1]
    assert afiliado[3] == no_afiliado[3]
    assert afiliado[4] == no_afiliado[4]


def test_vectorizar_usuario_reportado_baja_feature_de_buen_historial():
    limpio = vs.vectorizar_usuario(_usuario())
    reportado = vs.vectorizar_usuario(_usuario(**{"Reportado en data crédito": "Reportado"}))

    assert limpio[3] == 1.0
    assert reportado[3] == 0.0


def test_vectorizar_usuario_ingreso_mayor_da_feature_de_ingreso_mayor():
    bajo = vs.vectorizar_usuario(_usuario(**{"Rango salarial": "de 0 - 1.750.905"}))
    alto = vs.vectorizar_usuario(_usuario(**{"Rango salarial": "de 9.000.000 - 10.000.000"}))

    assert alto[0] > bajo[0]


def test_vectorizar_usuario_sin_fecha_de_inicio_no_falla():
    usuario = _usuario()
    usuario.pop("Fecha de inicio de labores")
    vector = vs.vectorizar_usuario(usuario)
    assert vector[4] == 0.0  # antiguedad_norm por defecto


# ---------------------------------------------------------------------
# similitud_coseno
# ---------------------------------------------------------------------

def test_similitud_coseno_vectores_identicos_es_1():
    import numpy as np

    v = np.array([0.5, 0.2, 1.0, 0.8, 0.3])
    assert vs.similitud_coseno(v, v.copy()) == pytest.approx(1.0)


def test_similitud_coseno_vectores_ortogonales_es_0():
    import numpy as np

    a = np.array([1.0, 0.0])
    b = np.array([0.0, 1.0])
    assert vs.similitud_coseno(a, b) == pytest.approx(0.0)


def test_similitud_coseno_vector_cero_no_lanza_error():
    import numpy as np

    cero = np.zeros(5)
    otro = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    assert vs.similitud_coseno(cero, otro) == 0.0


# ---------------------------------------------------------------------
# calcular_centroides
# ---------------------------------------------------------------------

def _dataset_fake():
    filas = [
        # 2 compradores exitosos con perfil fuerte
        _usuario(**{"Rango salarial": "de 9.000.000 - 10.000.000", "Estado de vivienda propia": "Con vivienda propia"}),
        _usuario(**{"Rango salarial": "de 9.000.000 - 10.000.000", "Estado de vivienda propia": "Con vivienda propia"}),
        # 2 rechazados con perfil debil
        _usuario(**{
            "Rango salarial": "de 0 - 1.750.905",
            "Estado laboral": "Desempleado",
            "Afiliado a colsubsidio": "No",
            "Reportado en data crédito": "Reportado",
            "Estado de vivienda propia": "Rechazado",
        }),
        _usuario(**{
            "Rango salarial": "de 0 - 1.750.905",
            "Estado laboral": "Desempleado",
            "Afiliado a colsubsidio": "No",
            "Reportado en data crédito": "Reportado",
            "Estado de vivienda propia": "Rechazado",
        }),
    ]
    return pd.DataFrame(filas)


def test_calcular_centroides_agrupa_por_estado_de_vivienda(monkeypatch):
    monkeypatch.setattr(data_store, "cargar_usuarios", lambda: _dataset_fake())

    centroides = vs.calcular_centroides()

    assert set(centroides.keys()) == {"Con vivienda propia", "Rechazado"}
    # el centroide de compradores exitosos debe tener mayor ingreso e
    # historial mejor que el de rechazados
    assert centroides["Con vivienda propia"][0] > centroides["Rechazado"][0]  # ingreso_norm
    assert centroides["Con vivienda propia"][3] > centroides["Rechazado"][3]  # buen_historial_norm


# ---------------------------------------------------------------------
# calcular_similitud_vectorial
# ---------------------------------------------------------------------

def test_calcular_similitud_vectorial_perfil_identico_al_centroide_positivo(monkeypatch):
    monkeypatch.setattr(data_store, "cargar_usuarios", lambda: _dataset_fake())

    # mismo perfil que los "Con vivienda propia" del dataset fake
    usuario = _usuario(**{"Rango salarial": "de 9.000.000 - 10.000.000"})
    resultado = vs.calcular_similitud_vectorial(usuario)

    assert resultado["score_vectorial"] > 90.0
    assert "Con vivienda propia" in resultado["similitudes_por_centroide"]


def test_calcular_similitud_vectorial_perfil_opuesto_da_score_bajo(monkeypatch):
    monkeypatch.setattr(data_store, "cargar_usuarios", lambda: _dataset_fake())

    # mismo perfil que los "Rechazado" del dataset fake
    usuario = _usuario(**{
        "Rango salarial": "de 0 - 1.750.905",
        "Estado laboral": "Desempleado",
        "Afiliado a colsubsidio": "No",
        "Reportado en data crédito": "Reportado",
    })
    resultado = vs.calcular_similitud_vectorial(usuario)
    resultado_bueno = vs.calcular_similitud_vectorial(_usuario(**{"Rango salarial": "de 9.000.000 - 10.000.000"}))

    assert resultado["score_vectorial"] < resultado_bueno["score_vectorial"]
