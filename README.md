# rag-m2 — RAG mini-project

A two-source Retrieval-Augmented-Generation system for the course mini-project.

- **PDF source:** Warhammer 40k Core Rules (`rag/data/raw/Core Rules.pdf`)
- **SQL source:** `rag/data/raw/wahadb.sqlite` (21 tables of Warhammer 40k rules/datasheets)
- **Router agent** picks which source to query per question.

## Quick start

```bash
uv sync                                       # installs everything from uv.lock
cp .env.example .env && $EDITOR .env          # paste GOOGLE_API_KEY
make test                                     # 163 passed, 1 skipped
make sanity                                   # the 4 teacher sanity questions (Lecture 1 PDF p. 42)
make demo                                     # 4 scripted turns across pdf / sql / both / follow-up
make chat                                     # multi-turn CLI with /zh /fr /en translation
make eval-e2e                                 # 36-question RAGAS run (results checked in)
```

### Grading rubric → where to find the evidence

The grading breakdown is 8 points across five areas (Lecture 1 PDF, p. 6). The table points
each one at the files that back it up.

| Rubric item | Where in the repo |
|---|---|
| **RAG Setup** | [`parser/`](rag/src_rag/parser/) (docling) → [`chunker/`](rag/src_rag/chunker/) (section-aware) → [`retriever/pdf.py`](rag/src_rag/retriever/pdf.py) (Chroma + bge-small, query prefix, section-prepended) + [`retriever/sql*.py`](rag/src_rag/retriever/) (text-to-SQL, data dictionary, few-shot, read-only connection) + [`chatbot/router.py`](rag/src_rag/chatbot/router.py) + [`chatbot/app.py`](rag/src_rag/chatbot/app.py) |
| **Evaluation and monitoring** | [`evaluation/pdf_eval.py`](rag/src_rag/evaluation/pdf_eval.py) (Hit@5, MRR) + [`evaluation/sql_eval.py`](rag/src_rag/evaluation/sql_eval.py) (exact / relaxed) + [`evaluation/e2e_eval.py`](rag/src_rag/evaluation/e2e_eval.py) (RAGAS over 36 mixed questions) + [`e2e_report.md`](rag/data/eval_results/e2e_report.md) + [`e2e_analysis.md`](rag/data/eval_results/e2e_analysis.md); `GeminiLlm` records per-call usage via `llm.usage()` |
| **Advanced RAG** | LLM-driven router with JSON-enum output (Lecture 3 routing / Lecture 4 agentic); `both` routing *splits* the question into a `pdf_question` + `sql_question` (query decomposition); multi-turn follow-ups are *contextualized* into standalone questions before routing (query rewriting). All in [`chatbot/`](rag/src_rag/chatbot/). |
| **Interface** | `make chat` multi-turn CLI with `/help` `/history` `/last` `/sources` (links the answer back to its PDF page / SQL — the UI point from Lecture 1), `/zh` `/fr` `/en` translation (nice-to-have from Lecture 1 PPT), `/reset`, `/quit`. See [`chatbot/app.py`](rag/src_rag/chatbot/app.py). |
| **Code quality** | 163 unit tests mirroring the source layout under [`tests/`](tests/); a single contract in [`interfaces.py`](rag/src_rag/interfaces.py) that both sides build against; `uv` + `Makefile` for one-command runs; read-only SQL connection; `.env` for secrets. |

All teacher-provided data (PDF, SQLite, data dictionary) is committed under
`rag/data/raw/`, so `git clone` + `uv sync` is enough to start. The LLM is
Google AI Studio (Gemini); get a free key at <https://aistudio.google.com/>.
Everything LLM-touching (`make chat`, `make demo`, `make eval-e2e`) needs
`GOOGLE_API_KEY`; `make test` and `make eval` don't.

## Architecture

