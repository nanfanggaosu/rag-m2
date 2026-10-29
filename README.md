# rag-m2 — RAG mini-project

A two-source Retrieval-Augmented-Generation system for the course mini-project.

- **PDF source:** Warhammer 40k Core Rules (`rag/data/raw/Core Rules.pdf`)
- **SQL source:** `rag/data/raw/wahadb.sqlite` (21 tables of Warhammer 40k rules/datasheets)
- **Router agent** picks which source to query per question.

## Architecture (phase 1 draft)

```
                       ┌──────────────┐
                 ┌────▶│  PDF-RAG     │──▶ chunks + page + section
  question ─▶ Router   │  (owner: A)  │
                 └────▶│  SQL-RAG     │──▶ SQL + rows
                       │  (owner: B)  │
                       └──────────────┘
                              │
                              ▼
                        final LLM call
                              │
                              ▼
                            answer
```

Everything upstream of the router (parsing, chunking, indexing) and everything
inside each RAG lives in its owner's branch. The two paths meet only at the
contract in [`rag/src_rag/interfaces.py`](rag/src_rag/interfaces.py).

## Directory layout

```
rag/
  data/
    raw/
      Core Rules.pdf                 # PDF corpus (teacher-provided)
      wahadb.sqlite                  # SQLite DB (teacher-provided, read-only in code)
      SQL_AGENT_DATA_DICTIONARY.md   # table/column docs (teacher-provided)
    parsed/                          # docling output: Core Rules.{md,json,txt}
  src_rag/
    parser/      # docling driver (A)
    chunker/     # text + table/image linking (A)
    retriever/   # pdf.py (A), sql.py (B), stubs.py
    llm/         # shared Google-AI-Studio wrapper
    chatbot/     # router.py + app.py (chat UI)
    evaluation/  # test-set + LLM-as-judge (joint)
    interfaces.py  # the contract — change only by consensus
tests/            # mirrors src_rag/
```

## Interface contract (summary)

See [`rag/src_rag/interfaces.py`](rag/src_rag/interfaces.py). The three functions each
side writes against:

| Function | Owner | Returns |
|---|---|---|
| `PdfRag(question, k=5)` | A | `PdfRagResult` — list of `PdfChunk(text, page, section, score)` |
| `SqlRag(question, max_rows=50)` | B | `SqlRagResult` — `sql`, `rows`, `columns`, optional `error` |
| `Router(question)` | joint | `RouterDecision(source, rationale)` |

Both sides have stub implementations in `rag/src_rag/retriever/stubs.py` so the
router and chat loop run end-to-end before either side is real.

## Setup

```bash
uv sync          # install everything from uv.lock
uv run pytest -q # should print "3 passed"
```

Teacher-provided data (PDF, SQLite, data dictionary) is committed under
`rag/data/raw/`, so `git clone` + `uv sync` is enough to start.

## Team

- **A — Yawen Zhang** ([@nanfanggaosu](https://github.com/nanfanggaosu))
- **B — Ruxin Xie** ([@xieruxin922](https://github.com/xieruxin922))

## Make targets

| Command | What it does |
|---|---|
| `make parse` | Run docling on `rag/data/raw/*.pdf` |
| `make index` | Chunk + embed into the vector DB (TODO) |
| `make chat`  | Launch the chat loop (stubs for now) |
| `make eval`  | Run evaluation (TODO) |
| `make test`  | `uv run pytest` |

## Division of work

| Area | Owner | Notes |
|---|---|---|
| Scaffold, interface, router, chat shell, docs | **joint** | this phase |
| `parser/`, `chunker/`, `retriever/pdf.py`, vector DB, embeddings | **A** | PDF path |
| `retriever/sql.py` (text-to-SQL), data dictionary prompting, read-only connection | **B** | SQL path |
| `llm/` (Google AI Studio wrapper) | **joint** | both sides need it |
| `evaluation/` | **joint** | A writes rules questions, B writes data questions |

## Decisions log

- **Package manager:** `uv` (2026-10-29). Faster than pip; `uv.lock` makes the
  partner's env reproducible.
- **Vector DB:** TBD — likely ChromaDB for simplicity.
- **Embedding model:** `BAAI/bge-small-en-v1.5` (2026-10-29). 512-token context,
  384-dim, strong on the MTEB leaderboard among small open-source models. All 261
  chunks of `Core Rules.pdf` fit (max 374 tokens), so no truncation and no need
  to split long elements by sentence.
- **LLM provider:** Google AI Studio (per teacher's grading convention).
- **SQL connection:** must be opened with `mode=ro`. Never writable from
  LLM-reachable code paths.
- **Out of scope:** ColBERT / late interaction (teacher said so in lecture 3).

## Open questions

- Which embedding model exactly? Decide when A starts on the retriever.
- How many chunks `k` for the first retrieval pass? Start with `k=20` + re-rank to 5?
- Does the final answer always cite its source (page / SQL query)? Likely yes — important for the UI.
