"""Minimal end-to-end chat loop.

PDF retriever (ChromaDB + bge-small), SQL retriever (text-to-SQL via Gemini),
LLM-driven router (pdf/sql/both), LLM-synthesized final answer.

    uv run python -m rag.src_rag.chatbot.app
"""
from __future__ import annotations

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


_PDF_ONLY_SYSTEM = (
    "You answer Warhammer 40,000 rules questions using excerpts from the "
    "Core Rules PDF. Cite the page for every claim like '(p. 39)'. If the "
    "excerpts do not cover the question, say so plainly rather than guessing."
)

_SQL_ONLY_SYSTEM = (
    "You answer Warhammer 40,000 data questions using the result of a SQL "
    "query over the datasheets database. State the query that was run and "
    "summarise the rows. If the rows do not answer the question, say so."
)

_BOTH_SYSTEM = (
    "You answer a Warhammer 40,000 question that needs both a rule "
    "explanation (from the Core Rules PDF) and specific data (from the "
    "datasheets SQL database). Combine the two. Cite PDF page numbers for "
    "rule claims and the SQL query/rows for data claims."
)


def answer(
    question: str,
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

    decision = route(question, llm)
    pdf_result: PdfRagResult | None = None
    sql_result: SqlRagResult | None = None
    if decision.source in ("pdf", "both"):
        pdf_result = pdf_rag(question)
    if decision.source in ("sql", "both"):
        sql_result = sql_rag(question)
    text = _synthesize(question, decision.source, pdf_result, sql_result, llm)
    return FinalAnswer(
        text=text,
        source=decision.source,
        pdf=pdf_result,
        sql=sql_result,
        decision=decision,
    )


def _synthesize(
    question: str,
    source: str,
    pdf: PdfRagResult | None,
    sql: SqlRagResult | None,
    llm: Llm,
) -> str:
    system = {
        "pdf": _PDF_ONLY_SYSTEM,
        "sql": _SQL_ONLY_SYSTEM,
        "both": _BOTH_SYSTEM,
    }.get(source, _PDF_ONLY_SYSTEM)
    parts = [system, f"Question: {question}"]
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
        " | ".join(str(r.get(c, "")) for c in sql.columns) for r in sql.rows[:20]
    )
    tail = ""
    if len(sql.rows) > 20:
        tail = f"\n... {len(sql.rows) - 20} more rows"
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
            parts.append(f"[via SQL]\n{sql.sql}\nrows={sql.rows}")
    return (
        "\n\n".join(parts) if parts else f"(no results — router picked {source!r})"
    )


def main() -> None:
    from rag.src_rag.llm.gemini import GeminiLlm

    llm = GeminiLlm()
    print("rag-m2 chat. Ctrl-D to quit.")
    while True:
        try:
            q = input("> ").strip()
        except EOFError:
            print()
            return
        if not q:
            continue
        print(answer(q, llm=llm).text)


if __name__ == "__main__":
    main()
