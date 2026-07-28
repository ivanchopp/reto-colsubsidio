"""
Motor de scoring real. Reemplaza el pseudocodigo/stubs de
RECURSOS/Algoritmo_de_Scoring_y_Enrutamiento.py (que llamaba a un
modelo_xgboost inexistente) con reglas explicitas y verificables, basadas en:
  - Las reglas de negocio que SI estaban explicitas en ese pseudocodigo
    (penalizacion por reporte en datacredito, penalizacion regla 90/10,
    umbrales CALIENTE/FRIO).
  - El arbol de decision VIS / No VIS de RECURSOS/buyer_persona_scoring_schema.json.
  - Comparacion contra el comportamiento de otros usuarios con el mismo
    perfil dentro del Excel (perfilamiento inteligente de leads).
"""
from dataclasses import dataclass, field

from app import config, data_store, vector_similarity

SEGMENTO_INCOME_THRESHOLD_SMLV = 4.0  # por debajo de esto, el lead aplica a VIS
CREDIT_SCORE_THRESHOLD = 600
CREDIT_SCORE_REPORTADO = 300
CREDIT_SCORE_NO_REPORTADO = 750

EMPLOYER_TIER_MULTIPLIER = {"Tier 1": 1.15, "Tier 2": 1.0, "Tier 3": 0.85}

# penalizacion fija (no formula) para leads sin registro en el sistema: no hay
# como verificar ingreso, estabilidad laboral ni antecedentes en centrales de
# riesgo, asi que no corren el modelo de reglas real -- se les asigna este
# score bajo por defecto en vez de dejarlos sin calificar ("SIN DATOS"), para
# que el asesor los vea como lead de baja confianza y no los pierda de vista.
SCORE_NO_REGISTRADO = 15.0

# savings_fna_cesantias del buyer_persona_scoring_schema.json: rol
# "liquidity_indicator". Poder aportar cuota inicial es lo que separa una
# intencion de una compra, asi que suma; declarar que NO se tiene no penaliza
# (mucha gente compra igual con credito y subsidio), solo deja de sumar.
BONO_AHORRO_CUOTA_INICIAL = 8.0

# Mismo rol "liquidity_indicator", pero con el dato verificado de la base
# (usuarios.ahorros) en vez de lo declarado en la conversacion. Vale mas que
# BONO_AHORRO_CUOTA_INICIAL porque es un dato duro, y escala con el monto en
# vez de ser un bono fijo -- ver AHORRO_VERIFICADO_TECHO_COP en config.py.
BONO_AHORRO_VERIFICADO_MAX = 10.0

# Los datos que el usuario declara en la conversacion no estan verificados
# contra ninguna fuente: valen, pero menos que un registro en la base. Un lead
# sin registro que conversa bien puede llegar lejos, no al mismo lugar que uno
# con historial comprobable.
FACTOR_CONFIANZA_DECLARADO = 0.75


@dataclass
class ResultadoScoring:
    score: float  # 0-100
    segmento_lead: str  # CALIENTE / TIBIO / FRIO
    project_segment: str  # VIS / No VIS
    razones: list[str] = field(default_factory=list)
    peer_stats: dict | None = None
    subsidios_elegibles: list = field(default_factory=list)
    # desglose {etiqueta, valor, peso, categoria} de como el blend final
    # (reglas/peers/vectorial + bono de subsidios) llego al score -- lo usa
    # el panel del asesor para el grafico de torta. None cuando el score no
    # viene de ese blend (ver calcular_score_no_registrado).
    contribuciones: list[dict] | None = None


def _midpoint_rango_salarial(rango: str) -> float:
    rango = str(rango).lower().replace("de ", "").strip()
    partes = [p.strip().replace(".", "") for p in rango.split("-")]
    numeros = [float(p) for p in partes if p.replace(",", "").isdigit()]
    if len(numeros) != 2:
        return 0.0
    return sum(numeros) / 2


