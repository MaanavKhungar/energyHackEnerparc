from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from rag.config import settings
from rag.embedder import load_model
from rag.indexer import ingest, setup_collection
from rag.loader import load_file
from rag.pipeline import answer


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.model = load_model()
    app.state.qdrant = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    setup_collection(app.state.qdrant, settings.collection_name)
    yield
    app.state.qdrant.close()


app = FastAPI(title="Energy RAG", lifespan=lifespan)


class IngestRequest(BaseModel):
    paths: list[str]


class IngestResponse(BaseModel):
    files_loaded: int
    chunks_indexed: int


class QueryRequest(BaseModel):
    question: str
    source_type: str | None = None  # "csv" or "pdf" to filter by source type


class QueryResponse(BaseModel):
    answer: str
    sources: list[dict]


@app.post("/ingest", response_model=IngestResponse)
def ingest_endpoint(req: IngestRequest):
    files_loaded = 0
    chunks_indexed = 0

    for path_str in req.paths:
        path = Path(path_str)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {path_str}")
        docs = load_file(path)
        files_loaded += 1
        for doc in docs:
            chunks_indexed += ingest(doc, app.state.qdrant, settings.collection_name)

    return IngestResponse(files_loaded=files_loaded, chunks_indexed=chunks_indexed)


@app.post("/query", response_model=QueryResponse)
def query_endpoint(req: QueryRequest):
    query_filter = None
    if req.source_type:
        query_filter = Filter(
            must=[FieldCondition(key="source_type", match=MatchValue(value=req.source_type))]
        )

    result = answer(req.question, app.state.model, app.state.qdrant, settings, query_filter)
    return QueryResponse(**result)


@app.get("/health")
def health():
    try:
        info = app.state.qdrant.get_collection(settings.collection_name)
        points_count = info.points_count
    except Exception:
        points_count = 0
    return {"status": "ok", "collection": settings.collection_name, "points_count": points_count}
