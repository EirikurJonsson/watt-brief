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


def test_window_spread_is_priciest_minus_cheapest():
    assert analyse(full_day()).window_spread_eur_per_mwh == pytest.approx(136.0)


def at(hour: int, minute: int = 0):
    from datetime import UTC, datetime

    return datetime(2026, 10, 31, hour, minute, tzinfo=UTC)


def test_windows_that_have_already_started_are_not_recommended_part_way_through_the_day():
    facts = analyse(full_day(), now=at(14, 30))
    assert facts.windows_from_utc == "2026-10-31T14:00Z"
    assert facts.cheapest_window.start_utc >= "2026-10-31T14:00Z"
    assert facts.priciest_window.start_utc >= "2026-10-31T14:00Z"
    assert (
        analyse(full_day()).cheapest_window.start_utc == "2026-10-31T10:00Z"
    )  # whole day unchanged


def test_a_window_starting_in_the_current_slot_is_still_usable():
    facts = analyse(full_day(), now=at(10, 20))
    assert facts.windows_from_utc == "2026-10-31T10:00Z"
    assert facts.cheapest_window.start_utc == "2026-10-31T10:00Z"


def test_whole_day_statistics_do_not_change_with_the_time():
    whole, later = analyse(full_day()), analyse(full_day(), now=at(14, 30))
    assert (whole.mean_eur_per_mwh, whole.min_at_utc, whole.max_at_utc) == (
        later.mean_eur_per_mwh,
        later.min_at_utc,
        later.max_at_utc,
    )


def test_prices_still_to_come_are_analysed_whole():
    from datetime import UTC, datetime

    facts = analyse(full_day(), now=datetime(2026, 10, 30, 12, tzinfo=UTC))
    assert facts.windows_from_utc is None
    assert facts.cheapest_window.start_utc == "2026-10-31T10:00Z"


def test_a_day_with_no_window_left_falls_back_to_the_whole_day():
    facts = analyse(full_day(), now=at(21, 30))  # fewer than three hours remain
    assert facts.windows_from_utc is None
    assert facts.cheapest_window.start_utc == "2026-10-31T10:00Z"
