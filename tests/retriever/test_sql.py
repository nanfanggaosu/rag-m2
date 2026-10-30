import pytest

from rag.src_rag.retriever.sql import run_sql


def test_select_returns_rows_and_columns():
    out = run_sql("SELECT Id, name FROM factions WHERE Id = 'ORK'")
    assert out.error is None
    assert out.columns == ["Id", "name"]
    assert out.rows == [{"Id": "ORK", "name": "Orks"}]
    assert out.elapsed_ms is not None


def test_cte_query_is_allowed():
    out = run_sql("WITH f AS (SELECT Id FROM factions) SELECT count(*) AS n FROM f")
    assert out.error is None
    assert out.rows == [{"n": 25}]


def test_rows_are_capped_at_max_rows():
    out = run_sql("SELECT DatasheetId FROM datasheets_stratagems", max_rows=7)
    assert out.error is None
    assert len(out.rows) == 7


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM factions",
        "DROP TABLE factions",
        "UPDATE factions SET name = 'x'",
        "INSERT INTO factions (Id) VALUES ('x')",
        "PRAGMA table_info(factions)",
        "ATTACH DATABASE ':memory:' AS other",
        "SELECT 1; DROP TABLE factions",
        "WITH x AS (SELECT 1) DELETE FROM factions",
    ],
)
def test_non_read_queries_are_rejected(sql):
    out = run_sql(sql)
    assert out.error
    assert out.rows == []
    assert run_sql("SELECT count(*) AS n FROM factions").rows == [{"n": 25}]


def test_unknown_column_reports_error():
    out = run_sql("SELECT no_such_column FROM factions")
    assert out.error and "no_such_column" in out.error


def test_slow_query_is_interrupted():
    out = run_sql(
        "SELECT count(*) FROM datasheets_stratagems a, datasheets_stratagems b",
        timeout_s=0.05,
    )
    assert out.error and "interrupted" in out.error
