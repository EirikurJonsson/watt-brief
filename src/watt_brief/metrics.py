"""Prometheus metrics, on a per-app registry so tests never collide."""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "wb_requests_total", "Requests by outcome", ["outcome"], registry=self.registry
        )
        self.guard_rejections = Counter(
            "wb_guard_rejections_total",
            "Guard rejections",
            ["stage", "reason"],
            registry=self.registry,
        )
        self.latency = Histogram(
            "wb_request_seconds",
            "End-to-end request time",
            buckets=(0.5, 1, 2, 3, 5, 8, 13, 30),
            registry=self.registry,
        )
        self.llm_calls = Counter(
            "wb_llm_calls_total", "Model calls by step", ["step"], registry=self.registry
        )
        self.llm_tokens = Counter(
            "wb_llm_tokens_total", "Tokens", ["direction"], registry=self.registry
        )
        self.llm_cost = Counter("wb_llm_cost_usd_total", "Model spend", registry=self.registry)
        self.spend_today = Gauge("wb_spend_today_usd", "Spend today (UTC)", registry=self.registry)
        self.spend_cap = Gauge("wb_spend_cap_usd", "Daily spend cap", registry=self.registry)
        self.kill_switch = Gauge("wb_kill_switch", "1 when active", registry=self.registry)
        self.bans = Gauge("wb_banned_clients", "Clients currently banned", registry=self.registry)

    def render(self) -> bytes:
        return generate_latest(self.registry)
