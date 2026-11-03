import httpx
import pytest

from watt_brief.fx import (
    CACHE_SECONDS,
    FRANKFURTER_URL,
    RETRY_SECONDS,
    FxRate,
    FxSource,
    make_display,
)
from watt_brief.units import Display, convert_price

BODY = {"amount": 1.0, "base": "EUR", "date": "2026-11-02", "rates": {"DKK": 7.5}}


def test_eur_per_mwh_is_the_default_and_unchanged():
    assert convert_price(69.25) == 69.25


def test_mwh_to_kwh_divides_by_1000():
    assert convert_price(85.2, "kWh") == 0.0852


def test_dkk_per_mwh_multiplies_by_the_rate():
    assert convert_price(100.0, "MWh", 7.5) == 750.0


def test_dkk_per_kwh_combines_both():
    assert convert_price(100.0, "kWh", 7.5) == 0.75
    assert Display("kWh", "DKK", 7.5, "2026-11-02").convert(100.0) == 0.75


def test_negative_prices_convert_with_their_sign():
    assert convert_price(-20.0, "kWh", 7.5) == -0.15


def test_display_label():
    assert Display().label == "EUR/MWh"
    assert Display("kWh", "DKK", 7.5, "2026-11-02").label == "DKK/kWh"


class Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


def make_source(handler):
    clock = Clock()
    calls: list[httpx.Request] = []

    def counting(req: httpx.Request):
        calls.append(req)
        return handler(req)

    return FxSource(httpx.MockTransport(counting), clock), clock, calls


def test_fx_fetches_the_documented_url_and_parses_rate_and_date():
    source, _, calls = make_source(lambda req: httpx.Response(200, json=BODY))
    assert source() == FxRate(rate=7.5, date="2026-11-02")
    assert str(calls[0].url) == FRANKFURTER_URL


def test_fx_is_cached_for_about_an_hour_then_refetched():
    source, clock, calls = make_source(lambda req: httpx.Response(200, json=BODY))
    source()
    clock.now = CACHE_SECONDS - 1
    source()
    assert len(calls) == 1
    clock.now = CACHE_SECONDS + 1
    source()
    assert len(calls) == 2


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"rates": {}}),
        httpx.Response(200, json={"date": "2026-11-02", "rates": {"DKK": 0}}),
    ],
)
def test_fx_failure_gives_none_and_does_not_hammer(response):
    source, clock, calls = make_source(lambda req: response)
    assert source() is None
    assert source() is None
    assert len(calls) == 1
    clock.now = RETRY_SECONDS + 1
    source()
    assert len(calls) == 2


def test_fx_network_error_gives_none():
    def boom(req: httpx.Request):
        raise httpx.ConnectError("down")

    source, _, _ = make_source(boom)
    assert source() is None


def test_make_display_falls_back_to_eur_and_says_so():
    shown = make_display("kWh", "DKK", lambda: None)
    assert shown.currency == "EUR" and shown.fallback and shown.unit == "kWh"
    assert shown.convert(100.0) == 0.1


def test_make_display_uses_the_rate_for_dkk_and_never_asks_for_eur():
    def fail() -> FxRate | None:
        raise AssertionError("EUR must not fetch a rate")

    assert make_display("MWh", "EUR", fail) == Display()
    shown = make_display("kWh", "DKK", lambda: FxRate(7.5, "2026-11-02"))
    assert (shown.currency, shown.rate, shown.rate_date, shown.fallback) == (
        "DKK",
        7.5,
        "2026-11-02",
        False,
    )
