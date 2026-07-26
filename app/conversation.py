"""Orquestacion de la conversacion. Las fases y transiciones las decide
este modulo en Python (deterministico, auditable, imposible de romper por
una alucinacion del LLM); el LLM solo se usa para redactar cada mensaje en
lenguaje natural, siguiendo las reglas de SOBRE MI/.
"""
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app import config, data_store, extraccion, llm_client, recommender, scoring

BASE_DIR = Path(__file__).resolve().parent.parent
SOBRE_MI_DIR = BASE_DIR / "SOBRE MI"

# Temas de la conversacion, en el orden en que se preguntan. Los que tienen
# califica=True alimentan el scoring (ver app/extraccion.py): no se preguntan
# de frente ("cuanto ganas", "estas afiliado") sino de costado, como indica
# SOBREMI.md, y van intercalados con los aspiracionales para que la charla no
# se sienta como un formulario.
# El campo de cada tema que califica es el dato que esa pregunta busca: si el
# usuario ya lo conto por su cuenta antes de que le tocara el turno, la
# pregunta se salta (ver _preguntas_restantes). Preguntar algo que la persona
# acaba de responder es la forma mas rapida de que la charla se sienta un
# formulario automatico.
TEMAS = [
    {
        "pregunta": "que suenos o planes tiene con este paso de comprar vivienda",
        "campo": None,
    },
    {
        "pregunta": "en que empresa trabaja actualmente o a que se dedica hoy",
        "campo": "situacion_laboral",
    },
    {
        "pregunta": "si esta pensando en comprar para vivir ahi o como inversion",
        "campo": None,
    },
    {
        "pregunta": "si ya viene ahorrando o tiene cesantias pensando en la cuota inicial",
        "campo": "ahorro_cuota_inicial",
    },
    {
        "pregunta": "con quien se estaria mudando (solo/a, en pareja, con hijos)",
        "campo": "estructura_familiar",
    },
    {
        "pregunta": "que es indispensable para el/ella en su proxima casa (espacio, ubicacion, zonas comunes)",
        "campo": None,
    },
    {
        "pregunta": "como se imagina o donde se ve viviendo en los proximos 5 anios",
        "campo": None,
    },
    {
        "pregunta": "como es su estilo de vida hoy (trabajo, familia, deporte, rutina)",
        "campo": None,
    },
]

PREGUNTAS_ASPIRACIONALES_SUGERIDAS = [t["pregunta"] for t in TEMAS]
PREGUNTAS_QUE_CALIFICAN = {t["pregunta"] for t in TEMAS if t["campo"]}
CAMPO_POR_PREGUNTA = {t["pregunta"]: t["campo"] for t in TEMAS if t["campo"]}

# MIN sube de 3 a 4 y MAX de 5 a 6 para que la conversacion alcance a pasar
# por los tres temas que califican (posiciones 2, 4 y 5 de TEMAS) antes de
# recomendar. Con los valores viejos la charla cerraba habiendo preguntado uno
# solo, y el score seguia saliendo entero de la base.
MIN_PREGUNTAS = 4
MAX_PREGUNTAS = 6
LIMITE_EVASION = 2

FRASES_EVASION = {
    "no quiero responder", "no quiero decir", "no quiero contar",
    "prefiero no responder", "prefiero no decir", "prefiero no contar",
    "no voy a responder", "no te voy a decir", "no es tu asunto",
    "no te importa", "es confidencial", "eso no te lo",
}
PALABRAS_EVASION_CORTAS = {"no", "nada", "ninguno", "ninguna", "paso", "siguiente"}


def _cargar_texto(nombre_archivo: str) -> str:
    ruta = SOBRE_MI_DIR / nombre_archivo
    return ruta.read_text(encoding="utf-8") if ruta.exists() else ""


