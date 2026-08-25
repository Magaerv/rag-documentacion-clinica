"""Compara los tres modos de recuperación sobre el mismo conjunto de evaluación.

El README afirma que la búsqueda híbrida es mejor que la vectorial pura para
este dominio. Este script existe para que esa afirmación deje de ser una
hipótesis razonable y pase a ser un resultado medido — o para desmentirla,
que también es un resultado publicable.

El umbral de relevancia se desactiva en los tres modos. Los puntajes no son
comparables entre sí (fusión de rankings, similitud coseno y BM25 viven en
escalas distintas), así que un umbral fijo penalizaría a unos modos y no a
otros, y el experimento terminaría midiendo el umbral en vez de la
recuperación.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import Config  # noqa: E402
from consulta import MODOS  # noqa: E402
from evaluar import evaluar  # noqa: E402

ETIQUETAS = {
    "hibrida": "Híbrida (significado + término)",
    "vectorial": "Solo significado",
    "texto": "Solo término exacto",
}

METRICAS = [
    ("recupero_documento_esperado_%", "Recuperó el documento correcto"),
    ("acerto_el_dato_%", "Acertó el dato pedido"),
    ("cobertura_respondibles_%", "Respondió, citó y acertó"),
    ("abstencion_correcta_%", "Se abstuvo cuando debía"),
    ("citaron_fuente_%", "Citó la fuente"),
]


def main() -> None:
    cfg = Config.desde_entorno()
    raiz = Path(__file__).resolve().parents[1]
    casos = yaml.safe_load(
        (raiz / "evaluacion" / "preguntas.yaml").read_text(encoding="utf-8")
    )["casos"]

    print(f"Comparando {len(MODOS)} modos sobre {len(casos)} casos.\n")

    resultados = {}
    for modo in MODOS:
        print(f"  {ETIQUETAS[modo]}...", flush=True)
        resultados[modo] = evaluar(cfg, casos, modo=modo, aplicar_umbral=False)

    ancho = max(len(d) for _, d in METRICAS) + 2
    print("\n" + " " * ancho + "".join(f"{m:>14}" for m in MODOS))
    print("-" * (ancho + 14 * len(MODOS)))
    for clave, descripcion in METRICAS:
        fila = "".join(f"{resultados[m]['resumen'][clave]:>13.1f}%" for m in MODOS)
        print(f"{descripcion:<{ancho}}{fila}")

    # Desglose por grupo. El promedio general esconde justamente lo que el
    # experimento quiere ver: si cada mecanismo falla donde se espera que falle.
    grupos = {}
    for caso in casos:
        grupos.setdefault(caso.get("grupo", "general"), []).append(caso["pregunta"])

    if len(grupos) > 1:
        print("\nRecuperó el documento correcto, por grupo de preguntas:\n")
        indice_detalle = {
            m: {f["pregunta"]: f for f in resultados[m]["detalle"]} for m in MODOS
        }
        etiqueta_grupo = {
            "parafrasis": "Paráfrasis (sin las palabras del doc)",
            "termino": "Término técnico infrecuente",
            "general": "Generales",
        }
        ancho_g = max(len(v) for v in etiqueta_grupo.values()) + 2
        print(" " * ancho_g + "".join(f"{m:>14}" for m in MODOS))
        for grupo, preguntas in sorted(grupos.items()):
            fila = ""
            for m in MODOS:
                filas = [indice_detalle[m][p] for p in preguntas]
                con_esperado = [f for f in filas if f["documento_esperado"]]
                aciertos = sum(1 for f in con_esperado if f["recupero_esperado"])
                pct = 100 * aciertos / len(con_esperado) if con_esperado else 0.0
                fila += f"{pct:>13.1f}%"
            print(f"{etiqueta_grupo.get(grupo, grupo):<{ancho_g}}{fila}")

    # Los casos donde los modos difieren son lo más informativo del experimento:
    # muestran qué recupera uno que el otro no, en vez de un promedio.
    print("\nCasos con resultado distinto entre modos:\n")
    detalle = {m: {f["pregunta"]: f for f in resultados[m]["detalle"]} for m in MODOS}
    hubo = False
    for caso in casos:
        p = caso["pregunta"]
        estados = {m: detalle[m][p]["correcto"] for m in MODOS}
        if len(set(estados.values())) > 1:
            hubo = True
            marcas = "  ".join(f"{m}={'ok' if estados[m] else 'NO'}" for m in MODOS)
            print(f"  · {p}")
            print(f"    {marcas}")
    if not hubo:
        print("  Ninguno: los tres modos resolvieron igual todos los casos.")

    salida = raiz / "resultados-comparacion.json"
    salida.write_text(
        json.dumps(
            {m: resultados[m] for m in MODOS}, ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    print(f"\nDetalle completo en {salida.name}")


if __name__ == "__main__":
    main()
