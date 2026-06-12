"""Quick smoke test: ingest a PDF and run a query against it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qdrant_client import QdrantClient

from rag.config import settings
from rag.embedder import load_model
from rag.indexer import ingest, setup_collection
from rag.loader import load_file
from rag.pipeline import answer

PDF = Path(__file__).parent.parent / "data" / "BayWa_TUM_DI_LAB_SS2025_FinalReport.pdf"
QUERY = "What are the main findings of this report?"

print(f"Loading: {PDF.name}")
docs = load_file(PDF)
print(f"  → {len(docs)} pages extracted")

client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
setup_collection(client, settings.collection_name)
model = load_model()

total = 0
for doc in docs:
    total += ingest(doc, client, settings.collection_name)
print(f"  → {total} chunks indexed")

print(f"\nQuery: {QUERY}\n")
result = answer(QUERY, model, client, settings)
print("Answer:", result["answer"])
print("\nSources:")
for s in result["sources"]:
    print(f"  - {s['source']} ({s['source_type']})")

client.close()
