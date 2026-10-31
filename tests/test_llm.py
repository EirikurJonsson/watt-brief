import json

import httpx
import pytest

from watt_brief.config import Settings
from watt_brief.llm import LLMClient, LLMError
from watt_brief.logging import redact

SECRET = "sk-test1234567890abcdef"


def make_settings(**overrides) -> Settings:
    values = {
        "llm_base_url": "https://llm.example/v1",
        "llm_api_key": SECRET,
        "model_planner": "m",
        "model_analyst": "m",
        "model_critic": "m",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def client_with(handler, **overrides) -> LLMClient:
    return LLMClient(make_settings(**overrides), transport=httpx.MockTransport(handler))


def ok_response(**usage):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "hello"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, **usage},
        },
    )


def test_complete_returns_text_and_usage():
    c = client_with(lambda req: ok_response())
    result = c.complete("t", "m", "sys", "user")
    assert result.text == "hello"
    assert (result.input_tokens, result.output_tokens) == (10, 5)
    assert result.cost_usd is None  # no price known, so no invented number


def test_cost_from_provider_when_reported():
    c = client_with(lambda req: ok_response(estimated_cost=0.0042))
    assert c.complete("t", "m", "s", "u").cost_usd == 0.0042


def test_cost_from_config_prices():
    c = client_with(
        lambda req: ok_response(),
        price_input_per_mtok_usd=1.0,
        price_output_per_mtok_usd=2.0,
    )
    assert c.complete("t", "m", "s", "u").cost_usd == pytest.approx(20 / 1_000_000)


def test_request_carries_bearer_and_max_tokens():
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return ok_response()

    client_with(handler).complete("t", "m", "s", "u")
    assert seen["auth"] == f"Bearer {SECRET}"
    assert seen["body"]["max_tokens"] == 1000


def test_http_error_raises_without_leaking_key():
    c = client_with(lambda req: httpx.Response(401, json={"error": "nope"}))
    with pytest.raises(LLMError) as err:
        c.complete("t", "m", "s", "u")
    assert SECRET not in str(err.value)
    assert "401" in str(err.value)


def test_malformed_body_raises():
    c = client_with(lambda req: httpx.Response(200, json={"unexpected": True}))
    with pytest.raises(LLMError):
        c.complete("t", "m", "s", "u")


def test_redact_removes_keys_and_tokens():
    text = f"Authorization: Bearer {SECRET} and sk-abcdefgh12345 and securityToken=abc123&x=1"
    out = redact(text)
    assert SECRET not in out and "abcdefgh12345" not in out and "abc123" not in out
    assert "x=1" in out
