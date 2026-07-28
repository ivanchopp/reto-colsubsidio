"""Unico punto de contacto con el proveedor de LLM. Aislado a proposito:
para cambiar de proveedor o de modelo solo se toca este archivo."""
import logging

from app import config

MENSAJE_FALLBACK = "Uy, se me cruzaron los cables un segundo. ¿Me repites lo último que me contabas?"

# el timeout por defecto del SDK de OpenAI es de 10 minutos -- si el
# proveedor o la red se cuelgan, eso se siente como que "el chat esta
# trabado". Con un timeout corto, si algo falla, cae rapido al mensaje de
# fallback (ver generar_respuesta) en vez de dejar al usuario esperando.
TIMEOUT_LLM_SEGUNDOS = 30


def generar_respuesta(system_prompt: str, historial: list[dict], instruccion_turno: str) -> str:
    """historial: lista de {"role": "user"|"assistant", "content": str}
    instruccion_turno: contexto interno (nunca visible al usuario) que le dice
    al LLM que debe hacer en este turno especifico.

    Si el proveedor falla (limite de cuota, red, etc.) devuelve MENSAJE_FALLBACK
    en vez de lanzar la excepcion, para que la conversacion no truene con un
    error 500 a mitad de la demo. Quien llama debe comparar contra
    MENSAJE_FALLBACK antes de dar por completado un paso critico (ver
    conversation._pasar_a_recomendacion), para no cerrar la sesion con una
    recomendacion que nunca se le llego a comunicar al usuario."""
    mensajes = [{"role": "system", "content": system_prompt}]
    mensajes += historial
    mensajes.append({"role": "system", "content": instruccion_turno})

    try:
        if config.LLM_PROVIDER == "vertex":
            return _generar_vertex(system_prompt, historial, instruccion_turno)
        if config.LLM_PROVIDER == "gemini":
            return _generar_gemini(system_prompt, historial, instruccion_turno)
        return _generar_openai(mensajes)
    except Exception as exc:
        print(f"[llm_client] error llamando al proveedor {config.LLM_PROVIDER}: {exc}")
        return MENSAJE_FALLBACK


SYSTEM_PROMPT_EXTRACTOR = (
    "Eres un extractor de datos. Recibes un mensaje de un usuario y devuelves "
    "UNICAMENTE un objeto JSON valido, sin texto alrededor y sin bloques de "
    "codigo. No inventes valores: si un dato no esta presente o no es claro, "
    "usa null. No razones en voz alta."
)


def extraer_json(instruccion: str) -> dict:
    """Llamada auxiliar al LLM que devuelve datos estructurados en vez de un
    mensaje para el usuario. Usa un system prompt neutro (no la persona del
    asesor) porque aqui no se conversa, se clasifica.

    Nunca lanza: si el proveedor falla o devuelve algo que no es JSON, retorna
    {} y el flujo sigue sin los datos declarados. Una extraccion fallida no
    puede tumbar la conversacion -- pero antes tampoco dejaba rastro: un fallo
    sistematico (ej. un cambio de proveedor que rompe el formato JSON
    esperado) se veia identico a "el usuario no conto nada util" y podia
    degradar la calidad de los datos declarados durante semanas sin que nadie
    lo notara. Ver metricas_extraccion().
    """
    import json

    _metricas_extraccion["intentos"] += 1

    respuesta = generar_respuesta(SYSTEM_PROMPT_EXTRACTOR, [], instruccion)
    if respuesta == MENSAJE_FALLBACK:
        _registrar_fallo_extraccion("el proveedor de LLM fallo (ver el error logueado arriba)")
        return {}

    texto = respuesta.strip()
    # algunos modelos envuelven el JSON en ```json ... ``` pese a la instruccion
    if texto.startswith("```"):
        texto = texto.split("```")[1] if "```" in texto[3:] else texto[3:]
        texto = texto.removeprefix("json").strip()
    # o lo acompanan de una frase: se recorta al primer objeto balanceado
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fin <= inicio:
        _registrar_fallo_extraccion(f"la respuesta no trae un objeto JSON: {texto[:200]!r}")
        return {}

    try:
        datos = json.loads(texto[inicio : fin + 1])
    except (ValueError, TypeError):
        _registrar_fallo_extraccion(f"el JSON no es parseable: {texto[inicio:fin + 1][:200]!r}")
        return {}

    if not isinstance(datos, dict):
        _registrar_fallo_extraccion(f"el JSON parseo pero no es un objeto: {type(datos).__name__}")
        return {}

    return datos


