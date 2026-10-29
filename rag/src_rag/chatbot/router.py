"""Keyword-based router stub.

Phase-1 placeholder so the pipeline is end-to-end runnable. Replace with an LLM-driven
router (per the lecture-4 pattern) once the LLM wrapper is in.
"""
from __future__ import annotations

from rag.src_rag.interfaces import RouterDecision

SQL_HINTS = (
    "how many", "count", "list all", "stats", "faction", "datasheet", "stratagem",
    "点数", "数值", "数据表",
)


def route(question: str) -> RouterDecision:
    q = question.lower()
    if any(h in q for h in SQL_HINTS):
        return RouterDecision(source="sql", rationale="matched a structured-data keyword")
    return RouterDecision(source="pdf", rationale="default: rules questions go to PDF")
