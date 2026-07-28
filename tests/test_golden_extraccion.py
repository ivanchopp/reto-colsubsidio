"""Golden set de extraccion: llama al LLM real configurado (no un stub) con
mensajes representativos de lo que dice un usuario real, y compara contra lo
que deberia extraerse.

Por que existe aparte de tests/test_extraccion.py: ese archivo estubea
llm_client.extraer_json y prueba la capa de validacion (_limpiar) -- nunca
ejercita el prompt en si. Un cambio en INSTRUCCION, o un cambio de
LLM_PROVIDER (openai/gemini/vertex, o de modelo dentro del mismo proveedor),
puede degradar silenciosamente la calidad de la extraccion sin que ese
archivo lo note, porque el stub siempre devuelve exactamente lo que el test
le pide.

No corre por defecto: llama a un LLM real, cuesta dinero, tarda mas y no es
100% determinista (dos corridas del mismo caso pueden no coincidir siempre --
son mensajes de intencion razonablemente clara, pero sigue siendo un modelo
de lenguaje). Se salta salvo que se pida explicitamente:

    RUN_GOLDEN_EXTRACCION=1 python -m pytest tests/test_golden_extraccion.py -v

Correr esto despues de: tocar INSTRUCCION en app/extraccion.py, cambiar
LLM_PROVIDER o el modelo del proveedor activo en .env, o antes de promover
cualquiera de esos cambios a produccion.

Nota sobre el tier gratuito de Gemini (LLM_PROVIDER=gemini sin billing): el
limite no es solo por minuto (5 req/min), tambien hay un tope diario (20
req/dia con el modelo por defecto al momento de escribir esto). Los 15 casos
de este set pueden agotar ese tope en una sola corrida -- si eso pasa, los
casos fallan con un 429 en el log, no por mala extraccion. Con un plan de
pago o un modelo distinto ese limite no aplica.
"""
import os
import time

import pytest

from app import config, extraccion

RUN_GOLDEN_EXTRACCION = os.getenv("RUN_GOLDEN_EXTRACCION") == "1"

# El tier gratuito de varios proveedores es estricto con el ritmo de
# requests (Gemini free tier: 5 por minuto) -- se descubrio corriendo este
# mismo eval en serie, que hacia fallar 5 de 15 casos por 429 (quota
# exceeded), no por mala extraccion. Ajustable a 0 para un plan de pago sin
# ese limite.
DELAY_ENTRE_CASOS_SEGUNDOS = float(os.getenv("GOLDEN_EXTRACCION_DELAY_SEGUNDOS", "15"))

pytestmark = pytest.mark.skipif(
    not RUN_GOLDEN_EXTRACCION,
    reason=(
        "eval opcional contra el LLM real: cuesta dinero y no es 100% determinista. "
        "Correr con RUN_GOLDEN_EXTRACCION=1 despues de tocar el prompt de extraccion "
        "(app/extraccion.py) o cambiar de proveedor/modelo (.env)."
    ),
)


def _proveedor_configurado() -> bool:
    if config.LLM_PROVIDER == "vertex":
        return bool(config.VERTEX_PROJECT and config.VERTEX_CREDENTIALS_PATH)
    if config.LLM_PROVIDER == "gemini":
        return bool(config.GOOGLE_API_KEY)
    return bool(config.OPENAI_API_KEY)


@pytest.fixture(scope="module", autouse=True)
def _requiere_credenciales():
    if not _proveedor_configurado():
        pytest.fail(
            f"RUN_GOLDEN_EXTRACCION=1 pero no hay credenciales configuradas para "
            f"LLM_PROVIDER={config.LLM_PROVIDER!r} en .env. Configura la API key "
            "correspondiente antes de correr este eval."
        )


# Todos los casos declaran las 6 claves explicitamente (None donde no aplica)
# para que el eval tambien detecte alucinaciones: un valor donde se esperaba
# null es tan fallo como un valor equivocado.
_CAMPOS = (
    "empresa", "situacion_laboral", "ahorro_cuota_inicial",
    "estructura_familiar", "tiene_vivienda", "ingresos_mensuales_aprox",
)

TEMA_AHORRO = "si ya viene ahorrando o tiene cesantias pensando en la cuota inicial"
TEMA_FAMILIA = "con quien se estaria mudando (solo/a, en pareja, con hijos)"
TEMA_ASPIRACIONAL = "que suenos o planes tiene con este paso de comprar vivienda"

