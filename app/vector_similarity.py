"""Similitud vectorial contra centroides (señal complementaria al arbol de
reglas de app/scoring.py y al peer-matching de app/data_store.py).

Cada usuario del Excel se convierte en un vector numerico. Se calcula el
centroide (vector promedio) de cada resultado historico conocido en
'Estado de vivienda propia' (Con vivienda propia / Desistido / Rechazado /
Sin vivienda). Un lead nuevo se compara por similitud coseno contra esos
centroides: entre mas cerca del centroide "Con vivienda propia", mas
probable se asume su compra.

Con solo ~50 registros los centroides son ruidosos por diseño (grupos de
pocas decenas de personas) — por eso esta señal se blende con peso menor
junto a las otras dos, nunca decide sola.
"""
from functools import lru_cache

import numpy as np
import pandas as pd

from app import config, data_store

RESULTADO_POSITIVO = "Con vivienda propia"

TIER_A_NUMERO = {"Tier 1": 1.0, "Tier 2": 0.66, "Tier 3": 0.33}
ANTIGUEDAD_TECHO_MESES = 120.0  # 10 anios, satura el feature de antiguedad

# Shrinkage tipo Empirical Bayes sobre el peso de esta senal en el blend
# (ver app/scoring.py): un centroide calculado sobre pocos usuarios es
# ruidoso, y antes eso pesaba lo mismo en el blend que un centroide con
# cientos de usuarios detras. PSEUDO_CONTEO_CENTROIDE es el numero de
# usuarios al que el centroide positivo ya aporta la mitad de la confianza
# maxima (n / (n + k)); mismo criterio y mismo valor que
# scoring.PSEUDO_CONTEO_PEERS. Con la base actual (914 usuarios en "Con
# vivienda propia") la confianza practicamente satura en 1.0 -- el shrinkage
# protege sobre todo a una base mas chica o desbalanceada.
PSEUDO_CONTEO_CENTROIDE = 10


def _midpoint_rango_salarial(rango: str) -> float:
    from app.scoring import _midpoint_rango_salarial as f

    return f(rango)


def _antiguedad_meses(usuario: dict) -> float:
    fecha = usuario.get("Fecha de inicio de labores")
    if fecha is None or pd.isna(fecha):
        return 0.0
    fecha = pd.Timestamp(fecha)
    meses = (pd.Timestamp.now() - fecha).days / 30.44
    return max(0.0, meses)


def vectorizar_usuario(usuario: dict) -> np.ndarray:
    """Convierte un usuario en un vector de 5 features, cada una normalizada
    aproximadamente a [0, 1] para que ninguna domine la distancia por escala."""
    from app.scoring import _employer_tier

    ingreso_smlv = _midpoint_rango_salarial(usuario.get("Rango salarial", "")) / config.SMLV_COP
    ingreso_norm = min(ingreso_smlv / 10.0, 1.0)

    tier_norm = TIER_A_NUMERO[_employer_tier(usuario)]

    afiliado_norm = 1.0 if str(usuario.get("Afiliado a colsubsidio", "")).strip().lower() == "si" else 0.0

    buen_historial_norm = (
        0.0 if str(usuario.get("Reportado en data crédito", "")).strip().lower() == "reportado" else 1.0
    )

    antiguedad_norm = min(_antiguedad_meses(usuario) / ANTIGUEDAD_TECHO_MESES, 1.0)

    return np.array([ingreso_norm, tier_norm, afiliado_norm, buen_historial_norm, antiguedad_norm])


def similitud_coseno(a: np.ndarray, b: np.ndarray) -> float:
    norma_a, norma_b = np.linalg.norm(a), np.linalg.norm(b)
    if norma_a == 0 or norma_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norma_a * norma_b))


@lru_cache(maxsize=1)
def calcular_centroides() -> dict:
    """Vectoriza todo el Excel y promedia por resultado historico.
    Cacheado: el Excel no cambia durante la ejecucion del proceso."""
    df = data_store.cargar_usuarios()
    centroides = {}
    for resultado, grupo in df.groupby("Estado de vivienda propia"):
        vectores = [vectorizar_usuario(fila.to_dict()) for _, fila in grupo.iterrows()]
        centroides[resultado] = np.mean(vectores, axis=0)
    return centroides


@lru_cache(maxsize=1)
def contar_centroides() -> dict:
    """Cuantos usuarios soportan cada centroide -- la base del shrinkage de
    confianza (ver PSEUDO_CONTEO_CENTROIDE). Cacheado por la misma razon que
    calcular_centroides."""
    df = data_store.cargar_usuarios()
    return df["Estado de vivienda propia"].value_counts().to_dict()


def calcular_similitud_vectorial(usuario: dict) -> dict:
    """Devuelve la similitud coseno del usuario contra cada centroide y un
    score_vectorial (0-100) basado en que tan cerca esta del centroide de
    compradores exitosos frente a los demas centroides."""
    vector_usuario = vectorizar_usuario(usuario)
    centroides = calcular_centroides()

    similitudes = {
        resultado: round(similitud_coseno(vector_usuario, centroide), 4)
        for resultado, centroide in centroides.items()
    }

    similitud_positiva = similitudes.get(RESULTADO_POSITIVO, 0.0)

    # Posicion RELATIVA del usuario entre los centroides, no la similitud
    # absoluta contra el positivo. El rango teorico del coseno es [-1, 1],
    # pero las cinco componentes del vector son no negativas, asi que en la
    # practica vive en [0, 1] y el mapeo (sim + 1) / 2 lo comprimia todo a
    # [50, 100]: en la base real daba entre 77 y 99.5 para todo el mundo, un
    # offset casi constante sin poder de discriminacion. Normalizar contra el
    # centroide mas lejano del propio usuario usa el ranking completo (que ya
    # se calculaba y se descartaba) y devuelve el rango 0-100 util: 100 si el
    # centroide de compradores es el mas cercano, 0 si es el mas lejano.
    valores = list(similitudes.values())
    rango = max(valores) - min(valores) if valores else 0.0
    if rango > 0:
        score_vectorial = (similitud_positiva - min(valores)) / rango * 100
    else:
        # un solo centroide (o todos equidistantes): no hay ranking del que
        # extraer senal, se devuelve el punto medio en vez de un extremo
        score_vectorial = 50.0
    score_vectorial = max(0.0, min(100.0, score_vectorial))

    soporte_positivo = contar_centroides().get(RESULTADO_POSITIVO, 0)
    confianza = soporte_positivo / (soporte_positivo + PSEUDO_CONTEO_CENTROIDE)

    return {
        "score_vectorial": round(score_vectorial, 1),
        "similitudes_por_centroide": similitudes,
        # cuantos usuarios soportan el centroide "Con vivienda propia" y que
        # tanto pesa por eso esta senal en el blend de scoring.py -- no el
        # score en si (ya viene acotado 0-100 y con un piso neutro de 50
        # cuando no hay ranking del que sacar señal), sino su influencia.
        "soporte_centroide_positivo": soporte_positivo,
        "confianza": round(confianza, 3),
    }
