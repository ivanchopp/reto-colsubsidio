# Miempresa.md - Especificación del MVP (Versión Híbrida)

## 1. Qué hace
Un agente conversacional híbrido (WhatsApp -> Web) que cualifica leads de pauta digital para Vivienda VIS. Inicia con un saludo automatizado en WhatsApp que dirige al usuario a un widget interactivo en el portal web. Allí, procesa texto y notas de voz mediante Gemini 2.5 Flash, extrae variables financieras y calcula la probabilidad de compra usando similitud vectorial (NumPy) en tiempo real, todo visible para los jueces en un Dashboard de Explicabilidad.

## 2. Qué NO hace
- **No integraciones en producción:** El inicio en WhatsApp es simulado (mock). No hay conexión real con WhatsApp Business API, Salesforce, ni DataCrédito.
- **No procesamiento de bases en tiempo real:** No se usa una base de datos pesada en caliente; se usa un archivo pre-calculado `centroids.json`.
- **No envíos ni automatizaciones reales:** El envío al equipo comercial se simula en el panel de explicabilidad; no hay webhooks ni emails reales.
- **No backoffice ni autenticación:** No se creará un panel de administración para ajustar pesos matemáticos ni sistemas de login complejos para el usuario.
- **No trámites legales:** Queda fuera cualquier flujo de originación de crédito o firma de documentos.

## 3. Usuario y momento
- **Usuario:** Interesado en vivienda VIS captado mediante pauta en Meta Ads (Click-to-WhatsApp).
- **Momento:** Altamente transaccional. Llega a WhatsApp buscando información rápida y es transicionado a una landing page web donde interactúa con el asesor digital a través de texto o voz.

## 4. Flujo en 5 pasos
1. **Captura y Transición:** El lead envía el mensaje pre-configurado a WhatsApp. El bot saluda, captura implícitamente el número y entrega el link al portal web.
2. **Navegación Web Multimodal:** El usuario abre el chatbot web (estado guardado en LocalStorage). Puede interactuar enviando notas de voz o escribiendo.
3. **Extracción y Scoring (Background):** A través de preguntas indirectas (ej. "¿En qué empresa trabajas?"), el bot extrae entidades (ingresos, subsidios). En background, compara el perfil contra `centroids.json` modificando el score vectorial.
4. **Penalización Regulatoria:** Si en dos intentos el bot no logra validar la afiliación (o infiere que no es afiliado), aplica la penalización (Score * 0.80) por la regla 90/10.
5. **Resolución (Handoff o Nutrición):** 
   - *Score > 0.70 (Calientes):* Se cierra la venta, confirma el número de WhatsApp original y se envía la alerta al Dashboard del asesor.
   - *Score < 0.40 (Fríos):* No hay transferencia humana. El bot dirige amablemente al usuario a enlaces de ahorro o afiliación.

## 5. Criterios de Aceptación (Demo)
- **Criterio 1 (Transición y Memoria):** DADO que el usuario llega vía WhatsApp simulado, CUANDO hace clic en el enlace, ENTONCES el widget web inicia la conversación reconociendo su llegada y manteniendo la sesión viva aunque refresque la página (LocalStorage).
- **Criterio 2 (Multimodalidad y Explicabilidad):** DADO que el usuario envía una nota de voz, CUANDO Gemini 2.5 Flash procesa el audio, ENTONCES el "Panel de Explicabilidad" muestra en vivo la extracción de variables y el recálculo matemático de los vectores.
- **Criterio 3 (Fricción y Bloqueo):** DADO que un usuario exige un asesor sin responder preguntas, CUANDO las variables quedan en cero, ENTONCES el score se desploma y el sistema bloquea el traspaso al equipo comercial, redirigiéndolo a flujos de nutrición.

## 6. Datos que toca
- **Inputs:** Número de WhatsApp (simulado al inicio), notas de voz, texto, respuestas a preguntas indirectas.
- **Memoria Temporal:** LocalStorage (frontend web), SQLite/PostgreSQL (estado de la sesión web).
- **Base de Conocimiento:** Archivo local `centroids.json` generado a partir del pre-procesamiento de los 4,142 registros históricos.

## 7. Supuestos por validar
- Asumimos que la tasa de rebote al sacar al usuario de WhatsApp hacia la landing page web no será crítica gracias al diseño UI tipo chat del widget.
- Asumimos que los usuarios otorgarán permisos de micrófono en el navegador; de lo contrario, el fallback de texto será suficiente.