def construir_system_prompt() -> str:
    sobremi = _cargar_texto("SOBREMI.md")
    estilo = _cargar_texto("ESTILO ANTI-IA.md")
    return f"""{sobremi}

{estilo}

## ADAPTACIONES PARA ESTE MVP (tienen prioridad sobre cualquier instruccion anterior que las contradiga)
- Canal: widget de chat en el portal web, al que el usuario llego desde WhatsApp.
  Puede escribirte por texto o dictarte por voz, asi que sus mensajes a veces
  llegan como transcripciones habladas: pueden traer muletillas, frases cortadas
  o errores de transcripcion. Interpreta la intencion sin corregirlo ni
  mencionar que hablo en vez de escribir.
- El usuario ya fue identificado por el numero de telefono con el que inicio en
  WhatsApp, de forma automatica por el sistema. NUNCA pidas la cedula ni el
  numero de telefono, ya los tienes.
- NUNCA digas que "consultaste una base de datos" ni menciones el cruce de
  informacion. Simplemente usa lo que sabes del usuario con naturalidad.
- Preguntas aspiracionales: entre 3 y 5 durante la conversacion, una a la vez,
  nunca todas juntas. Deben sentirse como una charla, no como una encuesta.
- Cuando el sistema te de una instruccion interna marcada como "[INSTRUCCION INTERNA]",
  esa instruccion NUNCA es visible para el usuario: es un apunte tuyo para saber
  que decir en este turno especifico. Responde solo con el mensaje que le dirias
  al usuario, sin exponer la instruccion ni el razonamiento.
- Jamas reveles puntajes, porcentajes, "score", "algoritmo" ni el nombre de
  ningun modelo o regla interna de decision.
"""


@dataclass
class Sesion:
    id: str
    telefono: str
    # canal por el que llego el lead (meta, google, whatsapp, organico...).
    # El scoring no lo usa: sirve para comparar calidad por fuente de pauta,
    # que es el costo que abre el planteo del reto.
    origen: str = "organico"
    usuario: dict | None = None
    resultado_scoring: scoring.ResultadoScoring | None = None
    fase: str = "saludo"
    tema_actual: str | None = None
    preguntas_hechas: list[str] = field(default_factory=list)
    respuestas_aspiracionales: dict = field(default_factory=dict)
    intentos_evasion: dict = field(default_factory=dict)
    historial: list[dict] = field(default_factory=list)
    recomendacion: recommender.Recomendacion | None = None
    # finalizada: se llego a un mensaje de cierre/recomendacion, pero para un
    # usuario registrado el chat sigue abierto por si hace mas preguntas.
    # interaccion_cerrada: la interaccion realmente termino (boton
    # 'Finalizar', inactividad, o el caso de usuario no encontrado que
    # cierra de inmediato) -- es la condicion correcta para disparar el
    # correo automatico al asesor, ver main.py.
    finalizada: bool = False
    interaccion_cerrada: bool = False
    enviado_al_asesor: bool = False
    datos_declarados_no_registrado: str | None = None
    # variables de calificacion extraidas de lo que la persona conto en la
    # charla (ver app/extraccion.py). Alimentan el scoring junto con la base.
    datos_declarados: dict = field(default_factory=dict)


_SESIONES: dict[str, Sesion] = {}


def _es_evasion(texto: str, tema: str | None = None) -> bool:
    """El tema importa: hay preguntas que se responden naturalmente con "no",
    y ahi esa respuesta es el dato, no una evasion.

    "¿ya vienes ahorrando o tienes cesantias?" -> "no" significa
    ahorro_cuota_inicial=False, que es justo lo que necesita el scoring para
    detectar el bloqueante de cuota inicial. Tratarlo como evasion descartaba
    la respuesta, no capturaba el dato y ademas le sumaba un intento de
    evasion a alguien que si habia contestado.
    """
    texto_low = texto.strip().lower()
    palabras = [p.strip(".,!¡¿?") for p in texto_low.split()]
    if palabras and len(palabras) <= 3 and all(p in PALABRAS_EVASION_CORTAS for p in palabras):
        return CAMPO_POR_PREGUNTA.get(tema) not in extraccion.CAMPOS_BOOLEANOS
    return any(frase in texto_low for frase in FRASES_EVASION)


