from qdrant_client import QdrantClient
from qdrant_client.models import Filter
from sentence_transformers import SentenceTransformer

from rag.config import Settings
from rag.generator import generate
from rag.retriever import retrieve


def answer(
    query: str,
    model: SentenceTransformer,
    qdrant_client: QdrantClient,
    settings: Settings,
    query_filter: Filter | None = None,
) -> dict:
    chunks = retrieve(query, model, qdrant_client, settings.collection_name, settings.retrieval_top_k, query_filter)
    if not chunks:
        return {"answer": "No relevant information found.", "sources": []}
    response = generate(query, chunks)
    sources = [{"source": c["source"], "source_type": c["source_type"]} for c in chunks]
    return {"answer": response, "sources": sources}
