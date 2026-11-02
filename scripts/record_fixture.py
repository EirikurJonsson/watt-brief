"""Record a live ENTSO-E day-ahead response as a test fixture.

Usage: uv run python scripts/record_fixture.py DE_LU 2026-11-02 tests/fixtures/live_de_lu_2026-11-02.xml
The response holds no credentials; the script refuses to write one if it ever does.
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from watt_brief.config import get_settings
from watt_brief.entsoe import API_URL, DAY_AHEAD_PRICES, ZONES
from watt_brief.sources import MARKET_TZ

zone, day, out = sys.argv[1:4]
token = get_settings().entsoe_api_token
assert token is not None, "ENTSOE_API_TOKEN is not set"
start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=MARKET_TZ)
end = start + timedelta(days=1)
fmt = "%Y%m%d%H%M"
response = httpx.get(
    API_URL,
    params={
        "securityToken": token.get_secret_value(),
        "documentType": DAY_AHEAD_PRICES,
        "in_Domain": ZONES[zone],
        "out_Domain": ZONES[zone],
        "periodStart": start.astimezone(UTC).strftime(fmt),
        "periodEnd": end.astimezone(UTC).strftime(fmt),
    },
    timeout=60,
)
assert token.get_secret_value() not in response.text, "response contains the token"
Path(out).write_text(response.text)
print(f"wrote {out} ({len(response.text)} bytes, HTTP {response.status_code})")
