# AGENTS.md — rules for coding agents working on this project

Scope: this file is auto-loaded by coding agents (Claude Code, Codex, Cursor, etc.) every time
they operate on this repo. Keep it short.

## Project in one line
A two-source RAG system (PDF: Warhammer 40k Core Rules; SQLite:
`rag/data/raw/wahadb.sqlite`) with a router agent on top, built for the RAG course
mini-project. All teacher-provided inputs live under `rag/data/raw/`.

## Core rules
1. **Don't add unnecessary comments.** Only write a comment when the *why* is non-obvious.
   Never explain *what* code does — well-named identifiers already do that.
2. **Edit, don't duplicate.** Prefer modifying existing files over creating parallel ones.
   Never create a `foo_new.py` next to `foo.py`.
3. **Respect module boundaries.** The project is split into `parser / chunker / retriever /
   llm / chatbot / evaluation`. If a change crosses two modules, update the
   interface in `rag/src_rag/interfaces.py` first, then both sides.
4. **Tests mirror source layout.** For every file `rag/src_rag/<mod>/<file>.py` there is
   `tests/<mod>/test_<file>.py`. Add a test alongside any non-trivial code.
5. **Secrets live in `.env`.** Never hard-code API keys. Read them via `os.environ` and
   document the expected variable in `.env.example`.
6. **The SQL connection is read-only.** `sqlite3.connect("...?mode=ro", uri=True)`. Never open
   a writable connection from LLM-reachable code paths.
7. **Follow the pair's interface contract.** The two data paths (`pdf_rag`, `sql_rag`) must
   match the signatures in `rag/src_rag/interfaces.py` so the router works regardless of
   which side is still a stub.

## Dependencies & environment
- Package manager: **`uv`** (not pip, not conda).
- Add a runtime dep: `uv add <pkg>`. Add a dev dep: `uv add --dev <pkg>`.
- Sync after pulling: `uv sync`.
- Run anything: `uv run python ...` or `uv run pytest`.

## Make targets (short list)
- `make parse` — run docling on `rag/data/raw/*.pdf`
- `make index` — chunk + embed the parsed output into the vector DB
- `make chat`  — launch the chat UI
- `make eval`  — run the evaluation pipeline
- `make test`  — `uv run pytest`

## Non-goals
- Not building a general-purpose PDF parser. Rules specific to the Warhammer rulebook are OK.
- Not implementing ColBERT / late interaction (teacher explicitly said this is out of scope).
- Not wiring in multiple LLM providers. Google AI Studio only.
