#!/usr/bin/env python3
"""Build read-only account-safe facts from PG scope and signed GET facts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import sys
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
        with engine.begin() as conn:
            live_facts = collect_account_safe_live_facts_from_pg_scope(
                conn,
                env_file=Path(args.env_file).expanduser() if args.env_file else None,
                base_url=args.base_url,
                timeout_seconds=args.timeout_seconds,
            )
            artifact = build_runtime_account_safe_facts(live_facts=live_facts)
            account_safe_ready = (
                artifact["checks"]["account_safe_facts_ready"] is True
            )
            business_blocker = None
            fact_binding_invocation_id = args.action_time_invocation_id
            if args.action_time_invocation_id and not account_safe_ready:
                business_blocker = str(
                    (artifact.get("blockers") or [
                        "action_time_account_safe_facts_not_satisfied"
                    ])[0]
                )
                # Persist the fail-closed facts, but never bind an unsatisfied
                # fact set into the action-time invocation.
                fact_binding_invocation_id = None
            fact_snapshot_ids = write_account_safe_fact_snapshots(
                conn,
                artifact=artifact,
                source_ref="runtime_account_safe_pg_scope_readonly",
                action_time_invocation_id=fact_binding_invocation_id,
            )
    finally:
        engine.dispose()
    artifact["source_mode"] = "db_backed"
    artifact["projection_target"] = "production_current"
    artifact["collector_source_mode"] = "pg_scope_direct_readonly_exchange"
    artifact["pg_fact_snapshot_ids"] = fact_snapshot_ids
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "account_safe_facts_ready": account_safe_ready,
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
            account_safe_ready
            or business_blocker is not None
            or args.allow_blocked_current_projection
        )
        else 2
    )


def collect_account_safe_live_facts_from_pg_scope(
    conn: sa.engine.Connection,
    *,
    env_file: Path | None,
    base_url: str = DEFAULT_BASE_URL,
    timeout_seconds: float = 12,
    urlopen: UrlOpen | None = None,
) -> dict[str, Any]:
    scope = _pg_account_safe_scope_summary(conn)
    symbols = list(scope["symbols"])
    api_key = _env_value(
        ("EXCHANGE_API_KEY", "BINANCE_API_KEY", "binance_exchange_key"),
        env_file=env_file,
    )
    api_secret = _env_value(
        ("EXCHANGE_API_SECRET", "BINANCE_SECRET_KEY", "binance_exchange_secret"),
        env_file=env_file,
    )
    payloads: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {
        "scope_identity": ",".join(scope["identity_errors"])
        for _ in [0]
        if scope["identity_errors"]
    }
    opener = urlopen if urlopen is not None else urllib.request.urlopen
    collected_at_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    for name, (_method, path, signed) in READ_ONLY_ENDPOINTS.items():
        try:
            payloads[name] = _request_json(
                base_url=base_url,
                path=path,
                api_key=api_key,
                api_secret=api_secret,
                signed=signed,
                timeout_seconds=timeout_seconds,
                urlopen=opener,
            )
        except Exception as exc:
            errors[name] = f"{type(exc).__name__}:{str(exc)[:220]}"
            payloads[name] = {}

    exchange_rules = _exchange_rules(payloads["exchange_info"], symbols)
    position = _position_summary(payloads["position_risk"], symbols)
    open_orders = _open_order_summary(payloads["open_orders"], symbols)
    account = _account_summary(payloads["account"])
    leverage_brackets = _leverage_bracket_summary(
        payloads["leverage_brackets"], symbols
    )
    account_mode = _account_mode_summary(
        payloads["account_mode"],
        account_id=scope.get("account_id"),
        exchange_id=scope.get("exchange_id"),
        runtime_profile_id=scope.get("runtime_profile_id"),
        collected_at_ms=collected_at_ms,
    )
    budget = _budget_state(account_payload=payloads["account"], handoff_summary=scope)
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
