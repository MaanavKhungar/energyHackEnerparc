import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from rag.chunker import chunk_text
from rag.config import settings
from rag.embedder import embed, load_model
from rag.loader import Document


def setup_collection(client: QdrantClient, collection_name: str, vector_size: int = 1024) -> None:
    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )


def _point_id(source: str, location: int | None, chunk_index: int) -> str:
    # Deterministic: re-indexing the same document overwrites rather than duplicates.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}_{location}_{chunk_index}"))


def ingest(doc: Document, client: QdrantClient, collection_name: str) -> int:
    chunks = chunk_text(doc.page_text, settings.chunk_size, settings.chunk_overlap)
    if not chunks:
        return 0

    vectors = embed(chunks, load_model())

    location = doc.page_number if doc.page_number is not None else doc.row_index
    base_payload: dict = {"source": doc.source, "source_type": doc.source_type}
    if doc.page_number is not None:
        base_payload["page_number"] = doc.page_number
    if doc.row_index is not None:
        base_payload["row_index"] = doc.row_index

    points = [
        PointStruct(
            id=_point_id(doc.source, location, i),
            vector=vector,
            payload={**base_payload, "chunk_text": chunk, "chunk_index": i},
        )
        for i, (chunk, vector) in enumerate(zip(chunks, vectors))
    ]

    client.upsert(collection_name=collection_name, points=points)
    return len(points)
