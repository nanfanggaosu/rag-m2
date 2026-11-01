from pathlib import Path

import pytest

from rag.src_rag.evaluation.pdf_eval import evaluate, load_questions
from rag.src_rag.retriever.pdf import INDEX_DIR

pytestmark = pytest.mark.skipif(
    not any(INDEX_DIR.rglob("*.sqlite3")),
    reason="vector index not built; run `make index` first.",
)


def test_question_set_parses():
    qs = load_questions()
    assert len(qs) >= 5
    for q in qs:
        assert q.id and q.question
        assert q.expected_pages or q.expected_sections, (
            f"question {q.id!r} has no expected signal"
        )


def test_evaluate_runs_and_hits_most_questions():
    summary = evaluate(k=5)
    # Loose floor so a one-off regression on a single question doesn't fail
    # the suite, but a broken retriever still trips it.
    assert summary["hit@5_section"] >= 0.6, summary
    assert summary["mrr@5_section"] > 0.0
