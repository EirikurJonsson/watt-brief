"""HTTP service. One endpoint that does work, behind every abuse control.

Order of checks, cheapest first: kill switch, ban, rate limit, spend cap, body size and shape,
concurrency, then the pipeline. Error bodies are fixed messages and never echo user input.
"""

import asyncio
import hmac
import ipaddress
import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, field_validator

from watt_brief.alerts import AlertManager
from watt_brief.brief import LANGUAGES
from watt_brief.chart import ZONE_LABELS, chart_payload
from watt_brief.config import Settings
from watt_brief.entsoe import ZONES
from watt_brief.errors import BriefError, GuardRejected
from watt_brief.guards import MESSAGES as GUARD_MESSAGES
from watt_brief.history import PriceHistory
from watt_brief.limits import AbuseTracker, KillSwitch, RateLimiter, SpendTracker
from watt_brief.llm import Completion, LLMClient, LLMError
from watt_brief.logging import log, new_request_id
from watt_brief.metrics import Metrics
from watt_brief.pipeline import FactsSource, NoDataError, run_pipeline
from watt_brief.planner import UNSPECIFIED
from watt_brief.sources import (
    WARM_INTERVAL_SECONDS,
    SeriesSource,
    build_history,
    build_series_source,
    facts_from,
)
from watt_brief.units import CURRENCIES, UNITS, make_display

logger = logging.getLogger(__name__)

# The commit this image was built from (set by CI), so "what is running" is one request.
VERSION = os.environ.get("GIT_SHA", "dev")[:12]

MAX_BODY_BYTES = 4096
STATIC_DIR = Path(__file__).parent / "static"

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
}

MESSAGES = {
    "killed": "The service is paused. Try again later.",
    "banned": "Too many requests. Try again later.",
    "rate_limited": "Too many requests. Try again later.",
    "budget": "Today's budget is used up. Try again tomorrow (UTC).",
    "busy": "The service is busy. Try again in a moment.",
    "bad_request": 'Send JSON like {"question": "When is power cheapest tomorrow?"}.',
    "too_large": "That request is too large.",
    "bad_type": "Send the request as application/json.",
    "error": "Something went wrong. Try again later.",
    "model_error": "I couldn't produce a brief right now. Try again later.",
}


def error_body(code: str) -> dict:
    """The English message for API users, plus a stable code the page translates."""
    return {"error": MESSAGES[code], "code": code}


class BriefRequest(BaseModel):
    question: str = Field(max_length=2000)
    # Choices from the page. A zone given here wins over a country named in the question.
    zone: str | None = None
    unit: str = "MWh"
    currency: str = "EUR"
    language: str = "en"

    @field_validator("language")
    @classmethod
    def _language_known(cls, value: str) -> str:
        if value not in LANGUAGES:
            raise ValueError("unknown language")
        return value

    @field_validator("zone")
    @classmethod
    def _zone_known(cls, value: str | None) -> str | None:
        if value is not None and value not in ZONES:
            raise ValueError("unknown zone")
        return value

    @field_validator("unit")
    @classmethod
    def _unit_known(cls, value: str) -> str:
        if value not in UNITS:
            raise ValueError("unknown unit")
        return value

    @field_validator("currency")
    @classmethod
    def _currency_known(cls, value: str) -> str:
        if value not in CURRENCIES:
            raise ValueError("unknown currency")
        return value


