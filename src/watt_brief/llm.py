"""Thin OpenAI-compatible chat client. Records tokens, latency and cost per call. See ADR 001."""

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from watt_brief.config import Settings
from watt_brief.logging import log

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """A model call failed. The message never contains credentials."""


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float | None  # None when neither the provider nor config gives a price


# Transient: worth another try. Anything else (bad key, bad request) is not.
RETRY_STATUSES = {408, 429, *range(500, 600)}
MAX_RETRY_AFTER_SECONDS = 5.0


class LLMClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        on_completion: Callable[[str, Completion], None] | None = None,
        on_retry: Callable[[str, str], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._settings = settings
        # Called for every successful call, so spend is counted even if the request later fails.
        self._on_completion = on_completion
        self._on_retry = on_retry
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=settings.llm_base_url,
            headers={"Authorization": f"Bearer {settings.llm_api_key.get_secret_value()}"},
            timeout=settings.llm_timeout_seconds,
            transport=transport,
        )

    def complete(self, step: str, model: str, system: str, user: str) -> Completion:
        payload = {
            "model": model,
            "max_tokens": self._settings.max_output_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        start = time.perf_counter()
        try:
            response = self._post_with_retries(step, model, payload, start)
            response.raise_for_status()
            body = response.json()
            text = body["choices"][0]["message"]["content"]
            usage = body.get("usage", {})
        except httpx.HTTPStatusError as exc:
            log(logger, "llm_error", step=step, model=model, status=exc.response.status_code)
            raise LLMError(f"model call failed with HTTP {exc.response.status_code}") from None
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            log(logger, "llm_error", step=step, model=model, kind=type(exc).__name__)
            raise LLMError(f"model call failed: {type(exc).__name__}") from None

        latency_ms = int((time.perf_counter() - start) * 1000)
        input_tokens = int(usage.get("prompt_tokens", 0))
        output_tokens = int(usage.get("completion_tokens", 0))
        completion = Completion(
            text=text,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=self._cost(usage, input_tokens, output_tokens),
        )
        if self._on_completion:
            self._on_completion(step, completion)
        log(
            logger,
            "llm_call",
            step=step,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_usd=completion.cost_usd,
        )
        return completion

    def _post_with_retries(
        self, step: str, model: str, payload: dict, start: float
    ) -> httpx.Response:
        """POST, retrying transient failures with backoff inside a total time budget."""
        s = self._settings
        attempt = 0
        while True:
            retry_after: float | None = None
            try:
                response = self._http.post("/chat/completions", json=payload)
                if response.status_code not in RETRY_STATUSES:
                    return response
                reason = f"http_{response.status_code}"
                header = response.headers.get("retry-after", "")
                if header.isdigit():
                    retry_after = min(float(header), MAX_RETRY_AFTER_SECONDS)
                last: httpx.Response | None = response
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                reason = type(exc).__name__
                last = None

            delay = (
                retry_after
                if retry_after is not None
                else 0.5 * 2**attempt + random.random() * 0.25
            )
            elapsed = time.perf_counter() - start
            if attempt >= s.llm_max_retries or elapsed + delay > s.llm_retry_budget_seconds:
                if last is not None:
                    return last  # the caller turns the final error status into an LLMError
                raise httpx.TransportError(reason)
            attempt += 1
            log(
                logger,
                "llm_retry",
                step=step,
                model=model,
                attempt=attempt,
                reason=reason,
                delay_s=round(delay, 2),
            )
            if self._on_retry:
                self._on_retry(step, reason)
            self._sleep(delay)

    def _cost(self, usage: dict, input_tokens: int, output_tokens: int) -> float | None:
        reported = usage.get("estimated_cost")
        if isinstance(reported, int | float):
            return float(reported)
        s = self._settings
        if s.price_input_per_mtok_usd is None or s.price_output_per_mtok_usd is None:
            return None
        return (
            input_tokens * s.price_input_per_mtok_usd + output_tokens * s.price_output_per_mtok_usd
        ) / 1_000_000

    def close(self) -> None:
        self._http.close()
