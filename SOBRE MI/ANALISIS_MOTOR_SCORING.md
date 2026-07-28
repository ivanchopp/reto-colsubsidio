# Análisis y roadmap — Motor de verificación del scoring

> Documento de análisis, no de especificación. No describe qué hace el
> producto hoy (eso lo hace `MIEMPRESA.md`); describe qué le falta al motor de
> scoring para ser más preciso, más auditable y más robusto, y qué se
> necesitaría para lograrlo.

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
recomienda una vivienda. El problema no es "reglas vs. ML": es que hoy las
reglas están **calibradas una sola vez a mano, sin validación estadística
continua, sin trazabilidad de versión, y alimentadas por una extracción LLM
que no reporta su propia incertidumbre**. Cuatro limitaciones estructurales
concentran la mayoría del riesgo de precisión:

1. **Calibración sin backtesting.** Los umbrales y pesos (`app/config.py`) se
   fijaron para producir una distribución "razonable" sobre la misma base
   sintética que los genera, no contra un holdout ni contra outcomes reales.
   Ya hubo un incidente de este tipo: meses sin ningún lead CALIENTE, sin que
   los tests unitarios (que verifican reglas individuales, no la distribución
   agregada) lo detectaran — de ahí nació `tests/test_distribucion_scoring.py`.
2. **Sin versionado del score.** Si `config.py` cambia, no queda registro de
   qué configuración produjo un score histórico guardado en `leads`. No se
   puede reproducir ni auditar una decisión pasada.
3. **Extracción LLM sin calibrar su propia confianza.** `app/extraccion.py`
   aplica un único factor de descuento (`FACTOR_CONFIANZA_DECLARADO = 0.75`)
   a todo el perfil declarado, sin distinguir un dato que el usuario afirmó
   con seguridad de uno inferido con dudas. Un fallo de parseo devuelve `{}`
   en silencio, sin métrica que lo detecte.
4. **Señales estadísticas sin control de muestra pequeña.** Las señales de
   peers y similitud vectorial (`app/data_store.py`,
   `app/vector_similarity.py`) no tienen un mínimo de muestra explícito ni
   intervalo de confianza — solo un ancla parcial a 50 cuando el peer group es
   igual al promedio general.

Las siguientes secciones desarrollan cada frente priorizado (rigor
estadístico, explicabilidad, robustez conversacional), qué datos hacen falta,
y un roadmap con lo que ya es accionable hoy (sin datos reales) frente a lo
que solo tiene sentido cuando lleguen outcomes reales de leads.

## 2. Rigor estadístico y calibración

### 2.1 Backtesting formal

`scripts/calibrar_scoring.py` calcula el score de **toda** la base y elige
los umbrales para que CALIENTE caiga en el percentil objetivo de esa misma
base. Es calibración, no validación: no hay ningún conjunto de datos que el
motor no haya visto usado para comprobar que la calibración generaliza.

En cuanto haya outcomes reales de leads (tabla `leads`, ver sección 5):

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

### 2.2 De pesos fijados a mano a pesos ajustados por datos

Los multiplicadores actuales (`EMPLOYER_TIER_MULTIPLIER`, el 0,2/0,8 de la
regla 90/10, los pesos 0,6/0,2/0,2 del blend, los bonos +5/+8/+20/-30) son
todos valores de negocio razonados, no ajustados contra resultados reales.
Con volumen suficiente de outcomes, la recomendación es **regresión logística
regularizada** sobre las mismas variables que hoy alimentan las reglas — no
un modelo caja negra: mantiene un coeficiente interpretable por variable
(equivalente a "peso de la regla"), pero ese peso queda respaldado por datos
en vez de por intuición. Esto preserva la explicabilidad que el diseño actual
ya prioriza, solo cambia cómo se fija cada número.

### 2.3 Shrinkage formal en peers y similitud vectorial

`data_store.peers_con_perfil_similar` mide conversión de un grupo definido
por rango salarial + estado laboral + afiliación. Cuando ese grupo es
pequeño, el "lift" contra la tasa base es ruido, no señal — hoy se compensa
parcialmente (si hay menos de 3 peers, el peso de esa señal vuelve a reglas),
pero es un corte binario, no una degradación proporcional al tamaño de
muestra. Recomendado: shrinkage tipo Empirical Bayes, donde el peso efectivo
de la señal de peers crece con `n` en vez de activarse/desactivarse en un
umbral fijo. Igual aplica a los centroides de `vector_similarity.py`, que hoy
se recalculan en vivo sobre toda la base sin ponderar por cuántos usuarios
soportan cada centroide.

### 2.4 Shadow scoring antes de cambiar producción

Para no repetir el incidente de "meses sin CALIENTE": antes de reemplazar
pesos o umbrales en producción, correrlos en paralelo (shadow) contra tráfico
real y comparar la distribución resultante contra la vigente, con alerta si
se desvía más de un margen razonable. Esto convierte
`test_distribucion_scoring.py` de una red de seguridad reactiva (detecta el
bug en CI) a una preventiva (detecta el bug antes del deploy).

