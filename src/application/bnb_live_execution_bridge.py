"""BNB one-shot live execution bridge dry run.

This module verifies the path from PG-backed Owner live authorization to the
execution boundary. It never creates execution intents, orders, permissions,
runtime starts, or exchange writes.
"""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.owner_trial_flow import (
    OwnerTrialFlowError,
    OwnerTrialFlowService,
    SUPPORTED_OWNER_TRIAL_CARRIER_ID,
)
from src.application.strategy_trial_architecture_governance import (
    build_bnb_strategy_trial_architecture_governance,
)
from src.application.strategy_trial_preflight_facts import TrialPreflightFactsSnapshot
from src.infrastructure.database import get_pg_session_maker


BridgeStatus = Literal[
    "dry_run_reached_execution_boundary",
    "blocked_before_execution_boundary",
]


class BnbLiveExecutionBridgeDryRunRequest(BaseModel):
    carrier_id: str = SUPPORTED_OWNER_TRIAL_CARRIER_ID
    symbol: str = "BNB/USDT:USDT"
    side: Literal["long", "short"] = "long"
    max_notional: Decimal = Field(default=Decimal("20"), gt=Decimal("0"))
    quantity: Decimal = Field(default=Decimal("0.01"), gt=Decimal("0"))
    leverage: Decimal = Field(default=Decimal("1"), gt=Decimal("0"))
    protection_plan_type: Literal["single_tp_plus_sl"] = "single_tp_plus_sl"


class BnbLiveExecutionBridgeTableAudit(BaseModel):
    execution_intents: bool
    orders: bool
    brc_execution_results: bool
    expected_execution_intents_migration: str = "033"
    order_table_migration: str = "002"
    result_logging_migration: str = "017"
    correct_pg_database_checked: bool = True


class BnbLiveExecutionBridgeDryRunResponse(BaseModel):
    generated_from: Literal["bnb_live_execution_bridge_dry_run_v1"] = (
        "bnb_live_execution_bridge_dry_run_v1"
    )
    generated_at_ms: int
    carrier_id: str
    symbol: str
    side: Literal["long", "short"]
    bridge_status: BridgeStatus
    final_preflight_result: Literal["passed", "blocked"]
    hard_blockers: list[str] = Field(default_factory=list)
    authorization_hard_blockers_snapshot: list[str] = Field(default_factory=list)
    acknowledged_strategy_warnings: list[str] = Field(default_factory=list)
    strategy_warnings_block_execution: Literal[False] = False
    execution_boundary: dict[str, Any]
    table_audit: BnbLiveExecutionBridgeTableAudit
    environment_checks: dict[str, bool | str]
    preflight_fact_checks: dict[str, dict[str, Any]]
    non_permissions: dict[str, bool]
    dry_run_only: Literal[True] = True


