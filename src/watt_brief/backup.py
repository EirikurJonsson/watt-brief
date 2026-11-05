"""Consistent copies of the SQLite files: python -m watt_brief.backup [--keep 14] [DIR]

Uses SQLite's own online backup, so the copy is whole even while the service is writing (a plain
file copy of a WAL database can miss recent writes). Each copy is checked before it is kept.
Reads SPEND_DB_PATH and HISTORY_DB_PATH from the environment. DIR defaults to a `backups`
folder next to the history database; point it at a different disk or sync it off the machine,
because a backup on the same disk does not survive that disk.
"""

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from watt_brief.config import Settings, get_settings


def backup_database(source: Path, folder: Path, stamp: str) -> Path:
    destination = folder / f"{source.stem}-{stamp}{source.suffix}"
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
        verdict = dst.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        src.close()
        dst.close()
    if verdict != "ok":
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"backup of {source.name} failed its integrity check: {verdict}")
    return destination


def prune(folder: Path, name: str, keep: int) -> None:
    """Keep the newest `keep` copies of one database (names sort by their timestamp)."""
    copies = sorted(folder.glob(f"{name}-*"))
    for old in copies[: max(len(copies) - keep, 0)]:
        old.unlink()


def run(
    settings: Settings, folder: Path | None = None, keep: int = 14, now: datetime | None = None
):
    sources = [Path(settings.history_db_path), Path(settings.spend_db_path)]
    folder = folder or Path(settings.history_db_path).parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    made = []
    for source in sources:
        if not source.exists():
            continue  # e.g. no history database when running on the synthetic fixture
        made.append(backup_database(source, folder, stamp))
        prune(folder, source.stem, keep)
    return made


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up the SQLite databases")
    parser.add_argument("folder", nargs="?", type=Path)
    parser.add_argument("--keep", type=int, default=14, help="copies of each database to keep")
    args = parser.parse_args()
    made = run(get_settings(), args.folder, args.keep)
    if not made:
        sys.exit("nothing to back up: no database files found")
    for path in made:
        print(path)


if __name__ == "__main__":
    main()