def _employer_tier(usuario: dict) -> str:
    estado = str(usuario.get("Estado laboral", "")).strip()
    contrato = str(usuario.get("Tipo de contrato", "")).strip()
    if estado == "Empleado" and contrato == "Indefinido":
        return "Tier 1"
    if estado == "Empleado" and contrato == "Fijo":
        return "Tier 2"
    return "Tier 3"  # Independiente, Obra y labor, Desempleado


def _peer_conversion_stats(usuario: dict) -> dict:
    peers = data_store.peers_con_perfil_similar(usuario)
    total = len(peers)
    if total == 0:
        return {"total_peers": 0}
    conteo = peers["Estado de vivienda propia"].value_counts(normalize=True) * 100
    return {
        "total_peers": total,
        "pct_con_vivienda_propia": round(conteo.get("Con vivienda propia", 0.0), 1),
        "pct_desistido": round(conteo.get("Desistido", 0.0), 1),
        "pct_rechazado": round(conteo.get("Rechazado", 0.0), 1),
        "pct_sin_vivienda": round(conteo.get("Sin vivienda", 0.0), 1),
    }


def _lift_de_peers(conversion_peers: float) -> float:
    """Convierte la tasa de conversion de un grupo de peers en una senal 0-100
    comparable con las otras dos del blend.

    La tasa cruda no sirve como score: es un porcentaje de conversion, no un
    puntaje. En la base real ningun grupo pasa del 33%, asi que entraba a un
    slot de 0-100 aportando como maximo 6.6 de los 20 puntos que tenia
    asignados. Lo que importa no es el valor absoluto sino cuanto se despega
    del promedio general: se ancla la tasa base en 50 (grupo promedio, senal
    neutra) y el doble de la base en 100.
    """
    base = data_store.tasa_base_conversion()
    if base <= 0:
        return 50.0
    return max(0.0, min(100.0, conversion_peers / base * 50.0))


