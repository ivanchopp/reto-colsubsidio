# Plan de Proyecto: Asesor Digital de Vivienda Colsubsidio

**Última actualización:** 5 de agosto de 2026

---

## 🏷️ Labels Propuestos

### Por Prioridad
- **🔴 blocker** - Bloquea otros trabajos, crítico para avanzar
- **🟠 high-priority** - Importante, debe resolverse pronto
- **🟡 medium-priority** - Normal, puede esperar un poco
- **🟢 low-priority** - Mejora, puede hacerse después

### Por Tipo de Trabajo
- **✨ feature** - Nueva funcionalidad
- **🐛 bug** - Error que hay que corregir
- **🔧 maintenance** - Limpieza de código, refactoring, deuda técnica
- **📖 documentation** - Documentación o comentarios
- **🧪 testing** - Tests, cobertura, QA
- **🚀 performance** - Optimización, velocidad, escalabilidad
- **🔐 security** - Seguridad, privacidad, permisos
- **🎨 ui-ux** - Interfaz, diseño, usabilidad

### Por Área
- **backend** - FastAPI, scoring, conversación, base de datos
- **frontend** - HTML, CSS, JavaScript, chat, panel asesor
- **data** - Migraciones, esquema, validación, RECURSOS/
- **deployment** - Render, configuración, CI/CD
- **llm** - LLM, prompts, agente conversacional

### Estados Especiales
- **help-wanted** - Se busca colaboración
- **good-first-issue** - Bueno para principiantes
- **needs-review** - Necesita revisión
- **wontfix** - No se va a hacer
- **duplicate** - Duplicado de otro issue

---

## 📅 Milestones

### Milestone 1: MVP Base Consolidado
**Objetivo:** Asegurar que el core del sistema funciona correctamente en producción
**Duración:** 2 semanas
**Inicio:** 5 de agosto

#### Issues Asociados:
1. Validar integración Supabase en producción
2. Auditar y corregir errores de scoring
3. Completar cobertura de tests unitarios
4. Documentar flujos de API

---

### Milestone 2: Experiencia del Asesor Mejorada
**Objetivo:** Panel del asesor más intuitivo y con más datos accionables
**Duración:** 3 semanas
**Inicio:** 19 de agosto

#### Issues Asociados:
1. Rediseñar panel `/asesor` con mejores visualizaciones
2. Agregar filtros avanzados y búsqueda
3. Exportar leads a CSV/Excel
4. Dashboard de métricas en tiempo real

---

### Milestone 3: Robustez y Seguridad
**Objetivo:** Mejorar manejo de errores, logging y protección de datos
**Duración:** 2 semanas
**Inicio:** 9 de septiembre

#### Issues Asociados:
1. Implementar rate limiting en API
2. Mejorar logging estructurado
3. Cifrar datos sensibles en base
4. Auditoría de acceso y cambios

---

### Milestone 4: Escalabilidad
**Objetivo:** Preparar sistema para crecer a más usuarios y flujos
**Duración:** 3 semanas
**Inicio:** 23 de septiembre

#### Issues Asociados:
1. Separar sesiones en Redis
2. Implementar caché de recomendaciones
3. Optimizar queries a Supabase
4. Configurar CDN para assets estáticos

---

## 🔗 Issues Detallados

### Issue 1: Validar integración Supabase en producción
**Estado:** Todo  
**Prioridad:** 🔴 blocker  
**Labels:** backend, data, testing  
**Milestone:** MVP Base Consolidado  
**Asignado a:** TBD

**Descripción:**
Verificar que la conexión y queries a Supabase funcionan correctamente en el entorno de producción (Render).

**Checklist:**
- [ ] Verificar conexión SSL/TLS a base
- [ ] Probar migraciones de datos (usuarios, subsidios, proyectos)
- [ ] Validar tabla `leads` se escribe correctamente
- [ ] Revisar pool de conexiones y timeout
- [ ] Documentar variables de entorno requeridas
- [ ] Crear script de health check
- [ ] Registrar queries lentas en logs

**Notas:**
Crítico para que el sistema no falle en producción. Coordinar con el equipo de DevOps.

---

### Issue 2: Auditar y corregir errores de scoring
**Estado:** Todo  
**Prioridad:** 🔴 blocker  
**Labels:** backend, bug, testing  
**Milestone:** MVP Base Consolidado  
**Asignado a:** TBD

**Descripción:**
Revisar la lógica de scoring (app/scoring.py) y validar que los umbrales y pesos coinciden con la especificación de SOBRE MI/MIEMPRESA.md.

**Checklist:**
- [ ] Ejecutar `python scripts/calibrar_scoring.py`
- [ ] Validar distribución de scores vs. objetivo (% CALIENTE)
- [ ] Revisar árbol de reglas de negocio (peso 0,6)
- [ ] Auditar señal de LLM (peso 0,2)
- [ ] Auditar señal de similitud con proyectos (peso 0,2)
- [ ] Probar casos edge (sin datos, usuario no registrado, etc.)
- [ ] Documentar fórmula en README

