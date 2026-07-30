# Análisis y roadmap — Motor de verificación del scoring

> Documento de análisis, no de especificación. No describe qué hace el
> producto hoy (eso lo hace `MIEMPRESA.md`); describe qué le falta al motor de
> scoring para ser más preciso, más auditable y más robusto, y qué se
> necesitaría para lograrlo.

**Estado de implementación:** de los 15 ítems del roadmap (sección 6), los
**9 que no dependían de datos reales ya están implementados y en producción**
(ver el detalle marcado **[Implementado]** en cada sección, y la columna
Estado de la tabla). Los **6 restantes siguen pendientes**: todos, por
diseño, requieren volumen de outcomes reales de leads (backtesting, pesos por
regresión logística, shadow scoring, cadencia formal de recalibración) o son
trabajo de auditoría/monitoreo continuo que no se abordó en esta ronda
(auditoría de impacto dispar, monitoreo de distribución en producción).

## 1. Resumen ejecutivo

El motor de scoring (`app/scoring.py` y módulos asociados) es **lógica de
reglas 100% determinística**, calibrada a mano sobre una base sintética de
3.449 usuarios. No hay modelo de ML entrenado — el pseudocódigo original del
reto (`RECURSOS/Algoritmo_de_Scoring_y_Enrutamiento.py`) llamaba a un
`modelo_xgboost` que nunca existió, y `scoring.py` lo reemplazó
explícitamente por reglas explícitas y verificables. El LLM solo interviene
para extraer variables declaradas de la conversación (`app/extraccion.py`) y
para redactar mensajes; nunca decide el score.

Esa decisión de diseño (reglas explícitas en vez de un modelo opaco) es
correcta para un producto que necesita explicar por qué a alguien no se le
recomienda una vivienda. El problema no era "reglas vs. ML": era que las
reglas estaban **calibradas una sola vez a mano, sin validación estadística
continua, sin trazabilidad de versión, y alimentadas por una extracción LLM
que no reportaba su propia incertidumbre**. De las cuatro limitaciones
estructurales identificadas, tres ya se resolvieron:

1. **Calibración sin backtesting.** *(Pendiente — requiere outcomes reales,
   ver sección 2.1.)* Los umbrales y pesos siguen calibrados sobre la misma
   base sintética que los genera, no contra un holdout ni contra outcomes
   reales. Ya hubo un incidente de este tipo: meses sin ningún lead CALIENTE,
   sin que los tests unitarios lo detectaran — de ahí nació
   `tests/test_distribucion_scoring.py`, que sí sigue corriendo como red de
   seguridad en cada cambio (dos recalibraciones de umbrales durante esta
   ronda de trabajo, tras conectar `ahorros` y tras el shrinkage de peers, se
   detectaron y aplicaron gracias a ese test).
2. **Sin versionado del score.** *(Resuelto.)* `config.SCORING_VERSION`
   (hoy `"1.1"`) viaja en cada `ResultadoScoring` y se persiste en
   `leads.scoring_version`.
3. **Extracción LLM sin calibrar su propia confianza.** *(Resuelto.)*
   `app/scoring._confianza_declarado()` reemplazó el descuento plano por un
   factor que depende de qué tan directamente se afirmó cada dato, y
   `app/llm_client.metricas_extraccion()` mide la tasa de fallos de
   extracción en vez de dejarla en silencio.
4. **Señales estadísticas sin control de muestra pequeña.** *(Resuelto.)*
   Peers y similitud vectorial ahora usan shrinkage tipo Empirical Bayes
   (`PSEUDO_CONTEO_PEERS` / `PSEUDO_CONTEO_CENTROIDE`, ambos en 10) en vez de
   un corte binario o un ancla fija.

Las siguientes secciones desarrollan cada frente priorizado (rigor
estadístico, explicabilidad, robustez conversacional), qué datos hacen falta,
y el roadmap con lo ya implementado marcado explícitamente.

## 2. Rigor estadístico y calibración

### 2.1 Backtesting formal — Pendiente (requiere outcomes reales)

`scripts/calibrar_scoring.py` calcula el score de **toda** la base y elige
los umbrales para que CALIENTE caiga en el percentil objetivo de esa misma
base. Sigue siendo calibración, no validación: no hay ningún conjunto de
datos que el motor no haya visto usado para comprobar que la calibración
generaliza. Nada de esto cambia hasta que haya outcomes reales de leads.

En cuanto los haya (tabla `leads`, ver sección 5):

