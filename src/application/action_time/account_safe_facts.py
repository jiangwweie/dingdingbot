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
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from src.application.action_time.runtime_pg_fact_snapshots import (  # noqa: E402
    write_account_safe_fact_snapshots,
)
from collect_strategy_group_live_facts_readonly import (  # noqa: E402
    DEFAULT_BASE_URL,
    READ_ONLY_ENDPOINTS,
    UrlOpen,
    _account_summary,
    _budget_state,
    _env_value,
    _exchange_rules,
    _next_attempt_gate_state,
    _open_order_summary,
    _position_summary,
    _protection_state,
    _request_json,
)
DEFAULT_ENV_FILE = Path("/home/ubuntu/brc-deploy/env/live-readonly.env")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--allow-non-postgres-for-test", action="store_true")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--timeout-seconds", type=float, default=12)
    args = parser.parse_args(argv)

    if not args.database_url:
        print(
            "ERROR: PG_DATABASE_URL is required for DB-backed account-safe facts",
            file=sys.stderr,
        )
        return 2
    if not args.database_url.startswith(
        ("postgresql://", "postgresql+psycopg://")
    ) and not args.allow_non_postgres_for_test:
        print(
            "ERROR: DB-backed account-safe facts require PostgreSQL DSN",
            file=sys.stderr,
        )
        return 2

    engine = sa.create_engine(args.database_url)
    try:
        with engine.begin() as conn:
            live_facts = collect_account_safe_live_facts_from_pg_scope(
                conn,
                env_file=Path(args.env_file).expanduser() if args.env_file else None,
                base_url=args.base_url,
                timeout_seconds=args.timeout_seconds,
            )
            artifact = build_runtime_account_safe_facts(live_facts=live_facts)
            fact_snapshot_ids = write_account_safe_fact_snapshots(
                conn,
                artifact=artifact,
                source_ref="runtime_account_safe_pg_scope_readonly",
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
                "account_safe_facts_ready": artifact["checks"][
                    "account_safe_facts_ready"
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if artifact["checks"]["account_safe_facts_ready"] is True else 2


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
    errors: dict[str, str] = {}
    opener = urlopen if urlopen is not None else urllib.request.urlopen
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
    budget = _budget_state(account_payload=payloads["account"], handoff_summary=scope)
    protection = _protection_state(scope)
    next_attempt_gate = _next_attempt_gate_state(
        position=position,
        open_orders=open_orders,
    )
    return {
        "scope": "strategy_group_live_facts_input",
        "status": "ready" if not errors and symbols else "partial",
        "source": "pg_scope_binance_usdm_futures_readonly_get_endpoints",
        "source_mode": "pg_scope_direct_readonly_exchange",
        "supported_symbol_count": len(symbols),
        "exchange_rules": exchange_rules,
        "account": account,
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
    scope_rows = [
        dict(row)
        for row in conn.execute(
            sa.text(
                """
                SELECT DISTINCT
                  candidate.strategy_group_id,
                  candidate.symbol,
                  policy.max_notional
                FROM brc_strategy_group_candidate_scope AS candidate
                LEFT JOIN brc_owner_policy_current AS policy
                  ON policy.policy_current_id = candidate.policy_current_id
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
            )
        ).mappings()
    ]
    symbols = sorted({str(row.get("symbol") or "").upper() for row in scope_rows if row.get("symbol")})
    max_notional_values = [
        value
        for value in (_decimal_or_none(row.get("max_notional")) for row in scope_rows)
        if value is not None
    ]
    max_notional = max(max_notional_values, default=None)
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
        "max_notional_requirement_usdt": str(max_notional) if max_notional is not None else None,
        "has_candidate_specific_protection_template": int(protection_count or 0) > 0,
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
    account = _as_dict(live_facts.get("account"))
    active_position = _as_dict(live_facts.get("active_position"))
    open_orders = _as_dict(live_facts.get("open_orders"))
    budget = _as_dict(live_facts.get("budget"))
    exchange_rules = _as_dict(live_facts.get("exchange_rules"))
    next_attempt_gate = _as_dict(live_facts.get("next_attempt_gate"))
    protection = _as_dict(live_facts.get("protection"))
    source_safety = _as_dict(live_facts.get("safety_invariants"))

    checks = {
        "source_live_facts_ready": live_facts.get("status") == "ready",
        "account_balance_present": account.get("available_balance_present") is True,
        "account_balance_positive": account.get("available_balance_positive") is True,
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
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
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
        "facts": {
            "active_position_or_open_order_clear": (
                checks["active_position_clear"] and checks["open_orders_clear"]
            ),
            "action_time_available_balance": (
                checks["account_balance_present"]
                and checks["account_balance_positive"]
                and checks["budget_available"]
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


if __name__ == "__main__":
    raise SystemExit(main())