**Notas:**
Ver app/config.py para umbrales. Usar casos de prueba del archivo SOBRE MI/MIEMPRESA.md.

---

### Issue 3: Completar cobertura de tests unitarios
**Estado:** Todo  
**Prioridad:** 🟠 high-priority  
**Labels:** backend, testing, maintenance  
**Milestone:** MVP Base Consolidado  
**Asignado a:** TBD

**Descripción:**
Aumentar cobertura de tests a mínimo 80%. Incluir tests para conversación, extracción, scoring y manejo de errores.

**Checklist:**
- [ ] Revisar cobertura actual con pytest-cov
- [ ] Agregar tests para extraccion.py (NLU)
- [ ] Agregar tests para conversation.py (estado, fases)
- [ ] Agregar tests para scoring.py (blend, umbrales)
- [ ] Agregar tests para handoff.py (debe_derivar_al_asesor)
- [ ] Agregar tests de integración (DB + API)
- [ ] Configurar cobertura en CI/CD
- [ ] Documentar cómo correr tests localmente

**Notas:**
Tests de integración usan la BD real (ver conftest.py). Ver requirements-dev.txt.

---

### Issue 4: Documentar flujos de API
**Estado:** Todo  
**Prioridad:** 🟡 medium-priority  
**Labels:** backend, documentation  
**Milestone:** MVP Base Consolidado  
**Asignado a:** TBD

**Descripción:**
Crear documentación de OpenAPI/Swagger para todos los endpoints.

**Checklist:**
- [ ] Agregar docstrings a app/main.py
- [ ] Generar OpenAPI spec automáticamente
- [ ] Crear archivo openapi.json
- [ ] Documentar /api/chat endpoints (GET sesión, POST mensaje)
- [ ] Documentar /api/asesor endpoints (GET leads, resumen, métricas)
- [ ] Documentar códigos de error y rate limits
- [ ] Agregar ejemplos de request/response
- [ ] Publicar en Swagger UI o ReDoc

**Notas:**
FastAPI genera spec automáticamente en /openapi.json.

---

### Issue 5: Rediseñar panel `/asesor` con mejores visualizaciones
**Estado:** Todo  
**Prioridad:** 🟠 high-priority  
**Labels:** frontend, ui-ux, feature  
**Milestone:** Experiencia del Asesor Mejorada  
**Asignado a:** TBD

**Descripción:**
Mejorar interfaz del panel del asesor con gráficos, cards interactivos y mejor navegación.

**Checklist:**
- [ ] Rediseñar header con métricas resumidas
- [ ] Agregar gráficos de distribución (CALIENTE/TIBIO/FRIO)
- [ ] Agregar timeline de conversaciones por hora
- [ ] Mejorar card de lead individual (más datos visibles)
- [ ] Agregar mini preview del resumen sin click
- [ ] Responsive design para móvil y tablet
- [ ] Auditar accesibilidad (WCAG 2.1)
- [ ] Testear en navegadores modernos

**Notas:**
Diseño debe mantener velocidad y legibilidad. Ver static/asesor.css y static/asesor.js.

---

### Issue 6: Agregar filtros avanzados y búsqueda
**Estado:** Todo  
**Prioridad:** 🟡 medium-priority  
**Labels:** frontend, feature  
**Milestone:** Experiencia del Asesor Mejorada  
**Asignado a:** TBD

**Descripción:**
Permitir filtrar leads por segmento, ciudad, canal, rango de scores, fecha, etc. Agregar búsqueda por nombre/teléfono.

**Checklist:**
- [ ] Crear UI para filtros (dropdown, date picker, etc.)
- [ ] Implementar búsqueda en client-side (no afecte API)
- [ ] Agregar endpoint /api/asesor/filtros-disponibles
- [ ] Persistir filtros en localStorage
- [ ] Agregar botón "Limpiar filtros"
- [ ] Mostrar badge con cantidad de filtros activos
- [ ] Validar performance con 1000+ leads
- [ ] Documentar sintaxis de búsqueda

**Notas:**
Considerar usar una librería de búsqueda ligera (lunr.js) si es necesario.

---

### Issue 7: Exportar leads a CSV/Excel
**Estado:** Todo  
**Prioridad:** 🟡 medium-priority  
**Labels:** backend, feature  
**Milestone:** Experiencia del Asesor Mejorada  
**Asignado a:** TBD

**Descripción:**
Permitir descargar lista de leads activos en formato CSV o Excel, con todas las columnas relevantes.

