"""Scripted `interfaces.Llm` for tests: no network, no API key, deterministic."""
from __future__ import annotations

import json
from collections import deque
from collections.abc import Iterable
from typing import Any


class FakeLlm:
    def __init__(self, replies: Iterable[str | dict[str, Any]]) -> None:
        self._replies = deque(replies)
        self.prompts: list[str] = []

    def _next(self, prompt: str) -> str | dict[str, Any]:
        self.prompts.append(prompt)
        if not self._replies:
            raise AssertionError(f"FakeLlm ran out of replies at prompt #{len(self.prompts)}")
        return self._replies.popleft()

    def complete(self, prompt: str) -> str:
        reply = self._next(prompt)
        return reply if isinstance(reply, str) else json.dumps(reply)

    def complete_json(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        reply = self._next(prompt)
        return reply if isinstance(reply, dict) else json.loads(reply)
