import math

from rag.src_rag.chatbot.router_examples import EXAMPLES
from rag.src_rag.evaluation.e2e_eval import (
    E2eQuestion,
    Record,
    TrackingLlm,
    answer_for_scoring,
    load_questions,
    render_report,
    run_question,
    summarize,
)
from rag.src_rag.llm.fake import FakeLlm
from rag.src_rag.retriever.sql_examples import load_examples
from rag.src_rag.retriever.stubs import stub_pdf_rag, stub_sql_rag

QUESTIONS = load_questions()


def test_question_set_is_well_formed():
    ids = [q.id for q in QUESTIONS]
    assert len(ids) == len(set(ids))
    assert {q.expected_source for q in QUESTIONS} == {"pdf", "sql", "both"}
    for q in QUESTIONS:
        assert q.reference and "GOLD_COUNT" not in q.reference
        if q.expected_source in ("pdf", "both"):
            assert q.expected_pages and q.expected_sections
        # "A space marine" spans many datasheets, so this question has no single gold result.
        if q.expected_source in ("sql", "both") and q.id != "t-toughness-space-marine":
            assert q.expected_rows


def test_teachers_questions_are_in_the_set():
    questions = {q.question for q in QUESTIONS}
    assert {
        "What is the rule for grenades?",
        "How can I use a stratagem?",
        "What are the different ways to score points?",
        "What is the toughness of a space marine?",
    } <= questions


def test_questions_do_not_leak_from_any_prompt():
    prompts = {e.question.lower() for e in EXAMPLES}
    prompts |= {e.question.lower() for e in load_examples("fewshot")}
    assert not [q.id for q in QUESTIONS if q.question.lower() in prompts]


def test_answer_for_scoring_drops_the_sql_citation():
    assert answer_for_scoring("57 units.\n\nSource:\nSELECT 1") == "57 units."
    assert answer_for_scoring("57 units.\n\n**Source:**\n```sql\nSELECT 1\n```") == "57 units."
    assert answer_for_scoring("Cover adds 1 (p. 44).") == "Cover adds 1 (p. 44)."


def test_run_question_scores_a_correct_sql_answer():
    q = E2eQuestion("x", "How many?", "sql", "ref", expected_rows=[[1]])
    llm = TrackingLlm(FakeLlm([{"source": "sql", "rationale": "r"}, "One."]))
    rec = run_question(q, llm, pdf_rag=stub_pdf_rag, sql_rag=stub_sql_rag)
    assert rec.routed_source == "sql" and rec.answer == "One."
    assert rec.sql_exact is True and rec.failure is None
    assert "SELECT 1" in rec.contexts[0]


def test_run_question_counts_a_missed_retriever_as_wrong():
    q = E2eQuestion("x", "q", "both", "ref", (9,), ("DEEP STRIKE",), [[1]])
    llm = TrackingLlm(FakeLlm([{"source": "pdf", "rationale": "r"}, "A."]))
    rec = run_question(q, llm, pdf_rag=stub_pdf_rag, sql_rag=stub_sql_rag)
    assert rec.sql_exact is False and rec.sql_error == "SQL path not called"
    assert rec.section_hit is False and rec.page_hit is False


def test_router_fallback_from_llm_failure_is_flagged():
    class Failing:
        def complete(self, prompt):
            raise RuntimeError("429 quota")

        def complete_json(self, prompt, schema):
            raise RuntimeError("429 quota")

    q = E2eQuestion("x", "q", "pdf", "ref")
    rec = run_question(q, TrackingLlm(Failing()), pdf_rag=stub_pdf_rag, sql_rag=stub_sql_rag)
    assert rec.routed_source == "pdf"
    assert "429" in rec.failure


def _record(id, expected, routed, **kwargs):
    return Record(id, "q", expected, "ref", routed_source=routed, **kwargs)


def test_summarize_excludes_failures_and_splits_by_source():
    records = [
        _record("a", "pdf", "pdf", section_hit=True, ragas={"faithfulness": 1.0}),
        _record("b", "sql", "pdf", sql_exact=False, sql_relaxed=False, ragas={"faithfulness": 0.5}),
        _record("c", "pdf", "pdf", failure="429"),
    ]
    s = summarize(records)
    assert s["incomplete"] == ["c"]
    assert s["overall"]["questions"] == 2
    assert s["overall"]["router_accuracy"] == 0.5
    assert s["by_source"]["pdf"]["pdf_section_hit"] == 1.0
    assert s["overall"]["ragas"]["faithfulness"] == 0.75
    assert s["router_confusion"]["sql"]["pdf"] == 1
    assert s["router_mistakes"] == [{"id": "b", "expected": "sql", "routed": "pdf"}]


def test_summarize_ignores_nan_scores_but_counts_them():
    records = [
        _record("a", "pdf", "pdf", ragas={"faithfulness": 1.0}),
        _record("b", "pdf", "pdf", ragas={"faithfulness": math.nan}),
    ]
    s = summarize(records)
    assert s["overall"]["ragas"]["faithfulness"] == 1.0
    assert s["overall"]["ragas_missing"]["faithfulness"] == 1


def test_report_warns_about_missing_scores():
    records = [_record("a", "pdf", "pdf", ragas={"faithfulness": math.nan})]
    assert "Incomplete: RAGAS scores missing" in render_report(summarize(records), records, "m")


def test_render_report_lists_questions_and_metrics():
    records = [_record("a", "sql", "sql", sql_exact=True, sql_relaxed=True)]
    text = render_report(summarize(records), records, "m")
    assert "Router accuracy" in text and "RAGAS faithfulness" in text
    assert "| a | sql |  | exact |" in text
