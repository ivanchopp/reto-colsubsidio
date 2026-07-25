"""Migra los datos locales de RECURSOS/ (Excel de usuarios y subsidios, JSON
de proyectos) a las tablas de Supabase creadas por RECURSOS/sql/schema.sql.

Uso:
    1. Crea el proyecto en supabase.com y corre RECURSOS/sql/schema.sql en su SQL Editor.
    2. Copia la cadena de conexion (Project Settings > Database > Connection
       string, formato SQLAlchemy) a SUPABASE_DB_URL en tu .env.
    3. Corre este script: python scripts/migrar_a_supabase.py

Es seguro correrlo varias veces: cada tabla se vacia (truncate) antes de
volver a cargarse, asi que siempre queda igual al contenido de RECURSOS/.
"""
import json
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import config, db  # noqa: E402

COLUMNAS_USUARIOS = {
    "Documento": "documento",
    "Nombre": "nombre",
    "Edad": "edad",
    "Correo": "correo",
    "Número teléfono": "telefono",
    "Dirección": "direccion",
    "Ciudad": "ciudad",
    "Afiliado a colsubsidio": "afiliado_colsubsidio",
    "Estado vivienda propia": "estado_vivienda_propia",
    "Suscripciones actuales": "suscripciones_actuales",
    "Estado laboral": "estado_laboral",
    "Fecha inicio labores": "fecha_inicio_labores",
    "Tipo contrato": "tipo_contrato",
    "Rango salarial": "rango_salarial",
    "Ha pedido subsidios": "ha_pedido_subsidios",
    "Reportado en data crédito": "reportado_data_credito",
}

COLUMNAS_SUBSIDIOS = {
    "Subsidio": "subsidio",
    "Requisitos Salariales (SMMLV)": "requisitos_salariales_smmlv",
    "¿Permite Subsidios Anteriores?": "permite_subsidios_anteriores",
    "¿Permite Tener Vivienda Propia?": "permite_vivienda_propia",
    "¿Situación Laboral es Riesgo?": "situacion_laboral_riesgo",
}


def migrar_usuarios(engine):
    df = pd.read_excel(config.EXCEL_USUARIOS)
    df = df.rename(columns=COLUMNAS_USUARIOS)[list(COLUMNAS_USUARIOS.values())]
    df["telefono"] = (
        df["telefono"].astype("Int64").astype(str).str.replace(r"\D", "", regex=True)
    )
    # el Excel mezcla fechas reales y texto en esta columna; se normaliza a
    # 'YYYY-MM-DD' para que quede consistente en la tabla (columna text)
    df["fecha_inicio_labores"] = (
        pd.to_datetime(df["fecha_inicio_labores"], errors="coerce", dayfirst=False)
        .dt.strftime("%Y-%m-%d")
    )
    with engine.begin() as conn:
        conn.execute(text("truncate table usuarios"))
        df.to_sql("usuarios", conn, if_exists="append", index=False)
    print(f"usuarios: {len(df)} filas cargadas")


def migrar_subsidios(engine):
    df = pd.read_excel(config.EXCEL_SUBSIDIOS)
    df = df.rename(columns=COLUMNAS_SUBSIDIOS)[list(COLUMNAS_SUBSIDIOS.values())]
    with engine.begin() as conn:
        conn.execute(text("truncate table subsidios"))
        df.to_sql("subsidios", conn, if_exists="append", index=False)
    print(f"subsidios: {len(df)} filas cargadas")


def migrar_proyectos(engine):
    filas = []
    for ruta in sorted(config.PROYECTOS_REALES_DIR.glob("*.json")):
        with open(ruta, encoding="utf-8") as f:
            brochure = json.load(f)
        filas.append({"slug": ruta.stem, "data": json.dumps(brochure, ensure_ascii=False)})

    with engine.begin() as conn:
        conn.execute(text("truncate table proyectos"))
        for fila in filas:
            conn.execute(
                text("insert into proyectos (slug, data) values (:slug, cast(:data as jsonb))"),
                fila,
            )
    print(f"proyectos: {len(filas)} filas cargadas")


def main():
    engine = db.get_engine()
    migrar_usuarios(engine)
    migrar_subsidios(engine)
    migrar_proyectos(engine)
    print("Listo. Verifica los datos en el Table Editor de Supabase.")


if __name__ == "__main__":
    main()
