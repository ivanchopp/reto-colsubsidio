"""Evalua a que subsidios de vivienda aplica un comprador, comparando su
perfil (rango salarial, si ya pidio subsidio antes, si ya tiene vivienda
propia, estabilidad laboral, ciudad y edad) contra los requisitos de cada
programa en RECURSOS/Subsidios Vivienda Colombia.xlsx.
"""
import re
import unicodedata
from dataclasses import dataclass

from app import config, data_store
from app.scoring import _employer_tier, _midpoint_rango_salarial

# ciudades de Antioquia que pueden aparecer en el Excel de usuarios; se usa
# para el filtro regional de VIVA Mi Casa (Antioquia)
CIUDADES_ANTIOQUIA = {
    "medellin", "envigado", "itagui", "bello", "sabaneta", "rionegro",
    "apartado", "turbo", "caucasia", "la estrella", "copacabana",
}

BONUS_POR_SUBSIDIO = 5.0
BONUS_MAXIMO = 15.0


def _normaliza(texto) -> str:
    if texto is None:
        return ""
    texto = str(texto).strip()
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()


@dataclass
class Subsidio:
    nombre: str
    requisito_salarial_texto: str


def _parsear_rango_smlv(texto: str) -> tuple[float, float] | None:
    """Convierte 'De 0 a 4 SMMLV', 'Hasta 4 SMMLV (...)' o 'Inferiores a 2
    SMMLV' en (minimo, maximo). None si el texto no se puede interpretar
    como un rango numerico (ej. 'Depende de la reglamentacion')."""
    t = _normaliza(texto)

    m = re.search(r"de\s+(\d+(?:[.,]\d+)?)\s+a\s+(\d+(?:[.,]\d+)?)", t)
    if m:
        return float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))

    m = re.search(r"(hasta|inferior(?:es)?\s+a)\s+(\d+(?:[.,]\d+)?)", t)
    if m:
        return 0.0, float(m.group(2).replace(",", "."))

    return None


def _ingreso_smlv(usuario: dict) -> float:
    ingreso = _midpoint_rango_salarial(usuario.get("Rango salarial", ""))
    return ingreso / config.SMLV_COP if ingreso else 0.0


def _cumple_ciudad(nombre_subsidio: str, ciudad_usuario: str) -> bool:
    nombre_norm = _normaliza(nombre_subsidio)
    ciudad_norm = _normaliza(ciudad_usuario)
    if "bogota" in nombre_norm:
        return "bogota" in ciudad_norm
    if "antioquia" in nombre_norm:
        return ciudad_norm in CIUDADES_ANTIOQUIA
    return True  # subsidio nacional, sin restriccion de ciudad


def _cumple_edad(nombre_subsidio: str, usuario: dict) -> bool:
    if "generacion fna" not in _normaliza(nombre_subsidio):
        return True  # solo Generacion FNA tiene requisito de edad (18-28)
    edad = usuario.get("Edad")
    if edad is None or (isinstance(edad, float) and edad != edad):  # NaN
        return False  # sin dato de edad, no se puede verificar -> se excluye
    return 18 <= edad <= 28


def evaluar_subsidios(usuario: dict) -> list[Subsidio]:
    df = data_store.cargar_subsidios()
    ingreso_smlv = _ingreso_smlv(usuario)
    ya_tuvo_subsidio = str(usuario.get("Ha pedido subsidios", "")).strip().lower() == "si"
    tiene_vivienda_propia = str(usuario.get("Estado de vivienda propia", "")).strip().lower() == "con vivienda propia"
    situacion_riesgo = _employer_tier(usuario) == "Tier 3"
    ciudad = usuario.get("Ciudad", "")

    elegibles = []
    for _, fila in df.iterrows():
        nombre = fila["Subsidio"]

        rango = _parsear_rango_smlv(fila["Requisitos Salariales (SMMLV)"])
        if rango is None:
            continue  # requisito no interpretable numericamente, se omite de la comparacion automatica
        minimo, maximo = rango
        if not (minimo <= ingreso_smlv <= maximo):
            continue

        permite_subsidio_previo = _normaliza(fila["¿Permite Subsidios Anteriores?"]) == "si"
        if ya_tuvo_subsidio and not permite_subsidio_previo:
            continue

        permite_vivienda_propia = _normaliza(fila["¿Permite Tener Vivienda Propia?"]) == "si"
        if tiene_vivienda_propia and not permite_vivienda_propia:
            continue

        situacion_es_riesgo_para_este_subsidio = _normaliza(fila["¿Situación Laboral es Riesgo?"]) == "si"
        if situacion_riesgo and situacion_es_riesgo_para_este_subsidio:
            continue

        if not _cumple_ciudad(nombre, ciudad):
            continue

        if not _cumple_edad(nombre, usuario):
            continue

        elegibles.append(Subsidio(nombre=nombre, requisito_salarial_texto=fila["Requisitos Salariales (SMMLV)"]))

    return elegibles


def calcular_bonus_score(subsidios_elegibles: list[Subsidio]) -> float:
    return min(BONUS_MAXIMO, BONUS_POR_SUBSIDIO * len(subsidios_elegibles))