def _preguntas_restantes(sesion: Sesion) -> list[str]:
    """Temas que faltan por preguntar. Se descartan los que califican cuyo dato
    la persona ya conto espontaneamente: no tiene sentido preguntar 'en que
    empresa trabajas' a alguien que abrio la charla diciendo donde trabaja."""
    return [
        pregunta
        for pregunta in PREGUNTAS_ASPIRACIONALES_SUGERIDAS
        if pregunta not in sesion.preguntas_hechas
        and CAMPO_POR_PREGUNTA.get(pregunta) not in sesion.datos_declarados
    ]


def _capturar_datos_declarados(sesion: Sesion, texto_usuario: str, tema: str | None) -> None:
    """Extrae variables de calificacion del mensaje y recalcula el score.

    Corre en TODOS los turnos de la fase aspiracional, no solo en los temas
    que califican: la gente aporta datos duros cuando quiere, no cuando se los
    preguntan. En una prueba real el usuario dijo "tengo unas cesantias
    guardadas para la cuota inicial" respondiendo a una pregunta aspiracional,
    y ese dato se perdia porque la extraccion solo miraba los temas
    calificadores. Cuesta una llamada extra al LLM por turno y evita tirar a
    la basura justamente la informacion que el reto pide capturar.

    El score se recalcula aqui mismo para que el panel de explicabilidad lo
    muestre moverse durante la conversacion, no solo al final.
    """
    if _es_evasion(texto_usuario, tema):
        return

    nuevos = extraccion.extraer_de_mensaje(texto_usuario, tema)
    if not nuevos:
        return

    sesion.datos_declarados.update(nuevos)

    if sesion.usuario:
        sesion.resultado_scoring = scoring.calcular_score(
            sesion.usuario, datos_declarados=sesion.datos_declarados
        )
    else:
        sesion.resultado_scoring = scoring.calcular_score_no_registrado(sesion.datos_declarados)


def _construir_resumen_usuario(usuario: dict) -> str:
    """Construye un resumen con los campos disponibles del usuario para incluir en la instruccion."""
    campos = {
        "Nombre": usuario.get("Nombre"),
        "Ciudad": usuario.get("Ciudad"),
        "Afiliado a colsubsidio": usuario.get("Afiliado a colsubsidio"),
        "Estado de vivienda propia": usuario.get("Estado de vivienda propia"),
        "Suscripciones actuales": usuario.get("Suscripciones actuales"),
        "Estado laboral": usuario.get("Estado laboral"),
        "Fecha de inicio de labores": usuario.get("Fecha de inicio de labores"),
        "Tipo de contrato": usuario.get("Tipo de contrato"),
        "Rango salarial": usuario.get("Rango salarial"),
        "Ha pedido subsidios": usuario.get("Ha pedido subsidios"),
        "Reportado en data crédito": usuario.get("Reportado en data crédito"),
        "Edad": usuario.get("Edad"),
    }
    
    partes = []
    for campo, valor in campos.items():
        if valor and str(valor).strip() and str(valor).lower() not in ("nan", "none", ""):
            partes.append(f"{campo}: {valor}")
    
    return ". ".join(partes) if partes else ""


