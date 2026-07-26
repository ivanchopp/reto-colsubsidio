"""Carga y consulta de las fuentes de datos: usuarios, subsidios y catalogo
de proyectos, todo almacenado en Supabase/Postgres (RECURSOS/sql/schema.sql).
Las tablas se pueden ver y editar directamente desde el Table Editor de
Supabase; cargar_* cachea en memoria por proceso (se refresca al reiniciar
el servidor), igual que antes cuando la fuente era el Excel local."""
from functools import lru_cache

import pandas as pd

from app import db

SQL_USUARIOS = """
    select
        documento as "Documento",
        nombre as "Nombre",
        edad as "Edad",
        correo as "Correo",
        telefono as "Telefono",
        direccion as "Dirección",
        ciudad as "Ciudad",
        afiliado_colsubsidio as "Afiliado a colsubsidio",
        estado_vivienda_propia as "Estado de vivienda propia",
        suscripciones_actuales as "Suscripciones actuales",
        estado_laboral as "Estado laboral",
        fecha_inicio_labores as "Fecha de inicio de labores",
        tipo_contrato as "Tipo de contrato",
        rango_salarial as "Rango salarial",
        ha_pedido_subsidios as "Ha pedido subsidios",
        reportado_data_credito as "Reportado en data crédito"
    from usuarios
"""

SQL_SUBSIDIOS = """
    select
        subsidio as "Subsidio",
        requisitos_salariales_smmlv as "Requisitos Salariales (SMMLV)",
        permite_subsidios_anteriores as "¿Permite Subsidios Anteriores?",
        permite_vivienda_propia as "¿Permite Tener Vivienda Propia?",
        situacion_laboral_riesgo as "¿Situación Laboral es Riesgo?"
    from subsidios
"""

SQL_PROYECTOS = "select slug, data from proyectos order by slug"


@lru_cache(maxsize=1)
def cargar_usuarios() -> pd.DataFrame:
    df = pd.read_sql(SQL_USUARIOS, db.get_engine()).copy()
    # asignacion de columna completa (no .loc): el telefono pasa de numerico a
    # texto, y .loc conserva el dtype original en vez de reemplazarlo
    df["Telefono"] = df["Telefono"].astype(str).str.replace(r"\D", "", regex=True)
    return df


@lru_cache(maxsize=1)
def cargar_subsidios() -> pd.DataFrame:
    return pd.read_sql(SQL_SUBSIDIOS, db.get_engine())


def _normalizar_proyecto_real(brochure: dict) -> dict:
    """Convierte un brochure-inmobiliario-v2 (tabla proyectos, columna data)
    a la forma plana que usa el recomendador, conservando el contenido
    verificado (bot.argumentos_venta, resumen, perfil_comprador) para que el
    agente pueda explicar la recomendacion con datos reales."""
    proyecto = brochure.get("proyecto", {})
    ubicacion = brochure.get("ubicacion", {})
    financiacion = brochure.get("financiacion", {})
    bot_info = brochure.get("bot", {})

    # OJO: proyecto.tipo es el TIPO DE INMUEBLE (Apartamentos, Apartaestudios,
    # Casas...), no la clasificacion VIS/No VIS. Esa vive en
    # financiacion.clasificacion_vivienda -- usar proyecto.tipo aqui por error
    # hacia que projects reales quedaran con segmento_poblacional="Apartamentos"
    # y nunca hicieran match de segmento en el recomendador.
    segmento = financiacion.get("clasificacion_vivienda")
    if not segmento:
        # sin clasificacion explicita: si aplica subsidio, en la practica
        # de Colsubsidio casi siempre corresponde a segmento VIS
        segmento = "VIS" if financiacion.get("aplica_subsidio") else "No VIS"

    # los 2 brochures mas viejos (pamplona-maipore, versalles) usan un
    # esquema previo donde proyecto.tipo guardaba el segmento (VIS/No VIS)
    # en vez del tipo de inmueble -- se descarta si parece un segmento
    tipo_inmueble = proyecto.get("tipo")
    if tipo_inmueble and _normaliza(tipo_inmueble) in {"vis", "no vis", "vip"}:
        tipo_inmueble = None

    return {
        "nombre_proyecto": proyecto.get("nombre", brochure.get("slug", "")),
        "ciudad": ubicacion.get("ciudad", ""),
        "segmento_poblacional": segmento,
        "categoria_dominante": tipo_inmueble or "Apartamento",
        "etapa_actual": proyecto.get("estado_entrega", ""),
        "precio_promedio_millones_cop": None,  # se pacta en SMMLV al escriturar, no hay COP fijo
        "tasa_desistimiento_pct": None,  # sin historico propio
        "promedio_grupo_familiar": None,
        "amenities": brochure.get("amenities", []),
        "fuente": "real",
        "nota_financiacion": financiacion.get("nota", ""),
        "tipologias": brochure.get("tipologias", []),
        "lugares_cercanos": brochure.get("lugares_cercanos", {}),
        "resumen": bot_info.get("resumen", ""),
        "perfil_comprador": bot_info.get("perfil_comprador", ""),
        "argumentos_venta": bot_info.get("argumentos_venta", []),
        "brochure_url": brochure.get("fuente", {}).get("flipbook_url", ""),
    }


