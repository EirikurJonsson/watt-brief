import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from watt_brief.backup import run
from watt_brief.config import Settings
from watt_brief.history import PriceHistory

T0 = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)


def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        llm_base_url="https://x/v1",
        llm_api_key="sk-x",
        model_planner="m",
        model_analyst="m",
        model_critic="m",
        history_db_path=str(tmp_path / "history.sqlite"),
        spend_db_path=str(tmp_path / "spend.sqlite"),
    )


def seed(tmp_path):
    from watt_brief.entsoe import PricePoint, PriceSeries

    history = PriceHistory(str(tmp_path / "history.sqlite"))  # stays open: the service is running
    history.save(PriceSeries("DK1", 60, [PricePoint(T0, 42.0)], T0))
    sqlite3.connect(tmp_path / "spend.sqlite").execute("CREATE TABLE spend (x)").connection.close()
    return history


def test_both_databases_are_copied_and_the_copy_holds_the_data(tmp_path):
    history = seed(tmp_path)
    made = run(settings(tmp_path), now=T0)
    history.close()
    assert sorted(p.name for p in made) == [
        "history-20261105T090000Z.sqlite",
        "spend-20261105T090000Z.sqlite",
    ]
    copy = sqlite3.connect(made[0])
    assert copy.execute("SELECT eur_per_mwh FROM prices").fetchone() == (42.0,)


def test_only_the_newest_copies_are_kept(tmp_path):
    history = seed(tmp_path)
    for day in range(5):
        run(settings(tmp_path), keep=3, now=T0 + timedelta(days=day))
    history.close()
    names = sorted(p.name for p in (tmp_path / "backups").glob("history-*"))
    assert names == [f"history-202611{d:02d}T090000Z.sqlite" for d in (7, 8, 9)]


def test_a_missing_database_is_skipped_not_an_error(tmp_path):
    assert run(settings(tmp_path), now=T0) == []


def test_a_corrupt_database_is_reported(tmp_path):
    (tmp_path / "history.sqlite").write_bytes(b"this is not sqlite" * 100)
    with pytest.raises(sqlite3.DatabaseError):
        run(settings(tmp_path), now=T0)
