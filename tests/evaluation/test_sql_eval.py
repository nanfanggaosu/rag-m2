from rag.src_rag.evaluation.sql_eval import evaluate, summarize
from rag.src_rag.llm.fake import FakeLlm
from rag.src_rag.retriever.sql_examples import load_examples
from rag.src_rag.retriever.sql_rag import SqlRag


def test_gold_sql_scores_full_marks():
    examples = load_examples("eval")
    llm = FakeLlm([{"reasoning": "", "sql": e.sql} for e in examples])
    rows = evaluate(SqlRag(llm), examples)
    summary = summarize(rows)
    assert summary["exact_accuracy"] == 1.0
    assert summary["relaxed_accuracy"] == 1.0
    assert summary["avg_attempts"] == 1.0


def test_wrong_and_broken_answers_are_scored():
    examples = load_examples("eval")[:2]
    llm = FakeLlm([
        {"reasoning": "", "sql": "SELECT 0 AS n_datasheets"},
        {"reasoning": "", "sql": "SELECT broken"},
        {"reasoning": "", "sql": "SELECT broken"},
        {"reasoning": "", "sql": "SELECT broken"},
    ])
    rows = evaluate(SqlRag(llm), examples)
    assert [r.exact for r in rows] == [False, False]
    assert rows[1].error and rows[1].attempts == 3
    assert summarize(rows)["errors"] == 1