```
Offline
  PDF -> docling -> section-aware chunks (261) -> bge-small embeddings -> ChromaDB
  SQLite + data dictionary -> schema text, join graph, value index; few-shot examples

Online (one chat turn)
                     user question + prior turns
                                 │
                                 ▼
            ┌────────── contextualize (LLM) ──────────┐
            │  rewrites a follow-up ("what about     │
            │  Orks?") into a standalone question    │
            └─────────────────┬───────────────────────┘
                              ▼
                        LLM router (JSON)
                   schema={source: pdf|sql|both,
                           rationale, pdf_question?,
                           sql_question?}
                   on error → defaults to pdf
                              │
       ┌──────────────────────┼─────────────────────────┐
       ▼                  both: router splits           ▼
    pdf path          into pdf_question + sql_question  sql path
       │                      │          │                │
       │                      ▼          ▼                │
       ▼              pdf retriever   text-to-SQL agent   ▼
  Chroma + bge-small     (top-5          prompt + schema      SQLite (ro)
  query prefix +         chunks,         context + few-shot   JOIN graph
  section-prepended      cites page      + value index        + fix-encoding
  k=5                    + section)      retry ≤3 on error    on text columns
       │                      │          │                │
       └──────────────────────┼──────────┼────────────────┘
                              ▼          ▼
                       LLM answer synthesizer
                 (per-source system prompt; cites PDF
                  pages, ends SQL answers with "Source:";
                  on LLM failure returns raw-dump fallback)
                              │
                              ▼
                   FinalAnswer(text, source,
                               pdf?, sql?, decision)
                              │
                              ▼
                      added to chat history
```

The two paths meet only at the contract in
[`rag/src_rag/interfaces.py`](rag/src_rag/interfaces.py). The router returns a
`RouterDecision`, the retrievers return `PdfRagResult` and `SqlRagResult`, the
synthesizer wraps everything in `FinalAnswer` — none of these types reference each
other's internals, so each side can evolve independently.

### Why these choices

- **One LLM wrapper, one cache.** `GeminiLlm` is threaded through the router, SQL
  agent and synthesizer, so retries, per-minute pacing and SHA-keyed caching
  apply once per prompt across the whole system. See
  [`rag/src_rag/llm/gemini.py`](rag/src_rag/llm/gemini.py).
- **Router returns JSON, enum-restricted.** `complete_json(prompt, schema)` with
  `source ∈ {pdf, sql, both}`. Few-shot examples live in
  [`router_examples.py`](rag/src_rag/chatbot/router_examples.py) (6 pdf + 6 sql
  + 3 both), separate from the prompt string.
- **"both" is split, not duplicated.** When the router returns `both`, it also
  returns `pdf_question` and `sql_question` — each retriever runs its own
  focused sub-query, which raises exact-match on the SQL side without
  overloading the PDF retriever with data-shaped text.
- **Soft failure, loud when it matters.** The router falls back to `pdf` on any
  LLM error; the SQL path packs its own LLM failures into `SqlRagResult.error`
  instead of crashing the turn; the synthesizer has a raw-dump fallback. The
  PDF indexer fails loud if the Chroma collection is empty — that's a setup
  bug, not a per-turn hiccup.
- **Read-only SQL.** `sqlite3.connect(..., mode=ro, uri=True)`; never writable
  from LLM-reachable code paths.
- **Multi-turn context.** `app.answer()` accepts `history: list[Turn]` and uses
  the LLM to turn follow-ups into standalone questions before the router sees
  them. The last 3 turns go into the synthesizer prompt so the answer tone
  continues the conversation. See
  [`rag/src_rag/chatbot/app.py`](rag/src_rag/chatbot/app.py).

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
    retriever/   # pdf.py (A), sql*.py (B), stubs.py
    llm/         # shared Google-AI-Studio wrapper
    chatbot/     # router.py + app.py (multi-turn chat, /zh translation) + demo.py + sanity.py (joint)
    evaluation/  # pdf_eval, sql_eval, e2e_eval (RAGAS) and question sets (joint)
    interfaces.py  # the contract — change only by consensus
