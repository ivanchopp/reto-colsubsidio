# Asesor Digital de Vivienda Colsubsidio (Demo)

Agente conversacional que perfila usuarios, recomienda proyectos de vivienda y
subsidios aplicables, y hace el *handoff* del resumen al asesor comercial por
correo. Backend en FastAPI, frontend estático simple, y LLM configurable
(OpenAI, Gemini o Vertex AI).

## Demo desplegada (Render)

- **Chat del cliente**: https://colsubsidio-asesor-vivienda.onrender.com/

- **Panel del asesor**: https://colsubsidio-asesor-vivienda.onrender.com/asesor
  (usuario `asesor`, contraseña = valor de `ASESOR_PASSWORD` configurado en
  el entorno de Render — pídela por un canal privado, no está en este repo)

- **Buzón de correo del asesor**: `retocolsubsidio@gmail.com` — la contraseña
  se comparte por un canal privado (password manager / chat directo), nunca
  en este repositorio.

El plan gratuito de Render duerme el servicio tras un rato sin tráfico: la
primera petición después de eso puede tardar ~30-60s en responder mientras
arranca de nuevo.

Al cerrarse cada conversación, el resumen del lead (perfil, score, proyecto
recomendado y subsidios aplicables) se envía automáticamente por correo a
**retocolsubsidio@gmail.com** (configurado en `ASESOR_EMAIL_DESTINO`; ver
`app/email_sender.py` y `app/handoff.py`). Ese mismo resumen también queda
disponible en vivo en el panel del asesor de arriba.

## Requisitos

- Python 3.11+
- Una cuenta de [Supabase](https://supabase.com) (Postgres). **No es
  opcional**: `app/data_store.py` lee todo desde la base, los Excel y JSON de
  `RECURSOS/` son solo la fuente de carga inicial. Sin `SUPABASE_DB_URL` la
  app levanta pero cualquier consulta falla.
- Una API key de OpenAI o Google (Gemini/Vertex) para el LLM
- (Opcional) Credenciales SMTP para el envío del correo al asesor
- (Opcional) `ASESOR_PASSWORD` para habilitar el panel `/asesor`

## Instalación

1. Clona el repositorio e instala las dependencias:

   ```bash
   git clone https://github.com/ivanchopp/reto-colsubsidio.git
   cd reto-colsubsidio
   python -m venv .venv
   .venv\Scripts\activate      # Windows
   # source .venv/bin/activate # macOS/Linux
   pip install -r requirements.txt
   ```

2. Copia la plantilla de variables de entorno y complétala:

   ```bash
   cp .env.example .env
   ```

   Edita `.env` y define, como mínimo:

   - `LLM_PROVIDER` (`openai`, `gemini` o `vertex`) y la API key correspondiente
     (`OPENAI_API_KEY` o `GOOGLE_API_KEY`). Para `vertex`, además necesitas
     `GOOGLE_CLOUD_PROJECT` y un archivo de credenciales de cuenta de servicio
     (ver `GOOGLE_APPLICATION_CREDENTIALS` en `.env.example`).
   - `SUPABASE_DB_URL`: cadena de conexión de tu proyecto de Supabase
     (Project Settings > Database > Connection string, formato SQLAlchemy).
   - `SMTP_USER` / `SMTP_PASSWORD` / `ASESOR_EMAIL_DESTINO` si quieres que el
     envío de correo al asesor funcione (si no, el resumen igual se genera
     pero el envío fallará silenciosamente).

   **Nunca subas tu `.env` ni ningún archivo de credenciales a git** — ya
   están excluidos en `.gitignore`.

3. Crea las tablas y migra los datos de ejemplo a Supabase:

   ```bash
   # 1. Corre RECURSOS/sql/schema.sql en el SQL Editor de tu proyecto Supabase
   # 2. Con SUPABASE_DB_URL ya configurada en .env:
   python scripts/migrar_a_supabase.py
   ```

   Este script es idempotente: `usuarios`, `subsidios` y `proyectos` se vacían
   y se vuelven a cargar con el contenido de `RECURSOS/`, así que se puede
   correr varias veces sin problema. **No toca la tabla `leads`**, que es la
   que se escribe en vivo con cada conversación.

   Si el archivo fuente cambia sus encabezados o trae documentos repetidos, el
   script se detiene con un mensaje explícito en vez de cargar datos rotos.

4. Crea la tabla de leads del panel del asesor (idempotente, nunca borra):

   ```bash
   python scripts/crear_tabla_leads.py
   ```

## Ejecutar el servidor

```bash
uvicorn app.main:app --reload
```

- Chat del cliente: [http://localhost:8000](http://localhost:8000)
- Panel del asesor: [http://localhost:8000/asesor](http://localhost:8000/asesor)
  (usuario `asesor`, contraseña de `ASESOR_PASSWORD`)

## Correr los tests

```bash
pip install -r requirements-dev.txt
pytest
```

`tests/test_distribucion_scoring.py` es de integración y consulta la base
real; se salta solo si no hay `SUPABASE_DB_URL` configurada.

## Calibrar el scoring

```bash
python scripts/calibrar_scoring.py
```

Reporta el rango que usa cada señal del blend, la distribución de scores sobre
toda la base y qué umbrales hacen falta para el porcentaje objetivo de leads
CALIENTE definido en `app/config.py`. Correrlo después de cambiar la base de
usuarios o los pesos del scoring.

## Estructura del proyecto

```
app/           Backend FastAPI (scoring, recomendador, conversación, envío de correo, panel asesor)
static/        Frontend estático (HTML/CSS/JS), chat del cliente y panel del asesor
RECURSOS/      Fuente de carga: usuarios y subsidios (Excel), brochures de proyectos (JSON), schema SQL
scripts/       Migración de datos, creación de la tabla leads y calibración del scoring
tests/         Suite de pytest (unitarios + un módulo de integración)
SOBRE MI/      Contrato de tono del agente y especificación del MVP
SKILL/         Recursos de marca
```

## Notas

- Los datos en `RECURSOS/Base_de_datos_usuarios_Colombia.xlsx` son sintéticos,
  generados para efectos de esta demo.
- El valor de `SMLV_COP` en `app/config.py` debe actualizarse al salario
  mínimo legal vigente real cuando corresponda.
- El estado de cada conversación vive en memoria del proceso, no en la base:
  al reiniciar el servidor se pierden las sesiones abiertas. Lo que sí
  persiste es el lead, que se guarda en Supabase en cada turno.
- `SOBRE MI/MIEMPRESA.md` documenta el alcance real del MVP y sus pendientes
  conocidos.