- Separar un **holdout** que nunca se use para fijar pesos ni umbrales.
- Medir el motor contra ese holdout con métricas estándar de scoring:
  - **AUC-ROC / Gini** — ¿el score ordena correctamente a quienes terminan
    "Con vivienda propia" por encima de quienes no?
  - **Curva de calibración** — por decil de score, ¿la tasa real de
    conversión sube monótonamente y de forma proporcional?
  - **KS statistic** — separación entre la distribución de score de
    convertidos vs. no convertidos.
  - **PSI (Population Stability Index)** — para detectar cuándo la población
    de leads entrantes se desvía de la población sobre la que se calibró,
    señal de que toca recalibrar.

### 2.2 De pesos fijados a mano a pesos ajustados por datos — Pendiente (requiere outcomes reales)

Los multiplicadores actuales (`EMPLOYER_TIER_MULTIPLIER`, el 0,2/0,8 de la
regla 90/10, los pesos 0,6/0,2/0,2 del blend, los bonos +5/+8/+20/-30) siguen
siendo valores de negocio razonados, no ajustados contra resultados reales.
Con volumen suficiente de outcomes, la recomendación sigue siendo
**regresión logística regularizada** sobre las mismas variables que hoy
alimentan las reglas — no un modelo caja negra: mantiene un coeficiente
interpretable por variable (equivalente a "peso de la regla"), pero ese peso
queda respaldado por datos en vez de por intuición.

### 2.3 Shrinkage formal en peers y similitud vectorial — Implementado

`_peer_conversion_stats` y `vector_similarity.calcular_similitud_vectorial`
ahora calculan una `confianza` (0-1) con la fórmula clásica de shrinkage
`n / (n + k)`, `k = PSEUDO_CONTEO_PEERS = PSEUDO_CONTEO_CENTROIDE = 10`
(mismo valor en ambos módulos, verificado por
`test_peers_y_vectorial_usan_el_mismo_pseudo_conteo`). El peso efectivo de
cada señal en el blend es `peso_nominal × confianza`: crece gradualmente con
el tamaño de muestra en vez de activarse/desactivarse en un umbral fijo
(`MIN_PEERS_PARA_BLEND = 3` ya no existe). La tasa de conversión del grupo de
peers también se encoge hacia el promedio general de la base
(`_tasa_peers_con_shrinkage`) en vez de usarse cruda. Recalibró la
distribución real lo suficiente como para mover `UMBRAL_CALIENTE`/
`UMBRAL_TIBIO` (52,6/31,1 → 52,0/30,3) y subir `SCORING_VERSION` a `1.1`.

### 2.4 Shadow scoring antes de cambiar producción — Pendiente (requiere outcomes reales)

Para no repetir el incidente de "meses sin CALIENTE": antes de reemplazar
pesos o umbrales en producción, correrlos en paralelo (shadow) contra tráfico
real y comparar la distribución resultante contra la vigente, con alerta si
se desvía más de un margen razonable. No implementado — sigue dependiendo de
tener tráfico real de producción contra el cual comparar. En esta ronda, las
dos recalibraciones de umbrales se validaron corriendo
`scripts/calibrar_scoring.py` contra la base completa antes de aplicar el
cambio, que es una versión manual y más débil de esta misma idea.

### 2.5 Cadencia de recalibración — Pendiente (requiere outcomes reales)

La recalibración sigue siendo manual y esporádica (correr el script cuando
alguien lo recuerda o cuando un cambio de código lo amerita, como pasó dos
veces en esta ronda). Formalizar una cadencia (p. ej. mensual, o disparada
por PSI fuera de rango) solo tiene sentido con outcomes reales entrando.

## 3. Explicabilidad y auditoría

### 3.1 Reason codes estructurados — Implementado

`ResultadoScoring.codigos_razones` acompaña a `razones` (mismo orden, misma
longitud, garantizado por el helper `_agregar(codigo, texto)` en vez de
`razones.append(texto)` suelto). Hay 24 códigos `RC_*` cubriendo cada regla
que puede afectar el score, incluidos los cuatro nuevos `RC_CONFLICTO_*` de
la sección 4.3. Se persiste en `leads.codigos_razones` (jsonb). Habilitó
exactamente lo que se buscaba: tests que verifican "este perfil debe
disparar exactamente estos códigos" (`tests/test_reason_codes.py`,
`tests/test_conflictos.py`) en vez de comparar substrings de texto libre. La
analítica agregada por canal/ciudad sigue sin construirse (no se pidió en
esta ronda).

### 3.2 Versionado del score — Implementado

