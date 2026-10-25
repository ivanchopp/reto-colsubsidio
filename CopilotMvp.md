Asesor digital para vivienda de Colsubsidio
Este proyecto es un MVP de asesor digital para vivienda de Colsubsidio: un agente conversacional que identifica al usuario, calcula su perfil de compra, recomienda proyectos y subsidios adecuados, y entrega un handoff comercial a un asesor por correo. La solución está bien enfocada en un caso real de negocio con una arquitectura clara: backend en Python/FastAPI, frontend estático, almacenamiento en Supabase (Postgres), integración con LLM multi-proveedor y un motor de scoring sofisticado.

Qué desarrollé / implementé en el proyecto:
- Backend de API y flujo de conversación:
  - Un servicio FastAPI en app/main.py con rutas para iniciar sesión, enviar mensajes, cerrar la conversación, consultar estado y exponer endpoints para el panel del asesor.
  - Manejo de sesiones en memoria, con persistencia parcial del lead en Supabase para no perder información al cerrar la conversación.
  - Lógica de negocio separada por módulos: conversation.py, handoff.py, scoring.py, recommender.py, data_store.py, leads_store.py, llm_client.py.
- Motor de perfilamiento y recomendación:
  - Un sistema de scoring basado en reglas de negocio, comparaciones con perfiles similares y similitud vectorial.
  - Evaluación de subsidios, segmentación VIS/No VIS, identificación de leads CALIENTE/TIBIO/FRIO y cálculo de factores de riesgo/afinidad.
  - Recomendación de proyectos según perfil, ciudad, ingreso, afinidad y elegibilidad.
- Integración con LLM y extracción estructurada:
  - Abstracción para OpenAI, Gemini y Vertex AI en app/llm_client.py.
  - Envío de prompts y extracción de JSON para clasificar datos del usuario sin depender del modelo específico.
  - Fallbacks robustos ante error de proveedor o formato inválido.
- Panel del asesor y flujo comercial:
  - Frontend estático en static/asesor.html y static/asesor.js para consultar leads del día, revisar métricas y ver detalle de cada sesión.
  - Generación de resúmenes de lead y envío automático por correo usando Resend.
  - Autenticación básica para proteger la vista del asesor.
- Persistencia y carga masiva de datos:
  - Carga de datos desde Excel/JSON a Supabase con scripts de migración.
  - Estructura de base para usuarios, subsidios, proyectos y leads.
  - Validación de esquemas y manejo explícito de data quality.

Técnicas y herramientas que utilicé:
- Python moderno y arquitectura de servicios:
  - FastAPI + Pydantic para APIs y validación de payloads.
  - Separación de responsabilidades por módulos, con modelos de dominio y servicios claros.
  - Dependencias e inyección de dependencias para proteger endpoints del asesor.
- Diseño robusto de inteligencia artificial:
  - Prompt engineering con system prompts y prompts por turno.
  - Extracción de datos en JSON estructurado para convertir conversaciones libres en datos útiles.
  - Estrategia de resiliencia: fallback cuando el modelo falla, validación del JSON y captura de métricas de extracción.
- Modelado de negocio y análisis de datos:
  - Reglas explicables para scoring: ingreso, estabilidad laboral, afiliación, crédito, ahorro, subsidios, segmento.
  - Blend de señales: reglas + peer matching + similitud vectorial.
  - Uso de metrics y calibration logic para ajustar pesos y umbrales según comportamiento real.
- Base de datos y ETL:
  - Supabase/Postgres para persistencia operativa.
  - Scripts ETL para migrar recursos de RECURSOS/ a tablas estructuradas.
  - Validación idempotente de carga y manejo de inconsistencias.
- Frontend ligero:
  - HTML/CSS/JavaScript estático, sin framework pesado, ideal para un MVP de demo.
  - Consumo de APIs REST para renderizar estado del chat y lead.
- Observabilidad y operación:
  - Logging de errores, métricas de extracción y manejo de fail-open para no romper la experiencia del usuario.
  - Middleware para cache-control y control de errores HTTP.
  - Configuración centralizada con variables de entorno.

La parte más interesante del proyecto es la combinación de varios niveles:
- Conversación con LLM
- Clasificación de datos
- Scoring explicable con reglas del negocio
- Comparación con históricos
- Recomendación práctica
- Persistencia y handoff comercial

Es decir, no es solo un chatbot; es un sistema de lead qualification y recomendación comercial con un pipeline completo. La arquitectura demuestra capacidad para construir soluciones end-to-end en Python: API, LLM, lógica de negocio, analítica, base de datos y frontend, todo integrado en una experiencia que simula un producto real de venta de vivienda y subsidios.
