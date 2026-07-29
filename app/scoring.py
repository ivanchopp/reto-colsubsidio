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

# Vocabulario de app/extraccion.py (situacion_laboral) -> vocabulario de la
# base (Estado laboral). Un solo diccionario compartido entre
# _perfil_desde_declarados (arma el perfil sintetico de un no registrado) y
# _detectar_conflictos (compara lo declarado contra un usuario SI registrado)
# para que ambos usen la misma equivalencia.
MAPA_SITUACION_A_ESTADO_LABORAL = {
    "empleado_formal": "Empleado",
    "independiente": "Independiente",
    "desempleado": "Desempleado",
}

# Margen de tolerancia sobre el "Rango salarial" de la base antes de marcar
# conflicto con el ingreso declarado: el rango es un bucket, no un numero
# exacto, y un autoreporte cerca del borde no deberia dispararlo.
TOLERANCIA_INGRESO_DECLARADO_PCT = 0.15

# Umbrales para conflicto entre el ahorro declarado (booleano, de la
# conversacion) y el ahorro verificado (usuarios.ahorros, COP). La base
# sintetica no tiene ceros (ver RECURSOS/Base_de_datos_usuarios_Colombia.xlsx,
# minimo real ~3.479 COP), asi que un simple ">0" marcaria conflicto en casi
# cualquier "no tengo ahorro" declarado -- estos umbrales delimitan una zona
# neutra donde declarar cualquiera de las dos cosas es razonable.
UMBRAL_AHORRO_CONFLICTO_BAJO_COP = 500_000  # declara SI tener, la base muestra menos que esto
UMBRAL_AHORRO_CONFLICTO_ALTO_COP = 3_000_000  # declara NO tener, la base muestra mas que esto

# Peso de cada senal en el blend final (ver mas abajo en calcular_score) y
# minimo de peers para que esa senal aplique -- documentado tambien en
# SOBRE MI/MIEMPRESA.md seccion 6. Extraidas a constantes con nombre (en vez
# de literales inline) para que tests/test_documentacion_consistente.py
# pueda compararlas contra el texto del documento sin parsear codigo fuente.
PESO_REGLAS = 0.6
PESO_PEERS = 0.2
PESO_VECTORIAL = 0.2
MIN_PEERS_PARA_BLEND = 3  # con menos, el peso de "peers" vuelve a reglas

# Regla 90/10: penalizacion individual sobre el score de reglas (distinta de
# la cuota agregada leads_store.PCT_MAXIMO_NO_AFILIADOS). Documentado en
# SOBRE MI/MIEMPRESA.md seccion 6.
MULT_NO_AFILIADO_VIS = 0.2
MULT_NO_AFILIADO_NO_VIS = 0.8
BONO_AFILIADO_NO_VIS = 5.0

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
#
# El descuento no es plano: un perfil donde la persona afirmo un ingreso
# concreto no deberia valer lo mismo que uno donde solo se sabe la situacion
# laboral y el ingreso se asumio por la mediana del grupo
# (INGRESO_SUPUESTO_POR_SITUACION) -- eso es justo lo que el descuento fijo
# de antes no distinguia. Ver _confianza_declarado().
FACTOR_CONFIANZA_INGRESO_EXPLICITO = 0.85  # afirmo un numero: situacion + ingreso declarados
FACTOR_CONFIANZA_INGRESO_INFERIDO = 0.70   # afirmo su situacion, el ingreso se asumio por la mediana
FACTOR_CONFIANZA_SIN_SITUACION = 0.55      # ni siquiera se sabe a que se dedica

# Cada campo secundario que tambien se declaro (ahorro, estructura familiar,
# vivienda) suma un poco de certeza extra sobre la base de arriba. El techo
# evita que un perfil declarado, por completo que sea, llegue a valer lo
# mismo que uno verificado en la base.
BONO_CONFIANZA_POR_CAMPO_SECUNDARIO = 0.02
FACTOR_CONFIANZA_TECHO = 0.9
_CAMPOS_SECUNDARIOS_CONFIANZA = ("ahorro_cuota_inicial", "estructura_familiar", "tiene_vivienda")

