"""Scripted end-to-end demo.

Runs the chat on a short, hand-picked set of questions covering each path
(pdf / sql / both) plus one multi-turn follow-up. Prints what the router
decided, which chunks or SQL were used, and the final answer.

    make demo
    uv run python -m rag.src_rag.chatbot.demo
"""
from __future__ import annotations

from dataclasses import dataclass

from rag.src_rag.chatbot.app import Turn, answer


@dataclass(frozen=True)
class DemoStep:
    label: str
    question: str
    # When set, the step is a follow-up: use history from steps up to this index.
    uses_history_through: int | None = None


STEPS: list[DemoStep] = [
    DemoStep(
        label="PDF rule",
        question="How does deep strike work?",
    ),
    DemoStep(
        label="SQL lookup",
        question="How many datasheets does the Orks faction have?",
    ),
    DemoStep(
        label="Both — rule + data",
        question="What is Deep Strike, and which Necrons units have it?",
    ),
    DemoStep(
        label="Multi-turn follow-up",
        question="And which of them have the FLY keyword too?",
        uses_history_through=2,
    ),
]


def _print_sources(result) -> None:
    dec = result.decision
    if dec is None:
        return
    print(f"  router: {dec.source}  —  {dec.rationale.strip()[:120]}")
    if dec.source == "both":
        if dec.pdf_question:
            print(f"    split pdf: {dec.pdf_question}")
        if dec.sql_question:
            print(f"    split sql: {dec.sql_question}")
    if result.pdf is not None:
        pages = sorted({c.page for c in result.pdf.chunks})
        print(f"  pdf: {len(result.pdf.chunks)} chunks, pages {pages}")
    if result.sql is not None:
        s = result.sql
        if s.error:
            print(f"  sql error: {s.error}")
        else:
            total = f" of {s.total_rows}" if s.total_rows else ""
            print(f"  sql: {len(s.rows)} rows{total}")
            print(f"    {s.sql}")


def run() -> list[Turn]:
    from rag.src_rag.llm.gemini import GeminiLlm

    llm = GeminiLlm()
    history: list[Turn] = []
    for i, step in enumerate(STEPS):
        bar = "=" * 70
        print(f"\n{bar}\n[{i + 1}/{len(STEPS)}] {step.label}\nQ: {step.question}\n{bar}")
        use_history = history if step.uses_history_through is not None else []
        result = answer(step.question, history=use_history, llm=llm)
        _print_sources(result)
        print()
        print(result.text)
        history.append(Turn(question=step.question, answer=result))
    return history


if __name__ == "__main__":
    run()
