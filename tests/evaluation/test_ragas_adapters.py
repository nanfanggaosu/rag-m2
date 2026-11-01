import asyncio
from types import SimpleNamespace

import pytest

ragas_adapters = pytest.importorskip("rag.src_rag.evaluation.ragas_adapters")

from rag.src_rag.llm.fake import FakeLlm  # noqa: E402


def _prompt(text):
    return SimpleNamespace(to_string=lambda: text)


def test_llm_adapter_passes_the_prompt_and_returns_n_generations():
    llm = FakeLlm(["answer"])
    wrapped = ragas_adapters.wrap_llm(llm)
    result = wrapped.generate_text(_prompt("hello"), n=2)
    assert llm.prompts == ["hello"]
    assert [g.text for g in result.generations[0]] == ["answer", "answer"]
    assert wrapped.is_finished(result)


def test_llm_adapter_async_matches_sync():
    wrapped = ragas_adapters.wrap_llm(FakeLlm(["answer"]))
    result = asyncio.run(wrapped.agenerate_text(_prompt("hello")))
    assert result.generations[0][0].text == "answer"


def test_metrics_are_the_five_we_report():
    from rag.src_rag.evaluation.e2e_eval import RAGAS_METRICS

    assert {m.name for m in ragas_adapters.ragas_metrics()} == set(RAGAS_METRICS)
