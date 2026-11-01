"""Contract between the two RAG paths (PDF, SQL) and the router.

Both partners build independently against these types. Change this file by consensus,
not unilaterally — a breaking change here forces the other side to rework.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


Source = Literal["pdf", "sql", "both"]


@dataclass(frozen=True)
class PdfChunk:
    """One retrieved passage from the PDF corpus."""

    chunk_id: str
    text: str
    page: int
    section: str | None = None
    score: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PdfRagResult:
    """What `pdf_rag(question)` returns."""

    chunks: list[PdfChunk]
    elapsed_ms: float | None = None
    retriever: str | None = None


@dataclass(frozen=True)
class SqlRagResult:
    """What `sql_rag(question)` returns."""

    sql: str
    rows: list[dict[str, Any]]
    columns: list[str]
    elapsed_ms: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class RouterDecision:
    """What the router picks before calling a tool."""

    source: Source
    rationale: str


@dataclass(frozen=True)
class FinalAnswer:
    """End-to-end response surfaced to the chat UI."""

    text: str
    source: Source
    pdf: PdfRagResult | None = None
    sql: SqlRagResult | None = None
    decision: RouterDecision | None = None


class PdfRag(Protocol):
    """Partner A's deliverable. Any class implementing this is a valid PDF retriever."""

    def __call__(self, question: str, *, k: int = 5) -> PdfRagResult: ...


class SqlRag(Protocol):
    """Partner B's deliverable."""

    def __call__(self, question: str, *, max_rows: int = 50) -> SqlRagResult: ...


class Router(Protocol):
    def __call__(self, question: str) -> RouterDecision: ...


class Llm(Protocol):
    """Shared LLM wrapper. Must support simple text completion and JSON-mode calls."""

    def complete(self, prompt: str) -> str: ...

    def complete_json(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]: ...
