"""Fill the price history with past days: python -m watt_brief.backfill --days 30

Reads ENTSOE_API_TOKEN and HISTORY_DB_PATH from the environment. Safe to re-run: rows are upserted.
"""

import argparse
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from watt_brief.config import Settings, get_settings
from watt_brief.entsoe import ZONES, EntsoeClient, EntsoeError
from watt_brief.history import PriceHistory
from watt_brief.logging import configure_logging, log
from watt_brief.sources import MARKET_TZ

logger = logging.getLogger(__name__)


def backfill(
    settings: Settings,
    history: PriceHistory,
    days: int,
    client: EntsoeClient | None = None,
    zones: list[str] | None = None,
    today: datetime | None = None,
    pause: Callable[[float], None] = time.sleep,
) -> tuple[int, int]:
    """Fetch each past Brussels-time delivery day (and today). Returns (days saved, days missing)."""
    entsoe = client or EntsoeClient(settings)
    midnight = (
        (today or datetime.now(UTC))
        .astimezone(MARKET_TZ)
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )
    saved = missing = 0
    for zone in zones or list(ZONES):
        for back in range(days, -1, -1):
            start = midnight - timedelta(days=back)
            end = midnight - timedelta(days=back - 1)
            try:
                series = entsoe.day_ahead_prices(zone, start.astimezone(UTC), end.astimezone(UTC))
            except EntsoeError as exc:
                missing += 1
                log(
                    logger,
                    "backfill_missing",
                    zone=zone,
                    day=start.date().isoformat(),
                    why=str(exc),
                )
            else:
                history.save(series, fetched_at=datetime.now(UTC))
                saved += 1
            pause(0.3)  # stay far below ENTSO-E's request limit
    return saved, missing


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--zone", action="append", choices=sorted(ZONES))
    args = parser.parse_args()
    configure_logging()
    settings = get_settings()
    history = PriceHistory(settings.history_db_path)
    try:
        saved, missing = backfill(settings, history, args.days, zones=args.zone)
    finally:
        history.close()
    print(f"saved {saved} zone-days, {missing} unavailable; {settings.history_db_path}")


if __name__ == "__main__":
    main()
