"""Pruebas de main._lead_payload -- mapea una Sesion en memoria al shape que
espera leads_store.upsert_lead. Sin DB, sin HTTP: se construye la Sesion a
mano y se llama la funcion directo."""
from app import config, conversation, main, scoring, subsidios


def _sesion_base(**overrides):
    base = dict(id="abc-123", telefono="3001234567", fase="aspiracional")
    base.update(overrides)
    return conversation.Sesion(**base)


def test_usuario_registrado_con_score():
    resultado = scoring.ResultadoScoring(
        score=71.3,
        segmento_lead="CALIENTE",
        project_segment="No VIS",
        razones=["Ingreso estimado 5.0 SMLV -> segmento No VIS, aporte base 70.0 pts"],
        peer_stats={"total_peers": 4, "pct_con_vivienda_propia": 50.0},
        subsidios_elegibles=[subsidios.Subsidio(nombre="Mi Casa Ya", requisito_salarial_texto="De 0 a 4 SMMLV")],
        contribuciones=[{"etiqueta": "Reglas", "valor": 42.8, "peso": 0.6, "categoria": "reglas"}],
    )
    sesion = _sesion_base(
        usuario={"Nombre": "Carlos Ramírez", "Ciudad": "Bogotá", "Documento": 123456789},
        resultado_scoring=resultado,
        fase="cierre",
        finalizada=True,
        interaccion_cerrada=True,
        enviado_al_asesor=True,
    )

    payload = main._lead_payload(sesion)

    assert payload["session_id"] == "abc-123"
    assert payload["nombre"] == "Carlos Ramírez"
    assert payload["ciudad"] == "Bogotá"
    assert payload["usuario_registrado"] is True
    assert payload["documento"] == 123456789
    assert payload["score"] == 71.3
    assert payload["segmento_lead"] == "CALIENTE"
    assert payload["scoring_version"] == config.SCORING_VERSION
    assert payload["subsidios_elegibles"] == [{"nombre": "Mi Casa Ya", "requisito_salarial_texto": "De 0 a 4 SMMLV"}]
    assert payload["contribuciones"] == resultado.contribuciones
    assert payload["fase"] == "cierre"
    assert payload["finalizada"] is True
    assert payload["interaccion_cerrada"] is True
    assert payload["enviado_al_asesor"] is True


def test_usuario_no_registrado_sin_score_todavia():
    sesion = _sesion_base(
        usuario=None,
        datos_declarados_no_registrado="Soy Ana, vivo en Bogotá",
        fase="captura_basica",
    )

    payload = main._lead_payload(sesion)

    assert payload["usuario_registrado"] is False
    assert payload["nombre"] == "Soy Ana, vivo en Bogotá"
    assert payload["ciudad"] is None
    assert payload["documento"] is None
    assert payload["score"] is None
    assert payload["segmento_lead"] is None
    assert payload["scoring_version"] is None
    assert payload["contribuciones"] is None


def test_usuario_no_registrado_con_score_fijo_al_cerrar():
    resultado = scoring.calcular_score_no_registrado()
    sesion = _sesion_base(
        usuario=None,
        datos_declarados_no_registrado="Soy Ana, vivo en Bogotá",
        resultado_scoring=resultado,
        fase="cierre",
        finalizada=True,
        interaccion_cerrada=True,
    )

    payload = main._lead_payload(sesion)

    assert payload["score"] == scoring.SCORE_NO_REGISTRADO
    assert payload["segmento_lead"] == "FRIO"
    assert payload["scoring_version"] == config.SCORING_VERSION
    assert payload["contribuciones"] is None
    assert payload["subsidios_elegibles"] == []
