"""Abuse controls: rate limits, temporary bans, daily spend cap, kill switch.

All in-process or in one SQLite file, which is right for a single-instance service.
"""

import sqlite3
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

Clock = Callable[[], float]

MAX_TRACKED_KEYS = 10_000


class RateLimiter:
    """Sliding window per key: `per_minute` and `per_day` requests."""

    def __init__(self, per_minute: int, per_day: int, clock: Clock = time.time):
        self._per_minute = per_minute
        self._per_day = per_day
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Record a hit. Returns (allowed, retry_after_seconds)."""
        now = self._clock()
        with self._lock:
            if len(self._hits) > MAX_TRACKED_KEYS:
                self._prune(now)
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > 86_400:
                hits.popleft()
            if len(hits) >= self._per_day:
                return False, int(86_400 - (now - hits[0])) + 1
            recent = [t for t in hits if now - t <= 60]
            if len(recent) >= self._per_minute:
                return False, int(60 - (now - recent[0])) + 1
            hits.append(now)
            return True, 0

    def _prune(self, now: float) -> None:
        stale = [k for k, h in self._hits.items() if not h or now - h[-1] > 86_400]
        for key in stale:
            del self._hits[key]


class AbuseTracker:
    """Bans a key for a while after repeated guard rejections."""

    def __init__(
        self,
        rejections: int = 10,
        window_seconds: int = 600,
        ban_seconds: int = 3600,
        clock: Clock = time.time,
    ):
        self._rejections = rejections
        self._window = window_seconds
        self._ban = ban_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = {}
        self._banned_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def record_rejection(self, key: str) -> bool:
        """Returns True if this rejection triggered a ban."""
        now = self._clock()
        with self._lock:
            if len(self._events) > MAX_TRACKED_KEYS:
                self._events.clear()
            events = self._events.setdefault(key, deque())
            events.append(now)
            while events and now - events[0] > self._window:
                events.popleft()
            if len(events) >= self._rejections:
                self._banned_until[key] = now + self._ban
                events.clear()
                return True
            return False

    def is_banned(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            until = self._banned_until.get(key)
            if until is None:
                return False
            if now >= until:
                del self._banned_until[key]
                return False
            return True

    @property
    def banned_count(self) -> int:
        now = self._clock()
        with self._lock:
            return sum(1 for until in self._banned_until.values() if until > now)


class SpendTracker:
    """Daily spend in USD (UTC day), persisted so a restart cannot reset the cap."""

    def __init__(self, db_path: str, clock: Callable[[], datetime] | None = None):
        self._clock = clock or (lambda: datetime.now(UTC))
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS spend "
                "(day TEXT PRIMARY KEY, usd REAL NOT NULL, calls INTEGER NOT NULL)"
            )
            self._db.commit()

    def _day(self) -> str:
        return self._clock().strftime("%Y-%m-%d")

    def add(self, usd: float) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO spend (day, usd, calls) VALUES (?, ?, 1) "
                "ON CONFLICT(day) DO UPDATE SET usd = usd + excluded.usd, calls = calls + 1",
                (self._day(), usd),
            )
            self._db.commit()

    def today(self) -> float:
        with self._lock:
            row = self._db.execute("SELECT usd FROM spend WHERE day = ?", (self._day(),)).fetchone()
        return row[0] if row else 0.0

    def close(self) -> None:
        with self._lock:
            self._db.close()


class KillSwitch:
    """On when the file exists. Create it to stop all model calls, delete it to resume."""

    def __init__(self, path: str):
        self._path = Path(path)

    def active(self) -> bool:
        return self._path.exists()
