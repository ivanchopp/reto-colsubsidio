from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

RECURSOS_DIR = BASE_DIR / "RECURSOS"
EXCEL_USUARIOS = RECURSOS_DIR / "Base_de_datos_usuarios_Colombia.xlsx"
EXCEL_SUBSIDIOS = RECURSOS_DIR / "Subsidios Vivienda Colombia.xlsx"
# El nombre debe coincidir exacto con la carpeta en disco: macOS no distingue
# mayusculas y Linux (Render) si, asi que un "PROYECTOS" aqui hace que el glob
# no encuentre nada en el servidor y la migracion cargue cero proyectos sin
# lanzar ningun error.
PROYECTOS_REALES_DIR = RECURSOS_DIR / "Proyectos"
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

# --- Calibracion del scoring (ver scripts/calibrar_scoring.py) ---
# Techo de normalizacion del ingreso, en SMLV, para cada segmento. Tiene que
# quedar cerca del ingreso maximo que realmente aparece en la base para ese
# segmento: si se pone por encima, ningun perfil llega a saturar el aporte de
# ingreso y todo el scoring queda con un techo artificial que no se ve en
# ninguna parte. Correr scripts/calibrar_scoring.py despues de cambiar la
# fuente de datos para verificar que siguen calzando.
TECHO_SMLV_VIS = 3.1
TECHO_SMLV_NO_VIS = 4.4

# Porcentaje de leads que deberian caer en CALIENTE. Es una decision de
# capacidad del equipo comercial, no una propiedad de los datos: cuantos leads
# puede atender el equipo por dia. Los umbrales de abajo salen de aplicar este
# porcentaje sobre la distribucion real (scripts/calibrar_scoring.py).
PCT_OBJETIVO_CALIENTE = 0.12
PCT_OBJETIVO_TIBIO = 0.38  # el 38% siguiente; el resto queda FRIO (nutricion)

# Ingreso supuesto, en pesos, para un lead sin registro que dice a que se
# dedica pero no cuanto gana. Sin esto el ingreso entra en 0 y "no sabemos"
# termina puntuando igual que "no gana nada", que es justo lo que el reto pide
# evitar ("valida, o infiere razonablemente, capacidad de compra"). Los valores
# son la mediana real de cada grupo en la base de usuarios; se recalculan con
# scripts/calibrar_scoring.py. Es un supuesto explicito, y como tal queda
# escrito en las razones del score para que el asesor lo vea.
INGRESO_SUPUESTO_POR_SITUACION = {
    "empleado_formal": 4_377_262,
    "independiente": 4_377_262,
    "desempleado": 2_626_358,
}

# Umbrales de corte del score, calculados con scripts/calibrar_scoring.py
# sobre los 3.449 usuarios de la base (percentiles 88 y 50). Recalibrar si
# cambia la base o los porcentajes objetivo de arriba.
UMBRAL_CALIENTE = 53.6
UMBRAL_TIBIO = 29.1
