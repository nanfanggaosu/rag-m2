"""LLM-driven router: classify a question as pdf-rules, sql-data, or both.

Uses `llm.complete_json` with an enum-restricted schema plus few-shot examples
from `router_examples.py`. On any error — bad JSON, invalid source, API
failure — falls back to the PDF path: rules questions are the more common
case and the rulebook is a safer place to look than a possibly-wrong SQL
query.
"""
from __future__ import annotations

import json
from typing import Any

from rag.src_rag.chatbot.router_examples import EXAMPLES
from rag.src_rag.interfaces import Llm, RouterDecision

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "source": {"type": "string", "enum": ["pdf", "sql", "both"]},
        "rationale": {"type": "string"},
        "pdf_question": {"type": "string"},
        "sql_question": {"type": "string"},
    },
    "required": ["source", "rationale"],
}

_SYSTEM = (
    "You route Warhammer 40k Q&A to one of two retrieval backends.\n"
    "- pdf: rules, mechanics, phases, keywords, abilities, actions "
    "(the Core Rules PDF).\n"
    "- sql: faction/unit/datasheet/stratagem/enhancement lookups by name, "
    "counts, points costs (the SQLite datasheets DB), including lookups that only "
    "mention a phase or rule as a filter.\n"
    "- both: the question needs a rule explanation AND a specific "
    "unit/data lookup. Then also give pdf_question (the rule part alone) and "
    "sql_question (the data part alone), each understandable on its own and "
    "keeping every condition from the original question (faction, unit, phase, "
    "numbers) in the part it belongs to.\n"
    "Return JSON only."
)


def _build_prompt(question: str) -> str:
    lines = [_SYSTEM, "", "Examples:"]
    for ex in EXAMPLES:
        lines.append(f"Q: {ex.question}")
        reply = {"source": ex.source, "rationale": ex.rationale}
        if ex.source == "both":
            reply |= {"pdf_question": ex.pdf_question, "sql_question": ex.sql_question}
        lines.append(f"A: {json.dumps(reply)}")
    lines.append("")
    lines.append(f"Q: {question}")
    lines.append("A:")
    return "\n".join(lines)


def route(question: str, llm: Llm) -> RouterDecision:
    prompt = _build_prompt(question)
    try:
        resp = llm.complete_json(prompt, _SCHEMA)
    except Exception as e:
        return RouterDecision(
            source="pdf", rationale=f"router error, defaulting to pdf: {e}"
        )
    source = resp.get("source")
    if source not in ("pdf", "sql", "both"):
        return RouterDecision(
            source="pdf",
            rationale=f"invalid source {source!r} from LLM, defaulting to pdf",
        )
    if source != "both":
        return RouterDecision(source=source, rationale=resp.get("rationale") or "")
    return RouterDecision(
        source=source,
        rationale=resp.get("rationale") or "",
        pdf_question=resp.get("pdf_question") or None,
        sql_question=resp.get("sql_question") or None,
    )
