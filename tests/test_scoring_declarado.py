"""Tests de la calificacion que aporta la conversacion (bloque 2).

Cubren las dos features del buyer_persona_scoring_schema.json que hasta ahora
no se usaban -- family_structure y savings_fna_cesantias -- y el caso de los
leads sin registro, que antes recibian todos la misma penalizacion fija de 15
sin importar lo que contaran.
"""
import pytest

from app import config, scoring


# ---------------------------------------------------------------------
# savings_fna_cesantias (liquidez declarada)
# ---------------------------------------------------------------------

def test_ahorro_declarado_suma_al_score(make_usuario):
    usuario = make_usuario()
    sin_ahorro = scoring.calcular_score(usuario)
    con_ahorro = scoring.calcular_score(usuario, datos_declarados={"ahorro_cuota_inicial": True})

    assert con_ahorro.score == pytest.approx(
        sin_ahorro.score + scoring.BONO_AHORRO_CUOTA_INICIAL
    )
    assert any("ahorro" in r.lower() for r in con_ahorro.razones)


def test_declarar_que_no_hay_ahorro_no_penaliza(make_usuario):
    """No tener cuota inicial no descalifica: mucha gente compra con credito y
    subsidio. Solo deja de sumar."""
    usuario = make_usuario()
    sin_dato = scoring.calcular_score(usuario)
    declara_que_no = scoring.calcular_score(
        usuario, datos_declarados={"ahorro_cuota_inicial": False}
    )

    assert declara_que_no.score == pytest.approx(sin_dato.score)


def test_ahorro_aparece_en_las_contribuciones(make_usuario):
    resultado = scoring.calcular_score(
        make_usuario(), datos_declarados={"ahorro_cuota_inicial": True}
    )
    categorias = [c["categoria"] for c in resultado.contribuciones]
    assert "declarado" in categorias


# ---------------------------------------------------------------------
# ahorros verificado (usuarios.ahorros): dato duro de la base, distinto
# de savings_fna_cesantias declarado en la conversacion
# ---------------------------------------------------------------------

def test_ahorro_verificado_al_techo_suma_el_bono_maximo(make_usuario):
    usuario = make_usuario(ahorros=config.AHORRO_VERIFICADO_TECHO_COP)
    sin_ahorro = scoring.calcular_score(make_usuario())
    con_ahorro = scoring.calcular_score(usuario)

    assert con_ahorro.score == pytest.approx(
        sin_ahorro.score + scoring.BONO_AHORRO_VERIFICADO_MAX
    )
    assert any("ahorro verificado" in r.lower() for r in con_ahorro.razones)


def test_ahorro_verificado_por_encima_del_techo_no_suma_de_mas(make_usuario):
    al_techo = scoring.calcular_score(make_usuario(ahorros=config.AHORRO_VERIFICADO_TECHO_COP))
    muy_por_encima = scoring.calcular_score(
        make_usuario(ahorros=config.AHORRO_VERIFICADO_TECHO_COP * 3)
    )
    assert muy_por_encima.score == pytest.approx(al_techo.score)


def test_ahorro_verificado_escala_con_el_monto(make_usuario):
    usuario = make_usuario(ahorros=config.AHORRO_VERIFICADO_TECHO_COP / 2)
    sin_ahorro = scoring.calcular_score(make_usuario())
    con_ahorro = scoring.calcular_score(usuario)

    assert con_ahorro.score == pytest.approx(
        sin_ahorro.score + scoring.BONO_AHORRO_VERIFICADO_MAX / 2
    )


def test_ahorro_verificado_tiene_prioridad_sobre_el_declarado(make_usuario):
    """Si el usuario esta registrado con ahorros verificados, lo declarado en
    la conversacion no debe sumar aparte: seria contar la misma senal dos
    veces con distinta confianza."""
    usuario = make_usuario(ahorros=config.AHORRO_VERIFICADO_TECHO_COP)
    resultado = scoring.calcular_score(
        usuario, datos_declarados={"ahorro_cuota_inicial": True}
    )

    assert resultado.score == pytest.approx(
        scoring.calcular_score(usuario).score
    )
    categorias = [c["categoria"] for c in resultado.contribuciones]
    assert "ahorro_verificado" in categorias
    assert "declarado" not in categorias


