import pytest

from rag.src_rag.retriever.sql import run_sql
from rag.src_rag.retriever.sql_schema import (
    fix_encoding,
    join_edges,
    join_path,
    load_schema,
    render_schema,
)


def _path_tables(edges):
    return set().union(*(e.tables for e in edges))


def test_schema_covers_every_live_table_and_column():
    schema = load_schema()
    assert len(schema) == 21
    for t in schema.values():
        live = run_sql(f'SELECT * FROM "{t.name}" LIMIT 0').columns
        assert [c.name for c in t.columns] == live
        assert all(c.description for c in t.columns), t.name


def test_table_stats_come_from_live_data():
    schema = load_schema()
    assert schema["factions"].n_rows == 25
    phase = next(c for c in schema["stratagems"].columns if c.name == "phase")
    assert "Shooting phase" in phase.top_values


def test_every_documented_join_matches_real_rows():
    edges = join_edges()
    assert len(edges) == 27
    for e in edges:
        out = run_sql(
            f'SELECT 1 FROM "{e.left_table}" l JOIN "{e.right_table}" r '
            f'ON l."{e.left_column}" = r."{e.right_column}" LIMIT 1'
        )
        assert out.error is None and out.rows, e.sql


def test_join_path_adds_junction_table():
    edges = join_path(["datasheets", "stratagems"])
    assert _path_tables(edges) == {"datasheets", "datasheets_stratagems", "stratagems"}


def test_join_path_prefers_junction_over_factions_hub():
    edges = join_path(["datasheets", "enhancements"])
    assert "factions" not in _path_tables(edges)


def test_join_path_connects_three_tables():
    edges = join_path(["factions", "datasheets", "datasheets_wargear"])
    assert _path_tables(edges) == {"factions", "datasheets", "datasheets_wargear"}
    assert len(edges) == 2


def test_join_path_edge_cases():
    assert join_path(["datasheets"]) == []
    assert join_path(["datasheets", "last_update"]) == []
    with pytest.raises(ValueError):
        join_path(["no_such_table"])


def test_render_subset_includes_only_needed_tables():
    text = render_schema(["datasheets", "stratagems"])
    assert "TABLE datasheets_stratagems" in text
    assert "TABLE enhancements" not in text
    assert "stratagems.id = datasheets_stratagems.stratagemId" in text


def test_render_flags_data_quirks():
    text = render_schema(["datasheets", "stratagems"])
    assert "role — role/category [ALWAYS EMPTY" in text
    assert "'Either player’s turn'" in text
    assert "empty in 67 rows" in text


def test_render_full_schema_lists_all_tables():
    text = render_schema()
    assert text.count("\nTABLE ") + text.startswith("TABLE ") == 21


def test_fix_encoding():
    assert fix_encoding("playerâ\x80\x99s") == "player’s"
    assert fix_encoding("plain") == "plain"
    assert fix_encoding("café") == "café"
