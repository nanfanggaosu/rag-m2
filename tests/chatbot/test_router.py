from rag.src_rag.chatbot.app import answer
from rag.src_rag.chatbot.router import route
from rag.src_rag.retriever.stubs import stub_pdf_rag, stub_sql_rag


def test_rules_question_routes_to_pdf():
    assert route("How does deep strike work?").source == "pdf"


def test_numeric_question_routes_to_sql():
    assert route("How many datasheets are in the Space Marines faction?").source == "sql"


def test_end_to_end_stub_answer_runs():
    # Inject stubs so the wiring test doesn't require a built vector index.
    out = answer("How does deep strike work?", pdf_rag=stub_pdf_rag, sql_rag=stub_sql_rag)
    assert out.source == "pdf"
    assert out.text
    assert out.pdf is not None and out.pdf.chunks