`config.SCORING_VERSION` (número incrementado a mano, igual criterio que
mantener `MIEMPRESA.md` al día) viaja en `ResultadoScoring.scoring_version` y
se persiste en `leads.scoring_version`. Ya se usó de verdad: subió de `"1.0"`
a `"1.1"` con el shrinkage de la sección 2.3.

### 3.3 Auditoría de impacto dispar — Pendiente

`estructura_familiar` y, más indirectamente, `ciudad` (vía peers) siguen
sin una revisión periódica de impacto dispar sobre subgrupos. No se abordó
en esta ronda.

### 3.4 Monitoreo de salud del modelo — Pendiente

Sigue sin existir una alerta en producción si la distribución
CALIENTE/TIBIO/FRIO se aleja del baseline (hoy 12,0%/38,0%/50,0%, actualizado
dos veces en esta ronda). Lo que sí existe es la verificación manual vía
`scripts/calibrar_scoring.py` antes de cada cambio de pesos/umbrales, y el
gate de CI (`tests/test_distribucion_scoring.py`) — ninguno de los dos es
monitoreo continuo en producción.

### 3.5 Consistencia entre documentación y código — Implementado

`tests/test_documentacion_consistente.py` compara 12 afirmaciones numéricas
textuales de `MIEMPRESA.md` (pesos del blend, multiplicadores de la regla
90/10, umbrales, cupo regulatorio, pseudo-conteo de shrinkage) contra las
constantes con nombre que las producen, y falla en CI si se desincronizan.
Ya demostró su utilidad: detectó en desarrollo que `MIEMPRESA.md` habría
quedado desactualizado tras cada una de las dos recalibraciones de umbrales
de esta ronda. `SOBRE MI/SYSTEMPROMPT.md` (la spec obsoleta que motivó este
ítem) sigue sin tocarse — decidir si se elimina o actualiza queda fuera de
alcance de este documento.

## 4. Robustez del agente conversacional (extracción de datos declarados)

### 4.1 Cobertura de features — Pendiente

Sigue sin hacerse el cruce explícito entre los 6 campos que extrae
`app/extraccion.py` y los features no usados de
`RECURSOS/buyer_persona_scoring_schema.json`. No se abordó en esta ronda.

### 4.2 Confianza por campo, no por perfil — Implementado

`FACTOR_CONFIANZA_DECLARADO` (descuento plano de 0,75 para todo el perfil)
se reemplazó por `app/scoring._confianza_declarado()`: una base según qué
tan directamente se afirmó lo que más pesa en el score (ingreso + situación
laboral: `0,85` explícito / `0,70` inferido / `0,55` sin situación), más un
bono pequeño por cada campo secundario declarado (ahorro, estructura
familiar, vivienda), con techo en `0,9` — ningún perfil declarado llega a
valer lo mismo que uno verificado. La confianza se deriva en código de la
procedencia del dato (afirmado vs. inferido vs. ausente), no le pide al LLM
que se autoevalúe.

### 4.3 Detección de conflictos entre lo declarado y lo registrado — Implementado

`app/scoring._detectar_conflictos()` compara, cuando el usuario está
registrado, situación laboral, ingreso (con 15% de tolerancia sobre el
rango salarial de la base), ahorro declarado vs. `ahorros` verificado (con
una zona neutra entre $500k y $3M COP para no generar ruido) y vivienda
(solo contra los valores sin ambigüedad de la base). Es puramente
informativo — se agrega a `razones`/`codigos_razones` y a
`ResultadoScoring.conflictos`, persistido en `leads.conflictos`, pero nunca
cambia el score, verificado explícitamente con un test.

### 4.4 Fallos silenciosos de extracción — Implementado

`app/llm_client.metricas_extraccion()` cuenta intentos y fallos reales de
`extraer_json` (proveedor caído, JSON sin balancear, JSON no parseable, JSON
que no es un objeto — distinguido de "el usuario no contó nada útil", que no
cuenta como fallo), con `logging.warning` en cada fallo y la tasa expuesta en
`/api/asesor/resumen-dia`. Los contadores viven en memoria de proceso (se
reinician con cada deploy), suficiente para ver un fallo sistemático durante
el día.

### 4.5 Golden set de evaluación — Implementado

`tests/test_golden_extraccion.py`: 15 casos representativos, opcional (no
corre en la suite normal — cuesta dinero y no es determinista, se activa con
`RUN_GOLDEN_EXTRACCION=1`). Se corrió de verdad contra el Gemini configurado
en el proyecto y encontró dos alucinaciones reales del prompt (mencionar
"cesantías" disparaba `situacion_laboral="empleado_formal"` sin que se dijera
nada sobre trabajo; mencionar "mi esposo" en una respuesta evasiva sobre
ahorro disparaba `estructura_familiar="Nuclear Integrada"`). Ambas se
corrigieron en `INSTRUCCION` (`app/extraccion.py`) y se reverificaron contra
el LLM real.

