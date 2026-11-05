"""What the UI needs to draw the price chart. Pure data, no model involved."""

from datetime import datetime
from zoneinfo import ZoneInfo

from watt_brief.analysis import Availability, analyse
from watt_brief.entsoe import PriceSeries
from watt_brief.units import EUR_PER_MWH, Display

MARKET_TZ = ZoneInfo("Europe/Brussels")

ZONE_NAMES = {
    "DE_LU": "Germany and Luxembourg",
    "FR": "France",
    "NL": "the Netherlands",
    "BE": "Belgium",
    "AT": "Austria",
    "ES": "Spain",
    "DK1": "Denmark West (DK1: Jutland and Funen)",
    "DK2": "Denmark East (DK2: Zealand and Copenhagen)",
}

# Short labels for the country selector.
ZONE_LABELS = {
    "DE_LU": "Germany/Luxembourg",
    "FR": "France",
    "NL": "Netherlands",
    "BE": "Belgium",
    "AT": "Austria",
    "ES": "Spain",
    "DK1": "Denmark West (DK1)",
    "DK2": "Denmark East (DK2)",
}


def _iso(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%MZ")


def compare_with_previous(
    series: PriceSeries, previous: PriceSeries | None, display: Display = EUR_PER_MWH
) -> dict | None:
    """Mean price against the previous day's. None unless that day is nearly complete and has the
    same slot length, so a half-recorded day never produces a misleading percentage."""
    if previous is None or previous.resolution_minutes != series.resolution_minutes:
        return None
    if len(previous.points) < 0.9 * len(series.points):
        return None
    mean = sum(p.eur_per_mwh for p in series.points) / len(series.points)
    before = sum(p.eur_per_mwh for p in previous.points) / len(previous.points)
    change = None if abs(before) < 1.0 else round((mean - before) / abs(before) * 100)
    return {
        "date": previous.points[0].start.astimezone(MARKET_TZ).strftime("%Y-%m-%d"),
        "mean": display.convert(before),
        "change_pct": change,
    }


def chart_payload(
    series: PriceSeries,
    window_hours: int,
    data_source: str,
    previous: PriceSeries | None = None,
    display: Display = EUR_PER_MWH,
    now: datetime | None = None,
    availability: Availability | None = None,
) -> dict:
    """Series plus the two highlighted windows, computed by the same code the brief uses."""
    facts = analyse(series, window_hours=window_hours, now=now, availability=availability)
    return {
        "zone": series.zone,
        "zone_name": ZONE_NAMES.get(series.zone, series.zone),
        "data_source": data_source,
        # When the prices were fetched from the market operator; null for the synthetic day.
        "fetched_at": _iso(series.fetched_at) if series.fetched_at else None,
        "resolution_minutes": series.resolution_minutes,
        "window_hours": window_hours,
        # What the prices below are in. Converted from EUR/MWh by Display, nowhere else.
        "unit": display.unit,
        "currency": display.currency,
        "price_label": display.label,
        # The fixed ERM II central rate, shown so the conversion is never a hidden number.
        "fx": (
            {"rate": display.rate, "basis": "fixed ERM II central rate"}
            if display.currency != "EUR"
            else None
        ),
        "mean": display.convert(facts.mean_eur_per_mwh),
        "previous_day": compare_with_previous(series, previous, display),
        "cheapest_window": {
            "start": facts.cheapest_window.start_utc,
            "end": facts.cheapest_window.end_utc,
            "avg": display.convert(facts.cheapest_window.avg_eur_per_mwh),
        },
        "priciest_window": {
            "start": facts.priciest_window.start_utc,
            "end": facts.priciest_window.end_utc,
            "avg": display.convert(facts.priciest_window.avg_eur_per_mwh),
        },
        # compact [time, price] pairs: the chart redraws from these
        "points": [[_iso(p.start), display.convert(p.eur_per_mwh)] for p in series.points],
    }
