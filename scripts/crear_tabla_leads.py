"""Crea la tabla `leads` en Supabase (panel del asesor comercial).

A diferencia de scripts/migrar_a_supabase.py, este script es puramente
aditivo: solo corre `create table if not exists` / `create index if not
exists` -- nunca hace truncate ni delete, porque `leads` es una tabla viva
que se llena en cada conversacion, no un catalogo estatico que se recarga
desde Excel/JSON.

Uso:
    python scripts/crear_tabla_leads.py

Es seguro correrlo varias veces (los "if not exists" lo hacen idempotente).
"""
import sys
from pathlib import Path

from sqlalchemy import text

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import db  # noqa: E402

DDL = """
create table if not exists leads (
    session_id uuid primary key,
    telefono text not null,
    nombre text,
    ciudad text,
    usuario_registrado boolean not null default false,
    documento bigint,
    score numeric(5,1),
    segmento_lead text,
    project_segment text,
    razones jsonb,
    peer_stats jsonb,
    subsidios_elegibles jsonb,
    contribuciones jsonb,
    fase text not null,
    finalizada boolean not null default false,
    interaccion_cerrada boolean not null default false,
    enviado_al_asesor boolean not null default false,
    creado_en timestamptz not null default now(),
    actualizado_en timestamptz not null default now()
);
"""

INDICES = [
    "create index if not exists idx_leads_creado_en on leads (creado_en desc);",
    "create index if not exists idx_leads_telefono on leads (telefono);",
]


def main():
    engine = db.get_engine()
    with engine.begin() as conn:
        conn.execute(text(DDL))
        for indice in INDICES:
            conn.execute(text(indice))
    print("Listo. Tabla 'leads' creada (o ya existia). Verifica en el Table Editor de Supabase.")


if __name__ == "__main__":
    main()