## 5. Datos necesarios / ground truth

Con datos reales de outcomes en camino, lo que la tabla `leads` sigue
necesitando capturar para que sirvan como ground truth utilizable (nada de
esta lista se implementó en esta ronda — todo depende de decisiones de
negocio sobre cómo y cuándo llegan esos outcomes):

- **Resultado final con timestamp** — no solo el score al momento de cerrar
  la conversación, sino qué pasó después (compró, desistió, fue rechazado,
  sigue sin vivienda), y cuándo se supo.
- **Canal/origen del lead** — ya se guarda (para la vista de calidad por
  canal en `/asesor`); falta confirmar que el pipeline de outcomes reales lo
  preserva.
- **Correcciones del asesor** — cuando un humano anula o ajusta la
  recomendación del motor, esa corrección es una señal de ground truth
  adicional, más rápida de acumular que esperar el desenlace final de cada
  lead.
- **Separación temporal calibración/validación** — a medida que crece el
  volumen real, evitar calibrar y validar sobre la misma ventana de tiempo.

### Quick win de bajo esfuerzo, sin depender de datos reales — Implementado

La columna `ahorros` (liquidez verificada) ya está conectada end-to-end:
`scripts/migrar_a_supabase.py` la incluye en `COLUMNAS_USUARIOS`,
`data_store.SQL_USUARIOS` la selecciona, y `scoring.calcular_score` la usa
como señal dura (bono escalado por monto, hasta `BONO_AHORRO_VERIFICADO_MAX
= 10` pts, tope en `config.AHORRO_VERIFICADO_TECHO_COP`), con prioridad
sobre el booleano declarado en la conversación cuando ambos existen. La
migración se corrió contra la base real de Supabase.

## 6. Roadmap priorizado

| Ítem | Sección | Estado | Esfuerzo | ¿Requiere outcomes reales? |
|---|---|---|---|---|
| Conectar `ahorros` verificado end-to-end | 5 | ✅ Implementado | Bajo | No |
| Versionado de score en `leads` | 3.2 | ✅ Implementado | Bajo | No |
| Reason codes estructurados | 3.1 | ✅ Implementado | Medio | No |
| Métrica de tasa de fallos de extracción LLM | 4.4 | ✅ Implementado | Bajo | No |
| Golden set de evaluación de extracción | 4.5 | ✅ Implementado | Medio | No |
| Confianza por campo en extracción declarada | 4.2 | ✅ Implementado | Medio | No |
| Detección de conflictos declarado vs. registrado | 4.3 | ✅ Implementado | Medio | No |
| Test de consistencia `MIEMPRESA.md` ↔ `config.py` | 3.5 | ✅ Implementado | Bajo | No |
| Shrinkage formal en peers / similitud vectorial | 2.3 | ✅ Implementado | Medio | No (mejora con la base sintética actual, se afina más con datos reales) |
| Monitoreo continuo de distribución CALIENTE/TIBIO/FRIO | 3.4 | ⏳ Pendiente | Medio | No para el mecanismo; sí para saber qué es "normal" en producción |
| Backtesting formal con holdout | 2.1 | ⏳ Pendiente | Alto | **Sí** |
| Pesos ajustados por regresión logística | 2.2 | ⏳ Pendiente | Alto | **Sí** |
| Shadow scoring antes de cambios en producción | 2.4 | ⏳ Pendiente | Alto | **Sí** (para comparar contra tráfico real) |
| Auditoría de impacto dispar | 3.3 | ⏳ Pendiente | Medio | Se puede empezar con la base sintética, pero solo es concluyente con datos reales |
| Cadencia formal de recalibración | 2.5 | ⏳ Pendiente | Bajo (proceso) | **Sí** (para que tenga sentido recalibrar) |

Los 9 ítems marcados "No" en la columna de outcomes reales ya están
implementados. Los 6 restantes siguen pendientes porque, tal como se
identificó al escribir este documento, dependen de datos que el sistema
todavía no tiene (outcomes reales de leads) o son trabajo de auditoría y
monitoreo continuo que no entraba en el alcance de esta ronda. Varios de los
ítems ya implementados (reason codes, versionado, golden set) eran además
prerrequisitos técnicos para que el backtesting y el shadow scoring sean
posibles cuando lleguen los datos reales — ese trabajo de base ya está
hecho.
