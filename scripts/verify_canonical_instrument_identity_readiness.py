#!/usr/bin/env python3
"""Certify active canonical instrument identity and V2 rule readiness from PG."""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
import os
import sys
from pathlib import Path

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pg_dsn import normalize_sync_postgres_dsn  # noqa: E402
from src.application.action_time.instrument_risk_facts import (  # noqa: E402
    InstrumentRiskFactsError,
    load_current_instrument_rule_snapshot,
    load_exact_instrument_identity,
)
from src.application.action_time.instrument_rule_projector import (  # noqa: E402
    InstrumentRuleProjectionError,
    load_active_instrument_rule_targets,
)


EXPECTED_ACTIVE_LANE_COUNT = 22
EXPECTED_ACTIVE_INSTRUMENT_COUNT = 6
DEFAULT_RUNTIME_PROFILE_ID = "owner-runtime-console-v1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("PG_DATABASE_URL") or os.getenv("DATABASE_URL") or "",
    )
    parser.add_argument(
        "--runtime-profile-id", default=DEFAULT_RUNTIME_PROFILE_ID,
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or PG_DATABASE_URL is required")

    engine = sa.create_engine(normalize_sync_postgres_dsn(args.database_url))
    try:
        with engine.connect() as conn:
            now_ms = _database_now_ms(conn)
            targets = load_active_instrument_rule_targets(
                conn,
                runtime_profile_id=args.runtime_profile_id,
                expected_instrument_count=EXPECTED_ACTIVE_INSTRUMENT_COUNT,
            )
            lane_count = int(
                conn.execute(
                    sa.text(
                        """
                        SELECT count(*)
                        FROM brc_strategy_group_candidate_scope AS candidate
                        JOIN brc_runtime_scope_bindings AS runtime
                          ON runtime.candidate_scope_id = candidate.candidate_scope_id
                         AND runtime.status = 'active'
                         AND runtime.runtime_profile_id = :runtime_profile_id
                        JOIN brc_candidate_scope_event_bindings AS event_binding
                          ON event_binding.candidate_scope_id = candidate.candidate_scope_id
                         AND event_binding.status = 'active'
                        WHERE candidate.status = 'active'
                          AND candidate.scope_state = 'live_submit_allowed'
                        """
                    ),
                    {"runtime_profile_id": args.runtime_profile_id},
                ).scalar_one()
            )
            if lane_count != EXPECTED_ACTIVE_LANE_COUNT:
                raise RuntimeError("canonical_instrument_readiness_lane_count_invalid")
            for target in targets:
                identity = load_exact_instrument_identity(
                    conn, target.identity.exchange_instrument_id
                )
                if identity != target.identity:
                    raise RuntimeError("canonical_instrument_readiness_identity_changed")
                load_current_instrument_rule_snapshot(
                    conn,
                    exchange_instrument_id=identity.exchange_instrument_id,
                    planned_notional=Decimal("1"),
                    now_ms=now_ms,
                )
    except (InstrumentRiskFactsError, InstrumentRuleProjectionError, sa.exc.SQLAlchemyError) as exc:
        raise RuntimeError(str(exc)) from exc
    finally:
        engine.dispose()

    payload = {
        "schema": "brc.canonical_instrument_identity_readiness.v1",
        "status": "canonical_instrument_identity_readiness_certified",
        "active_lane_count": lane_count,
        "canonical_instrument_count": len(targets),
        "current_v2_rule_count": len(targets),
        "exchange_write_called": False,
        "order_created": False,
        "files_written": 0,
    }
    print(json.dumps(payload, sort_keys=True) if args.json else payload["status"])
    return 0


def _database_now_ms(conn: sa.Connection) -> int:
    if conn.dialect.name == "postgresql":
        return int(
            conn.execute(
                sa.text("SELECT (extract(epoch from clock_timestamp()) * 1000)::bigint")
            ).scalar_one()
        )
    import time

    return int(time.time() * 1000)


if __name__ == "__main__":
    raise SystemExit(main())
