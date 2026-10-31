"""Thin OpenAI-compatible chat client. Records tokens, latency and cost per call. See ADR 001."""

import logging
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


class LLMClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        on_completion: Callable[[str, Completion], None] | None = None,
    ):
        self._settings = settings
        # Called for every successful call, so spend is counted even if the request later fails.
        self._on_completion = on_completion
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
            response = self._http.post("/chat/completions", json=payload)
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
