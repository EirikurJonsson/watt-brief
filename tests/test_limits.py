from datetime import UTC, datetime

from watt_brief.limits import AbuseTracker, KillSwitch, RateLimiter, SpendTracker


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_rate_limiter_blocks_per_minute_then_recovers():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=3, per_day=100, clock=clock)
    assert all(limiter.check("a")[0] for _ in range(3))
    allowed, retry = limiter.check("a")
    assert not allowed and 0 < retry <= 61
    clock.now += 61
    assert limiter.check("a")[0]


def test_rate_limiter_keys_are_independent():
    limiter = RateLimiter(per_minute=1, per_day=100, clock=FakeClock())
    assert limiter.check("a")[0]
    assert not limiter.check("a")[0]
    assert limiter.check("b")[0]


def test_rate_limiter_daily_cap():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=100, per_day=5, clock=clock)
    for _ in range(5):
        assert limiter.check("a")[0]
        clock.now += 120
    allowed, retry = limiter.check("a")
    assert not allowed and retry > 3600
    clock.now += 86_400
    assert limiter.check("a")[0]


def test_ban_after_repeated_rejections_then_expires():
    clock = FakeClock()
    abuse = AbuseTracker(rejections=3, window_seconds=600, ban_seconds=3600, clock=clock)
    assert not abuse.record_rejection("a")
    assert not abuse.record_rejection("a")
    assert abuse.record_rejection("a")
    assert abuse.is_banned("a") and abuse.banned_count == 1
    assert not abuse.is_banned("b")
    clock.now += 3601
    assert not abuse.is_banned("a") and abuse.banned_count == 0


def test_slow_rejections_do_not_ban():
    clock = FakeClock()
    abuse = AbuseTracker(rejections=3, window_seconds=600, clock=clock)
    for _ in range(10):
        assert not abuse.record_rejection("a")
        clock.now += 400
    assert not abuse.is_banned("a")


def test_spend_accumulates_and_resets_each_utc_day():
    now = {"t": datetime(2026, 10, 31, 23, 59, tzinfo=UTC)}
    spend = SpendTracker(":memory:", clock=lambda: now["t"])
    spend.add(0.25)
    spend.add(0.5)
    assert spend.today() == 0.75
    now["t"] = datetime(2026, 11, 1, 0, 1, tzinfo=UTC)
    assert spend.today() == 0.0


def test_spend_survives_restart(tmp_path):
    db = str(tmp_path / "data" / "spend.sqlite")
    first = SpendTracker(db)
    first.add(0.4)
    first.close()
    assert SpendTracker(db).today() == 0.4


def test_kill_switch_follows_the_file(tmp_path):
    flag = tmp_path / "KILL"
    switch = KillSwitch(str(flag))
    assert not switch.active()
    flag.touch()
    assert switch.active()
    flag.unlink()
    assert not switch.active()
