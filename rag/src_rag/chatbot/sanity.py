"""Teacher's four sanity questions (Lecture 1 PDF, p. 42).

Runs each question through the full chat pipeline on a fresh history, prints
the router decision + evidence + answer. These are the questions the grader
said he would try himself:

    - What is the rule for grenades?
    - How can I use a stratagem?
    - What are the different ways to score points?
    - What is the toughness of a space marine?

    make sanity
    uv run python -m rag.src_rag.chatbot.sanity
"""
from __future__ import annotations

from rag.src_rag.chatbot.app import Turn, answer
from rag.src_rag.chatbot.demo import _print_sources

SANITY_QUESTIONS: tuple[str, ...] = (
    "What is the rule for grenades?",
    "How can I use a stratagem?",
    "What are the different ways to score points?",
    "What is the toughness of a space marine?",
)


def run() -> list[Turn]:
    from rag.src_rag.llm.gemini import GeminiLlm

    llm = GeminiLlm()
    results: list[Turn] = []
    for i, q in enumerate(SANITY_QUESTIONS, 1):
        bar = "=" * 70
        print(f"\n{bar}\n[{i}/{len(SANITY_QUESTIONS)}] {q}\n{bar}")
        result = answer(q, llm=llm)
        _print_sources(result)
        print()
        print(result.text)
        results.append(Turn(question=q, answer=result))
    return results


if __name__ == "__main__":
    run()
