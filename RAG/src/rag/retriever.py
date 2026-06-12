from qdrant_client import QdrantClient
from qdrant_client.models import Filter
from sentence_transformers import SentenceTransformer

from rag.embedder import embed


def retrieve(
    query: str,
    model: SentenceTransformer,
    client: QdrantClient,
    collection_name: str,
    top_k: int = 5,
    query_filter: Filter | None = None,
) -> list[dict]:
    query_vector = embed([query], model)[0]

    results = client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=top_k,
        with_payload=True,
        query_filter=query_filter,
    ).points

    return [
        {
            "chunk_text": hit.payload["chunk_text"],
            "source": hit.payload["source"],
            "source_type": hit.payload["source_type"],
            "page_number": hit.payload.get("page_number"),
            "row_index": hit.payload.get("row_index"),
            "score": hit.score,
        }
        for hit in results
    ]
