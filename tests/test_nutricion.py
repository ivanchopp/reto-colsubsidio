"""Pruebas de app/nutricion.py: que le falta a un lead que hoy no puede
comprar. El reto pide identificar y nutrir a estos leads, no descartarlos, y
para eso el asesor necesita saber que destrabaria cada caso."""
import pytest

from app import nutricion, scoring


@pytest.fixture
def resultado(make_usuario):
    """El resultado del scoring no cambia los bloqueantes (se detectan sobre
    el perfil), pero la firma lo pide: se usa uno cualquiera."""
    return scoring.calcular_score(make_usuario())


def codigos(bloqueantes):
    return [b["codigo"] for b in bloqueantes]


def test_perfil_sano_no_tiene_bloqueantes(make_usuario, resultado):
    usuario = make_usuario()  # Empleado/Indefinido, afiliado, sin reportes
    assert nutricion.detectar_bloqueantes(usuario, resultado) == []


def test_detecta_reporte_en_centrales(make_usuario, resultado):
    usuario = make_usuario(**{"Reportado en data crédito": "Reportado"})
    assert "datacredito" in codigos(nutricion.detectar_bloqueantes(usuario, resultado))


def test_detecta_desempleo(make_usuario, resultado):
    usuario = make_usuario(**{"Estado laboral": "Desempleado"})
    assert "sin_empleo" in codigos(nutricion.detectar_bloqueantes(usuario, resultado))


def test_desempleo_y_informalidad_son_excluyentes(make_usuario, resultado):
    """Un desempleado no necesita ademas el consejo de formalizar ingresos:
    seria ruido sobre el bloqueante real."""
    usuario = make_usuario(**{"Estado laboral": "Desempleado"})
    detectados = codigos(nutricion.detectar_bloqueantes(usuario, resultado))

    assert "sin_empleo" in detectados
    assert "ingreso_informal" not in detectados


def test_detecta_ingreso_informal(make_usuario, resultado):
    usuario = make_usuario(
        **{"Estado laboral": "Independiente", "Tipo de contrato": "Obra y labor"}
    )
    assert "ingreso_informal" in codigos(nutricion.detectar_bloqueantes(usuario, resultado))


def test_detecta_no_afiliado(make_usuario, resultado):
    usuario = make_usuario(**{"Afiliado a colsubsidio": "No"})
    assert "no_afiliado" in codigos(nutricion.detectar_bloqueantes(usuario, resultado))


def test_ahorro_solo_es_bloqueante_si_lo_dijo_explicitamente(make_usuario, resultado):
    """No haber mencionado el ahorro no es lo mismo que no tenerlo."""
    usuario = make_usuario()

    sin_mencion = nutricion.detectar_bloqueantes(usuario, resultado, {})
    dijo_que_no = nutricion.detectar_bloqueantes(
        usuario, resultado, {"ahorro_cuota_inicial": False}
    )
    dijo_que_si = nutricion.detectar_bloqueantes(
        usuario, resultado, {"ahorro_cuota_inicial": True}
    )

    assert "sin_cuota_inicial" not in codigos(sin_mencion)
    assert "sin_cuota_inicial" in codigos(dijo_que_no)
    assert "sin_cuota_inicial" not in codigos(dijo_que_si)


def test_detecta_ingreso_insuficiente(make_usuario, resultado):
    usuario = make_usuario(**{"Rango salarial": "de 500.000 - 900.000"})
    assert "ingreso_insuficiente" in codigos(nutricion.detectar_bloqueantes(usuario, resultado))


def test_sin_dato_de_ingreso_no_se_marca_insuficiente(make_usuario, resultado):
    """Ingreso 0 significa 'no se sabe' (no se declaro ni esta en la base), no
    'gana cero'. Marcarlo como bloqueante seria inventar un diagnostico."""
    usuario = make_usuario(**{"Rango salarial": ""})
    assert "ingreso_insuficiente" not in codigos(nutricion.detectar_bloqueantes(usuario, resultado))


def test_bloqueantes_vienen_ordenados_por_prioridad(make_usuario, resultado):
    usuario = make_usuario(
        **{
            "Reportado en data crédito": "Reportado",
            "Estado laboral": "Desempleado",
            "Afiliado a colsubsidio": "No",
        }
    )
    bloqueantes = nutricion.detectar_bloqueantes(usuario, resultado)
    prioridades = [b["prioridad"] for b in bloqueantes]

    assert prioridades == sorted(prioridades)
    # el reporte en centrales es lo primero a resolver: sin eso no hay credito
    assert bloqueantes[0]["codigo"] == "datacredito"


def test_cada_bloqueante_trae_una_accion_concreta(make_usuario, resultado):
    usuario = make_usuario(
        **{"Estado laboral": "Desempleado", "Afiliado a colsubsidio": "No"}
    )
    for bloqueante in nutricion.detectar_bloqueantes(usuario, resultado):
        assert bloqueante["accion"].strip(), f"{bloqueante['codigo']} sin accion"
        assert bloqueante["titulo"].strip()


def test_plan_de_nutricion_toma_el_bloqueante_mas_prioritario(make_usuario, resultado):
    usuario = make_usuario(
        **{"Reportado en data crédito": "Reportado", "Afiliado a colsubsidio": "No"}
    )
    plan = nutricion.plan_de_nutricion(nutricion.detectar_bloqueantes(usuario, resultado))

    assert "centrales de riesgo" in plan.lower()


def test_plan_de_nutricion_sin_bloqueantes_es_none():
    assert nutricion.plan_de_nutricion([]) is None
