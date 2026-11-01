"""SQL path: verified question -> SQL examples (few-shot pool + held-out eval set).

See the result:
    uv run python -m rag.src_rag.retriever.sql_examples                     # check every example
    uv run python -m rag.src_rag.retriever.sql_examples "How many points do Boyz cost?"
    uv run python -m rag.src_rag.retriever.sql_examples --update-expected   # after editing the JSON
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

from rapidfuzz import fuzz, process, utils

from rag.src_rag.interfaces import SqlRagResult
from rag.src_rag.retriever.sql import PROJECT_ROOT, run_sql

EXAMPLES_PATH = PROJECT_ROOT / "rag" / "data" / "sql_examples.json"
EXPECTED_MAX_ROWS = 100

Split = Literal["fewshot", "eval"]


@dataclass(frozen=True)
class SqlExample:
    id: str
    split: Split
    question: str
    sql: str
    notes: str
    expected: list[list[Any]] | None = None


def load_examples(split: Split | None = None) -> list[SqlExample]:
    raw = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
    examples = [SqlExample(**r) for r in raw]
    return [e for e in examples if split is None or e.split == split]


def result_rows(out: SqlRagResult) -> list[list[Any]]:
    return [[r[c] for c in out.columns] for r in out.rows]


def _norm(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def _row_key(row: list[Any]) -> tuple[str, ...]:
    return tuple(sorted(_norm(v) for v in row))


def results_match(expected: list[list[Any]], actual: list[list[Any]]) -> bool:
    """Execution-accuracy check: same multiset of rows, ignoring row order and column order.

    Column order and aliases are free choices of whoever wrote the SQL, so they don't count.
    """
    return Counter(map(_row_key, expected)) == Counter(map(_row_key, actual))


def results_contain(expected: list[list[Any]], actual: list[list[Any]]) -> bool:
    """Relaxed check: same number of rows, and each expected row's values appear in its own
    actual row, which may carry extra columns (e.g. an added Id or faction name)."""
    if len(expected) != len(actual):
        return False
    exp = [Counter(map(_norm, r)) for r in expected]
    act = [Counter(map(_norm, r)) for r in actual]
    owner: dict[int, int] = {}

    def assign(i: int, seen: set[int]) -> bool:
        for j, a in enumerate(act):
            if j not in seen and not exp[i] - a:
                seen.add(j)
                if j not in owner or assign(owner[j], seen):
                    owner[j] = i
                    return True
        return False

    return all(assign(i, set()) for i in range(len(exp)))


def check_example(example: SqlExample) -> tuple[bool, SqlRagResult]:
    out = run_sql(example.sql, max_rows=EXPECTED_MAX_ROWS)
    ok = out.error is None and example.expected is not None and results_match(
        example.expected, result_rows(out)
    )
    return ok, out


def select_examples(question: str, *, k: int = 3, split: Split = "fewshot") -> list[SqlExample]:
    """Most lexically similar examples; a stand-in until embedding search lands."""
    pool = load_examples(split)
    hits = process.extract(
        question, [e.question for e in pool], scorer=fuzz.token_sort_ratio,
        processor=utils.default_process, limit=k,
    )
    return [pool[idx] for _, _, idx in hits]


def render_examples(examples: list[SqlExample]) -> str:
    blocks = [f"Q: {e.question}\nSQL: {e.sql}\nNote: {e.notes}" for e in examples]
    return "EXAMPLES\n" + "\n\n".join(blocks) if blocks else ""


def update_expected() -> None:
    raw = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
    for r in raw:
        out = run_sql(r["sql"], max_rows=EXPECTED_MAX_ROWS)
        if out.error:
            raise RuntimeError(f"{r['id']}: {out.error}")
        r["expected"] = result_rows(out)
    EXAMPLES_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote expected results for {len(raw)} examples to {EXAMPLES_PATH.relative_to(PROJECT_ROOT)}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="*")
    parser.add_argument("--update-expected", action="store_true")
    args = parser.parse_args()

    if args.update_expected:
        update_expected()
    elif args.question:
        print(render_examples(select_examples(" ".join(args.question))))
    else:
        for e in load_examples():
            ok, out = check_example(e)
            print(f"{'PASS' if ok else 'FAIL'}  {e.id} [{e.split:7}] {len(out.rows):3} rows  {e.question}")


if __name__ == "__main__":
    main()
