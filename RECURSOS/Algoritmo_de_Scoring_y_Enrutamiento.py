import numpy as np

def procesar_lead_inmobiliario(datos_usuario, modelo_xgboost, catalogo_proyectos):
    """
    Calcula la probabilidad de compra, aplica reglas de negocio y define la acción del bot.
    """
    # 1. Identificación del origen del lead
    es_afiliado = datos_usuario.get('afiliado_colsubsidio', False)
    
    # 2. Preprocesamiento de Variables Críticas
    # El modelo da mayor peso a la combinación de 'tipo_contrato' y 'fecha_inicio_labores' 
    # sobre el 'rango_salarial' puro.
    features = preparar_features_para_modelo(datos_usuario)
    
    # 3. Predicción Base (Probabilidad de 0 a 1)
    # Se extrae la probabilidad de la clase positiva (compra exitosa)
    score_base = modelo_xgboost.predict_proba(features)[1] 
    
    # 4. Reglas de Negocio y Penalizaciones
    # Castigo drástico por reporte negativo en centrales (filtro casi eliminatorio)
    if datos_usuario.get('reportado_datacredito', False) == True:
        score_base *= 0.10 
        
    # Penalización de la regla 90/10 para No Afiliados
    if not es_afiliado:
        score_base *= 0.80
        
    # 5. Resolución de Segmentos Intermedios (Aproximación)
    if score_base >= 0.55:
        # Aproxima hacia arriba asegurando que cruce el umbral de > 0.70
        score_final = max(score_base, 0.75) 
        segmento = 'CALIENTE'
    else:
        # Aproxima hacia abajo asegurando que quede en el umbral de < 0.40
        score_final = min(score_base, 0.35) 
        segmento = 'FRÍO'
        
    # 6. Etiquetado para el CRM del Asesor Comercial
    etiquetas_crm = []
    if not es_afiliado:
        etiquetas_crm.append('🟡 NO AFILIADO')
        
    if segmento == 'CALIENTE':
        etiquetas_crm.append('🟢 LEAD CALIENTE')
    else:
        etiquetas_crm.append('🔴 LEAD FRÍO')
        
    # 7. Ejecución de Acciones
    # Transferencia universal en background al asesor humano
    enviar_a_crm_asesor(datos_usuario, score_final, etiquetas_crm)
    
    # Definición de la acción frontal del Asesor Digital
    if segmento == 'CALIENTE':
        proyecto_ideal = cruzar_con_json_proyectos(datos_usuario, catalogo_proyectos)
        accion_bot = {
            "tipo_respuesta": "cierre_celebratorio",
            "mensaje": f"¡Excelentes noticias! Tienes un perfil ideal. Hemos encontrado viabilidad para tu vivienda en la categoría {proyecto_ideal['tipo']}."
        }
    else:
        accion_bot = {
            "tipo_respuesta": "despedida_cortes",
            "mensaje": "Gracias por compartir tu información. Te invitamos a explorar nuestra sección de educación financiera para seguir preparándote para tu futura vivienda."
        }
        
    return {
        "score_calculado": round(score_final, 2),
        "etiquetas_asignadas": etiquetas_crm,
        "instruccion_front_end": accion_bot
    }

# --- Funciones Auxiliares (Mockups de soporte) ---

def preparar_features_para_modelo(datos):
    # Transforma las variables categóricas (ej. tipo_contrato) y numéricas
    # en un array procesable por XGBoost.
    return np.array([datos.values()])

def enviar_a_crm_asesor(datos, score, etiquetas):
    # API Call que inserta el lead en la base del asesor humano sin notificar al usuario.
    pass

def cruzar_con_json_proyectos(datos, catalogo):
    # Lógica que lee el rango_salarial y asigna VIS, VIP o No VIS.
    return {"tipo": "VIS"}