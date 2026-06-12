import ollama

from rag.config import settings

_SYSTEM_PROMPT = """\
You are an energy industry assistant. Answer questions using only the context provided below.

Rules:
- Answer only from the provided context. If the context does not contain enough \
information to answer, say so clearly.
- Cite the source when you use information, e.g. "According to [1] report.pdf, ..." \
or "The data in [2] shows...".
- Be concise. One to three paragraphs unless the question requires more detail.
- Do not hallucinate numbers, statistics, or claims not in the context.\
"""


def _build_context_block(chunks: list[dict]) -> str:
    sections = []
    for i, chunk in enumerate(chunks, start=1):
        source = chunk["source"]
        if chunk.get("page_number") is not None:
            loc = f"page {chunk['page_number']}"
        elif chunk.get("row_index") is not None:
            loc = f"row {chunk['row_index']}"
        else:
            loc = ""
        header = f"[{i}] {source}" + (f" ({loc})" if loc else "")
        sections.append(f"{header}\n{chunk['chunk_text']}")
    return "\n\n---\n\n".join(sections)


def generate(query: str, context_chunks: list[dict]) -> str:
    context_block = _build_context_block(context_chunks)
    user_message = f"Context:\n\n{context_block}\n\nQuestion: {query}"

    response = ollama.chat(
        model=settings.ollama_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        stream=False,
    )
    return response["message"]["content"]
