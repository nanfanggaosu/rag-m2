"""Shared Google AI Studio (Gemini) wrapper implementing `interfaces.Llm`.

Try it:
    uv run python -m rag.src_rag.llm.gemini "Say hi in five words"
    uv run python -m rag.src_rag.llm.gemini --json "Which Warhammer 40k faction are Boyz from?"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = PROJECT_ROOT / "rag" / "data" / "cache" / "llm"

# Pinned rather than a "-latest" alias so cached results and eval numbers stay reproducible.
DEFAULT_MODEL = "gemini-3.5-flash"
TIMEOUT_MS = 60_000
RETRYABLE_CODES = frozenset({429, 500, 502, 503, 504})
# A longer wait than this is a used-up daily quota, not a per-minute limit: fail fast.
MAX_RETRY_WAIT_S = 120.0
_RETRY_IN = re.compile(r"retry in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s")

load_dotenv(PROJECT_ROOT / ".env")


class LlmError(RuntimeError):
    pass


@dataclass(frozen=True)
class LlmCall:
    model: str
    cached: bool
    elapsed_ms: float
    prompt_tokens: int
    output_tokens: int
    thinking_tokens: int


def _server_retry_delay(message: str | None) -> float | None:
    m = _RETRY_IN.search(message or "")
    if not m:
        return None
    return int(m[1] or 0) * 3600 + int(m[2] or 0) * 60 + float(m[3]) + 1.0


def _api_key() -> str:
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise LlmError("GOOGLE_API_KEY is not set: copy .env.example to .env and fill it in")
    return key


class GeminiLlm:
    def __init__(
        self,
        model: str | None = None,
        *,
        temperature: float = 0.0,
        use_cache: bool = True,
        cache_dir: Path = CACHE_DIR,
        max_retries: int = 3,
        min_interval_s: float | None = None,
        client: Any = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = model or os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
        self.temperature = temperature
        self.use_cache = use_cache
        self.cache_dir = cache_dir
        self.max_retries = max_retries
        if min_interval_s is None:
            min_interval_s = float(os.environ.get("GEMINI_MIN_INTERVAL_S") or 0)
        self.min_interval_s = min_interval_s
        self._next_call_at = 0.0
        self.calls: list[LlmCall] = []
        self._client = client or genai.Client(
            api_key=_api_key(), http_options=types.HttpOptions(timeout=TIMEOUT_MS)
        )
        self._sleep = sleep

    def complete(self, prompt: str) -> str:
        return self._generate(prompt, None)

    def complete_json(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(2):
            text = self._generate(prompt, schema, refresh=attempt > 0)
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
        raise LlmError(f"model did not return a JSON object: {text[:200]!r}")

    def usage(self) -> dict[str, float]:
        return {
            "calls": len(self.calls),
            "cached_calls": sum(c.cached for c in self.calls),
            "prompt_tokens": sum(c.prompt_tokens for c in self.calls),
            "output_tokens": sum(c.output_tokens for c in self.calls),
            "thinking_tokens": sum(c.thinking_tokens for c in self.calls),
            "elapsed_ms": sum(c.elapsed_ms for c in self.calls),
        }

    def _cache_path(self, prompt: str, schema: dict[str, Any] | None) -> Path:
        key = json.dumps([self.model, self.temperature, prompt, schema], sort_keys=True)
        return self.cache_dir / f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    def _generate(self, prompt: str, schema: dict[str, Any] | None, refresh: bool = False) -> str:
        t0 = time.perf_counter()
        path = self._cache_path(prompt, schema)
        if self.use_cache and not refresh and path.exists():
            text = json.loads(path.read_text(encoding="utf-8"))["text"]
            self.calls.append(LlmCall(self.model, True, (time.perf_counter() - t0) * 1000, 0, 0, 0))
            return text

        config = types.GenerateContentConfig(
            temperature=self.temperature,
            response_mime_type="application/json" if schema else None,
            response_json_schema=schema,
        )
        resp = self._call_with_retry(prompt, config)
        if resp.text is None:
            raise LlmError("model returned no text (empty or blocked response)")

        u = resp.usage_metadata
        self.calls.append(LlmCall(
            self.model, False, (time.perf_counter() - t0) * 1000,
            (u and u.prompt_token_count) or 0,
            (u and u.candidates_token_count) or 0,
            (u and u.thoughts_token_count) or 0,
        ))
        if self.use_cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(
                {"model": self.model, "prompt": prompt, "schema": schema, "text": resp.text},
                ensure_ascii=False, indent=2,
            ), encoding="utf-8")
        return resp.text

    def _call_with_retry(self, prompt: str, config: types.GenerateContentConfig) -> Any:
        for attempt in range(self.max_retries + 1):
            self._wait_for_turn()
            delay = 2.0 * 2**attempt
            try:
                return self._client.models.generate_content(
                    model=self.model, contents=prompt, config=config
                )
            except errors.APIError as e:
                if e.code not in RETRYABLE_CODES or attempt == self.max_retries:
                    raise LlmError(f"Gemini API error {e.code}: {e.message}") from e
                delay = _server_retry_delay(e.message) or delay
                if delay > MAX_RETRY_WAIT_S:
                    raise LlmError(f"Gemini API error {e.code}: {e.message}") from e
            except httpx.TransportError as e:
                if attempt == self.max_retries:
                    raise LlmError(f"network error talking to Gemini: {e}") from e
            self._sleep(delay)
        raise AssertionError("unreachable")

    def _wait_for_turn(self) -> None:
        wait = self._next_call_at - time.monotonic()
        if wait > 0:
            self._sleep(wait)
        self._next_call_at = time.monotonic() + self.min_interval_s


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", nargs="+")
    parser.add_argument("--json", action="store_true", help="ask for {answer, confidence} JSON")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--model")
    args = parser.parse_args()

    llm = GeminiLlm(args.model, use_cache=not args.no_cache)
    prompt = " ".join(args.prompt)
    if args.json:
        schema = {
            "type": "object",
            "properties": {"answer": {"type": "string"}, "confidence": {"type": "number"}},
            "required": ["answer", "confidence"],
        }
        print(json.dumps(llm.complete_json(prompt, schema), ensure_ascii=False, indent=2))
    else:
        print(llm.complete(prompt))
    print(f"\n-- model={llm.model} {llm.usage()}")


if __name__ == "__main__":
    main()
