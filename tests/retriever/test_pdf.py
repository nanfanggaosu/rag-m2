from pathlib import Path

import pytest

from rag.src_rag.retriever.pdf import INDEX_DIR, pdf_rag

pytestmark = pytest.mark.skipif(
    not any(INDEX_DIR.rglob("*.sqlite3")),
    reason="vector index not built; run `make index` first.",
)


@pytest.fixture(scope="module")
def flying():
    return pdf_rag("How do flying models charge?", k=5)


def test_returns_requested_k(flying):
    assert len(flying.chunks) == 5


def test_each_chunk_has_valid_shape(flying):
    for c in flying.chunks:
        assert c.chunk_id
        assert c.text.strip()
        assert c.page > 0
        assert c.score is not None and 0.0 <= c.score <= 1.0


def test_top_result_is_flying_section(flying):
    top = flying.chunks[0]
    sect = (top.section or "").upper()
    assert "FLY" in sect or "CHARGE" in sect, (
        f"top chunk should be about flying/charging; got {top.section!r} on p{top.page}"
    )


def test_fight_phase_question_hits_fight_pages():
    r = pdf_rag("How do melee attacks resolve in the fight phase?", k=5)
    pages = [c.page for c in r.chunks]
    # Fight phase lives on pp 32-34
    assert any(32 <= p <= 34 for p in pages), f"expected a fight-phase page, got {pages}"


def test_scores_are_descending():
    r = pdf_rag("stratagems command points", k=5)
    scores = [c.score for c in r.chunks]
    assert scores == sorted(scores, reverse=True), f"scores not descending: {scores}"
