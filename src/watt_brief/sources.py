"""Where price facts come from: synthetic fixture for demos, ENTSO-E for the real thing."""

import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from watt_brief.analysis import PriceFacts, analyse
from watt_brief.config import Settings
from watt_brief.entsoe import EntsoeClient, EntsoeError, PriceSeries, parse_day_ahead_xml
from watt_brief.logging import log
from watt_brief.pipeline import FactsSource, NoDataError

logger = logging.getLogger(__name__)

FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/day_ahead_full_day.xml"
MARKET_TZ = ZoneInfo("Europe/Brussels")
CACHE_SECONDS = 3600


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


def entsoe_series_source(settings: Settings, client: EntsoeClient | None = None) -> SeriesSource:
    """Real prices, cached per zone so user traffic cannot hammer ENTSO-E."""
    entsoe = client or EntsoeClient(settings)
    cache: dict[str, tuple[float, PriceSeries]] = {}
    lock = threading.Lock()

    def get(zone: str) -> PriceSeries:
        with lock:
            hit = cache.get(zone)
            if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
                return hit[1]
        last_error: EntsoeError | None = None
        for start, end in _delivery_days(datetime.now(UTC)):
            try:
                series = entsoe.day_ahead_prices(zone, start, end)
            except EntsoeError as exc:
                last_error = exc
                continue
            with lock:
                cache[zone] = (time.monotonic(), series)
            return series
        log(logger, "entsoe_unavailable", zone=zone)
        raise NoDataError("Price data is not available right now.") from last_error

    return get


def entsoe_facts_source(settings: Settings, client: EntsoeClient | None = None) -> FactsSource:
    return facts_from(entsoe_series_source(settings, client))


def build_series_source(settings: Settings) -> SeriesSource:
    if settings.facts_source == "entsoe":
        return entsoe_series_source(settings)
    return fixture_series_source()


def build_facts_source(settings: Settings) -> FactsSource:
    return facts_from(build_series_source(settings))
