"""SQL path: schema context (column docs + live value stats) and the join graph.

See the result:
    uv run python -m rag.src_rag.retriever.sql_schema                     # whole schema
    uv run python -m rag.src_rag.retriever.sql_schema datasheets stratagems
"""
from __future__ import annotations

import heapq
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache

from rag.src_rag.interfaces import SqlRagResult
from rag.src_rag.retriever.sql import PROJECT_ROOT, run_sql

DICTIONARY_PATH = PROJECT_ROOT / "rag" / "data" / "raw" / "SQL_AGENT_DATA_DICTIONARY.md"

ENUM_MAX_DISTINCT = 15
LONG_TEXT_AVG_LEN = 60
SAMPLE_COUNT = 3
SAMPLE_MAX_LEN = 40

# `factions` links to six tables, so without a penalty almost every pair of tables is two
# hops apart through it and the specific junction tables (e.g. datasheets_stratagems) lose ties.
_HUB_TABLES = frozenset({"factions"})
_HUB_WEIGHT = 2.0


@dataclass(frozen=True)
class Column:
    table: str
    name: str
    description: str | None
    n_nonempty: int
    n_distinct: int
    avg_len: float
    top_values: tuple[str, ...]

    @property
    def mis_encoded(self) -> bool:
        return any(fix_encoding(v) != v for v in self.top_values)


@dataclass(frozen=True)
class Table:
    name: str
    description: str | None
    n_rows: int
    columns: tuple[Column, ...]


@dataclass(frozen=True)
class JoinEdge:
    left_table: str
    left_column: str
    right_table: str
    right_column: str

    @property
    def tables(self) -> frozenset[str]:
        return frozenset({self.left_table, self.right_table})

    @property
    def sql(self) -> str:
        return f"{self.left_table}.{self.left_column} = {self.right_table}.{self.right_column}"


def fix_encoding(text: str) -> str:
    """Undo UTF-8-read-as-Latin-1 mojibake (e.g. 'playerâ\\x80\\x99s' -> 'player’s')."""
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _query(sql: str, max_rows: int = 1000) -> SqlRagResult:
    out = run_sql(sql, max_rows=max_rows)
    if out.error:
        raise RuntimeError(f"{out.error}\n{sql}")
    return out


@cache
def _dictionary() -> tuple[dict[str, str], dict[str, dict[str, str]], tuple[JoinEdge, ...]]:
    text = DICTIONARY_PATH.read_text(encoding="utf-8")
    table_docs = dict(re.findall(r"^\| `(\w+)` \| \d+ \| (.+?) \|$", text, re.M))

    column_docs: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in text.split("## Relationship map")[0].splitlines():
        if m := re.match(r"^### `(\w+)`$", line):
            current = column_docs.setdefault(m[1], {})
        elif current is not None and (m := re.match(r"^- `(\w+)` — (.+)$", line)):
            current[m[1]] = m[2]

    edges = tuple(
        JoinEdge(*m) for m in re.findall(r"^- `(\w+)\.(\w+)` -> `(\w+)\.(\w+)`$", text, re.M)
    )
    return table_docs, column_docs, edges


def _column_stats(table: str, column: str) -> tuple[int, int, float, tuple[str, ...]]:
    c = f'"{column}"'
    stats = _query(
        f"SELECT count(nullif({c}, '')) AS nonempty, count(DISTINCT nullif({c}, '')) AS n_distinct, "
        f"avg(length(nullif({c}, ''))) AS avg_len FROM \"{table}\""
    ).rows[0]
    top = _query(
        f"SELECT {c} AS v FROM \"{table}\" WHERE {c} != '' "
        f"GROUP BY {c} ORDER BY count(*) DESC, {c} LIMIT {ENUM_MAX_DISTINCT}"
    ).rows
    return stats["nonempty"], stats["n_distinct"], stats["avg_len"] or 0.0, tuple(str(r["v"]) for r in top)


