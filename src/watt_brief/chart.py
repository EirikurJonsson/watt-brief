"""What the UI needs to draw the price chart. Pure data, no model involved."""

from watt_brief.analysis import analyse
from watt_brief.entsoe import PriceSeries

ZONE_NAMES = {
    "DE_LU": "Germany and Luxembourg",
    "FR": "France",
    "NL": "the Netherlands",
    "BE": "Belgium",
    "AT": "Austria",
    "ES": "Spain",
}


def _iso(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%MZ")


def chart_payload(series: PriceSeries, window_hours: int, data_source: str) -> dict:
    """Series plus the two highlighted windows, computed by the same code the brief uses."""
    facts = analyse(series, window_hours=window_hours)
    return {
        "zone": series.zone,
        "zone_name": ZONE_NAMES.get(series.zone, series.zone),
        "data_source": data_source,
        # When the prices were fetched from the market operator; null for the synthetic day.
        "fetched_at": _iso(series.fetched_at) if series.fetched_at else None,
        "resolution_minutes": series.resolution_minutes,
        "window_hours": window_hours,
        "mean": facts.mean_eur_per_mwh,
        "cheapest_window": {
            "start": facts.cheapest_window.start_utc,
            "end": facts.cheapest_window.end_utc,
            "avg": facts.cheapest_window.avg_eur_per_mwh,
        },
        "priciest_window": {
            "start": facts.priciest_window.start_utc,
            "end": facts.priciest_window.end_utc,
            "avg": facts.priciest_window.avg_eur_per_mwh,
        },
        # compact [time, price] pairs: the chart redraws from these
        "points": [[_iso(p.start), p.eur_per_mwh] for p in series.points],
    }
