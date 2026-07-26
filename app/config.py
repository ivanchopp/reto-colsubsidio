from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

RECURSOS_DIR = BASE_DIR / "RECURSOS"
EXCEL_USUARIOS = RECURSOS_DIR / "Base_de_datos_usuarios_Colombia.xlsx"
EXCEL_SUBSIDIOS = RECURSOS_DIR / "Subsidios Vivienda Colombia.xlsx"
PROYECTOS_REALES_DIR = RECURSOS_DIR / "PROYECTOS"
SCORING_SCHEMA = RECURSOS_DIR / "buyer_persona_scoring_schema.json"

# Base de datos en la nube (Supabase/Postgres) que reemplaza los Excel/JSON
# de arriba como fuente de datos de usuarios, subsidios y proyectos.
# Cadena de conexion desde Supabase: Project Settings > Database > Connection
# string (formato SQLAlchemy: postgresql+psycopg://...).
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL", "")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-review")

# Vertex AI (alternativa a la API key de AI Studio: usa la cuenta de
# facturacion de Cloud directamente, sin el limite diario del Free Tier).
# GOOGLE_APPLICATION_CREDENTIALS debe apuntar a un archivo JSON de cuenta
# de servicio con el rol "Vertex AI User".
VERTEX_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "")
VERTEX_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
VERTEX_CREDENTIALS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
if VERTEX_CREDENTIALS_PATH:
    # resuelve a ruta absoluta (relativa a la raiz del proyecto) y la
    # reescribe en el entorno: google-auth busca esta variable directamente,
    # y una ruta relativa puede fallar segun desde donde se lance el server
    _ruta_absoluta = (BASE_DIR / VERTEX_CREDENTIALS_PATH).resolve()
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(_ruta_absoluta)
    VERTEX_CREDENTIALS_PATH = str(_ruta_absoluta)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or "587")
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
ASESOR_EMAIL_DESTINO = os.getenv("ASESOR_EMAIL_DESTINO", "")

# Contrasena compartida para entrar al panel del asesor comercial (/asesor).
# Si queda vacia, ese panel se deshabilita por completo (ver app/auth.py).
ASESOR_PASSWORD = os.getenv("ASESOR_PASSWORD", "")

# SMLV usado para normalizar ingresos. Ajustar al valor vigente real.
SMLV_COP = 1_423_500