**Checklist:**
- [ ] Crear endpoint GET /api/asesor/export?format=csv|xlsx
- [ ] Incluir todas las columnas del resumen (teléfono, nombre, ciudad, score, etc.)
- [ ] Sanitizar datos sensibles antes de exportar
- [ ] Agregar timestamp a nombre del archivo
- [ ] Auditar permisos (solo admin)
- [ ] Testear con dataset grande
- [ ] Documentar formato de exportación
- [ ] Agregar botón en interfaz

**Notas:**
Para Excel usar openpyxl o xlsxwriter. Para CSV usar csv module de stdlib.

---

### Issue 8: Dashboard de métricas en tiempo real
**Estado:** Todo  
**Prioridad:** 🟡 medium-priority  
**Labels:** frontend, backend, feature  
**Milestone:** Experiencia del Asesor Mejorada  
**Asignado a:** TBD

**Descripción:**
Crear dashboard con métricas vivas: leads por hora, conversión por canal, valor promedio, etc.

**Checklist:**
- [ ] Crear endpoint /api/asesor/metricas-tiempo-real
- [ ] Calcular: leads activos, tasa de conversión, score promedio
- [ ] Calcular: conversiones por canal de origen
- [ ] Calcular: tiempo promedio de conversación
- [ ] Agregar gráfico de línea (leads por hora)
- [ ] Agregar tabla de canales con KPIs
- [ ] Implementar auto-refresh cada 30 segundos
- [ ] Usar WebSocket si tráfico es muy alto

**Notas:**
Métricas deben calcularse desde tabla `leads` en Supabase.

---

### Issue 9: Implementar rate limiting en API
**Estado:** Todo  
**Prioridad:** 🟠 high-priority  
**Labels:** backend, security, feature  
**Milestone:** Robustez y Seguridad  
**Asignado a:** TBD

**Descripción:**
Proteger API contra abuso limitando requests por IP y por sesión.

