"""EUR/DKK from Frankfurter (ECB reference rates), cached in process.

No rate is ever hardcoded. If the fetch fails the caller shows EUR and says so.
"""

import logging
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from watt_brief.logging import log
from watt_brief.units import Display

logger = logging.getLogger(__name__)

FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest?base=EUR&symbols=DKK"
CACHE_SECONDS = 3600
# After a failed fetch, do not retry for this long, so an outage is not hammered by page loads.
RETRY_SECONDS = 60


@dataclass(frozen=True)
class FxRate:
    rate: float  # DKK per EUR
    date: str  # the date the rate is published for
    source: str = "frankfurter.app"


RateSource = Callable[[], FxRate | None]


class FxSource:
    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        # follow_redirects: the old .app host still 301s to the .dev API. Without this, the
        # redirect body is not JSON and every DKK request would quietly fall back to EUR.
        self._client = httpx.Client(transport=transport, timeout=5.0, follow_redirects=True)
        self._clock = clock
        self._lock = threading.Lock()
        self._rate: FxRate | None = None
        self._expires = 0.0

    def __call__(self) -> FxRate | None:
        with self._lock:
            if self._clock() < self._expires:
                return self._rate
            self._rate = self._fetch()
            self._expires = self._clock() + (CACHE_SECONDS if self._rate else RETRY_SECONDS)
            return self._rate

    def _fetch(self) -> FxRate | None:
        try:
            response = self._client.get(FRANKFURTER_URL)
            response.raise_for_status()
            body = response.json()
            rate = float(body["rates"]["DKK"])
            date = str(body["date"])
            if not math.isfinite(rate) or rate <= 0:
                raise ValueError("bad rate")
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            log(logger, "fx_unavailable", kind=type(exc).__name__)
            return None
        return FxRate(rate=rate, date=date)


def make_display(unit: str, currency: str, get_rate: RateSource) -> Display:
    if currency != "DKK":
        return Display(unit=unit)
    fx = get_rate()
    if fx is None:
        return Display(unit=unit, fallback=True)
    return Display(unit=unit, currency="DKK", rate=fx.rate, rate_date=fx.date)
