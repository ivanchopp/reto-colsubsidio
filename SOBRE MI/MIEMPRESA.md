# Miempresa.md - Especificación del MVP

> Este documento describe lo que el proyecto **hace hoy**, no lo que se
> planeó en su momento. Si el código y este archivo se contradicen, gana el
> código y hay que corregir este archivo.

## 1. Qué hace

Un agente conversacional web que cualifica leads de pauta digital para
vivienda VIS y No VIS. El usuario entra al widget de chat del portal, se le
identifica por el número de teléfono con el que venía de WhatsApp, y el
sistema cruza ese número contra la base de usuarios.

Durante la charla el agente hace preguntas aspiracionales abiertas y, al
cerrar, entrega tres cosas: un score de viabilidad de 0 a 100 con su
explicación en lenguaje natural, una recomendación de proyecto real tomada de
los brochures del catálogo, y los subsidios de vivienda a los que el usuario
aplica.

El cierre dispara un correo real al asesor comercial con el resumen del lead,
y el lead queda guardado en Supabase para el panel `/asesor`.

El LLM es configurable por `.env`: OpenAI, Gemini (AI Studio) o Vertex AI.

## 2. Qué NO hace

- **No hay integraciones externas en producción.** La llegada desde WhatsApp
  se asume, no se recibe: no hay conexión con WhatsApp Business API, ni con
  Salesforce, ni con DataCrédito. El campo "reportado en centrales" sale de
  la base de usuarios, no de una consulta real.
- **No persiste la sesión de chat del lado del servidor.** El estado
  conversacional vive en un diccionario en memoria del proceso
  (`app/conversation.py`). El navegador guarda la conversación en
  `localStorage` y la retoma tras un refresh, validando primero que la sesión
  siga existiendo; pero si el servidor se reinicia, se pierde. Lo que sí
  sobrevive es el lead, que se escribe en la tabla `leads` en cada turno.
- **No procesa audio.** El dictado por voz lo resuelve el navegador con la Web
  Speech API (`static/app.js:369`): la transcripción llega al backend como
  texto normal. El LLM nunca recibe audio.
- **No hay backoffice de configuración.** Los pesos y umbrales del scoring se
  cambian en `app/config.py`, no desde una pantalla.
- **No toca trámites legales.** Nada de originación de crédito, aprobación
  hipotecaria ni firma de documentos.

## 3. Usuario y momento

- **Usuario:** interesado en vivienda captado por pauta digital, típicamente
  Meta Ads con click-to-WhatsApp.
- **Momento:** transaccional. Llega buscando información rápida e interactúa
  con el asesor digital escribiendo o dictando.

## 4. Flujo real

1. **Llegada e identificación.** El lead entra por la pantalla que simula la
   conversación de WhatsApp (paso 1 de la pauta click-to-WhatsApp) y pasa al
   widget con su número. El sistema lo busca en la tabla `usuarios`, registra
   el canal de origen y calcula su score inicial. Nunca se pide la cédula.
2. **Conversación mixta.** Hasta 6 preguntas abiertas, una por turno,
   intercalando aspiracionales (sueños, uso previsto, proyección a 5 años,
   imprescindibles) con tres que alimentan el scoring: en qué empresa trabaja,
   si viene ahorrando o tiene cesantías, y con quién se mudaría. Las tres son
   indirectas, nunca se pregunta el ingreso ni la afiliación de frente.
   Cada respuesta pasa por `app/extraccion.py`, que traduce el lenguaje
   natural a las variables del modelo y recalcula el score en vivo. Si la
   persona ya contó un dato por su cuenta, esa pregunta se salta. Si evade dos
   veces un tema, el agente cambia de tema y sigue.
3. **Scoring.** Blend de tres señales: árbol de reglas de negocio (peso 0,6),
   conversión histórica de usuarios con perfil similar (0,2) y similitud
   vectorial contra centroides de resultados históricos (0,2), más bonos por
   subsidios aplicables y por ahorro declarado para la cuota inicial. Ver
   sección 6.
4. **Recomendación.** Se elige un proyecto del catálogo según el segmento
   VIS/No VIS y las respuestas aspiracionales, y el LLM explica por qué encaja
   usando solo datos verificados del brochure.
5. **Resolución.**
   - *CALIENTE o TIBIO:* cierre celebratorio, se confirma que un asesor lo va
     a contactar.
   - *FRIO:* cierre educativo, se explica con tacto qué conviene preparar
     (ahorro, formalización de ingresos) sin cerrar la puerta. El lead queda
     marcado con sus bloqueantes concretos para poder retomarlo más adelante
     (ver `app/nutricion.py`), en vez de descartarse.

   En ambos casos, cuando la interacción se cierra de verdad (botón
   "Finalizar" o 3 minutos de inactividad) sale el correo al asesor.

## 5. Estado actual de los datos

Todo vive en Supabase (Postgres). Los Excel y JSON de `RECURSOS/` son la
fuente de carga, no la fuente de lectura en caliente: se migran con
`scripts/migrar_a_supabase.py`.

| Tabla | Contenido | Filas |
|---|---|---|
| `usuarios` | base de usuarios sintética | 3.449 |
| `subsidios` | subsidios de vivienda y sus requisitos | 7 |
| `proyectos` | brochures reales en JSONB | 18 |
| `leads` | una fila por sesión de chat, escrita en vivo | variable |

La tabla `leads` guarda además el canal de origen, la afiliación (para el cupo
90/10), los bloqueantes de nutrición y las variables declaradas en la
conversación.