**Checklist:**
- [ ] Agregar dependencia slowapi o similar
- [ ] Limitar POST /api/chat/mensaje a 1 req/segundo por sesión
- [ ] Limitar POST /api/iniciar a 5 req/minuto por IP
- [ ] Limitar GET /api/asesor/* a 10 req/minuto por usuario
- [ ] Retornar headers X-RateLimit-*
- [ ] Loguear intentos excesivos
- [ ] Documentar límites en API docs
- [ ] Testear con load testing

**Notas:**
Coordinar con DevOps sobre límites en proxy (Render).

---

### Issue 10: Mejorar logging estructurado
**Estado:** Todo  
**Prioridad:** 🟡 medium-priority  
**Labels:** backend, maintenance, debugging  
**Milestone:** Robustez y Seguridad  
**Asignado a:** TBD

**Descripción:**
Cambiar logging de print/basicConfig a formato JSON estructurado con niveles claros.

**Checklist:**
- [ ] Integrar python-json-logger
- [ ] Definir campos estándar (timestamp, level, session_id, endpoint, etc.)
- [ ] Reemplazar logging.error(), warning(), etc. en todo el código
- [ ] Agregar contexto de request (user, IP, duración)
- [ ] Loguear cambios importantes en leads
- [ ] Loguear errores de LLM con stack trace
- [ ] Configurar rotación de logs
- [ ] Verificar logs en Render dashboard

**Notas:**
Ver app/email_sender.py para ejemplo de logging.error existente.

---

### Issue 11: Cifrar datos sensibles en base
**Estado:** Todo  
**Prioridad:** 🔴 blocker  
**Labels:** backend, security, data  
**Milestone:** Robustez y Seguridad  
**Asignado a:** TBD

**Descripción:**
Encriptar documento de identidad, teléfono y otros datos sensibles en tabla `leads`.

**Checklist:**
- [ ] Evaluar opciones: Fernet (cryptography), NaCl, o soporte nativo de Supabase
- [ ] Definir columnas a cifrar: documento, teléfono, email
- [ ] Implementar funciones encrypt/decrypt
- [ ] Crear migration script para datos existentes
- [ ] Actualizar app/main.py para encriptar antes de INSERT
- [ ] Actualizar panel asesor para desencriptar al mostrar
- [ ] Documentar política de acceso a claves
- [ ] Auditar en logs quién accede a datos cifrados

**Notas:**
Supabase soporta pgcrypto extension. Considerar key rotation.

---

### Issue 12: Auditoría de acceso y cambios
**Estado:** Todo  
**Prioridad:** 🟡 medium-priority  
**Labels:** backend, security, maintenance  
**Milestone:** Robustez y Seguridad  
**Asignado a:** TBD

**Descripción:**
Implementar audit log para registrar quién accede a datos de leads y cuándo.

**Checklist:**
- [ ] Crear tabla `audit_logs` en Supabase
- [ ] Registrar: usuario, acción, lead_id, timestamp, IP
- [ ] Loguear: login al panel, visualización de lead, exportación
- [ ] Loguear: cambios manuales (si aplica)
- [ ] Crear endpoint /api/asesor/audit-logs (solo admin)
- [ ] Retener logs por mínimo 1 año
- [ ] Alertar si acceso sospechoso
- [ ] Documentar política de retención

**Notas:**
Considerar usar Supabase RLS (Row Level Security) para mayor seguridad.

---

### Issue 13: Separar sesiones en Redis
**Estado:** Todo  
**Prioridad:** 🟡 medium-priority  
**Labels:** backend, performance, scalability  
**Milestone:** Escalabilidad  
**Asignado a:** TBD

**Descripción:**
Mover estado de conversaciones de memoria en proceso a Redis para permitir múltiples instancias.

**Checklist:**
- [ ] Agregar dependencia redis y aioredis
- [ ] Refactorizar app/conversation.py para usar Redis
- [ ] Definir TTL de sesión (24 horas)
- [ ] Configurar Redis en Render
- [ ] Migrar datos de sesiones en memoria a Redis
- [ ] Implementar invalidación al cerrar sesión
- [ ] Testear con múltiples procesos
- [ ] Documentar configuración de Redis

**Notas:**
Esto permite escalar a múltiples workers sin perder estado.

---

### Issue 14: Implementar caché de recomendaciones
**Estado:** Todo  
**Prioridad:** 🟡 medium-priority  
**Labels:** backend, performance, feature  
**Milestone:** Escalabilidad  
**Asignado a:** TBD

**Descripción:**
Cachear proyectos recomendados por perfil para evitar queries repetidas.

**Checklist:**
- [ ] Crear tabla `cache_recomendaciones` en Supabase o usar Redis
- [ ] Guardar: profile_hash -> proyecto_recomendado
- [ ] Definir TTL de caché (24 horas)
- [ ] Invalidar caché cuando cambien datos base
- [ ] Monitorear hit rate del caché
- [ ] Documentar estrategia de invalidación
- [ ] Testear performance con dataset grande

**Notas:**
Ver app/recomendador.py para lógica actual.

---

### Issue 15: Optimizar queries a Supabase
**Estado:** Todo  
**Prioridad:** 🟡 medium-priority  
**Labels:** backend, performance, data  
**Milestone:** Escalabilidad  
**Asignado a:** TBD

**Descripción:**
Revisar y optimizar todas las queries SQL para reducir latencia y uso de recursos.

**Checklist:**
- [ ] Perfil queries con EXPLAIN ANALYZE
- [ ] Agregar índices faltantes en `leads`, `usuarios`, `subsidios`
- [ ] Eliminar N+1 queries en app/data_store.py
- [ ] Usar selectivos en SELECT (no SELECT *)
- [ ] Implementar pagination en endpoints de lista
- [ ] Cachear datos que cambian poco (usuarios, subsidios)
- [ ] Documentar plan de queries en README
- [ ] Monitorear en Supabase dashboard

**Notas:**
Revisar app/data_store.py especialmente.

---

### Issue 16: Configurar CDN para assets estáticos
**Estado:** Todo  
**Prioridad:** 🟢 low-priority  
**Labels:** frontend, performance, deployment  
**Milestone:** Escalabilidad  
**Asignado a:** TBD

**Descripción:**
Servir archivos estáticos (CSS, JS, imágenes) desde CDN para mejorar velocidad global.

**Checklist:**
- [ ] Evaluar opciones: Cloudflare, Render CDN, etc.
- [ ] Crear bucket en storage (Supabase, S3, etc.)
- [ ] Configurar CORS correctamente
- [ ] Versionar assets (cache busting)
- [ ] Minificar CSS y JS
- [ ] Optimizar imágenes (WebP, srcset)
- [ ] Configurar headers de caché (Cache-Control)
- [ ] Testear desde múltiples regiones

**Notas:**
Puede esperar a después del MVP.

---

## 📊 Resumen de Trabajo

| Milestone | Issues | Prioridad | Duración |
|-----------|--------|-----------|----------|
| MVP Base Consolidado | 4 | 🔴🔴🟠 | 2 sem |
| Experiencia del Asesor | 4 | 🟠🟡🟡🟡 | 3 sem |
| Robustez y Seguridad | 4 | 🔴🟡🟡🟡 | 2 sem |
| Escalabilidad | 4 | 🟢🟡🟡🟡 | 3 sem |

**Total:** 16 issues  
**Duración estimada:** 10 semanas  
**Fecha de conclusión estimada:** 14 de octubre de 2026

---

## 🚀 Próximos Pasos

1. Revisar este plan con el equipo
2. Crear issues en GitHub con este template
3. Asignar issues a miembros del equipo
4. Agregar estimaciones de esfuerzo (story points)
5. Comenzar con issues 🔴 blocker
6. Revisar progreso semanalmente
