"""Evaluate the PDF retriever against a hand-labelled question set.

Metrics (all macro-averaged over the question set):
  - Hit@k (section): fraction of questions where any of the top-k chunks has a
    section matching an expected section.
  - Hit@k (page):    same, but matching a page in expected_pages.
  - MRR (section):   1 / rank of the first section-matching chunk (0 if none in top-k).

Why both page and section hits: section is the "topical" label the retriever's
embedding carries since the prepending change; page is a looser signal that
survives when sections overlap on the same spread.

Run:
    uv run python -m rag.src_rag.evaluation.pdf_eval
    uv run python -m rag.src_rag.evaluation.pdf_eval --k 5
    uv run python -m rag.src_rag.evaluation.pdf_eval --verbose
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from rag.src_rag.interfaces import PdfRag
from rag.src_rag.retriever.pdf import pdf_rag as default_pdf_rag

QUESTIONS_PATH = Path(__file__).resolve().parent / "questions_pdf.jsonl"


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    expected_pages: list[int]
    expected_sections: list[str]


def load_questions(path: Path = QUESTIONS_PATH) -> list[Question]:
    out = []
    for line in path.open():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        d = json.loads(line)
        out.append(
            Question(
                id=d["id"],
                question=d["question"],
                expected_pages=list(d.get("expected_pages") or []),
                expected_sections=[s.upper() for s in (d.get("expected_sections") or [])],
            )
        )
    return out


def _section_rank(chunks, expected: set[str]) -> int | None:
    """1-indexed rank of the first chunk whose section matches; None if no match."""
    for i, c in enumerate(chunks, start=1):
        if (c.section or "").upper() in expected:
            return i
    return None


def _page_hit(chunks, expected: set[int]) -> bool:
    return any(c.page in expected for c in chunks)


def evaluate(
    questions: list[Question] | None = None,
    *,
    pdf_rag: PdfRag = default_pdf_rag,
    k: int = 5,
    verbose: bool = False,
) -> dict:
    questions = questions if questions is not None else load_questions()
    n = len(questions)
    hits_section = hits_page = 0
    rr_sum = 0.0
    per_q = []
    for q in questions:
        res = pdf_rag(q.question, k=k)
        exp_sec = set(q.expected_sections)
        exp_pg = set(q.expected_pages)
        rank = _section_rank(res.chunks, exp_sec)
        pg_hit = _page_hit(res.chunks, exp_pg)
        if rank is not None:
            hits_section += 1
            rr_sum += 1.0 / rank
        if pg_hit:
            hits_page += 1
        per_q.append(
            {
                "id": q.id,
                "question": q.question,
                "section_rank": rank,
                "page_hit": pg_hit,
                "top": [
                    {"page": c.page, "section": c.section, "score": c.score}
                    for c in res.chunks[:3]
                ],
            }
        )

    summary = {
        "n": n,
        "k": k,
        f"hit@{k}_section": hits_section / n if n else 0.0,
        f"hit@{k}_page": hits_page / n if n else 0.0,
        f"mrr@{k}_section": rr_sum / n if n else 0.0,
    }
    if verbose:
        summary["per_question"] = per_q
    return summary


def _print_report(summary: dict) -> None:
    k = summary["k"]
    print(f"n={summary['n']}  k={k}")
    print(f"  Hit@{k} (section): {summary[f'hit@{k}_section']:.2%}")
    print(f"  Hit@{k} (page):    {summary[f'hit@{k}_page']:.2%}")
    print(f"  MRR@{k} (section): {summary[f'mrr@{k}_section']:.3f}")
    if "per_question" in summary:
        print("\nPer-question:")
        for r in summary["per_question"]:
            mark = "✓" if r["section_rank"] == 1 else ("~" if r["section_rank"] else "✗")
            print(
                f"  {mark} [{r['id']}] rank={r['section_rank']} "
                f"page_hit={r['page_hit']}  — {r['question']}"
            )
            for t in r["top"]:
                print(f"       p{t['page']:>2}  {t['section']!r}  score={t['score']:.3f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    _print_report(evaluate(k=args.k, verbose=args.verbose))


if __name__ == "__main__":
    main()
