"""SQL path (partner B): text-to-SQL over wahadb.sqlite, conforming to `interfaces.SqlRag`.

Pipeline: match values -> assemble prompt (rules, schema, values, few-shot examples)
-> LLM writes SQL -> run read-only -> on error or empty result, feed it back and retry.

Try it:
    uv run python -m rag.src_rag.retriever.sql_rag "How many points do Boyz cost?"
    uv run python -m rag.src_rag.retriever.sql_rag --show-prompt "Which units can a Hive Tyrant lead?"
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field

from rag.src_rag.interfaces import Llm, SqlRagResult
from rag.src_rag.retriever.sql import run_sql
from rag.src_rag.retriever.sql_examples import render_examples, select_examples
from rag.src_rag.retriever.sql_schema import render_schema
from rag.src_rag.retriever.sql_values import match_values, render_value_hints

MAX_ATTEMPTS = 3
N_EXAMPLES = 3

RULES = """\
You write SQLite queries for a Warhammer 40,000 rules database.
Write ONE read-only query (SELECT or WITH) that answers the question.

RULES
- Every column is TEXT. CAST(x AS INTEGER) before numeric comparison, ordering or arithmetic;
  strip the inch mark first for movement, e.g. CAST(REPLACE(m, '"', '') AS INTEGER).
- Join only on the id columns listed under JOINS. When the user names a faction, join
  factions and filter on factions.name.
- Use the literals listed under VALUES. '→' entries are exact matches; '≈' entries are
  candidates, pick the one that fits the question.
- Columns marked ALWAYS EMPTY must not be used. Text marked as mis-encoded must be matched with LIKE.
- Rows are often repeated across detachments or sources: use DISTINCT or count(DISTINCT ...).
- For most/least/highest/lowest questions return every tied row (compare with max()/min()),
  not LIMIT 1, unless the question asks for a fixed number of results.
- In datasheets_models_cost, rows with an empty cost are tier headers ('YOUR UNIT COSTS',
  'YOUR 1ST TO 3RD UNITS COST', ...). Each price belongs to the nearest header above it by line.
- Exclude datasheets.virtual = 'true' when counting or listing datasheets.
- Return only the columns needed to answer, using names rather than ids.
- Add LIMIT {max_rows} unless the query already returns few rows."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string", "description": "Tables, joins and filters needed, briefly."},
        "sql": {"type": "string"},
    },
    "required": ["reasoning", "sql"],
}


@dataclass(frozen=True)
class Attempt:
    sql: str
    reasoning: str
    result: SqlRagResult


def build_prompt(question: str, *, max_rows: int, feedback: list[Attempt] = ()) -> str:
    parts = [
        RULES.format(max_rows=max_rows),
        "SCHEMA\n" + render_schema(),
        render_value_hints(match_values(question)),
        render_examples(select_examples(question, k=N_EXAMPLES)),
    ]
    for a in feedback:
        problem = a.result.error or "the query ran but returned no rows"
        parts.append(
            f"PREVIOUS ATTEMPT\nSQL: {a.sql}\nPROBLEM: {problem}\n"
            "Fix the query. If you are sure the correct answer is empty, return the same query."
        )
    parts.append(f"QUESTION: {question}")
    return "\n\n".join(p for p in parts if p)


@dataclass
class SqlRag:
    llm: Llm
    max_attempts: int = MAX_ATTEMPTS
    last_attempts: list[Attempt] = field(default_factory=list)

    def __call__(self, question: str, *, max_rows: int = 50) -> SqlRagResult:
        t0 = time.perf_counter()
        attempts: list[Attempt] = []
        for _ in range(self.max_attempts):
            reply = self.llm.complete_json(
                build_prompt(question, max_rows=max_rows, feedback=attempts), OUTPUT_SCHEMA
            )
            sql = str(reply.get("sql", "")).strip()
            result = run_sql(sql, max_rows=max_rows)
            attempts.append(Attempt(sql, str(reply.get("reasoning", "")), result))
            if result.error is None and (result.rows or _repeats_previous(attempts)):
                break
        self.last_attempts = attempts

        final = attempts[-1].result
        return SqlRagResult(
            sql=final.sql,
            rows=final.rows,
            columns=final.columns,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
            error=final.error,
        )


def _repeats_previous(attempts: list[Attempt]) -> bool:
    return len(attempts) > 1 and attempts[-1].sql == attempts[-2].sql


_default: SqlRag | None = None


def sql_rag(question: str, *, max_rows: int = 50) -> SqlRagResult:
    """Ready-to-use `SqlRag` backed by Gemini, for the router and chat app."""
    global _default
    if _default is None:
        from rag.src_rag.llm.gemini import GeminiLlm

        _default = SqlRag(GeminiLlm())
    return _default(question, max_rows=max_rows)


def main() -> None:
    from rag.src_rag.llm.gemini import GeminiLlm

    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="+")
    parser.add_argument("--show-prompt", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    question = " ".join(args.question)

    if args.show_prompt:
        print(build_prompt(question, max_rows=50), end="\n\n" + "=" * 80 + "\n")

    llm = GeminiLlm(use_cache=not args.no_cache)
    rag = SqlRag(llm)
    out = rag(question)
    for i, a in enumerate(rag.last_attempts, 1):
        status = a.result.error or f"{len(a.result.rows)} rows"
        print(f"ATTEMPT {i}: {status}\n  reasoning: {a.reasoning}\n  sql: {a.sql}\n")
    print("RESULT")
    print("  " + " | ".join(out.columns))
    for row in out.rows[:20]:
        print("  " + " | ".join(str(row[c]) for c in out.columns))
    if len(out.rows) > 20:
        print(f"  ... {len(out.rows) - 20} more rows")
    print(f"\n-- {out.elapsed_ms:.0f} ms, llm {llm.usage()}")


if __name__ == "__main__":
    main()
