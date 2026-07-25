# Asesor Digital de Vivienda Colsubsidio (Demo)

Agente conversacional que perfila usuarios, recomienda proyectos de vivienda y
subsidios aplicables, y hace el *handoff* del resumen al asesor comercial por
correo. Backend en FastAPI, frontend estático simple, y LLM configurable
(OpenAI, Gemini o Vertex AI).

## Requisitos

- Python 3.11+
- Una cuenta de [Supabase](https://supabase.com) (Postgres) para los datos, o
  usar los Excel/JSON locales de `RECURSOS/` como alternativa de solo lectura
- Una API key de OpenAI o Google (Gemini/Vertex) para el LLM
- (Opcional) Credenciales SMTP para el envío del correo al asesor

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

   Este script es idempotente: cada tabla se vacía y se vuelve a cargar con el
   contenido de `RECURSOS/`, así que se puede correr varias veces sin problema.

## Ejecutar el servidor

```bash
uvicorn app.main:app --reload
```

La app queda disponible en [http://localhost:8000](http://localhost:8000).

## Correr los tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Estructura del proyecto

```
app/           Backend FastAPI (scoring, recomendador, conversación, envío de correo)
static/        Frontend estático (HTML/CSS/JS)
RECURSOS/      Datos base: usuarios y subsidios (Excel), catálogo de proyectos (JSON), schema SQL
scripts/       Utilidades, incl. migración de datos a Supabase
tests/         Suite de pytest
```

## Notas

- Los datos en `RECURSOS/Base_de_datos_usuarios_Colombia.xlsx` son sintéticos,
  generados para efectos de esta demo.
- El valor de `SMLV_COP` en `app/config.py` debe actualizarse al salario
  mínimo legal vigente real cuando corresponda.
