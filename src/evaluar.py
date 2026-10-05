"""Evalúa el sistema contra el conjunto de preguntas de evaluacion/preguntas.yaml.

Incluye preguntas sin respuesta en el corpus para medir si el sistema se abstiene.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import Config  # noqa: E402
from consulta import _normalizar, responder  # noqa: E402

CITA = re.compile(r"\[[^\]\n]+·[^\]\n]+\]")


def evaluar(cfg: Config, casos: list[dict], modo: str = "vectorial",
            aplicar_umbral: bool = True) -> dict:
    filas = []

    for caso in casos:
        pregunta = caso["pregunta"]
        respondible = caso.get("respondible", True)
        documento_esperado = caso.get("documento_esperado")

        r = responder(cfg, pregunta, modo, aplicar_umbral)

        cito = bool(CITA.search(r.texto))
        documentos = {f.documento for f in r.fuentes}
        recupero_esperado = documento_esperado in documentos if documento_esperado else None

        # Verifica que la respuesta contenga el dato esperado, no solo que cite.
        esperado = caso.get("respuesta_contiene") or []
        normalizada = _normalizar(r.texto)
        acerto = (
            any(_normalizar(clave) in normalizada for clave in esperado)
            if esperado
            else None
        )

        if respondible:
            # Correcto: respondió, citó y acertó el dato.
            ok = (not r.se_abstuvo) and cito and (acerto is not False)
        else:
            # Correcto: se abstuvo.
            ok = r.se_abstuvo

        filas.append(
            {
                "pregunta": pregunta,
                "respondible": respondible,
                "se_abstuvo": r.se_abstuvo,
                "cito_fuente": cito,
                "consulto_modelo": r.consulto_modelo,
                "documento_esperado": documento_esperado,
                "recupero_esperado": recupero_esperado,
                "acerto_el_dato": acerto,
                "correcto": ok,
                "respuesta": r.texto,
                "fuentes": [f"{f.documento} · {f.seccion}" for f in r.fuentes],
            }
        )

    respondibles = [f for f in filas if f["respondible"]]
    no_respondibles = [f for f in filas if not f["respondible"]]

    def tasa(sub: list[dict], clave: str = "correcto") -> float:
        return round(100 * sum(1 for f in sub if f[clave]) / len(sub), 1) if sub else 0.0

    resumen = {
        "total": len(filas),
        "cobertura_respondibles_%": tasa(respondibles),
        "abstencion_correcta_%": tasa(no_respondibles),
        "citaron_fuente_%": tasa(respondibles, "cito_fuente"),
        "acerto_el_dato_%": round(
            100
            * sum(1 for f in respondibles if f["acerto_el_dato"])
            / max(1, sum(1 for f in respondibles if f["acerto_el_dato"] is not None)),
            1,
        ),
        "recupero_documento_esperado_%": (
            round(
                100
                * sum(1 for f in respondibles if f["recupero_esperado"])
                / max(1, sum(1 for f in respondibles if f["documento_esperado"])),
                1,
            )
        ),
        "abstenciones_sin_invocar_modelo": sum(
            1 for f in filas if not f["consulto_modelo"]
        ),
    }

    return {"resumen": resumen, "detalle": filas}


def main() -> None:
    cfg = Config.desde_entorno()
    raiz = Path(__file__).resolve().parents[1]
    archivo = raiz / "evaluacion" / "preguntas.yaml"

    casos = yaml.safe_load(archivo.read_text(encoding="utf-8"))["casos"]
    print(f"Evaluando {len(casos)} casos...\n")

    resultado = evaluar(cfg, casos)

    for clave, valor in resultado["resumen"].items():
        print(f"  {clave:38} {valor}")

    fallidos = [f for f in resultado["detalle"] if not f["correcto"]]
    if fallidos:
        print(f"\n{len(fallidos)} caso(s) fallidos:")
        for f in fallidos:
            motivo = "inventó" if not f["respondible"] else ("se abstuvo" if f["se_abstuvo"] else "no citó")
            print(f"  · [{motivo}] {f['pregunta']}")

    salida = raiz / "resultados-evaluacion.json"
    salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDetalle completo en {salida.name}")


if __name__ == "__main__":
    main()
