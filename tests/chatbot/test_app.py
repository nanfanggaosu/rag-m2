from dataclasses import replace

from rag.src_rag.chatbot.app import _format_sql, answer
from rag.src_rag.interfaces import SqlRagResult
from rag.src_rag.llm.fake import FakeLlm
from rag.src_rag.retriever.stubs import stub_pdf_rag, stub_sql_rag


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


def test_both_sends_each_side_its_own_question():
    seen = {}

    def pdf(question, *, k=5):
        seen["pdf"] = question
        return stub_pdf_rag(question, k=k)

    def sql(question, *, max_rows=50):
        seen["sql"] = question
        return stub_sql_rag(question, max_rows=max_rows)

    llm = FakeLlm([
        {
            "source": "both",
            "rationale": "x",
            "pdf_question": "How does Fly work?",
            "sql_question": "Which units have Fly?",
        },
        "answer",
    ])
    answer("How does Fly work and which units have it?", pdf_rag=pdf, sql_rag=sql, llm=llm)
    assert seen == {"pdf": "How does Fly work?", "sql": "Which units have Fly?"}


def test_both_without_split_questions_uses_the_original():
    seen = []

    def sql(question, *, max_rows=50):
        seen.append(question)
        return stub_sql_rag(question, max_rows=max_rows)

    llm = FakeLlm([{"source": "both", "rationale": "x"}, "answer"])
    answer("original?", pdf_rag=stub_pdf_rag, sql_rag=sql, llm=llm)
    assert seen == ["original?"]


def test_sql_llm_failure_does_not_crash_the_answer():
    class FailsAfterRouter:
        def complete(self, prompt):
            return "the query failed"

        def complete_json(self, prompt, schema):
            if "route Warhammer" in prompt:
                return {"source": "sql", "rationale": "x"}
            raise RuntimeError("429 quota")

    out = answer("How many Orks units?", pdf_rag=stub_pdf_rag, llm=FailsAfterRouter())
    assert "LLM call failed" in out.sql.error
    assert out.text == "the query failed"


def _result(**kwargs):
    base = SqlRagResult(sql="SELECT 1", rows=[{"name": "A"}], columns=["name"], total_rows=1)
    return replace(base, **kwargs)


def test_format_sql_reports_cut_off_rows():
    rows = [{"name": str(i)} for i in range(50)]
    text = _format_sql(_result(rows=rows, total_rows=88))
    assert "(cut off: showing 50 of 88 rows)" in text
    assert text.count("\n") >= 50


def test_format_sql_says_nothing_when_complete():
    assert "cut off" not in _format_sql(_result())


def test_format_sql_repairs_mis_encoded_text():
    text = _format_sql(_result(rows=[{"name": "Rollin\xe2\x80\x99 Deff"}]))
    assert "Rollin\u2019 Deff" in text
