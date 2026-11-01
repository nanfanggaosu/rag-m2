import os
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors

from rag.src_rag.llm import gemini
from rag.src_rag.llm.gemini import GeminiLlm, LlmError

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}


def _response(text, prompt_tokens=10, output_tokens=5, thinking_tokens=20):
    usage = SimpleNamespace(
        prompt_token_count=prompt_tokens,
        candidates_token_count=output_tokens,
        thoughts_token_count=thinking_tokens,
    )
    return SimpleNamespace(text=text, usage_metadata=usage)


def _api_error(code):
    return errors.APIError(code, {"error": {"code": code, "message": f"boom {code}", "status": "X"}})


class FakeClient:
    """Stands in for genai.Client: replays scripted responses or exceptions."""

    def __init__(self, *outcomes):
        self._outcomes = list(outcomes)
        self.requests = []
        self.models = self

    def generate_content(self, *, model, contents, config):
        self.requests.append(SimpleNamespace(model=model, contents=contents, config=config))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def make_llm(tmp_path):
    def make(*outcomes, **kwargs):
        client = FakeClient(*outcomes)
        sleeps = []
        llm = GeminiLlm("test-model", client=client, cache_dir=tmp_path, sleep=sleeps.append, **kwargs)
        return llm, client, sleeps
    return make


def test_complete_returns_text_with_deterministic_config(make_llm):
    llm, client, _ = make_llm(_response("hello"))
    assert llm.complete("hi") == "hello"
    req = client.requests[0]
    assert req.model == "test-model" and req.contents == "hi"
    assert req.config.temperature == 0.0
    assert req.config.response_mime_type is None


def test_complete_json_requests_structured_output(make_llm):
    llm, client, _ = make_llm(_response('{"answer": "Orks"}'))
    assert llm.complete_json("faction?", SCHEMA) == {"answer": "Orks"}
    config = client.requests[0].config
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == SCHEMA


def test_complete_json_retries_once_on_invalid_json(make_llm):
    llm, client, _ = make_llm(_response("not json"), _response('{"answer": "Orks"}'))
    assert llm.complete_json("faction?", SCHEMA) == {"answer": "Orks"}
    assert len(client.requests) == 2


def test_complete_json_gives_up_after_second_invalid_reply(make_llm):
    llm, _, _ = make_llm(_response("nope"), _response("[1, 2]"))
    with pytest.raises(LlmError, match="JSON object"):
        llm.complete_json("faction?", SCHEMA)


def test_rate_limit_is_retried_with_backoff(make_llm):
    llm, client, sleeps = make_llm(_api_error(429), _api_error(503), _response("ok"))
    assert llm.complete("hi") == "ok"
    assert len(client.requests) == 3
    assert sleeps == [2.0, 4.0]


def _quota_error(wait):
    return errors.APIError(429, {"error": {"code": 429, "message": f"Please retry in {wait}.", "status": "X"}})


def test_rate_limit_waits_as_long_as_the_server_asks(make_llm):
    llm, _, sleeps = make_llm(_quota_error("41.5s"), _response("ok"))
    assert llm.complete("hi") == "ok"
    assert sleeps == [42.5]


def test_used_up_daily_quota_fails_without_waiting(make_llm):
    llm, client, sleeps = make_llm(_quota_error("16h30m15.8s"))
    with pytest.raises(LlmError, match="429"):
        llm.complete("hi")
    assert sleeps == [] and len(client.requests) == 1


def test_min_interval_spaces_out_real_calls(make_llm):
    llm, _, sleeps = make_llm(_response("a"), _response("b"), min_interval_s=12.0)
    llm.complete("one")
    llm.complete("two")
    assert len(sleeps) == 1 and 11.0 < sleeps[0] <= 12.0


def test_min_interval_skips_cached_calls(make_llm):
    llm, _, sleeps = make_llm(_response("a"), min_interval_s=12.0)
    llm.complete("one")
    llm.complete("one")
    assert sleeps == []


def test_network_error_is_retried(make_llm):
    llm, _, sleeps = make_llm(httpx.ConnectError("down"), _response("ok"))
    assert llm.complete("hi") == "ok"
    assert sleeps == [2.0]


def test_client_error_is_not_retried(make_llm):
    llm, client, sleeps = make_llm(_api_error(400))
    with pytest.raises(LlmError, match="400"):
        llm.complete("hi")
    assert len(client.requests) == 1 and sleeps == []


def test_retries_are_bounded(make_llm):
    llm, client, _ = make_llm(*[_api_error(503)] * 3, max_retries=2)
    with pytest.raises(LlmError, match="503"):
        llm.complete("hi")
    assert len(client.requests) == 3


def test_empty_response_raises(make_llm):
    llm, _, _ = make_llm(_response(None))
    with pytest.raises(LlmError, match="no text"):
        llm.complete("hi")


def test_cache_hit_skips_the_api(make_llm):
    llm, client, _ = make_llm(_response("first"), _response("other"))
    assert llm.complete("hi") == "first"
    assert llm.complete("hi") == "first"
    assert len(client.requests) == 1
    assert [c.cached for c in llm.calls] == [False, True]
    assert llm.complete("different prompt") == "other"


def test_cache_can_be_disabled(make_llm):
    llm, client, _ = make_llm(_response("a"), _response("b"), use_cache=False)
    assert [llm.complete("hi"), llm.complete("hi")] == ["a", "b"]
    assert len(client.requests) == 2


def test_usage_sums_tokens(make_llm):
    llm, _, _ = make_llm(_response("a", 10, 5, 20), _response("b", 1, 2, 3))
    llm.complete("x")
    llm.complete("y")
    usage = llm.usage()
    assert (usage["calls"], usage["prompt_tokens"], usage["output_tokens"], usage["thinking_tokens"]) == (2, 11, 7, 23)


def test_missing_api_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(LlmError, match="GOOGLE_API_KEY"):
        GeminiLlm()


def test_model_can_come_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_MODEL", "env-model")
    assert GeminiLlm(client=FakeClient(), cache_dir=tmp_path).model == "env-model"
    monkeypatch.delenv("GEMINI_MODEL")
    assert GeminiLlm(client=FakeClient(), cache_dir=tmp_path).model == gemini.DEFAULT_MODEL


@pytest.mark.skipif(os.environ.get("LLM_LIVE_TESTS") != "1", reason="set LLM_LIVE_TESTS=1 to call the real API")
def test_live_json_call(tmp_path):
    llm = GeminiLlm(cache_dir=tmp_path)
    out = llm.complete_json("Which Warhammer 40k faction do Boyz belong to? One word.", SCHEMA)
    assert "ork" in out["answer"].lower()
