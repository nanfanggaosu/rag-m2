from pathlib import Path

import pytest

from rag.src_rag.chunker.chunk import chunk_parsed_json

PARSED = (
    Path(__file__).resolve().parents[2]
    / "rag" / "data" / "parsed" / "Core Rules.json"
)

pytestmark = pytest.mark.skipif(
    not PARSED.exists(),
    reason="Run `make parse` first; parsed JSON isn't on disk.",
)


@pytest.fixture(scope="module")
def chunks():
    return chunk_parsed_json(PARSED)


def test_emits_many_chunks(chunks):
    assert len(chunks) > 50


def test_every_chunk_has_text_and_page(chunks):
    for c in chunks:
        assert c.text.strip()
        assert c.page > 0


def test_sections_lost_by_md_are_recovered(chunks):
    """These were missing from the markdown export; chunker must keep them."""
    sections = [c.section or "" for c in chunks]
    for header in (
        "MISSION OBJECTIVES",
        "DETERMINE ATTACKER AND DEFENDER",
        "DECLARE BATTLE FORMATIONS",
        "DEPLOY ARMIES",
        "DETERMINE FIRST TURN",
        "RESOLVE PRE-BATTLE RULES",
    ):
        assert any(header in s for s in sections), (
            f"section header not referenced by any chunk: {header}"
        )


def test_no_boilerplate_leaks(chunks):
    joined = "\n".join(c.text for c in chunks)
    assert "CORE RULES |" not in joined, "page_footer leaked into chunk text"


def test_pages_cover_the_whole_book(chunks):
    pages = {c.page for c in chunks}
    assert min(pages) == 1
    assert max(pages) >= 55