def calcular_score(
    usuario: dict,
    family_structure: str | None = None,
    datos_declarados: dict | None = None,
) -> ResultadoScoring:
    """datos_declarados: lo que el usuario conto en la conversacion, ya
    normalizado por app/extraccion.py. Complementa la base, no la reemplaza:
    los datos duros verificables (ingreso, centrales de riesgo) siguen saliendo
    del registro cuando existe."""
    razones: list[str] = []
    datos_declarados = datos_declarados or {}

    # family_structure explicito gana sobre el declarado (lo usan los tests
    # para probar la rama sin pasar por la extraccion)
    if family_structure is None:
        family_structure = datos_declarados.get("estructura_familiar")

    ingreso_promedio = _midpoint_rango_salarial(usuario.get("Rango salarial", ""))
    ingreso_smlv = ingreso_promedio / config.SMLV_COP if ingreso_promedio else 0.0

    afiliado = str(usuario.get("Afiliado a colsubsidio", "")).strip().lower() == "si"
    reportado_datacredito = (
        str(usuario.get("Reportado en data crédito", "")).strip().lower() == "reportado"
    )
    credit_score = CREDIT_SCORE_REPORTADO if reportado_datacredito else CREDIT_SCORE_NO_REPORTADO
    tier = _employer_tier(usuario)
    desempleado = str(usuario.get("Estado laboral", "")).strip() == "Desempleado"

    project_segment = "VIS" if ingreso_smlv <= SEGMENTO_INCOME_THRESHOLD_SMLV else "No VIS"
    base_weight_income = 0.4 if project_segment == "VIS" else 0.7
    # techo de normalizacion propio de cada segmento, calibrado contra el
    # ingreso maximo real de la base (ver config). Antes el techo No VIS era
    # 6.0 SMLV fijo, pero el rango salarial mas alto del archivo llega a 4.3:
    # ningun perfil saturaba nunca el aporte de ingreso y eso solo se bajaba
    # el techo de todo el sistema.
    techo_smlv = (
        config.TECHO_SMLV_VIS if project_segment == "VIS" else config.TECHO_SMLV_NO_VIS
    )

    score = base_weight_income * min(ingreso_smlv / techo_smlv, 1.0) * 100
    razones.append(
        f"Ingreso estimado {ingreso_smlv:.1f} SMLV -> segmento {project_segment}, "
        f"aporte base {score:.1f} pts"
    )

    score *= EMPLOYER_TIER_MULTIPLIER[tier]
    razones.append(f"Estabilidad laboral {tier} ({usuario.get('Estado laboral')} / {usuario.get('Tipo de contrato')})")

    if desempleado:
        score *= 0.15
        razones.append("Sin empleo activo: penalizacion fuerte a la capacidad de pago")

    if project_segment == "VIS":
        if not afiliado:
            score *= 0.2
            razones.append("No afiliado a Colsubsidio en segmento VIS: penalizacion severa (regla 90/10)")
        if family_structure == "Monoparental Joven":
            if afiliado:
                score += 20
                razones.append("Hogar monoparental joven afiliado: +20 pts (aplica beneficios VIS)")
            else:
                score -= 30
                razones.append("Hogar monoparental joven no afiliado: -30 pts")
    else:  # No VIS
        if credit_score < CREDIT_SCORE_THRESHOLD:
            score = 0
            razones.append("Historial crediticio insuficiente para No VIS: score anulado")
        elif afiliado:
            score += 5
            razones.append("Afiliado a Colsubsidio: +5 pts")
        if not afiliado:
            score *= 0.8
            razones.append("No afiliado a Colsubsidio: penalizacion regla 90/10 (x0.8)")

    if reportado_datacredito:
        score *= 0.10
        razones.append("Reportado negativamente en centrales de riesgo: penalizacion casi eliminatoria")

    score = max(0.0, min(100.0, score))

    # blend final: combina el score de reglas con dos senales independientes
    # -- peer-matching (categorico, exacto) y similitud vectorial contra
    # centroides (continuo, aproximado). El arbol de reglas siempre conserva
    # la mayor parte del peso porque codifica restricciones regulatorias
    # (90/10, umbrales VIS/No VIS) que no dependen del tamano de la muestra.
    # Se probo subir "vectorial" a 0.3 con los 500 registros actuales, pero
    # con las tasas de conversion reales de la base (~25-35%, no picos de
    # muestras chicas) eso hacia que nadie llegara a CALIENTE -- se revirtio
    # a 0.2 hasta recalibrar el umbral de CALIENTE junto con el peso.
    pesos = {"reglas": 0.6}
    senales = {"reglas": score}

    peer_stats = _peer_conversion_stats(usuario)
    if peer_stats.get("total_peers", 0) >= 3:
        conversion_peers = peer_stats["pct_con_vivienda_propia"]
        pesos["peers"] = 0.2
        senales["peers"] = _lift_de_peers(conversion_peers)
        razones.append(
            f"{peer_stats['total_peers']} usuarios con perfil similar (mismo rango salarial, "
            f"estado laboral y afiliacion): {conversion_peers}% concreto compra historicamente "
            f"(promedio general de la base: {data_store.tasa_base_conversion():.1f}%)"
        )
    else:
        pesos["reglas"] += 0.2  # sin suficientes peers, ese peso vuelve a las reglas

    vector_stats = vector_similarity.calcular_similitud_vectorial(usuario)
    pesos["vectorial"] = 0.2
    senales["vectorial"] = vector_stats["score_vectorial"]
    razones.append(
        f"Similitud vectorial del perfil contra centroides historicos "
        f"(compro/desistio/rechazado/sin vivienda): {vector_stats['score_vectorial']}/100 "
        "de cercania al centroide de compradores exitosos"
    )

    score = sum(pesos[k] * senales[k] for k in senales)

    _ETIQUETAS_CONTRIBUCION = {
        "reglas": "Reglas (ingreso, estabilidad, afiliación)",
        "peers": "Perfiles similares",
        "vectorial": "Similitud vectorial",
    }
    contribuciones = [
        {
            "etiqueta": _ETIQUETAS_CONTRIBUCION[k],
            "valor": round(pesos[k] * senales[k], 1),
            "peso": pesos[k],
            "categoria": k,
        }
        for k in senales
    ]

    # bono por subsidios de vivienda a los que aplica: poder aportar un
    # subsidio a la cuota inicial mejora su capacidad real de compra
    from app import subsidios  # import diferido: subsidios.py importa de este modulo

    subsidios_elegibles = subsidios.evaluar_subsidios(usuario)
    if subsidios_elegibles:
        bono = subsidios.calcular_bonus_score(subsidios_elegibles)
        score += bono
        nombres = ", ".join(s.nombre for s in subsidios_elegibles)
        razones.append(f"Aplica a {len(subsidios_elegibles)} subsidio(s) de vivienda (+{bono:.0f} pts): {nombres}")
        contribuciones.append(
            {"etiqueta": "Bono por subsidios", "valor": round(bono, 1), "peso": None, "categoria": "subsidios"}
        )

    # liquidez para la cuota inicial: preferir el dato verificado de la base
    # (usuarios.ahorros) sobre lo declarado en la conversacion cuando ambos
    # estan disponibles. NaN se descarta con la comparacion ahorros==ahorros
    # (una fila de pandas sin ahorros llega como NaN, no como None).
    ahorros_verificados = usuario.get("ahorros")
    hay_ahorro_verificado = (
        isinstance(ahorros_verificados, (int, float)) and ahorros_verificados == ahorros_verificados
    )

    if hay_ahorro_verificado:
        bono = min(ahorros_verificados / config.AHORRO_VERIFICADO_TECHO_COP, 1.0) * BONO_AHORRO_VERIFICADO_MAX
        score += bono
        razones.append(
            f"Ahorro verificado en la base (${ahorros_verificados:,.0f} COP) para la cuota "
            f"inicial (+{bono:.1f} pts): dato duro, no declarado"
        )
        contribuciones.append(
            {
                "etiqueta": "Ahorro verificado",
                "valor": round(bono, 1),
                "peso": None,
                "categoria": "ahorro_verificado",
            }
        )
    elif datos_declarados.get("ahorro_cuota_inicial") is True:
        score += BONO_AHORRO_CUOTA_INICIAL
        razones.append(
            f"Declara tener ahorro o cesantias para la cuota inicial "
            f"(+{BONO_AHORRO_CUOTA_INICIAL:.0f} pts): mejora su capacidad real de compra"
        )
        contribuciones.append(
            {
                "etiqueta": "Ahorro para cuota inicial",
                "valor": BONO_AHORRO_CUOTA_INICIAL,
                "peso": None,
                "categoria": "declarado",
            }
        )

    score = max(0.0, min(100.0, score))

    if score >= config.UMBRAL_CALIENTE:
        segmento_lead = "CALIENTE"
    elif score >= config.UMBRAL_TIBIO:
        segmento_lead = "TIBIO"
    else:
        segmento_lead = "FRIO"

    return ResultadoScoring(
        score=round(score, 1),
        segmento_lead=segmento_lead,
        project_segment=project_segment,
        razones=razones,
        peer_stats=peer_stats,
        subsidios_elegibles=subsidios_elegibles,
        contribuciones=contribuciones,
    )


