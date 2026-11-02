import threading
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from watt_brief.config import Settings
from watt_brief.entsoe import EntsoeClient
from watt_brief.pipeline import NoDataError
from watt_brief.sources import (
    CACHE_SECONDS,
    STALE_SECONDS,
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


def test_entsoe_source_caches_per_zone():
    calls = []

    def handler(req):
        calls.append(req.url.params["in_Domain"])
        return httpx.Response(200, text=XML)

    source = entsoe_source(handler)
    source("DE_LU")
    source("DE_LU")
    assert len(calls) == 1


def test_entsoe_source_falls_back_to_today_when_tomorrow_is_not_published():
    responses = [NO_DATA, XML]
    calls = []

    def handler(req):
        calls.append(req.url.params["periodStart"])
        return httpx.Response(200, text=responses[len(calls) - 1])

    series = entsoe_source(handler)("DE_LU")
    assert len(calls) == 2 and calls[0] > calls[1]
    assert len(series.points) == 24


def test_entsoe_source_reports_no_data_when_nothing_is_published():
    source = entsoe_source(lambda req: httpx.Response(200, text=NO_DATA))
    with pytest.raises(NoDataError):
        source("DE_LU")


def test_entsoe_series_records_when_it_was_fetched_and_keeps_it_while_cached():
    source = entsoe_source(lambda req: httpx.Response(200, text=XML))
    before = datetime.now(UTC)
    first = source("DE_LU")
    second = source("DE_LU")
    assert first.fetched_at is not None and before <= first.fetched_at <= datetime.now(UTC)
    assert second.fetched_at == first.fetched_at


def test_fixture_series_has_no_fetch_time():
    assert fixture_series_source()("DE_LU").fetched_at is None


def test_chart_payload_shows_the_fetch_time_for_real_data_only():
    from watt_brief.chart import chart_payload

    real = entsoe_source(lambda req: httpx.Response(200, text=XML))("DE_LU")
    payload = chart_payload(real, 3, "entsoe")
    assert payload["fetched_at"] == real.fetched_at.strftime("%Y-%m-%dT%H:%MZ")
    assert chart_payload(fixture_series_source()("DE_LU"), 3, "synthetic")["fetched_at"] is None


def test_concurrent_requests_on_a_cold_cache_make_one_fetch():
    calls = []
    gate = threading.Event()

    def handler(req):
        calls.append(1)
        gate.wait(2)
        return httpx.Response(200, text=XML)

    source = entsoe_source(handler)
    threads = [threading.Thread(target=source, args=("DE_LU",)) for _ in range(5)]
    for t in threads:
        t.start()
    gate.set()
    for t in threads:
        t.join()
    assert len(calls) == 1


def test_an_expired_entry_is_served_when_the_refresh_fails(monkeypatch):
    from watt_brief import sources

    ok = [True]

    def handler(req):
        return httpx.Response(200, text=XML if ok[0] else NO_DATA)

    clock = [1000.0]
    monkeypatch.setattr(sources.time, "monotonic", lambda: clock[0])
    source = entsoe_source(handler)
    first = source("DE_LU")
    ok[0] = False
    clock[0] += CACHE_SECONDS + 1
    assert source("DE_LU") is first
    clock[0] += STALE_SECONDS
    with pytest.raises(NoDataError):
        source("DE_LU")


def test_unknown_zone_has_no_data_without_touching_the_network():
    def handler(req):
        raise AssertionError("no request expected")

    with pytest.raises(NoDataError):
        entsoe_source(handler)("XX")
