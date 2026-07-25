"""Unico punto de contacto con el proveedor de LLM. Aislado a proposito:
para cambiar de proveedor o de modelo solo se toca este archivo."""
from app import config

MENSAJE_FALLBACK = "Uy, se me cruzaron los cables un segundo. ¿Me repites lo último que me contabas?"


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


def _generar_openai(mensajes: list[dict]) -> str:
    from openai import OpenAI

    if not config.OPENAI_API_KEY:
        return _fallback_sin_key(mensajes)

    client = OpenAI(api_key=config.OPENAI_API_KEY)
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
