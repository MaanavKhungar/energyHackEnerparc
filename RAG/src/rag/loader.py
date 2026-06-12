import csv
from pathlib import Path

import pymupdf
from pydantic import BaseModel


class Document(BaseModel):
    source: str
    source_type: str  # "csv" or "pdf"
    page_text: str
    page_number: int | None = None
    row_index: int | None = None


def load_csv(path: str | Path) -> list[Document]:
    path = Path(path)
    docs = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            text = " | ".join(f"{k}: {v}" for k, v in row.items() if v)
            docs.append(Document(
                source=path.name,
                source_type="csv",
                page_text=text,
                row_index=i,
            ))
    return docs


def load_pdf(path: str | Path) -> list[Document]:
    path = Path(path)
    docs = []
    with pymupdf.open(str(path)) as pdf:
        for page_num, page in enumerate(pdf):
            text = page.get_text()
            if text.strip():
                docs.append(Document(
                    source=path.name,
                    source_type="pdf",
                    page_text=text,
                    page_number=page_num + 1,
                ))
    return docs


def load_file(path: str | Path) -> list[Document]:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        return load_csv(path)
    elif path.suffix.lower() == ".pdf":
        return load_pdf(path)
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")