def iniciar_sesion(telefono: str, origen: str = "organico") -> tuple[Sesion, str]:
    session_id = str(uuid.uuid4())
    usuario = data_store.buscar_usuario_por_telefono(telefono)
    sesion = Sesion(id=session_id, telefono=telefono, origen=origen, usuario=usuario)

    if usuario:
        sesion.resultado_scoring = scoring.calcular_score(usuario)
        resumen_usuario = _construir_resumen_usuario(usuario)
        instruccion = (
            "[INSTRUCCION INTERNA] Este es el primer mensaje de la conversacion. "
            f"Datos del usuario: {resumen_usuario}. "
            "Saludalo de forma calida y natural (nunca menciones que revisaste una base de datos). "
            "Luego haz, con tus propias palabras, "
            f"esta primera pregunta abierta: '{PREGUNTAS_ASPIRACIONALES_SUGERIDAS[0]}'."
        )
        sesion.fase = "aspiracional"
        sesion.tema_actual = PREGUNTAS_ASPIRACIONALES_SUGERIDAS[0]
        sesion.preguntas_hechas.append(PREGUNTAS_ASPIRACIONALES_SUGERIDAS[0])
    else:
        instruccion = (
            "[INSTRUCCION INTERNA] Este es el primer mensaje de la conversacion y no "
            "encontraste registro previo de este numero. Saluda de forma calida y pide "
            "su nombre y ciudad para poder ayudarle, sin sonar a formulario."
        )
        sesion.fase = "captura_basica"

    respuesta = llm_client.generar_respuesta(construir_system_prompt(), [], instruccion)
    sesion.historial.append({"role": "assistant", "content": respuesta})
    _SESIONES[session_id] = sesion
    return sesion, respuesta


def obtener_sesion(session_id: str) -> Sesion | None:
    return _SESIONES.get(session_id)


def procesar_mensaje(sesion: Sesion, texto_usuario: str) -> str:
    sesion.historial.append({"role": "user", "content": texto_usuario})

    if sesion.fase == "captura_basica":
        # se guarda tal cual (sin parsear nombre/ciudad por separado) para no
        # arriesgar una extraccion equivocada; el asesor lo lee como texto
        # libre en el correo de handoff (ver handoff.formatear_email)
        sesion.datos_declarados_no_registrado = texto_usuario.strip()
        # el primer mensaje de un no registrado suele traer nombre y ciudad,
        # pero a veces tambien a que se dedica: se extrae igual
        _capturar_datos_declarados(sesion, texto_usuario, None)
        instruccion = (
            f"[INSTRUCCION INTERNA] El usuario respondio: '{texto_usuario}'. "
            "Agradece y continua con la primera pregunta aspiracional: "
            f"'{PREGUNTAS_ASPIRACIONALES_SUGERIDAS[0]}'."
        )
        sesion.fase = "aspiracional"
        sesion.tema_actual = PREGUNTAS_ASPIRACIONALES_SUGERIDAS[0]
        sesion.preguntas_hechas.append(PREGUNTAS_ASPIRACIONALES_SUGERIDAS[0])
        respuesta = llm_client.generar_respuesta(construir_system_prompt(), sesion.historial, instruccion)
        sesion.historial.append({"role": "assistant", "content": respuesta})
        return respuesta

    if sesion.fase == "aspiracional":
        tema = sesion.tema_actual
        _capturar_datos_declarados(sesion, texto_usuario, tema)
        if _es_evasion(texto_usuario, tema):
            sesion.intentos_evasion[tema] = sesion.intentos_evasion.get(tema, 0) + 1
            if sesion.intentos_evasion[tema] < LIMITE_EVASION:
                instruccion = (
                    f"[INSTRUCCION INTERNA] El usuario evadio la pregunta sobre '{tema}'. "
                    "No insistas de forma agresiva: cambia de tema con suavidad y sigue la charla."
                )
            else:
                instruccion = None  # se resuelve abajo, avanza de tema igual
        else:
            sesion.respuestas_aspiracionales[tema] = texto_usuario
            instruccion = None

        preguntas_restantes = _preguntas_restantes(sesion)
        # no se recomienda hasta haber cubierto los temas que califican, ya sea
        # porque se preguntaron o porque la persona los conto sola. El tope de
        # MAX_PREGUNTAS sigue mandando, para que la charla no se estire
        # indefinidamente si evade todo.
        califican_pendientes = {
            pregunta
            for pregunta in PREGUNTAS_QUE_CALIFICAN
            if pregunta not in sesion.preguntas_hechas
            and CAMPO_POR_PREGUNTA[pregunta] not in sesion.datos_declarados
        }
        suficientes = (
            not califican_pendientes and len(sesion.respuestas_aspiracionales) >= MIN_PREGUNTAS
        ) or len(sesion.preguntas_hechas) >= MAX_PREGUNTAS

        if instruccion is None:
            if suficientes or not preguntas_restantes:
                return _pasar_a_recomendacion(sesion)
            siguiente_tema = preguntas_restantes[0]
            sesion.tema_actual = siguiente_tema
            sesion.preguntas_hechas.append(siguiente_tema)
            instruccion = (
                f"[INSTRUCCION INTERNA] El usuario respondio: '{texto_usuario}'. Agradece brevemente "
                "de forma natural (no repitas siempre la misma muletilla) y haz, con tus propias palabras, "
                f"esta siguiente pregunta abierta: '{siguiente_tema}'."
            )

        respuesta = llm_client.generar_respuesta(construir_system_prompt(), sesion.historial, instruccion)
        sesion.historial.append({"role": "assistant", "content": respuesta})
        return respuesta

    if sesion.fase in ("recomendacion", "cierre"):
        instruccion = (
            f"[INSTRUCCION INTERNA] La conversacion ya cerro con una recomendacion. El usuario escribio: "
            f"'{texto_usuario}'. Respondele de forma breve y natural, resolviendo su duda si es sencilla, "
            "sin repetir toda la recomendacion anterior."
        )
        respuesta = llm_client.generar_respuesta(construir_system_prompt(), sesion.historial, instruccion)
        sesion.historial.append({"role": "assistant", "content": respuesta})
        return respuesta

    return "Disculpa, ¿me lo puedes repetir?"


