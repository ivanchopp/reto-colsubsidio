"""Extraccion de variables de calificacion a partir de lo que el usuario
cuenta en la conversacion.

Por que existe: hasta ahora el score salia 100% de la base de datos y la
charla no aportaba nada. El reto pide explicitamente inferir capacidad de
compra "con la data que tenga a mano y preguntando lo que falte, sin sentirse
como un interrogatorio" (Perfilamiento inteligente de leads.txt), y SOBREMI.md
da el metodo: preguntas indirectas, nunca el dato duro de frente.

Aqui se traducen esas respuestas en lenguaje natural a las variables que
consume app/scoring.py, incluidas las dos features de
RECURSOS/buyer_persona_scoring_schema.json que hasta ahora no se usaban:
family_structure y savings_fna_cesantias.

La extraccion es best-effort: si el LLM falla o el usuario no dijo nada util,
el campo queda en None y el scoring simplemente no lo usa. Nunca bloquea la
conversacion.
"""
from app import llm_client

# Valores admitidos por campo. Se validan al recibir la respuesta del LLM:
# cualquier cosa fuera de esta lista se descarta en vez de propagarse al
# scoring como un valor basura.
VALORES_SITUACION_LABORAL = {"empleado_formal", "independiente", "desempleado"}
VALORES_ESTRUCTURA_FAMILIAR = {"Monoparental Joven", "Nuclear Integrada", "Sin Grupo"}

CAMPOS_BOOLEANOS = {"ahorro_cuota_inicial", "tiene_vivienda"}

INSTRUCCION = """Extrae del siguiente mensaje de un usuario los datos que esten presentes.

Mensaje del usuario: "{texto}"

Contexto: se le acababa de preguntar sobre "{tema}".

Devuelve un JSON con exactamente estas claves:
- "empresa": nombre de la empresa donde trabaja, o null.
- "situacion_laboral": "empleado_formal" si el mensaje dice explicitamente que
  trabaja con contrato en una empresa, "independiente" si dice que trabaja por
  su cuenta o por prestacion de servicios, "desempleado" si dice que no tiene
  trabajo ahora. null si no se puede saber. Mencionar cesantias o ahorros por
  si solo NO es evidencia de situacion laboral (un independiente tambien puede
  tener cesantias guardadas en un fondo).
- "ahorro_cuota_inicial": true si menciona tener ahorros, cesantias o dinero
  guardado para la cuota inicial; false si dice explicitamente que no tiene;
  null si no se menciona.
- "estructura_familiar": "Monoparental Joven" si es una persona joven sola con
  hijos, "Nuclear Integrada" si el mensaje dice explicitamente con quien se
  mudaria (pareja, con o sin hijos), "Sin Grupo" si dice que se mudaria solo o
  sola. null si el mensaje no responde con quien se mudaria -- mencionar a la
  pareja o la familia en otro contexto (por ejemplo, quien administra los
  ahorros) no cuenta como respuesta a esta pregunta.
- "tiene_vivienda": true si ya tiene vivienda propia, false si dice que no,
  null si no se menciona.
- "ingresos_mensuales_aprox": ingreso mensual en pesos colombianos como numero
  entero, solo si el usuario lo menciona explicitamente. null en cualquier
  otro caso.

No infieras mas alla de lo que dice el mensaje. Ante la duda, null."""


def _limpiar(datos: dict) -> dict:
    """Se queda solo con los campos conocidos y con valores del tipo correcto.
    Un LLM puede devolver 'no se', 'Empleado' o un string donde se esperaba un
    booleano; nada de eso debe llegar al scoring."""
    limpio = {}

    situacion = datos.get("situacion_laboral")
    if situacion in VALORES_SITUACION_LABORAL:
        limpio["situacion_laboral"] = situacion

    estructura = datos.get("estructura_familiar")
    if estructura in VALORES_ESTRUCTURA_FAMILIAR:
        limpio["estructura_familiar"] = estructura

    for campo in CAMPOS_BOOLEANOS:
        if isinstance(datos.get(campo), bool):
            limpio[campo] = datos[campo]

    empresa = datos.get("empresa")
    if isinstance(empresa, str) and empresa.strip():
        limpio["empresa"] = empresa.strip()

    ingresos = datos.get("ingresos_mensuales_aprox")
    if isinstance(ingresos, (int, float)) and not isinstance(ingresos, bool) and ingresos > 0:
        limpio["ingresos_mensuales_aprox"] = float(ingresos)

    return limpio


def extraer_de_mensaje(texto: str, tema: str) -> dict:
    """Devuelve solo los campos que el usuario efectivamente menciono. Las
    claves ausentes significan 'no se sabe', que no es lo mismo que un valor
    negativo: quien llama debe hacer .get() y no asumir defaults."""
    if not texto or not texto.strip():
        return {}
    datos = llm_client.extraer_json(INSTRUCCION.format(texto=texto.strip(), tema=tema))
    return _limpiar(datos)


def resumir_para_asesor(declarados: dict) -> list[str]:
    """Lineas legibles de lo que aporto la conversacion, para el correo de
    handoff y el panel del asesor."""
    if not declarados:
        return []

    etiquetas = {
        "empresa": lambda v: f"Trabaja en: {v}",
        "situacion_laboral": lambda v: f"Situacion laboral declarada: {v.replace('_', ' ')}",
        "ahorro_cuota_inicial": lambda v: (
            "Tiene ahorro o cesantias para la cuota inicial"
            if v
            else "Declara no tener ahorro para la cuota inicial"
        ),
        "estructura_familiar": lambda v: f"Grupo familiar: {v}",
        "tiene_vivienda": lambda v: (
            "Ya tiene vivienda propia" if v else "No tiene vivienda propia"
        ),
        "ingresos_mensuales_aprox": lambda v: f"Ingreso mensual declarado: ${v:,.0f} COP",
    }
    return [etiquetas[campo](valor) for campo, valor in declarados.items() if campo in etiquetas]
