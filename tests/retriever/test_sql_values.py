import pytest

from rag.src_rag.retriever.sql import run_sql
from rag.src_rag.retriever.sql_values import (
    INDEXED_COLUMNS,
    _sql_literal,
    load_value_index,
    match_values,
    render_value_hints,
)


def _found(question):
    return {(m.entry.table, m.entry.column, m.entry.display) for m in match_values(question)}


def test_index_covers_every_indexed_column():
    entries = load_value_index()
    columns = {(e.table, e.column) for e in entries}
    assert columns == {(ic.table, ic.column) for ic in INDEXED_COLUMNS}
    assert sum(e.table == "factions" for e in entries) == 25


def test_exact_multi_word_name_wins_over_its_parts():
    found = _found("What is the toughness of Warboss in Mega Armour?")
    assert ("datasheets", "name", "Warboss In Mega Armour") in found
    assert ("datasheets", "name", "Warboss") not in found


def test_typo_is_tolerated():
    assert ("datasheets", "name", "Warboss") in _found("what are the stats of the warbos")


def test_plural_finds_containing_names():
    matches = match_values("How many points do Intercessors cost?")
    partial = {m.entry.display for m in matches if m.partial and m.entry.table == "datasheets"}
    assert "Intercessor Squad" in partial


def test_generic_question_words_do_not_match():
    assert {m.entry.display for m in match_values("How many units have the Fly keyword?")} == {"Fly"}
    assert match_values("How does the game work?") == []


def test_mis_encoded_value_gets_like_condition():
    m = next(
        m for m in match_values("What is the wound characteristic of a C'tan Shard of the Nightbringer?")
        if m.entry.table == "datasheets"
    )
    assert m.entry.sql_condition == "datasheets.name LIKE 'C%tan Shard of the Nightbringer'"


@pytest.mark.parametrize(
    "question",
    [
        "Which stratagems can the Warboss use in the Shooting phase?",
        "What is the wound characteristic of a C'tan Shard of the Nightbringer?",
        "What enhancements are available in the Gladius Task Force detachment?",
        "Which units can take a lascannon?",
        "How many points do Intercessors cost?",
    ],
)
def test_every_suggested_condition_finds_rows(question):
    matches = match_values(question)
    assert matches
    for m in matches:
        out = run_sql(f"SELECT 1 FROM {m.entry.table} WHERE {m.entry.sql_condition} LIMIT 1")
        assert out.error is None and out.rows, m.entry.sql_condition


def test_render_shows_literal_and_ids():
    text = render_value_hints(match_values("List all Space Marines detachments"))
    assert "factions.name = 'Space Marines'" in text
    assert "Id 'SM'" in text
    assert render_value_hints([]) == ""


def test_sql_literal_escapes_quotes():
    assert _sql_literal("O'Brien") == "'O''Brien'"
