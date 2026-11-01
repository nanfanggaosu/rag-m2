"""Plug our cached, rate-limited Gemini wrapper and local embeddings into RAGAS."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.outputs import Generation, LLMResult
from ragas.embeddings.base import BaseRagasEmbeddings
from ragas.llms.base import BaseRagasLLM
from ragas.metrics import (
    AnswerCorrectness,
    Faithfulness,
    LLMContextPrecisionWithReference,
    LLMContextRecall,
    ResponseRelevancy,
)

from rag.src_rag.interfaces import Llm


@dataclass
class _GeminiForRagas(BaseRagasLLM):
    llm: Llm = field(default=None)

    def generate_text(self, prompt, n=1, temperature=0.01, stop=None, callbacks=None) -> LLMResult:
        text = self.llm.complete(prompt.to_string())
        return LLMResult(generations=[[Generation(text=text) for _ in range(n)]])

    # Blocking on purpose: calls must stay one at a time to respect the rate limit.
    async def agenerate_text(self, prompt, n=1, temperature=0.01, stop=None, callbacks=None) -> LLMResult:
        return self.generate_text(prompt, n, temperature, stop, callbacks)

    def is_finished(self, response: LLMResult) -> bool:
        return True


class _LocalEmbeddings(BaseRagasEmbeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        from rag.src_rag.retriever.pdf import _model

        return _model().encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return self.embed_query(text)


def wrap_llm(llm: Llm) -> Any:
    return _GeminiForRagas(llm=llm)


def wrap_embeddings() -> Any:
    return _LocalEmbeddings()


def ragas_metrics() -> list[Any]:
    # strictness=1: the default of 3 only costs extra calls here because our calls are deterministic.
    return [
        Faithfulness(),
        ResponseRelevancy(strictness=1),
        LLMContextPrecisionWithReference(),
        LLMContextRecall(),
        AnswerCorrectness(),
    ]
