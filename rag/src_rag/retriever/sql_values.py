"""SQL path: value index — map names mentioned in a question to exact stored literals.

See the result:
    uv run python -m rag.src_rag.retriever.sql_values                          # index stats
    uv run python -m rag.src_rag.retriever.sql_values "How many points do Intercessors cost?"
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from functools import cache

from rapidfuzz import fuzz, process, utils

from rag.src_rag.retriever.sql import run_sql
from rag.src_rag.retriever.sql_schema import fix_encoding

FUZZY_CUTOFF = 88.0
MAX_SPAN_WORDS = 8
MAX_PARTIAL_PER_SPAN = 5
PARTIAL_MIN_COVERAGE = 0.5
MAX_MATCHES = 15
MAX_IDS_SHOWN = 3


@dataclass(frozen=True)
class IndexedColumn:
    table: str
    column: str
    id_column: str | None = None
    faction_column: str | None = None


INDEXED_COLUMNS = (
    IndexedColumn("factions", "name", "Id"),
    IndexedColumn("datasheets", "name", "Id", "factionId"),
    IndexedColumn("stratagems", "name", "id", "FactionId"),
    IndexedColumn("detachments", "name", "Id", "factionId"),
    IndexedColumn("enhancements", "name", "id", "FactionId"),
    IndexedColumn("abilities", "name", "Id", "factionId"),
    IndexedColumn("detachment_abilities", "name", "Id", "factionId"),
    IndexedColumn("datasheets_keywords", "keyword"),
    IndexedColumn("datasheets_wargear", "name"),
    IndexedColumn("datasheets_abilities", "name"),
)

# Question words that would otherwise fuzzy-match stored names (e.g. "keyword" -> 'KEYWORDS').
STOPWORDS = frozenset("""
a an the of in on at to for with and or is are was were be do does did can could will would
what which who whose how many much list all any each every have has had there their this that
these those it its me my i you your show give tell find get use used using from by as about than
more most less least number count total per into out up only also not no some other
unit units datasheet datasheets model models stratagem stratagems faction factions detachment
detachments enhancement enhancements ability abilities keyword keywords weapon weapons wargear
point points cost costs stat stats profile profiles phase toughness save wound wounds movement
leadership attack attacks damage strength range rule rules army armies card cards
shooting shoot fight fighting charge command turn round battle battlefield enemy opponent
friendly take available characteristic characteristics value values type types name names
""".split())


@dataclass(frozen=True)
class ValueEntry:
    table: str
    column: str
    value: str
    ids: tuple[str, ...]
    factions: tuple[str, ...]
    n_rows: int

    @property
    def display(self) -> str:
        return fix_encoding(self.value)

    @property
    def sql_condition(self) -> str:
        """Condition that matches the stored text, even when its punctuation is mis-encoded."""
        target = f"{self.table}.{self.column}"
        if self.display != self.value:
            pattern = re.sub(r"[^\x00-\x7f]+", "%", self.display)
            return f"{target} LIKE {_sql_literal(pattern)}"
        return f"{target} = {_sql_literal(self.value)}"


@dataclass(frozen=True)
class ValueMatch:
    span: str
    entry: ValueEntry
    score: float
    partial: bool


def _sql_literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def _split(text: str) -> list[str]:
    return utils.default_process(text).split()


@cache
def load_value_index() -> tuple[ValueEntry, ...]:
    entries = []
    for ic in INDEXED_COLUMNS:
        col = f'"{ic.column}"'
        ids = f'group_concat(DISTINCT "{ic.id_column}")' if ic.id_column else "''"
        facs = f'group_concat(DISTINCT "{ic.faction_column}")' if ic.faction_column else "''"
        out = run_sql(
            f'SELECT {col} AS v, {ids} AS ids, {facs} AS facs, count(*) AS n FROM "{ic.table}" '
            f"WHERE {col} != '' GROUP BY {col}",
            max_rows=100_000,
        )
        if out.error:
            raise RuntimeError(out.error)
        for r in out.rows:
            entries.append(ValueEntry(
                ic.table, ic.column, r["v"],
                tuple(x for x in (r["ids"] or "").split(",") if x),
                tuple(sorted({x for x in (r["facs"] or "").split(",") if x})),
                r["n"],
            ))
    return tuple(entries)


@cache
def _search_structures() -> tuple[list[str], list[tuple[str, ...]], dict[str, set[int]]]:
    entries = load_value_index()
    processed = [utils.default_process(e.display) for e in entries]
    stemmed = [tuple(_stem(w) for w in p.split()) for p in processed]
    by_word: dict[str, set[int]] = defaultdict(set)
    for i, words in enumerate(stemmed):
        for w in words:
            by_word[w].add(i)
    return processed, stemmed, by_word


def _contains(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    n = len(needle)
    return any(haystack[i:i + n] == needle for i in range(len(haystack) - n + 1))


def match_values(question: str, *, cutoff: float = FUZZY_CUTOFF) -> list[ValueMatch]:
    """Stored values the question refers to, best first.

    Two channels: whole-span fuzzy match (tolerates typos), then, for spans left unmatched,
    values that contain the span's words (so "Intercessors" finds 'Intercessor Squad').
    A span inside an already-matched longer span is skipped, so "Warboss in Mega Armour"
    does not also report 'Warboss'.
    """
    entries = load_value_index()
    processed, stemmed, by_word = _search_structures()
    words = _split(question)
    spans = [
        (i, j) for i in range(len(words))
        for j in range(i + 1, min(i + MAX_SPAN_WORDS, len(words)) + 1)
        if words[i] not in STOPWORDS and words[j - 1] not in STOPWORDS
    ]

    candidates = []
    for i, j in spans:
        for _, score, idx in process.extract(
            " ".join(words[i:j]), processed, scorer=fuzz.ratio, processor=None,
            score_cutoff=cutoff, limit=None,
        ):
            candidates.append((score, j - i, i, j, idx))
    candidates.sort(key=lambda c: (-c[0], -c[1], c[2]))

    covered: set[int] = set()
    accepted_spans: set[tuple[int, int]] = set()
    seen: set[int] = set()
    matches: list[ValueMatch] = []
    for score, _, i, j, idx in candidates:
        if idx in seen or ((i, j) not in accepted_spans and set(range(i, j)) <= covered):
            continue
        seen.add(idx)
        accepted_spans.add((i, j))
        covered |= set(range(i, j))
        matches.append(ValueMatch(" ".join(words[i:j]), entries[idx], score, partial=False))

    for i, j in sorted(spans, key=lambda s: (s[0] - s[1], s[0])):
        if set(range(i, j)) & covered:
            continue
        span = " ".join(words[i:j])
        needle = tuple(_stem(w) for w in words[i:j])
        pool = set.intersection(*(by_word.get(w, set()) for w in needle))
        # Coverage filter: an ordinary word ("work") is a small part of the names that contain
        # it ('KNIFE WORK'), while a real reference ("intercessors") is most of the name.
        hits = sorted(
            (idx for idx in pool
             if idx not in seen and _contains(stemmed[idx], needle)
             and len(span) >= PARTIAL_MIN_COVERAGE * len(processed[idx])),
            key=lambda idx: (len(processed[idx]), processed[idx]),
        )[:MAX_PARTIAL_PER_SPAN]
        if not hits:
            continue
        covered |= set(range(i, j))
        for idx in hits:
            seen.add(idx)
            score = 100.0 * len(span) / len(processed[idx])
            matches.append(ValueMatch(span, entries[idx], score, partial=True))

    return matches[:MAX_MATCHES]


def _render_match(m: ValueMatch) -> str:
    e = m.entry
    details = []
    if e.ids:
        shown = ", ".join(_sql_literal(x) for x in e.ids[:MAX_IDS_SHOWN])
        more = f" +{len(e.ids) - MAX_IDS_SHOWN} more" if len(e.ids) > MAX_IDS_SHOWN else ""
        details.append(f"Id {shown}{more}")
    if e.factions:
        details.append("faction " + ", ".join(e.factions))
    if not e.ids:
        details.append(f"{e.n_rows} rows")
    arrow = "≈" if m.partial else "→"
    return f'  "{m.span}" {arrow} {e.sql_condition}  ({"; ".join(details)})'


def render_value_hints(matches: list[ValueMatch]) -> str:
    if not matches:
        return ""
    lines = ["VALUES MENTIONED IN THE QUESTION (→ exact match, ≈ partial match; use these literals)"]
    lines += [_render_match(m) for m in matches]
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    question = " ".join(sys.argv[1:])
    if not question:
        counts: dict[str, int] = defaultdict(int)
        for e in load_value_index():
            counts[f"{e.table}.{e.column}"] += 1
        for name, n in counts.items():
            print(f"{name:32} {n:6} distinct values")
        print(f"{'total':32} {sum(counts.values()):6}")
        return
    print(render_value_hints(match_values(question)) or "(no values matched)")


if __name__ == "__main__":
    main()
