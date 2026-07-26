"""Calibra y audita el motor de scoring contra la base completa.

Corre calcular_score sobre todos los usuarios y reporta tres cosas:

  1. El rango real de cada senal del blend (reglas / peers / vectorial). Si
     una senal no usa su rango completo, esta desperdiciando el peso que
     tiene asignado y le pone un techo artificial al score final.
  2. La distribucion del score y los umbrales que hacen falta para que
     CALIENTE y TIBIO queden en los porcentajes objetivo de config.py.
  3. La distribucion resultante con los umbrales que hay hoy configurados.

Uso:
    python scripts/calibrar_scoring.py

Si los umbrales sugeridos no coinciden con config.UMBRAL_CALIENTE /
config.UMBRAL_TIBIO, actualizalos ahi. Este script no escribe nada.
"""
import collections
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import config, data_store, scoring  # noqa: E402


def percentil(valores_ordenados: list[float], p: float) -> float:
    if not valores_ordenados:
        return 0.0
    idx = int(p * (len(valores_ordenados) - 1))
    return valores_ordenados[idx]


def main():
    df = data_store.cargar_usuarios()
    total = len(df)
    print(f"Usuarios evaluados: {total}")
    print(f"Tasa base de conversion de la base: {data_store.tasa_base_conversion():.1f}%\n")

    scores = []
    segmentos = collections.Counter()
    senales_crudas = collections.defaultdict(list)

    for _, fila in df.iterrows():
        resultado = scoring.calcular_score(fila.to_dict())
        scores.append(resultado.score)
        segmentos[resultado.segmento_lead] += 1
        for contribucion in resultado.contribuciones or []:
            if contribucion["peso"]:
                senales_crudas[contribucion["categoria"]].append(
                    contribucion["valor"] / contribucion["peso"]
                )

    print("--- Rango real de cada senal (cruda, 0-100) ---")
    for categoria, valores in sorted(senales_crudas.items()):
        valores.sort()
        cobertura = (valores[-1] - valores[0])
        print(
            f"  {categoria:<10} min {valores[0]:5.1f} | mediana {percentil(valores, 0.5):5.1f} "
            f"| max {valores[-1]:5.1f} | usa {cobertura:.0f} de 100 puntos de rango"
        )

    scores.sort()
    print("\n--- Distribucion del score final ---")
    for p in (0, 25, 50, 75, 88, 95, 100):
        print(f"  p{p:<3} {percentil(scores, p / 100):5.1f}")

    corte_caliente = percentil(scores, 1 - config.PCT_OBJETIVO_CALIENTE)
    corte_tibio = percentil(scores, 1 - config.PCT_OBJETIVO_CALIENTE - config.PCT_OBJETIVO_TIBIO)

    print(
        f"\n--- Umbrales sugeridos para {config.PCT_OBJETIVO_CALIENTE:.0%} CALIENTE "
        f"/ {config.PCT_OBJETIVO_TIBIO:.0%} TIBIO ---"
    )
    print(f"  UMBRAL_CALIENTE = {corte_caliente:.1f}")
    print(f"  UMBRAL_TIBIO    = {corte_tibio:.1f}")

    print(
        f"\n--- Distribucion con los umbrales configurados hoy "
        f"(CALIENTE >= {config.UMBRAL_CALIENTE}, TIBIO >= {config.UMBRAL_TIBIO}) ---"
    )
    for nombre in ("CALIENTE", "TIBIO", "FRIO"):
        cantidad = segmentos[nombre]
        print(f"  {nombre:<9} {cantidad:5d}  ({cantidad / total * 100:5.1f}%)")

    if segmentos["CALIENTE"] == 0:
        print(
            "\n  AVISO: ningun lead alcanza CALIENTE. El handoff al asesor esta "
            "muerto: revisa los umbrales de arriba."
        )


if __name__ == "__main__":
    main()
