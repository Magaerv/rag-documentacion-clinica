"""Configuración del sistema. Todo valor sensible viaja por variables de entorno."""

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
            # Vacío = API v1 de Azure OpenAI, donde api-version dejó de ser
            # necesaria. Se completa solo para fijar una versión con fecha,
            # que es lo que hay que hacer si un modelo exige una en particular.
            openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION", "").strip(),
            deployment_embeddings=_requerida("AZURE_OPENAI_DEPLOYMENT_EMBEDDINGS"),
            deployment_chat=_requerida("AZURE_OPENAI_DEPLOYMENT_CHAT"),
            search_endpoint=_requerida("AZURE_SEARCH_ENDPOINT"),
            search_api_key=_requerida("AZURE_SEARCH_API_KEY"),
            indice=os.getenv("AZURE_SEARCH_INDEX", "documentacion-clinica"),
            tamano_fragmento=int(os.getenv("TAMANO_FRAGMENTO", "800")),
            solapamiento=int(os.getenv("SOLAPAMIENTO", "150")),
            top_k=int(os.getenv("TOP_K", "5")),
            # Por debajo de este puntaje, el fragmento no se le pasa al modelo:
            # el sistema se abstiene sin invocar el chat.
            #
            # 0.62 no es un valor elegido a ojo. Se midió el puntaje del mejor
            # fragmento recuperado para las 42 preguntas de evaluación (ver
            # calibrar.py). Las dos poblaciones se superponen —8 de las 11
            # preguntas sin respuesta puntúan por encima de la peor pregunta
            # respondible—, así que no existe un corte que las separe. Pero
            # hasta 0.66 se frenan 3 de esas 11 sin perder ninguna respuesta
            # legítima. Se eligió 0.62 en vez de 0.66 para dejar margen: la
            # peor respondible puntúa 0.6604, y un umbral pegado a ese borde
            # cortaría cualquier pregunta futura apenas por debajo.
            #
            # Alcance real: esta capa filtra alrededor de un cuarto de las
            # preguntas sin respuesta. El resto lo frena la instrucción dada
            # al modelo.
            umbral_relevancia=float(os.getenv("UMBRAL_RELEVANCIA", "0.62")),
        )


# Dimensión del vector de text-embedding-3-small. Si cambiás de modelo,
# hay que cambiar esto y recrear el índice: el esquema la declara fija.
DIMENSION_EMBEDDING = 1536
