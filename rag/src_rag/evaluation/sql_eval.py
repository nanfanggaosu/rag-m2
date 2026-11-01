"""Evaluate the SQL path on the held-out questions (execution accuracy).

    uv run python -m rag.src_rag.evaluation.sql_eval
    uv run python -m rag.src_rag.evaluation.sql_eval --out sql_eval_results.json

Only the `eval` split is scored: the `fewshot` split feeds the prompt, so scoring it would
let the model copy its own answer.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from rag.src_rag.interfaces import SqlRag
from rag.src_rag.retriever.sql_examples import (
    EXPECTED_MAX_ROWS,
    SqlExample,
    load_examples,
    result_rows,
    results_contain,
    results_match,
)


@dataclass(frozen=True)
class EvalRow:
    id: str
    question: str
    exact: bool
    relaxed: bool
    attempts: int
    error: str | None
    sql: str
    elapsed_ms: float


def evaluate(rag: SqlRag, examples: list[SqlExample]) -> list[EvalRow]:
    rows = []
    for ex in examples:
        out = rag(ex.question, max_rows=EXPECTED_MAX_ROWS)
        actual = result_rows(out)
        rows.append(EvalRow(
            id=ex.id,
            question=ex.question,
            exact=out.error is None and results_match(ex.expected, actual),
            relaxed=out.error is None and results_contain(ex.expected, actual),
            attempts=len(getattr(rag, "last_attempts", [])) or 1,
            error=out.error,
            sql=out.sql,
            elapsed_ms=out.elapsed_ms or 0.0,
        ))
    return rows


def summarize(rows: list[EvalRow]) -> dict[str, float]:
    n = len(rows)
    return {
        "questions": n,
        "exact_accuracy": sum(r.exact for r in rows) / n,
        "relaxed_accuracy": sum(r.relaxed for r in rows) / n,
        "errors": sum(r.error is not None for r in rows),
        "avg_attempts": sum(r.attempts for r in rows) / n,
        "avg_elapsed_ms": sum(r.elapsed_ms for r in rows) / n,
    }


def main() -> None:
    from rag.src_rag.llm.gemini import GeminiLlm
    from rag.src_rag.retriever.sql_rag import SqlRag as GeminiSqlRag

    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--out", type=Path, help="also write per-question results as JSON")
    args = parser.parse_args()

    llm = GeminiLlm(use_cache=not args.no_cache)
    rows = evaluate(GeminiSqlRag(llm), load_examples("eval"))
    for r in rows:
        mark = "PASS" if r.exact else ("~ok" if r.relaxed else "FAIL")
        print(f"{mark:4}  {r.id}  attempts={r.attempts}  {r.question}")
        if not r.exact:
            print(f"        sql: {r.sql}")
            if r.error:
                print(f"        error: {r.error}")

    summary = summarize(rows)
    print("\nSUMMARY " + json.dumps(summary, indent=2))
    print(f"LLM usage {llm.usage()}")
    if args.out:
        args.out.write_text(json.dumps(
            {"model": llm.model, "summary": summary, "rows": [asdict(r) for r in rows]},
            ensure_ascii=False, indent=2,
        ), encoding="utf-8")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
