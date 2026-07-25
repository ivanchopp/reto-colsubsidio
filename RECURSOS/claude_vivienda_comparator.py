import pandas as pd
import json

class ViviendaAIComparator:
    """
    Herramienta para procesar el dataset de compradores y generar prompts estructurados
    para modelos de lenguaje (LLMs) enfocados en predicción de riesgo inmobiliario.
    """
    def __init__(self, dataset_path):
        # Cargar los datos limpios
        self.df = pd.read_csv(dataset_path)
        
    def obtener_resumen_proyecto(self, nombre_proyecto):
        """Filtra y agrega estadísticas clave de un proyecto inmobiliario."""
        datos = self.df[self.df['NOMBRE_PROYECTO'].str.contains(nombre_proyecto, case=False, na=False)]
        
        if datos.empty:
            return {"Error": f"No se encontraron datos para {nombre_proyecto}"}
            
        return {
            "Proyecto": nombre_proyecto,
            "Total_Prospectos": len(datos),
            "Tasa_Desistimiento_Porcentaje": round(datos['IS_DESISTIMIENTO_TARGET'].mean() * 100, 2),
            "Entidad_Financiera_Dominante": datos['Entidad Financiera compra'].mode()[0],
            "Rango_Edad_Principal": datos['RANGO_EDAD_CLEAN'].mode()[0],
            "Promedio_Grupo_Familiar": round(datos['NO_GRUPO_FAMILAR_CLEAN'].mean(), 1),
            "Precio_Promedio_Vivienda_Millones": round(datos['VLR_VIVIENDA_MILLONES_COP'].mean(), 2)
        }

    def generar_prompt_comparativo(self, proyecto_a, proyecto_b):
        """
        Compila la información en un formato que un LLM puede leer, comparar
        y sobre el cual puede aplicar razonamiento paramétrico.
        """
        resumen_a = self.obtener_resumen_proyecto(proyecto_a)
        resumen_b = self.obtener_resumen_proyecto(proyecto_b)
        
        prompt = f"""
Eres un analista de ciencia de datos experto en el mercado inmobiliario colombiano.
Te he proporcionado los resúmenes estadísticos de dos proyectos distintos extraídos de nuestro modelo.

--- DATOS DEL PROYECTO 1 ---
{json.dumps(resumen_a, indent=2, ensure_ascii=False)}

--- DATOS DEL PROYECTO 2 ---
{json.dumps(resumen_b, indent=2, ensure_ascii=False)}

Por favor, realiza las siguientes tareas:
1. Compara ambos ecosistemas: ¿Cuál presenta un mayor riesgo de iliquidez (desistimiento) y cómo influye la "Entidad Financiera Dominante" (ej. Colsubsidio vs Bancos)?
2. Basado en el 'Precio_Promedio' y el 'Rango_Edad', deduce si estamos comparando un ecosistema VIS con un No VIS, y explica cómo eso altera la probabilidad de compra.
3. Proporciona una recomendación de pesos paramétricos que deberíamos asignar a la variable 'Rango_Edad' en nuestro algoritmo de Random Forest/XGBoost para cada uno de estos proyectos.
"""
        return prompt

    def generar_prompt_analisis_caidas(self):
        """Genera un análisis de los negocios caídos para encontrar patrones."""
        caidos = self.df[self.df['IS_DESISTIMIENTO_TARGET'] == 1].copy()
        resumen = caidos[['NOMBRE_PROYECTO', 'MEDIO', 'RANGO_EDAD_CLEAN', 'VLR_VIVIENDA_MILLONES_COP']].to_dict(orient='records')
        
        prompt = f"""
A continuación te presento un JSON con los perfiles de los negocios que se CAYERON (IS_DESISTIMIENTO_TARGET = 1):

{json.dumps(resumen, indent=2, ensure_ascii=False)}

Por favor, identifica los patrones comunes de fracaso. ¿Existe algún "MEDIO" de captación o "RANGO_EDAD" que esté altamente correlacionado con el desistimiento? 
"""
        return prompt

# ==========================================
# Ejecución de Prueba
# ==========================================
if __name__ == "__main__":
    # Inicializar comparador
    comparator = ViviendaAIComparator('dataset_vivienda_ML_ready.csv')
    
    # 1. Generar prompt comparativo entre un proyecto de alto valor y uno VIS
    prompt_comparativo = comparator.generar_prompt_comparativo("Los Nogales", "VERDE ESPERANZA")
    
    # 2. Generar prompt de análisis de errores/caídas
    prompt_errores = comparator.generar_prompt_analisis_caidas()
    
    print("--- ARCHIVO GENERADO CORRECTAMENTE ---")
    print("Puedes pasar los prompts resultantes a la IA para que razone sobre los datos.")
