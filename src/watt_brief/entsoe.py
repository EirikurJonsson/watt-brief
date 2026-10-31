"""ENTSO-E Transparency Platform day-ahead prices.

Fetched XML is untrusted: it is parsed with defusedxml and reduced to numbers. Raw text from
the source never reaches a prompt (see docs/threat-model.md).
"""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from watt_brief.config import Settings
from watt_brief.logging import log

logger = logging.getLogger(__name__)

API_URL = "https://web-api.tp.entsoe.eu/api"
DAY_AHEAD_PRICES = "A44"

# Bidding zone EIC codes. Only zones listed here can be requested, so a user question can
# never put free text into the URL. Verify each against the live API once the token arrives.
ZONES = {
    "DE_LU": "10Y1001A1001A82H",
    "FR": "10YFR-RTE------C",
    "NL": "10YNL----------L",
    "BE": "10YBE----------2",
    "AT": "10YAT-APG------L",
    "ES": "10YES-REE------0",
}

_RESOLUTION = re.compile(r"^PT(\d+)M$")


class EntsoeError(Exception):
    """Fetching or parsing failed. The message never contains the token."""


@dataclass(frozen=True)
class PricePoint:
    start: datetime  # UTC
    eur_per_mwh: float


@dataclass(frozen=True)
class PriceSeries:
    zone: str
    resolution_minutes: int
    points: list[PricePoint]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(node, name: str):
    return next((c for c in node.iter() if _local(c.tag) == name), None)


def _parse_time(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)


def parse_day_ahead_xml(xml: str, zone: str) -> PriceSeries:
    try:
        root = ElementTree.fromstring(xml)
    except (ElementTree.ParseError, DefusedXmlException) as exc:
        raise EntsoeError(f"unreadable response: {type(exc).__name__}") from None

    if _local(root.tag) == "Acknowledgement_MarketDocument":
        reason = _find(root, "text")
        raise EntsoeError(f"no data: {reason.text if reason is not None else 'unknown reason'}")

    points: list[PricePoint] = []
    resolution: int | None = None
    for period in (n for n in root.iter() if _local(n.tag) == "Period"):
        match = _RESOLUTION.match(_find(period, "resolution").text.strip())
        if not match:
            raise EntsoeError("unsupported resolution")
        step = int(match.group(1))
        if resolution not in (None, step):
            raise EntsoeError("mixed resolutions in one response")
        resolution = step

        start = _parse_time(_find(_find(period, "timeInterval"), "start").text.strip())
        end = _parse_time(_find(_find(period, "timeInterval"), "end").text.strip())
        slots = int((end - start) / timedelta(minutes=step))

        by_position = {}
        for point in (n for n in period if _local(n.tag) == "Point"):
            position = int(_find(point, "position").text)
            by_position[position] = float(_find(point, "price.amount").text)

        # A03 curves omit positions where the price did not change: carry the last one forward.
        last = None
        for position in range(1, slots + 1):
            last = by_position.get(position, last)
            if last is None:
                raise EntsoeError("series starts with a missing price")
            points.append(PricePoint(start + timedelta(minutes=step * (position - 1)), last))

    if not points or resolution is None:
        raise EntsoeError("no price points in response")
    points.sort(key=lambda p: p.start)
    return PriceSeries(zone=zone, resolution_minutes=resolution, points=points)


class EntsoeClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        if settings.entsoe_api_token is None:
            raise EntsoeError("ENTSOE_API_TOKEN is not set")
        self._token = settings.entsoe_api_token.get_secret_value()
        self._http = httpx.Client(timeout=30.0, transport=transport)

    def day_ahead_prices(self, zone: str, start: datetime, end: datetime) -> PriceSeries:
        if zone not in ZONES:
            raise EntsoeError(f"unsupported zone: {zone}")
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise EntsoeError("start and end must be timezone-aware with end after start")
        fmt = "%Y%m%d%H%M"
        params = {
            "securityToken": self._token,
            "documentType": DAY_AHEAD_PRICES,
            "in_Domain": ZONES[zone],
            "out_Domain": ZONES[zone],
            "periodStart": start.astimezone(UTC).strftime(fmt),
            "periodEnd": end.astimezone(UTC).strftime(fmt),
        }
        try:
            response = self._http.get(API_URL, params=params)
        except httpx.HTTPError as exc:
            log(logger, "entsoe_error", zone=zone, kind=type(exc).__name__)
            raise EntsoeError(f"request failed: {type(exc).__name__}") from None

        if response.status_code == 401:
            raise EntsoeError("ENTSO-E rejected the token (HTTP 401)")
        if response.status_code >= 400 and "<" not in response.text:
            raise EntsoeError(f"ENTSO-E returned HTTP {response.status_code}")

        series = parse_day_ahead_xml(response.text, zone)
        log(
            logger,
            "entsoe_fetch",
            zone=zone,
            points=len(series.points),
            resolution_minutes=series.resolution_minutes,
        )
        return series

    def close(self) -> None:
        self._http.close()