def test_ahorro_verificado_aparece_en_las_contribuciones(make_usuario):
    resultado = scoring.calcular_score(make_usuario(ahorros=config.AHORRO_VERIFICADO_TECHO_COP))
    categorias = [c["categoria"] for c in resultado.contribuciones]
    assert "ahorro_verificado" in categorias


def test_sin_columna_ahorros_cae_al_declarado(make_usuario):
    """Un usuario sin el campo (leads armados antes de conectar la columna,
    o el perfil sintetico de un no registrado) no debe romper el calculo."""
    usuario = make_usuario()  # make_usuario no incluye "ahorros" por defecto
    resultado = scoring.calcular_score(
        usuario, datos_declarados={"ahorro_cuota_inicial": True}
    )
    assert resultado.score == pytest.approx(
        scoring.calcular_score(usuario).score + scoring.BONO_AHORRO_CUOTA_INICIAL
    )


def test_ahorros_nan_cae_al_declarado(make_usuario):
    """Una fila de pandas sin dato en una columna numerica llega como NaN, no
    como None -- no debe tratarse como 'tiene $nan de ahorro verificado'."""
    usuario = make_usuario(ahorros=float("nan"))
    resultado = scoring.calcular_score(
        usuario, datos_declarados={"ahorro_cuota_inicial": True}
    )
    categorias = [c["categoria"] for c in resultado.contribuciones]
    assert "declarado" in categorias
    assert "ahorro_verificado" not in categorias


# ---------------------------------------------------------------------
# family_structure: antes era codigo muerto (nadie pasaba el valor)
# ---------------------------------------------------------------------

def test_estructura_familiar_declarada_activa_la_rama_del_schema(make_usuario):
    usuario = make_usuario()  # VIS, afiliado
    base = scoring.calcular_score(usuario)
    monoparental = scoring.calcular_score(
        usuario, datos_declarados={"estructura_familiar": "Monoparental Joven"}
    )

    assert monoparental.score > base.score
    assert any("monoparental" in r.lower() for r in monoparental.razones)


def test_estructura_familiar_explicita_gana_sobre_la_declarada(make_usuario):
    """El parametro explicito existe para los tests y para un futuro override
    del asesor; no debe quedar tapado por lo que extrajo la conversacion."""
    usuario = make_usuario()
    resultado = scoring.calcular_score(
        usuario,
        family_structure="Nuclear Integrada",
        datos_declarados={"estructura_familiar": "Monoparental Joven"},
    )
    assert not any("monoparental" in r.lower() for r in resultado.razones)


# ---------------------------------------------------------------------
# Leads sin registro
# ---------------------------------------------------------------------

def test_sin_datos_declarados_cae_en_la_penalizacion_fija():
    resultado = scoring.calcular_score_no_registrado()

    assert resultado.score == scoring.SCORE_NO_REGISTRADO
    assert resultado.segmento_lead == "FRIO"
    assert resultado.project_segment == "Sin dato (no registrado)"


def test_diccionario_vacio_equivale_a_sin_datos():
    assert scoring.calcular_score_no_registrado({}).score == scoring.SCORE_NO_REGISTRADO


def test_un_buen_perfil_declarado_supera_la_penalizacion_fija():
    """El caso que el reto pide no perder: alguien sin registro que igual
    demuestra capacidad de compra."""
    resultado = scoring.calcular_score_no_registrado(
        {
            "situacion_laboral": "empleado_formal",
            "ingresos_mensuales_aprox": 6_000_000,
            "ahorro_cuota_inicial": True,
        }
    )
    assert resultado.score > scoring.SCORE_NO_REGISTRADO


def test_desempleado_declarado_puntua_peor_que_empleado_formal():
    empleado = scoring.calcular_score_no_registrado(
        {"situacion_laboral": "empleado_formal", "ingresos_mensuales_aprox": 4_000_000}
    )
    desempleado = scoring.calcular_score_no_registrado(
        {"situacion_laboral": "desempleado", "ingresos_mensuales_aprox": 4_000_000}
    )
    assert empleado.score > desempleado.score


