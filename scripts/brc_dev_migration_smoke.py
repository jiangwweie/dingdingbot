#!/usr/bin/env python3
"""Non-destructive BRC Operation Layer migration smoke helper.

The default path copies the local SQLite development database to a temporary
file, stamps the copy to the known pre-operation baseline when needed, upgrades
the copy to head, and verifies the Operation Layer ledger tables. It never
modifies the source database unless --work-db intentionally points at it.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
OPERATION_TABLES = {
    "brc_operations",
    "brc_preflight_snapshots",
    "brc_execution_results",
}


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve()}"


def _table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type='table'"
            )
        }


def _alembic_versions(db_path: Path) -> list[str]:
    if "alembic_version" not in _table_names(db_path):
        return []
    with sqlite3.connect(db_path) as conn:
        return [row[0] for row in conn.execute("select version_num from alembic_version")]


def _config(db_path: Path) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", _sqlite_url(db_path))
    return cfg


def run_smoke(
    *,
    source_db: Path | None,
    work_db: Path | None,
    baseline_revision: str,
    target_revision: str,
    fresh: bool,
) -> dict[str, object]:
    if fresh and source_db is not None:
        raise ValueError("--fresh cannot be combined with --source-db")
    if not fresh and source_db is None:
        raise ValueError("--source-db is required unless --fresh is used")

    if work_db is None:
        suffix = "fresh.db" if fresh else "copy.db"
        work_db = Path(tempfile.gettempdir()) / f"brc_operation_migration_smoke_{suffix}"
    work_db = work_db.resolve()
    if work_db.exists():
        work_db.unlink()
    work_db.parent.mkdir(parents=True, exist_ok=True)

    if fresh:
        work_db.touch()
    else:
        assert source_db is not None
        source_db = source_db.resolve()
        if not source_db.exists():
            raise FileNotFoundError(source_db)
        if source_db == work_db:
            raise ValueError("refusing to use the source DB as the work DB")
        shutil.copy2(source_db, work_db)

    before_tables = sorted(_table_names(work_db))
    before_versions = _alembic_versions(work_db)
    cfg = _config(work_db)
    stamped = False
    if fresh:
        command.upgrade(cfg, target_revision)
    elif before_versions:
        command.upgrade(cfg, target_revision)
    else:
        command.stamp(cfg, baseline_revision)
        stamped = True
        command.upgrade(cfg, target_revision)

    after_tables = _table_names(work_db)
    missing = sorted(OPERATION_TABLES - after_tables)
    after_versions = _alembic_versions(work_db)
    if missing:
        raise RuntimeError(f"operation migration missing tables: {missing}")
    return {
        "work_db": str(work_db),
        "source_db": str(source_db) if source_db is not None else None,
        "fresh": fresh,
        "baseline_revision": baseline_revision,
        "target_revision": target_revision,
        "stamped_baseline": stamped,
        "before_alembic_versions": before_versions,
        "after_alembic_versions": after_versions,
        "before_table_count": len(before_tables),
        "operation_tables": sorted(OPERATION_TABLES),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, default=REPO_ROOT / "data" / "v3_dev.db")
    parser.add_argument("--work-db", type=Path, default=None)
    parser.add_argument("--baseline-revision", default="016")
    parser.add_argument("--target-revision", default="head")
    parser.add_argument("--fresh", action="store_true", help="run against a new temporary SQLite DB")
    args = parser.parse_args(argv)

    source_db = None if args.fresh else args.source_db
    result = run_smoke(
        source_db=source_db,
        work_db=args.work_db,
        baseline_revision=args.baseline_revision,
        target_revision=args.target_revision,
        fresh=args.fresh,
    )
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