@cache
def load_schema() -> dict[str, Table]:
    """Live tables and columns, annotated with the data dictionary and value statistics."""
    table_docs, column_docs, _ = _dictionary()
    names = [r["name"] for r in _query(
        "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).rows]

    schema: dict[str, Table] = {}
    for t in names:
        live_columns = _query(f'SELECT * FROM "{t}" LIMIT 0').columns
        n_rows = _query(f'SELECT count(*) AS n FROM "{t}"').rows[0]["n"]
        docs = column_docs.get(t, {})
        columns = tuple(
            Column(t, col, docs.get(col), *_column_stats(t, col)) for col in live_columns
        )
        schema[t] = Table(t, table_docs.get(t), n_rows, columns)
    return schema


def join_edges() -> list[JoinEdge]:
    return list(_dictionary()[2])


@cache
def _graph() -> dict[str, list[tuple[str, JoinEdge, float]]]:
    graph: dict[str, list[tuple[str, JoinEdge, float]]] = {t: [] for t in load_schema()}
    for e in join_edges():
        w = _HUB_WEIGHT if e.tables & _HUB_TABLES else 1.0
        graph[e.left_table].append((e.right_table, e, w))
        graph[e.right_table].append((e.left_table, e, w))
    return graph


def _nearest(sources: set[str], targets: set[str]) -> list[JoinEdge] | None:
    """Cheapest path from any source table to the closest target table (Dijkstra)."""
    graph = _graph()
    dist = {t: 0.0 for t in sources}
    prev: dict[str, tuple[str, JoinEdge]] = {}
    heap = [(0.0, t) for t in sorted(sources)]
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist[node]:
            continue
        if node in targets:
            path = []
            while node not in sources:
                node, edge = prev[node]
                path.append(edge)
            return path[::-1]
        for nb, edge, w in graph[node]:
            if d + w < dist.get(nb, float("inf")):
                dist[nb] = d + w
                prev[nb] = (node, edge)
                heapq.heappush(heap, (d + w, nb))
    return None


def join_path(tables: Iterable[str]) -> list[JoinEdge]:
    """Join edges connecting `tables`, adding intermediate tables when needed.

    Greedy Steiner tree: start from the first table and repeatedly attach the nearest
    remaining one. Tables with no join edges (e.g. `last_update`) are left out.
    """
    wanted = list(dict.fromkeys(tables))
    unknown = [t for t in wanted if t not in load_schema()]
    if unknown:
        raise ValueError(f"unknown tables: {unknown}")
    if not wanted:
        return []

    connected = {wanted[0]}
    remaining = set(wanted[1:])
    edges: list[JoinEdge] = []
    while remaining:
        path = _nearest(connected, remaining)
        if path is None:
            break
        for e in path:
            if e not in edges:
                edges.append(e)
            connected |= e.tables
        remaining -= connected
    return edges


def _render_value(v: str) -> str:
    v = fix_encoding(v)
    return repr(v if len(v) <= SAMPLE_MAX_LEN else v[: SAMPLE_MAX_LEN - 1] + "…")


def _render_column(c: Column, n_rows: int) -> str:
    line = f"  {c.name}"
    if c.description:
        line += f" — {c.description}"
    if c.n_nonempty == 0:
        return line + " [ALWAYS EMPTY, do not use]"

    notes = []
    if c.avg_len > LONG_TEXT_AVG_LEN:
        notes.append("free text")
    elif c.n_distinct <= ENUM_MAX_DISTINCT:
        notes.append("values: " + " | ".join(_render_value(v) for v in c.top_values))
    else:
        notes.append("e.g. " + " | ".join(_render_value(v) for v in c.top_values[:SAMPLE_COUNT]))
    if c.n_nonempty < n_rows:
        notes.append(f"empty in {n_rows - c.n_nonempty} rows")
    if c.mis_encoded:
        notes.append("punctuation is mis-encoded in stored text, match with LIKE")
    return f"{line} [{'; '.join(notes)}]"


def render_schema(tables: Iterable[str] | None = None) -> str:
    """Schema text for the prompt: all tables, or the given ones plus the tables needed to join them."""
    schema = load_schema()
    if tables is None:
        names = list(schema)
    else:
        names = list(dict.fromkeys(tables))
        names += [t for e in join_path(names) for t in sorted(e.tables) if t not in names]
        names = list(dict.fromkeys(names))

    blocks = []
    for name in names:
        t = schema[name]
        header = f"TABLE {t.name} ({t.n_rows} rows)" + (f" — {t.description}" if t.description else "")
        blocks.append("\n".join([header, *(_render_column(c, t.n_rows) for c in t.columns)]))

    edges = [e.sql for e in join_edges() if e.tables <= set(names)]
    if edges:
        blocks.append("JOINS (all values are TEXT, compare as strings)\n" + "\n".join(f"  {e}" for e in edges))
    return "\n\n".join(blocks)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    tables = sys.argv[1:] or None
    text = render_schema(tables)
    print(text)
    if tables:
        print("\nJOIN PATH")
        for e in join_path(tables):
            print(f"  {e.sql}")
    print(f"\n-- {len(text)} chars (~{len(text) // 4} tokens)")


if __name__ == "__main__":
    main()