class BnbLiveExecutionBridgeDryRunService:
    def __init__(
        self,
        *,
        owner_trial_flow_service: OwnerTrialFlowService,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._owner_trial_flow_service = owner_trial_flow_service
        self._session_maker = session_maker or get_pg_session_maker()
        self._env = env or os.environ

    async def run(
        self,
        request: BnbLiveExecutionBridgeDryRunRequest | None = None,
        *,
        fact_snapshot: TrialPreflightFactsSnapshot | None = None,
    ) -> BnbLiveExecutionBridgeDryRunResponse:
        request = request or BnbLiveExecutionBridgeDryRunRequest()
        hard_blockers: list[str] = []
        authorization_hard_blockers_snapshot: list[str] = []
        carrier = build_bnb_strategy_trial_architecture_governance().owner_review_packet.carrier
        try:
            current = await self._owner_trial_flow_service.current(carrier_id=request.carrier_id)
        except OwnerTrialFlowError as exc:
            hard_blockers.append(exc.code)
            current = None

        if request.carrier_id != SUPPORTED_OWNER_TRIAL_CARRIER_ID:
            hard_blockers.append("unsupported_carrier")
        if request.symbol not in {carrier.symbol, carrier.runtime_symbol}:
            hard_blockers.append("symbol_mismatch")
        if request.side != carrier.side:
            hard_blockers.append("side_mismatch")
        if request.max_notional != carrier.max_notional:
            hard_blockers.append("cap_mismatch")
        if request.quantity != carrier.quantity:
            hard_blockers.append("quantity_mismatch")
        if request.leverage != carrier.leverage:
            hard_blockers.append("leverage_mismatch")
        if request.protection_plan_type != carrier.protection_plan_type:
            hard_blockers.append("protection_plan_mismatch")

        authorization = current.live_authorization if current is not None else None
        if authorization is None:
            hard_blockers.append("missing_explicit_owner_live_authorization")
        else:
            if authorization.carrier_id != request.carrier_id:
                hard_blockers.append("authorization_carrier_mismatch")
            if authorization.symbol not in {request.symbol, carrier.symbol, carrier.runtime_symbol}:
                hard_blockers.append("authorization_symbol_mismatch")
            if authorization.side != request.side:
                hard_blockers.append("authorization_side_mismatch")
            if authorization.max_notional != request.max_notional:
                hard_blockers.append("authorization_cap_mismatch")
            if authorization.quantity != request.quantity:
                hard_blockers.append("authorization_quantity_mismatch")
            if authorization.leverage != request.leverage:
                hard_blockers.append("authorization_leverage_mismatch")
            if authorization.protection_plan_type != request.protection_plan_type:
                hard_blockers.append("authorization_protection_plan_mismatch")
            if not authorization.single_use:
                hard_blockers.append("authorization_not_single_use")
            if authorization.consumed:
                hard_blockers.append("authorization_already_consumed")
            if authorization.execution_intent_created or authorization.order_created:
                hard_blockers.append("authorization_already_executed")
            if (
                authorization.live_ready
                or authorization.order_permission_granted
                or authorization.execution_permission_granted
                or authorization.auto_execution_enabled
            ):
                hard_blockers.append("authorization_contains_executable_state")
            authorization_hard_blockers_snapshot = list(authorization.hard_blockers)

        if current is not None and current.unacknowledged_warnings:
            hard_blockers.append("strategy_warning_acknowledgement_incomplete")

        environment_checks = _environment_checks(self._env)
        hard_blockers.extend(
            code for code, ok in environment_checks.items() if isinstance(ok, bool) and not ok
        )

        fact_checks = _fact_checks(fact_snapshot)
        for fact in fact_checks.values():
            hard_blockers.extend(str(code) for code in fact.get("blockers", []))
        hard_blockers.extend(_fact_gate_blockers(fact_checks))

        table_audit = await self._audit_tables()
        if not table_audit.execution_intents:
            hard_blockers.append("execution_intents_table_missing")
        if not table_audit.orders:
            hard_blockers.append("orders_table_missing")
        if not table_audit.brc_execution_results:
            hard_blockers.append("result_logging_table_missing")

        hard_blockers = _dedupe(hard_blockers)
        order_result_logging_available = table_audit.orders and table_audit.brc_execution_results
        protection_executable = request.protection_plan_type == carrier.protection_plan_type
        exit_cleanup_available = order_result_logging_available and protection_executable
        bridge_status: BridgeStatus = (
            "blocked_before_execution_boundary"
            if hard_blockers
            else "dry_run_reached_execution_boundary"
        )
        return BnbLiveExecutionBridgeDryRunResponse(
            generated_at_ms=int(time.time() * 1000),
            carrier_id=request.carrier_id,
            symbol=request.symbol,
            side=request.side,
            bridge_status=bridge_status,
            final_preflight_result="blocked" if hard_blockers else "passed",
            hard_blockers=hard_blockers,
            authorization_hard_blockers_snapshot=authorization_hard_blockers_snapshot,
            acknowledged_strategy_warnings=(
                current.acknowledged_warnings if current is not None else []
            ),
            execution_boundary={
                "would_create_execution_intent_if_all_gates_passed": False,
                "would_create_order": False,
                "order_path_enabled": False,
                "protection_executable": protection_executable,
                "exit_cleanup_available": exit_cleanup_available,
                "order_result_logging_available": order_result_logging_available,
                "boundary": "dry_run_preview_only",
                "reason": "This task verifies gates only; executable intent/order creation remains disabled.",
            },
            table_audit=table_audit,
            environment_checks=environment_checks,
            preflight_fact_checks=fact_checks,
            non_permissions={
                "live_ready": False,
                "execution_permission_granted": False,
                "order_permission_granted": False,
                "execution_intent_created": False,
                "order_created": False,
                "runtime_started": False,
                "exchange_write_api_called": False,
            },
        )

    async def _audit_tables(self) -> BnbLiveExecutionBridgeTableAudit:
        async with self._session_maker() as session:
            bind = session.get_bind()
            dialect_name = bind.dialect.name if bind is not None else ""
            if dialect_name == "sqlite":
                names = await session.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name IN "
                        "('execution_intents', 'orders', 'brc_execution_results')"
                    )
                )
                existing = set(names.scalars().all())
            else:
                existing = set()
                for table_name in ["execution_intents", "orders", "brc_execution_results"]:
                    result = await session.execute(
                        text("SELECT to_regclass(:name)"),
                        {"name": f"public.{table_name}"},
                    )
                    if result.scalar() is not None:
                        existing.add(table_name)
        return BnbLiveExecutionBridgeTableAudit(
            execution_intents="execution_intents" in existing,
            orders="orders" in existing,
            brc_execution_results="brc_execution_results" in existing,
        )


