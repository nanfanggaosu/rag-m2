from rag.src_rag.chatbot.app import answer
from rag.src_rag.chatbot.router import route


def test_rules_question_routes_to_pdf():
    assert route("How does deep strike work?").source == "pdf"


def test_numeric_question_routes_to_sql():
    assert route("How many datasheets are in the Space Marines faction?").source == "sql"


def test_end_to_end_stub_answer_runs():
    out = answer("How does deep strike work?")
    assert out.source == "pdf"
    assert out.text
    assert out.pdf is not None and out.pdf.chunks
