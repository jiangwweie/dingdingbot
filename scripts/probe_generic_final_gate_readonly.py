#!/usr/bin/env python3
"""Probe GenericActionSpec final gate with live/read-only guards.

Default behavior is DRY-RUN. The script only reads PG/exchange facts when
RUN_GENERIC_FINAL_GATE_PROBE=true and all live/read-only environment guards
pass. It never creates authorizations, execution intents, orders, runtime
transitions, or exchange writes.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Mapping

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.application.bnb_live_execution_boundary import BnbLiveExecutionBoundaryDryRunService
from src.application.owner_action_carrier_catalog import (
    TREND_OWNER_ACTION_CARRIER_ID,
    get_owner_action_carrier,
)
from src.application.production_strategy_family_admission import GenericActionSpec
from src.interfaces import api_brc_console


RUN_ENV = "RUN_GENERIC_FINAL_GATE_PROBE"
DEFAULT_CARRIER_ID = TREND_OWNER_ACTION_CARRIER_ID
PROBE_GUARD_ENV_KEYS = (
    "TRADING_ENV",
    "EXCHANGE_TESTNET",
    "BRC_EXECUTION_PERMISSION_MAX",
    "RUNTIME_CONTROL_API_ENABLED",
    "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED",
    "CORE_EXECUTION_INTENT_BACKEND",
    "CORE_ORDER_BACKEND",
    "CORE_POSITION_BACKEND",
    "PG_DATABASE_URL",
    "EXCHANGE_NAME",
    "EXCHANGE_API_KEY",
    "EXCHANGE_API_SECRET",
)


def _bool_env(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_value(env: Mapping[str, str], name: str, default: str = "") -> str:
    return str(env.get(name, default)).strip()


def guard_probe_environment(env: Mapping[str, str]) -> None:
    expected = {
        "TRADING_ENV": "live",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "read_only",
        "RUNTIME_CONTROL_API_ENABLED": "false",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
        "CORE_EXECUTION_INTENT_BACKEND": "postgres",
        "CORE_ORDER_BACKEND": "postgres",
        "CORE_POSITION_BACKEND": "postgres",
    }
    failures: list[str] = []
    for name, expected_value in expected.items():
        actual = _env_value(env, name).lower()
        if actual != expected_value:
            failures.append(f"{name}={env.get(name)!r}, expected {expected_value!r}")
    if not _env_value(env, "PG_DATABASE_URL"):
        failures.append("PG_DATABASE_URL is required")
    if _env_value(env, "RUNTIME_CONTROL_API_ENABLED").lower() in {"1", "true", "yes", "on"}:
        failures.append("runtime control API must remain disabled")
    if failures:
        raise ValueError("unsafe generic final-gate probe environment: " + "; ".join(failures))


def snapshot_probe_environment(env: Mapping[str, str]) -> dict[str, str]:
    return {key: _env_value(env, key) for key in PROBE_GUARD_ENV_KEYS if _env_value(env, key)}


def restore_probe_environment(snapshot: Mapping[str, str]) -> None:
    os.environ.update(snapshot)
    guard_probe_environment(os.environ)


def build_probe_plan(env: Mapping[str, str]) -> dict:
    carrier_id = _env_value(env, "GENERIC_FINAL_GATE_CARRIER_ID", DEFAULT_CARRIER_ID)
    return {
        "mode": "run" if _bool_env(env.get(RUN_ENV)) else "dry_run",
        "carrier_id": carrier_id,
        "path": "GenericActionSpec -> read-only facts -> FinalGate",
        "required_env": {
            "TRADING_ENV": "live",
            "EXCHANGE_TESTNET": "false",
            "BRC_EXECUTION_PERMISSION_MAX": "read_only",
            "RUNTIME_CONTROL_API_ENABLED": "false",
            "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
            "CORE_EXECUTION_INTENT_BACKEND": "postgres",
            "CORE_ORDER_BACKEND": "postgres",
            "CORE_POSITION_BACKEND": "postgres",
            "PG_DATABASE_URL": "set",
        },
        "safety": {
            "creates_authorization": False,
            "creates_execution_intent": False,
            "places_order": False,
            "starts_runtime": False,
            "exchange_write_methods_called": False,
            "default_is_dry_run": True,
        },
    }


def probe_guard_blocker(error: ValueError) -> dict:
    return {
        "result": "blocked",
        "stage": "probe_environment_guard",
        "blockers": ["unsafe_generic_final_gate_probe_environment"],
        "message": str(error),
        "safety": {
            "creates_authorization": False,
            "creates_execution_intent": False,
            "places_order": False,
            "starts_runtime": False,
            "exchange_write_methods_called": False,
        },
    }


def action_spec_for_carrier(carrier_id: str) -> GenericActionSpec:
    carrier = get_owner_action_carrier(carrier_id)
    if carrier is None:
        return GenericActionSpec(
            family=carrier_id,
            strategy_family_id=carrier_id,
            carrier_id=carrier_id,
            admission_level="L0",
            status="invalid_blocked",
            action_registry_supported=False,
            hard_blockers=["unsupported_carrier"],
        )
    return GenericActionSpec(
        family=carrier.strategy_family,
        strategy_family_id=carrier.strategy_id,
        carrier_id=carrier.carrier_id,
        admission_level="L3",
        status="valid_blocked_final_gate",
        action_registry_supported=True,
        symbol=carrier.runtime_symbol,
        side=carrier.side,
        quantity=str(carrier.quantity),
        max_notional=str(carrier.max_notional),
        leverage=str(carrier.leverage),
        max_attempts=1,
        protection_mode=carrier.protection_plan_type,
        review_requirement="post_action_review_required",
        hard_blockers=[],
        action_entry_payload_ref=f"action-entry:{carrier.carrier_id}",
    )


async def run_probe(env: Mapping[str, str]) -> dict:
    guard_probe_environment(env)
    env_snapshot = snapshot_probe_environment(env)
    carrier_id = _env_value(env, "GENERIC_FINAL_GATE_CARRIER_ID", DEFAULT_CARRIER_ID)
    action_spec = action_spec_for_carrier(carrier_id)
    api_module = api_brc_console._api_module()
    restore_probe_environment(env_snapshot)
    gateway_binding = await api_brc_console._owner_bounded_exchange_gateway_binding(api_module)
    gateway = gateway_binding.get("gateway")
    try:
        profile = api_brc_console._strategy_profile_for_owner_action_scope(
            carrier_id=str(action_spec.carrier_id or carrier_id),
            symbol=str(action_spec.symbol or ""),
            side=str(action_spec.side or "long"),
        )
        owner_trial_service = api_brc_console._owner_trial_flow_service_instance()
        session_maker = getattr(
            getattr(owner_trial_service, "_repository", None),
            "_session_maker",
            None,
        )
        collector = api_brc_console._strategy_trial_preflight_fact_collector(
            api_module,
            session_maker=session_maker,
        )
        fact_snapshot = await collector.collect(profile)
        service = BnbLiveExecutionBoundaryDryRunService(
            owner_trial_flow_service=owner_trial_service,
            session_maker=session_maker,
        )
        final_gate = await service.run_action_spec(action_spec, fact_snapshot=fact_snapshot)
        facts = fact_snapshot.fact_map()
        return {
            "result": final_gate.final_preflight_result,
            "carrier_id": carrier_id,
            "gateway_binding": {
                "status": gateway_binding.get("status"),
                "blockers": gateway_binding.get("blockers", []),
                "gateway_type": gateway_binding.get("gateway_type"),
            },
            "fact_status": {
                fact_id: {
                    "status": fact.status,
                    "source": fact.source,
                    "blockers": fact.blockers or ([fact.blocker] if fact.blocker else []),
                }
                for fact_id, fact in facts.items()
            },
            "final_gate": {
                "projection_status": final_gate.projection_status,
                "hard_blockers": final_gate.hard_blockers,
                "owner_trigger_visible": final_gate.owner_execution_trigger.visible,
                "owner_trigger_enabled": final_gate.owner_execution_trigger.enabled,
                "execution_intent_created": final_gate.non_permissions["execution_intent_created"],
                "order_created": final_gate.non_permissions["order_created"],
                "runtime_started": final_gate.non_permissions["runtime_started"],
                "exchange_write_api_called": final_gate.non_permissions["exchange_write_api_called"],
            },
        }
    finally:
        close = getattr(gateway, "close", None)
        if callable(close):
            maybe = close()
            if asyncio.iscoroutine(maybe):
                await maybe
        if hasattr(api_module, "_owner_bounded_exchange_gateway"):
            setattr(api_module, "_owner_bounded_exchange_gateway", None)


async def main() -> int:
    plan = build_probe_plan(os.environ)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if not _bool_env(os.getenv(RUN_ENV)):
        print()
        print("DRY RUN - no PG/exchange reads performed.")
        print(f"Set {RUN_ENV}=true only for a live/read-only evidence probe.")
        return 0
    try:
        result = await run_probe(os.environ)
    except ValueError as exc:
        print(json.dumps(probe_guard_blocker(exc), ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
