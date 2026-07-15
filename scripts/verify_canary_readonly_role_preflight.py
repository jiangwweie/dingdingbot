#!/usr/bin/env python3
"""Fail-closed PostgreSQL role and direct-DML preflight for deploy canaries."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import normalize_sync_postgres_dsn  # noqa: E402


CANARY_ROLE = "pg_read_all_data"
PROBE_TABLE = "brc_runtime_capabilities_current"
FORBIDDEN_STATEMENTS = (
    "INSERT INTO brc_runtime_capabilities_current "
    "(capability_id,status,certification_ref,updated_at_ms) "
    "VALUES ('deploy-role-probe','disabled','deploy-role-probe',0)",
    "UPDATE brc_runtime_capabilities_current SET updated_at_ms=updated_at_ms WHERE false",
    "DELETE FROM brc_runtime_capabilities_current WHERE false",
    "TRUNCATE brc_runtime_capabilities_current",
)


def verify_role_preflight(database_url: str) -> dict[str, object]:
    dsn = normalize_sync_postgres_dsn(database_url)
    if not dsn.startswith(("postgresql://", "postgresql+psycopg://")):
        raise ValueError("postgresql_database_url_required")
    engine = sa.create_engine(dsn)
    rejected: list[str] = []
    try:
        with engine.connect() as conn:
            with conn.begin():
                conn.execute(sa.text("SET LOCAL statement_timeout = '5s'"))
                conn.execute(sa.text("SET LOCAL ROLE pg_read_all_data"))
                conn.execute(sa.text("SET TRANSACTION READ ONLY"))
                row = conn.execute(
                    sa.text(
                        "SELECT current_user, current_setting('transaction_read_only') AS read_only, "
                        "has_table_privilege(current_user,:table,'SELECT') AS can_select, "
                        "has_table_privilege(current_user,:table,'INSERT') AS can_insert, "
                        "has_table_privilege(current_user,:table,'UPDATE') AS can_update, "
                        "has_table_privilege(current_user,:table,'DELETE') AS can_delete, "
                        "has_table_privilege(current_user,:table,'TRUNCATE') AS can_truncate"
                    ),
                    {"table": PROBE_TABLE},
                ).mappings().one()
                if (
                    row["current_user"] != CANARY_ROLE
                    or row["read_only"] != "on"
                    or row["can_select"] is not True
                    or any(row[name] is not False for name in (
                        "can_insert", "can_update", "can_delete", "can_truncate"
                    ))
                ):
                    raise RuntimeError("canary_role_privilege_shape_invalid")
                for statement in FORBIDDEN_STATEMENTS:
                    savepoint = conn.begin_nested()
                    try:
                        conn.execute(sa.text(statement))
                    except DBAPIError as exc:
                        savepoint.rollback()
                        sqlstate = str(getattr(exc.orig, "sqlstate", "") or "")
                        if sqlstate not in {"25006", "42501"}:
                            raise RuntimeError("canary_dml_rejection_sqlstate_invalid") from exc
                        rejected.append(statement.split(None, 1)[0])
                    else:
                        savepoint.rollback()
                        raise RuntimeError("canary_forbidden_dml_succeeded")
    finally:
        engine.dispose()
    return {
        "status": "canary_readonly_role_preflight_passed",
        "current_user": CANARY_ROLE,
        "membership_mode": "SET_LOCAL_ROLE",
        "transaction_read_only": True,
        "rejected_statements": rejected,
        "exchange_write_called": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("PG_DATABASE_URL", ""),
        required=not bool(os.getenv("PG_DATABASE_URL")),
    )
    args = parser.parse_args(argv)
    try:
        result = verify_role_preflight(args.database_url)
    except (ValueError, RuntimeError, DBAPIError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