def test_se_aplica_el_factor_de_confianza():
    """Lo declarado no vale lo mismo que lo verificado."""
    declarados = {"situacion_laboral": "empleado_formal", "ingresos_mensuales_aprox": 6_000_000}
    sin_verificar = scoring.calcular_score_no_registrado(declarados)
    como_si_estuviera_en_la_base = scoring.calcular_score(
        scoring._perfil_desde_declarados(declarados), datos_declarados=declarados
    )

    assert sin_verificar.score < como_si_estuviera_en_la_base.score
    assert sin_verificar.score == pytest.approx(
        round(como_si_estuviera_en_la_base.score * scoring.FACTOR_CONFIANZA_DECLARADO, 1)
    )
    assert any("sin verificar" in r.lower() for r in sin_verificar.razones)


def test_el_segmento_del_no_registrado_respeta_los_umbrales_configurados():
    resultado = scoring.calcular_score_no_registrado(
        {"situacion_laboral": "empleado_formal", "ingresos_mensuales_aprox": 6_000_000}
    )
    esperado = (
        "CALIENTE"
        if resultado.score >= config.UMBRAL_CALIENTE
        else "TIBIO"
        if resultado.score >= config.UMBRAL_TIBIO
        else "FRIO"
    )
    assert resultado.segmento_lead == esperado


# ---------------------------------------------------------------------
# _perfil_desde_declarados: los huecos se llenan neutros, no en contra
# ---------------------------------------------------------------------

def test_lo_no_declarado_queda_neutro_no_en_el_peor_valor():
    perfil = scoring._perfil_desde_declarados({})

    # no saber si esta reportado en centrales no es lo mismo que estarlo
    assert perfil["Reportado en data crédito"] == "No reportado"
    # no declarar situacion laboral no lo vuelve desempleado
    assert perfil["Estado laboral"] != "Desempleado"


def test_solo_el_empleado_formal_se_asume_afiliado():
    """En Colombia el empleado formal esta afiliado a una caja por ley; del
    resto no se puede afirmar."""
    formal = scoring._perfil_desde_declarados({"situacion_laboral": "empleado_formal"})
    independiente = scoring._perfil_desde_declarados({"situacion_laboral": "independiente"})

    assert formal["Afiliado a colsubsidio"] == "Si"
    assert independiente["Afiliado a colsubsidio"] == "No"


# ---------------------------------------------------------------------
# Prior de ingreso: "no se" no es lo mismo que "no gana nada"
# ---------------------------------------------------------------------

def test_situacion_laboral_sin_ingreso_usa_el_prior():
    perfil = scoring._perfil_desde_declarados({"situacion_laboral": "empleado_formal"})
    esperado = config.INGRESO_SUPUESTO_POR_SITUACION["empleado_formal"]
    assert str(esperado) in perfil["Rango salarial"]


def test_el_ingreso_declarado_gana_sobre_el_prior():
    perfil = scoring._perfil_desde_declarados(
        {"situacion_laboral": "empleado_formal", "ingresos_mensuales_aprox": 9_000_000}
    )
    assert "9000000" in perfil["Rango salarial"]


def test_sin_situacion_laboral_no_se_inventa_ingreso():
    perfil = scoring._perfil_desde_declarados({"ahorro_cuota_inicial": True})
    assert perfil["Rango salarial"] == ""


def test_el_supuesto_de_ingreso_queda_escrito_en_las_razones():
    resultado = scoring.calcular_score_no_registrado({"situacion_laboral": "empleado_formal"})
    assert any("se asume la mediana" in r.lower() for r in resultado.razones)


def test_no_se_declara_supuesto_si_el_usuario_dio_su_ingreso():
    resultado = scoring.calcular_score_no_registrado(
        {"situacion_laboral": "empleado_formal", "ingresos_mensuales_aprox": 5_000_000}
    )
    assert not any("se asume la mediana" in r.lower() for r in resultado.razones)
