"""Stub retrievers so the router/chatbot/eval loop can run before either side is real.

Replace with the real `PdfRag` / `SqlRag` implementations when they land.
"""
from __future__ import annotations

from rag.src_rag.interfaces import PdfChunk, PdfRagResult, SqlRagResult


def stub_pdf_rag(question: str, *, k: int = 5) -> PdfRagResult:
    chunks = [
        PdfChunk(
            chunk_id=f"stub-pdf-{i}",
            text=f"[stub chunk {i}] placeholder passage relevant to: {question!r}",
            page=i + 1,
            section="STUB SECTION",
            score=1.0 - i * 0.1,
        )
        for i in range(k)
    ]
    return PdfRagResult(chunks=chunks, retriever="stub")


def stub_sql_rag(question: str, *, max_rows: int = 50) -> SqlRagResult:
    return SqlRagResult(
        sql=f"-- stub query for: {question}\nSELECT 1 AS stub_col;",
        rows=[{"stub_col": 1}],
        columns=["stub_col"],
    )