def finalizar_sesion(sesion: Sesion, motivo: str = "manual") -> str:
    """Cierra la conversacion a peticion explicita: boton 'Finalizar' del
    usuario o inactividad de 3 min (ver /api/finalizar en main.py). Es lo que
    marca interaccion_cerrada=True (dispara el correo al asesor, ver main.py),
    incluso si ya se habia dado una recomendacion antes (sesion.finalizada);
    un usuario registrado puede seguir haciendo preguntas despues de la
    recomendacion, y el correo no debe salir hasta que de verdad termine.
    Idempotente: si la interaccion ya estaba cerrada no genera un nuevo
    mensaje de despedida, solo repite el ultimo."""
    if sesion.interaccion_cerrada:
        return sesion.historial[-1]["content"] if sesion.historial else ""

    if motivo == "inactividad":
        instruccion = (
            "[INSTRUCCION INTERNA] La conversacion se esta cerrando automaticamente porque "
            "el usuario no respondio en varios minutos. Explicale, de forma breve y calida "
            "(sin sonar brusco ni robotico), que estas cerrando la conversacion por inactividad, "
            "y deja claro que puede escribir de nuevo cuando quiera retomarla."
        )
    else:
        instruccion = (
            "[INSTRUCCION INTERNA] El usuario decidio finalizar la conversacion voluntariamente "
            "desde el chat. Agradece su tiempo y despidete de forma breve y calida."
        )

    respuesta = llm_client.generar_respuesta(construir_system_prompt(), sesion.historial, instruccion)
    sesion.historial.append({"role": "assistant", "content": respuesta})
    sesion.fase = "cierre"
    sesion.finalizada = True
    sesion.interaccion_cerrada = True
    return respuesta


