import httpx
import pytest

from watt_brief.config import Settings
from watt_brief.llm import LLMClient, LLMError

SECRET = "sk-test-retry-key-123456"
OK = {
    "choices": [{"message": {"content": "hi"}}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
}


def settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        llm_base_url="https://x/v1",
        llm_api_key=SECRET,
        model_planner="m",
        model_analyst="m",
        model_critic="m",
        **overrides,
    )


def client(responses, **overrides):
    """responses: list of httpx.Response or Exception, consumed in order (the last repeats)."""
    calls, sleeps, retries = [], [], []

    def handler(req: httpx.Request):
        calls.append(req)
        item = responses[min(len(calls), len(responses)) - 1]
        if isinstance(item, Exception):
            raise item
        return item

    c = LLMClient(
        settings(**overrides),
        transport=httpx.MockTransport(handler),
        on_retry=lambda step, reason: retries.append((step, reason)),
        sleep=sleeps.append,
    )
    return c, calls, sleeps, retries


def ok():
    return httpx.Response(200, json=OK)


def test_a_server_error_is_retried_then_succeeds():
    c, calls, sleeps, retries = client([httpx.Response(503), ok()])
    assert c.complete("t", "m", "s", "u").text == "hi"
    assert len(calls) == 2 and retries == [("t", "http_503")]
    assert 0.5 <= sleeps[0] <= 0.76


def test_backoff_grows_between_attempts():
    c, calls, sleeps, _ = client([httpx.Response(500), httpx.Response(500), ok()])
    c.complete("t", "m", "s", "u")
    assert len(calls) == 3 and sleeps[1] > sleeps[0]


def test_retries_are_bounded_and_the_final_error_is_reported():
    c, calls, _, _ = client([httpx.Response(502)], llm_max_retries=2)
    with pytest.raises(LLMError, match="HTTP 502"):
        c.complete("t", "m", "s", "u")
    assert len(calls) == 3


def test_rate_limit_honours_retry_after_up_to_a_cap():
    c, _, sleeps, _ = client([httpx.Response(429, headers={"retry-after": "2"}), ok()])
    c.complete("t", "m", "s", "u")
    assert sleeps == [2.0]

    c, _, sleeps, _ = client([httpx.Response(429, headers={"retry-after": "600"}), ok()])
    c.complete("t", "m", "s", "u")
    assert sleeps == [5.0]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_client_errors_are_not_retried(status):
    c, calls, sleeps, _ = client([httpx.Response(status)])
    with pytest.raises(LLMError, match=str(status)):
        c.complete("t", "m", "s", "u")
    assert len(calls) == 1 and sleeps == []


def test_timeouts_and_connection_errors_are_retried():
    c, calls, _, retries = client([httpx.ReadTimeout("slow"), httpx.ConnectError("down"), ok()])
    assert c.complete("t", "m", "s", "u").text == "hi"
    assert len(calls) == 3
    assert [r for _, r in retries] == ["ReadTimeout", "ConnectError"]


def test_persistent_network_failure_raises_a_clean_error_without_the_key():
    c, calls, _, _ = client([httpx.ConnectError("boom")], llm_max_retries=1)
    with pytest.raises(LLMError) as err:
        c.complete("t", "m", "s", "u")
    assert len(calls) == 2 and SECRET not in str(err.value)


def test_the_total_time_budget_stops_retries_early():
    c, calls, _, _ = client([httpx.Response(503)], llm_retry_budget_seconds=0.1)
    with pytest.raises(LLMError):
        c.complete("t", "m", "s", "u")
    assert len(calls) == 1  # the first backoff alone would blow the budget


def test_cost_is_only_counted_for_the_successful_attempt():
    spent = []
    calls = []

    def handler(req):
        calls.append(req)
        if len(calls) == 1:
            return httpx.Response(500)
        body = {**OK, "usage": {**OK["usage"], "estimated_cost": 0.002}}
        return httpx.Response(200, json=body)

    c = LLMClient(
        settings(),
        transport=httpx.MockTransport(handler),
        on_completion=lambda step, comp: spent.append(comp.cost_usd),
        sleep=lambda s: None,
    )
    c.complete("t", "m", "s", "u")
    assert spent == [0.002]
