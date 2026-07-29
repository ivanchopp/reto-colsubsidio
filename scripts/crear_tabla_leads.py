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
    "create index if not exists idx_leads_origen on leads (origen);",
]

# Columnas agregadas despues de la creacion original de la tabla. Se aplican
# con "add column if not exists" para que este script siga siendo idempotente
# y seguro de correr sobre una tabla que ya tiene datos: nunca borra ni
# reescribe filas existentes, solo agrega la columna con su default.
COLUMNAS_NUEVAS = [
    # canal por el que entro el lead (meta, google, whatsapp, organico...):
    # permite comparar volumen contra calidad por fuente de pauta
    "alter table leads add column if not exists origen text not null default 'organico';",
    # afiliacion a Colsubsidio, necesaria para el cupo agregado de la regla
    # 90/10 en el panel del asesor
    "alter table leads add column if not exists afiliado boolean;",
    # que le falta concretamente a un lead frio para poder comprar (flujo de
    # nutricion, ver app/nutricion.py)
    "alter table leads add column if not exists bloqueantes jsonb;",
    # variables de calificacion extraidas de la conversacion
    "alter table leads add column if not exists datos_declarados jsonb;",
    # config.SCORING_VERSION vigente al momento del calculo: permite saber
    # con que pesos/umbrales salio un score historico despues de que
    # config.py haya cambiado (ver app/scoring.py)
    "alter table leads add column if not exists scoring_version text;",
    # codigo estable por cada entrada de razones (ver app/scoring.py RC_*):
    # permite analitica agregada (que razon rechaza mas leads, por canal o
    # ciudad) sin parsear texto libre
    "alter table leads add column if not exists codigos_razones jsonb;",
    # discrepancias entre lo declarado en la conversacion y la base
    # (ver app/scoring._detectar_conflictos): informativo, no cambia el
    # score, pero le da al asesor una senal de que revisar
    "alter table leads add column if not exists conflictos jsonb;",
]


def main():
    engine = db.get_engine()
    with engine.begin() as conn:
        conn.execute(text(DDL))
        for columna in COLUMNAS_NUEVAS:
            conn.execute(text(columna))
        for indice in INDICES:
            conn.execute(text(indice))
    print("Listo. Tabla 'leads' creada (o ya existia). Verifica en el Table Editor de Supabase.")


if __name__ == "__main__":
    main()
