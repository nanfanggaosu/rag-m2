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
| `make chunk` | Chunk the parsed JSON into `rag/data/chunks.jsonl` |
| `make index` | Embed chunks into the Chroma vector DB |
| `make chat`  | Launch the chat loop (real PDF retriever + stub SQL) |
| `make eval`  | Run the PDF-side evaluation set |
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
- **Query prefix:** apply the model card's recommended prefix
  `"Represent this sentence for searching relevant passages: "` to the query
  only (passages take no prefix). Sanity-check (same 2 hard questions, top-3
  retrieval, bge-small cosine):

  | Question | Before prefix | After prefix |
  |---|---|---|
  | "How does deep strike work?" | p49 EXAMPLE BATTLEFIELDS (0.665), p33 FIGHT (0.659), p32 FIGHT PHASE (0.659) — all wrong | p49 EXAMPLE BATTLEFIELDS (0.639), p32 FIGHT PHASE (0.632), p32 FIGHTS FIRST (0.626) — still all wrong |
  | "When do I determine the attacker and defender?" | p57 / p59 DECLARE BATTLE FORMATIONS (0.720), p33 MAKE MELEE ATTACKS (0.703) | p57 / p59 DECLARE BATTLE FORMATIONS (0.704), p33 MAKE MELEE ATTACKS (0.685) |

  Prefix alone did not fix either case — scores shifted but rankings did not.
  Kept anyway per the model card; the next improvement (section prepending)
  targets the actual failure mode.
- **Section prepending at index time:** embed `"{section}\n{text}"` instead of
  just `text`. Sections like `DEEP STRIKE` or `DETERMINE ATTACKER AND DEFENDER`
  are topical signals that body sentences alone don't carry. Max token count
  rises from 374 → 390, still well under 512. Same sanity, same 2 questions,
  top-3 retrieval:

  | Question | After prefix only | After prefix + section prepended |
  |---|---|---|
  | "How does deep strike work?" | p49 EXAMPLE BATTLEFIELDS (0.639), p32 FIGHT PHASE (0.632), p32 FIGHTS FIRST (0.626) — all wrong | **p39 DEEP STRIKE (0.696)** ✓, p33 FIGHT (0.631), p32 FIGHT PHASE (0.626) |
  | "When do I determine the attacker and defender?" | p57 / p59 DECLARE BATTLE FORMATIONS (0.704), p33 MAKE MELEE ATTACKS (0.685) | **p57 / p59 DETERMINE ATTACKER AND DEFENDER (0.779)** ✓, p60 DETERMINE VICTOR (0.708) |

  Top-1 is now correct on both. Rebuild the index with `make index` after any
  chunker change.
- **PDF eval set (phase-1 baseline, 2026-10-30):** 10 hand-labelled questions in
  `rag/src_rag/evaluation/questions_pdf.jsonl`, each with expected page(s) and
  section(s). Current baseline on `chroma+bge-small` + query prefix + section
  prepended, k=5:

  | Metric | Score |
  |---|---|
  | Hit@5 (section) | 100% |
  | Hit@5 (page)    | 100% |
  | MRR@5 (section) | 0.925 |

  Only miss: `saving-throw` ("What happens on a save roll?") lands at rank 4 —
  the token "roll" pulls top-3 to `COMMAND RE-ROLL` / `ROLL-OFFS` / `RE-ROLLS`
  instead of `4. SAVING THROW` (p22). Classic dense-only failure mode where a
  fixed term matters more than semantic similarity. Candidate fix if it recurs:
  BM25 + RRF hybrid (lecture 3). Not doing it yet — need more labelled failures
  first. Run `make eval` to reproduce.
- **LLM provider:** Google AI Studio (per teacher's grading convention).
- **SQL connection:** must be opened with `mode=ro`. Never writable from
  LLM-reachable code paths.
- **Out of scope:** ColBERT / late interaction (teacher said so in lecture 3).

## Open questions

- How many chunks `k` for the first retrieval pass? Current default `k=5`; try
  `k=20` + re-rank to 5 once we have an LLM reranker wired.
- Does the final answer always cite its source (page / SQL query)? Likely yes
  — important for the UI.
- Grow the PDF eval set past 10 questions and start tracking per-category
  failures (fixed-term vs. descriptive, single-section vs. multi-section).
