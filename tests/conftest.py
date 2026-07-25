"""Fixtures compartidos para los tests de scoring.

`sin_peers`, `vectorial_neutro` y `sin_subsidios` son autouse: stubean
data_store.peers_con_perfil_similar, vector_similarity.calcular_similitud_vectorial
y subsidios.evaluar_subsidios para que ningun test dependa de los Excel
reales (Base_de_datos_usuarios_Colombia.xlsx, Subsidios Vivienda Colombia.xlsx)
ni de sus centroides, que cambian si alguien edita los archivos.
`vectorial_neutro` devuelve 50.0 (punto medio, "sin senal") y `sin_subsidios`
devuelve [] (ningun subsidio elegible) salvo que el test los sobreescriba
explicitamente (ver test_vector_similarity.py y test_subsidios.py). Asi los
tests corren en milisegundos y no se rompen si los Excel cambian.
"""
import pandas as pd
import pytest

from app import data_store, subsidios, vector_similarity


@pytest.fixture(autouse=True)
def sin_peers(monkeypatch):
    monkeypatch.setattr(data_store, "peers_con_perfil_similar", lambda usuario: pd.DataFrame())


@pytest.fixture(autouse=True)
def vectorial_neutro(request, monkeypatch):
    # test_vector_similarity.py prueba la funcion real: no la estubeamos ahi
    if request.module.__name__.endswith("test_vector_similarity"):
        return
    stub = lambda usuario: {"score_vectorial": 50.0, "similitudes_por_centroide": {}}
    monkeypatch.setattr(vector_similarity, "calcular_similitud_vectorial", stub)


@pytest.fixture(autouse=True)
def sin_subsidios(request, monkeypatch):
    # test_subsidios.py prueba la funcion real: no la estubeamos ahi
    if request.module.__name__.endswith("test_subsidios"):
        return
    monkeypatch.setattr(subsidios, "evaluar_subsidios", lambda usuario: [])


@pytest.fixture
def make_usuario():
    """Factory de usuario con valores por defecto razonables (VIS,
    Tier 1, afiliado, sin reportes negativos). Cada test sobreescribe
    solo los campos que le interesan."""

    def _make(**overrides):
        base = {
            "Rango salarial": "de 4.000.000 - 5.000.000",
            "Estado laboral": "Empleado",
            "Tipo de contrato": "Indefinido",
            "Afiliado a colsubsidio": "Si",
            "Reportado en data crédito": "No reportado",
        }
        base.update(overrides)
        return base

    return _make
