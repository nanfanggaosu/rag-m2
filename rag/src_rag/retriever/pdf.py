"""Minimal PDF retriever: embed chunks with bge-small, store in ChromaDB, query top-k.

Phase-2 minimum version — no re-ranker, no BM25, no parent-child. Those optimisations
go on top later. The public surface conforms to `rag.src_rag.interfaces.PdfRag`.

Build the index once:
    uv run python -m rag.src_rag.retriever.pdf

Query from code:
    from rag.src_rag.retriever.pdf import pdf_rag
    pdf_rag("how does deep strike work?", k=5)
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from rag.src_rag.interfaces import PdfChunk, PdfRagResult

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CHUNKS_PATH = PROJECT_ROOT / "rag" / "data" / "chunks.jsonl"
INDEX_DIR = PROJECT_ROOT / "rag" / "data" / "index" / "chroma"
COLLECTION = "pdf_core_rules"
MODEL_NAME = "BAAI/bge-small-en-v1.5"
# bge-en-v1.5 model card: prepend this to the QUERY only; passages take no prefix.
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


@lru_cache(maxsize=1)
def _collection() -> chromadb.Collection:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(INDEX_DIR), settings=Settings(anonymized_telemetry=False)
    )
    return client.get_or_create_collection(
        name=COLLECTION, metadata={"hnsw:space": "cosine"}
    )


def _doc_for_embedding(section: str | None, text: str) -> str:
    """Prepend the section title so the embedding carries topical context, not
    just the body sentence. Verified against the token budget (max 390 < 512)."""
    return f"{section}\n{text}" if section else text


def build_index() -> int:
    """Read chunks.jsonl, embed everything, store in Chroma. Returns #indexed."""
    if not CHUNKS_PATH.exists():
        raise FileNotFoundError(f"{CHUNKS_PATH} missing; run `make chunk` first.")
    chunks = [json.loads(l) for l in CHUNKS_PATH.open()]
    col = _collection()
    # Rebuild from scratch so the index always matches the latest chunks.jsonl.
    existing = col.get(include=[])["ids"]
    if existing:
        col.delete(ids=existing)
    docs = [_doc_for_embedding(c.get("section"), c["text"]) for c in chunks]
    embeddings = _model().encode(
        docs, normalize_embeddings=True, show_progress_bar=False
    ).tolist()
    col.add(
        ids=[c["chunk_id"] for c in chunks],
        embeddings=embeddings,
        documents=[c["text"] for c in chunks],
        metadatas=[
            {"page": c["page"], "section": c.get("section") or ""} for c in chunks
        ],
    )
    return len(chunks)


def pdf_rag(question: str, *, k: int = 5) -> PdfRagResult:
    q_emb = _model().encode(
        [_QUERY_PREFIX + question], normalize_embeddings=True, show_progress_bar=False
    ).tolist()
    res = _collection().query(query_embeddings=q_emb, n_results=k)
    out: list[PdfChunk] = []
    for cid, doc, meta, dist in zip(
        res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        out.append(
            PdfChunk(
                chunk_id=cid,
                text=doc,
                page=int(meta.get("page") or 0),
                section=(meta.get("section") or None) or None,
                score=1.0 - float(dist),  # cosine distance → cosine similarity
            )
        )
    return PdfRagResult(chunks=out, retriever="chroma+bge-small")


def main() -> None:
    n = build_index()
    print(f"indexed {n} chunks -> {INDEX_DIR.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
