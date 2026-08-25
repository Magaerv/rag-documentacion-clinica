"""Creación del índice en Azure AI Search y carga de los fragmentos.

El índice guarda a la vez el texto y su vector. Eso habilita búsqueda
híbrida: recuperación vectorial por significado más BM25 por palabra exacta.
La decisión está justificada en DECISIONES.md — en documentación clínica hay
términos que no toleran aproximación, y la búsqueda puramente vectorial los
confunde con sus vecinos semánticos.
"""

from __future__ import annotations

import sys
from pathlib import Path

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from openai import AzureOpenAI, OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DIMENSION_EMBEDDING, Config  # noqa: E402
from ingesta import Fragmento, leer_corpus  # noqa: E402


def cliente_openai(cfg: Config):
    """Cliente de Azure OpenAI.

    Por defecto usa la **API v1**, donde `api-version` ya no es un parámetro:
    el recurso expone las rutas bajo `/openai/v1/` y el SDK estándar de OpenAI
    habla con él directamente. Fijar una versión con fecha obliga a revisarla
    cada vez que sale un modelo nuevo, y era la causa más común de que un
    despliegue reciente devolviera "modelo no encontrado".

    Si algún modelo llegara a exigir una versión concreta, se define
    AZURE_OPENAI_API_VERSION y el cliente vuelve al modo con fecha.
    """
    if cfg.openai_api_version:
        return AzureOpenAI(
            azure_endpoint=cfg.openai_endpoint,
            api_key=cfg.openai_api_key,
            api_version=cfg.openai_api_version,
        )

    base = cfg.openai_endpoint.rstrip("/")
    return OpenAI(base_url=f"{base}/openai/v1/", api_key=cfg.openai_api_key)


def vectorizar(cliente: AzureOpenAI, cfg: Config, textos: list[str]) -> list[list[float]]:
    """Genera embeddings en lotes. La API acepta varios textos por llamada."""
    vectores: list[list[float]] = []
    LOTE = 64
    for i in range(0, len(textos), LOTE):
        respuesta = cliente.embeddings.create(
            model=cfg.deployment_embeddings,
            input=textos[i : i + LOTE],
        )
        vectores.extend(d.embedding for d in respuesta.data)
    return vectores


def crear_indice(cfg: Config) -> None:
    cliente = SearchIndexClient(cfg.search_endpoint, AzureKeyCredential(cfg.search_api_key))

    campos = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="texto", type=SearchFieldDataType.String, analyzer_name="es.microsoft"),
        SearchableField(name="documento", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(name="seccion", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="orden", type=SearchFieldDataType.Int32, sortable=True),
        SearchField(
            name="vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=DIMENSION_EMBEDDING,
            vector_search_profile_name="perfil-hnsw",
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw")],
        profiles=[VectorSearchProfile(name="perfil-hnsw", algorithm_configuration_name="hnsw")],
    )

    indice = SearchIndex(name=cfg.indice, fields=campos, vector_search=vector_search)
    cliente.create_or_update_index(indice)
    print(f"Índice '{cfg.indice}' creado o actualizado.")


def cargar(cfg: Config, fragmentos: list[Fragmento]) -> None:
    oai = cliente_openai(cfg)
    print(f"Generando embeddings de {len(fragmentos)} fragmentos...")

    # Se indexa el texto con su procedencia incorporada, no el texto pelado.
    # Ver Fragmento.texto_indexado: sin el encabezado, un fragmento corto
    # pierde el tema del que habla y se vuelve irrecuperable.
    textos = [f.texto_indexado() for f in fragmentos]
    vectores = vectorizar(oai, cfg, textos)

    documentos = []
    for fragmento, texto, vector in zip(fragmentos, textos, vectores):
        d = fragmento.como_dict()
        d["texto"] = texto
        d["vector"] = vector
        documentos.append(d)

    cliente = SearchClient(cfg.search_endpoint, cfg.indice, AzureKeyCredential(cfg.search_api_key))

    LOTE = 500
    subidos = 0
    for i in range(0, len(documentos), LOTE):
        resultado = cliente.upload_documents(documents=documentos[i : i + LOTE])
        fallidos = [r for r in resultado if not r.succeeded]
        if fallidos:
            raise RuntimeError(f"{len(fallidos)} documento(s) fallaron al indexar: {fallidos[0].error_message}")
        subidos += len(resultado)

    print(f"{subidos} fragmentos indexados.")
    _eliminar_huerfanos(cliente, {d["id"] for d in documentos})


def _eliminar_huerfanos(cliente: SearchClient, ids_vigentes: set[str]) -> None:
    """Borra del índice los fragmentos que ya no existen en el corpus.

    Subir documentos actualiza los que coinciden por id y agrega los nuevos,
    pero no elimina nada. Sin esta reconciliación, editar o borrar un documento
    del corpus deja sus fragmentos viejos indexados para siempre, y el sistema
    podría recuperarlos y citarlos como documentación vigente.

    En un sistema cuya garantía es que toda respuesta sea rastreable al corpus,
    un fragmento huérfano no es basura acumulada: es una cita falsa esperando
    que alguien haga la pregunta correcta.
    """
    en_indice = {doc["id"] for doc in cliente.search(search_text="*", select=["id"])}
    huerfanos = en_indice - ids_vigentes

    if not huerfanos:
        print("Sin fragmentos huérfanos.")
        return

    cliente.delete_documents(documents=[{"id": i} for i in huerfanos])
    print(f"{len(huerfanos)} fragmento(s) huérfano(s) eliminado(s).")


def main() -> None:
    cfg = Config.desde_entorno()
    raiz = Path(__file__).resolve().parents[1]

    fragmentos = leer_corpus(raiz / "corpus", cfg.tamano_fragmento, cfg.solapamiento)
    print(f"{len(fragmentos)} fragmentos desde {len({f.documento for f in fragmentos})} documento(s).")

    crear_indice(cfg)
    cargar(cfg, fragmentos)


if __name__ == "__main__":
    main()
