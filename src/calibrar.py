"""Mide los puntajes de recuperación para elegir el umbral de relevancia.

Compara el puntaje del mejor fragmento en preguntas respondibles y no
respondibles, y muestra qué pasaría con cada umbral candidato.
"""

from __future__ import annotations

import json
import statistics as stats
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import Config  # noqa: E402
from consulta import recuperar  # noqa: E402

MODO = "vectorial"


def describir(nombre: str, valores: list[float]) -> None:
    if not valores:
        print(f"  {nombre}: sin datos")
        return
    print(
        f"  {nombre:<18} n={len(valores):<3} "
        f"mín={min(valores):.4f}  mediana={stats.median(valores):.4f}  "
        f"máx={max(valores):.4f}"
    )


def main() -> None:
    cfg = Config.desde_entorno()
    raiz = Path(__file__).resolve().parents[1]
    casos = yaml.safe_load(
        (raiz / "evaluacion" / "preguntas.yaml").read_text(encoding="utf-8")
    )["casos"]

    print(f"Midiendo puntajes de {len(casos)} preguntas en modo {MODO}...\n")

    filas = []
    for caso in casos:
        fuentes = recuperar(cfg, caso["pregunta"], MODO)
        filas.append(
            {
                "pregunta": caso["pregunta"],
                "respondible": caso.get("respondible", True),
                "puntaje_top": fuentes[0].puntaje if fuentes else 0.0,
            }
        )

    resp = [f["puntaje_top"] for f in filas if f["respondible"]]
    nores = [f["puntaje_top"] for f in filas if not f["respondible"]]

    print("Puntaje del mejor fragmento recuperado:\n")
    describir("Respondibles", resp)
    describir("No respondibles", nores)

    # Hay separación limpia si el peor respondible supera al mejor no respondible.
    print()
    if min(resp) > max(nores):
        umbral = (min(resp) + max(nores)) / 2
        print(f"  SEPARACIÓN LIMPIA. Umbral posible: {umbral:.4f}")
        print(f"  (peor respondible {min(resp):.4f} > mejor no respondible {max(nores):.4f})")
    else:
        solapamiento = [p for p in nores if p >= min(resp)]
        print(f"  SE SUPERPONEN. {len(solapamiento)} de {len(nores)} preguntas sin")
        print(f"  respuesta puntúan por encima de la peor pregunta respondible.")
        print("  Ningún umbral las separa sin perder respuestas legítimas.")

    # Efecto de cada umbral candidato.
    print("\nQué pasaría con cada umbral candidato:\n")
    print("  umbral     abstiene bien   pierde respondibles")
    candidatos = sorted({round(p, 3) for p in nores + resp})
    for u in candidatos:
        gana = sum(1 for p in nores if p < u)
        pierde = sum(1 for p in resp if p < u)
        marca = "  <-- sin costo" if pierde == 0 and gana > 0 else ""
        print(f"  {u:<10.3f} {gana:>8} / {len(nores):<6} {pierde:>10} / {len(resp)}{marca}")

    salida = raiz / "resultados-calibracion.json"
    salida.write_text(
        json.dumps(
            {
                "modo": MODO,
                "umbral_configurado": cfg.umbral_relevancia,
                "respondibles": {"n": len(resp), "min": min(resp), "max": max(resp)},
                "no_respondibles": {"n": len(nores), "min": min(nores), "max": max(nores)},
                "separacion_limpia": min(resp) > max(nores),
                "detalle": filas,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nDetalle en {salida.name}")


if __name__ == "__main__":
    main()