De los 18 proyectos, 2 son documentos agregadores (portafolio y revista) que
el recomendador descarta, así que el catálogo recomendable son 16.

## 6. Scoring: cómo se calcula

El score final es un blend de tres señales independientes, cada una
normalizada a 0-100 antes de mezclarse:

| Señal | Peso | Qué mide |
|---|---|---|
| Reglas | 0,6 | ingreso en SMLV, estabilidad laboral, afiliación, centrales de riesgo, umbral VIS/No VIS |
| Peers | 0,2 | conversión histórica del grupo con mismo rango salarial, estado laboral y afiliación, medida como lift contra el promedio general de la base |
| Vectorial | 0,2 | posición relativa del perfil entre los centroides de los cuatro resultados históricos |

Si un usuario tiene menos de 3 peers, ese peso vuelve a las reglas.

Los centroides se calculan en vivo sobre la base y se cachean por proceso. No
hay un `centroids.json` precalculado.

**Regla 90/10.** Se aplica en dos niveles. Como penalización individual: en
VIS un no afiliado multiplica su score de reglas por 0,2, en No VIS por 0,8 y
además pierde el bono de +5. Y como cuota agregada en el panel del asesor, que
muestra cuánto cupo de no afiliados queda sobre los leads derivables del día
(ver sección 7).

**Umbrales.** CALIENTE desde 53,6 y TIBIO desde 29,1, calibrados con
`scripts/calibrar_scoring.py` para que CALIENTE sea el 12% superior de la
base. Distribución actual sobre los 3.449 usuarios: 11,9% CALIENTE, 37,8%
TIBIO, 50,3% FRIO.

Los umbrales son una decisión de capacidad del equipo comercial, no una
propiedad de los datos. Para moverlos: cambiar `PCT_OBJETIVO_CALIENTE` en
`app/config.py`, correr el script de calibración y copiar los dos valores que
sugiere.

## 7. Panel del asesor comercial

En `/asesor`, protegido con HTTP Basic Auth: usuario fijo `asesor` y la
contraseña compartida de `ASESOR_PASSWORD`. Si esa variable queda vacía el
panel se deshabilita por completo, nunca queda abierto por accidente.

Muestra los leads del día con su score, segmento, razones del cálculo,
subsidios aplicables y el desglose de contribuciones de cada señal.

Además tiene dos vistas agregadas que un lead individual no puede responder:

- **Cupo regulatorio 90/10.** Cuántos de los leads derivables (los CALIENTE,
  que son los que consumen cupo) son afiliados y cuántos no, contra el 10%
  permitido. Un lead sin registro cuenta como no afiliado: no hay con qué
  verificarlo y frente a una cuota regulatoria conviene el criterio
  conservador.
- **Calidad por canal.** Volumen y porcentaje de leads CALIENTE por origen
  (Meta, Google, WhatsApp, orgánico, contact center). Es la comparación con la
  que abre el reto: la pauta paga trae volumen y convierte peor que el
  orgánico, y sin medirlo por canal no se puede decidir dónde recortar.

En el detalle de un lead que no es CALIENTE aparece su **plan de nutrición**:
qué le falta concretamente para poder comprar, con la acción que destraba cada
caso (ver `app/nutricion.py`).

## 8. Criterios de aceptación

- **Identificación sin fricción:** dado un teléfono que existe en la base,
  cuando arranca la conversación, entonces el agente saluda por el nombre sin
  pedir cédula y sin mencionar que consultó una base de datos.
- **Explicabilidad:** dado un lead cerrado, cuando el asesor lo abre en
  `/asesor`, entonces ve el score, el segmento y las razones concretas que lo
  produjeron.
- **Handoff:** dada una interacción que se cierra, cuando se dispara el
  cierre, entonces sale un correo real al asesor con el resumen del lead.
- **Distribución operable:** dado el conjunto completo de usuarios, cuando se
  calcula el score de todos, entonces las tres categorías quedan pobladas y
  CALIENTE cae en un rango atendible. Verificado por
  `tests/test_distribucion_scoring.py`.
- **Fricción y bloqueo:** dado un usuario que evade las preguntas, cuando no
  aporta datos, entonces su score cae y el cierre es educativo en vez de
  handoff.

## 9. Pendientes conocidos

- **Persistencia de la sesión del lado del servidor.** El navegador ya retoma
  la conversación tras un refresh (`localStorage`), pero el estado sigue
  viviendo en memoria del proceso: si el servidor se reinicia, la
  conversación se pierde y el widget arranca de cero. El lead sí sobrevive,
  porque se escribe en Supabase en cada turno.
- **Recomendación para leads sin registro.** Ya se les calcula score y
  segmento VIS/No VIS con lo que declaran, pero todavía no se les recomienda
  un proyecto: la conversación cierra antes.
- **La entrada por WhatsApp es una simulación.** No hay integración con
  WhatsApp Business API; la pantalla previa reproduce el paso para mostrar de
  dónde viene el número.
- **El origen del lead no se valida.** Llega por `?origen=` en la URL y se
  acota al vocabulario conocido, pero nada impide que alguien lo falsee.

## 10. Supuestos por validar

- La tasa de rebote al llevar al usuario de WhatsApp a la landing no será
  crítica gracias al diseño tipo chat del widget.
- Los usuarios darán permiso de micrófono; si no, el fallback de texto
  alcanza.
- Los datos de `usuarios` son sintéticos, así que las tasas de conversión
  históricas que alimentan las señales de peers y vectorial son plausibles
  pero no reales.
