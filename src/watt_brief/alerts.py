"""Alert rules. Pure evaluation plus a small manager that de-duplicates and notifies.

Rules fire on spend nearing the cap, an error spike, an abuse pattern, and the kill switch.
Notification is a structured log line, plus an optional webhook if one is configured. The webhook
body is `{"text": ...}` JSON by default, or a plain-text ntfy message (`webhook_format="ntfy"`).
"""

import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from watt_brief.logging import log

logger = logging.getLogger(__name__)

WINDOW = 50  # recent requests considered for rates
MIN_REQUESTS = 20  # no rate alerts on tiny samples
ERROR_RATE_LIMIT = 0.2
REJECTION_RATE_LIMIT = 0.5
COOLDOWN_SECONDS = 1800


@dataclass(frozen=True)
class Alert:
    name: str
    severity: str  # "warning" or "critical"
    message: str


def webhook_request(alert: Alert, webhook_format: str) -> dict:
    """httpx keyword arguments for one alert. Headers stay ASCII, which HTTP requires."""
    text = f"[watt-brief {alert.severity}] {alert.message}"
    if webhook_format == "ntfy":
        critical = alert.severity == "critical"
        return {
            "content": alert.message.encode(),
            "headers": {
                "Title": f"watt-brief: {alert.name}",
                "Priority": "high" if critical else "default",
                "Tags": "rotating_light" if critical else "warning",
            },
        }
    return {"json": {"text": text}}


def evaluate(
    spend_today: float,
    cap: float,
    outcomes: list[str],
    kill_active: bool,
    banned_keys: int,
) -> list[Alert]:
    alerts = []
    if kill_active:
        alerts.append(Alert("kill_switch", "critical", "Kill switch is active; serving nothing."))
    if cap > 0:
        used = spend_today / cap
        if used >= 1.0:
            alerts.append(
                Alert("spend_cap", "critical", f"Daily spend cap reached: ${spend_today:.4f}.")
            )
        elif used >= 0.8:
            alerts.append(Alert("spend_high", "warning", f"Daily spend at {used:.0%} of the cap."))
    if len(outcomes) >= MIN_REQUESTS:
        errors = sum(1 for o in outcomes if o == "error") / len(outcomes)
        rejected = sum(1 for o in outcomes if o in ("rejected", "rate_limited")) / len(outcomes)
        if errors > ERROR_RATE_LIMIT:
            alerts.append(
                Alert("error_spike", "critical", f"{errors:.0%} of recent requests failed.")
            )
        if rejected > REJECTION_RATE_LIMIT:
            alerts.append(
                Alert("abuse_pattern", "warning", f"{rejected:.0%} of recent requests rejected.")
            )
    if banned_keys:
        alerts.append(
            Alert("bans_active", "warning", f"{banned_keys} client(s) temporarily banned.")
        )
    return alerts


class AlertManager:
    def __init__(
        self,
        webhook_url: str | None = None,
        webhook_format: str = "json",
        clock: Callable[[], float] = time.monotonic,
        post: Callable[[str, Alert, str], None] | None = None,
    ):
        self._webhook_url = webhook_url
        self._format = webhook_format
        self._clock = clock
        self._post = post or self._post_webhook
        self._last_fired: dict[str, float] = {}
        self.outcomes: deque[str] = deque(maxlen=WINDOW)

    def record(self, outcome: str) -> None:
        self.outcomes.append(outcome)

    def check(
        self, spend_today: float, cap: float, kill_active: bool, banned_keys: int
    ) -> list[Alert]:
        """Evaluate rules and notify each alert at most once per cooldown."""
        fired = []
        now = self._clock()
        for alert in evaluate(spend_today, cap, list(self.outcomes), kill_active, banned_keys):
            last = self._last_fired.get(alert.name)
            if last is not None and now - last < COOLDOWN_SECONDS:
                continue
            self._last_fired[alert.name] = now
            fired.append(alert)
            level = logging.ERROR if alert.severity == "critical" else logging.WARNING
            log(
                logger,
                "alert",
                level=level,
                name=alert.name,
                severity=alert.severity,
                message=alert.message,
            )
            if self._webhook_url:
                self._post(self._webhook_url, alert, self._format)
        return fired

    @staticmethod
    def _post_webhook(url: str, alert: Alert, webhook_format: str) -> None:
        try:
            httpx.post(url, timeout=5.0, **webhook_request(alert, webhook_format))
        except httpx.HTTPError as exc:
            # Never let a broken notifier break the service; do not log the URL (may hold a token).
            log(logger, "alert_webhook_failed", kind=type(exc).__name__)
