#!/usr/bin/env python3
"""Materialize the PG action-time fact-to-Ticket unit atomically."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.application.action_time.ticket_materialization_sequence import (  # noqa: E402
    materialize_action_time_ticket_sequence,
)
from src.application.action_time.action_time_invocation import (  # noqa: E402
    load_action_time_invocation,
)
from src.application.runtime_process_outcome import (  # noqa: E402
    runtime_process_exit_code,
)
from src.infrastructure.sync_pg_dsn import (  # noqa: E402
    is_sync_postgres_dsn,
    normalize_sync_postgres_dsn,
)
from src.infrastructure.binance_usdm_account_risk_snapshot import (  # noqa: E402
    BinanceUsdmAccountRiskSnapshotProvider,
    FullAccountRiskSnapshot,
)
from src.infrastructure.binance_usdm_streaming_signed_reader import (  # noqa: E402
    BinanceUsdmStreamingSignedReader,
)
from scripts.collect_strategy_group_live_facts_readonly import (  # noqa: E402
    DEFAULT_BASE_URL,
    _env_value,
)


DEFAULT_ENV_FILE = Path("/home/ubuntu/brc-deploy/env/live-readonly.env")


@dataclass(frozen=True)
class _ActiveAccountRiskScope:
    account_id: str
    runtime_profile_id: str
    exchange_id: str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--now-ms", type=int, default=None)
    parser.add_argument("--action-time-invocation-id", default="")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--account-risk-timeout-seconds", type=float, default=12)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--allow-non-postgres-for-test",
        action="store_true",
        help="Allow SQLite/non-PG URLs only for unit tests.",
    )
    args = parser.parse_args(argv)
    database_url = normalize_sync_postgres_dsn(args.database_url)
    if args.require_database_url and not database_url:
        print(
            "ERROR: PG_DATABASE_URL is required for atomic Action-Time Ticket sequence",
            file=sys.stderr,
        )
        return 2
    if not database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    action_time_invocation_id = str(args.action_time_invocation_id or "").strip()
    if not action_time_invocation_id:
        print(
            "ERROR: --action-time-invocation-id is required for Action-Time Ticket sequence",
            file=sys.stderr,
        )
        return 2
    if not args.allow_non_postgres_for_test and not is_sync_postgres_dsn(database_url):
        print(
            "ERROR: atomic Action-Time Ticket sequence requires PostgreSQL DSN",
            file=sys.stderr,
        )
        return 2

    engine = sa.create_engine(database_url)
    try:
        prefetched_account_snapshot: FullAccountRiskSnapshot | None = None
        if is_sync_postgres_dsn(database_url):
            with engine.connect() as conn:
                scope = _active_account_risk_scope(
                    conn,
                    action_time_invocation_id=action_time_invocation_id,
                )
                conn.rollback()
            if scope is not None:
                prefetched_account_snapshot = _fetch_account_risk_snapshot(
                    scope=scope,
                    env_file=Path(args.env_file).expanduser() if args.env_file else None,
                    base_url=args.base_url,
                    timeout_seconds=args.account_risk_timeout_seconds,
                )
        with engine.begin() as conn:
            report = materialize_action_time_ticket_sequence(
                conn,
                action_time_invocation_id=action_time_invocation_id,
                stage_at_ms=args.now_ms,
                prefetched_account_snapshot=prefetched_account_snapshot,
            )
    except sa.exc.SQLAlchemyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, default=str))
    else:
        print(report["status"])
    return runtime_process_exit_code(report["process_outcome"])


def _active_account_risk_scope(
    conn: sa.Connection,
    *,
    action_time_invocation_id: str,
) -> _ActiveAccountRiskScope | None:
    """Read one active policy scope without holding a DB transaction for I/O."""

    invocation = load_action_time_invocation(
        conn,
        action_time_invocation_id=action_time_invocation_id,
    )
    rows = conn.execute(
        sa.text(
            """
            SELECT account_id, runtime_profile_id
            FROM brc_account_risk_policy_current
            WHERE runtime_profile_id = :runtime_profile_id
              AND activation_state = 'active'
            ORDER BY account_id
            LIMIT 2
            """
        ),
        {"runtime_profile_id": invocation.lane_identity.runtime_profile_id},
    ).mappings().all()
    if not rows:
        return None
    if len(rows) != 1:
        raise ValueError("active_account_risk_policy_scope_ambiguous")
    row = rows[0]
    return _ActiveAccountRiskScope(
        account_id=str(row["account_id"]),
        runtime_profile_id=str(row["runtime_profile_id"]),
        exchange_id="binance_usdm",
    )


def _fetch_account_risk_snapshot(
    *,
    scope: _ActiveAccountRiskScope,
    env_file: Path | None,
    base_url: str,
    timeout_seconds: float,
) -> FullAccountRiskSnapshot:
    """Perform bounded signed GET collection before the atomic PG sequence."""

    api_key = _env_value(
        ("EXCHANGE_API_KEY", "BINANCE_API_KEY", "binance_exchange_key"),
        env_file=env_file,
    )
    api_secret = _env_value(
        ("EXCHANGE_API_SECRET", "BINANCE_SECRET_KEY", "binance_exchange_secret"),
        env_file=env_file,
    )

    reader = (
        BinanceUsdmStreamingSignedReader(
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            timeout_seconds=timeout_seconds,
        )
        if api_key and api_secret
        else None
    )

    async def signed_get(path: str):
        if reader is None:
            raise RuntimeError("exchange_api_key_or_secret_missing")
        return await asyncio.to_thread(reader.get, path)

    provider = BinanceUsdmAccountRiskSnapshotProvider(
        account_id=scope.account_id,
        exchange_id=scope.exchange_id,
        signed_get=signed_get,
    )
    return asyncio.run(provider.fetch(timeout_seconds=timeout_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
