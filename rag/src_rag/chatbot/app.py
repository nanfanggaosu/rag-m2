"""End-to-end chat loop with multi-turn history.

PDF retriever (ChromaDB + bge-small), SQL retriever (text-to-SQL via Gemini),
LLM-driven router (pdf/sql/both), LLM-synthesized final answer.

    uv run python -m rag.src_rag.chatbot.app

Commands inside the chat: /help /reset /history /last /sources /quit.
"""
from __future__ import annotations

from dataclasses import dataclass

from rag.src_rag.chatbot.router import route
from rag.src_rag.interfaces import (
    FinalAnswer,
    Llm,
    PdfRag,
    PdfRagResult,
    SqlRag,
    SqlRagResult,
)
from rag.src_rag.retriever.pdf import pdf_rag as real_pdf_rag
from rag.src_rag.retriever.sql_rag import SqlRag as GeminiSqlRag
from rag.src_rag.retriever.sql_schema import fix_encoding


_PDF_ONLY_SYSTEM = (
    "You answer Warhammer 40,000 rules questions using excerpts from the "
    "Core Rules PDF. Cite the page for every claim like '(p. 39)'. If the "
    "excerpts do not cover the question, say so plainly rather than guessing."
)

_SQL_ONLY_SYSTEM = (
    "You answer Warhammer 40,000 data questions using the result of a SQL "
    "query over the datasheets database. Start with the direct answer in plain "
    "language, then end with the query that was run under 'Source:'. If the rows "
    "were cut off, report the true total and say the list is partial. If the "
    "query failed or the rows do not answer the question, say so."
)

_BOTH_SYSTEM = (
    "You answer a Warhammer 40,000 question that needs both a rule "
    "explanation (from the Core Rules PDF) and specific data (from the "
    "datasheets SQL database). Start with the direct answer, combining the two. "
    "Cite PDF page numbers for rule claims and end with the SQL query under "
    "'Source:'. If the rows were cut off, report the true total and say the list "
    "is partial. If either source does not cover its part, say so."
)

_CONTEXTUALIZE_SYSTEM = (
    "Rewrite the follow-up question into a standalone question that does not "
    "need the prior conversation. Resolve pronouns and short references using "
    "the conversation. If the follow-up is already standalone, return it "
    "unchanged. Return the rewritten question only, no preface."
)

_TRANSLATE_SYSTEM = (
    "Translate the following answer into {lang}. Keep all page citations like "
    "'(p. 39)' and any SQL under a 'Source:' line unchanged. Return the "
    "translated answer only, no preface."
)

# Lecture 1 PPT lists translation as a nice-to-have for the chat interface.
LANGUAGES = {
    "/zh": "Simplified Chinese",
    "/fr": "French",
    "/en": "English",
}

# Only the last few turns go into prompts, to keep tokens bounded.
HISTORY_WINDOW = 3


@dataclass(frozen=True)
class Turn:
    question: str
    answer: FinalAnswer


def answer(
    question: str,
    history: list[Turn] | None = None,
    pdf_rag: PdfRag = real_pdf_rag,
    sql_rag: SqlRag | None = None,
    llm: Llm | None = None,
) -> FinalAnswer:
    if llm is None:
        # Lazy import so tests that pass their own `llm` don't need GOOGLE_API_KEY.
        from rag.src_rag.llm.gemini import GeminiLlm

        llm = GeminiLlm()
    if sql_rag is None:
        sql_rag = GeminiSqlRag(llm)

    history = history or []
    standalone = _contextualize(question, history, llm) if history else question

    decision = route(standalone, llm)
    pdf_result: PdfRagResult | None = None
    sql_result: SqlRagResult | None = None
    if decision.source in ("pdf", "both"):
        pdf_result = pdf_rag(decision.pdf_question or standalone)
    if decision.source in ("sql", "both"):
        sql_result = sql_rag(decision.sql_question or standalone)
    text = _synthesize(
        question, standalone, decision.source, pdf_result, sql_result, history, llm
    )
    return FinalAnswer(
        text=text,
        source=decision.source,
        pdf=pdf_result,
        sql=sql_result,
        decision=decision,
    )


def _contextualize(question: str, history: list[Turn], llm: Llm) -> str:
    convo = "\n".join(
        f"User: {t.question}\nAssistant: {t.answer.text}"
        for t in history[-HISTORY_WINDOW:]
    )
    prompt = (
        f"{_CONTEXTUALIZE_SYSTEM}\n\n"
        f"Conversation so far:\n{convo}\n\n"
        f"Follow-up: {question}\n\nStandalone question:"
    )
    try:
        rewritten = llm.complete(prompt).strip()
    except Exception:
        return question
    return rewritten or question


