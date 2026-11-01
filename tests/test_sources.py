from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from watt_brief.config import Settings
from watt_brief.entsoe import EntsoeClient
from watt_brief.pipeline import NoDataError
from watt_brief.sources import (
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