# Reason codes: identificador estable por cada regla que puede afectar el
# score, en paralelo al texto en espanol de "razones" (ver ResultadoScoring).
# Existen para dos cosas que un texto libre no permite: testear "este perfil
# debe disparar exactamente estos codigos" sin comparar substrings fragiles,
# y agregar analitica (que razon rechaza mas leads, por canal o por ciudad)
# sin tener que parsear texto en el panel del asesor.
RC_INGRESO_BASE = "RC_INGRESO_BASE"
RC_ESTABILIDAD_LABORAL = "RC_ESTABILIDAD_LABORAL"
RC_DESEMPLEO = "RC_DESEMPLEO"
RC_NO_AFILIADO_VIS = "RC_NO_AFILIADO_VIS"
RC_MONOPARENTAL_AFILIADO = "RC_MONOPARENTAL_AFILIADO"
RC_MONOPARENTAL_NO_AFILIADO = "RC_MONOPARENTAL_NO_AFILIADO"
RC_CREDITO_INSUFICIENTE_NO_VIS = "RC_CREDITO_INSUFICIENTE_NO_VIS"
RC_AFILIADO_NO_VIS = "RC_AFILIADO_NO_VIS"
RC_NO_AFILIADO_NO_VIS = "RC_NO_AFILIADO_NO_VIS"
RC_REPORTADO_DATACREDITO = "RC_REPORTADO_DATACREDITO"
RC_PEERS_SIMILARES = "RC_PEERS_SIMILARES"
RC_SIMILITUD_VECTORIAL = "RC_SIMILITUD_VECTORIAL"
RC_SUBSIDIOS_ELEGIBLES = "RC_SUBSIDIOS_ELEGIBLES"
RC_AHORRO_VERIFICADO = "RC_AHORRO_VERIFICADO"
RC_AHORRO_DECLARADO = "RC_AHORRO_DECLARADO"
RC_NO_ENCONTRADO_EN_SISTEMA = "RC_NO_ENCONTRADO_EN_SISTEMA"
RC_SIN_DATOS_DECLARADOS = "RC_SIN_DATOS_DECLARADOS"
RC_PENALIZACION_FIJA_NO_REGISTRADO = "RC_PENALIZACION_FIJA_NO_REGISTRADO"
RC_SUPUESTO_INGRESO = "RC_SUPUESTO_INGRESO"
RC_FACTOR_CONFIANZA_DECLARADO = "RC_FACTOR_CONFIANZA_DECLARADO"
RC_CONFLICTO_SITUACION_LABORAL = "RC_CONFLICTO_SITUACION_LABORAL"
RC_CONFLICTO_INGRESO = "RC_CONFLICTO_INGRESO"
RC_CONFLICTO_AHORRO = "RC_CONFLICTO_AHORRO"
RC_CONFLICTO_VIVIENDA = "RC_CONFLICTO_VIVIENDA"


@dataclass
class ResultadoScoring:
    score: float  # 0-100
    segmento_lead: str  # CALIENTE / TIBIO / FRIO
    project_segment: str  # VIS / No VIS
    razones: list[str] = field(default_factory=list)
    # codigo estable por cada entrada de "razones", mismo orden y misma
    # longitud -- ver el bloque RC_* arriba.
    codigos_razones: list[str] = field(default_factory=list)
    peer_stats: dict | None = None
    subsidios_elegibles: list = field(default_factory=list)
    # desglose {etiqueta, valor, peso, categoria} de como el blend final
    # (reglas/peers/vectorial + bono de subsidios) llego al score -- lo usa
    # el panel del asesor para el grafico de torta. None cuando el score no
    # viene de ese blend (ver calcular_score_no_registrado).
    contribuciones: list[dict] | None = None
    # config.SCORING_VERSION vigente al momento del calculo -- se persiste en
    # leads.scoring_version para poder auditar con que reglas salio un score
    # historico despues de que config.py haya cambiado.
    scoring_version: str = config.SCORING_VERSION
    # discrepancias entre lo que la persona declaro en la conversacion y lo
    # que dice la base (ver _detectar_conflictos). Informativo: no cambia el
    # score, solo lo señala para que un asesor lo revise -- puede ser un dato
    # de base desactualizado o una extraccion del LLM incorrecta, y en ambos
    # casos conviene mirarlo en vez de resolverlo en silencio a favor de una
    # fuente. Siempre vacio para un lead sin registro (no hay con que
    # comparar lo declarado).
    conflictos: list[dict] = field(default_factory=list)


