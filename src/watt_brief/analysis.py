"""Deterministic price statistics. Every number in a brief comes from here, not from the model."""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from watt_brief.entsoe import PriceSeries


@dataclass(frozen=True)
class Window:
    start_utc: str
    end_utc: str
    avg_eur_per_mwh: float


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


def analyse(series: PriceSeries, window_hours: int = 3) -> PriceFacts:
    if window_hours * 60 % series.resolution_minutes:
        raise ValueError("window must be a whole number of price slots")
    windows = _windows(series, window_hours)
    if not windows:
        raise ValueError("series is shorter than the window")

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
        min_eur_per_mwh=low.eur_per_mwh,
        min_at_utc=_iso(low.start),
        max_eur_per_mwh=high.eur_per_mwh,
        max_at_utc=_iso(high.start),
        negative_price_slots=sum(1 for p in prices if p < 0),
        window_hours=window_hours,
        cheapest_window=cheapest,
        priciest_window=priciest,
        window_spread_eur_per_mwh=round(priciest.avg_eur_per_mwh - cheapest.avg_eur_per_mwh, 2),
    )
