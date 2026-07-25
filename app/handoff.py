"""Arma el resumen estructurado que se le entrega al asesor comercial:
info del usuario, proyecto recomendado, probabilidad de compra y un dato
interesante para romper el hielo en la llamada."""
from app.conversation import Sesion


def _dato_interesante(sesion: Sesion) -> str:
    if sesion.respuestas_aspiracionales:
        tema, respuesta = next(iter(sesion.respuestas_aspiracionales.items()))
        return f"al preguntarle sobre {tema}, respondio: \"{respuesta}\""
    if sesion.usuario and sesion.usuario.get("Suscripciones actuales"):
        return f"mencionamos que tiene suscripcion activa a {sesion.usuario['Suscripciones actuales']}"
    return ""


def construir_resumen(sesion: Sesion) -> dict:
    usuario = sesion.usuario or {}
    resultado = sesion.resultado_scoring
    recomendacion = sesion.recomendacion

    return {
        "usuario": {
            "nombre": usuario.get("Nombre", "Sin identificar"),
            "documento": usuario.get("Documento", ""),
            "correo": usuario.get("Correo", ""),
            "telefono": sesion.telefono,
            "ciudad": usuario.get("Ciudad", ""),
            "afiliado_colsubsidio": usuario.get("Afiliado a colsubsidio", ""),
        },
        "proyecto_recomendado": (
            {
                "nombre": recomendacion.proyecto["nombre_proyecto"],
                "ciudad": recomendacion.proyecto["ciudad"],
                "segmento": recomendacion.proyecto["segmento_poblacional"],
                "precio_promedio_millones_cop": recomendacion.proyecto["precio_promedio_millones_cop"],
            }
            if recomendacion
            else None
        ),
        "probabilidad_compra": (
            {
                "score": resultado.score,
                "segmento_lead": resultado.segmento_lead,
                "razones": resultado.razones,
            }
            if resultado
            else None
        ),
        "subsidios_aplicables": (
            [s.nombre for s in resultado.subsidios_elegibles] if resultado else []
        ),
        "dato_interesante": _dato_interesante(sesion),
        "respuestas_aspiracionales": sesion.respuestas_aspiracionales,
    }


_ETIQUETA_URGENCIA = {
    "CALIENTE": "listo para cerrar — vale la pena llamar hoy mismo",
    "TIBIO": "con buen potencial, pero todavia necesita acompañamiento",
    "FRIO": "aun no esta listo para comprar, mejor pasar este lead a flujo de nutricion",
}


def formatear_email(resumen: dict) -> tuple[str, str]:
    u = resumen["usuario"]
    proyecto = resumen["proyecto_recomendado"]
    prob = resumen["probabilidad_compra"]
    subsidios = resumen["subsidios_aplicables"]

    segmento_lead = prob["segmento_lead"] if prob else "SIN DATOS"
    asunto = f"Nuevo lead {segmento_lead}: {u['nombre']}"

    afiliado_txt = (
        "esta afiliado a Colsubsidio" if str(u["afiliado_colsubsidio"]).strip().lower() == "si"
        else "no esta afiliado a Colsubsidio todavia"
    )
    contacto_partes = [p for p in [u["telefono"], u["correo"]] if p]
    contacto_txt = " o ".join(str(p) for p in contacto_partes) or "sin datos de contacto"

    parrafos = [
        "Hola,",
        "",
        f"Te comparto un lead que acaba de terminar su conversacion con el Asesor Digital de Vivienda.",
        "",
        f"{u['nombre']} ({u['documento']}) vive en {u['ciudad']} y {afiliado_txt}. "
        f"Se puede contactar al {contacto_txt}.",
    ]

    if resumen.get("dato_interesante"):
        parrafos.append("")
        parrafos.append(f"Durante la conversacion, {resumen['dato_interesante']}.")

    if prob:
        urgencia = _ETIQUETA_URGENCIA.get(segmento_lead, "")
        parrafos.append("")
        parrafos.append(
            f"Su probabilidad de compra quedo calificada como {segmento_lead} "
            f"(score interno {prob['score']}/100) — {urgencia}. Esto se basa en:"
        )
        parrafos += [f"  • {razon}" for razon in prob["razones"]]
    else:
        parrafos.append("")
        parrafos.append("Aun no hay suficiente informacion para calcular su probabilidad de compra.")

    if proyecto:
        precio = proyecto.get("precio_promedio_millones_cop")
        precio_txt = f"${precio}M COP" if precio is not None else "el precio se pacta en SMMLV al momento de escriturar"
        parrafos.append("")
        parrafos.append(
            f"El proyecto que mejor se ajusta a su perfil es {proyecto['nombre']}, en {proyecto['ciudad']} "
            f"(segmento {proyecto['segmento']}); {precio_txt}."
        )
    else:
        parrafos.append("")
        parrafos.append("Todavia no hay un proyecto recomendado (informacion insuficiente).")

    if subsidios:
        parrafos.append("")
        if len(subsidios) == 1:
            parrafos.append(f"Tambien aplica al subsidio de vivienda {subsidios[0]}, lo que le ayudaria con la cuota inicial.")
        else:
            lista = ", ".join(subsidios[:-1]) + f" y {subsidios[-1]}"
            parrafos.append(f"Ademas aplica a varios subsidios de vivienda: {lista} — vale la pena mencionarle esto en la llamada.")

    parrafos += ["", "Saludos,", "Asesor Digital de Vivienda"]

    return asunto, "\n".join(parrafos)
