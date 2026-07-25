"""Conexion a la base de datos en la nube (Supabase / Postgres) que reemplaza
los Excel/JSON locales de RECURSOS/. El engine se crea de forma perezosa
(solo al primer query real) para que importar este modulo no falle si
SUPABASE_DB_URL todavia no esta configurada (ej. corriendo los tests)."""
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app import config


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    if not config.SUPABASE_DB_URL:
        raise RuntimeError(
            "SUPABASE_DB_URL no esta configurada. Define esa variable en .env "
            "con la cadena de conexion de tu proyecto de Supabase "
            "(Project Settings > Database > Connection string)."
        )
    return create_engine(config.SUPABASE_DB_URL, pool_pre_ping=True)
