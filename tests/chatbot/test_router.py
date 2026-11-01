from rag.src_rag.chatbot.router import route
from rag.src_rag.llm.fake import FakeLlm


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


def test_route_both_carries_the_split_questions():
    llm = FakeLlm([{
        "source": "both",
        "rationale": "rule + data",
        "pdf_question": "How does Fly work?",
        "sql_question": "Which units have Fly?",
    }])
    r = route("How does Fly work and which units have it?", llm)
    assert r.pdf_question == "How does Fly work?"
    assert r.sql_question == "Which units have Fly?"


def test_route_prompt_keeps_conditions_when_splitting():
    captured = FakeLlm([{"source": "pdf", "rationale": "ok"}])
    route("anything", captured)
    assert "keeping every condition from the original question" in captured.prompts[0]


def test_route_prompt_shows_split_questions_for_both():
    captured = FakeLlm([{"source": "pdf", "rationale": "ok"}])
    route("anything", captured)
    assert '"pdf_question": "How does the Fly keyword work?"' in captured.prompts[0]