def _describir_proyecto_para_llm(proyecto: dict) -> str:
    """Arma la ficha de datos verificados del proyecto que se le pasa al LLM.
    Si el proyecto viene de un brochure real (RECURSOS/PROYECTOS/*.json) se
    incluyen los argumentos de venta y el perfil de comprador ya redactados
    y verificados; si es del catalogo sintetico se arma una ficha basica."""
    if proyecto.get("fuente") == "real":
        tipologias = proyecto.get("tipologias", [])
        resumen_tipologias = "; ".join(
            f"{t.get('codigo')}: {t.get('alcobas')} alcoba(s), {t.get('area_construida_m2')} m2"
            for t in tipologias
        ) or "sin detalle de tipologias"
        argumentos = "; ".join(proyecto.get("argumentos_venta", [])) or "sin argumentos registrados"
        brochure_url = proyecto.get("brochure_url", "")
        nota_brochure = (
            f"Brochure digital del proyecto (link real, compartelo tal cual, sin modificarlo ni "
            f"inventar otro): {brochure_url} -- al final de tu mensaje, invita al usuario con una "
            "frase natural a revisarlo si quiere conocer mas del proyecto, e incluye el link."
            if brochure_url else ""
        )
        return (
            f"Proyecto sugerido: {proyecto['nombre_proyecto']} en {proyecto['ciudad']} "
            f"(segmento {proyecto['segmento_poblacional']}, estado: {proyecto.get('etapa_actual', 'sin dato')}). "
            f"Resumen verificado: {proyecto.get('resumen', '')} "
            f"Perfil de comprador ideal segun el proyecto: {proyecto.get('perfil_comprador', '')} "
            f"Tipologias disponibles: {resumen_tipologias}. "
            f"Amenities: {', '.join(proyecto.get('amenities', [])) or 'zonas comunes basicas'}. "
            f"Argumentos de venta verificados (elige los 2-3 mas relevantes para este usuario, no los repitas todos): {argumentos}. "
            f"Sobre el precio: {proyecto.get('nota_financiacion') or 'no se tiene un valor fijo en pesos, se pacta en salarios minimos al momento de escriturar'}. "
            "Si el usuario pregunta por un precio exacto en pesos, dile con honestidad que el asesor "
            f"se lo confirma, sin inventar una cifra. {nota_brochure}"
        )

    precio = proyecto.get("precio_promedio_millones_cop")
    precio_txt = f"precio promedio ${precio}M COP" if precio is not None else "precio a confirmar con el asesor"
    return (
        f"Proyecto sugerido: {proyecto['nombre_proyecto']} en {proyecto['ciudad']}, "
        f"categoria {proyecto.get('categoria_dominante', 'vivienda')}, {precio_txt}, "
        f"amenities: {', '.join(proyecto.get('amenities', [])) or 'zonas comunes basicas'}."
    )


