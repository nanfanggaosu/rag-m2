"""Minimal end-to-end chat loop wired against stubs.

Prove the plumbing works before either side is real:
    uv run python -m rag.src_rag.chatbot.app
"""
from __future__ import annotations

from rag.src_rag.chatbot.router import route
from rag.src_rag.interfaces import FinalAnswer, PdfRag, SqlRag
from rag.src_rag.retriever.stubs import stub_pdf_rag, stub_sql_rag


def answer(
    question: str,
    pdf_rag: PdfRag = stub_pdf_rag,
    sql_rag: SqlRag = stub_sql_rag,
) -> FinalAnswer:
    decision = route(question)
    if decision.source == "sql":
        sql = sql_rag(question)
        text = f"[via SQL] {sql.sql}\nrows={sql.rows}"
        return FinalAnswer(text=text, source="sql", sql=sql, decision=decision)
    pdf = pdf_rag(question)
    text = "[via PDF]\n" + "\n---\n".join(c.text for c in pdf.chunks[:3])
    return FinalAnswer(text=text, source="pdf", pdf=pdf, decision=decision)


def main() -> None:
    print("rag-m2 chat (stub). Ctrl-D to quit.")
    while True:
        try:
            q = input("> ").strip()
        except EOFError:
            print()
            return
        if not q:
            continue
        print(answer(q).text)


if __name__ == "__main__":
    main()