# Contadores en memoria de proceso (se reinician con cada deploy/restart,
# igual que el resto del estado en memoria de la app -- ver "pendientes
# conocidos" en SOBRE MI/MIEMPRESA.md). Alcanza para ver un fallo sistematico
# durante el dia: para retener historia entre reinicios haria falta
# persistirlo en Supabase, que hoy es mas de lo que este problema necesita.
_metricas_extraccion = {"intentos": 0, "fallos": 0}


def _registrar_fallo_extraccion(motivo: str) -> None:
    _metricas_extraccion["fallos"] += 1
    logging.warning(
        "[llm_client] fallo de extraccion #%d: %s", _metricas_extraccion["fallos"], motivo
    )


def metricas_extraccion() -> dict:
    """Tasa de fallos de extraer_json desde que arranco el proceso. La expone
    /api/asesor/resumen-dia para que un fallo sistematico sea visible en el
    panel en vez de solo en los logs de Render."""
    intentos = _metricas_extraccion["intentos"]
    fallos = _metricas_extraccion["fallos"]
    return {
        "intentos": intentos,
        "fallos": fallos,
        "tasa_fallos_pct": round(fallos / intentos * 100, 1) if intentos else 0.0,
    }


def _resetear_metricas_extraccion() -> None:
    """Solo para tests: los contadores son estado global de proceso y no
    deben arrastrarse de un test a otro."""
    _metricas_extraccion["intentos"] = 0
    _metricas_extraccion["fallos"] = 0


def _generar_openai(mensajes: list[dict]) -> str:
    from openai import OpenAI

    if not config.OPENAI_API_KEY:
        return _fallback_sin_key(mensajes)

    client = OpenAI(api_key=config.OPENAI_API_KEY, timeout=TIMEOUT_LLM_SEGUNDOS, max_retries=1)
    resp = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=mensajes,
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()


def _generar_gemini(system_prompt: str, historial: list[dict], instruccion_turno: str) -> str:
    import google.generativeai as genai

    if not config.GOOGLE_API_KEY:
        return _fallback_sin_key([{"content": instruccion_turno}])

    genai.configure(api_key=config.GOOGLE_API_KEY)
    modelo = genai.GenerativeModel(config.GEMINI_MODEL, system_instruction=system_prompt)
    chat = modelo.start_chat(history=[
        {"role": "user" if h["role"] == "user" else "model", "parts": [h["content"]]}
        for h in historial
    ])
    resp = chat.send_message(instruccion_turno)
    return resp.text.strip()


def _generar_vertex(system_prompt: str, historial: list[dict], instruccion_turno: str) -> str:
    """Usa Vertex AI (google-genai con vertexai=True) en vez de la API key
    de AI Studio. Requiere GOOGLE_CLOUD_PROJECT y GOOGLE_APPLICATION_CREDENTIALS
    (archivo JSON de cuenta de servicio con rol Vertex AI User) configurados
    en .env -- ver config.py."""
    from google import genai
    from google.genai import types

    if not (config.VERTEX_PROJECT and config.VERTEX_CREDENTIALS_PATH):
        return _fallback_sin_key([{"content": instruccion_turno}])

    client = genai.Client(
        vertexai=True, project=config.VERTEX_PROJECT, location=config.VERTEX_LOCATION
    )
    contenidos = [
        types.Content(
            role="user" if h["role"] == "user" else "model",
            parts=[types.Part(text=h["content"])],
        )
        for h in historial
    ]
    contenidos.append(types.Content(role="user", parts=[types.Part(text=instruccion_turno)]))

    resp = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=contenidos,
        config=types.GenerateContentConfig(system_instruction=system_prompt),
    )
    return resp.text.strip()


def _fallback_sin_key(mensajes: list[dict]) -> str:
    return (
        "[MODO SIN API KEY] Configura OPENAI_API_KEY o GOOGLE_API_KEY en el archivo .env "
        "para activar las respuestas del agente. Instruccion interna que se iba a usar: "
        f"{mensajes[-1]['content']}"
    )
