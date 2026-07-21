#!/usr/bin/env python3
"""Build read-only account-safe facts from PG scope and signed GET facts."""

from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, TimeoutError, wait
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
import urllib.request

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[3]

from src.application.action_time.runtime_pg_fact_snapshots import (  # noqa: E402
    write_account_safe_fact_snapshots,
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
    ACCOUNT_MODE_SOURCE,
    DEFAULT_BASE_URL,
    READ_ONLY_ENDPOINTS,
    UrlOpen,
    _account_mode_summary,
    _account_summary,
    _budget_state,
    _env_value,
    _exchange_rules,
    _next_attempt_gate_state,
    _leverage_bracket_summary,
    _open_order_summary,
    _position_summary,
    _protection_state,
    _request_json,
)
DEFAULT_ENV_FILE = Path("/home/ubuntu/brc-deploy/env/live-readonly.env")
ACCOUNT_MODE_VALID_FOR_MS = 60_000
ACCOUNT_MODE_MAX_FUTURE_SKEW_MS = 5_000


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--allow-non-postgres-for-test", action="store_true")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout-seconds", type=float, default=12)
    parser.add_argument("--action-time-invocation-id", default=None)
    parser.add_argument(
        "--allow-blocked-current-projection",
        action="store_true",
        help=(
            "Return success after a blocked fact projection is durably written; "
            "intended for recurring read-only collection cadence only."
        ),
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        print(
            "ERROR: PG_DATABASE_URL is required for DB-backed account-safe facts",
            file=sys.stderr,
        )
        return 2
    database_url = normalize_sync_postgres_dsn(args.database_url)
    if not is_sync_postgres_dsn(database_url) and not args.allow_non_postgres_for_test:
        print(
            "ERROR: DB-backed account-safe facts require PostgreSQL DSN",
            file=sys.stderr,
        )
        return 2

    engine = sa.create_engine(database_url)
    try:
        artifact = materialize_account_safe_facts(
            engine,
            action_time_invocation_id=args.action_time_invocation_id,
            env_file=Path(args.env_file).expanduser() if args.env_file else None,
            base_url=args.base_url,
            timeout_seconds=args.timeout_seconds,
        )
    finally:
        engine.dispose()
    account_safe_ready = artifact["checks"]["account_safe_facts_ready"] is True
    action_time_check = artifact["checks"].get("action_time_account_facts_ready")
    action_time_account_facts_ready = (
        account_safe_ready
        if action_time_check is None
        else action_time_check is True
    )
    business_blocker = artifact.get("business_blocker")
    fact_snapshot_ids = artifact["pg_fact_snapshot_ids"]
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "account_safe_facts_ready": account_safe_ready,
                "action_time_account_facts_ready": action_time_account_facts_ready,
                "action_time_invocation_id": args.action_time_invocation_id,
                "pg_fact_snapshot_ids": sorted(fact_snapshot_ids),
                "process_outcome": (
                    {
                        "process_state": "business_blocked",
                        "business_state": "temporarily_unavailable",
                        "first_blocker": business_blocker,
                    }
                    if business_blocker
                    else {
                        "process_state": "succeeded",
                        "business_state": "ready",
                        "first_blocker": None,
                    }
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return (
        0
        if (
            (
                action_time_account_facts_ready
                if args.action_time_invocation_id
                else account_safe_ready
            )
            or business_blocker is not None
            or args.allow_blocked_current_projection
        )
        else 2
    )


def materialize_account_safe_facts(
    engine: sa.Engine,
    *,
    action_time_invocation_id: str | None,
    env_file: Path | None,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = 12,
    urlopen: UrlOpen | None = None,
) -> dict[str, Any]:
    """Collect readonly facts and persist their PG snapshots without a CLI hop.

    The short PG scope read completes before signed network I/O.  Only the
    final snapshot insert uses a write transaction, so no database lock spans
    an exchange request.
    """

    with engine.connect() as conn:
        scope = _pg_account_safe_scope_summary(conn)
        conn.rollback()
    live_facts = collect_account_safe_live_facts_from_scope(
        scope,
        env_file=env_file,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        urlopen=urlopen,
    )
    artifact = build_runtime_account_safe_facts(live_facts=live_facts)
    account_safe_ready = artifact["checks"]["account_safe_facts_ready"] is True
    has_action_time_account_fact_shape = (
        "action_time_account_facts_ready" in artifact["checks"]
    )
    action_time_account_facts_ready = artifact["checks"].get(
        "action_time_account_facts_ready"
    )
    if action_time_account_facts_ready is None:
        # Existing test/diagnostic callers may carry only the pre-R10 fact
        # shape.  They retain the old fail-closed semantics; production
        # collectors always emit the capacity-aware field below.
        action_time_account_facts_ready = account_safe_ready
    else:
        action_time_account_facts_ready = action_time_account_facts_ready is True
    business_blocker = None
    fact_binding_invocation_id = action_time_invocation_id
    if action_time_invocation_id and not action_time_account_facts_ready:
        business_blocker = (
            _action_time_account_fact_blocker(artifact)
            if has_action_time_account_fact_shape
            else str(
                (artifact.get("blockers") or [
                    "action_time_account_safe_facts_not_satisfied"
                ])[0]
            )
        )
        # Persist the fail-closed facts, but never bind an account fact set
        # that cannot satisfy the Invocation-bound capacity boundary.
        fact_binding_invocation_id = None
    with engine.begin() as conn:
        fact_snapshot_ids = write_account_safe_fact_snapshots(
            conn,
            artifact=artifact,
            source_ref="runtime_account_safe_pg_scope_readonly",
            action_time_invocation_id=fact_binding_invocation_id,
        )
    return {
        **artifact,
        "business_blocker": business_blocker,
        "action_time_account_facts_ready": action_time_account_facts_ready,
        "source_mode": "db_backed",
        "projection_target": "production_current",
        "collector_source_mode": "pg_scope_direct_readonly_exchange",
        "pg_fact_snapshot_ids": fact_snapshot_ids,
    }


def collect_account_safe_live_facts_from_pg_scope(
    conn: sa.engine.Connection,
    *,
    env_file: Path | None,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = 12,
    urlopen: UrlOpen | None = None,
) -> dict[str, Any]:
    scope = _pg_account_safe_scope_summary(conn)
    return collect_account_safe_live_facts_from_scope(
        scope,
        env_file=env_file,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        urlopen=urlopen,
    )


def collect_account_safe_live_facts_from_scope(
    scope: dict[str, Any],
    *,
    env_file: Path | None,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = 12,
    urlopen: UrlOpen | None = None,
) -> dict[str, Any]:
    """Collect one complete account snapshot and rules within one deadline.

    The account snapshot is the sole account/position/order/mode authority for
    this Action-Time fact generation.  Exchange contract and leverage rules
    are independent read-only surfaces, so they run concurrently with it.
    """

    symbols = list(scope["symbols"])
    api_key = _env_value(
        ("EXCHANGE_API_KEY", "BINANCE_API_KEY", "binance_exchange_key"),
        env_file=env_file,
    )
    api_secret = _env_value(
        ("EXCHANGE_API_SECRET", "BINANCE_SECRET_KEY", "binance_exchange_secret"),
        env_file=env_file,
    )
    errors: dict[str, str] = {
        "scope_identity": ",".join(scope["identity_errors"])
        for _ in [0]
        if scope["identity_errors"]
    }
    opener = urlopen if urlopen is not None else urllib.request.urlopen
    collected_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    payloads, account_risk_snapshot, collection_errors = _collect_action_time_inputs(
        account_id=str(scope.get("account_id") or ""),
        exchange_id=str(scope.get("exchange_id") or ""),
        api_key=api_key,
        api_secret=api_secret,
        env_file=env_file,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        urlopen=opener,
    )
    errors.update(collection_errors)

    exchange_rules = _exchange_rules(payloads.get("exchange_info", {}), symbols)
    leverage_brackets = _leverage_bracket_summary(
        payloads.get("leverage_brackets", {}), symbols
    )
    account = _account_summary_from_snapshot(account_risk_snapshot)
    position = _position_summary_from_snapshot(account_risk_snapshot, symbols)
    open_orders = _open_order_summary_from_snapshot(account_risk_snapshot, symbols)
    account_mode = _account_mode_summary_from_snapshot(
        account_risk_snapshot,
        account_id=scope.get("account_id"),
        exchange_id=scope.get("exchange_id"),
        runtime_profile_id=scope.get("runtime_profile_id"),
        collected_at_ms=collected_at_ms,
    )
    budget = _budget_state(
        account_payload=_account_payload_from_snapshot(account_risk_snapshot),
        handoff_summary=scope,
    )
    protection = _protection_state(scope)
    next_attempt_gate = _next_attempt_gate_state(
        position=position,
        open_orders=open_orders,
    )
    return {
        "scope": "strategy_group_live_facts_input",
        "status": (
            "ready"
            if (
                not errors
                and symbols
                and account_mode.get("position_mode_safe") is True
            )
            else "partial"
        ),
        "source": "pg_scope_binance_usdm_futures_readonly_get_endpoints",
        "source_mode": "pg_scope_direct_readonly_exchange",
        "supported_symbol_count": len(symbols),
        "exchange_rules": exchange_rules,
        "account": account,
        "leverage_brackets": leverage_brackets,
        "account_mode": account_mode,
        "active_position": position,
        "open_orders": open_orders,
        "protection": protection,
        "budget": budget,
        "next_attempt_gate": next_attempt_gate,
        "account_risk_snapshot": (
            account_risk_snapshot.model_dump(mode="json")
            if account_risk_snapshot is not None
            else {}
        ),
        "collector_errors": errors,
        "safety_invariants": {
            "signed_get_only": True,
            "post_delete_put_used": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "execution_intent_created": False,
            "runtime_budget_mutated": False,
            "withdrawal_or_transfer_created": False,
            "secrets_printed": False,
        },
    }


def _collect_action_time_inputs(
    *,
    account_id: str,
    exchange_id: str,
    api_key: str | None,
    api_secret: str | None,
    env_file: Path | None,
    base_url: str,
    timeout_seconds: float,
    urlopen: UrlOpen,
) -> tuple[dict[str, dict[str, Any]], FullAccountRiskSnapshot | None, dict[str, str]]:
    """Run the independent readonly inputs under one wall-clock budget."""

    payloads: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    account_snapshot: FullAccountRiskSnapshot | None = None
    if timeout_seconds <= 0:
        return payloads, None, {"action_time_inputs": "timeout_invalid"}
    request_specs = {
        name: READ_ONLY_ENDPOINTS[name]
        for name in ("exchange_info", "leverage_brackets")
    }
    executor = ThreadPoolExecutor(max_workers=len(request_specs) + 1)
    futures: dict[Future[Any], str] = {}
    try:
        for name, (_method, path, signed) in request_specs.items():
            futures[executor.submit(
                _request_json,
                base_url=base_url,
                path=path,
                api_key=api_key,
                api_secret=api_secret,
                signed=signed,
                timeout_seconds=timeout_seconds,
                urlopen=urlopen,
            )] = name
        futures[executor.submit(
            _fetch_account_risk_snapshot,
            account_id=account_id,
            exchange_id=exchange_id,
            env_file=env_file,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )] = "account_risk_snapshot"
        deadline = time.monotonic() + timeout_seconds
        pending = set(futures)
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            done, pending = wait(
                pending,
                timeout=remaining,
                return_when=FIRST_COMPLETED,
            )
            if not done:
                raise TimeoutError
            for future in done:
                name = futures[future]
                try:
                    value = future.result()
                except Exception as exc:
                    errors[name] = _collector_error(exc)
                    continue
                if name == "account_risk_snapshot":
                    account_snapshot = (
                        value if isinstance(value, FullAccountRiskSnapshot) else None
                    )
                    if account_snapshot is None:
                        errors[name] = "snapshot_missing"
                    elif not account_snapshot.snapshot_ready:
                        errors[name] = str(
                            account_snapshot.failure_code
                            or "account_risk_snapshot_not_ready"
                        )
                    continue
                payloads[name] = value if isinstance(value, dict) else {}
        return payloads, account_snapshot, errors
    except TimeoutError:
        for future, name in futures.items():
            if not future.done():
                future.cancel()
                errors[name] = "collection_deadline_exceeded"
        snapshot = None
        for future, name in futures.items():
            if name != "account_risk_snapshot" or not future.done():
                continue
            try:
                value = future.result()
            except Exception as exc:
                errors[name] = _collector_error(exc)
                continue
            if isinstance(value, FullAccountRiskSnapshot):
                snapshot = value
                if not snapshot.snapshot_ready:
                    errors[name] = str(
                        snapshot.failure_code or "account_risk_snapshot_not_ready"
                    )
        return payloads, snapshot, errors
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _collector_error(exc: Exception) -> str:
    return f"{type(exc).__name__}:{str(exc)[:220]}"


def _account_summary_from_snapshot(
    snapshot: FullAccountRiskSnapshot | None,
) -> dict[str, Any]:
    if snapshot is None or not snapshot.snapshot_ready:
        return {"status": "missing"}
    total_wallet_balance = snapshot.total_wallet_balance
    available_balance = snapshot.available_balance
    return {
        "status": "fresh",
        "exchange_account_trade_permission": snapshot.can_trade is True,
        "total_wallet_balance": (
            str(total_wallet_balance) if total_wallet_balance is not None else None
        ),
        "available_balance": (
            str(available_balance) if available_balance is not None else None
        ),
        "total_wallet_balance_present": total_wallet_balance is not None,
        "total_wallet_balance_positive": (
            total_wallet_balance is not None and total_wallet_balance > Decimal("0")
        ),
        "available_balance_present": available_balance is not None,
        "available_balance_positive": (
            available_balance is not None and available_balance > Decimal("0")
        ),
    }


def _account_payload_from_snapshot(
    snapshot: FullAccountRiskSnapshot | None,
) -> dict[str, Any]:
    if snapshot is None or not snapshot.snapshot_ready:
        return {}
    return {
        "payload": {
            "canTrade": snapshot.can_trade is True,
            "totalWalletBalance": (
                str(snapshot.total_wallet_balance)
                if snapshot.total_wallet_balance is not None
                else None
            ),
            "availableBalance": (
                str(snapshot.available_balance)
                if snapshot.available_balance is not None
                else None
            ),
        }
    }


def _position_summary_from_snapshot(
    snapshot: FullAccountRiskSnapshot | None,
    symbols: list[str],
) -> dict[str, Any]:
    if snapshot is None or not snapshot.snapshot_ready:
        return {"status": "missing", "active_count": None, "active_symbols": []}
    scoped_symbols = set(symbols)
    active = sorted(
        {
            row.exchange_symbol
            for row in snapshot.positions
            if row.exchange_symbol in scoped_symbols and row.position_qty != 0
        }
    )
    return {
        "status": "no_active_position" if not active else "active_position_present",
        "active_count": len(active),
        "active_symbols": active,
    }


def _open_order_summary_from_snapshot(
    snapshot: FullAccountRiskSnapshot | None,
    symbols: list[str],
) -> dict[str, Any]:
    if snapshot is None or not snapshot.snapshot_ready:
        return {"status": "missing", "open_order_count": None, "open_order_symbols": []}
    scoped_symbols = set(symbols)
    matched = sorted(
        {
            row.exchange_symbol
            for row in (*snapshot.regular_open_orders, *snapshot.algo_open_orders)
            if row.exchange_symbol in scoped_symbols
        }
    )
    return {
        "status": "no_open_orders" if not matched else "open_orders_present",
        "open_order_count": len(matched),
        "open_order_symbols": matched,
    }


def _account_mode_summary_from_snapshot(
    snapshot: FullAccountRiskSnapshot | None,
    *,
    account_id: str | None,
    exchange_id: str | None,
    runtime_profile_id: str | None,
    collected_at_ms: int,
) -> dict[str, Any]:
    if snapshot is None or not snapshot.snapshot_ready:
        return _account_mode_summary(
            {},
            account_id=account_id,
            exchange_id=exchange_id,
            runtime_profile_id=runtime_profile_id,
            collected_at_ms=collected_at_ms,
        )
    return _account_mode_summary(
        {
            "payload": {"dualSidePosition": snapshot.position_mode == "hedge"},
            "observed_at_ms": snapshot.observed_at_ms,
        },
        account_id=account_id,
        exchange_id=exchange_id,
        runtime_profile_id=runtime_profile_id,
        collected_at_ms=collected_at_ms,
    )


def _fetch_account_risk_snapshot(
    *,
    account_id: str,
    exchange_id: str,
    env_file: Path | None,
    base_url: str,
    timeout_seconds: float,
) -> FullAccountRiskSnapshot | None:
    """Fetch one complete, all-account capacity snapshot outside PG scope reads."""

    if not account_id or exchange_id != "binance_usdm":
        return None
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
    return asyncio.run(provider.fetch(timeout_seconds=timeout_seconds))


def _pg_account_safe_scope_summary(conn: sa.engine.Connection) -> dict[str, Any]:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    scope_rows = [
        dict(row)
        for row in conn.execute(
            sa.text(
                """
                SELECT DISTINCT
                  candidate.strategy_group_id,
                  candidate.symbol,
                  runtime.runtime_profile_id,
                  version.risk_envelope,
                  instrument.exchange_id
                FROM brc_strategy_group_candidate_scope AS candidate
                LEFT JOIN brc_owner_policy_current AS policy
                  ON policy.policy_current_id = candidate.policy_current_id
                LEFT JOIN brc_runtime_scope_bindings AS runtime
                  ON runtime.candidate_scope_id = candidate.candidate_scope_id
                 AND runtime.status = 'active'
                LEFT JOIN brc_strategy_groups AS strategy_group
                  ON strategy_group.strategy_group_id = candidate.strategy_group_id
                LEFT JOIN brc_strategy_group_versions AS version
                  ON version.strategy_group_version_id = strategy_group.current_version_id
                LEFT JOIN brc_symbol_instrument_mappings AS mapping
                  ON mapping.symbol = candidate.symbol
                 AND mapping.status = 'active'
                 AND mapping.valid_from_ms <= :now_ms
                 AND (
                   mapping.valid_until_ms IS NULL
                   OR mapping.valid_until_ms > :now_ms
                 )
                LEFT JOIN brc_exchange_instruments AS instrument
                  ON instrument.exchange_instrument_id = mapping.exchange_instrument_id
                 AND instrument.status = 'active'
                WHERE candidate.status = 'active'
                  AND candidate.scope_state = 'live_submit_allowed'
                  AND (
                    policy.policy_current_id IS NULL
                    OR (
                      policy.enabled_state = 'enabled'
                      AND policy.pretrade_candidate_allowed = true
                    )
                  )
                ORDER BY candidate.strategy_group_id, candidate.symbol
                """
            ),
            {"now_ms": now_ms},
        ).mappings()
    ]
    symbols = sorted({str(row.get("symbol") or "").upper() for row in scope_rows if row.get("symbol")})
    runtime_profile_ids = {
        str(row.get("runtime_profile_id") or "").strip()
        for row in scope_rows
        if str(row.get("runtime_profile_id") or "").strip()
    }
    account_ids = {
        str(_json_object(row.get("risk_envelope")).get("account_id") or "").strip()
        for row in scope_rows
        if str(_json_object(row.get("risk_envelope")).get("account_id") or "").strip()
    }
    exchange_ids = {
        str(row.get("exchange_id") or "").strip()
        for row in scope_rows
        if str(row.get("exchange_id") or "").strip()
    }
    identity_errors: list[str] = []
    if len(account_ids) != 1:
        identity_errors.append("account_id_missing_or_ambiguous")
    if len(exchange_ids) != 1:
        identity_errors.append("exchange_id_missing_or_ambiguous")
    elif exchange_ids != {"binance_usdm"}:
        identity_errors.append("exchange_id_not_binance_usdm")
    if len(runtime_profile_ids) != 1:
        identity_errors.append("runtime_profile_id_missing_or_ambiguous")
    protection_count = conn.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM brc_strategy_group_candidate_scope AS candidate
            JOIN brc_candidate_scope_event_bindings AS binding
              ON binding.candidate_scope_id = candidate.candidate_scope_id
            JOIN brc_strategy_side_event_specs AS spec
              ON spec.event_spec_id = binding.event_spec_id
            LEFT JOIN brc_owner_policy_current AS policy
              ON policy.policy_current_id = candidate.policy_current_id
            WHERE candidate.status = 'active'
              AND candidate.scope_state = 'live_submit_allowed'
              AND binding.status = 'active'
              AND spec.status = 'current'
              AND COALESCE(spec.protection_ref_type, '') <> ''
              AND (
                policy.policy_current_id IS NULL
                OR (
                  policy.enabled_state = 'enabled'
                  AND policy.pretrade_candidate_allowed = true
                )
              )
            """
        )
    ).scalar_one()
    return {
        "symbols": symbols,
        "strategy_group_count": len({str(row.get("strategy_group_id")) for row in scope_rows}),
        "risk_capacity_source": "dynamic_wallet_and_available_balance",
        "has_candidate_specific_protection_template": int(protection_count or 0) > 0,
        "account_id": next(iter(account_ids), None) if len(account_ids) == 1 else None,
        "exchange_id": (
            next(iter(exchange_ids), None) if len(exchange_ids) == 1 else None
        ),
        "runtime_profile_id": (
            next(iter(runtime_profile_ids), None)
            if len(runtime_profile_ids) == 1
            else None
        ),
        "identity_errors": identity_errors,
    }


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def build_runtime_account_safe_facts(
    *, live_facts: dict[str, Any], generated_at_utc: str | None = None
) -> dict[str, Any]:
    effective_generated_at_utc = generated_at_utc or datetime.now(
        timezone.utc
    ).isoformat()
    account = _as_dict(live_facts.get("account"))
    active_position = _as_dict(live_facts.get("active_position"))
    open_orders = _as_dict(live_facts.get("open_orders"))
    budget = _as_dict(live_facts.get("budget"))
    exchange_rules = _as_dict(live_facts.get("exchange_rules"))
    next_attempt_gate = _as_dict(live_facts.get("next_attempt_gate"))
    protection = _as_dict(live_facts.get("protection"))
    source_safety = _as_dict(live_facts.get("safety_invariants"))
    leverage_brackets = _as_dict(live_facts.get("leverage_brackets"))
    account_risk_snapshot = _as_dict(live_facts.get("account_risk_snapshot"))
    account_mode = _normalized_account_mode_fact(
        _as_dict(live_facts.get("account_mode")),
        generated_at_utc=effective_generated_at_utc,
    )
    total_wallet_balance = _decimal_or_none(account.get("total_wallet_balance"))
    available_balance = _decimal_or_none(account.get("available_balance"))

    checks = {
        "source_live_facts_ready": live_facts.get("status") == "ready",
        "account_balance_present": account.get("available_balance_present") is True,
        "account_balance_positive": account.get("available_balance_positive") is True,
        "account_wallet_balance_present": total_wallet_balance is not None,
        "account_wallet_balance_positive": (
            total_wallet_balance is not None
            and total_wallet_balance.is_finite()
            and total_wallet_balance > Decimal("0")
        ),
        "account_trade_permission": account.get("exchange_account_trade_permission")
        is True,
        "active_position_clear": active_position.get("status")
        == "no_active_position",
        "open_orders_clear": open_orders.get("status") == "no_open_orders",
        "budget_available": str(budget.get("status") or "").startswith("available"),
        "exchange_rules_ready": exchange_rules.get("status") == "ready",
        "next_attempt_gate_ready": next_attempt_gate.get("status")
        == "ready_for_strategy_signal",
        "protection_template_ready": str(protection.get("status") or "").startswith(
            "ready"
        ),
        "account_mode_ready": account_mode.get("position_mode_safe") is True,
        "leverage_brackets_ready": leverage_brackets.get("status") == "ready",
        "source_signed_get_only": source_safety.get("signed_get_only") is True,
        "source_exchange_write_called": source_safety.get("exchange_write_called")
        is True,
        "source_order_created": source_safety.get("order_created") is True,
    }
    # The legacy action-time surface intentionally remains flat-only.  The
    # account-capacity path needs a narrower fact: all non-position account
    # safety checks are healthy, while exact position/order ownership will be
    # reclassified from the full account snapshot inside its PG transaction.
    account_capacity_base_safe = (
        all(
            value is True
            for key, value in checks.items()
            if key
            not in {
                "active_position_clear",
                "open_orders_clear",
                "next_attempt_gate_ready",
                "source_exchange_write_called",
                "source_order_created",
            }
        )
        and checks["source_exchange_write_called"] is False
        and checks["source_order_created"] is False
    )
    account_capacity_base = _account_capacity_base_fact(
        snapshot=account_risk_snapshot,
        account_mode=account_mode,
        generated_at_utc=effective_generated_at_utc,
    )
    action_time_account_facts_ready = (
        account_capacity_base_safe and account_capacity_base["ready"]
    )
    ready = (
        all(
            value is True
            for key, value in checks.items()
            if key
            not in {
                "source_exchange_write_called",
                "source_order_created",
            }
        )
        and checks["source_exchange_write_called"] is False
        and checks["source_order_created"] is False
    )
    blockers = [
        key
        for key, value in checks.items()
        if (
            value is not True
            and key not in {"source_exchange_write_called", "source_order_created"}
        )
        or (
            key in {"source_exchange_write_called", "source_order_created"}
            and value is not False
        )
    ]
    return {
        "schema": "brc.runtime_account_safe_facts.v1",
        "scope": "runtime_account_safe_facts_readonly",
        "status": (
            "runtime_account_safe_facts_ready"
            if ready
            else "runtime_account_safe_facts_blocked"
        ),
        "generated_at_utc": effective_generated_at_utc,
        "checks": {
            **checks,
            "account_safe_facts_ready": ready,
            "account_safe": ready,
            "account_capacity_base_safe": account_capacity_base_safe,
            "account_capacity_base_ready": account_capacity_base["ready"],
            # The Action-Time path is capacity-aware: a valid 1/2 account can
            # continue to exact NettingDomain checks in the Ticket transaction.
            # The flat-only account_safe_facts_ready remains a legacy broad
            # projection and must not veto a different-instrument second Ticket.
            "action_time_account_facts_ready": action_time_account_facts_ready,
            "private_action_time_facts_ready": ready,
            "active_position_or_open_order_clear": (
                checks["active_position_clear"] and checks["open_orders_clear"]
            ),
            "action_time_available_balance": (
                checks["account_balance_present"]
                and checks["account_balance_positive"]
                and checks["budget_available"]
            ),
        },
        "blockers": blockers,
        "account_mode": account_mode,
        "facts": {
            "active_position_or_open_order_clear": (
                checks["active_position_clear"] and checks["open_orders_clear"]
            ),
            "action_time_available_balance": (
                checks["account_balance_present"]
                and checks["account_balance_positive"]
                and checks["budget_available"]
            ),
            "total_wallet_balance": (
                str(total_wallet_balance) if total_wallet_balance is not None else None
            ),
            "available_balance": (
                str(available_balance) if available_balance is not None else None
            ),
            "exchange_max_leverage_by_symbol": dict(
                leverage_brackets.get("max_leverage_by_symbol") or {}
            ),
            "exchange_rules_ready": checks["exchange_rules_ready"],
            "protection_template_ready": checks["protection_template_ready"],
            "account_capacity_base_safe": account_capacity_base_safe,
            "account_capacity_base": account_capacity_base["values"],
            "account_capacity_source_snapshot_id": account_capacity_base["values"].get(
                "account_capacity_source_snapshot_id"
            ),
        },
        "source_status": live_facts.get("status"),
        "safety_invariants": {
            "signed_get_only": source_safety.get("signed_get_only") is True,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
            "order_created": False,
            "withdrawal_or_transfer_created": False,
            "credential_mutation_created": False,
        },
    }


def _account_capacity_base_fact(
    *,
    snapshot: dict[str, Any],
    account_mode: dict[str, Any],
    generated_at_utc: str,
) -> dict[str, Any]:
    """Derive the non-flat capacity fact from one full account snapshot only."""

    generated_at_ms = _iso_to_ms(generated_at_utc)
    observed_at_ms = _integer_or_none(snapshot.get("observed_at_ms"))
    valid_until_ms = _integer_or_none(snapshot.get("valid_until_ms"))
    account_id = str(snapshot.get("account_id") or "").strip()
    exchange_id = str(snapshot.get("exchange_id") or "").strip()
    runtime_profile_id = str(account_mode.get("runtime_profile_id") or "").strip()
    source_snapshot_id = str(snapshot.get("source_snapshot_id") or "").strip()
    position_mode = snapshot.get("position_mode")
    snapshot_fresh = (
        generated_at_ms is not None
        and observed_at_ms is not None
        and valid_until_ms is not None
        and observed_at_ms <= generated_at_ms + ACCOUNT_MODE_MAX_FUTURE_SKEW_MS
        and valid_until_ms > observed_at_ms
        and generated_at_ms <= valid_until_ms
        and source_snapshot_id != ""
    )
    identity_exact = (
        account_id != ""
        and account_id == str(account_mode.get("account_id") or "").strip()
        and exchange_id != ""
        and exchange_id == str(account_mode.get("exchange_id") or "").strip()
        and runtime_profile_id != ""
        and account_mode.get("position_mode_safe") is True
        and account_mode.get("account_mode") == position_mode
    )
    ready = (
        snapshot.get("snapshot_ready") is True
        and snapshot_fresh
        and identity_exact
        and snapshot.get("can_trade") is True
        and position_mode in {"one_way", "hedge"}
    )
    values = {
        "schema_version": "account_capacity_base.v1",
        "account_id": account_id or None,
        "exchange_id": exchange_id or None,
        "runtime_profile_id": runtime_profile_id or None,
        "account_capacity_source_snapshot_id": source_snapshot_id or None,
        "snapshot_complete": snapshot.get("snapshot_ready") is True,
        # The provider makes full-account collection fail closed.  Preserve its
        # typed reason through the account-capacity surface so the Action-Time
        # outcome names the failed exchange-read boundary instead of reporting
        # only a generic capacity fact.
        "failure_code": _snapshot_failure_code(snapshot),
        "can_trade": snapshot.get("can_trade") is True,
        "position_mode": position_mode if position_mode in {"one_way", "hedge"} else None,
        "total_wallet_balance": snapshot.get("total_wallet_balance"),
        "available_balance": snapshot.get("available_balance"),
        "exchange_total_initial_margin": snapshot.get("exchange_total_initial_margin"),
        "observed_at_ms": observed_at_ms,
        "valid_until_ms": valid_until_ms,
        "regular_open_order_count": len(snapshot.get("regular_open_orders") or []),
        "algo_open_order_count": len(snapshot.get("algo_open_orders") or []),
        "position_count": len(snapshot.get("positions") or []),
    }
    return {"ready": ready, "values": values}


def _action_time_account_fact_blocker(artifact: dict[str, Any]) -> str:
    """Return the capacity-owned blocker used before Invocation fact binding."""

    checks = _as_dict(artifact.get("checks"))
    facts = _as_dict(artifact.get("facts"))
    capacity = _as_dict(facts.get("account_capacity_base"))
    failure_code = _snapshot_failure_code(capacity)
    if failure_code:
        return f"account_capacity_base_fact_not_ready:{failure_code}"
    if checks.get("account_capacity_base_safe") is not True:
        return "account_capacity_base_fact_not_safe"
    if checks.get("account_capacity_base_ready") is not True:
        return "account_capacity_base_fact_not_ready"
    return "action_time_account_facts_not_satisfied"


def _snapshot_failure_code(values: dict[str, Any]) -> str | None:
    """Return a bounded provider failure identifier suitable for a blocker."""

    value = str(values.get("failure_code") or "").strip()
    if not value:
        return None
    return value if value.replace("_", "").isalnum() else None


def _integer_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _iso_to_ms(value: str) -> int | None:
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalized_account_mode_fact(
    value: dict[str, Any],
    *,
    generated_at_utc: str,
) -> dict[str, Any]:
    """Revalidate producer truth and discard unsafe authoritative mode values."""

    account_id = str(value.get("account_id") or "").strip()
    exchange_id = str(value.get("exchange_id") or "").strip()
    runtime_profile_id = str(value.get("runtime_profile_id") or "").strip()
    source = str(value.get("source") or "").strip()
    observed_at = str(value.get("observed_at") or "").strip()
    raw_dual_side_position = value.get("dual_side_position")
    raw_account_mode = str(value.get("account_mode") or "").strip()
    observed_ms = _iso_to_ms(observed_at)
    generated_ms = _iso_to_ms(generated_at_utc)
    expected_mode = (
        "hedge"
        if raw_dual_side_position is True
        else "one_way"
        if raw_dual_side_position is False
        else None
    )
    shape_valid = (
        type(raw_dual_side_position) is bool
        and raw_account_mode in {"one_way", "hedge"}
        and raw_account_mode == expected_mode
        and account_id != ""
        and exchange_id != ""
        and source == ACCOUNT_MODE_SOURCE
        and observed_ms is not None
        and generated_ms is not None
        and value.get("position_mode_safe") is True
    )
    fresh = (
        shape_valid
        and observed_ms <= generated_ms + ACCOUNT_MODE_MAX_FUTURE_SKEW_MS
        and generated_ms <= observed_ms + ACCOUNT_MODE_VALID_FOR_MS
    )
    if not value:
        status = "missing"
    elif shape_valid and not fresh:
        status = "stale"
    elif not shape_valid:
        status = "malformed"
    else:
        status = "fresh"
    result = {
        "status": status,
        "account_id": account_id or None,
        "exchange_id": exchange_id or None,
        "runtime_profile_id": runtime_profile_id or None,
        "account_mode": raw_account_mode if fresh else None,
        "dual_side_position": raw_dual_side_position if fresh else None,
        "position_mode_safe": bool(fresh),
        "observed_at": observed_at or None,
        "source": source or None,
    }
    if not fresh and expected_mode is not None:
        result["observed_account_mode"] = expected_mode
        result["observed_dual_side_position"] = raw_dual_side_position
    return result


def _iso_to_ms(value: str) -> int | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


def _json_object(value: Any) -> dict[str, Any]:
    while isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return dict(value) if isinstance(value, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
