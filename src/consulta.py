"""Recuperación y generación con cita de fuente y abstención."""

from __future__ import annotations

import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import Config  # noqa: E402
from indice import cliente_openai  # noqa: E402

SIN_INFORMACION = "No tengo esa información en la documentación disponible."

# Frases que indican que el modelo no encontró el dato. No alcanza con la
# frase exacta: a veces responde "no especifica el arancel de ...", que también
# es una abstención válida.
MARCADORES_ABSTENCION = (
    "no tengo esa información",
    "no especifica",
    "no se especifica",
    "no figura",
    "no indica",
    "no menciona",
    "no detalla",
    "no está en la documentación",
    "no contiene esa información",
)


def _normalizar(texto: str) -> str:
    """Minúsculas y sin tildes."""
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


_MARCADORES_NORM = tuple(_normalizar(m) for m in MARCADORES_ABSTENCION)


def es_abstencion(texto: str) -> bool:
    normalizado = _normalizar(texto)
    return any(m in normalizado for m in _MARCADORES_NORM)

INSTRUCCIONES = """Respondés preguntas sobre documentación institucional usando \
exclusivamente los fragmentos que se te entregan.

Reglas, en orden de prioridad:

1. Si los fragmentos no contienen la respuesta, respondé exactamente:
   "{sin_info}"
   No completes con conocimiento propio. No infieras. No generalices a partir
   de un fragmento parecido.

2. Si la contienen, respondé de forma concreta y citá al final de cada
   afirmación la fuente entre corchetes, con el formato [documento · sección].

3. Si los fragmentos se contradicen entre sí, decilo explícitamente y citá
   ambos en lugar de elegir uno.

4. No des indicaciones médicas, diagnósticos ni recomendaciones de tratamiento,
   aunque los fragmentos las contengan. Este sistema responde sobre qué dice la
   documentación, no sobre qué debe hacer un paciente. Si la pregunta pide eso,
   señalá qué documento lo trata y remitilo a consulta profesional."""


@dataclass
class Fuente:
    documento: str
    seccion: str
    puntaje: float
    texto: str


@dataclass
class Respuesta:
    pregunta: str
    texto: str
    fuentes: list[Fuente] = field(default_factory=list)
    se_abstuvo: bool = False
    consulto_modelo: bool = True


def completar(cliente, despliegue: str, mensajes: list[dict]) -> str:
    """Llama al modelo con temperature=0; si el modelo no lo admite, reintenta sin él."""
    try:
        r = cliente.chat.completions.create(
            model=despliegue, temperature=0, messages=mensajes
        )
    except Exception as e:
        if "temperature" not in str(e).lower():
            raise
        r = cliente.chat.completions.create(model=despliegue, messages=mensajes)

    return (r.choices[0].message.content or "").strip()


MODOS = ("hibrida", "vectorial", "texto")


def recuperar(cfg: Config, pregunta: str, modo: str = "vectorial") -> list[Fuente]:
    """Recupera los fragmentos más relevantes.

    Modos: `vectorial` (por defecto, el mejor en comparar.py), `texto` (BM25)
    e `hibrida`. Los puntajes no son comparables entre modos.
    """
    if modo not in MODOS:
        raise ValueError(f"modo debe ser uno de {MODOS}, no {modo!r}")

    consultas_vector = None
    if modo in ("hibrida", "vectorial"):
        oai = cliente_openai(cfg)
        vector = oai.embeddings.create(
            model=cfg.deployment_embeddings, input=[pregunta]
        ).data[0].embedding
        consultas_vector = [
            VectorizedQuery(vector=vector, k_nearest_neighbors=cfg.top_k * 3, fields="vector")
        ]

    cliente = SearchClient(cfg.search_endpoint, cfg.indice, AzureKeyCredential(cfg.search_api_key))
    resultados = cliente.search(
        search_text=pregunta if modo in ("hibrida", "texto") else None,
        vector_queries=consultas_vector,
        select=["texto", "documento", "seccion"],
        top=cfg.top_k,
    )

    return [
        Fuente(
            documento=r["documento"],
            seccion=r["seccion"],
            puntaje=r["@search.score"],
            texto=r["texto"],
        )
        for r in resultados
    ]


def responder(cfg: Config, pregunta: str, modo: str = "vectorial",
              aplicar_umbral: bool = True) -> Respuesta:
    """Responde con los fragmentos recuperados.

    `aplicar_umbral=False` se usa al comparar modos (comparar.py).
    """
    fuentes = recuperar(cfg, pregunta, modo)
    relevantes = (
        [f for f in fuentes if f.puntaje >= cfg.umbral_relevancia]
        if aplicar_umbral
        else fuentes
    )

    # Si nada supera el umbral, se abstiene sin llamar al modelo.
    if not relevantes:
        return Respuesta(
            pregunta=pregunta,
            texto=SIN_INFORMACION,
            fuentes=[],
            se_abstuvo=True,
            consulto_modelo=False,
        )

    # Cada fragmento ya incluye su encabezado [documento · sección].
    contexto = "\n\n---\n\n".join(f.texto for f in relevantes)

    oai = cliente_openai(cfg)
    texto = completar(
        oai,
        cfg.deployment_chat,
        [
            {"role": "system", "content": INSTRUCCIONES.format(sin_info=SIN_INFORMACION)},
            {"role": "user", "content": f"FRAGMENTOS:\n\n{contexto}\n\nPREGUNTA: {pregunta}"},
        ],
    )

    return Respuesta(
        pregunta=pregunta,
        texto=texto,
        fuentes=relevantes,
        se_abstuvo=es_abstencion(texto),
    )


def main() -> None:
    cfg = Config.desde_entorno()
    print("Preguntá sobre la documentación. Enter vacío para salir.\n")

    while True:
        try:
            pregunta = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not pregunta:
            break

        r = responder(cfg, pregunta)
        print(f"\n{r.texto}\n")
        if r.fuentes:
            print("Fuentes consultadas:")
            for f in r.fuentes:
                print(f"  · {f.documento} — {f.seccion} (puntaje {f.puntaje:.4f})")
        elif not r.consulto_modelo:
            print("(nada superó el umbral de relevancia; no se consultó al modelo)")
        print()


if __name__ == "__main__":
    main()