def _normaliza(texto: str) -> str:
    import unicodedata

    if texto is None:
        return ""
    texto = str(texto).strip()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return texto.lower()


@lru_cache(maxsize=1)
def cargar_proyectos_reales() -> list[dict]:
    import json

    df = pd.read_sql(SQL_PROYECTOS, db.get_engine())
    proyectos = []
    for _, fila in df.iterrows():
        brochure = fila["data"]
        if isinstance(brochure, str):
            brochure = json.loads(brochure)
        if brochure.get("_tipo_documento") == "portafolio":
            # documento agregador (portafolio/revista con varios proyectos
            # adentro), no es un proyecto individual recomendable
            continue
        proyectos.append(_normalizar_proyecto_real(brochure))
    return proyectos


def cargar_catalogo() -> list[dict]:
    return cargar_proyectos_reales()


def buscar_usuario_por_telefono(telefono: str) -> dict | None:
    telefono_limpio = "".join(ch for ch in str(telefono) if ch.isdigit())
    # acepta que el usuario escriba con o sin indicativo +57
    if telefono_limpio.startswith("57") and len(telefono_limpio) > 10:
        telefono_limpio = telefono_limpio[-10:]

    df = cargar_usuarios()
    coincidencias = df[df["Telefono"] == telefono_limpio]
    if coincidencias.empty:
        return None
    return coincidencias.iloc[0].to_dict()


def peers_con_perfil_similar(usuario: dict) -> pd.DataFrame:
    """Usuarios con Rango salarial + Estado laboral + Afiliacion iguales al
    usuario dado (excluyendolo a el mismo). Es la base del 'perfilamiento
    inteligente': comparar contra el comportamiento de otros usuarios con
    las mismas caracteristicas."""
    df = cargar_usuarios()
    mismo_perfil = (
        (df["Rango salarial"] == usuario.get("Rango salarial"))
        & (df["Estado laboral"] == usuario.get("Estado laboral"))
        & (df["Afiliado a colsubsidio"] == usuario.get("Afiliado a colsubsidio"))
    )
    peers = df[mismo_perfil]
    if "Documento" in usuario:
        peers = peers[peers["Documento"] != usuario.get("Documento")]
    return peers


@lru_cache(maxsize=1)
def tasa_base_conversion() -> float:
    """Porcentaje de TODA la base que termino 'Con vivienda propia'. Es la
    linea de base contra la que se mide un grupo de peers: una conversion del
    30% no dice nada por si sola, dice mucho si el promedio general es 15% y
    poco si es 45%."""
    df = cargar_usuarios()
    if df.empty:
        return 0.0
    return float((df["Estado de vivienda propia"] == "Con vivienda propia").mean() * 100)
