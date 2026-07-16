#!/usr/bin/env python3
"""Run one bounded ticket-bound lifecycle maintenance scheduler pass."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import resource
import sys
import time
from typing import Any, Iterator

import sqlalchemy as sa


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.action_time.lifecycle_maintenance_scheduler import (  # noqa: E402
    run_ticket_bound_lifecycle_maintenance_scheduler,
    select_ticket_bound_lifecycle_maintenance_scopes,
)
from src.application.action_time.exchange_command_worker import (  # noqa: E402
    run_one_ticket_bound_exchange_command,
)
from src.application.action_time.exchange_command_reconciliation import (  # noqa: E402
    run_one_unknown_exchange_command_reconciliation,
)
from src.application.action_time.exchange_scope import (  # noqa: E402
    resolve_ticket_bound_exchange_scope,
)
from src.application.action_time.lifecycle_mutation_capability import (  # noqa: E402
    lifecycle_mutation_capability_decision,
)
from src.application.action_time.exchange_snapshot_provider import (  # noqa: E402
    ATTEMPT_AUTHORITY_BOUNDARY,
    AUTHORITY_BOUNDARY as SNAPSHOT_AUTHORITY_BOUNDARY,
    fetch_resolved_ticket_bound_exchange_snapshot,
    load_ticket_conditional_parent_order_ids,
)
from src.application.action_time.post_submit_reconciliation_tick import (  # noqa: E402
    select_ticket_bound_first_reconciliation_tick_scopes,
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


LIFECYCLE_MUTATION_COMMAND_SOURCES = (
    "protection_recovery",
    "runner_mutation",
    "orphan_cleanup",
    "exit_policy_runner",
    "exit_policy_close",
    "exit_policy_tp1_reprice",
)
DEFAULT_ACCOUNT_RISK_ENV_FILE = Path("/home/ubuntu/brc-deploy/env/live-readonly.env")


class LifecycleStageTelemetry:
    """Bounded in-process performance facts for one lifecycle invocation."""

    def __init__(self) -> None:
        self.started_at = time.monotonic()
        self._stage_started_at: dict[str, float] = {}
        self.stage_durations_ms: dict[str, int] = {}
        self.exchange_request_count = 0
        self.pg_transaction_count = 0

    def start_stage(self, stage: str) -> None:
        if stage in self._stage_started_at:
            raise ValueError(f"lifecycle_stage_already_started:{stage}")
        self._stage_started_at[stage] = time.monotonic()

    def finish_stage(self, stage: str) -> None:
        started_at = self._stage_started_at.pop(stage, None)
        if started_at is None:
            raise ValueError(f"lifecycle_stage_not_started:{stage}")
        elapsed_ms = int(round((time.monotonic() - started_at) * 1000))
        self.stage_durations_ms[stage] = (
            self.stage_durations_ms.get(stage, 0) + max(0, elapsed_ms)
        )

    @contextmanager
    def stage(self, stage: str) -> Iterator[None]:
        self.start_stage(stage)
        try:
            yield
        finally:
            self.finish_stage(stage)

    def snapshot(self, *, deadline_at: float) -> dict[str, Any]:
        now = time.monotonic()
        return {
            "stage_durations_ms": dict(sorted(self.stage_durations_ms.items())),
            "total_duration_ms": max(
                0, int(round((now - self.started_at) * 1000))
            ),
            "exchange_request_count": int(self.exchange_request_count),
            "pg_transaction_count": int(self.pg_transaction_count),
            "peak_rss_kib": _peak_rss_kib(),
            "deadline_remaining_seconds": round(max(0.0, deadline_at - now), 3),
        }


def _peak_rss_kib() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value // 1024 if sys.platform == "darwin" else value


async def _amain(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    database_url = normalize_sync_postgres_dsn(args.database_url or "")
    if args.require_database_url and not database_url:
        print("ERROR: PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if not database_url:
        print("ERROR: --database-url or PG_DATABASE_URL is required", file=sys.stderr)
        return 2
    if not is_sync_postgres_dsn(database_url):
        print("ERROR: lifecycle maintenance scheduler requires PostgreSQL DSN", file=sys.stderr)
        return 2

    telemetry = LifecycleStageTelemetry()
    engine = sa.create_engine(database_url)
    gateway = None
    worker_payload: dict[str, Any] = {}
    deadline_at = telemetry.started_at + float(args.global_deadline_seconds)
    try:
        with telemetry.stage("initial_pg_scope_selection"):
            with engine.begin() as conn:
                telemetry.pg_transaction_count += 1
                initial_first_tick_scopes = [
                    {**scope, "scheduler_scope_kind": "first_post_submit"}
                    for scope in select_ticket_bound_first_reconciliation_tick_scopes(
                        conn,
                        max_scopes=1,
                    )
                ]
                initial_scopes = select_ticket_bound_lifecycle_maintenance_scopes(
                    conn,
                    max_lifecycle_scopes=1,
                )
                command_pending = _prepared_or_unknown_command_exists(conn)
                capability = lifecycle_mutation_capability_decision(conn)
        requires_gateway = bool(
            command_pending or initial_first_tick_scopes or initial_scopes
        )
        gateway_binding: dict[str, Any] = {}
        if requires_gateway:
            with telemetry.stage("gateway_binding"):
                gateway_binding = await _await_before_deadline(
                    _runtime_exchange_gateway_binding(),
                    deadline_at=deadline_at,
                    stage="gateway_binding",
                )
            gateway = gateway_binding.get("gateway")
            if gateway is None:
                payload = {
                    **_blocked_gateway_payload(gateway_binding),
                    "performance": telemetry.snapshot(deadline_at=deadline_at),
                }
                print(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    )
                )
                return 1
            telemetry.exchange_request_count += 2

        worker_payload: dict[str, Any] = {
            "status": "durable_mutation_disabled",
            "exchange_write_called": False,
            "blockers": [],
        }
        durable_mutation_enabled = capability["enabled"] is True
        reconciliation_payload: dict[str, Any] = {
            "status": "no_unknown_commands",
            "exchange_read_called": False,
            "exchange_write_called": False,
            "blockers": [],
        }
        if command_pending and gateway is not None:
            with telemetry.stage("unknown_command_reconciliation"):
                telemetry.exchange_request_count += 1
                reconciliation_payload = (
                    await _await_before_deadline(
                        run_one_unknown_exchange_command_reconciliation(
                            engine,
                            gateway=gateway,
                            now_ms=int(time.time() * 1000),
                        ),
                        deadline_at=deadline_at,
                        stage="unknown_command_reconciliation",
                    )
                )
        if (
            command_pending
            and durable_mutation_enabled
            and gateway is not None
            and reconciliation_payload.get("status") == "no_unknown_commands"
        ):
            dispatch_timeout = max(
                0.1,
                _remaining_seconds(deadline_at, "durable_exchange_command") - 1.0,
            )
            with telemetry.stage("durable_exchange_command"):
                telemetry.exchange_request_count += 1
                worker_payload = await run_one_ticket_bound_exchange_command(
                    engine,
                    gateway=gateway,
                    worker_id=f"ticket-lifecycle:{os.getpid()}",
                    lease_ms=args.command_lease_ms,
                    command_sources=LIFECYCLE_MUTATION_COMMAND_SOURCES,
                    dispatch_timeout_seconds=dispatch_timeout,
                )
            _remaining_seconds(deadline_at, "durable_exchange_command_result")

        with telemetry.stage("snapshot_scope_selection"):
            with engine.begin() as conn:
                telemetry.pg_transaction_count += 1
                first_tick_scopes = [
                    {**scope, "scheduler_scope_kind": "first_post_submit"}
                    for scope in select_ticket_bound_first_reconciliation_tick_scopes(
                        conn,
                        max_scopes=1,
                    )
                ]
                scopes = select_ticket_bound_lifecycle_maintenance_scopes(
                    conn,
                    max_lifecycle_scopes=1,
                )
                prepared_scopes = _prepare_snapshot_scopes(
                    conn,
                    first_tick_scopes=first_tick_scopes,
                    scopes=scopes,
                )

        provided_snapshots: dict[str, dict[str, Any]] = {}
        for prepared in prepared_scopes:
            with telemetry.stage("exchange_snapshot"):
                snapshot_payload = await _await_before_deadline(
                    fetch_resolved_ticket_bound_exchange_snapshot(
                        scope=prepared["scope"],
                        snapshot_identity=prepared["snapshot_identity"],
                        gateway=gateway,
                        timeout_seconds=min(
                            args.snapshot_timeout_seconds,
                            _remaining_seconds(deadline_at, "exchange_snapshot"),
                        ),
                        recent_fill_limit=50,
                        conditional_parent_order_ids=prepared[
                            "conditional_parent_order_ids"
                        ],
                        now_ms=prepared["now_ms"],
                        authority_boundary=prepared["authority_boundary"],
                    ),
                    deadline_at=deadline_at,
                    stage="exchange_snapshot",
                )
                provided_snapshots[prepared["snapshot_identity"]] = snapshot_payload
                telemetry.exchange_request_count += int(
                    snapshot_payload.get("exchange_request_count") or 1
                )

        with engine.connect() as conn:
            account_risk_scopes = _active_account_risk_scopes(
                conn,
                prepared_scopes=prepared_scopes,
            )
            conn.rollback()
        provided_account_risk_snapshots = await _prefetch_account_risk_snapshots(
            account_risk_scopes,
            env_file=Path(args.account_risk_env_file).expanduser(),
            base_url=args.account_risk_base_url,
            timeout_seconds=min(
                args.account_risk_timeout_seconds,
                _remaining_seconds(deadline_at, "account_risk_snapshot"),
            ),
        )

        _remaining_seconds(deadline_at, "pg_lifecycle_projection")
        with telemetry.stage("pg_lifecycle_projection"):
            with engine.begin() as conn:
                telemetry.pg_transaction_count += 1
                maintenance_payload = await run_ticket_bound_lifecycle_maintenance_scheduler(
                    conn,
                    gateway=None,
                    allow_exchange_mutation=False,
                    fetch_exchange_snapshot=False,
                    max_lifecycle_scopes=1,
                    max_actions_per_scope=args.max_actions_per_scope,
                    snapshot_timeout_seconds=args.snapshot_timeout_seconds,
                    provided_exchange_snapshots=provided_snapshots,
                    provided_account_risk_snapshots=provided_account_risk_snapshots,
                )
        payload = {
            **maintenance_payload,
            "schema": "brc.ticket_bound_lifecycle_production_worker.v2",
            "durable_mutation_enabled": durable_mutation_enabled,
            "durable_mutation_capability_ref": (
                capability.get("capability", {}).get("certification_ref")
            ),
            "exchange_command_worker": worker_payload,
            "exchange_command_reconciliation": reconciliation_payload,
            "exchange_write_called": (
                worker_payload.get("exchange_write_called") is True
            ),
            "network_inside_pg_transaction": False,
            "max_mutation_commands_per_invocation": 1,
            "global_deadline_seconds": float(args.global_deadline_seconds),
            "deadline_remaining_seconds": max(0.0, deadline_at - time.monotonic()),
            "performance": telemetry.snapshot(deadline_at=deadline_at),
        }
    except TimeoutError as exc:
        payload = {
            "schema": "brc.ticket_bound_lifecycle_production_worker.v2",
            "status": "scheduler_process_failed",
            "first_blocker": "lifecycle_global_deadline_exceeded",
            "blockers": ["lifecycle_global_deadline_exceeded", str(exc)],
            "exchange_write_called": worker_payload.get("exchange_write_called") is True,
            "network_inside_pg_transaction": False,
            "global_deadline_seconds": float(args.global_deadline_seconds),
            "performance": telemetry.snapshot(deadline_at=deadline_at),
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 1
    finally:
        engine.dispose()
        close = getattr(gateway, "close", None)
        if callable(close):
            await close()

    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if payload.get("status") in {
        "scheduler_complete",
        "scheduler_blocked",
        "no_maintainable_lifecycle",
    } else 1


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_amain(argv))


async def _runtime_exchange_gateway_binding() -> dict[str, Any]:
    from src.infrastructure.runtime_exchange_gateway_binding import (
        bind_runtime_exchange_submit_gateway,
    )

    return await bind_runtime_exchange_submit_gateway(
        sys.modules[__name__],
        lifecycle_readonly=True,
    )


def _blocked_gateway_payload(gateway_binding: dict[str, Any]) -> dict[str, Any]:
    blockers = [
        str(item)
        for item in (gateway_binding.get("blockers") or [])
        if str(item or "").strip()
    ]
    return {
        "schema": "brc.ticket_bound_lifecycle_maintenance_scheduler.v1",
        "status": "scheduler_blocked",
        "selected_scope_count": 0,
        "scopes": [],
        "runs": [],
        "first_blocker": blockers[0] if blockers else "runtime_exchange_gateway_unavailable",
        "blockers": blockers or ["runtime_exchange_gateway_unavailable"],
        "next_action": "repair_runtime_exchange_gateway_binding",
        "exchange_read_called": False,
        "exchange_write_called": False,
        "finalgate_called": False,
        "operation_layer_called": False,
        "withdrawal_or_transfer_created": False,
        "live_profile_changed": False,
        "order_sizing_changed": False,
        "runtime_budget_mutated": False,
        "authority_boundary": (
            "ticket_bound_lifecycle_maintenance_scheduler_cli; gateway binding "
            "failed before lifecycle maintenance; no exchange call or file output"
        ),
    }


def _prepared_or_unknown_command_exists(conn: sa.engine.Connection) -> bool:
    return conn.execute(
        sa.text(
            """
            SELECT exchange_command_id
            FROM brc_ticket_bound_exchange_commands
            WHERE command_source IN :command_sources
              AND command_state IN ('prepared', 'dispatching', 'outcome_unknown')
            ORDER BY exchange_command_id
            LIMIT 1
            """
        ).bindparams(sa.bindparam("command_sources", expanding=True)),
        {"command_sources": tuple(LIFECYCLE_MUTATION_COMMAND_SOURCES)},
    ).first() is not None


def _prepare_snapshot_scopes(
    conn: sa.engine.Connection,
    *,
    first_tick_scopes: list[dict[str, Any]],
    scopes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    now_ms = int(time.time() * 1000)
    for item in first_tick_scopes[:1]:
        resolution = resolve_ticket_bound_exchange_scope(
            conn,
            ticket_id=str(item.get("ticket_id") or ""),
            now_ms=now_ms,
        )
        if resolution.status == "resolved" and resolution.scope is not None:
            prepared.append(
                {
                    "snapshot_identity": str(
                        item["protected_submit_attempt_id"]
                    ),
                    "scope": resolution.scope,
                    "conditional_parent_order_ids": (
                        load_ticket_conditional_parent_order_ids(
                            conn,
                            ticket_id=str(item.get("ticket_id") or ""),
                        )
                    ),
                    "now_ms": now_ms,
                    "authority_boundary": ATTEMPT_AUTHORITY_BOUNDARY,
                }
            )
        return prepared
    for item in scopes[:1]:
        if not item.get("exit_protection_set_id"):
            continue
        resolution = resolve_ticket_bound_exchange_scope(
            conn,
            ticket_id=str(item.get("ticket_id") or ""),
            now_ms=now_ms,
        )
        if resolution.status == "resolved" and resolution.scope is not None:
            prepared.append(
                {
                    "snapshot_identity": str(item["exit_protection_set_id"]),
                    "scope": resolution.scope,
                    "conditional_parent_order_ids": (
                        load_ticket_conditional_parent_order_ids(
                            conn,
                            ticket_id=str(item.get("ticket_id") or ""),
                        )
                    ),
                    "now_ms": now_ms,
                    "authority_boundary": SNAPSHOT_AUTHORITY_BOUNDARY,
                }
            )
    return prepared


def _active_account_risk_scopes(
    conn: sa.Connection,
    *,
    prepared_scopes: list[dict[str, Any]],
) -> dict[str, tuple[str, str, str]]:
    """Return Ticket-to-account scopes only for active capacity policy.

    The result is intentionally keyed by Ticket rather than symbol.  A single
    full-account snapshot may be reused for multiple selected Tickets of the
    same account, while the scheduler remains unable to infer account truth
    from per-Ticket exchange snapshots.
    """

    if not prepared_scopes:
        return {}
    active_pairs = {
        (str(row["account_id"]), str(row["runtime_profile_id"]))
        for row in conn.execute(
            sa.text(
                """
                SELECT account_id, runtime_profile_id
                FROM brc_account_risk_policy_current
                WHERE activation_state = 'active'
                ORDER BY account_id, runtime_profile_id
                """
            )
        ).mappings()
    }
    result: dict[str, tuple[str, str, str]] = {}
    for prepared in prepared_scopes:
        scope = prepared.get("scope")
        if scope is None:
            continue
        account_id = str(getattr(scope, "account_id", "") or "")
        runtime_profile_id = str(getattr(scope, "runtime_profile_id", "") or "")
        exchange_id = str(getattr(scope, "exchange_id", "") or "")
        ticket_id = str(getattr(scope, "ticket_id", "") or "")
        if (
            ticket_id
            and exchange_id == "binance_usdm"
            and (account_id, runtime_profile_id) in active_pairs
        ):
            result[ticket_id] = (account_id, runtime_profile_id, exchange_id)
    return result


async def _prefetch_account_risk_snapshots(
    ticket_scopes: dict[str, tuple[str, str, str]],
    *,
    env_file: Path,
    base_url: str,
    timeout_seconds: float,
) -> dict[str, FullAccountRiskSnapshot]:
    """Fetch one full-account snapshot per selected account outside PG work."""

    by_account: dict[tuple[str, str], FullAccountRiskSnapshot] = {}
    for account_id, _runtime_profile_id, exchange_id in sorted(set(ticket_scopes.values())):
        key = (account_id, exchange_id)
        by_account[key] = await _fetch_account_risk_snapshot(
            account_id=account_id,
            exchange_id=exchange_id,
            env_file=env_file,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    return {
        ticket_id: by_account[(account_id, exchange_id)]
        for ticket_id, (account_id, _runtime_profile_id, exchange_id) in ticket_scopes.items()
    }


async def _fetch_account_risk_snapshot(
    *,
    account_id: str,
    exchange_id: str,
    env_file: Path,
    base_url: str,
    timeout_seconds: float,
) -> FullAccountRiskSnapshot:
    """Use the official signed GET collector only; no gateway mutation surface."""

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

    async def signed_get(path: str) -> Any:
        if reader is None:
            raise RuntimeError("exchange_api_key_or_secret_missing")
        return await asyncio.to_thread(reader.get, path)

    provider = BinanceUsdmAccountRiskSnapshotProvider(
        account_id=account_id,
        exchange_id=exchange_id,
        signed_get=signed_get,
    )
    return await provider.fetch(timeout_seconds=timeout_seconds)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--fetch-exchange-snapshot", action="store_true")
    parser.add_argument("--allow-exchange-mutation", action="store_true")
    parser.add_argument("--max-lifecycle-scopes", type=int, default=1)
    parser.add_argument("--max-actions-per-scope", type=int, default=16)
    parser.add_argument("--snapshot-timeout-seconds", type=float, default=8.0)
    parser.add_argument(
        "--account-risk-env-file",
        default=str(DEFAULT_ACCOUNT_RISK_ENV_FILE),
    )
    parser.add_argument("--account-risk-base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--account-risk-timeout-seconds", type=float, default=12.0)
    parser.add_argument("--command-lease-ms", type=int, default=15_000)
    parser.add_argument("--global-deadline-seconds", type=float, default=28.0)
    args = parser.parse_args(argv)
    if args.global_deadline_seconds <= 0:
        parser.error("--global-deadline-seconds must be positive")
    return args


async def _await_before_deadline(
    awaitable: Any,
    *,
    deadline_at: float,
    stage: str,
) -> Any:
    return await asyncio.wait_for(
        awaitable,
        timeout=_remaining_seconds(deadline_at, stage),
    )


def _remaining_seconds(deadline_at: float, stage: str) -> float:
    remaining = float(deadline_at) - time.monotonic()
    if remaining <= 0:
        raise TimeoutError(f"lifecycle_global_deadline_exceeded:{stage}")
    return remaining


if __name__ == "__main__":
    raise SystemExit(main())