def _midpoint_rango_salarial(rango: str) -> float:
    rango = str(rango).lower().replace("de ", "").strip()
    partes = [p.strip().replace(".", "") for p in rango.split("-")]
    numeros = [float(p) for p in partes if p.replace(",", "").isdigit()]
    if len(numeros) != 2:
        return 0.0
    return sum(numeros) / 2


def _bounds_rango_salarial(rango: str) -> tuple[float, float] | None:
    """Limites (min, max) de un 'Rango salarial' de la base, para comparar un
    ingreso puntual declarado contra el bucket completo en vez de solo contra
    el punto medio (ver _detectar_conflictos)."""
    rango = str(rango).lower().replace("de ", "").strip()
    partes = [p.strip().replace(".", "") for p in rango.split("-")]
    numeros = [float(p) for p in partes if p.replace(",", "").isdigit()]
    if len(numeros) != 2:
        return None
    return min(numeros), max(numeros)


def _employer_tier(usuario: dict) -> str:
    estado = str(usuario.get("Estado laboral", "")).strip()
    contrato = str(usuario.get("Tipo de contrato", "")).strip()
    if estado == "Empleado" and contrato == "Indefinido":
        return "Tier 1"
    if estado == "Empleado" and contrato == "Fijo":
        return "Tier 2"
    return "Tier 3"  # Independiente, Obra y labor, Desempleado


