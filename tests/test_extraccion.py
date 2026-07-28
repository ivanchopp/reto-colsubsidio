"""Tests de app/extraccion.py: la traduccion de lo que dice el usuario a las
variables que consume el scoring.

No llaman al LLM real (seria lento y no determinista): se estubea
llm_client.extraer_json y se verifica la capa de validacion, que es donde
esta el riesgo. Un LLM puede devolver 'no se', 'Empleado', un string donde
se esperaba un booleano o un JSON con claves de mas; nada de eso debe llegar
al motor de scoring.
"""
import pytest

from app import extraccion, llm_client


@pytest.fixture(autouse=True)
def metricas_extraccion_limpias():
    """Los contadores de llm_client.metricas_extraccion son estado global de
    proceso: sin resetearlos, el orden en que corren los tests cambiaria el
    resultado de las aserciones de abajo."""
    llm_client._resetear_metricas_extraccion()
    yield
    llm_client._resetear_metricas_extraccion()


@pytest.fixture
def respuesta_llm(monkeypatch):
    def _set(datos):
        monkeypatch.setattr(llm_client, "extraer_json", lambda instruccion: datos)

    return _set


def test_extrae_los_campos_validos(respuesta_llm):
    respuesta_llm(
        {
            "empresa": "Bancolombia",
            "situacion_laboral": "empleado_formal",
            "ahorro_cuota_inicial": True,
            "estructura_familiar": "Nuclear Integrada",
            "tiene_vivienda": False,
            "ingresos_mensuales_aprox": 4500000,
        }
    )
    datos = extraccion.extraer_de_mensaje("trabajo en Bancolombia", "empresa")

    assert datos["empresa"] == "Bancolombia"
    assert datos["situacion_laboral"] == "empleado_formal"
    assert datos["ahorro_cuota_inicial"] is True
    assert datos["estructura_familiar"] == "Nuclear Integrada"
    assert datos["tiene_vivienda"] is False
    assert datos["ingresos_mensuales_aprox"] == 4500000.0


def test_descarta_valores_fuera_del_vocabulario(respuesta_llm):
    respuesta_llm({"situacion_laboral": "Empleado", "estructura_familiar": "Pareja joven"})
    datos = extraccion.extraer_de_mensaje("algo", "empresa")

    assert "situacion_laboral" not in datos
    assert "estructura_familiar" not in datos


def test_descarta_booleanos_que_no_son_booleanos(respuesta_llm):
    respuesta_llm({"ahorro_cuota_inicial": "si", "tiene_vivienda": 1})
    datos = extraccion.extraer_de_mensaje("algo", "ahorro")

    assert datos == {}


def test_ignora_nulls_y_claves_desconocidas(respuesta_llm):
    respuesta_llm(
        {"empresa": None, "situacion_laboral": None, "color_favorito": "azul", "empresa_extra": "x"}
    )
    assert extraccion.extraer_de_mensaje("algo", "empresa") == {}


def test_descarta_ingreso_no_positivo_o_booleano(respuesta_llm):
    respuesta_llm({"ingresos_mensuales_aprox": 0})
    assert extraccion.extraer_de_mensaje("algo", "empresa") == {}

    # True es instancia de int en Python: no debe colarse como ingreso de 1 peso
    respuesta_llm({"ingresos_mensuales_aprox": True})
    assert extraccion.extraer_de_mensaje("algo", "empresa") == {}


def test_mensaje_vacio_no_llama_al_llm(monkeypatch):
    def explotar(instruccion):
        raise AssertionError("no deberia llamarse al LLM con un mensaje vacio")

    monkeypatch.setattr(llm_client, "extraer_json", explotar)
    assert extraccion.extraer_de_mensaje("   ", "empresa") == {}


def test_extraccion_fallida_no_rompe(respuesta_llm):
    """Si el proveedor falla, extraer_json devuelve {} y el flujo sigue sin
    los datos declarados en vez de tumbar la conversacion."""
    respuesta_llm({})
    assert extraccion.extraer_de_mensaje("trabajo en algo", "empresa") == {}


def test_resumir_para_asesor_es_legible():
    lineas = extraccion.resumir_para_asesor(
        {"situacion_laboral": "empleado_formal", "ahorro_cuota_inicial": True, "tiene_vivienda": False}
    )
    texto = " | ".join(lineas)

    assert "empleado formal" in texto
    assert "ahorro" in texto.lower()
    assert "No tiene vivienda propia" in texto


def test_resumir_sin_datos_devuelve_vacio():
    assert extraccion.resumir_para_asesor({}) == []


# ---------------------------------------------------------------------
# Parseo de la respuesta cruda del LLM (llm_client.extraer_json)
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "crudo, esperado, es_fallo",
    [
        ('{"empresa": "Acme"}', {"empresa": "Acme"}, False),
        ('```json\n{"empresa": "Acme"}\n```', {"empresa": "Acme"}, False),
        ('Claro, aqui tienes: {"empresa": "Acme"}', {"empresa": "Acme"}, False),
        ("no encontre datos", {}, True),
        ("", {}, True),
        ('{"roto": ', {}, True),
        ('["no", "es", "objeto"]', {}, True),
    ],
)
def test_extraer_json_tolera_respuestas_sucias(monkeypatch, crudo, esperado, es_fallo):
    monkeypatch.setattr(
        llm_client, "generar_respuesta", lambda system, historial, instruccion: crudo
    )
    assert llm_client.extraer_json("da algo") == esperado

    metricas = llm_client.metricas_extraccion()
    assert metricas["intentos"] == 1
    assert metricas["fallos"] == (1 if es_fallo else 0)


def test_extraer_json_devuelve_vacio_si_el_proveedor_falla(monkeypatch):
    monkeypatch.setattr(
        llm_client,
        "generar_respuesta",
        lambda system, historial, instruccion: llm_client.MENSAJE_FALLBACK,
    )
    assert llm_client.extraer_json("da algo") == {}
    assert llm_client.metricas_extraccion() == {"intentos": 1, "fallos": 1, "tasa_fallos_pct": 100.0}


# ---------------------------------------------------------------------
# metricas_extraccion: tasa de fallos monitoreada (ver /api/asesor/resumen-dia)
# ---------------------------------------------------------------------

def test_metricas_extraccion_arranca_en_cero():
    assert llm_client.metricas_extraccion() == {"intentos": 0, "fallos": 0, "tasa_fallos_pct": 0.0}


def test_metricas_extraccion_calcula_la_tasa_de_fallos(monkeypatch):
    respuestas = iter(['{"empresa": "Acme"}', "no encontre datos", "tampoco esta vez"])
    monkeypatch.setattr(
        llm_client, "generar_respuesta", lambda system, historial, instruccion: next(respuestas)
    )

    for _ in range(3):
        llm_client.extraer_json("da algo")

    assert llm_client.metricas_extraccion() == {
        "intentos": 3,
        "fallos": 2,
        "tasa_fallos_pct": round(2 / 3 * 100, 1),
    }


def test_fallo_de_extraccion_queda_logueado(monkeypatch, caplog):
    monkeypatch.setattr(
        llm_client, "generar_respuesta", lambda system, historial, instruccion: "no hay json aqui"
    )
    with caplog.at_level("WARNING"):
        llm_client.extraer_json("da algo")

    assert any("fallo de extraccion" in r.message for r in caplog.records)
