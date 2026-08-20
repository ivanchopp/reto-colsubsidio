"""
Catálogo centralizado de códigos de razón (reason codes) usados por el motor de scoring.
Cada entrada tiene la forma estándar:
    { "code": "RC_XXX", "message": "Texto en ES", "delta": -30, "metadata": {"rule_id":"id", "feature":"ingreso"} }

Este módulo vive en app/scoring/reason_codes.py y exporta:
  - REASON_CODES: dict de ReasonCode indexado por código
  - get_reason(code): devuelve el objeto ReasonCode
  - ALL_REASON_CODES: lista de códigos disponibles

El catálogo cubre los códigos definidos en app/scoring.py y añade metadatos
útiles para UI/analítica/tests.
"""
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class ReasonCode:
    code: str
    message: str
    delta: float  # impacto típico en puntos (positivo/negativo). Puede ser aproximado.
    metadata: Dict[str, Any] | None = None


REASON_CODES: Dict[str, ReasonCode] = {
    "RC_INGRESO_BASE": ReasonCode(
        code="RC_INGRESO_BASE",
        message=(
            "Aporte base calculado a partir del ingreso estimado (SMLV) "
            "y techo de normalización. Impacto proporcional al ingreso relativo."
        ),
        delta=0.0,
        metadata={"rule_id": "ingreso_base", "feature": "ingreso"},
    ),

    "RC_ESTABILIDAD_LABORAL": ReasonCode(
        code="RC_ESTABILIDAD_LABORAL",
        message=(
            "Ajuste por estabilidad laboral / tipo de contrato (empleado indefinido -> mejor estabilidad)."
        ),
        delta=10.0,
        metadata={"rule_id": "estabilidad_laboral", "feature": "estado_laboral"},
    ),

    "RC_DESEMPLEO": ReasonCode(
        code="RC_DESEMPLEO",
        message="Sin empleo activo: penalización fuerte por pérdida de capacidad de pago.",
        delta=-85.0,
        metadata={"rule_id": "desempleo", "feature": "estado_laboral"},
    ),

    "RC_NO_AFILIADO_VIS": ReasonCode(
        code="RC_NO_AFILIADO_VIS",
        message=(
            "No afiliado a Colsubsidio en segmento VIS: penalización severa "
            "según la regla 90/10 (reduce drásticamente la elegibilidad VIS)."
        ),
        delta=-80.0,
        metadata={"rule_id": "90_10_vis", "feature": "afiliacion"},
    ),

    "RC_MONOPARENTAL_AFILIADO": ReasonCode(
        code="RC_MONOPARENTAL_AFILIADO",
        message="Hogar monoparental joven afiliado: bono por beneficios VIS.",
        delta=20.0,
        metadata={"rule_id": "monoparental_joven", "feature": "estructura_familiar"},
    ),

    "RC_MONOPARENTAL_NO_AFILIADO": ReasonCode(
        code="RC_MONOPARENTAL_NO_AFILIADO",
        message="Hogar monoparental joven no afiliado: penalización por pérdida de beneficios VIS.",
        delta=-30.0,
        metadata={"rule_id": "monoparental_joven", "feature": "estructura_familiar"},
    ),

    "RC_CREDITO_INSUFICIENTE_NO_VIS": ReasonCode(
        code="RC_CREDITO_INSUFICIENTE_NO_VIS",
        message=(
            "Historial crediticio insuficiente para No VIS: según regla de negocio el score se anula "
            "para este segmento."
        ),
        delta=-100.0,
        metadata={"rule_id": "credito_threshold_no_vis", "feature": "credit_score"},
    ),

    "RC_AFILIADO_NO_VIS": ReasonCode(
        code="RC_AFILIADO_NO_VIS",
        message="Afiliado a Colsubsidio en No VIS: pequeño bono en el score.",
        delta=5.0,
        metadata={"rule_id": "afiliado_no_vis", "feature": "afiliacion"},
    ),

    "RC_NO_AFILIADO_NO_VIS": ReasonCode(
        code="RC_NO_AFILIADO_NO_VIS",
        message="No afiliado a Colsubsidio en No VIS: penalización por regla 90/10.",
        delta=-20.0,
        metadata={"rule_id": "90_10_no_vis", "feature": "afiliacion"},
    ),

    "RC_REPORTADO_DATACREDITO": ReasonCode(
        code="RC_REPORTADO_DATACREDITO",
        message=(
            "Reportado negativamente en centrales de riesgo: penalización muy fuerte "
            "(reduce drásticamente la probabilidad de aprobación)."
        ),
        delta=-90.0,
        metadata={"rule_id": "datacredito_reportado", "feature": "reportes_credito"},
    ),

    "RC_PEERS_SIMILARES": ReasonCode(
        code="RC_PEERS_SIMILARES",
        message=(
            "Señal derivada del comportamiento de peers con perfil similar: tasa de conversión ajustada "
            "por shrinkage. Impacto depende del tamaño y la tasa del grupo."
        ),
        delta=0.0,
        metadata={"rule_id": "peers_conversion", "feature": "peers"},
    ),

    "RC_SIMILITUD_VECTORIAL": ReasonCode(
        code="RC_SIMILITUD_VECTORIAL",
        message=(
            "Similitud vectorial contra centroides históricos: indica cercanía a compradores exitosos. "
            "Impacto proporcional a la similitud y al soporte del centroide."
        ),
        delta=0.0,
        metadata={"rule_id": "vector_similarity", "feature": "vectorial"},
    ),

    "RC_SUBSIDIOS_ELEGIBLES": ReasonCode(
        code="RC_SUBSIDIOS_ELEGIBLES",
        message="Aplica a subsidios de vivienda: bono en el score por mejorar la capacidad de compra.",
        delta=8.0,
        metadata={"rule_id": "subsidios", "feature": "subsidios"},
    ),

    "RC_AHORRO_VERIFICADO": ReasonCode(
        code="RC_AHORRO_VERIFICADO",
        message="Ahorro verificado en la base para la cuota inicial: bono directo (dato duro).",
        delta=10.0,
        metadata={"rule_id": "ahorro_verificado", "feature": "ahorros"},
    ),

    "RC_AHORRO_DECLARADO": ReasonCode(
        code="RC_AHORRO_DECLARADO",
        message="Declara tener ahorro o cesantías para la cuota inicial: bono por dato declarado.",
        delta=8.0,
        metadata={"rule_id": "ahorro_declarado", "feature": "ahorro_cuota_inicial"},
    ),

    "RC_NO_ENCONTRADO_EN_SISTEMA": ReasonCode(
        code="RC_NO_ENCONTRADO_EN_SISTEMA",
        message=(
            "Número no encontrado en el sistema: perfil construido desde la conversación (sin verificar)."
        ),
        delta=0.0,
        metadata={"rule_id": "no_registrado", "feature": "registro"},
    ),

    "RC_SIN_DATOS_DECLARADOS": ReasonCode(
        code="RC_SIN_DATOS_DECLARADOS",
        message="La conversación no aportó datos de calificación: ausencia de señales verificables.",
        delta=-5.0,
        metadata={"rule_id": "sin_datos", "feature": "conversacion"},
    ),

    "RC_PENALIZACION_FIJA_NO_REGISTRADO": ReasonCode(
        code="RC_PENALIZACION_FIJA_NO_REGISTRADO",
        message=(
            "Penalización fija asignada a leads no registrados: score bajo por defecto hasta "
            "que se verifiquen o registre el lead."
        ),
        delta=-15.0,
        metadata={"rule_id": "penalizacion_no_registrado", "feature": "registro"},
    ),

    "RC_SUPUESTO_INGRESO": ReasonCode(
        code="RC_SUPUESTO_INGRESO",
        message=(
            "No declaró ingreso: se asume la mediana del grupo según situación laboral. "
            "Es una suposición que debe confirmarse."
        ),
        delta=0.0,
        metadata={"rule_id": "supuesto_ingreso", "feature": "ingreso_inferido"},
    ),

    "RC_FACTOR_CONFIANZA_DECLARADO": ReasonCode(
        code="RC_FACTOR_CONFIANZA_DECLARADO",
        message=(
            "Ajuste por confianza en datos declarados (factor multiplicativo que reduce el score "
            "cuando los datos no están verificados)."
        ),
        delta=-15.0,
        metadata={"rule_id": "factor_confianza", "feature": "confianza_declarado"},
    ),

    "RC_CONFLICTO_SITUACION_LABORAL": ReasonCode(
        code="RC_CONFLICTO_SITUACION_LABORAL",
        message=(
            "Conflicto entre situación laboral declarada y registro en la base: revisar con el usuario."
        ),
        delta=0.0,
        metadata={"rule_id": "conflicto_situacion", "feature": "situacion_laboral"},
    ),

    "RC_CONFLICTO_INGRESO": ReasonCode(
        code="RC_CONFLICTO_INGRESO",
        message=(
            "Conflicto entre ingreso declarado y rango salarial en la base: revisar con el usuario."
        ),
        delta=0.0,
        metadata={"rule_id": "conflicto_ingreso", "feature": "ingresos_mensuales_aprox"},
    ),

    "RC_CONFLICTO_AHORRO": ReasonCode(
        code="RC_CONFLICTO_AHORRO",
        message=(
            "Conflicto entre ahorro declarado y ahorros verificados: revisar con el usuario."
        ),
        delta=0.0,
        metadata={"rule_id": "conflicto_ahorro", "feature": "ahorros"},
    ),

    "RC_CONFLICTO_VIVIENDA": ReasonCode(
        code="RC_CONFLICTO_VIVIENDA",
        message=(
            "Conflicto entre estado de vivienda declarado y registro en la base: revisar con el usuario."
        ),
        delta=0.0,
        metadata={"rule_id": "conflicto_vivienda", "feature": "tiene_vivienda"},
    ),
}


def get_reason(code: str) -> ReasonCode | None:
    """Devuelve el ReasonCode asociado o None si no existe."""
    return REASON_CODES.get(code)


ALL_REASON_CODES = list(REASON_CODES.keys())