CASOS = [
    {
        "id": "ahorro_positivo_con_cesantias",
        "tema": TEMA_AHORRO,
        "mensaje": "Sí, llevo como dos años ahorrando y tengo mis cesantías guardadas para la inicial.",
        "esperado": {"ahorro_cuota_inicial": True},
    },
    {
        "id": "ahorro_negativo_explicito",
        "tema": TEMA_AHORRO,
        "mensaje": "No, la verdad no he podido ahorrar nada todavía.",
        "esperado": {"ahorro_cuota_inicial": False},
    },
    {
        "id": "ahorro_evasivo_no_debe_inventar",
        "tema": TEMA_AHORRO,
        "mensaje": "Uy pues no sé, eso lo maneja mi esposo jajaja.",
        "esperado": {},  # ambiguo a proposito: no debe forzar true/false
    },
    {
        "id": "familia_monoparental_joven",
        "tema": TEMA_FAMILIA,
        "mensaje": "Me mudaría con mi hija, soy mamá soltera y ella tiene 4 años.",
        "esperado": {"estructura_familiar": "Monoparental Joven"},
    },
    {
        "id": "familia_nuclear_integrada",
        "tema": TEMA_FAMILIA,
        "mensaje": "Con mi esposo y nuestros dos hijos.",
        "esperado": {"estructura_familiar": "Nuclear Integrada"},
    },
    {
        "id": "familia_sin_grupo",
        "tema": TEMA_FAMILIA,
        "mensaje": "Solo yo, todavía no tengo pareja ni hijos.",
        "esperado": {"estructura_familiar": "Sin Grupo"},
    },
    {
        "id": "situacion_empleado_formal_con_empresa",
        "tema": TEMA_ASPIRACIONAL,
        "mensaje": "Trabajo en Bancolombia hace tres años con contrato fijo.",
        "esperado": {"situacion_laboral": "empleado_formal", "empresa": "Bancolombia"},
    },
    {
        "id": "situacion_independiente",
        "tema": TEMA_ASPIRACIONAL,
        "mensaje": "Soy independiente, hago diseño gráfico por mi cuenta.",
        "esperado": {"situacion_laboral": "independiente"},
    },
    {
        "id": "situacion_desempleado",
        "tema": TEMA_ASPIRACIONAL,
        "mensaje": "Ahorita estoy sin trabajo, me quedé sin empleo hace unos meses.",
        "esperado": {"situacion_laboral": "desempleado"},
    },
    {
        "id": "tiene_vivienda_propia",
        "tema": TEMA_ASPIRACIONAL,
        "mensaje": "Ya tengo un apartamento propio pero quiero comprar uno más grande.",
        "esperado": {"tiene_vivienda": True},
    },
    {
        "id": "no_tiene_vivienda",
        "tema": TEMA_ASPIRACIONAL,
        "mensaje": "No, vivo arrendado todavía.",
        "esperado": {"tiene_vivienda": False},
    },
    {
        "id": "ingreso_en_palabras",
        "tema": TEMA_ASPIRACIONAL,
        "mensaje": "Gano como 4 millones y medio al mes.",
        "esperado": {"ingresos_mensuales_aprox": 4_500_000},
    },
    {
        "id": "ingreso_en_numeros",
        "tema": TEMA_ASPIRACIONAL,
        "mensaje": "Mi sueldo es de 3.200.000 pesos mensuales.",
        "esperado": {"ingresos_mensuales_aprox": 3_200_000},
    },
    {
        "id": "sin_informacion_util",
        "tema": TEMA_ASPIRACIONAL,
        "mensaje": "Jajaja qué buena pregunta, la verdad nunca lo había pensado.",
        "esperado": {},
    },
    {
        "id": "multiples_datos_en_un_mensaje",
        "tema": TEMA_ASPIRACIONAL,
        "mensaje": (
            "Trabajo en una empresa de logística, gano cerca de 5 millones al mes, "
            "y ya tengo algo ahorrado para la inicial."
        ),
        "esperado": {
            "situacion_laboral": "empleado_formal",
            "ingresos_mensuales_aprox": 5_000_000,
            "ahorro_cuota_inicial": True,
        },
    },
]


def _comparar(esperado: dict, obtenido: dict) -> list[str]:
    """Compara campo por campo (no dict == dict): empresa admite match parcial
    insensible a mayusculas, ingreso admite +-5% de tolerancia, y cualquier
    campo no listado en 'esperado' se asume null (debe estar ausente)."""
    errores = []
    for campo in _CAMPOS:
        valor_esperado = esperado.get(campo)

        if valor_esperado is None:
            if campo in obtenido:
                errores.append(f"{campo}: se esperaba null, se extrajo {obtenido[campo]!r}")
            continue

        if campo not in obtenido:
            errores.append(f"{campo}: se esperaba {valor_esperado!r}, no se extrajo nada")
            continue

        valor_obtenido = obtenido[campo]
        if campo == "empresa":
            if valor_esperado.strip().lower() not in str(valor_obtenido).strip().lower():
                errores.append(f"empresa: se esperaba algo como {valor_esperado!r}, se extrajo {valor_obtenido!r}")
        elif campo == "ingresos_mensuales_aprox":
            if abs(valor_obtenido - valor_esperado) > valor_esperado * 0.05:
                errores.append(
                    f"ingresos_mensuales_aprox: se esperaba ~{valor_esperado:,.0f}, "
                    f"se extrajo {valor_obtenido:,.0f}"
                )
        elif valor_obtenido != valor_esperado:
            errores.append(f"{campo}: se esperaba {valor_esperado!r}, se extrajo {valor_obtenido!r}")

    return errores


@pytest.mark.parametrize("caso", CASOS, ids=[c["id"] for c in CASOS])
def test_extraccion_golden(caso):
    if DELAY_ENTRE_CASOS_SEGUNDOS:
        time.sleep(DELAY_ENTRE_CASOS_SEGUNDOS)
    obtenido = extraccion.extraer_de_mensaje(caso["mensaje"], caso["tema"])
    errores = _comparar(caso["esperado"], obtenido)
    assert not errores, (
        f"mensaje: {caso['mensaje']!r}\n"
        f"esperado: {caso['esperado']!r}\n"
        f"obtenido: {obtenido!r}\n" + "\n".join(errores)
    )
