"""Where price facts come from: synthetic fixture for demos, ENTSO-E for the real thing."""

import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from watt_brief.analysis import PriceFacts, analyse
from watt_brief.config import Settings
from watt_brief.entsoe import ZONES, EntsoeClient, EntsoeError, PriceSeries, parse_day_ahead_xml
from watt_brief.history import PriceHistory
from watt_brief.logging import log
from watt_brief.pipeline import FactsSource, NoDataError

logger = logging.getLogger(__name__)

FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/day_ahead_full_day.xml"
MARKET_TZ = ZoneInfo("Europe/Brussels")
CACHE_SECONDS = 3600
# If ENTSO-E is down when an entry expires, keep serving the old one for this long. Published
# day-ahead prices do not change; the chart shows the fetch time, so staleness is visible.
STALE_SECONDS = 12 * 3600


SeriesSource = Callable[[str], PriceSeries]


def facts_from(series_source: SeriesSource) -> FactsSource:
    def get(zone: str, window_hours: int) -> PriceFacts:
        return analyse(series_source(zone), window_hours=window_hours)

    return get


def fixture_series_source() -> SeriesSource:
    """The synthetic DE_LU fixture. Any other zone honestly has no data."""
    series = parse_day_ahead_xml(FIXTURE.read_text(), "DE_LU")

    def get(zone: str) -> PriceSeries:
        if zone != "DE_LU":
            raise NoDataError("I don't have price data for that zone yet.")
        return series

    return get


def fixture_facts_source() -> FactsSource:
    return facts_from(fixture_series_source())


def _delivery_days(now: datetime) -> list[tuple[datetime, datetime]]:
    """Tomorrow then today, as UTC (start, end) pairs for the Brussels-time market day."""
    local_midnight = now.astimezone(MARKET_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    days = []
    for offset in (1, 0):
        start = local_midnight + timedelta(days=offset)
        end = local_midnight + timedelta(days=offset + 1)
        days.append((start.astimezone(UTC), end.astimezone(UTC)))
    return days


class EntsoeSeriesSource:
    """Real prices, cached per zone so user traffic cannot hammer ENTSO-E.

    One fetch per zone at a time: concurrent requests on a cold or expired entry wait for the
    first and reuse its result. If a refresh fails, an entry younger than STALE_SECONDS is served,
    from memory or, after a restart, from the history table. Every fetch is written to history.
    """

    def __init__(
        self,
        settings: Settings,
        client: EntsoeClient | None = None,
        history: PriceHistory | None = None,
    ):
        self._entsoe = client or EntsoeClient(settings)
        self._history = history
        self._cache: dict[str, tuple[float, PriceSeries]] = {}
        self._lock = threading.Lock()
        self._zone_locks = {zone: threading.Lock() for zone in ZONES}
        self._serving_stale: set[str] = set()

    def _cached(self, zone: str, max_age: float) -> PriceSeries | None:
        with self._lock:
            hit = self._cache.get(zone)
        if hit and time.monotonic() - hit[0] < max_age:
            return hit[1]
        return None

    def _from_history(self, zone: str) -> PriceSeries | None:
        if self._history is None:
            return None
        for start, end in _delivery_days(datetime.now(UTC)):
            series = self._history.load(zone, start, end)
            if series and series.fetched_at:
                age = (datetime.now(UTC) - series.fetched_at).total_seconds()
                if age < STALE_SECONDS:
                    return series
        return None

    def __call__(self, zone: str) -> PriceSeries:
        fresh = self._cached(zone, CACHE_SECONDS)
        if fresh:
            return fresh
        if zone not in self._zone_locks:
            raise NoDataError("I don't have price data for that zone yet.")
        with self._zone_locks[zone]:
            fresh = self._cached(zone, CACHE_SECONDS)  # another request may have refreshed it
            if fresh:
                return fresh
            last_error: EntsoeError | None = None
            for start, end in _delivery_days(datetime.now(UTC)):
                try:
                    series = self._entsoe.day_ahead_prices(zone, start, end)
                except EntsoeError as exc:
                    last_error = exc
                    continue
                series = replace(series, fetched_at=datetime.now(UTC))
                with self._lock:
                    self._cache[zone] = (time.monotonic(), series)
                    self._serving_stale.discard(zone)
                self._record(series)
                return series
            stale = self._cached(zone, STALE_SECONDS) or self._from_history(zone)
            if stale:
                with self._lock:
                    self._serving_stale.add(zone)
                log(logger, "entsoe_stale", zone=zone)
                return stale
            log(logger, "entsoe_unavailable", zone=zone)
            raise NoDataError("Price data is not available right now.") from last_error

    def _record(self, series: PriceSeries) -> None:
        if self._history is None:
            return
        try:
            self._history.save(series)
        except sqlite3.Error as exc:  # history is a bonus: never fail a request over it
            log(logger, "history_write_failed", zone=series.zone, kind=type(exc).__name__)

    def serving_stale(self) -> list[str]:
        """Zones whose last refresh failed and are being answered from old data."""
        with self._lock:
            return sorted(self._serving_stale)

    def oldest_fetch_age_seconds(self) -> float | None:
        """Age of the least recently fetched cached zone; None before the first fetch."""
        with self._lock:
            ages = [time.monotonic() - at for at, _ in self._cache.values()]
        return max(ages) if ages else None


def entsoe_series_source(
    settings: Settings, client: EntsoeClient | None = None, history: PriceHistory | None = None
) -> EntsoeSeriesSource:
    return EntsoeSeriesSource(settings, client, history)


def entsoe_facts_source(settings: Settings, client: EntsoeClient | None = None) -> FactsSource:
    return facts_from(entsoe_series_source(settings, client))


def build_history(settings: Settings) -> PriceHistory | None:
    """Only real prices are worth keeping: the synthetic day must never reach the table."""
    if settings.facts_source != "entsoe":
        return None
    return PriceHistory(settings.history_db_path)


def build_series_source(settings: Settings, history: PriceHistory | None = None) -> SeriesSource:
    if settings.facts_source == "entsoe":
        return entsoe_series_source(settings, history=history)
    return fixture_series_source()


def build_facts_source(settings: Settings) -> FactsSource:
    return facts_from(build_series_source(settings))
