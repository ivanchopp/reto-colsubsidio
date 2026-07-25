"""Motor de recomendacion de proyecto: cruza el perfil duro del usuario
(ciudad, segmento, capacidad de pago) con las senales blandas recogidas en
la conversacion (suscripciones actuales, respuestas aspiracionales) contra
el catalogo de proyectos."""
import unicodedata
from dataclasses import dataclass, field

from app import config, data_store


def _normaliza(texto: str) -> str:
    texto = str(texto or "").strip().lower()
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


PALABRAS_INVERSION = {"invertir", "inversion", "arriendo", "renta", "negocio"}
PALABRAS_FAMILIA = {"familia", "hijos", "hijo", "hija", "esposa", "esposo", "pareja", "bebe"}
PALABRAS_TRANQUILIDAD = {"tranquilidad", "naturaleza", "verde", "silencio", "campo", "aire"}

# variantes de nombre para la misma amenidad, asi "Ecogym" tambien cuenta
# como coincidencia cuando el usuario dice que le gusta el "gimnasio"
SINONIMOS_AMENITIES = {
    "gimnasio": {"gimnasio", "ecogym", "gym"},
    "piscina": {"piscina"},
    "futbol": {"cancha multiple", "cancha de futbol", "futbol"},
}


def _amenity_coincide(amenity_normalizado: str, texto_usuario: str) -> str | None:
    for clave, variantes in SINONIMOS_AMENITIES.items():
        if amenity_normalizado in variantes and clave in texto_usuario:
            return clave
    return amenity_normalizado if amenity_normalizado in texto_usuario else None


@dataclass
class Recomendacion:
    proyecto: dict
    razones: list[str] = field(default_factory=list)
    alternativas: list[dict] = field(default_factory=list)


def _capacidad_pago_millones(usuario: dict) -> float:
    from app.scoring import _midpoint_rango_salarial

    ingreso = _midpoint_rango_salarial(usuario.get("Rango salarial", ""))
    # heuristica simple: financiacion a 20 anios, cuota ~= 30% del ingreso
    return round((ingreso * 0.30 * 12 * 20) / 1_000_000, 1)


def _score_amenities(usuario: dict, proyecto: dict) -> tuple[float, list[str]]:
    suscripciones = _normaliza(usuario.get("Suscripciones actuales", ""))
    amenities = [_normaliza(a) for a in proyecto.get("amenities", [])]
    puntos = 0.0
    razones = []
    for amenity in amenities:
        coincidencia = _amenity_coincide(amenity, suscripciones)
        if coincidencia:
            puntos += 15
            razones.append(f"le gusta {coincidencia} y el proyecto tiene {amenity}")
    return puntos, razones


def _score_aspiracional(respuestas: dict, proyecto: dict) -> tuple[float, list[str]]:
    texto = _normaliza(" ".join(str(v) for v in respuestas.values()))
    puntos = 0.0
    razones = []

    if any(p in texto for p in PALABRAS_INVERSION):
        # premia proyectos con menor tasa de desistimiento historica (mas "seguros")
        # si no hay historico propio (proyectos reales sin dataset), queda neutral
        tasa = proyecto.get("tasa_desistimiento_pct")
        if tasa is not None:
            puntos += max(0, 20 - tasa)
            if tasa < 20:
                razones.append("busca invertir y este proyecto tiene baja tasa de desistimiento historica")

    if any(p in texto for p in PALABRAS_FAMILIA):
        if (proyecto.get("promedio_grupo_familiar") or 0) >= 3:
            puntos += 15
            razones.append("busca espacio para su familia y el proyecto tiene buen tamano de grupo familiar promedio")
        elif any((t.get("alcobas") or 0) >= 2 for t in proyecto.get("tipologias", [])):
            puntos += 10
            razones.append("busca espacio para su familia y el proyecto tiene tipologias de 2 o mas alcobas")

    if any(p in texto for p in PALABRAS_TRANQUILIDAD):
        if "zonas verdes" in [_normaliza(a) for a in proyecto.get("amenities", [])]:
            puntos += 10
            razones.append("busca tranquilidad/naturaleza y el proyecto tiene zonas verdes")

    return puntos, razones


def recomendar_proyecto(usuario: dict, project_segment: str, respuestas_aspiracionales: dict | None = None) -> Recomendacion:
    respuestas_aspiracionales = respuestas_aspiracionales or {}
    catalogo = data_store.cargar_catalogo()
    ciudad_usuario = _normaliza(usuario.get("Ciudad", ""))
    capacidad_pago = _capacidad_pago_millones(usuario)

    candidatos = []
    for proyecto in catalogo:
        puntos = 0.0
        razones = []

        if _normaliza(proyecto["ciudad"]) == ciudad_usuario:
            puntos += 30
            razones.append(f"esta en {proyecto['ciudad']}, la misma ciudad del usuario")

        if proyecto["segmento_poblacional"] == project_segment:
            puntos += 25
            razones.append(f"encaja con el segmento {project_segment} calculado para este perfil")

        precio = proyecto.get("precio_promedio_millones_cop")
        if precio is None:
            pass  # sin precio fijo en COP (se pacta en SMMLV al escriturar): no se puntua, tampoco se penaliza
        elif precio <= capacidad_pago * 1.15:
            puntos += 20
            razones.append(f"precio promedio ${precio}M dentro de la capacidad de pago estimada (~${capacidad_pago}M)")
        else:
            puntos -= 15

        p_amenities, r_amenities = _score_amenities(usuario, proyecto)
        puntos += p_amenities
        razones += r_amenities

        p_aspiracional, r_aspiracional = _score_aspiracional(respuestas_aspiracionales, proyecto)
        puntos += p_aspiracional
        razones += r_aspiracional

        candidatos.append((puntos, proyecto, razones))

    candidatos.sort(key=lambda x: x[0], reverse=True)
    mejor_puntos, mejor_proyecto, mejor_razones = candidatos[0]
    alternativas = [c[1] for c in candidatos[1:3]]

    return Recomendacion(proyecto=mejor_proyecto, razones=mejor_razones, alternativas=alternativas)
