#!/usr/bin/env python3
"""Build read-only account-safe facts from StrategyGroup live facts input."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from typing import Any

import sqlalchemy as sa


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from runtime_pg_fact_snapshots import write_account_safe_fact_snapshots  # noqa: E402


DEFAULT_LIVE_FACTS_JSON = Path(
    "/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/strategy-group-live-facts-input.json"
)
DEFAULT_OUTPUT_JSON = Path(
    "/home/ubuntu/brc-deploy/reports/runtime-monitor/latest-account-safe-facts.json"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-facts-json", default=str(DEFAULT_LIVE_FACTS_JSON))
    parser.add_argument("--database-url", default=os.getenv("PG_DATABASE_URL", ""))
    parser.add_argument("--require-database-url", action="store_true")
    parser.add_argument("--allow-non-postgres-for-test", action="store_true")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
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

    artifact = build_runtime_account_safe_facts(
        live_facts=_read_json(Path(args.live_facts_json)),
    )
    engine = sa.create_engine(args.database_url)
    try:
        with engine.begin() as conn:
            fact_snapshot_ids = write_account_safe_fact_snapshots(
                conn,
                artifact=artifact,
                source_ref="runtime_live_facts_readonly",
            )
    finally:
        engine.dispose()
    artifact["source_mode"] = "db_backed"
    artifact["projection_target"] = "production_current"
    artifact["pg_fact_snapshot_ids"] = fact_snapshot_ids
    output_json = Path(args.output_json)
    _write_json(output_json, artifact)
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "account_safe_facts_ready": artifact["checks"][
                    "account_safe_facts_ready"
                ],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if artifact["checks"]["account_safe_facts_ready"] is True else 2


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


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
