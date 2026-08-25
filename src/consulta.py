"""Recuperación y generación con grounding.

El criterio de aceptación de este sistema no es que responda: es que no
infiera lo que no está en el corpus y que cite la fuente de cada respuesta.
Todo lo de abajo está ordenado alrededor de eso.
"""

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

# Detectar abstención por coincidencia exacta con la frase canónica resultó
# demasiado rígido. Cuando el corpus contiene algo relacionado pero no el dato
# pedido, el modelo produce una negativa más útil —"la documentación indica que
# la atención es arancelada, pero no especifica el arancel de ortodoncia"— que
# es la conducta correcta y que la coincidencia exacta contaba como invento.
#
# Estos marcadores reconocen la familia de negativas. El criterio sigue siendo
# el mismo: lo que importa es que el sistema declare la ausencia del dato, no
# la fórmula exacta con la que lo declare.
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
    """Minúsculas y sin tildes.

    La detección no debe depender de la acentuación: el modelo puede escribir
    "informacion" sin tilde y la negativa seguiría siendo una negativa. Hacer
    depender una métrica de un acento es construirla sobre arena.
    """
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
    """Invoca el modelo de chat pidiendo la salida más determinística posible.

    `temperature=0` es lo que queremos: ante los mismos fragmentos, la misma
    respuesta. Pero varias familias de modelos recientes solo admiten el valor
    por defecto y rechazan el parámetro. En ese caso se reintenta sin él, en
    lugar de fallar: la determinación exacta es deseable, no indispensable.
    """
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
    """Recupera los fragmentos más relevantes para la pregunta.

    Tres modos, para poder comparar qué aporta cada mecanismo:

    - `vectorial`: solo búsqueda por significado. Encuentra el fragmento
      aunque la pregunta use otras palabras, pero confunde términos que son
      vecinos semánticos entre sí.
    - `texto`: solo búsqueda por término (BM25). Encuentra la palabra exacta
      y pondera las infrecuentes, pero falla si la pregunta está formulada
      con otro vocabulario.
    - `hibrida`: las dos combinadas.

    El modo por defecto es `vectorial`, y no por costumbre: se midieron los
    tres sobre el mismo conjunto de evaluación y la búsqueda por significado
    acertó 31 de 31, la híbrida 30 y la textual 29. Combinar los mecanismos
    no mejoró nada y en un caso perjudicó — la coincidencia literal trajo un
    fragmento de un documento sin relación y, al fusionar los rankings,
    desplazó fuera del top al fragmento correcto. Ver comparar.py.

    Los puntajes NO son comparables entre modos: la híbrida los combina por
    fusión de rankings, la vectorial devuelve similitud y la textual, puntaje
    BM25. Por eso el umbral de relevancia solo tiene sentido dentro de un modo.
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
    """Responde la pregunta con los fragmentos recuperados.

    `aplicar_umbral` se desactiva al comparar modos de recuperación: los
    puntajes no son comparables entre sí, de modo que un umbral fijo
    penalizaría a unos modos y no a otros, y el experimento mediría el
    umbral en vez de la recuperación.
    """
    fuentes = recuperar(cfg, pregunta, modo)
    relevantes = (
        [f for f in fuentes if f.puntaje >= cfg.umbral_relevancia]
        if aplicar_umbral
        else fuentes
    )

    # Abstención temprana: si nada supera el umbral, no se invoca el modelo.
    # Ahorra el costo y, sobre todo, elimina la oportunidad de inventar.
    if not relevantes:
        return Respuesta(
            pregunta=pregunta,
            texto=SIN_INFORMACION,
            fuentes=[],
            se_abstuvo=True,
            consulto_modelo=False,
        )

    # El texto recuperado ya trae su encabezado [documento · sección]
    # incorporado desde la indexación, en el mismo formato que el prompt
    # le pide al modelo para citar.
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