def _detectar_conflictos(usuario: dict, datos_declarados: dict) -> list[dict]:
    """Compara lo declarado en la conversacion contra los datos verificados
    de la base, cuando el usuario esta registrado. No decide cual fuente
    tiene razon -- puede ser un dato de base desactualizado o una extraccion
    del LLM incorrecta -- solo lo señala para que un asesor lo revise. No
    cambia el score.

    Para un lead sin registro esto siempre da [] sin necesidad de un caso
    especial: el perfil que se compara (_perfil_desde_declarados) se arma con
    lo mismo que datos_declarados, asi que nunca hay con que contradecirlo.
    """
    conflictos: list[dict] = []

    situacion = datos_declarados.get("situacion_laboral")
    estado_esperado = MAPA_SITUACION_A_ESTADO_LABORAL.get(situacion)
    estado_base = str(usuario.get("Estado laboral", "")).strip()
    if estado_esperado and estado_base and estado_esperado != estado_base:
        conflictos.append(
            {
                "campo": "situacion_laboral",
                "codigo": RC_CONFLICTO_SITUACION_LABORAL,
                "valor_base": estado_base,
                "valor_declarado": situacion,
                "mensaje": (
                    f"Conflicto de situacion laboral: la base dice '{estado_base}', "
                    f"declaro '{situacion}' en la conversacion. Verificar con el usuario."
                ),
            }
        )

    ingreso_declarado = datos_declarados.get("ingresos_mensuales_aprox")
    limites = _bounds_rango_salarial(usuario.get("Rango salarial", ""))
    if ingreso_declarado and limites:
        minimo, maximo = limites
        margen = maximo * TOLERANCIA_INGRESO_DECLARADO_PCT
        if not (minimo - margen <= ingreso_declarado <= maximo + margen):
            conflictos.append(
                {
                    "campo": "ingresos_mensuales_aprox",
                    "codigo": RC_CONFLICTO_INGRESO,
                    "valor_base": usuario.get("Rango salarial"),
                    "valor_declarado": ingreso_declarado,
                    "mensaje": (
                        f"Conflicto de ingreso: la base ubica al usuario en el rango "
                        f"'{usuario.get('Rango salarial')}', declaro ${ingreso_declarado:,.0f} COP "
                        "en la conversacion. Verificar con el usuario."
                    ),
                }
            )

    if "ahorro_cuota_inicial" in datos_declarados:
        ahorro_declarado = datos_declarados["ahorro_cuota_inicial"]
        ahorros_base = usuario.get("ahorros")
        if isinstance(ahorros_base, (int, float)) and ahorros_base == ahorros_base:  # descarta NaN
            conflicto_por_bajo = ahorro_declarado and ahorros_base < UMBRAL_AHORRO_CONFLICTO_BAJO_COP
            conflicto_por_alto = (
                ahorro_declarado is False and ahorros_base > UMBRAL_AHORRO_CONFLICTO_ALTO_COP
            )
            if conflicto_por_bajo or conflicto_por_alto:
                conflictos.append(
                    {
                        "campo": "ahorro_cuota_inicial",
                        "codigo": RC_CONFLICTO_AHORRO,
                        "valor_base": ahorros_base,
                        "valor_declarado": ahorro_declarado,
                        "mensaje": (
                            f"Conflicto de ahorro: declaro "
                            f"{'tener' if ahorro_declarado else 'NO tener'} ahorro para la cuota "
                            f"inicial, la base muestra ${ahorros_base:,.0f} COP verificados. "
                            "Verificar con el usuario."
                        ),
                    }
                )

    if "tiene_vivienda" in datos_declarados:
        tiene_vivienda_declarado = datos_declarados["tiene_vivienda"]
        estado_vivienda_base = str(usuario.get("Estado de vivienda propia", "")).strip()
        # solo se compara contra los dos valores sin ambiguedad de la base:
        # "Desistido"/"Rechazado" describen el desenlace de un proceso pasado,
        # no si hoy tiene vivienda, y comparar contra eso daria falsos positivos
        contradice_con_vivienda = estado_vivienda_base == "Con vivienda propia" and not tiene_vivienda_declarado
        contradice_sin_vivienda = estado_vivienda_base == "Sin vivienda" and tiene_vivienda_declarado
        if contradice_con_vivienda or contradice_sin_vivienda:
            conflictos.append(
                {
                    "campo": "tiene_vivienda",
                    "codigo": RC_CONFLICTO_VIVIENDA,
                    "valor_base": estado_vivienda_base,
                    "valor_declarado": tiene_vivienda_declarado,
                    "mensaje": (
                        f"Conflicto de vivienda: la base dice '{estado_vivienda_base}', declaro "
                        f"{'tener' if tiene_vivienda_declarado else 'no tener'} vivienda propia "
                        "en la conversacion. Verificar con el usuario."
                    ),
                }
            )

    return conflictos


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
    codigos_razones: list[str] = []

    def _agregar(codigo: str, texto: str) -> None:
        codigos_razones.append(codigo)
        razones.append(texto)

    datos_declarados = datos_declarados or {}

    # discrepancias entre lo declarado y la base: solo informativo, no toca
    # el score. Ver _detectar_conflictos.
    conflictos = _detectar_conflictos(usuario, datos_declarados)
    for conflicto in conflictos:
        _agregar(conflicto["codigo"], conflicto["mensaje"])

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
    _agregar(
        RC_INGRESO_BASE,
        f"Ingreso estimado {ingreso_smlv:.1f} SMLV -> segmento {project_segment}, "
        f"aporte base {score:.1f} pts",
    )

    score *= EMPLOYER_TIER_MULTIPLIER[tier]
    _agregar(
        RC_ESTABILIDAD_LABORAL,
        f"Estabilidad laboral {tier} ({usuario.get('Estado laboral')} / {usuario.get('Tipo de contrato')})",
    )

    if desempleado:
        score *= 0.15
        _agregar(RC_DESEMPLEO, "Sin empleo activo: penalizacion fuerte a la capacidad de pago")

    if project_segment == "VIS":
        if not afiliado:
            score *= MULT_NO_AFILIADO_VIS
            _agregar(
                RC_NO_AFILIADO_VIS,
                "No afiliado a Colsubsidio en segmento VIS: penalizacion severa (regla 90/10)",
            )
        if family_structure == "Monoparental Joven":
            if afiliado:
                score += 20
                _agregar(
                    RC_MONOPARENTAL_AFILIADO,
                    "Hogar monoparental joven afiliado: +20 pts (aplica beneficios VIS)",
                )
            else:
                score -= 30
                _agregar(RC_MONOPARENTAL_NO_AFILIADO, "Hogar monoparental joven no afiliado: -30 pts")
    else:  # No VIS
        if credit_score < CREDIT_SCORE_THRESHOLD:
            score = 0
            _agregar(
                RC_CREDITO_INSUFICIENTE_NO_VIS,
                "Historial crediticio insuficiente para No VIS: score anulado",
            )
        elif afiliado:
            score += BONO_AFILIADO_NO_VIS
            _agregar(RC_AFILIADO_NO_VIS, f"Afiliado a Colsubsidio: +{BONO_AFILIADO_NO_VIS:.0f} pts")
        if not afiliado:
            score *= MULT_NO_AFILIADO_NO_VIS
            _agregar(
                RC_NO_AFILIADO_NO_VIS,
                f"No afiliado a Colsubsidio: penalizacion regla 90/10 (x{MULT_NO_AFILIADO_NO_VIS})",
            )

    if reportado_datacredito:
        score *= 0.10
        _agregar(
            RC_REPORTADO_DATACREDITO,
            "Reportado negativamente en centrales de riesgo: penalizacion casi eliminatoria",
        )

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
    pesos = {"reglas": PESO_REGLAS}
    senales = {"reglas": score}

    peer_stats = _peer_conversion_stats(usuario)
    if peer_stats.get("total_peers", 0) >= MIN_PEERS_PARA_BLEND:
        conversion_peers = peer_stats["pct_con_vivienda_propia"]
        pesos["peers"] = PESO_PEERS
        senales["peers"] = _lift_de_peers(conversion_peers)
        _agregar(
            RC_PEERS_SIMILARES,
            f"{peer_stats['total_peers']} usuarios con perfil similar (mismo rango salarial, "
            f"estado laboral y afiliacion): {conversion_peers}% concreto compra historicamente "
            f"(promedio general de la base: {data_store.tasa_base_conversion():.1f}%)",
        )
    else:
        pesos["reglas"] += PESO_PEERS  # sin suficientes peers, ese peso vuelve a las reglas

    vector_stats = vector_similarity.calcular_similitud_vectorial(usuario)
    pesos["vectorial"] = PESO_VECTORIAL
    senales["vectorial"] = vector_stats["score_vectorial"]
    _agregar(
        RC_SIMILITUD_VECTORIAL,
        f"Similitud vectorial del perfil contra centroides historicos "
        f"(compro/desistio/rechazado/sin vivienda): {vector_stats['score_vectorial']}/100 "
        "de cercania al centroide de compradores exitosos",
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
        _agregar(
            RC_SUBSIDIOS_ELEGIBLES,
            f"Aplica a {len(subsidios_elegibles)} subsidio(s) de vivienda (+{bono:.0f} pts): {nombres}",
        )
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
        _agregar(
            RC_AHORRO_VERIFICADO,
            f"Ahorro verificado en la base (${ahorros_verificados:,.0f} COP) para la cuota "
            f"inicial (+{bono:.1f} pts): dato duro, no declarado",
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
        _agregar(
            RC_AHORRO_DECLARADO,
            f"Declara tener ahorro o cesantias para la cuota inicial "
            f"(+{BONO_AHORRO_CUOTA_INICIAL:.0f} pts): mejora su capacidad real de compra",
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
        codigos_razones=codigos_razones,
        peer_stats=peer_stats,
        subsidios_elegibles=subsidios_elegibles,
        contribuciones=contribuciones,
        conflictos=conflictos,
    )


def _perfil_desde_declarados(declarados: dict) -> dict:
    """Arma un usuario parcial con la forma que esperan las reglas, a partir de
    lo que la persona conto. Los campos que no se sabe que valen se dejan
    neutros, nunca en el peor valor posible: no declarar algo no es lo mismo
    que declararlo en contra."""
    situacion = declarados.get("situacion_laboral")
    # neutro si no declaro: Tier 3 sin la penalizacion de desempleo
    estado_laboral = MAPA_SITUACION_A_ESTADO_LABORAL.get(situacion, "Independiente")

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


def _confianza_declarado(datos_declarados: dict) -> float:
    """Cuanto confiar en un perfil armado con datos de la conversacion, nunca
    verificados contra la base. Depende de que tan directamente afirmo la
    persona lo que mas pesa en el score final -- ingreso y situacion laboral,
    ver calcular_score -- con un pequeno ajuste por cuantos campos
    secundarios tambien conto (ahorro, estructura familiar, vivienda)."""
    situacion = datos_declarados.get("situacion_laboral")
    if not situacion:
        base = FACTOR_CONFIANZA_SIN_SITUACION
    elif "ingresos_mensuales_aprox" in datos_declarados:
        base = FACTOR_CONFIANZA_INGRESO_EXPLICITO
    else:
        base = FACTOR_CONFIANZA_INGRESO_INFERIDO

    secundarios_declarados = sum(
        campo in datos_declarados for campo in _CAMPOS_SECUNDARIOS_CONFIANZA
    )
    return min(
        base + secundarios_declarados * BONO_CONFIANZA_POR_CAMPO_SECUNDARIO,
        FACTOR_CONFIANZA_TECHO,
    )


def calcular_score_no_registrado(datos_declarados: dict | None = None) -> ResultadoScoring:
    """Score para leads cuyo telefono no esta en la base.

    Si la conversacion no aporto nada, se aplica la penalizacion fija
    SCORE_NO_REGISTRADO y el lead queda FRIO: no hay con que calificarlo.

    Si aporto datos, se corre el mismo motor de reglas sobre un perfil armado
    con lo declarado y se multiplica por un factor de confianza (ver
    _confianza_declarado), porque nada de eso esta verificado. Antes todos
    recibian el mismo 15 sin importar lo que contaran, asi que un no afiliado
    con ingresos altos y cuota inicial ahorrada quedaba igual que un
    desempleado: la mitad de los leads de la base son no afiliados, y ese
    caso es justamente el que el reto pide no perder de vista.
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
            codigos_razones=[
                RC_NO_ENCONTRADO_EN_SISTEMA,
                RC_SIN_DATOS_DECLARADOS,
                RC_PENALIZACION_FIJA_NO_REGISTRADO,
            ],
        )

    resultado = calcular_score(
        _perfil_desde_declarados(datos_declarados), datos_declarados=datos_declarados
    )

    factor_confianza = _confianza_declarado(datos_declarados)
    score = round(resultado.score * factor_confianza, 1)
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
    codigos_razones = [RC_NO_ENCONTRADO_EN_SISTEMA]
    situacion = datos_declarados.get("situacion_laboral")
    if not datos_declarados.get("ingresos_mensuales_aprox") and situacion:
        supuesto = config.INGRESO_SUPUESTO_POR_SITUACION.get(situacion)
        if supuesto:
            razones.append(
                f"No declaro ingreso: se asume la mediana de quienes estan en su misma "
                f"situacion laboral (${supuesto:,.0f} COP). Confirmar en la llamada."
            )
            codigos_razones.append(RC_SUPUESTO_INGRESO)
    razones += [
        *resultado.razones,
        f"Ajuste por datos sin verificar (confianza segun cuanto se afirmo vs. se "
        f"asumio): x{factor_confianza:.2f} ({resultado.score} -> {score})",
    ]
    codigos_razones += [*resultado.codigos_razones, RC_FACTOR_CONFIANZA_DECLARADO]

    return ResultadoScoring(
        score=score,
        segmento_lead=segmento_lead,
        project_segment=resultado.project_segment,
        razones=razones,
        codigos_razones=codigos_razones,
        peer_stats=resultado.peer_stats,
        subsidios_elegibles=resultado.subsidios_elegibles,
        contribuciones=resultado.contribuciones,
        conflictos=resultado.conflictos,
    )
