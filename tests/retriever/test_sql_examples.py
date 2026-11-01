import pytest

from rag.src_rag.retriever.sql_examples import (
    check_example,
    load_examples,
    render_examples,
    results_contain,
    results_match,
    select_examples,
)

EXAMPLES = load_examples()


@pytest.mark.parametrize("example", EXAMPLES, ids=[e.id for e in EXAMPLES])
def test_example_sql_reproduces_expected_result(example):
    ok, out = check_example(example)
    assert out.error is None
    assert ok, f"{example.id}: got {out.rows}"


def test_examples_are_well_formed():
    ids = [e.id for e in EXAMPLES]
    assert len(ids) == len(set(ids))
    assert len(load_examples("fewshot")) == 20
    assert len(load_examples("eval")) == 14
    assert all(e.expected for e in EXAMPLES)


def test_eval_questions_do_not_leak_into_fewshot_pool():
    fewshot = {e.question.lower() for e in load_examples("fewshot")}
    assert not any(e.question.lower() in fewshot for e in load_examples("eval"))


def test_results_match_ignores_row_and_column_order():
    expected = [["Orks", 88], ["Necrons", 61]]
    assert results_match(expected, [[61, "Necrons"], [88, "Orks"]])
    assert not results_match(expected, [["Orks", 88]])
    assert not results_match(expected, [["Orks", 88], ["Necrons", 60]])
    assert not results_match([["a"]], [["a"], ["a"]])


def test_results_match_treats_whole_floats_as_ints():
    assert results_match([["Orks", 35]], [["Orks", 35.0]])


def test_results_contain_allows_extra_columns():
    expected = [["Orks", 88], ["Necrons", 61]]
    assert results_contain(expected, [["ORK", "Orks", 88], ["NEC", "Necrons", 61]])
    assert not results_contain(expected, [["ORK", "Orks", 88]])
    assert not results_contain(expected, [["ORK", "Orks", 88], ["NEC", "Necrons", 60]])
    assert not results_contain([["a"], ["a"]], [["a", "x"], ["b", "y"]])


def test_select_examples_finds_same_pattern():
    picked = select_examples("How many points do Boyz cost?", k=3)
    assert len(picked) == 3
    assert picked[0].id == "f04"
    assert all(e.split == "fewshot" for e in picked)


def test_render_examples():
    text = render_examples(select_examples("List all detachments of the Orks faction.", k=1))
    assert text.startswith("EXAMPLES\nQ: List all detachments of the Necrons faction.")
    assert "SQL: SELECT dt.name" in text
    assert render_examples([]) == ""
