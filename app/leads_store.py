"""Persistencia de leads (sesiones de chat) para el panel del asesor
comercial. A diferencia de data_store.py (catalogo estatico, cacheado con
@lru_cache), esta tabla se escribe constantemente durante cada conversacion
-- ninguna funcion de aqui cachea resultados."""
import json

from sqlalchemy import text

from app import db


def _a_jsonb(valor):
    return json.dumps(valor) if valor is not None else None


def _de_jsonb(valor):
    """El driver normalmente ya devuelve jsonb como list/dict de Python, pero
    se deja esta conversion defensiva por si llega como string (ver el mismo
    patron en data_store.cargar_proyectos_reales)."""
    if isinstance(valor, str):
        return json.loads(valor)
    return valor


def upsert_lead(
    *,
    session_id: str,
    telefono: str,
    nombre: str | None,
    ciudad: str | None,
    usuario_registrado: bool,
    documento: int | None,
    score: float | None,
    segmento_lead: str | None,
    project_segment: str | None,
    razones: list[str] | None,
    peer_stats: dict | None,
    subsidios_elegibles: list[dict] | None,
    contribuciones: list[dict] | None,
    fase: str,
    finalizada: bool,
    interaccion_cerrada: bool,
    enviado_al_asesor: bool,
) -> None:
    with db.get_engine().begin() as conn:
        conn.execute(
            text(
                """
                insert into leads (
                    session_id, telefono, nombre, ciudad, usuario_registrado, documento,
                    score, segmento_lead, project_segment, razones, peer_stats,
                    subsidios_elegibles, contribuciones, fase, finalizada,
                    interaccion_cerrada, enviado_al_asesor
                ) values (
                    :session_id, :telefono, :nombre, :ciudad, :usuario_registrado, :documento,
                    :score, :segmento_lead, :project_segment,
                    cast(:razones as jsonb), cast(:peer_stats as jsonb),
                    cast(:subsidios_elegibles as jsonb), cast(:contribuciones as jsonb),
                    :fase, :finalizada, :interaccion_cerrada, :enviado_al_asesor
                )
                on conflict (session_id) do update set
                    telefono = excluded.telefono,
                    nombre = excluded.nombre,
                    ciudad = excluded.ciudad,
                    usuario_registrado = excluded.usuario_registrado,
                    documento = excluded.documento,
                    score = excluded.score,
                    segmento_lead = excluded.segmento_lead,
                    project_segment = excluded.project_segment,
                    razones = excluded.razones,
                    peer_stats = excluded.peer_stats,
                    subsidios_elegibles = excluded.subsidios_elegibles,
                    contribuciones = excluded.contribuciones,
                    fase = excluded.fase,
                    finalizada = excluded.finalizada,
                    interaccion_cerrada = excluded.interaccion_cerrada,
                    enviado_al_asesor = excluded.enviado_al_asesor,
                    actualizado_en = now()
                """
            ),
            {
                "session_id": session_id,
                "telefono": telefono,
                "nombre": nombre,
                "ciudad": ciudad,
                "usuario_registrado": usuario_registrado,
                "documento": documento,
                "score": score,
                "segmento_lead": segmento_lead,
                "project_segment": project_segment,
                "razones": _a_jsonb(razones),
                "peer_stats": _a_jsonb(peer_stats),
                "subsidios_elegibles": _a_jsonb(subsidios_elegibles),
                "contribuciones": _a_jsonb(contribuciones),
                "fase": fase,
                "finalizada": finalizada,
                "interaccion_cerrada": interaccion_cerrada,
                "enviado_al_asesor": enviado_al_asesor,
            },
        )


_CAMPOS_JSONB = ("razones", "peer_stats", "subsidios_elegibles", "contribuciones")


def _fila_a_dict(fila) -> dict:
    datos = dict(fila)
    for campo in _CAMPOS_JSONB:
        datos[campo] = _de_jsonb(datos.get(campo))
    return datos


def listar_leads_hoy() -> list[dict]:
    """Leads creados en el dia calendario de Colombia (UTC-5 fijo, sin
    horario de verano -- por eso no hace falta manejar cambios de offset)."""
    with db.get_engine().begin() as conn:
        filas = conn.execute(
            text(
                """
                select * from leads
                where (creado_en at time zone 'America/Bogota')::date
                    = (now() at time zone 'America/Bogota')::date
                order by creado_en desc
                """
            )
        ).mappings().all()
    return [_fila_a_dict(f) for f in filas]


def obtener_lead(session_id: str) -> dict | None:
    with db.get_engine().begin() as conn:
        fila = conn.execute(
            text("select * from leads where session_id = :sid"),
            {"sid": session_id},
        ).mappings().first()
    return _fila_a_dict(fila) if fila else None


def calcular_stats(leads: list[dict]) -> dict:
    """Funcion pura (no toca la DB) para poder testearla sin base de datos."""
    por_segmento: dict[str, int] = {}
    for lead in leads:
        segmento = lead.get("segmento_lead") or "SIN_DATOS"
        por_segmento[segmento] = por_segmento.get(segmento, 0) + 1
    return {"total": len(leads), "por_segmento": por_segmento}
