"""Que le falta a un lead que hoy no puede comprar, en terminos accionables.

El reto es explicito en esto: "los leads que hoy no pueden comprar no son
innecesarios. Alguien que no puede comprar hoy podria hacerlo en unos meses
con el acompanamiento adecuado. Un buen sistema los identifica y los nutre, no
los descarta" (Perfilamiento inteligente de leads.txt). Es tambien la mitad
del proposito social de Colsubsidio.

Hasta ahora un lead FRIO recibia un parrafo generico del LLM y nada mas: el
asesor no tenia forma de saber por que quedo frio ni que tendria que cambiar
para volver a llamarlo. Aqui se traduce el resultado del scoring en una lista
corta de bloqueantes concretos, cada uno con su accion sugerida, para que el
lead se pueda retomar en vez de perderse.

Es una funcion pura sobre el usuario y el resultado del scoring: no consulta
la base ni llama al LLM.
"""
from app import config, scoring

# Cada bloqueante tiene un codigo estable (para agrupar y filtrar en el panel),
# un texto para el asesor y la accion concreta que destraba el caso.
BLOQUEANTE_DATACREDITO = {
    "codigo": "datacredito",
    "titulo": "Reportado en centrales de riesgo",
    "accion": "Ponerse al dia y esperar la actualizacion del reporte antes de aplicar a credito",
    "prioridad": 1,
}
BLOQUEANTE_DESEMPLEO = {
    "codigo": "sin_empleo",
    "titulo": "Sin empleo activo",
    "accion": "Retomar cuando tenga ingreso estable; ofrecer el portal de empleo de Colsubsidio",
    "prioridad": 2,
}
BLOQUEANTE_INFORMALIDAD = {
    "codigo": "ingreso_informal",
    "titulo": "Ingreso sin contrato a termino indefinido",
    "accion": "Formalizar ingresos o acreditar historial de facturacion para mejorar el perfil bancario",
    "prioridad": 3,
}
BLOQUEANTE_NO_AFILIADO = {
    "codigo": "no_afiliado",
    "titulo": "No afiliado a Colsubsidio",
    "accion": "Invitar a afiliarse: habilita subsidios de caja y el cupo del 90% de vivienda",
    "prioridad": 4,
}
BLOQUEANTE_SIN_AHORRO = {
    "codigo": "sin_cuota_inicial",
    "titulo": "Sin ahorro para la cuota inicial",
    "accion": "Ofrecer plan de ahorro programado o cuenta AFC",
    "prioridad": 5,
}
BLOQUEANTE_INGRESO_BAJO = {
    "codigo": "ingreso_insuficiente",
    "titulo": "Ingreso por debajo del minimo para el segmento",
    "accion": "Reorientar a proyectos VIS y revisar subsidios concurrentes",
    "prioridad": 6,
}

# por debajo de esto no alcanza ni para la cuota de un VIS con subsidio
INGRESO_MINIMO_VIABLE_SMLV = 1.5


def detectar_bloqueantes(
    usuario: dict, resultado: scoring.ResultadoScoring, datos_declarados: dict | None = None
) -> list[dict]:
    """Devuelve los bloqueantes ordenados por prioridad. Lista vacia significa
    que no hay nada estructural que impida avanzar: si aun asi el lead quedo
    frio, es por combinacion de senales debiles, no por un impedimento
    puntual."""
    datos_declarados = datos_declarados or {}
    bloqueantes = []

    reportado = str(usuario.get("Reportado en data crédito", "")).strip().lower() == "reportado"
    if reportado:
        bloqueantes.append(BLOQUEANTE_DATACREDITO)

    estado_laboral = str(usuario.get("Estado laboral", "")).strip()
    if estado_laboral == "Desempleado":
        bloqueantes.append(BLOQUEANTE_DESEMPLEO)
    elif scoring._employer_tier(usuario) == "Tier 3":
        # Tier 3 sin estar desempleado = independiente u obra y labor: el
        # banco castiga el perfil aunque el ingreso alcance
        bloqueantes.append(BLOQUEANTE_INFORMALIDAD)

    afiliado = str(usuario.get("Afiliado a colsubsidio", "")).strip().lower() == "si"
    if not afiliado:
        bloqueantes.append(BLOQUEANTE_NO_AFILIADO)

    # solo se marca si la persona dijo explicitamente que no tiene: no
    # haberlo mencionado no es un bloqueante conocido
    if datos_declarados.get("ahorro_cuota_inicial") is False:
        bloqueantes.append(BLOQUEANTE_SIN_AHORRO)

    ingreso_smlv = (
        scoring._midpoint_rango_salarial(usuario.get("Rango salarial", "")) / config.SMLV_COP
    )
    if 0 < ingreso_smlv < INGRESO_MINIMO_VIABLE_SMLV:
        bloqueantes.append(BLOQUEANTE_INGRESO_BAJO)

    return sorted(bloqueantes, key=lambda b: b["prioridad"])


def plan_de_nutricion(bloqueantes: list[dict]) -> str | None:
    """Una linea para el correo al asesor: por donde empezar a acompanar a
    este lead. Devuelve None si no hay bloqueantes identificados."""
    if not bloqueantes:
        return None
    primero = bloqueantes[0]
    return f"{primero['titulo']} -> {primero['accion']}"
