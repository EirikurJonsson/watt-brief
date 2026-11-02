"""Check the live ENTSO-E API still looks the way the parser expects. Exit 1 on any surprise.

Run by .github/workflows/contract-check.yml every day, and by hand:
    ENTSOE_API_TOKEN=... uv run python scripts/contract_check.py
Two bugs (merged TimeSeries, wrong sequence) only showed up against the live API, so this is the
test that fixtures cannot be.
"""

import sys
from datetime import UTC, datetime

from watt_brief.config import get_settings
from watt_brief.entsoe import ZONES, EntsoeClient, EntsoeError
from watt_brief.sources import _delivery_days

PLAUSIBLE_EUR_PER_MWH = (-600.0, 5000.0)
SLOTS_PER_DAY = {92, 96, 100, 23 * 4, 25 * 4, 23, 24, 25}  # 15-minute or hourly, with DST days


def main() -> int:
    settings = get_settings()
    client = EntsoeClient(settings)
    today_start, today_end = _delivery_days(datetime.now(UTC))[1]
    problems = []
    for zone in ZONES:
        try:
            series = client.day_ahead_prices(zone, today_start, today_end)
        except EntsoeError as exc:
            problems.append(f"{zone}: {exc}")
            continue
        starts = [p.start for p in series.points]
        prices = [p.eur_per_mwh for p in series.points]
        if len(starts) != len(set(starts)):
            problems.append(f"{zone}: duplicate timestamps ({len(starts)} points)")
        if len(starts) not in SLOTS_PER_DAY:
            problems.append(f"{zone}: {len(starts)} points for one day")
        if not PLAUSIBLE_EUR_PER_MWH[0] <= min(prices) <= max(prices) <= PLAUSIBLE_EUR_PER_MWH[1]:
            problems.append(f"{zone}: prices outside {PLAUSIBLE_EUR_PER_MWH}")
        print(f"{zone}: {len(starts)} points at {series.resolution_minutes} min, OK so far")
    for line in problems:
        print(f"PROBLEM {line}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
