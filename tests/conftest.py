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

# Modulos que prueban el sistema real de punta a punta y por eso NO deben
# recibir los stubs de abajo. Se declara explicito, y no confiando en el orden
# de instanciacion de fixtures: un fixture de scope module se construye antes
# que los autouse de scope function, asi que un test de integracion "funciona"
# por accidente aunque los stubs esten activos, y se vuelve un falso positivo
# silencioso el dia que alguien le cambia el scope.
MODULOS_SIN_STUBS = {
    "test_vector_similarity",   # prueba la funcion vectorial real
    "test_subsidios",           # prueba la evaluacion de subsidios real
    "test_distribucion_scoring",  # integracion: mide la distribucion real
}


def _usa_stubs(request) -> bool:
    return not any(request.module.__name__.endswith(m) for m in MODULOS_SIN_STUBS)


@pytest.fixture(autouse=True)
def sin_peers(request, monkeypatch):
    if not _usa_stubs(request):
        return
    monkeypatch.setattr(data_store, "peers_con_perfil_similar", lambda usuario: pd.DataFrame())


@pytest.fixture(autouse=True)
def tasa_base_fija(request, monkeypatch):
    """La tasa base de conversion se usa para convertir la conversion de un
    grupo de peers en lift (ver scoring._lift_de_peers). Se fija en 26.0%, el
    valor real de la base al momento de calibrar, para que los tests no
    dependan de una consulta a Supabase ni cambien si la base se recarga."""
    if not _usa_stubs(request):
        return
    monkeypatch.setattr(data_store, "tasa_base_conversion", lambda: 26.0)


@pytest.fixture(autouse=True)
def vectorial_neutro(request, monkeypatch):
    if not _usa_stubs(request):
        return
    # confianza=1.0 (soporte "infinito"): asi el peso efectivo de vectorial
    # en el blend queda igual a PESO_VECTORIAL sin shrinkage, y los tests que
    # no le interesa esto no tienen que pensar en confianza para nada.
    stub = lambda usuario: {
        "score_vectorial": 50.0,
        "similitudes_por_centroide": {},
        "soporte_centroide_positivo": 999_999,
        "confianza": 1.0,
    }
    monkeypatch.setattr(vector_similarity, "calcular_similitud_vectorial", stub)


@pytest.fixture(autouse=True)
def sin_subsidios(request, monkeypatch):
    if not _usa_stubs(request):
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