def _pasar_a_recomendacion(sesion: Sesion) -> str:
    usuario = sesion.usuario
    if usuario is None:
        sesion.fase = "cierre"
        sesion.finalizada = True
        # a diferencia del usuario registrado (ver mas abajo), aqui no hay
        # recomendacion ni pie para mas preguntas: la interaccion termina
        # de verdad en este mismo mensaje, asi que el correo se puede
        # disparar ya (ver main.py)
        sesion.interaccion_cerrada = True
        # sin registro el score se arma con lo que la persona conto en la
        # charla, con un factor de confianza por no estar verificado; si no
        # conto nada, cae en la penalizacion fija. En ningun caso queda "SIN
        # DATOS": el lead no se pierde de vista.
        sesion.resultado_scoring = scoring.calcular_score_no_registrado(sesion.datos_declarados)
        instruccion = (
            "[INSTRUCCION INTERNA] No tienes datos financieros de este usuario en el sistema. "
            "Agradece la conversacion, explica con calidez que un asesor se pondra en contacto "
            "para continuar el proceso. Ademas, invitalo (de forma calida, sin sonar a venta "
            "agresiva) a registrarse como afiliado de Colsubsidio para que pueda disfrutar de "
            "todos los beneficios de pertenecer a Colsubsidio, y comparte este link para hacerlo: "
            "https://www.colsubsidio.com/afiliaciones -- luego despidete."
        )
        respuesta = llm_client.generar_respuesta(construir_system_prompt(), sesion.historial, instruccion)
        sesion.historial.append({"role": "assistant", "content": respuesta})
        return respuesta

    if sesion.resultado_scoring is None:
        sesion.resultado_scoring = scoring.calcular_score(
            usuario, datos_declarados=sesion.datos_declarados
        )

    sesion.recomendacion = recommender.recomendar_proyecto(
        usuario, sesion.resultado_scoring.project_segment, sesion.respuestas_aspiracionales
    )
    proyecto = sesion.recomendacion.proyecto
    razones_humanas = "; ".join(sesion.recomendacion.razones) or "encaja con su perfil general"
    segmento_lead = sesion.resultado_scoring.segmento_lead

    if segmento_lead in ("CALIENTE", "TIBIO"):
        tono = (
            "Cierra con un tono celebratorio y calido. Confirma que un asesor experto lo va a "
            "contactar pronto al mismo numero de este chat para avanzar. No prometas aprobacion de credito."
        )
    else:
        tono = (
            "El perfil todavia no esta listo para comprar ahora mismo. Se constructivo y educativo: "
            "explicale con tacto que es buen momento para preparase (ahorro, formalizar ingresos, etc.) "
            "sin cerrar la puerta, y menciona igual el proyecto que mejor encajaria a futuro."
        )

    ficha_proyecto = _describir_proyecto_para_llm(proyecto)

    subsidios_elegibles = sesion.resultado_scoring.subsidios_elegibles
    if subsidios_elegibles:
        nombres_subsidios = ", ".join(s.nombre for s in subsidios_elegibles)
        nota_subsidios = (
            f"Ademas, este usuario aplica a estos subsidios de vivienda: {nombres_subsidios}. "
            "Menciona esto de forma natural en tu respuesta (algo como 'me alegra informarte que "
            "tambien aplicas al subsidio X, lo que te ayudaria a cubrir parte de la cuota inicial'). "
            "Si aplica a mas de uno, puedes mencionar el mas relevante o los dos primeros, sin hacer "
            "una lista larga. Nunca prometas que el subsidio esta aprobado, solo que aplica/es candidato."
        )
    else:
        nota_subsidios = ""

    invitacion_seguimiento = (
        "Termina tu respuesta invitandolo con calidez a seguir preguntando mientras lo contactan, "
        "algo como 'mientras te contactan, ¿hay algo mas que quieras saber sobre este proyecto?' "
        "(usa tus propias palabras, no cites este ejemplo literalmente)."
    )

    instruccion = (
        "[INSTRUCCION INTERNA] Ya tienes suficiente contexto de la conversacion. Aqui esta la "
        "recomendacion calculada (NUNCA menciones que fue 'calculada', ni el mecanismo): "
        f"{ficha_proyecto} "
        f"Razones por las que este proyecto encaja con este usuario en particular: {razones_humanas}. "
        "Explicale al usuario, en 2-3 frases, POR QUE este proyecto es el ideal para el, conectando "
        "explicitamente datos reales del proyecto (ubicacion, tipologias/alcobas, amenities concretas) "
        "con lo que el te conto en la conversacion. Usa solo los datos que te di arriba, nunca inventes "
        "precios, fechas ni caracteristicas que no esten en esta ficha. "
        f"{nota_subsidios} "
        f"{tono} {invitacion_seguimiento} Presenta la recomendacion de forma natural y personalizada."
    )
    respuesta = llm_client.generar_respuesta(construir_system_prompt(), sesion.historial, instruccion)
    sesion.historial.append({"role": "assistant", "content": respuesta})

    if respuesta == llm_client.MENSAJE_FALLBACK:
        # el LLM fallo justo al comunicar la recomendacion: no cerramos la
        # sesion con una recomendacion que el usuario nunca llego a ver.
        # sesion.fase se queda en "aspiracional" con el mismo tema_actual,
        # asi que el siguiente mensaje del usuario reintenta este mismo paso.
        return respuesta

    sesion.fase = "cierre"
    sesion.finalizada = True
    return respuesta