def create_app(
    settings: Settings,
    *,
    get_facts: FactsSource | None = None,
    get_series: SeriesSource | None = None,
    history: PriceHistory | None = None,
    llm_transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    if settings.effective_default_zone not in ZONES:
        raise ValueError(f"DEFAULT_ZONE must be one of {', '.join(ZONES)}")
    metrics = Metrics()
    spend = SpendTracker(settings.spend_db_path)
    kill = KillSwitch(settings.kill_switch_file)
    limiter = RateLimiter(settings.rate_limit_per_minute, settings.rate_limit_per_day)
    abuse = AbuseTracker()
    alerts = AlertManager(settings.alert_webhook_url, settings.alert_webhook_format)
    slots = threading.BoundedSemaphore(settings.max_concurrent_requests)
    if history is None and get_series is None:
        history = build_history(settings)

    def on_data_event(kind: str, result: str) -> None:
        counter = metrics.entsoe_fetches if kind == "fetch" else metrics.price_cache
        counter.labels(result).inc()

    series_source = get_series or build_series_source(settings, history, on_data_event)
    facts_source = get_facts or facts_from(series_source)
    price_limiter = RateLimiter(60, 2000)
    data_source = "synthetic" if settings.facts_source == "fixture" else "entsoe"
    metrics.spend_cap.set(settings.daily_spend_cap_usd)

    def stale_zones() -> list[str]:
        report = getattr(series_source, "serving_stale", None)
        return report() if report else []

    def previous_day(series):
        if history is None or not series.points:
            return None
        first = series.points[0].start
        return history.load(series.zone, first - timedelta(days=1), first)

    def on_completion(step: str, completion: Completion) -> None:
        cost = completion.cost_usd
        if cost is None:
            cost = settings.fallback_cost_per_call_usd
        spend.add(cost)
        metrics.llm_calls.labels(step).inc()
        metrics.llm_tokens.labels("input").inc(completion.input_tokens)
        metrics.llm_tokens.labels("output").inc(completion.output_tokens)
        metrics.llm_cost.inc(cost)

    llm = LLMClient(
        settings,
        transport=llm_transport,
        on_completion=on_completion,
        on_retry=lambda step, reason: metrics.llm_retries.labels(reason).inc(),
    )

    warm = getattr(series_source, "warm", None)

    async def keep_warm() -> None:
        """Fetch ahead of users: today's prices at start-up, tomorrow's as soon as they exist."""
        while True:
            try:
                await run_in_threadpool(warm)  # type: ignore[arg-type]
            except Exception:  # never let the warm-up loop die
                metrics.warm_failures.inc()
                logger.exception("warm_failed")
            await asyncio.sleep(WARM_INTERVAL_SECONDS)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        warmer = asyncio.create_task(keep_warm()) if warm else None
        yield
        if warmer:
            warmer.cancel()
        llm.close()
        spend.close()
        if history is not None:
            history.close()

    app = FastAPI(
        title="watt-brief", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    def client_key(request: Request) -> str:
        if settings.trust_cf_connecting_ip:
            header = request.headers.get("cf-connecting-ip", "")
            try:
                return str(ipaddress.ip_address(header.strip()))
            except ValueError:
                pass
        return request.client.host if request.client else "unknown"

    def finish(outcome: str, status: int, body: dict, started: float, retry_after: int = 0):
        elapsed = time.perf_counter() - started
        metrics.requests.labels(outcome).inc()
        metrics.latency.observe(elapsed)
        alerts.record(outcome)
        today = spend.today()
        metrics.spend_today.set(today)
        metrics.bans.set(abuse.banned_count)
        alerts.check(
            today, settings.daily_spend_cap_usd, kill.active(), abuse.banned_count, stale_zones()
        )
        log(logger, "request", outcome=outcome, status=status, latency_ms=int(elapsed * 1000))
        headers = {"Retry-After": str(retry_after)} if retry_after else None
        return JSONResponse(body, status_code=status, headers=headers)

    async def read_limited(request: Request) -> bytes | None:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            return None
        data = b""
        async for chunk in request.stream():
            data += chunk
            if len(data) > MAX_BODY_BYTES:
                return None
        return data

    @app.post("/api/brief")
    async def brief(request: Request):
        started = time.perf_counter()
        request_id = new_request_id()
        key = client_key(request)

        if kill.active():
            return finish("killed", 503, error_body("killed"), started)
        if abuse.is_banned(key):
            return finish("banned", 429, error_body("banned"), started, 3600)
        allowed, retry_after = limiter.check(key)
        if not allowed:
            return finish("rate_limited", 429, error_body("rate_limited"), started, retry_after)
        if spend.today() >= settings.daily_spend_cap_usd:
            return finish("budget", 503, error_body("budget"), started, 3600)

        # Requiring JSON forces a CORS preflight, which another website cannot pass, so a
        # visitor's browser cannot be tricked into spending our budget with a plain form post.
        if not request.headers.get("content-type", "").lower().startswith("application/json"):
            return finish("rejected", 415, error_body("bad_type"), started)

        raw = await read_limited(request)
        if raw is None:
            return finish("rejected", 413, error_body("too_large"), started)
        try:
            payload = BriefRequest.model_validate(json.loads(raw))
        except (ValueError, ValidationError):
            abuse.record_rejection(key)
            return finish("rejected", 422, error_body("bad_request"), started)

        if not slots.acquire(blocking=False):
            return finish("busy", 503, error_body("busy"), started, 5)
        try:
            result = await run_in_threadpool(
                run_pipeline,
                llm,
                settings,
                payload.question,
                facts_source,
                use_planner=settings.use_planner,
                use_critic=settings.use_critic,
                zone=payload.zone,
                language=payload.language,
            )
        except GuardRejected as exc:
            metrics.guard_rejections.labels(exc.stage, exc.reason).inc()
            abuse.record_rejection(key)
            code = exc.reason if exc.reason in GUARD_MESSAGES else "unsafe_output"
            return finish("rejected", 422, {"error": str(exc), "code": code}, started)
        except NoDataError as exc:
            return finish("no_data", 422, {"error": str(exc), "code": exc.code}, started)
        except (BriefError, LLMError):
            return finish("error", 502, error_body("model_error"), started)
        except Exception as exc:  # noqa: BLE001 - last resort, must not leak
            # Type only: the message could contain request data.
            log(logger, "unhandled_error", kind=type(exc).__name__)
            return finish("error", 500, error_body("error"), started)
        finally:
            slots.release()

        if payload.zone:
            zone_source = "selector"
        else:
            zone_source = "default" if result.plan.zone == UNSPECIFIED else "question"
        body = {
            "recommendation": result.brief.recommendation,
            "reasoning": result.brief.reasoning,
            "caveats": result.brief.caveats,
            "zone": result.facts.zone,
            "zone_source": zone_source,
            "window_hours": result.facts.window_hours,
            "data_source": data_source,
            # The written brief quotes the facts, which stay in EUR/MWh. Only the chart converts.
            "brief_unit": "EUR/MWh",
            "language": payload.language,
            "request_id": request_id,
        }
        try:
            series = series_source(result.facts.zone)
            display = make_display(payload.unit, payload.currency)
            body["chart"] = chart_payload(
                series,
                result.facts.window_hours,
                data_source,
                previous_day(series),
                display,
                datetime.now(UTC),
                result.plan.availability,
            )
        except (NoDataError, ValueError):
            pass  # the brief is still useful without the chart
        return finish("ok", 200, body, started)

    @app.get("/api/prices")
    async def prices(
        request: Request,
        zone: str | None = None,
        hours: int = 3,
        unit: str = "MWh",
        currency: str = "EUR",
    ):
        """The day's price curve and its cheapest and priciest windows. No model call."""
        allowed, retry_after = price_limiter.check(client_key(request))
        if not allowed:
            return JSONResponse(
                error_body("rate_limited"),
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        zone = zone or settings.effective_default_zone
        if not (zone in ZONES and 1 <= hours <= 6 and unit in UNITS and currency in CURRENCIES):
            return JSONResponse(
                {"error": "Unknown zone, window, unit or currency.", "code": "bad_query"},
                status_code=422,
            )
        try:
            series = series_source(zone)
            display = make_display(unit, currency)
            payload = chart_payload(
                series, hours, data_source, previous_day(series), display, datetime.now(UTC)
            )
        except (NoDataError, ValueError) as exc:
            code = exc.code if isinstance(exc, NoDataError) else "no_data"
            return JSONResponse({"error": str(exc), "code": code}, status_code=404)
        return JSONResponse(payload, headers={"Cache-Control": "public, max-age=300"})

    @app.get("/api/zones")
    async def zones():
        """The supported zones, so the page never keeps its own list."""
        return JSONResponse(
            [{"code": code, "label": ZONE_LABELS[code]} for code in ZONES],
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @app.get("/healthz")
    async def healthz():
        cap = settings.daily_spend_cap_usd
        used = spend.today() / cap if cap > 0 else 1.0
        killed = kill.active()
        stale = stale_zones()
        status = "degraded" if killed or used >= 1.0 or stale else "ok"
        through_report = getattr(series_source, "prices_through", None)
        return {
            "status": status,
            "spend_used_pct": round(min(used, 9.99) * 100),
            "data_source": "synthetic" if settings.facts_source == "fixture" else "entsoe",
            "stale_zones": stale,
            "prices_through": through_report() if through_report else None,
            "version": VERSION,
        }

    @app.get("/metrics")
    async def metrics_endpoint(request: Request):
        token = settings.metrics_token
        if token is None:
            return Response(status_code=404)
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(supplied, token.get_secret_value()):
            return Response(status_code=404)
        metrics.spend_today.set(spend.today())
        metrics.kill_switch.set(1 if kill.active() else 0)
        metrics.stale_zones.set(len(stale_zones()))
        metrics.history_rows.set(history.count() if history else 0)
        return PlainTextResponse(
            metrics.render().decode(), media_type="text/plain; version=0.0.4; charset=utf-8"
        )

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/privacy", include_in_schema=False)
    async def privacy():
        return FileResponse(STATIC_DIR / "privacy.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app
