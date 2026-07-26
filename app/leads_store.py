"""Persistencia de leads (sesiones de chat) para el panel del asesor
comercial. A diferencia de data_store.py (catalogo estatico, cacheado con
@lru_cache), esta tabla se escribe constantemente durante cada conversacion
-- ninguna funcion de aqui cachea resultados."""
import json

from sqlalchemy import text

from app import config, db


# Regla 90/10: como maximo el 10% de las ventas puede ir a no afiliados.
PCT_MAXIMO_NO_AFILIADOS = 0.10

# Canales por los que puede entrar un lead. "organico" es la referencia del
# reto: los leads propios convierten mejor que los de pauta.
ORIGENES_VALIDOS = ("meta", "google", "whatsapp", "organico", "contact_center")
ORIGEN_POR_DEFECTO = "organico"


def normalizar_origen(valor: str | None) -> str:
    """El origen llega de un parametro de URL (utm-like), asi que puede venir
    con cualquier cosa. Se acota al vocabulario conocido en vez de guardar
    texto libre que despues no se puede agrupar."""
    normalizado = (valor or "").strip().lower()
    return normalizado if normalizado in ORIGENES_VALIDOS else ORIGEN_POR_DEFECTO


def _es_afiliado(lead: dict) -> bool:
    """Un lead sin registro no se puede contar como afiliado: no hay con que
    verificarlo, y frente a una cuota regulatoria conviene el criterio
    conservador."""
    if not lead.get("usuario_registrado"):
        return False
    return lead.get("afiliado") is True


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
    origen: str,
    afiliado: bool | None,
    bloqueantes: list[dict] | None,
    datos_declarados: dict | None,
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
                    interaccion_cerrada, enviado_al_asesor,
                    origen, afiliado, bloqueantes, datos_declarados
                ) values (
                    :session_id, :telefono, :nombre, :ciudad, :usuario_registrado, :documento,
                    :score, :segmento_lead, :project_segment,
                    cast(:razones as jsonb), cast(:peer_stats as jsonb),
                    cast(:subsidios_elegibles as jsonb), cast(:contribuciones as jsonb),
                    :fase, :finalizada, :interaccion_cerrada, :enviado_al_asesor,
                    :origen, :afiliado,
                    cast(:bloqueantes as jsonb), cast(:datos_declarados as jsonb)
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
                    origen = excluded.origen,
                    afiliado = excluded.afiliado,
                    bloqueantes = excluded.bloqueantes,
                    datos_declarados = excluded.datos_declarados,
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
                "origen": normalizar_origen(origen),
                "afiliado": afiliado,
                "bloqueantes": _a_jsonb(bloqueantes),
                "datos_declarados": _a_jsonb(datos_declarados),
            },
        )


_CAMPOS_JSONB = (
    "razones", "peer_stats", "subsidios_elegibles", "contribuciones",
    "bloqueantes", "datos_declarados",
)


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
    por_origen: dict[str, int] = {}
    for lead in leads:
        segmento = lead.get("segmento_lead") or "SIN_DATOS"
        por_segmento[segmento] = por_segmento.get(segmento, 0) + 1
        origen = lead.get("origen") or "desconocido"
        por_origen[origen] = por_origen.get(origen, 0) + 1
    return {
        "total": len(leads),
        "por_segmento": por_segmento,
        "por_origen": por_origen,
        "cuota_90_10": calcular_cuota_90_10(leads),
        "calidad_por_origen": calcular_calidad_por_origen(leads),
        "filtrados": calcular_filtrados(leads),
    }


def calcular_filtrados(leads: list[dict]) -> dict:
    """Leads que terminaron su conversacion y NO se derivaron al asesor.

    Es la metrica que resume para que existe el proyecto: cada uno de estos es
    tiempo que el equipo comercial no gasto persiguiendo a alguien que hoy no
    puede comprar, y que igual queda registrado con su plan de nutricion para
    retomarlo. Solo se cuentan conversaciones cerradas: una en curso todavia
    puede cambiar de segmento."""
    cerrados = [l for l in leads if l.get("interaccion_cerrada")]
    filtrados = [l for l in cerrados if l.get("segmento_lead") not in config.SEGMENTOS_DERIVABLES]
    return {
        "cerrados": len(cerrados),
        "filtrados": len(filtrados),
        "derivados": len(cerrados) - len(filtrados),
        "pct_filtrados": round(len(filtrados) / len(cerrados) * 100, 1) if cerrados else 0.0,
    }


def calcular_cuota_90_10(leads: list[dict]) -> dict:
    """Estado del cupo regulatorio: solo el 10% de las ventas de vivienda de
    Colsubsidio puede ir a no afiliados.

    El scoring ya penaliza al no afiliado lead por lead, pero la regla es una
    cuota agregada, no un descuento individual. Sin esta vista el asesor no
    tiene forma de saber cuanto cupo le queda: puede estar trabajando cinco no
    afiliados calientes cuando solo va a poder cerrar uno.

    Se cuentan unicamente los leads que llegarian al asesor (CALIENTE), que es
    donde el cupo se consume de verdad; un no afiliado frio no ocupa cupo.
    """
    derivables = [l for l in leads if l.get("segmento_lead") == "CALIENTE"]
    total = len(derivables)
    no_afiliados = sum(1 for l in derivables if not _es_afiliado(l))
    afiliados = total - no_afiliados

    # se redondea en vez de truncar: con 8 derivables el 10% es 0.8, y
    # truncar daria un cupo de 0, marcando "excedido" apenas aparece un solo
    # no afiliado. La regla aplica sobre las ventas de un periodo, no sobre
    # los leads de una tarde, asi que a volumen bajo el redondeo refleja mejor
    # la intencion sin dejar de ser estricto a escala.
    cupo_no_afiliados = round(total * PCT_MAXIMO_NO_AFILIADOS) if total else 0
    return {
        "derivables": total,
        "afiliados": afiliados,
        "no_afiliados": no_afiliados,
        "cupo_no_afiliados": cupo_no_afiliados,
        "cupo_disponible": max(0, cupo_no_afiliados - no_afiliados),
        "excedido": no_afiliados > cupo_no_afiliados,
        "pct_no_afiliados": round(no_afiliados / total * 100, 1) if total else 0.0,
    }


def calcular_calidad_por_origen(leads: list[dict]) -> list[dict]:
    """Cuantos leads trae cada canal y que proporcion llega a CALIENTE.

    Es la metrica con la que abre el reto: la pauta paga trae volumen pero
    convierte peor que el organico, y sin medirlo por canal no se puede
    decidir donde recortar. Ordenado por volumen para que el canal mas caro
    quede arriba."""
    por_origen: dict[str, dict] = {}
    for lead in leads:
        origen = lead.get("origen") or "desconocido"
        acumulado = por_origen.setdefault(origen, {"origen": origen, "total": 0, "calientes": 0})
        acumulado["total"] += 1
        if lead.get("segmento_lead") == "CALIENTE":
            acumulado["calientes"] += 1

    for acumulado in por_origen.values():
        acumulado["pct_calientes"] = round(acumulado["calientes"] / acumulado["total"] * 100, 1)
    return sorted(por_origen.values(), key=lambda o: -o["total"])