def _synthesize(
    original_question: str,
    standalone_question: str,
    source: str,
    pdf: PdfRagResult | None,
    sql: SqlRagResult | None,
    history: list[Turn],
    llm: Llm,
) -> str:
    system = {
        "pdf": _PDF_ONLY_SYSTEM,
        "sql": _SQL_ONLY_SYSTEM,
        "both": _BOTH_SYSTEM,
    }.get(source, _PDF_ONLY_SYSTEM)
    parts = [system]
    if history:
        convo = "\n".join(
            f"User: {t.question}\nAssistant: {t.answer.text}"
            for t in history[-HISTORY_WINDOW:]
        )
        parts.append(f"Prior conversation:\n{convo}")
    parts.append(f"Question: {original_question}")
    if original_question.strip() != standalone_question.strip():
        parts.append(f"Standalone form of the question: {standalone_question}")
    if pdf is not None:
        parts.append(_format_pdf(pdf))
    if sql is not None:
        parts.append(_format_sql(sql))
    parts.append("Answer:")
    prompt = "\n\n".join(parts)
    try:
        return llm.complete(prompt).strip()
    except Exception as e:
        return _raw_dump(source, pdf, sql) + f"\n\n(answer synthesizer failed: {e})"


def _format_pdf(pdf: PdfRagResult) -> str:
    lines = ["PDF rules excerpts (ranked):"]
    for c in pdf.chunks:
        section = c.section or "(no section)"
        lines.append(f"[p. {c.page}, {section}]\n{c.text}")
    return "\n\n".join(lines)


def _format_sql(sql: SqlRagResult) -> str:
    if sql.error:
        return f"SQL query attempted: {sql.sql}\nSQL error: {sql.error}"
    header = " | ".join(sql.columns)
    rows_str = "\n".join(
        " | ".join(fix_encoding(str(r.get(c, ""))) for c in sql.columns) for r in sql.rows
    )
    tail = ""
    if sql.total_rows is not None and sql.total_rows > len(sql.rows):
        tail = f"\n(cut off: showing {len(sql.rows)} of {sql.total_rows} rows)"
    return f"SQL query:\n{sql.sql}\n\nRows:\n{header}\n{rows_str}{tail}"


def _raw_dump(
    source: str, pdf: PdfRagResult | None, sql: SqlRagResult | None
) -> str:
    """Fallback shown when LLM synthesis fails — keeps the user from getting nothing."""
    parts: list[str] = []
    if pdf is not None:
        parts.append(
            "[via PDF]\n" + "\n---\n".join(c.text for c in pdf.chunks[:3])
        )
    if sql is not None:
        if sql.error:
            parts.append(f"[via SQL]\nerror: {sql.error}\nsql: {sql.sql}")
        else:
            parts.append(f"[via SQL]\n{_format_sql(sql)}")
    return (
        "\n\n".join(parts) if parts else f"(no results — router picked {source!r})"
    )


_HELP = """\
Commands:
  /help        show this message
  /reset       clear conversation history
  /history     show prior turns in this session
  /last        show the full retrieval detail of the last answer
  /sources     same as /last — show which chunks / SQL were used
  /zh /fr /en  translate the last answer (Chinese / French / English)
  /quit        leave the chat (ctrl-D or ctrl-C also work)

Anything else is sent as a question. The router picks pdf, sql, or both.
"""


def translate(text: str, lang: str, llm: Llm) -> str:
    prompt = _TRANSLATE_SYSTEM.format(lang=lang) + "\n\n" + text
    try:
        return llm.complete(prompt).strip()
    except Exception as e:
        return f"(translation failed: {e})\n\n{text}"


def _print_sources(turn: Turn) -> None:
    dec = turn.answer.decision
    print(f"[router: {dec.source if dec else '?'}" + (f" — {dec.rationale}]" if dec else "]"))
    if dec and dec.source == "both":
        if dec.pdf_question:
            print(f"  split pdf: {dec.pdf_question}")
        if dec.sql_question:
            print(f"  split sql: {dec.sql_question}")
    if turn.answer.pdf is not None:
        print("[pdf chunks]")
        for c in turn.answer.pdf.chunks:
            print(f"  p. {c.page}  {c.section or '(no section)'}  score={c.score}")
    if turn.answer.sql is not None:
        s = turn.answer.sql
        if s.error:
            print(f"[sql error]\n  {s.error}")
        else:
            total = f" of {s.total_rows}" if s.total_rows else ""
            print(f"[sql] rows: {len(s.rows)}{total}")
            print(f"  {s.sql}")


def main() -> None:
    from rag.src_rag.llm.gemini import GeminiLlm

    llm = GeminiLlm()
    history: list[Turn] = []
    print("rag-m2 chat. Type /help for commands, /quit to leave.")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not q:
            continue
        cmd = q.lower()
        if cmd in ("/quit", "/exit", "quit", "exit"):
            return
        if cmd == "/help":
            print(_HELP)
            continue
        if cmd == "/reset":
            history.clear()
            print("[history cleared]")
            continue
        if cmd == "/history":
            if not history:
                print("[no turns yet]")
            for i, t in enumerate(history, 1):
                print(f"{i}. Q: {t.question}\n   A: {t.answer.text}")
            continue
        if cmd in ("/last", "/sources"):
            if not history:
                print("[no answers yet]")
            else:
                _print_sources(history[-1])
            continue
        if cmd in LANGUAGES:
            if not history:
                print("[no answer to translate yet]")
            else:
                print(translate(history[-1].answer.text, LANGUAGES[cmd], llm))
            continue
        try:
            result = answer(q, history=history, llm=llm)
        except Exception as e:
            print(f"Could not answer: {e}")
            continue
        print(result.text)
        history.append(Turn(question=q, answer=result))


if __name__ == "__main__":
    main()
