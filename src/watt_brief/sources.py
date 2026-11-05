"""Where price facts come from: synthetic fixture for demos, ENTSO-E for the real thing."""

import logging
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
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
# Day-ahead prices for a delivery day are final once published, so a day is fetched once and kept
# (in memory and in the history table). Nothing here expires by age. What changes through the day
# is only whether tomorrow's prices exist yet.
#
# ENTSO-E has them from about 12:45 Brussels time. Before the first check we do not ask at all;
# after it we ask again every TOMORROW_RETRY_SECONDS until they appear.
TOMORROW_FIRST_CHECK = time(12, 30)
TOMORROW_OVERDUE = time(15, 0)  # still missing now: raise the alert
TOMORROW_RETRY_SECONDS = 600
# After a failed fetch of today's prices, wait before asking again, so an outage is not hammered.
TODAY_RETRY_SECONDS = 60
WARM_INTERVAL_SECONDS = 300


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
            raise NoDataError("I don't have price data for that zone yet.", "zone_unknown")
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


Day = tuple[datetime, datetime]  # UTC (start, end) of one Brussels-time delivery day


class EntsoeSeriesSource:
    """Real prices, fetched once per zone and delivery day and then served from the cache.

    Order of lookup for a day: memory, the history table (which survives restarts), ENTSO-E.
    One fetch per zone at a time, so concurrent requests share the result. Tomorrow's prices are
    preferred once they exist; until then today's are served. A background `warm()` keeps the
    cache full so users rarely wait on ENTSO-E.
    """

    def __init__(
        self,
        settings: Settings,
        client: EntsoeClient | None = None,
        history: PriceHistory | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._entsoe = client or EntsoeClient(settings)
        self._history = history
        self._clock = clock
        self._days: dict[tuple[str, datetime], PriceSeries] = {}
        self._attempted: dict[tuple[str, datetime], datetime] = {}
        self._tomorrow_missing: set[str] = set()
        self._lock = threading.Lock()
        self._zone_locks = {zone: threading.Lock() for zone in ZONES}

    def _complete(self, series: PriceSeries, day: Day) -> bool:
        expected = (day[1] - day[0]) / timedelta(minutes=series.resolution_minutes)
        return len(series.points) >= expected

    def _get_day(
        self, zone: str, day: Day, *, fetch: bool, retry_seconds: float
    ) -> PriceSeries | None:
        key = (zone, day[0])
        with self._lock:
            hit = self._days.get(key)
        if hit:
            return hit
        with self._zone_locks[zone]:
            with self._lock:
                hit = self._days.get(key)
            if hit:  # another request got it while this one waited
                return hit
            stored = self._history.load(zone, *day) if self._history else None
            if stored and self._complete(stored, day):
                with self._lock:
                    self._days[key] = stored
                return stored
            now = self._clock()
            last = self._attempted.get(key)
            if not fetch or (last and (now - last).total_seconds() < retry_seconds):
                return None
            self._attempted[key] = now
            try:
                series = self._entsoe.day_ahead_prices(zone, *day)
            except EntsoeError as exc:
                log(logger, "entsoe_not_available", zone=zone, day=day[0].isoformat(), why=str(exc))
                return None
            series = replace(series, fetched_at=now)
            with self._lock:
                self._days[key] = series
            self._record(series)
            return series

    def __call__(self, zone: str) -> PriceSeries:
        if zone not in self._zone_locks:
            raise NoDataError("I don't have price data for that zone yet.", "zone_unknown")
        now = self._clock()
        tomorrow, today = _delivery_days(now)
        self._forget_before(today[0])
        local = now.astimezone(MARKET_TZ).time()

        series = self._get_day(
            zone,
            tomorrow,
            fetch=local >= TOMORROW_FIRST_CHECK,
            retry_seconds=TOMORROW_RETRY_SECONDS,
        )
        if series is None:
            series = self._get_day(zone, today, fetch=True, retry_seconds=TODAY_RETRY_SECONDS)
            with self._lock:
                if series is not None and local >= TOMORROW_OVERDUE:
                    self._tomorrow_missing.add(zone)
        else:
            with self._lock:
                self._tomorrow_missing.discard(zone)
        if series is None:
            log(logger, "entsoe_unavailable", zone=zone)
            raise NoDataError("Price data is not available right now.", "no_prices")
        return series

    def _forget_before(self, day_start: datetime) -> None:
        with self._lock:
            for key in [k for k in self._days if k[1] < day_start]:
                del self._days[key]
            for key in [k for k in self._attempted if k[1] < day_start]:
                del self._attempted[key]

    def _record(self, series: PriceSeries) -> None:
        if self._history is None:
            return
        try:
            self._history.save(series)
        except sqlite3.Error as exc:  # history is a bonus: never fail a request over it
            log(logger, "history_write_failed", zone=series.zone, kind=type(exc).__name__)

    def warm(self) -> None:
        """Fill the cache for every zone, so a user's request finds the prices already there."""
        for zone in ZONES:
            try:
                self(zone)
            except NoDataError:
                pass  # already logged; the next round tries again

    def serving_stale(self) -> list[str]:
        """Zones answering with today's prices although tomorrow's are overdue."""
        with self._lock:
            return sorted(self._tomorrow_missing)

    def prices_through(self) -> str | None:
        """The last delivery date (Brussels time) held for every zone that has any; None if empty."""
        with self._lock:
            newest: dict[str, datetime] = {}
            for zone, start in self._days:
                newest[zone] = max(start, newest.get(zone, start))
        if not newest:
            return None
        return min(newest.values()).astimezone(MARKET_TZ).strftime("%Y-%m-%d")


def entsoe_series_source(
    settings: Settings,
    client: EntsoeClient | None = None,
    history: PriceHistory | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> EntsoeSeriesSource:
    return EntsoeSeriesSource(settings, client, history, clock)


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
