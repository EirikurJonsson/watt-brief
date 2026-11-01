from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from watt_brief.config import Settings
from watt_brief.entsoe import EntsoeClient, EntsoeError, parse_day_ahead_xml

FIXTURES = Path(__file__).parent / "fixtures"
TOKEN = "tok-secret-123456"
START = datetime(2026, 10, 30, 22, tzinfo=UTC)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def settings(token: str | None = TOKEN) -> Settings:
    return Settings(
        _env_file=None,
        llm_base_url="https://x/v1",
        llm_api_key="sk-x",
        model_planner="m",
        model_analyst="m",
        model_critic="m",
        entsoe_api_token=token,
    )


def client(handler) -> EntsoeClient:
    return EntsoeClient(settings(), transport=httpx.MockTransport(handler))


def test_parse_hourly():
    series = parse_day_ahead_xml(fixture("day_ahead_hourly.xml"), "DE_LU")
    assert series.resolution_minutes == 60
    assert [p.eur_per_mwh for p in series.points] == [10.0, 20.0, -5.0, 40.5]
    assert series.points[0].start == START
    assert series.points[3].start == START + timedelta(hours=3)


def test_parse_fills_gaps_in_compressed_curve():
    series = parse_day_ahead_xml(fixture("day_ahead_quarter_hour_gaps.xml"), "DE_LU")
    assert series.resolution_minutes == 15
    assert [p.eur_per_mwh for p in series.points] == [100.0, 100.0, 90.0, 90.0]


def test_acknowledgement_becomes_error():
    with pytest.raises(EntsoeError, match="no data"):
        parse_day_ahead_xml(fixture("acknowledgement_no_data.xml"), "DE_LU")


def test_garbage_is_rejected():
    with pytest.raises(EntsoeError):
        parse_day_ahead_xml("not xml at all", "DE_LU")


def test_entity_expansion_attack_is_rejected():
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        "<Publication_MarketDocument>&b;</Publication_MarketDocument>"
    )
    with pytest.raises(EntsoeError):
        parse_day_ahead_xml(bomb, "DE_LU")


def test_request_has_expected_params():
    seen = {}

    def handler(req: httpx.Request):
        seen.update(req.url.params)
        return httpx.Response(200, text=fixture("day_ahead_hourly.xml"))

    series = client(handler).day_ahead_prices("DE_LU", START, START + timedelta(hours=4))
    assert len(series.points) == 4
    assert seen["documentType"] == "A44"
    assert seen["in_Domain"] == seen["out_Domain"] == "10Y1001A1001A82H"
    assert seen["periodStart"] == "202610302200"
    assert seen["periodEnd"] == "202610310200"


def test_unknown_zone_never_reaches_the_network():
    def handler(req):
        raise AssertionError("network must not be called")

    with pytest.raises(EntsoeError, match="unsupported zone"):
        client(handler).day_ahead_prices("DE_LU&x=1", START, START + timedelta(hours=1))


def test_naive_datetimes_rejected():
    with pytest.raises(EntsoeError):
        client(lambda r: httpx.Response(200)).day_ahead_prices(
            "FR", datetime(2026, 10, 30), datetime(2026, 10, 31)
        )


def test_401_does_not_leak_token():
    c = client(lambda req: httpx.Response(401, text="Unauthorized"))
    with pytest.raises(EntsoeError) as err:
        c.day_ahead_prices("DE_LU", START, START + timedelta(hours=1))
    assert TOKEN not in str(err.value)


def test_missing_token_fails_clearly():
    with pytest.raises(EntsoeError, match="ENTSOE_API_TOKEN"):
        EntsoeClient(settings(token=None))


NS = 'xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"'


def doc(period_body: str) -> str:
    return f"<Publication_MarketDocument {NS}><TimeSeries><Period>{period_body}</Period></TimeSeries></Publication_MarketDocument>"


GOOD_INTERVAL = (
    "<timeInterval><start>2026-10-30T22:00Z</start><end>2026-10-30T23:00Z</end></timeInterval>"
)
GOOD_POINT = "<Point><position>1</position><price.amount>10.0</price.amount></Point>"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        # each piece of the response that we rely on, missing in turn
        (f"{GOOD_INTERVAL}{GOOD_POINT}", "resolution"),
        (f"<resolution>PT60M</resolution>{GOOD_POINT}", "timeInterval|start"),
        (
            "<resolution>PT60M</resolution><timeInterval><start>2026-10-30T22:00Z</start></timeInterval>"
            + GOOD_POINT,
            "end",
        ),
        (
            f"<resolution>PT60M</resolution>{GOOD_INTERVAL}<Point><price.amount>10</price.amount></Point>",
            "position",
        ),
        (
            f"<resolution>PT60M</resolution>{GOOD_INTERVAL}<Point><position>1</position></Point>",
            "price.amount",
        ),
        # present but wrong
        (
            f"<resolution>PT60M</resolution>{GOOD_INTERVAL}<Point><position>x</position><price.amount>1</price.amount></Point>",
            "malformed number",
        ),
        (
            f"<resolution>PT60M</resolution>{GOOD_INTERVAL}<Point><position>1</position><price.amount>cheap</price.amount></Point>",
            "malformed number",
        ),
        (
            "<resolution>PT60M</resolution><timeInterval><start>soon</start><end>later</end></timeInterval>"
            + GOOD_POINT,
            "malformed time",
        ),
        (f"<resolution>PT0M</resolution>{GOOD_INTERVAL}{GOOD_POINT}", "invalid|unsupported"),
        (
            "<resolution>PT60M</resolution><timeInterval><start>2026-10-30T23:00Z</start><end>2026-10-30T22:00Z</end></timeInterval>"
            + GOOD_POINT,
            "invalid time interval",
        ),
        (
            "<resolution>PT60M</resolution><timeInterval><start>2000-01-01T00:00Z</start><end>2026-01-01T00:00Z</end></timeInterval>"
            + GOOD_POINT,
            "too long",
        ),
    ],
)
def test_malformed_responses_raise_a_clean_error_never_a_crash(body, expected):
    with pytest.raises(EntsoeError) as err:
        parse_day_ahead_xml(doc(body), "DE_LU")
    assert any(part in str(err.value) for part in expected.split("|")), str(err.value)


def test_a_valid_minimal_response_still_parses():
    series = parse_day_ahead_xml(
        doc(f"<resolution>PT60M</resolution>{GOOD_INTERVAL}{GOOD_POINT}"), "DE_LU"
    )
    assert [p.eur_per_mwh for p in series.points] == [10.0]


def test_a_document_with_no_period_at_all_is_an_error():
    with pytest.raises(EntsoeError):
        parse_day_ahead_xml(
            f"<Publication_MarketDocument {NS}></Publication_MarketDocument>", "DE_LU"
        )
