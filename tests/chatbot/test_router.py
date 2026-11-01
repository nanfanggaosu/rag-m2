from rag.src_rag.chatbot.app import answer
from rag.src_rag.chatbot.router import route
from rag.src_rag.llm.fake import FakeLlm
from rag.src_rag.retriever.stubs import stub_pdf_rag, stub_sql_rag


def test_route_pdf_classification():
    llm = FakeLlm([{"source": "pdf", "rationale": "rules question"}])
    r = route("How does deep strike work?", llm)
    assert r.source == "pdf"
    assert r.rationale == "rules question"


def test_route_sql_classification():
    llm = FakeLlm([{"source": "sql", "rationale": "faction count"}])
    r = route("How many datasheets does Orks have?", llm)
    assert r.source == "sql"


def test_route_both_classification():
    llm = FakeLlm([{"source": "both", "rationale": "needs rule + data"}])
    r = route("Explain deep strike and give a Lictor's deep strike range.", llm)
    assert r.source == "both"


def test_route_bad_source_falls_back_to_pdf():
    llm = FakeLlm([{"source": "unknown", "rationale": "weird"}])
    r = route("something ambiguous", llm)
    assert r.source == "pdf"
    assert "defaulting to pdf" in r.rationale


def test_route_llm_error_falls_back_to_pdf():
    class RaisingLlm:
        def complete(self, prompt):
            return ""

        def complete_json(self, prompt, schema):
            raise RuntimeError("boom")

    r = route("anything", RaisingLlm())
    assert r.source == "pdf"
    assert "router error" in r.rationale


def test_route_prompt_contains_the_question_and_examples():
    captured = FakeLlm([{"source": "pdf", "rationale": "ok"}])
    route("How does deep strike work?", captured)
    sent = captured.prompts[0]
    assert "How does deep strike work?" in sent
    assert '"source": "pdf"' in sent
    assert '"source": "sql"' in sent
    assert '"source": "both"' in sent


def test_end_to_end_answer_pdf_only():
    # Router returns pdf, then synthesizer gets called with the chunks.
    llm = FakeLlm([
        {"source": "pdf", "rationale": "rules question"},
        "The stub answer references (p. 1).",
    ])
    out = answer(
        "How does deep strike work?",
        pdf_rag=stub_pdf_rag,
        sql_rag=stub_sql_rag,
        llm=llm,
    )
    assert out.source == "pdf"
    assert out.pdf is not None and out.pdf.chunks
    assert out.sql is None
    assert out.text == "The stub answer references (p. 1)."
    synth_prompt = llm.prompts[1]
    assert "PDF rules excerpts" in synth_prompt
    assert "SQL query" not in synth_prompt


def test_end_to_end_answer_sql_only():
    llm = FakeLlm([
        {"source": "sql", "rationale": "faction count"},
        "Orks have 88 datasheets.",
    ])
    out = answer(
        "How many datasheets does Orks have?",
        pdf_rag=stub_pdf_rag,
        sql_rag=stub_sql_rag,
        llm=llm,
    )
    assert out.source == "sql"
    assert out.sql is not None and out.sql.rows
    assert out.pdf is None
    assert out.text == "Orks have 88 datasheets."
    synth_prompt = llm.prompts[1]
    assert "SQL query" in synth_prompt
    assert "PDF rules excerpts" not in synth_prompt


def test_end_to_end_answer_fans_out_on_both():
    llm = FakeLlm([
        {"source": "both", "rationale": "needs rule + data"},
        "A Lictor has Deep Strike (p. 39); its range is …",
    ])
    out = answer(
        "What is deep strike and what is a Lictor's deep strike range?",
        pdf_rag=stub_pdf_rag,
        sql_rag=stub_sql_rag,
        llm=llm,
    )
    assert out.source == "both"
    assert out.pdf is not None and out.pdf.chunks
    assert out.sql is not None and out.sql.rows
    synth_prompt = llm.prompts[1]
    assert "PDF rules excerpts" in synth_prompt
    assert "SQL query" in synth_prompt


def test_synthesizer_falls_back_to_raw_dump_on_error():
    class HalfRaisingLlm:
        """Router call succeeds, synthesizer call raises."""

        def __init__(self):
            self.n = 0

        def complete(self, prompt):
            raise RuntimeError("synthesis boom")

        def complete_json(self, prompt, schema):
            return {"source": "pdf", "rationale": "ok"}

    out = answer(
        "anything",
        pdf_rag=stub_pdf_rag,
        sql_rag=stub_sql_rag,
        llm=HalfRaisingLlm(),
    )
    assert out.source == "pdf"
    assert "[via PDF]" in out.text
    assert "answer synthesizer failed" in out.text
