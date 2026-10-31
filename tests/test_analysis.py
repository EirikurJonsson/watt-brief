from pathlib import Path

import pytest

from watt_brief.analysis import analyse
from watt_brief.entsoe import parse_day_ahead_xml

FIXTURES = Path(__file__).parent / "fixtures"


def full_day():
    return parse_day_ahead_xml((FIXTURES / "day_ahead_full_day.xml").read_text(), "DE_LU")


def test_extremes_and_counts():
    facts = analyse(full_day())
    assert facts.min_eur_per_mwh == -4.0
    assert facts.min_at_utc == "2026-10-31T11:00Z"
    assert facts.max_eur_per_mwh == 155.0
    assert facts.max_at_utc == "2026-10-31T16:00Z"
    assert facts.negative_price_slots == 1
    assert facts.first_slot_utc == "2026-10-30T22:00Z"
    assert facts.last_slot_end_utc == "2026-10-31T22:00Z"


def test_cheapest_and_priciest_windows():
    facts = analyse(full_day())
    # prices 8, -4, 5 around the solar dip: avg 3.0
    assert facts.cheapest_window.avg_eur_per_mwh == pytest.approx(3.0)
    assert facts.cheapest_window.start_utc == "2026-10-31T10:00Z"
    assert facts.cheapest_window.end_utc == "2026-10-31T13:00Z"
    # 155, 142, 120 evening peak: avg 139.0
    assert facts.priciest_window.avg_eur_per_mwh == pytest.approx(139.0)
    assert facts.priciest_window.start_utc == "2026-10-31T16:00Z"


def test_mean():
    assert analyse(full_day()).mean_eur_per_mwh == pytest.approx(69.25)


def test_series_shorter_than_window_is_rejected():
    short = parse_day_ahead_xml((FIXTURES / "day_ahead_hourly.xml").read_text(), "DE_LU")
    with pytest.raises(ValueError):
        analyse(short, window_hours=6)


def test_quarter_hour_series():
    q = parse_day_ahead_xml((FIXTURES / "day_ahead_quarter_hour_gaps.xml").read_text(), "DE_LU")
    facts = analyse(q, window_hours=1)
    assert facts.cheapest_window.avg_eur_per_mwh == pytest.approx(95.0)
    assert facts.cheapest_window.end_utc == "2026-10-30T23:00Z"
