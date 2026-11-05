from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from watt_brief.backfill import backfill
from watt_brief.chart import compare_with_previous
from watt_brief.config import Settings
from watt_brief.entsoe import EntsoeClient, PricePoint, PriceSeries
from watt_brief.history import PriceHistory
from watt_brief.sources import build_history

D0 = datetime(2026, 11, 1, 23, tzinfo=UTC)


def series(prices, start=D0, zone="DE_LU", step=60) -> PriceSeries:
    points = [PricePoint(start + timedelta(minutes=step * i), p) for i, p in enumerate(prices)]
    return PriceSeries(zone, step, points, fetched_at=datetime(2026, 11, 2, 12, tzinfo=UTC))


def settings(**extra) -> Settings:
    return Settings(
        _env_file=None,
        llm_base_url="https://x/v1",
        llm_api_key="sk-x",
        model_planner="m",
        model_analyst="m",
        model_critic="m",
        entsoe_api_token="tok",
        **extra,
    )


def test_round_trip_keeps_prices_resolution_and_fetch_time():
    h = PriceHistory(":memory:")
    h.save(series([10.5, -3.0, 20.0]))
    got = h.load("DE_LU", D0, D0 + timedelta(hours=3))
    assert got is not None
    assert [p.eur_per_mwh for p in got.points] == [10.5, -3.0, 20.0]
    assert got.resolution_minutes == 60
    assert got.fetched_at == datetime(2026, 11, 2, 12, tzinfo=UTC)


def test_saving_twice_updates_in_place():
    h = PriceHistory(":memory:")
    h.save(series([1.0, 2.0]))
    h.save(series([1.0, 9.0]))
    assert h.count() == 2
    loaded = h.load("DE_LU", D0, D0 + timedelta(hours=2))
    assert loaded is not None and [p.eur_per_mwh for p in loaded.points] == [1.0, 9.0]


def test_load_is_per_zone_and_half_open():
    h = PriceHistory(":memory:")
    h.save(series([1.0, 2.0, 3.0]))
    h.save(series([7.0], zone="FR"))
    got = h.load("DE_LU", D0, D0 + timedelta(hours=2))
    assert got is not None and len(got.points) == 2  # the slot at `end` is excluded
    assert h.load("ES", D0, D0 + timedelta(hours=3)) is None
    assert h.count("FR") == 1


def test_history_persists_across_connections(tmp_path):
    path = str(tmp_path / "sub" / "h.sqlite")
    first = PriceHistory(path)
    first.save(series([4.0]))
    first.close()
    again = PriceHistory(path)
    assert again.count() == 1


def test_synthetic_data_is_never_kept():
    assert build_history(settings(facts_source="fixture")) is None
    assert build_history(settings(facts_source="entsoe", history_db_path=":memory:")) is not None


def test_comparison_with_the_previous_day():
    today = series([110.0] * 24)
    before = series([100.0] * 24, start=D0 - timedelta(days=1))
    result = compare_with_previous(today, before)
    assert result == {"date": "2026-11-01", "mean": 100.0, "change_pct": 10}


def test_comparison_refuses_a_half_recorded_or_different_resolution_day():
    today = series([110.0] * 24)
    assert compare_with_previous(today, None) is None
    assert compare_with_previous(today, series([100.0] * 10)) is None
    assert compare_with_previous(today, series([100.0] * 96, step=15)) is None


def test_no_percentage_when_yesterday_averaged_about_zero():
    result = compare_with_previous(series([5.0] * 24), series([0.2] * 24))
    assert result is not None and result["change_pct"] is None


def test_backfill_saves_each_day_and_counts_the_missing_ones():
    fixtures = Path(__file__).parent / "fixtures"
    bodies = [
        (fixtures / "day_ahead_full_day.xml").read_text(),
        (fixtures / "acknowledgement_no_data.xml").read_text(),
    ]
    calls = []

    def handler(req):
        calls.append(req.url.params["periodStart"])
        return httpx.Response(200, text=bodies[0] if len(calls) % 2 else bodies[1])

    h = PriceHistory(":memory:")
    client = EntsoeClient(settings(), transport=httpx.MockTransport(handler))
    saved, missing = backfill(
        settings(),
        h,
        days=3,
        client=client,
        zones=["DE_LU"],
        today=datetime(2026, 11, 2, 12, tzinfo=UTC),
        pause=lambda s: None,
    )
    assert (saved, missing) == (2, 2)
    assert len(calls) == 4 and calls == sorted(calls)  # oldest day first


def test_a_new_database_is_stamped_with_the_current_schema_version():
    from watt_brief.history import MIGRATIONS

    h = PriceHistory(":memory:")
    assert h._db.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)


def test_an_unversioned_database_from_before_migrations_is_adopted_with_its_rows():
    import sqlite3

    from watt_brief.history import MIGRATIONS, migrate

    db = sqlite3.connect(":memory:")
    db.execute(MIGRATIONS[0])  # how the table was created before versioning: user_version = 0
    db.execute(
        "INSERT INTO prices VALUES ('DK1', '2026-11-05T00:00Z', 50.0, 60, '2026-11-05T09:00Z')"
    )
    assert migrate(db) == len(MIGRATIONS)
    assert db.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 1
    assert migrate(db) == len(MIGRATIONS)  # running again changes nothing


def test_a_database_from_a_newer_build_is_refused_not_damaged():
    import sqlite3

    import pytest

    from watt_brief.history import MIGRATIONS, migrate

    db = sqlite3.connect(":memory:")
    db.execute(f"PRAGMA user_version = {len(MIGRATIONS) + 1}")
    with pytest.raises(RuntimeError, match="newer than this build"):
        migrate(db)
