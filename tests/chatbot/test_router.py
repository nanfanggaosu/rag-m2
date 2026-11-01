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
    # Few-shot examples (at least a couple of distinct sources) are embedded.
    assert '"source": "pdf"' in sent
    assert '"source": "sql"' in sent
    assert '"source": "both"' in sent


def test_end_to_end_answer_wiring_with_stubs():
    # Pure wiring test: stub LLM + stub retrievers. No index, no network.
    llm = FakeLlm([{"source": "pdf", "rationale": "stub"}])
    out = answer(
        "How does deep strike work?",
        pdf_rag=stub_pdf_rag,
        sql_rag=stub_sql_rag,
        llm=llm,
    )
    assert out.source == "pdf"
    assert out.text
    assert out.pdf is not None and out.pdf.chunks