### 2.5 Cadencia de recalibración

Hoy la recalibración es manual y esporádica (correr el script cuando alguien
lo recuerda). Con outcomes reales entrando, formalizar una cadencia (p. ej.
mensual, o disparada por PSI fuera de rango) en vez de dejarla a criterio
humano.

## 3. Explicabilidad y auditoría

### 3.1 Reason codes estructurados

`ResultadoScoring.razones` hoy es texto libre generado por cada regla
aplicada. Funciona para mostrarlo en `/asesor`, pero no es queryable ni
testeable de forma sistemática. Proponer una capa de **reason codes**: cada
regla que afecta el score emite un código estable (p. ej. `RC_NO_AFILIADO_VIS`,
`RC_CREDITO_REPORTADO`, `RC_MONOPARENTAL_JOVEN`) además del texto en
español. Esto habilita:

- Tests que verifican "este perfil debe disparar exactamente estos códigos",
  más robustos que comparar strings.
- Analítica agregada: qué razón es la que más rechaza leads por canal o por
  ciudad, información que hoy solo se puede leer lead por lead en el panel.

### 3.2 Versionado del score

Persistir en `leads`, junto al score, un identificador de la configuración
que lo produjo (hash de los valores relevantes de `app/config.py`, o un
número de versión incrementado a mano cada vez que cambian pesos/umbrales).
Sin esto, cualquier auditoría retrospectiva de un lead antiguo asume
implícitamente que los pesos nunca cambiaron desde entonces.

### 3.3 Auditoría de impacto dispar

Dos variables del árbol de reglas son sensibles-adyacentes:
`estructura_familiar` ("Monoparental Joven" con +20/-30 según afiliación) y,
más indirectamente, `ciudad` a través de las señales de peers. Recomendado:
revisión periódica (aunque sea manual al principio) de si estas variables
producen un impacto dispar no intencionado sobre subgrupos, antes de que el
motor se conecte a decisiones con más peso regulatorio.

### 3.4 Monitoreo de salud del modelo

Alertar si la distribución CALIENTE/TIBIO/FRIO se aleja del baseline
documentado (11,9%/37,8%/50,3%) más allá de un margen esperado, en producción
y no solo en el test de CI. Es la misma idea de la sección 2.4 pero como
monitoreo continuo, no solo como gate de deploy.

### 3.5 Consistencia entre documentación y código

Ya existe evidencia de que la documentación se desalinea del código sin que
nadie lo note: `SOBRE MI/SYSTEMPROMPT.md` describe un flujo (pide cédula, el
LLM decide todo) que contradice el comportamiento real, gobernado por
`SOBRE MI/SOBREMI.md`. Lo mismo puede pasarle a `MIEMPRESA.md` con los
umbrales y pesos que cita textualmente (53,6 / 29,1 / 0,6 / 0,2 / 0,2, etc.).
Recomendado: un test que lea esos valores desde `app/config.py` y falle si
`MIEMPRESA.md` queda desactualizado, en vez de confiar en que alguien lo
actualice a mano.

## 4. Robustez del agente conversacional (extracción de datos declarados)

### 4.1 Cobertura de features

`app/extraccion.py` extrae 6 campos (`empresa`, `situacion_laboral`,
`ahorro_cuota_inicial`, `estructura_familiar`, `tiene_vivienda`,
`ingresos_mensuales_aprox`). `RECURSOS/buyer_persona_scoring_schema.json`
define más features de las que efectivamente se usan hoy. Vale la pena un
cruce explícito: de esos features no usados, ¿cuáles aportarían señal real al
scoring y son extraíbles de una conversación natural sin sonar a
interrogatorio (la restricción de diseño que ya impone `SOBREMI.md`)?

### 4.2 Confianza por campo, no por perfil

Hoy `FACTOR_CONFIANZA_DECLARADO = 0.75` descuenta **todo** el perfil
declarado por igual. Un usuario que dice "gano exactamente 3.200.000 al mes"
no es igual de confiable que uno del que se infirió el ingreso a partir de su
situación laboral (`INGRESO_SUPUESTO_POR_SITUACION`). Proponer que el propio
prompt de extracción devuelva un nivel de certeza por campo (alta/media/baja)
y que el factor de confianza se aplique por campo, no como descuento plano.

### 4.3 Detección de conflictos entre lo declarado y lo registrado

Cuando el teléfono sí existe en `usuarios`, hoy no hay comparación explícita
entre el dato de base y lo que la persona declara en el chat — uno puede
sobreescribir al otro silenciosamente según el flujo de
`app/conversation.py`. Un conflicto (p. ej. la base dice "Desempleado" y el
usuario dice trabajar en una empresa) es información valiosa: puede ser un
dato de base desactualizado o una extracción LLM incorrecta, y en ambos casos
merece señalizarse en vez de resolverse en silencio a favor de una fuente.

