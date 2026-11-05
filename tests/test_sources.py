import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from watt_brief.config import Settings
from watt_brief.entsoe import EntsoeClient, parse_day_ahead_xml
from watt_brief.pipeline import NoDataError
from watt_brief.sources import (
    TODAY_RETRY_SECONDS,
    TOMORROW_RETRY_SECONDS,
    _delivery_days,
    entsoe_series_source,
    fixture_facts_source,
    fixture_series_source,
)

XML = (Path(__file__).parent / "fixtures/day_ahead_full_day.xml").read_text()
NO_DATA = (Path(__file__).parent / "fixtures/acknowledgement_no_data.xml").read_text()


def settings() -> Settings:
    return Settings(
        _env_file=None,
        llm_base_url="https://x/v1",
        llm_api_key="sk-x",
        model_planner="m",
        model_analyst="m",
        model_critic="m",
        entsoe_api_token="tok",
    )


def test_fixture_series_and_facts_agree():
    series = fixture_series_source()("DE_LU")
    facts = fixture_facts_source()("DE_LU", 3)
    assert len(series.points) == 24 and facts.zone == "DE_LU"


def test_fixture_other_zone_is_no_data():
    with pytest.raises(NoDataError):
        fixture_series_source()("FR")


def test_delivery_days_are_brussels_days_in_utc():
    # 2026-10-31 12:00 UTC is 13:00 in Brussels (CET, after the clocks go back on the 25th)
    tomorrow, today = _delivery_days(datetime(2026, 10, 31, 12, tzinfo=UTC))
    assert tomorrow[0] == datetime(2026, 10, 31, 23, tzinfo=UTC)
    assert today[0] == datetime(2026, 10, 30, 23, tzinfo=UTC)
    assert today[1] == tomorrow[0]


def entsoe_source(handler):
    client = EntsoeClient(settings(), transport=httpx.MockTransport(handler))
    return entsoe_series_source(settings(), client)


def test_fixture_series_has_no_fetch_time():
    assert fixture_series_source()("DE_LU").fetched_at is None


def test_chart_payload_shows_the_fetch_time_for_real_data_only():
    from watt_brief.chart import chart_payload

    real = entsoe_source(lambda req: httpx.Response(200, text=XML))("DE_LU")
    payload = chart_payload(real, 3, "entsoe")
    assert payload["fetched_at"] == real.fetched_at.strftime("%Y-%m-%dT%H:%MZ")
    assert chart_payload(fixture_series_source()("DE_LU"), 3, "synthetic")["fetched_at"] is None


# ---- the fetch-once cache, with a clock we control ----

MORNING = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)  # 10:00 in Brussels: tomorrow not published
AFTERNOON = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)  # 13:00 in Brussels: check for tomorrow
LATE = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)  # 16:00 in Brussels: tomorrow is overdue