tests/            # mirrors src_rag/
```

## Interface contract (summary)

See [`rag/src_rag/interfaces.py`](rag/src_rag/interfaces.py). The three functions each
side writes against:

| Function | Owner | Returns |
|---|---|---|
| `PdfRag(question, k=5)` | A | `PdfRagResult` — list of `PdfChunk(text, page, section, score)` |
| `SqlRag(question, max_rows=50)` | B | `SqlRagResult` — `sql`, `rows`, `columns`, optional `error`, `total_rows` |
| `route(question, llm)` | joint | `RouterDecision(source, rationale)`; for `both`, also `pdf_question`, `sql_question` |

Both sides have stub implementations in `rag/src_rag/retriever/stubs.py` so the
router and chat loop run end-to-end before either side is real.

## Setup

```bash
uv sync          # install everything from uv.lock
uv run pytest -q
```

Teacher-provided data (PDF, SQLite, data dictionary) is committed under
`rag/data/raw/`, so `git clone` + `uv sync` is enough to start.

Then copy `.env.example` to `.env` and set `GOOGLE_API_KEY` (Google AI Studio).

## Chat

```bash
make chat
```

Multi-turn CLI. One LLM is shared across router, SQL agent and synthesizer, so
each turn is cheap when the prompt-hash cache hits. In-chat commands:

| Command | What it does |
|---|---|
| `/help` | list all commands |
| `/reset` | clear conversation history |
| `/history` | show prior turns |
| `/last` / `/sources` | show which chunks or SQL were used in the last answer |
| `/zh` `/fr` `/en` | translate the last answer (keeps `(p. XX)` citations) |
| `/quit` | leave (ctrl-D / ctrl-C also work) |

Two scripted runs are checked in so a reviewer can see the system behave without typing:

- `make demo` → four hand-picked turns across pdf, sql, both, and a multi-turn follow-up; transcript in [`DEMO.md`](DEMO.md).
- `make sanity` → the four questions the grader explicitly listed in Lecture 1 PDF p. 42
  (grenades, stratagem, score points, Space Marine toughness); transcript at the bottom of
  [`DEMO.md`](DEMO.md).

## Evaluation

Three layered evaluations, each `make`-able:

| Target | Scope | What it measures |
|---|---|---|
| `make eval` | PDF retriever alone, no LLM | Hit@5 and MRR against 20 hand-labelled questions in [`questions_pdf.jsonl`](rag/src_rag/evaluation/questions_pdf.jsonl) |
| `make eval-sql` | SQL agent alone | Execution accuracy (exact / relaxed) against gold queries |
| `make eval-e2e` | Router + both retrievers + answer, RAGAS judge | Router accuracy, retrieval hit@5, SQL match, faithfulness, answer relevancy / correctness, context precision / recall |

Headline from the latest end-to-end run (36 mixed questions,
`gemini-3.1-flash-lite`; full report at [`rag/data/eval_results/e2e_report.md`](rag/data/eval_results/e2e_report.md)):

| Metric | Overall | pdf (14) | sql (14) | both (8) |
|---|---|---|---|---|
| Router accuracy | 35/36 (0.972) | 14/14 | 13/14 | 8/8 |
| PDF section hit@5 | 22/22 (1.000) | 14/14 | — | 8/8 |
| SQL exact / relaxed match | 17/22 / 19/22 | — | 10/14 / 12/14 | 7/8 / 7/8 |
| RAGAS faithfulness | 0.900 | 0.935 | 0.858 | 0.914 |
| RAGAS answer_relevancy | 0.913 | 0.859 | 0.939 | 0.964 |
| RAGAS answer_correctness | 0.783 | 0.731 | 0.864 | 0.729 |
| RAGAS context_recall | 0.951 | 0.982 | 0.929 | 0.938 |

Three cases to read the failures from, discussed in
[`e2e_analysis.md`](rag/data/eval_results/e2e_analysis.md): a `both`-routed SQL query that
dropped a Fight-phase filter; a `Stealth` ability missed because the few-shot patterns don't
cover "units with ability X"; a parsing bug on the wound-roll table (dice images → "+").
The 0.021 context-precision figure on `both` is a measurement artefact — RAGAS judges each
chunk against the full answer, so one chunk never looks fully useful for a two-part answer.
Section hit@5 is still 8/8.

## Team

- **A — Yawen Zhang** ([@nanfanggaosu](https://github.com/nanfanggaosu))
- **B — Ruxin Xie** ([@xieruxin922](https://github.com/xieruxin922))

## Make targets

| Command | What it does |
|---|---|
| `make parse` | Run docling on `rag/data/raw/*.pdf` |
| `make chunk` | Chunk the parsed JSON into `rag/data/chunks.jsonl` |
| `make index` | Embed chunks into the Chroma vector DB |
| `make chat`  | Launch the multi-turn chat loop (CLI) |
| `make demo`  | Run the scripted 4-step demo (pdf / sql / both / follow-up) |
| `make sanity` | Run the four teacher sanity questions (Lecture 1 PDF p. 42) |
| `make eval`  | Run the PDF retrieval evaluation (no LLM calls) |
| `make eval-sql` | Run the SQL execution-accuracy evaluation |
| `make eval-e2e` | Run the end-to-end RAGAS evaluation, written to `rag/data/eval_results/` |
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
- **Vector DB:** ChromaDB, for simplicity.
- **RAGAS install:** `pyproject.toml` drops `scikit-network` (no Windows wheel on Python
  3.14, only used for test-set generation) and keeps `langchain-community<0.4` (ragas 0.4
  imports a module removed in 0.4).
- **Model for evaluation:** `gemini-3.1-flash-lite` (free tier: 15 requests per minute, 500
  per day), because `gemini-3.5-flash` allows only 5 per minute and about 20 per day, while one
  end-to-end run needs about 410 calls. `gemini-3.5-flash` is currently served by
  `gemini-3.6-flash`. Results and analysis are in `rag/data/eval_results/`.
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
- **PDF eval set (phase-1 baseline, 2026-11-01):** 20 hand-labelled questions in
  `rag/src_rag/evaluation/questions_pdf.jsonl`, each with expected page(s) and
  section(s). Current baseline on `chroma+bge-small` + query prefix + section
  prepended, k=5:

  | Metric | Score |
  |---|---|
  | Hit@5 (section) | 100% |
  | Hit@5 (page)    | 100% |
  | MRR@5 (section) | 0.938 |

  Only misses (rank > 1):
  - `saving-throw` (rank 4): "What happens on a save roll?" — the token "roll"
    pulls top-3 to `COMMAND RE-ROLL` / `ROLL-OFFS` / `RE-ROLLS` instead of
    `4. SAVING THROW` (p22). Classic dense-only term-matching failure.
  - `battle-shock` (rank 2): top-1 is `INSANE BRAVERY` (p42, which discusses
    battle-shock mechanics) rather than the main `2. BATTLE-SHOCK` entry (p11).
    Topic is correct, section label isn't.

  Candidate fix if these recur: BM25 + RRF hybrid (lecture 3). Not doing it
  yet — need more labelled failures first. Run `make eval` to reproduce.
- **LLM provider:** Google AI Studio (per teacher's grading convention).
- **SQL connection:** must be opened with `mode=ro`. Never writable from
  LLM-reachable code paths.
- **Out of scope:** ColBERT / late interaction (teacher said so in lecture 3).

## Open questions

- How many chunks `k` for the first retrieval pass? Current default `k=5`; try
  `k=20` + re-rank to 5 once we have an LLM reranker wired.
- Does the final answer always cite its source (page / SQL query)? Likely yes
  — important for the UI.
- Track PDF eval failures per category (fixed-term vs. descriptive, single-section
  vs. multi-section).
