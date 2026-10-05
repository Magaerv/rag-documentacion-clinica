"""Configuración leída desde variables de entorno (.env)."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _requerida(nombre: str) -> str:
    valor = os.getenv(nombre)
    if not valor:
        raise RuntimeError(
            f"Falta la variable de entorno {nombre}. "
            "Copiá .env.example a .env y completá los valores."
        )
    return valor


@dataclass(frozen=True)
class Config:
    # Azure OpenAI
    openai_endpoint: str
    openai_api_key: str
    openai_api_version: str
    deployment_embeddings: str
    deployment_chat: str

    # Azure AI Search
    search_endpoint: str
    search_api_key: str
    indice: str

    # Segmentación
    tamano_fragmento: int
    solapamiento: int

    # Recuperación
    top_k: int
    umbral_relevancia: float

    @classmethod
    def desde_entorno(cls) -> "Config":
        return cls(
            openai_endpoint=_requerida("AZURE_OPENAI_ENDPOINT"),
            openai_api_key=_requerida("AZURE_OPENAI_API_KEY"),
            # Vacío = API v1.
            openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "").strip(),
            deployment_embeddings=_requerida("AZURE_OPENAI_DEPLOYMENT_EMBEDDINGS"),
            deployment_chat=_requerida("AZURE_OPENAI_DEPLOYMENT_CHAT"),
            search_endpoint=_requerida("AZURE_SEARCH_ENDPOINT"),
            search_api_key=_requerida("AZURE_SEARCH_API_KEY"),
            indice=os.getenv("AZURE_SEARCH_INDEX", "documentacion-clinica"),
            tamano_fragmento=int(os.getenv("TAMANO_FRAGMENTO", "800")),
            solapamiento=int(os.getenv("SOLAPAMIENTO", "150")),
            top_k=int(os.getenv("TOP_K", "5")),
            # Fragmentos por debajo de este puntaje no se pasan al modelo.
            # Valor medido con calibrar.py (la peor respondible puntúa 0.66);
            # 0.62 deja margen.
            umbral_relevancia=float(os.getenv("UMBRAL_RELEVANCIA", "0.62")),
        )


# Dimensión de text-embedding-3-small. Si cambia el modelo, recrear el índice.
DIMENSION_EMBEDDING = 1536
