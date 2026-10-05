"""Crea el índice en Azure AI Search y carga los fragmentos.

El índice guarda texto y vector, así que admite búsqueda vectorial, textual e
híbrida. Por defecto se usa la vectorial (ver comparar.py).
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

    Usa la API v1 por defecto. Si AZURE_OPENAI_API_VERSION está definida,
    usa esa versión.
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
    """Genera embeddings en lotes."""
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

    # Se indexa el texto con el encabezado [documento · sección].
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
    """Borra del índice los fragmentos que ya no están en el corpus,
    para que no se citen documentos editados o eliminados.
    """
    # Sin `top`, la búsqueda devuelve solo 50 resultados.
    LIMITE = 1000
    en_indice = {
        doc["id"] for doc in cliente.search(search_text="*", select=["id"], top=LIMITE)
    }
    if len(en_indice) >= LIMITE:
        print(
            f"Aviso: el índice tiene {LIMITE} o más fragmentos; la búsqueda de "
            "huérfanos puede estar incompleta. Hace falta paginar."
        )
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
