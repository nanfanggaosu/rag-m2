"""Turn docling's JSON output into retrieval-ready `PdfChunk`s.

Why we read JSON and not the .md: docling's markdown serializer loses section headers
on multi-column pages (verified with pypdfium2 as ground truth). The JSON preserves
every element with correct label, page, and bbox.

Chunking policy (phase 1 — recursive-ish, section-aware):
- iterate `texts` in docling's own reading order
- every `section_header` ends the current chunk and starts a new one
- `page_header` / `page_footer` are dropped (boilerplate like "CORE RULES | ...")
- lone decorative numerals ("1", "2", ...) next to step headers are dropped
- when a section is longer than `max_chars`, split into equal-section successive chunks
- tables (not in `texts`) are rendered to a tiny markdown table and emitted at their
  position on the page

Each chunk's section title lives in `PdfChunk.section` (metadata), not inlined into
the text — the orchestrator can prepend it when building the LLM prompt.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from rag.src_rag.interfaces import PdfChunk


INCLUDE_LABELS = {"text", "list_item", "caption", "section_header", "title"}
EXCLUDE_LABELS = {"page_header", "page_footer"}
_NUMERAL_RE = re.compile(r"^\d{1,3}$")
# docling sometimes merges a page footer into a running text block across pages;
# strip those lines from body text.
_FOOTER_LINE_RE = re.compile(r"^\s*CORE RULES\s*\|\s*.+$", re.MULTILINE)
# CJK ideographs / kana appear only as OCR mojibake in an English PDF — strip them.
# Non-CJK non-ASCII chars (■, ◦, ½, °, ∆) are kept: ■ marks list bullets and
# header pollution, the rest are legitimate symbols.
_CJK_RE = re.compile(r"[぀-ヿ一-鿿]")
# Section headers in this document are either ALL-CAPS titles, or (occasionally)
# Title-Case sidebar labels. These stop-words may legitimately appear inside a
# header without signalling body text.
_HEADER_STOP_WORDS = frozenset({
    "and", "or", "of", "the", "a", "an", "in", "on", "with", "by",
    "for", "to", "from", "your", "you",
})
# Bullets that signal "body/list content starts here" when found mid-header.
_HEADER_BULLETS_RE = re.compile(r"[•■◦]")  # • ■ ◦


def _strip_boilerplate(text: str) -> str:
    cleaned = _FOOTER_LINE_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _strip_cjk(text: str) -> str:
    return _CJK_RE.sub("", text)


def _clean_section_header(text: str) -> str:
    """Trim body text that docling glued onto a section_header (page-4 overview bug).

    Rules (fire in order):
      1. Truncate at the first bullet char (■ ◦ •); after a bullet the content
         is a list item that was glued on, not part of the title.
      2. Walk tokens left-to-right; the first fully-lowercase token that isn't a
         common stop-word marks where body text begins — truncate before it.
      3. Pop trailing isolated Title-Case tokens (sentence starters like "If",
         "Unit") that survived step 2.
    """
    text = _HEADER_BULLETS_RE.split(text, 1)[0].strip()
    kept: list[str] = []
    for tok in text.split():
        bare = re.sub(r"[^A-Za-z]", "", tok).lower()
        if bare and tok == tok.lower() and bare not in _HEADER_STOP_WORDS:
            break
        kept.append(tok)
    # Only strip trailing Title-Case tokens if the header has a real ALL-CAPS
    # prefix. Otherwise this is a legitimate Title-Case header like "Introduction".
    has_allcaps = any(len(t) > 1 and t.isupper() for t in kept)
    while kept and has_allcaps:
        last = kept[-1]
        if (
            len(last) > 1
            and last[0].isupper()
            and not last.isupper()
            and last[1:].islower()
        ):
            kept.pop()
        else:
            break
    return " ".join(kept).strip()


def _page(elem: dict) -> int | None:
    prov = elem.get("prov") or []
    return prov[0]["page_no"] if prov else None


def _bbox_key(elem: dict) -> tuple[int, float, float]:
    prov = elem.get("prov") or []
    if not prov:
        return (0, 0.0, 0.0)
    bb = prov[0]["bbox"]
    return (prov[0]["page_no"], -float(bb["t"]), float(bb["l"]))


def _render_table(tab: dict) -> str:
    cells = tab.get("data", {}).get("table_cells", [])
    if not cells:
        return ""
    rows: dict[int, list[tuple[int, str]]] = {}
    for c in cells:
        r = c.get("start_row_offset_idx", 0)
        rows.setdefault(r, []).append(
            (c.get("start_col_offset_idx", 0), _strip_cjk(c.get("text", "")))
        )
    return "\n".join(
        " | ".join(t for _, t in sorted(rows[r])) for r in sorted(rows)
    )


def chunk_parsed_json(path: Path, *, max_chars: int = 1200) -> list[PdfChunk]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    texts = data.get("texts", [])
    tables = sorted(data.get("tables", []), key=_bbox_key)

    chunks: list[PdfChunk] = []
    section: str | None = None
    buf: list[str] = []
    pages: set[int] = set()
    tab_i = 0

    def flush() -> None:
        if not buf:
            return
        body = "\n".join(buf).strip()
        if body:
            chunks.append(
                PdfChunk(
                    chunk_id=f"pdf-{len(chunks):04d}",
                    text=body,
                    page=min(pages) if pages else 0,
                    section=section,
                )
            )
        buf.clear()
        pages.clear()

    def emit_pending_tables_up_to(elem: dict) -> None:
        nonlocal tab_i
        key_here = _bbox_key(elem)
        while tab_i < len(tables) and _bbox_key(tables[tab_i]) <= key_here:
            md = _render_table(tables[tab_i])
            tp = _page(tables[tab_i])
            if md:
                buf.append(md)
                if tp:
                    pages.add(tp)
            tab_i += 1

    for elem in texts:
        label = elem.get("label")
        if label in EXCLUDE_LABELS or label not in INCLUDE_LABELS:
            continue
        txt = _strip_cjk((elem.get("text") or "")).strip()
        page = _page(elem)

        emit_pending_tables_up_to(elem)

        if label in ("section_header", "title"):
            new_section = _clean_section_header(txt) or None
            if buf:
                flush()
                section = new_section
            else:
                # No body for the previous section; chain so the parent isn't lost.
                section = (
                    f"{section} / {new_section}" if section and new_section else new_section
                )
            continue

        if not txt or _NUMERAL_RE.match(txt):
            continue

        cleaned = _strip_boilerplate(txt)
        if not cleaned:
            continue
        buf.append(f"- {cleaned}" if label == "list_item" else cleaned)
        if page:
            pages.add(page)

        if sum(len(x) for x in buf) >= max_chars:
            flush()

    # trailing tables + remainder
    while tab_i < len(tables):
        md = _render_table(tables[tab_i])
        tp = _page(tables[tab_i])
        if md:
            buf.append(md)
            if tp:
                pages.add(tp)
        tab_i += 1
    flush()
    return chunks


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    src = root / "rag" / "data" / "parsed" / "Core Rules.json"
    out = root / "rag" / "data" / "chunks.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    chunks = chunk_parsed_json(src)
    with out.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(
                {
                    "chunk_id": c.chunk_id,
                    "text": c.text,
                    "page": c.page,
                    "section": c.section,
                },
                ensure_ascii=False,
            ) + "\n")
    print(f"wrote {len(chunks)} chunks -> {out.relative_to(root)}")


if __name__ == "__main__":
    main()