class Market:
    """A fake ENTSO-E: serves a full day for each published window, no-data otherwise."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []  # (zone eic, periodStart)
        self.published: set[str] = set()  # periodStart values that have prices
        self.down = False

    def publish(self, start: datetime) -> None:
        self.published.add(start.strftime("%Y%m%d%H%M"))

    def __call__(self, req: httpx.Request) -> httpx.Response:
        params = req.url.params
        self.calls.append((params["in_Domain"], params["periodStart"]))
        if self.down:
            return httpx.Response(503, text="unavailable")
        if params["periodStart"] not in self.published:
            return httpx.Response(200, text=NO_DATA)
        start = datetime.strptime(params["periodStart"], "%Y%m%d%H%M").replace(tzinfo=UTC)
        end = datetime.strptime(params["periodEnd"], "%Y%m%d%H%M").replace(tzinfo=UTC)
        return httpx.Response(200, text=day_xml(start, end))


def day_xml(start: datetime, end: datetime, price: float = 50.0) -> str:
    hours = int((end - start) / timedelta(hours=1))
    points = "".join(
        f"<Point><position>{i}</position><price.amount>{price + i}</price.amount></Point>"
        for i in range(1, hours + 1)
    )
    fmt = "%Y-%m-%dT%H:%MZ"
    return (
        '<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">'
        "<TimeSeries><Period><timeInterval>"
        f"<start>{start.strftime(fmt)}</start><end>{end.strftime(fmt)}</end></timeInterval>"
        f"<resolution>PT60M</resolution>{points}</Period></TimeSeries></Publication_MarketDocument>"
    )


class Clock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def build(market: Market, now: datetime = MORNING, history=None):
    clock = Clock(now)
    client = EntsoeClient(settings(), transport=httpx.MockTransport(market))
    return entsoe_series_source(settings(), client, history, clock), clock


def windows(now: datetime):
    tomorrow, today = _delivery_days(now)
    return tomorrow, today


def test_a_day_is_fetched_once_and_never_again():
    market = Market()
    market.publish(windows(MORNING)[1][0])
    source, clock = build(market)
    first = source("DK1")
    clock.now += timedelta(hours=1, minutes=59)  # still before the first check for tomorrow
    assert source("DK1") is first
    assert len(market.calls) == 1


def test_tomorrow_is_not_requested_before_it_can_exist():
    market = Market()
    market.publish(windows(MORNING)[1][0])
    source, _ = build(market)
    source("DK1")
    assert [start for _, start in market.calls] == [windows(MORNING)[1][0].strftime("%Y%m%d%H%M")]


def test_tomorrow_is_checked_after_the_first_check_and_retried_every_ten_minutes():
    market = Market()
    tomorrow, today = windows(AFTERNOON)
    market.publish(today[0])
    source, clock = build(market, AFTERNOON)

    assert source("DK1").points[0].start == today[0]  # tomorrow not out: today's is served
    assert len(market.calls) == 2  # asked for tomorrow once, then fetched today
    clock.now += timedelta(seconds=TOMORROW_RETRY_SECONDS - 1)
    source("DK1")
    assert len(market.calls) == 2  # no new question inside the ten minutes
    clock.now += timedelta(seconds=2)
    source("DK1")
    assert len(market.calls) == 3  # asked again, still nothing

    market.publish(tomorrow[0])
    clock.now += timedelta(seconds=TOMORROW_RETRY_SECONDS + 1)
    assert source("DK1").points[0].start == tomorrow[0]
    asked = len(market.calls)
    clock.now += timedelta(hours=3)
    source("DK1")
    assert len(market.calls) == asked  # once published it is kept: no more requests


def test_an_outage_is_not_hammered_and_then_recovers():
    market = Market()
    market.down = True
    source, clock = build(market)
    with pytest.raises(NoDataError):
        source("DK1")
    with pytest.raises(NoDataError):
        source("DK1")
    assert len(market.calls) == 1  # the second request did not call again
    market.down = False
    market.publish(windows(MORNING)[1][0])
    clock.now += timedelta(seconds=TODAY_RETRY_SECONDS + 1)
    assert source("DK1").zone == "DK1"


def test_every_day_fetched_is_kept_in_history_and_a_restart_needs_no_request():
    from watt_brief.history import PriceHistory

    history = PriceHistory(":memory:")
    market = Market()
    market.publish(windows(MORNING)[1][0])
    first, _ = build(market, history=history)
    fetched = first("DK1")
    assert history.count("DK1") == 24

    restarted_market = Market()  # ENTSO-E could be down: nothing is published
    restarted, _ = build(restarted_market, history=history)
    served = restarted("DK1")
    assert restarted_market.calls == []
    assert [p.eur_per_mwh for p in served.points] == [p.eur_per_mwh for p in fetched.points]


def test_a_half_stored_day_is_fetched_again_not_trusted():
    from watt_brief.history import PriceHistory

    history = PriceHistory(":memory:")
    today = windows(MORNING)[1]
    partial = parse_day_ahead_xml(day_xml(today[0], today[0] + timedelta(hours=5)), "DK1")
    history.save(partial)
    market = Market()
    market.publish(today[0])
    source, _ = build(market, history=history)
    assert len(source("DK1").points) == 24 and len(market.calls) == 1


def test_missing_tomorrow_late_in_the_day_is_flagged_and_clears_when_published():
    market = Market()
    tomorrow, today = windows(LATE)
    market.publish(today[0])
    source, clock = build(market, LATE)
    source("DK1")
    assert source.serving_stale() == ["DK1"]
    market.publish(tomorrow[0])
    clock.now += timedelta(seconds=TOMORROW_RETRY_SECONDS + 1)
    source("DK1")
    assert source.serving_stale() == []


def test_missing_tomorrow_at_one_pm_is_not_yet_a_problem():
    market = Market()
    market.publish(windows(AFTERNOON)[1][0])
    source, _ = build(market, AFTERNOON)
    source("DK1")
    assert source.serving_stale() == []


def test_prices_through_reports_the_newest_day_held_for_every_zone():
    market = Market()
    tomorrow, today = windows(AFTERNOON)
    market.publish(today[0])
    market.publish(tomorrow[0])
    source, _ = build(market, AFTERNOON)
    assert source.prices_through() is None
    source("DK1")
    assert source.prices_through() == "2026-11-06"


def test_warm_fills_every_zone_so_user_requests_make_no_calls():
    from watt_brief.entsoe import ZONES

    market = Market()
    market.publish(windows(MORNING)[1][0])
    source, _ = build(market)
    source.warm()
    asked = len(market.calls)
    assert asked == len(ZONES)
    for zone in ZONES:
        source(zone)
    assert len(market.calls) == asked


def test_old_days_are_dropped_from_memory():
    market = Market()
    market.publish(windows(MORNING)[1][0])
    source, clock = build(market)
    source("DK1")
    clock.now += timedelta(days=2)
    market.publish(windows(clock.now)[1][0])
    assert source("DK1").points[0].start == windows(clock.now)[1][0]
    assert len(source._days) == 1  # type: ignore[attr-defined]


def test_unknown_zone_has_no_data_without_touching_the_network():
    market = Market()
    source, _ = build(market)
    with pytest.raises(NoDataError):
        source("XX")
    assert market.calls == []


def test_concurrent_requests_on_a_cold_cache_make_one_fetch():
    gate = threading.Event()

    class Slow(Market):
        def __call__(self, req):
            gate.wait(2)
            return super().__call__(req)

    market = Slow()
    market.publish(windows(MORNING)[1][0])
    source, _ = build(market)
    threads = [threading.Thread(target=source, args=("DK1",)) for _ in range(5)]
    for t in threads:
        t.start()
    gate.set()
    for t in threads:
        t.join()
    assert len(market.calls) == 1


def test_a_history_write_failure_never_fails_the_request():
    import sqlite3

    class Broken:
        def save(self, series):
            raise sqlite3.OperationalError("disk full")

        def load(self, *args):
            return None

    market = Market()
    market.publish(windows(MORNING)[1][0])
    source, _ = build(market, history=Broken())
    assert len(source("DK1").points) == 24
