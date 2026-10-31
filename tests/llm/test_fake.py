import pytest

from rag.src_rag.llm.fake import FakeLlm


def test_replies_in_order_and_records_prompts():
    llm = FakeLlm(["plain text", {"sql": "SELECT 1"}])
    assert llm.complete("p1") == "plain text"
    assert llm.complete_json("p2", {}) == {"sql": "SELECT 1"}
    assert llm.prompts == ["p1", "p2"]


def test_converts_between_text_and_json():
    llm = FakeLlm(['{"a": 1}', {"b": 2}])
    assert llm.complete_json("p", {}) == {"a": 1}
    assert llm.complete("p") == '{"b": 2}'


def test_running_out_of_replies_fails_loudly():
    llm = FakeLlm([])
    with pytest.raises(AssertionError, match="ran out"):
        llm.complete("p")
