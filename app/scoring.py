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


def calcular_score(usuario: dict, family_structure: str | None = None) -> ResultadoScoring:
    razones: list[str] = []

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
    # techo de normalizacion propio de cada segmento: en VIS el ingreso rara
    # vez supera el umbral de 4 SMLV, asi que se normaliza contra ese techo
    # y no contra un techo generico que aplastaria el puntaje.
    techo_smlv = SEGMENTO_INCOME_THRESHOLD_SMLV if project_segment == "VIS" else 6.0

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
        senales["peers"] = conversion_peers
        razones.append(
            f"{peer_stats['total_peers']} usuarios con perfil similar (mismo rango salarial, "
            f"estado laboral y afiliacion): {conversion_peers}% concreto compra historicamente"
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

    score = max(0.0, min(100.0, score))

    if score >= 70:
        segmento_lead = "CALIENTE"
    elif score >= 40:
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


def calcular_score_no_registrado() -> ResultadoScoring:
    """Score para leads que no tienen registro en el sistema (numero de
    telefono no encontrado en la base). No reutiliza calcular_score porque
    esa formula depende de datos duros -- rango salarial, estado laboral,
    afiliacion, datacredito -- que un no registrado no tiene; en vez de eso
    aplica la penalizacion fija SCORE_NO_REGISTRADO, siempre FRIO."""
    return ResultadoScoring(
        score=SCORE_NO_REGISTRADO,
        segmento_lead="FRIO",
        project_segment="Sin dato (no registrado)",
        razones=[
            "Numero no encontrado en el sistema: no hay forma de verificar ingreso, "
            "estabilidad laboral ni antecedentes en centrales de riesgo.",
            f"Se asigna una penalizacion fija de {SCORE_NO_REGISTRADO:.0f}/100 (FRIO) hasta "
            "que se registre o un asesor verifique sus datos manualmente.",
        ],
    )
