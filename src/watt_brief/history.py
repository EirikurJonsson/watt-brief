"""Day-ahead prices kept for later: a small SQLite table next to the spend database.

Published day-ahead prices do not change, so a row is written once per zone and slot and only
refreshed if the market operator republishes. The table backs the stale-data fallback after a
restart and the "compared with yesterday" figures. Only numbers are stored, never raw response text.
"""

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from watt_brief.entsoe import PricePoint, PriceSeries

_TIME = "%Y-%m-%dT%H:%MZ"

# Schema changes are appended here, never edited: the database remembers how many have run
# (PRAGMA user_version), so an older file is brought forward on start-up and a new file is built
# by running them all. Each entry is one SQL script.
MIGRATIONS = [
    """
    CREATE TABLE IF NOT EXISTS prices (
        zone TEXT NOT NULL,
        slot_start TEXT NOT NULL,          -- UTC, ISO 8601, sorts as text
        eur_per_mwh REAL NOT NULL,
        resolution_minutes INTEGER NOT NULL,
        fetched_at TEXT NOT NULL,          -- UTC
        PRIMARY KEY (zone, slot_start)
    )
    """,
]


def migrate(db: sqlite3.Connection) -> int:
    """Run the migrations this database has not seen. Returns the schema version now in place."""
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > len(MIGRATIONS):
        raise RuntimeError(
            f"history database is schema {version}, newer than this build ({len(MIGRATIONS)})"
        )
    for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
        with db:
            db.execute(script)
            db.execute(f"PRAGMA user_version = {number}")
    return len(MIGRATIONS)


def _fmt(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime(_TIME)


def _parse(text: str) -> datetime:
    return datetime.strptime(text, _TIME).replace(tzinfo=UTC)


class PriceHistory:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        migrate(self._db)
        self._lock = threading.Lock()

    def save(self, series: PriceSeries, fetched_at: datetime | None = None) -> None:
        stamp = _fmt(fetched_at or series.fetched_at or datetime.now(UTC))
        rows = [
            (series.zone, _fmt(p.start), p.eur_per_mwh, series.resolution_minutes, stamp)
            for p in series.points
        ]
        with self._lock, self._db:
            self._db.executemany(
                """INSERT INTO prices VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(zone, slot_start) DO UPDATE SET
                     eur_per_mwh = excluded.eur_per_mwh,
                     resolution_minutes = excluded.resolution_minutes,
                     fetched_at = excluded.fetched_at""",
                rows,
            )

    def load(self, zone: str, start: datetime, end: datetime) -> PriceSeries | None:
        """Slots starting in [start, end). None when there are none."""
        with self._lock:
            rows = self._db.execute(
                """SELECT slot_start, eur_per_mwh, resolution_minutes, fetched_at FROM prices
                   WHERE zone = ? AND slot_start >= ? AND slot_start < ? ORDER BY slot_start""",
                (zone, _fmt(start), _fmt(end)),
            ).fetchall()
        if not rows:
            return None
        return PriceSeries(
            zone=zone,
            resolution_minutes=rows[0][2],
            points=[PricePoint(_parse(r[0]), r[1]) for r in rows],
            fetched_at=_parse(max(r[3] for r in rows)),
        )

    def count(self, zone: str | None = None) -> int:
        query, args = "SELECT COUNT(*) FROM prices", ()
        if zone:
            query, args = query + " WHERE zone = ?", (zone,)
        with self._lock:
            return self._db.execute(query, args).fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._db.close()
