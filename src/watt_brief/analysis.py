"""Deterministic price statistics. Every number in a brief comes from here, not from the model."""

from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from watt_brief.entsoe import ZONE_TIMEZONES, PriceSeries


@dataclass(frozen=True)
class Window:
    start_utc: str
    end_utc: str
    avg_eur_per_mwh: float


@dataclass(frozen=True)
class Availability:
    """The hours of the day the user can use power, as local clock hours in the zone's country.

    `to_hour` of 24 means midnight. `from_hour` greater than `to_hour` wraps past midnight
    (22 to 6 is the night).
    """

    from_hour: int
    to_hour: int

    def allows(self, local: datetime) -> bool:
        minute = local.hour * 60 + local.minute
        start, end = self.from_hour * 60, self.to_hour * 60
        return start <= minute < end if start < end else minute >= start or minute < end


@dataclass(frozen=True)
class PriceFacts:
    zone: str
    resolution_minutes: int
    slot_count: int
    coverage_hours: float
    first_slot_utc: str
    last_slot_end_utc: str
    mean_eur_per_mwh: float
    min_eur_per_mwh: float
    min_at_utc: str
    max_eur_per_mwh: float
    max_at_utc: str
    negative_price_slots: int
    window_hours: int
    cheapest_window: Window
    priciest_window: Window
    window_spread_eur_per_mwh: float
    # When prices for today are being read part-way through the day, the windows are only those
    # that start at the current slot or later (nobody can use 03:00 at 14:00). None means every
    # window was considered: tomorrow's prices, or a day with no usable window left.
    windows_from_utc: str | None = None
    # Set when the user limited the hours they can use power. The hours are local clock times and
    # their UTC equivalents; `fits_availability` is False when no window fits inside them and the
    # windows above are therefore for the whole day.
    availability: dict | None = None
    fits_availability: bool | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%MZ")


def _windows(series: PriceSeries, window_hours: int) -> list[Window]:
    slot = timedelta(minutes=series.resolution_minutes)
    per_window = window_hours * 60 // series.resolution_minutes
    prices = [p.eur_per_mwh for p in series.points]
    out = []
    for i in range(len(prices) - per_window + 1):
        start = series.points[i].start
        avg = sum(prices[i : i + per_window]) / per_window
        out.append(Window(_iso(start), _iso(start + slot * per_window), round(avg, 2)))
    return out


def _still_usable(
    series: PriceSeries, windows: list[Window], now: datetime
) -> tuple[list[Window], str | None]:
    """Windows starting at the slot that contains `now` or later, and where that cut-off is."""
    started = [p.start for p in series.points if p.start <= now]
    if not started:
        return windows, None  # the prices are all still to come
    cutoff = _iso(started[-1])
    usable = [w for w in windows if w.start_utc >= cutoff]
    return (usable, cutoff) if usable else (windows, None)


def _availability_facts(series: PriceSeries, tz: ZoneInfo, hours: Availability) -> dict:
    """The user's local hours and the same hours in UTC, on the day the prices are mostly for."""
    day = series.points[len(series.points) // 2].start.astimezone(tz).date()

    def clock(hour: int) -> tuple[str, str]:
        base = datetime.combine(day, time(0), tzinfo=tz) + timedelta(hours=hour)
        return base.strftime("%H:%M"), base.astimezone(ZoneInfo("UTC")).strftime("%H:%M")

    local_from, utc_from = clock(hours.from_hour)
    local_to, utc_to = clock(hours.to_hour)
    return {
        "local_from": local_from,
        "local_to": local_to,
        "utc_from": utc_from,
        "utc_to": utc_to,
    }


def analyse(
    series: PriceSeries,
    window_hours: int = 3,
    now: datetime | None = None,
    availability: Availability | None = None,
) -> PriceFacts:
    if window_hours * 60 % series.resolution_minutes:
        raise ValueError("window must be a whole number of price slots")
    windows = _windows(series, window_hours)
    if not windows:
        raise ValueError("series is shorter than the window")
    fits = None
    availability_facts = None
    if availability is not None:
        tz = ZoneInfo(ZONE_TIMEZONES[series.zone])
        allowed = [availability.allows(p.start.astimezone(tz)) for p in series.points]
        per_window = window_hours * 60 // series.resolution_minutes
        inside = [w for i, w in enumerate(windows) if all(allowed[i : i + per_window])]
        fits = bool(inside)
        windows = inside or windows
        availability_facts = _availability_facts(series, tz, availability)
    windows_from = None
    if now is not None:
        windows, windows_from = _still_usable(series, windows, now)

    prices = [p.eur_per_mwh for p in series.points]
    low = min(series.points, key=lambda p: p.eur_per_mwh)
    high = max(series.points, key=lambda p: p.eur_per_mwh)
    last_end = series.points[-1].start + timedelta(minutes=series.resolution_minutes)

    cheapest = min(windows, key=lambda w: w.avg_eur_per_mwh)
    priciest = max(windows, key=lambda w: w.avg_eur_per_mwh)

    return PriceFacts(
        zone=series.zone,
        resolution_minutes=series.resolution_minutes,
        slot_count=len(series.points),
        coverage_hours=len(series.points) * series.resolution_minutes / 60,
        first_slot_utc=_iso(series.points[0].start),
        last_slot_end_utc=_iso(last_end),
        mean_eur_per_mwh=round(sum(prices) / len(prices), 2),
        min_eur_per_mwh=round(low.eur_per_mwh, 2),
        min_at_utc=_iso(low.start),
        max_eur_per_mwh=round(high.eur_per_mwh, 2),
        max_at_utc=_iso(high.start),
        negative_price_slots=sum(1 for p in prices if p < 0),
        window_hours=window_hours,
        cheapest_window=cheapest,
        priciest_window=priciest,
        window_spread_eur_per_mwh=round(priciest.avg_eur_per_mwh - cheapest.avg_eur_per_mwh, 2),
        windows_from_utc=windows_from,
        availability=availability_facts,
        fits_availability=fits,
    )
