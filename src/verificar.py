"""Comprueba que las credenciales y los despliegues estén bien configurados.

Se ejecuta antes de indexar nada. Cada verificación falla con un mensaje que
dice qué revisar, en vez de dejar que el error aparezca a mitad de la carga.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

OK = "  [ok]  "
ERR = "  [--]  "


def main() -> int:
    fallos = 0

    # 1. Variables de entorno
    try:
        from config import Config

        cfg = Config.desde_entorno()
        print(f"{OK}Variables de entorno completas")
    except Exception as e:
        print(f"{ERR}{e}")
        return 1

    # 2. Despliegue de embeddings
    try:
        from indice import cliente_openai

        oai = cliente_openai(cfg)
        r = oai.embeddings.create(model=cfg.deployment_embeddings, input=["prueba de conexión"])
        dim = len(r.data[0].embedding)
        print(f"{OK}Embeddings '{cfg.deployment_embeddings}' responde · dimensión {dim}")

        from config import DIMENSION_EMBEDDING

        if dim != DIMENSION_EMBEDDING:
            print(
                f"{ERR}La dimensión no coincide con la declarada ({DIMENSION_EMBEDDING}). "
                f"Actualizá DIMENSION_EMBEDDING en config.py a {dim} antes de crear el índice."
            )
            fallos += 1
    except Exception as e:
        print(f"{ERR}Embeddings: {type(e).__name__} — {e}")
        print("         Revisá AZURE_OPENAI_ENDPOINT, la clave, y que el nombre del")
        print("         despliegue coincida exactamente con el del portal.")
        fallos += 1

    # 3. Despliegue de chat
    try:
        from consulta import completar

        texto = completar(
            oai, cfg.deployment_chat, [{"role": "user", "content": "Respondé solo: listo"}]
        )
        print(f"{OK}Chat '{cfg.deployment_chat}' responde · {texto!r}")
    except Exception as e:
        print(f"{ERR}Chat: {type(e).__name__} — {e}")
        print("         Revisá que el despliegue de chat exista y esté activo.")
        fallos += 1

    # 4. Azure AI Search
    try:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents.indexes import SearchIndexClient

        cliente = SearchIndexClient(cfg.search_endpoint, AzureKeyCredential(cfg.search_api_key))
        indices = [i.name for i in cliente.list_indexes()]
        print(f"{OK}Azure AI Search responde · índices existentes: {indices or 'ninguno'}")
    except Exception as e:
        print(f"{ERR}Search: {type(e).__name__} — {e}")
        print("         Revisá AZURE_SEARCH_ENDPOINT (termina en .search.windows.net)")
        print("         y que la clave sea la de administrador, no la de consulta.")
        fallos += 1

    # 5. Corpus
    corpus = Path(__file__).resolve().parents[1] / "corpus"
    docs = [p for p in corpus.rglob("*") if p.suffix.lower() in {".md", ".txt"} and p.name != "README.md"]
    if docs:
        print(f"{OK}Corpus: {len(docs)} documento(s)")
    else:
        print(f"{ERR}Corpus vacío. Poné archivos .md o .txt en {corpus}")
        fallos += 1

    print()
    if fallos:
        print(f"{fallos} problema(s). Corregí y volvé a ejecutar.")
    else:
        print("Todo listo. Siguiente paso: python src/indice.py")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