def _perfil_desde_declarados(declarados: dict) -> dict:
    """Arma un usuario parcial con la forma que esperan las reglas, a partir de
    lo que la persona conto. Los campos que no se sabe que valen se dejan
    neutros, nunca en el peor valor posible: no declarar algo no es lo mismo
    que declararlo en contra."""
    situacion = declarados.get("situacion_laboral")
    estado_laboral = {
        "empleado_formal": "Empleado",
        "independiente": "Independiente",
        "desempleado": "Desempleado",
    }.get(situacion, "Independiente")  # neutro: Tier 3 sin la penalizacion de desempleo

    ingreso = declarados.get("ingresos_mensuales_aprox")
    if not ingreso and situacion:
        # no dijo cuanto gana, pero si a que se dedica: se asume la mediana de
        # ese grupo en vez de dejar el ingreso en 0. Ver INGRESO_SUPUESTO_*
        ingreso = config.INGRESO_SUPUESTO_POR_SITUACION.get(situacion)
    # el parser de rangos espera el formato del Excel; un ingreso puntual se
    # expresa como un rango degenerado para no duplicar logica de parseo
    rango_salarial = f"de {int(ingreso)} - {int(ingreso)}" if ingreso else ""

    return {
        "Rango salarial": rango_salarial,
        "Estado laboral": estado_laboral,
        # solo un empleado formal esta necesariamente afiliado a una caja de
        # compensacion; para el resto no se puede afirmar
        "Tipo de contrato": "Indefinido" if situacion == "empleado_formal" else "Obra y labor",
        "Afiliado a colsubsidio": "Si" if situacion == "empleado_formal" else "No",
        # sin consulta a centrales no hay reporte que aplicar: se asume limpio
        # en vez de castigar por falta de informacion
        "Reportado en data crédito": "No reportado",
        "Estado de vivienda propia": (
            "Con vivienda propia" if declarados.get("tiene_vivienda") else "Sin vivienda"
        ),
        "Ha pedido subsidios": "No",
    }