def _environment_checks(env: Mapping[str, str]) -> dict[str, bool | str]:
    trading_env = str(env.get("TRADING_ENV", "")).lower()
    exchange_testnet = str(env.get("EXCHANGE_TESTNET", "")).lower()
    runtime_control = str(env.get("RUNTIME_CONTROL_API_ENABLED", "false")).lower()
    test_injection = str(env.get("RUNTIME_TEST_SIGNAL_INJECTION_ENABLED", "false")).lower()
    permission_max = str(env.get("BRC_EXECUTION_PERMISSION_MAX", "read_only")).lower()
    return {
        "live_environment_valid": trading_env == "live",
        "exchange_testnet_false": exchange_testnet == "false",
        "runtime_control_disabled": runtime_control not in {"1", "true", "yes", "on"},
        "test_signal_injection_disabled": test_injection not in {"1", "true", "yes", "on"},
        "global_permission_not_order_allowed": permission_max != "order_allowed",
        "global_permission_not_execution_intent_allowed": permission_max != "execution_intent_allowed",
        "TRADING_ENV": trading_env or "unset",
        "EXCHANGE_TESTNET": exchange_testnet or "unset",
        "BRC_EXECUTION_PERMISSION_MAX": permission_max or "unset",
    }


def _fact_checks(
    snapshot: TrialPreflightFactsSnapshot | None,
) -> dict[str, dict[str, Any]]:
    if snapshot is None:
        return {
            "preflight_facts": {
                "status": "unavailable",
                "blocking": True,
                "blockers": ["preflight_facts_unavailable"],
            }
        }
    checks: dict[str, dict[str, Any]] = {}
    for fact in snapshot.facts:
        checks[fact.fact_id] = {
            "status": fact.status,
            "blocking": fact.blocking,
            "blocker": fact.blocker,
            "blockers": fact.blockers or ([fact.blocker] if fact.blocker else []),
            "source": fact.source,
            "evidence": fact.evidence,
        }
    return checks


def _fact_gate_blockers(fact_checks: dict[str, dict[str, Any]]) -> list[str]:
    if "preflight_facts" in fact_checks:
        return []

    blockers: list[str] = []
    required_facts = ["active_position", "open_order", "gks", "startup_guard", "account_facts"]
    for fact_id in required_facts:
        if fact_id not in fact_checks:
            blockers.append(f"{fact_id}_fact_missing")

    active_position = fact_checks.get("active_position")
    if active_position is not None:
        blockers.extend(_status_blockers(active_position, "active_position"))
        count = _int_evidence(active_position, "active_position_count")
        if count is not None and count > 0:
            blockers.append("active_position_conflict")

    open_order = fact_checks.get("open_order")
    if open_order is not None:
        blockers.extend(_status_blockers(open_order, "open_order"))
        count = _int_evidence(open_order, "open_order_count")
        if count is not None and count > 0:
            blockers.append("open_order_conflict")

    gks = fact_checks.get("gks")
    if gks is not None:
        blockers.extend(_status_blockers(gks, "gks"))
        if _bool_evidence(gks, "active") is True:
            blockers.append("gks_active")

    startup_guard = fact_checks.get("startup_guard")
    if startup_guard is not None:
        blockers.extend(_status_blockers(startup_guard, "startup_guard"))

    account_facts = fact_checks.get("account_facts")
    if account_facts is not None:
        blockers.extend(_status_blockers(account_facts, "account_facts"))
        evidence = account_facts.get("evidence") or {}
        if evidence.get("freshness") != "fresh":
            blockers.append("account_facts_not_fresh")
        if evidence.get("read_only_guarantee") is not True:
            blockers.append("account_facts_read_only_unverified")

    return blockers


def _status_blockers(fact: dict[str, Any], fact_id: str) -> list[str]:
    if fact.get("status") == "clear":
        return []
    if fact.get("blockers"):
        return []
    status = str(fact.get("status") or "unknown")
    return [f"{fact_id}_status_{status}"]


def _int_evidence(fact: dict[str, Any], key: str) -> int | None:
    evidence = fact.get("evidence") or {}
    value = evidence.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_evidence(fact: dict[str, Any], key: str) -> bool | None:
    evidence = fact.get("evidence") or {}
    value = evidence.get(key)
    return value if isinstance(value, bool) else None


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
