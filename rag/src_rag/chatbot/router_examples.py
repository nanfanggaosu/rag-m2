"""Few-shot examples for the LLM-driven Router.

Each example is a canonical question with the ground-truth source (pdf/sql/both)
and a short rationale the LLM can learn from. Sources:
  - PDF examples: picked from our evaluation set — all are rules/mechanics questions
  - SQL examples: picked from `rag/data/sql_examples.json` — covers count, list,
    lookup-by-name, filter-by-faction, filter-by-keyword, aggregation
  - both examples: hand-written cases that genuinely need rules + data
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RouterExample:
    question: str
    source: Literal["pdf", "sql", "both"]
    rationale: str
    pdf_question: str | None = None
    sql_question: str | None = None


EXAMPLES: list[RouterExample] = [
    RouterExample(
        "How does deep strike work?", "pdf",
        "Deep Strike is a core rule mechanic described in the rulebook.",
    ),
    RouterExample(
        "How do melee attacks resolve in the fight phase?", "pdf",
        "Asks for the sequence of a phase — explained in the rulebook.",
    ),
    RouterExample(
        "What is engagement range?", "pdf",
        "A core-rules concept definition.",
    ),
    RouterExample(
        "How does feel no pain work?", "pdf",
        "A keyword/ability defined in the rules.",
    ),
    RouterExample(
        "What do blast weapons do?", "pdf",
        "Weapon-category rule from the rulebook.",
    ),
    RouterExample(
        "How is the hit roll resolved?", "pdf",
        "A core attack-resolution rule.",
    ),
    RouterExample(
        "How many datasheets does the Orks faction have?", "sql",
        "A count query against the datasheets table.",
    ),
    RouterExample(
        "List all detachments of the Necrons faction.", "sql",
        "A list query from the detachments table filtered by faction.",
    ),
    RouterExample(
        "What are the stats of the Warboss In Mega Armour?", "sql",
        "A specific unit lookup from the datasheets table.",
    ),
    RouterExample(
        "How many points does an Intercessor Squad cost?", "sql",
        "A points-cost lookup from the datasheet-model table.",
    ),
    RouterExample(
        "How many units have the Fly keyword?", "sql",
        "A count query joining datasheets and keywords.",
    ),
    RouterExample(
        "What is the most expensive enhancement in the Orks faction?", "sql",
        "An aggregation over enhancements filtered by faction.",
    ),
    RouterExample(
        "What is a Lictor's move characteristic and how does the move phase work?", "both",
        "Needs the Lictor's Move stat (SQL) and the Movement Phase rules (PDF).",
        "How does the Movement phase work?",
        "What is the move characteristic of a Lictor?",
    ),
    RouterExample(
        "How does the Fly keyword work and which Space Marines units have it?", "both",
        "Needs the Fly rule (PDF) and a unit list filtered by keyword (SQL).",
        "How does the Fly keyword work?",
        "Which Space Marines units have the Fly keyword?",
    ),
    RouterExample(
        "What is deep strike and what is the range of a Lictor's deep strike ability?", "both",
        "Needs the Deep Strike rule (PDF) and the Lictor's specific ability data (SQL).",
        "What is deep strike?",
        "What does the deep strike ability of a Lictor say?",
    ),
]