def calcular_score_no_registrado(datos_declarados: dict | None = None) -> ResultadoScoring:
    """Score para leads cuyo telefono no esta en la base.

    Si la conversacion no aporto nada, se aplica la penalizacion fija
    SCORE_NO_REGISTRADO y el lead queda FRIO: no hay con que calificarlo.

    Si aporto datos, se corre el mismo motor de reglas sobre un perfil armado
    con lo declarado y se multiplica por FACTOR_CONFIANZA_DECLARADO, porque
    nada de eso esta verificado. Antes todos recibian el mismo 15 sin importar
    lo que contaran, asi que un no afiliado con ingresos altos y cuota inicial
    ahorrada quedaba igual que un desempleado: la mitad de los leads de la
    base son no afiliados, y ese caso es justamente el que el reto pide no
    perder de vista.
    """
    datos_declarados = datos_declarados or {}
    if not datos_declarados:
        return ResultadoScoring(
            score=SCORE_NO_REGISTRADO,
            segmento_lead="FRIO",
            project_segment="Sin dato (no registrado)",
            razones=[
                "Numero no encontrado en el sistema: no hay forma de verificar ingreso, "
                "estabilidad laboral ni antecedentes en centrales de riesgo.",
                "La conversacion tampoco aporto datos de calificacion.",
                f"Se asigna una penalizacion fija de {SCORE_NO_REGISTRADO:.0f}/100 (FRIO) hasta "
                "que se registre o un asesor verifique sus datos manualmente.",
            ],
        )

    resultado = calcular_score(
        _perfil_desde_declarados(datos_declarados), datos_declarados=datos_declarados
    )

    score = round(resultado.score * FACTOR_CONFIANZA_DECLARADO, 1)
    if score >= config.UMBRAL_CALIENTE:
        segmento_lead = "CALIENTE"
    elif score >= config.UMBRAL_TIBIO:
        segmento_lead = "TIBIO"
    else:
        segmento_lead = "FRIO"

    razones = [
        "Numero no encontrado en el sistema: el perfil se arma con lo que la persona "
        "conto en la conversacion, sin verificar contra la base.",
    ]
    situacion = datos_declarados.get("situacion_laboral")
    if not datos_declarados.get("ingresos_mensuales_aprox") and situacion:
        supuesto = config.INGRESO_SUPUESTO_POR_SITUACION.get(situacion)
        if supuesto:
            razones.append(
                f"No declaro ingreso: se asume la mediana de quienes estan en su misma "
                f"situacion laboral (${supuesto:,.0f} COP). Confirmar en la llamada."
            )
    razones += [
        *resultado.razones,
        f"Ajuste por datos sin verificar: x{FACTOR_CONFIANZA_DECLARADO} "
        f"({resultado.score} -> {score})",
    ]

    return ResultadoScoring(
        score=score,
        segmento_lead=segmento_lead,
        project_segment=resultado.project_segment,
        razones=razones,
        peer_stats=resultado.peer_stats,
        subsidios_elegibles=resultado.subsidios_elegibles,
        contribuciones=resultado.contribuciones,
    )