### 4.4 Fallos silenciosos de extracción

Un fallo de parseo del LLM en `extraccion.py` devuelve `{}` sin romper el
flujo — correcto para no bloquear la conversación, pero invisible: no hay
métrica que registre la tasa de fallos de extracción. Es el mismo patrón de
riesgo que causó el incidente de distribución (sección 2.4): un fallo
sistemático (p. ej. un cambio de proveedor LLM que rompe el formato JSON
esperado) podría degradar la calidad de los datos declarados durante semanas
sin que nadie lo note.

### 4.5 Golden set de evaluación

Un conjunto curado de mensajes de usuario representativos con el JSON
esperado, para correr como regresión cada vez que cambie el prompt de
extracción o el proveedor LLM (`LLM_PROVIDER` en `.env`: OpenAI, Gemini,
Vertex AI). Hoy el cambio de proveedor es una variable de entorno sin ningún
test que confirme que la calidad de extracción se mantiene entre proveedores.

## 5. Datos necesarios / ground truth

Con datos reales de outcomes ya en camino, lo que la tabla `leads` necesita
capturar para que sirvan como ground truth utilizable:

- **Resultado final con timestamp** — no solo el score al momento de cerrar
  la conversación, sino qué pasó después (compró, desistió, fue rechazado,
  sigue sin vivienda), y cuándo se supo. Sin el "cuándo", no se puede medir
  tiempo-a-conversión ni separar correctamente entrenamiento de validación
  por corte temporal.
- **Canal/origen del lead** — ya se guarda (para la vista de calidad por
  canal en `/asesor`); vale la pena confirmar que el pipeline de outcomes
  reales lo preserva, porque la precisión del scoring podría variar por
  canal y eso hoy no se puede medir.
- **Correcciones del asesor** — cuando un humano anula o ajusta la
  recomendación del motor, esa corrección es una señal de ground truth
  adicional, más rápida de acumular que esperar el desenlace final de cada
  lead, y directamente indica dónde el modelo se equivoca sistemáticamente.
- **Separación temporal calibración/validación** — a medida que crece el
  volumen real, evitar calibrar y validar sobre la misma ventana de tiempo
  (el mismo error que hoy comete `calibrar_scoring.py` contra la base
  sintética completa).

### Quick win de bajo esfuerzo, sin depender de datos reales

La columna `ahorros` (liquidez verificada) ya existe en `schema.sql` y en el
Excel de usuarios, pero no está conectada end-to-end:
`scripts/migrar_a_supabase.py` no la incluye en `COLUMNAS_USUARIOS`,
`data_store.py` no la selecciona en `SQL_USUARIOS`, y `scoring.py` nunca la
lee — hoy el único ahorro que cuenta es el booleano *declarado* en la
conversación (+8 puntos fijos, sin distinguir monto). Conectar esta columna
da una señal dura y verificada de capacidad de pago que hoy se está
ignorando, sin requerir ninguna integración externa nueva ni esperar a que
lleguen outcomes reales.

## 6. Roadmap priorizado

| Ítem | Sección | Esfuerzo | ¿Requiere outcomes reales? |
|---|---|---|---|
| Conectar `ahorros` verificado end-to-end | 5 | Bajo | No |
| Versionado de score en `leads` | 3.2 | Bajo | No |
| Reason codes estructurados | 3.1 | Medio | No |
| Métrica de tasa de fallos de extracción LLM | 4.4 | Bajo | No |
| Golden set de evaluación de extracción | 4.5 | Medio | No |
| Confianza por campo en extracción declarada | 4.2 | Medio | No |
| Detección de conflictos declarado vs. registrado | 4.3 | Medio | No |
| Test de consistencia `MIEMPRESA.md` ↔ `config.py` | 3.5 | Bajo | No |
| Shrinkage formal en peers / similitud vectorial | 2.3 | Medio | No (mejora con la base sintética actual, se afina más con datos reales) |
| Monitoreo continuo de distribución CALIENTE/TIBIO/FRIO | 3.4 | Medio | No para el mecanismo; sí para saber qué es "normal" en producción |
| Backtesting formal con holdout | 2.1 | Alto | **Sí** |
| Pesos ajustados por regresión logística | 2.2 | Alto | **Sí** |
| Shadow scoring antes de cambios en producción | 2.4 | Alto | **Sí** (para comparar contra tráfico real) |
| Auditoría de impacto dispar | 3.3 | Medio | Se puede empezar con la base sintética, pero solo es concluyente con datos reales |
| Cadencia formal de recalibración | 2.5 | Bajo (proceso) | **Sí** (para que tenga sentido recalibrar) |

La columna derecha es la más importante para secuenciar el trabajo: todo lo
marcado "No" es accionable ya, con el sistema actual, y varios ítems (reason
codes, versionado, golden set) son además prerrequisitos técnicos para que
el backtesting y el shadow scoring sean posibles cuando lleguen los datos
reales.
