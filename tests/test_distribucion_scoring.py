"""Test de integracion sobre la base real: verifica que la distribucion de
scores sea operable, no solo que cada regla aislada devuelva el numero que
esperamos.

Por que existe: el resto de la suite prueba calcular_score con usuarios
sinteticos cuyos rangos salariales ('de 9.000.000 - 10.000.000') no existen en
la base real. Eso dejo pasar durante meses un bug que rompia el producto
entero: las tres senales del blend vivian en escalas distintas y el score
maximo alcanzable era 63.6 contra un umbral CALIENTE de 70, asi que NINGUN
lead de los 3.449 podia llegar a CALIENTE y el handoff al asesor estaba
muerto. Todos los tests unitarios pasaban.

Estas pruebas son la red que faltaba. Hablan de la distribucion, no de casos
puntuales, y por eso necesitan la base real. Se saltan solas si no hay
SUPABASE_DB_URL configurada (CI sin credenciales).
"""
import collections

import pytest

from app import config, data_store, scoring

pytestmark = pytest.mark.skipif(
    not config.SUPABASE_DB_URL,
    reason="necesita la base real (SUPABASE_DB_URL sin configurar)",
)

# Se evalua una muestra determinista (un usuario de cada N) en vez de los
# 3.449: suficiente para detectar una distribucion degenerada y mantiene la
# suite en el orden de un segundo. Para el barrido completo esta
# scripts/calibrar_scoring.py.
PASO_MUESTRA = 7


@pytest.fixture(scope="module")
def distribucion():
    df = data_store.cargar_usuarios().iloc[::PASO_MUESTRA]
    segmentos = collections.Counter()
    senales = collections.defaultdict(list)
    for _, fila in df.iterrows():
        resultado = scoring.calcular_score(fila.to_dict())
        segmentos[resultado.segmento_lead] += 1
        for contribucion in resultado.contribuciones or []:
            if contribucion["peso"]:
                senales[contribucion["categoria"]].append(
                    contribucion["valor"] / contribucion["peso"]
                )
    return {"total": len(df), "segmentos": segmentos, "senales": senales}


def test_existen_leads_calientes(distribucion):
    """La garantia minima del producto: alguien tiene que poder llegar a
    CALIENTE, porque es lo unico que dispara el handoff al asesor."""
    assert distribucion["segmentos"]["CALIENTE"] > 0, (
        "Ningun lead alcanza CALIENTE: el handoff al asesor esta muerto. "
        "Corre scripts/calibrar_scoring.py y recalibra los umbrales en config."
    )


def test_los_tres_segmentos_estan_poblados(distribucion):
    for nombre in ("CALIENTE", "TIBIO", "FRIO"):
        assert distribucion["segmentos"][nombre] > 0, f"segmento {nombre} vacio"


def test_proporcion_de_calientes_es_operable(distribucion):
    """Ni tan estricto que el equipo comercial no reciba nada, ni tan laxo que
    reciba todo sin filtrar (que es el problema que el producto resuelve)."""
    pct = distribucion["segmentos"]["CALIENTE"] / distribucion["total"]
    assert 0.03 <= pct <= 0.30, f"CALIENTE quedo en {pct:.1%}, fuera del rango operable"


@pytest.mark.parametrize("senal", ["reglas", "vectorial"])
def test_cada_senal_usa_un_rango_amplio(distribucion, senal):
    """Una senal que siempre devuelve valores parecidos no aporta informacion:
    ocupa peso en el blend y actua como constante. Fue exactamente el caso de
    'vectorial', que iba de 77 a 99.5 sobre 100."""
    valores = distribucion["senales"][senal]
    assert valores, f"la senal {senal} no aparecio en ninguna contribucion"
    rango = max(valores) - min(valores)
    assert rango >= 40, (
        f"la senal {senal} solo usa {rango:.0f} de 100 puntos de rango: "
        "no esta discriminando entre perfiles"
    )


def test_umbrales_configurados_son_coherentes():
    assert 0 < config.UMBRAL_TIBIO < config.UMBRAL_CALIENTE <= 100
