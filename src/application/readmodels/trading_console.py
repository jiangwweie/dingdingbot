"""Trading Console aggregation and Owner action-entry read models.

This module composes existing repositories and runtime adapters into frontend
responses. This namespace intentionally has no mutation methods and never calls
exchange write APIs; product actions are surfaced as official Operation Layer /
FinalGate handoffs.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.application.budget_recommendation import (
    apply_budget_envelope_to_action_candidates,
    apply_budget_envelope_to_generic_action_specs,
    build_budget_recommendation,
)
from src.application.budgeted_autonomy import (
    BudgetedAutonomyAuthorization,
    BudgetedAutonomyCandidateInput,
    BudgetedAutonomyPositionEvidence,
    evaluate_budgeted_autonomy_loop,
)
from src.application.budgeted_autonomy_v01 import (
    BudgetedAutonomyDailyState,
    evaluate_budgeted_autonomy_v01,
)
from src.application.candidate_action_product_loop import (
    build_candidate_action_product_loop,
)
from src.application.notional_sizing import (
    ContractMarketRules,
    compute_notional_sizing,
    validate_fixed_quantity_scope,
)
from src.domain.owner_capital_adjustment import (
    OwnerCapitalAdjustmentRecord,
    OwnerCapitalBaseReviewInput,
    review_owner_capital_base_movement,
)
from src.domain.owner_capital_baseline_snapshot import OwnerCapitalBaselineSnapshot
from src.domain.live_lifecycle_review import BrcLiveLifecycleReviewRecord
from src.domain.right_tail_review import (
    RightTailTradePathFacts,
    summarize_right_tail_reviews,
)
from src.domain.runtime_semantic_review_packet import (
    summarize_runtime_semantic_review_packets,
)
from src.application.owner_action_carrier_catalog import owner_action_carrier_id_for_symbol
from src.application.production_strategy_family_admission import (
    build_production_strategy_family_admission_state,
)
from scripts.build_strategy_group_handoff_intake_packet import (
    DEFAULT_HANDOFF_DIR as DEFAULT_STRATEGY_GROUP_HANDOFF_DIR,
    DEFAULT_SOURCE_BRANCH as DEFAULT_STRATEGY_GROUP_HANDOFF_BRANCH,
    DEFAULT_SOURCE_COMMIT as DEFAULT_STRATEGY_GROUP_HANDOFF_COMMIT,
    DEFAULT_SOURCE_REPO as DEFAULT_STRATEGY_GROUP_HANDOFF_REPO,
    build_packet as build_strategy_group_handoff_intake_packet,
)
from scripts.build_strategy_group_live_facts_readiness_packet import (
    build_packet as build_strategy_group_live_facts_readiness_packet,
)
from scripts.build_strategygroup_runtime_pilot_status import (
    build_packet as build_strategygroup_runtime_pilot_status_packet,
)


DEFAULT_SYMBOL = "BNB/USDT:USDT"
DEFAULT_CARRIER_ID = "MI-001-BNB-LONG"
DEFAULT_STRATEGY_FAMILY_ID = "MI-001"
DEFAULT_SIGNAL_WATCHER_REPORT_DIR = "/home/ubuntu/brc-deploy/reports/runtime-signal-watcher"
DEFAULT_STRATEGY_GROUP_REPORT_DIR = "/home/ubuntu/brc-deploy/reports/strategygroup-runtime-pilot"
DEFAULT_STRATEGY_GROUP_HANDOFF_PACKET_PATH = (
    "/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/"
    "strategy-group-handoff-intake-packet.json"
)
DEFAULT_STRATEGY_GROUP_LIVE_FACTS_PATH = (
    "/home/ubuntu/brc-deploy/reports/runtime-signal-watcher/"
    "strategy-group-live-facts-input.json"
)
DEFAULT_STRATEGY_GROUP_HANDOFF_PACKET_GLOB = "strategy-group-handoff-intake-*.json"
DEFAULT_STRATEGY_GROUP_LIVE_FACTS_GLOB = "strategy-group-live-facts-readonly-*.json"
EXCHANGE_READ_TIMEOUT_SECONDS = 8.0
OPEN_ORDER_STATUSES = {"OPEN", "PARTIALLY_FILLED", "open", "partially_filled"}
PROTECTION_ROLES = {"SL", "TP1", "TP2", "TP3", "TP4", "TP5"}
TERMINAL_INTENT_STATUSES = {"blocked", "failed", "completed"}
SIGNAL_WATCHER_RESUME_READY_STATUSES = {
    "runtime_signal_ready_for_non_executing_prepare",
    "prepared_shadow_evidence_ready_for_owner_review",
}
SIGNAL_WATCHER_UNSAFE_FLAGS = {
    "exchange_write_called",
    "order_created",
    "order_lifecycle_called",
    "execution_intent_created",
    "runtime_budget_mutated",
    "withdrawal_or_transfer_created",
}


def _runtime_signal_watcher_owner_state(
    *,
    post_signal_auto_resume: dict[str, Any],
    readiness_status: str,
    missing: list[str],
    stale: bool,
    unsafe_flags: list[str],
    can_resume_steps_5_8: bool,
) -> dict[str, Any]:
    """Translate watcher packet fields into an Owner-facing recovery summary."""

    if unsafe_flags:
        blocked_at = "watcher_safety_invariants"
        blocked_reason = "watcher_evidence_contains_forbidden_effect_flags"
        automatic_recovery_action = "stop_resume_path_and_investigate_watcher_evidence"
        state = {
            "status": "blocked_hard_safety_stop",
            "blocker_class": "hard_safety_stop",
            "blocked_at": blocked_at,
            "blocked_reason": blocked_reason,
            "next_recover_condition": "forbidden_effect_flags_are_absent_in_current_evidence",
            "automatic_recovery_action": automatic_recovery_action,
            "downgrade_mode": "manual_review_only",
        }
    elif missing:
        blocked_at = "runtime_signal_watcher_evidence"
        blocked_reason = "watcher_evidence_missing"
        automatic_recovery_action = "run_or_wait_for_next_watcher_tick_and_rebuild_readiness_pack"
        state = {
            "status": "blocked_deployment_issue",
            "blocker_class": "deployment_issue",
            "blocked_at": blocked_at,
            "blocked_reason": blocked_reason,
            "next_recover_condition": "watcher_evidence_files_are_present",
            "automatic_recovery_action": automatic_recovery_action,
            "downgrade_mode": "observe_only_no_candidate_prepare",
        }
    elif stale:
        blocked_at = "runtime_signal_watcher_evidence"
        blocked_reason = "watcher_evidence_stale"
        automatic_recovery_action = "run_or_wait_for_next_watcher_tick_and_rebuild_readiness_pack"
        state = {
            "status": "blocked_deployment_issue",
            "blocker_class": "deployment_issue",
            "blocked_at": blocked_at,
            "blocked_reason": blocked_reason,
            "next_recover_condition": "watcher_evidence_files_are_fresh",
            "automatic_recovery_action": automatic_recovery_action,
            "downgrade_mode": "observe_only_no_candidate_prepare",
        }
    else:
        status = str(post_signal_auto_resume.get("status") or "")
        if not status:
            status = "ready" if readiness_status == "ready" else readiness_status
        blocked_at = str(
            post_signal_auto_resume.get("blocked_at")
            or ("none" if can_resume_steps_5_8 else "watcher_signal")
        )
        blocked_reason = str(
            post_signal_auto_resume.get("blocked_reason")
            or ("none" if can_resume_steps_5_8 else "no_fresh_strategy_signal")
        )
        automatic_recovery_action = str(
            post_signal_auto_resume.get("automatic_recovery_action")
            or (
                "continue_to_non_executing_prepare"
                if can_resume_steps_5_8
                else "continue_watcher_observation"
            )
        )
        blocker_class = "none"
        if blocked_reason != "none":
            blocker_class = (
                "waiting_for_market"
                if blocked_reason == "no_fresh_strategy_signal"
                else "review_only_warning"
            )
        state = {
            "status": status,
            "blocker_class": blocker_class,
            "blocked_at": blocked_at,
            "blocked_reason": blocked_reason,
            "next_recover_condition": str(
                post_signal_auto_resume.get("next_recover_condition")
                or (
                    "fresh_signal_already_available"
                    if can_resume_steps_5_8
                    else "runtime_signal_watcher_observes_a_fresh_signal_for_selected_scope"
                )
            ),
            "automatic_recovery_action": automatic_recovery_action,
            "downgrade_mode": str(
                post_signal_auto_resume.get("downgrade_mode")
                or ("armed_observation" if can_resume_steps_5_8 else "observe_only")
            ),
        }

    why_not_executable: list[str] = []
    if state["blocked_reason"] != "none":
        why_not_executable.append(str(state["blocked_reason"]))
    if unsafe_flags:
        why_not_executable.extend(f"forbidden_effect:{flag}" for flag in unsafe_flags)
    if missing:
        why_not_executable.append("watcher_evidence_missing:" + ",".join(missing))
    if stale:
        why_not_executable.append("watcher_evidence_stale")

    return {
        **state,
        "can_continue_without_owner_chat": bool(
            post_signal_auto_resume.get("can_continue_without_owner_chat")
        )
        or can_resume_steps_5_8,
        "requires_action_time_final_gate": bool(
            post_signal_auto_resume.get("requires_action_time_final_gate")
        ),
        "requires_official_operation_layer": bool(
            post_signal_auto_resume.get("requires_official_operation_layer")
        ),
        "why_not_executable": list(dict.fromkeys(why_not_executable)),
    }


def _runtime_signal_watcher_action_time_resume(
    *,
    resume_pack: dict[str, Any],
    post_signal_auto_resume: dict[str, Any],
    can_resume_steps_5_8: bool,
) -> dict[str, Any]:
    existing = resume_pack.get("action_time_resume")
    if isinstance(existing, dict) and existing:
        return existing

    if can_resume_steps_5_8 or post_signal_auto_resume.get("prepared_authorization_id"):
        status = "ready_for_action_time_final_gate"
        next_step = "run_official_action_time_final_gate_preflight"
        allowed_auto_actions = ["run_official_action_time_final_gate_preflight"]
        requires_fresh_action_time_facts = True
        final_gate_status = "not_run"
    elif post_signal_auto_resume.get("status") == "waiting_for_market":
        status = "waiting_for_market"
        next_step = "continue_watcher_observation"
        allowed_auto_actions = ["continue_watcher_observation"]
        requires_fresh_action_time_facts = False
        final_gate_status = "not_reached"
    else:
        status = "blocked"
        next_step = "resolve_watcher_resume_blockers"
        allowed_auto_actions = []
        requires_fresh_action_time_facts = False
        final_gate_status = "not_reached"

    return {
        "status": status,
        "next_step": next_step,
        "signal_input_json": resume_pack.get("signal_input_json"),
        "shadow_candidate_id": resume_pack.get("shadow_candidate_id"),
        "prepared_authorization_id": resume_pack.get("prepared_authorization_id"),
        "allowed_auto_actions": allowed_auto_actions,
        "forbidden_auto_actions_until_final_gate_pass": [
            "official_operation_layer_submit",
            "exchange_order",
            "order_lifecycle_submit",
            "runtime_budget_mutation",
        ],
        "requires_fresh_action_time_facts": requires_fresh_action_time_facts,
        "requires_action_time_final_gate": True,
        "requires_official_operation_layer": True,
        "final_gate_status": final_gate_status,
        "operation_layer_status": "not_reached",
        "places_order": False,
        "calls_order_lifecycle": False,
        "exchange_write_called": False,
        "withdrawal_or_transfer_requested": False,
    }


class TradingConsoleReadModelResponse(BaseModel):
    """Envelope shared by all Trading Console read models."""

    read_model: str
    generated_at_ms: int
    source: str = "trading_console_read_model_v1"
    freshness_status: str
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    unavailable: list[dict[str, Any]] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    no_action_guarantee: dict[str, bool] = Field(
        default_factory=lambda: {
            "places_order": False,
            "cancels_order": False,
            "replaces_order": False,
            "flattens_position": False,
            "retries_protection": False,
            "starts_runtime": False,
            "grants_auto_execution": False,
            "mutates_pg": False,
        }
    )
    live_ready: bool = False


@dataclass
class TradingConsoleDependencies:
    runtime_bound: bool = False
    runtime_config_provider: Optional[Any] = None
    account_snapshot: Optional[Any] = None
    exchange_gateway: Optional[Any] = None
    order_repo: Optional[Any] = None
    position_repo: Optional[Any] = None
    execution_intent_repo: Optional[Any] = None
    execution_recovery_repo: Optional[Any] = None
    audit_logger: Optional[Any] = None
    signal_repo: Optional[Any] = None
    brc_campaign_service: Optional[Any] = None
    live_lifecycle_review_repo: Optional[Any] = None
    owner_trial_flow_service: Optional[Any] = None
    campaign_state_service: Optional[Any] = None
    multi_carrier_budget_authorization_service: Optional[Any] = None
    owner_capital_adjustment_repo: Optional[Any] = None
    owner_capital_baseline_snapshot_repo: Optional[Any] = None
    global_kill_switch_service: Optional[Any] = None
    startup_trading_guard_service: Optional[Any] = None
    startup_reconciliation_summary: Optional[dict[str, Any]] = None
    execution_orchestrator: Optional[Any] = None


@dataclass
class TradingConsoleSnapshot:
    symbols: list[str]
    include_exchange: bool
    generated_at_ms: int
    environment: dict[str, Any]
    guards: dict[str, Any]
    account_snapshot_summary: dict[str, Any]
    pg_orders: list[dict[str, Any]]
    pg_open_orders: list[dict[str, Any]]
    pg_positions: list[dict[str, Any]]
    pg_intents: list[dict[str, Any]]
    recovery_tasks: list[dict[str, Any]]
    audit_events: list[dict[str, Any]]
    review_records: list[dict[str, Any]]
    live_lifecycle_reviews: list[dict[str, Any]]
    signal_records: list[dict[str, Any]]
    authorization_state: dict[str, Any]
    runtime_control_state: dict[str, Any]
    budget_authorization_state: dict[str, Any]
    exchange: dict[str, Any]
    warnings: list[dict[str, Any]]
    unavailable: list[dict[str, Any]]


class TradingConsoleReadModelService:
    """Build Trading Console product read models from non-mutating dependencies."""

    def __init__(self, deps: TradingConsoleDependencies) -> None:
        self._deps = deps

    async def snapshot(
        self,
        *,
        symbol: Optional[str] = None,
        include_exchange: bool = False,
        limit: int = 100,
    ) -> TradingConsoleSnapshot:
        generated_at_ms = _now_ms()
        symbols = self._resolve_symbols(symbol)
        warnings: list[dict[str, Any]] = []
        unavailable: list[dict[str, Any]] = []

        environment = self._environment_summary()
        guards = self._guard_summary(unavailable)
        account_summary = self._account_snapshot_summary()

        pg_orders = await self._read_pg_orders(symbol=symbol, limit=limit, unavailable=unavailable)
        pg_open_orders = [item for item in pg_orders if str(item.get("status")) in OPEN_ORDER_STATUSES]
        if not pg_open_orders:
            pg_open_orders = await self._read_pg_open_orders(symbol=symbol, unavailable=unavailable)
        pg_positions = await self._read_pg_positions(symbol=symbol, unavailable=unavailable)
        pg_intents = await self._read_intents(symbol=symbol, limit=limit, unavailable=unavailable)
        recovery_tasks = await self._read_recovery_tasks(unavailable=unavailable)
        audit_events = await self._read_audit_events(limit=limit, unavailable=unavailable)
        review_records = await self._read_reviews(limit=limit, unavailable=unavailable)
        live_lifecycle_reviews = await self._read_live_lifecycle_reviews(
            symbol=symbol,
            limit=limit,
            unavailable=unavailable,
        )
        signal_records = await self._read_signals(symbol=symbol, limit=limit, unavailable=unavailable)
        authorization_state = await self._read_authorization_state(
            carrier_id=DEFAULT_CARRIER_ID,
            unavailable=unavailable,
        )
        runtime_control_state = self._read_runtime_control_state(unavailable=unavailable)
        budget_authorization_state = await self._read_budget_authorization_state(unavailable=unavailable)
        exchange = await self._read_exchange(
            symbols=symbols,
            include_exchange=include_exchange,
            unavailable=unavailable,
        )
        if include_exchange and account_summary.get("status") == "not_available":
            exchange_account = exchange.get("account_snapshot_summary")
            if isinstance(exchange_account, dict) and exchange_account.get("status") == "available":
                account_summary = exchange_account

        self._append_state_warnings(
            warnings=warnings,
            pg_open_orders=pg_open_orders,
            pg_positions=pg_positions,
            exchange=exchange,
        )

        return TradingConsoleSnapshot(
            symbols=symbols,
            include_exchange=include_exchange,
            generated_at_ms=generated_at_ms,
            environment=environment,
            guards=guards,
            account_snapshot_summary=account_summary,
            pg_orders=pg_orders,
            pg_open_orders=pg_open_orders,
            pg_positions=pg_positions,
            pg_intents=pg_intents,
            recovery_tasks=recovery_tasks,
            audit_events=audit_events,
            review_records=review_records,
            live_lifecycle_reviews=live_lifecycle_reviews,
            signal_records=signal_records,
            authorization_state=authorization_state,
            runtime_control_state=runtime_control_state,
            budget_authorization_state=budget_authorization_state,
            exchange=exchange,
            warnings=warnings,
            unavailable=unavailable,
        )

    async def dashboard_state(
        self,
        *,
        symbol: Optional[str] = None,
        include_exchange: bool = False,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(symbol=symbol, include_exchange=include_exchange)
        consistency = self._consistency_summary(snap)
        return self._response(
            "dashboard_state",
            snap,
            data={
                "environment": snap.environment,
                "guards": snap.guards,
                "account_snapshot_summary": snap.account_snapshot_summary,
                "positions": {
                    "pg": snap.pg_positions,
                    "exchange": snap.exchange.get("positions", []),
                },
                "orders": {
                    "pg_open": snap.pg_open_orders,
                    "exchange_open": snap.exchange.get("open_orders", []),
                    "open_intents": [
                        item for item in snap.pg_intents
                        if str(item.get("status")) not in TERMINAL_INTENT_STATUSES
                    ],
                },
                "consistency": consistency,
                "authorization": snap.authorization_state,
                "freshness": self._freshness(snap),
            },
        )

    async def account_risk(
        self,
        *,
        symbol: Optional[str] = None,
        include_exchange: bool = False,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(symbol=symbol, include_exchange=include_exchange)
        positions = self._merge_positions_for_risk(snap)
        open_orders = self._classify_orders(snap)
        risk_state = "degraded" if snap.warnings or snap.unavailable else "healthy"
        if any(item.get("classification") == "orphan_protection" for item in open_orders):
            risk_state = "degraded"
        if not positions and not include_exchange:
            risk_state = "unknown"
        return self._response(
            "account_risk",
            snap,
            data={
                "risk_state": risk_state,
                "account": snap.account_snapshot_summary,
                "positions": positions,
                "open_orders": open_orders,
                "margin_facts": {
                    "available_margin": snap.account_snapshot_summary.get("available_balance"),
                    "wallet_equity": snap.account_snapshot_summary.get("total_balance"),
                    "unrealized_pnl": snap.account_snapshot_summary.get("unrealized_pnl"),
                },
                "protection_ownership": self._protection_summary(snap),
                "freshness": self._freshness(snap),
            },
        )

    async def order_ledger(
        self,
        *,
        symbol: Optional[str] = None,
        include_exchange: bool = False,
        limit: int = 100,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(
            symbol=symbol,
            include_exchange=include_exchange,
            limit=limit,
        )
        classified = self._classify_orders(snap)
        return self._response(
            "order_ledger",
            snap,
            data={
                "orders": classified,
                "groups": self._order_groups(snap.pg_orders),
                "classification_counts": _count_by(classified, "classification"),
                "unavailable_fields": {
                    "client_order_id": "not_available",
                    "fees": "not_available",
                    "funding": "not_available",
                    "slippage": "not_available",
                },
            },
        )

    async def protection_health(
        self,
        *,
        symbol: Optional[str] = None,
        include_exchange: bool = False,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(symbol=symbol, include_exchange=include_exchange)
        summary = self._protection_summary(snap)
        return self._response(
            "protection_health",
            snap,
            data=summary,
        )

    async def recovery_exception_state(
        self,
        *,
        symbol: Optional[str] = None,
        include_exchange: bool = False,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(symbol=symbol, include_exchange=include_exchange)
        classified_orders = self._classify_orders(snap)
        mismatch_orders = [
            item for item in classified_orders
            if item.get("classification") in {"pg_only", "exchange_only", "mismatch", "orphan_protection"}
        ]
        return self._response(
            "recovery_exception_state",
            snap,
            data={
                "recovery_tasks": snap.recovery_tasks,
                "recovery_task_counts": _count_by(snap.recovery_tasks, "status"),
                "mismatches": mismatch_orders,
                "manual_action_required": bool(mismatch_orders or snap.recovery_tasks),
                "read_only_actions": {
                    "manual_reconciliation": "existing_separate_api_if_enabled",
                },
                "operational_drift": snap.environment.get("operational_drift") or {},
                "deferred_actions": [
                    "retry_protection",
                    "cancel_order",
                    "flatten_position",
                    "resolve_recovery_task",
                ],
            },
        )

    async def authorization_state(
        self,
        *,
        symbol: Optional[str] = None,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(symbol=symbol, include_exchange=False)
        return self._response(
            "authorization_state",
            snap,
            data=snap.authorization_state,
        )

    async def execution_control_state(
        self,
        *,
        symbol: Optional[str] = None,
        include_exchange: bool = False,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(symbol=symbol, include_exchange=include_exchange)
        protection = self._protection_summary(snap)
        open_intents = [
            item for item in snap.pg_intents
            if str(item.get("status")) not in TERMINAL_INTENT_STATUSES
        ]
        blockers: list[dict[str, Any]] = []
        auth = snap.authorization_state
        if not auth.get("is_actionable"):
            blockers.append(
                {
                    "code": "authorization_not_actionable",
                    "message": auth.get("blocking_reason") or "No actionable authorization.",
                }
            )
        if protection.get("status") in {"orphaned", "partially_protected", "unprotected"}:
            blockers.append(
                {
                    "code": "protection_state_degraded",
                    "message": f"Protection state is {protection.get('status')}.",
                }
            )
        return self._response(
            "execution_control_state",
            snap,
            blockers=blockers,
            data={
                "hard_gate": {
                    "status": "blocked" if blockers else "official_execute_path_required",
                    "gates": [
                        {
                            "code": "authorization_actionable",
                            "status": "pass" if auth.get("is_actionable") else "block",
                        },
                        {
                            "code": "protection_health",
                            "status": "warning"
                            if protection.get("status") in {"orphaned", "unknown"}
                            else "pass",
                        },
                        {
                            "code": "open_intents",
                            "status": "warning" if open_intents else "pass",
                        },
                    ],
                },
                "execution_preview": {
                    "status": "not_available",
                    "reason": "trading_console_get_requires_official_operation_layer_submit",
                },
                "deferred_execute_endpoint": True,
            },
        )

    async def review_state(
        self,
        *,
        symbol: Optional[str] = None,
        limit: int = 100,
        include_exchange: bool = False,
        previous_account_equity: Decimal | None = None,
        current_account_equity: Decimal | None = None,
        starting_capital_base: Decimal | None = None,
        realized_trading_pnl: Decimal = Decimal("0"),
        tolerance: Decimal = Decimal("0"),
        owner_capital_currency: str = "USDT",
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(
            symbol=symbol,
            include_exchange=include_exchange,
            limit=limit,
        )
        filled_orders = [
            order for order in snap.pg_orders
            if order.get("filled_qty") not in {None, "0", "0E-18", "0.0"}
            or order.get("average_exec_price") is not None
        ]
        owner_capital_review = await self._owner_capital_base_review(
            snap=snap,
            previous_account_equity=previous_account_equity,
            current_account_equity=current_account_equity,
            starting_capital_base=starting_capital_base,
            realized_trading_pnl=realized_trading_pnl,
            tolerance=tolerance,
            currency=owner_capital_currency,
            limit=limit,
        )
        right_tail_review = self._right_tail_review(snap=snap)
        return self._response(
            "review_state",
            snap,
            data={
                "reviews": snap.review_records,
                "live_lifecycle_reviews": snap.live_lifecycle_reviews,
                "filled_order_facts": filled_orders,
                "positions": snap.pg_positions,
                "owner_capital_base_review": owner_capital_review,
                "right_tail_review": right_tail_review,
                "unavailable_fields": {
                    "fills_table": "not_available",
                    "fee": "not_available",
                    "fee_asset": "not_available",
                    "funding": "not_available",
                    "slippage": "not_available",
                },
            },
        )

    async def owner_capital_review(
        self,
        *,
        symbol: Optional[str] = None,
        limit: int = 100,
        include_exchange: bool = False,
        previous_account_equity: Decimal | None = None,
        current_account_equity: Decimal | None = None,
        starting_capital_base: Decimal | None = None,
        realized_trading_pnl: Decimal = Decimal("0"),
        tolerance: Decimal = Decimal("0"),
        owner_capital_currency: str = "USDT",
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(
            symbol=symbol,
            include_exchange=include_exchange,
            limit=limit,
        )
        return self._response(
            "owner_capital_review",
            snap,
            data=await self._owner_capital_base_review(
                snap=snap,
                previous_account_equity=previous_account_equity,
                current_account_equity=current_account_equity,
                starting_capital_base=starting_capital_base,
                realized_trading_pnl=realized_trading_pnl,
                tolerance=tolerance,
                currency=owner_capital_currency,
                limit=limit,
            ),
        )

    async def right_tail_review(
        self,
        *,
        symbol: Optional[str] = None,
        limit: int = 100,
        include_exchange: bool = False,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(
            symbol=symbol,
            include_exchange=include_exchange,
            limit=limit,
        )
        return self._response(
            "right_tail_review",
            snap,
            data=self._right_tail_review(snap=snap),
        )

    async def audit_chain(
        self,
        *,
        authorization_id: Optional[str] = None,
        runtime_instance_id: Optional[str] = None,
        trial_binding_id: Optional[str] = None,
        strategy_family_id: Optional[str] = None,
        strategy_family_version_id: Optional[str] = None,
        signal_evaluation_id: Optional[str] = None,
        order_candidate_id: Optional[str] = None,
        intent_id: Optional[str] = None,
        order_id: Optional[str] = None,
        exchange_order_id: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(symbol=symbol, include_exchange=False, limit=limit)
        chain_orders = self._filter_chain_orders(
            snap.pg_orders,
            order_id=order_id,
            exchange_order_id=exchange_order_id,
            runtime_instance_id=runtime_instance_id,
            trial_binding_id=trial_binding_id,
            strategy_family_id=strategy_family_id,
            strategy_family_version_id=strategy_family_version_id,
            signal_evaluation_id=signal_evaluation_id,
            order_candidate_id=order_candidate_id,
        )
        chain_intents = self._filter_chain_intents(
            snap.pg_intents,
            authorization_id=authorization_id,
            runtime_instance_id=runtime_instance_id,
            trial_binding_id=trial_binding_id,
            strategy_family_id=strategy_family_id,
            strategy_family_version_id=strategy_family_version_id,
            signal_evaluation_id=signal_evaluation_id,
            order_candidate_id=order_candidate_id,
            intent_id=intent_id,
            order_ids={str(item.get("order_id")) for item in chain_orders if item.get("order_id")},
            exchange_order_ids={
                str(item.get("exchange_order_id"))
                for item in chain_orders
                if item.get("exchange_order_id")
            },
        )
        order_ids = {str(item.get("order_id")) for item in chain_orders}
        signal_ids = {str(item.get("signal_id")) for item in chain_orders if item.get("signal_id")}
        chain_audit = [
            item for item in snap.audit_events
            if str(item.get("order_id")) in order_ids or str(item.get("signal_id")) in signal_ids
        ]
        return self._response(
            "audit_chain",
            snap,
            data={
                "query": {
                    "authorization_id": authorization_id,
                    "runtime_instance_id": runtime_instance_id,
                    "trial_binding_id": trial_binding_id,
                    "strategy_family_id": strategy_family_id,
                    "strategy_family_version_id": strategy_family_version_id,
                    "signal_evaluation_id": signal_evaluation_id,
                    "order_candidate_id": order_candidate_id,
                    "intent_id": intent_id,
                    "order_id": order_id,
                    "exchange_order_id": exchange_order_id,
                    "symbol": symbol,
                },
                "authorization": snap.authorization_state,
                "intents": chain_intents,
                "orders": chain_orders,
                "positions": snap.pg_positions,
                "reviews": snap.review_records,
                "audit_events": chain_audit,
                "raw_payload_policy": "masked_or_omitted",
            },
        )

    async def carrier_availability(
        self,
        *,
        include_exchange: bool = False,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(symbol=DEFAULT_SYMBOL, include_exchange=include_exchange)
        protection = self._protection_summary(snap)
        auth = snap.authorization_state
        blocked_reasons: list[str] = []
        if auth.get("is_actionable"):
            blocked_reasons.append("active_authorization_present")
        if snap.pg_open_orders:
            blocked_reasons.append("pg_open_orders_present")
        if protection.get("status") in {"orphaned", "partially_protected", "unprotected"}:
            blocked_reasons.append(f"protection_{protection.get('status')}")
        return self._response(
            "carrier_availability",
            snap,
            data={
                "carriers": [
                    {
                        "carrier_id": DEFAULT_CARRIER_ID,
                        "strategy_family_id": DEFAULT_STRATEGY_FAMILY_ID,
                        "symbol": DEFAULT_SYMBOL,
                        "side": "long",
                        "status": "blocked" if blocked_reasons else "candidate_available_for_review",
                        "blocked_reasons": blocked_reasons,
                        "authorization": auth,
                        "protection": protection,
                    }
                ],
                "sample_data_policy": "not_used",
            },
        )

    async def strategy_family_admission_state(
        self,
        *,
        owner_scope: Optional[dict[str, Any]] = None,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(symbol=DEFAULT_SYMBOL, include_exchange=False)
        state = build_production_strategy_family_admission_state(
            current_authorization_state=snap.authorization_state,
            owner_scope=owner_scope,
            now_ms=snap.generated_at_ms,
        )
        blockers = [
            {
                "code": record.id,
                "message": record.evidence,
                "severity": record.severity,
                "stage": record.stage,
            }
            for record in state.blocker_records
        ]
        if state.scope_review.verdict != "complete_dry_run_only":
            blockers.insert(
                0,
                {
                    "code": "production_scope_incomplete",
                    "message": (
                        "No candidate has complete symbol/side/quantity/max_notional/"
                        "leverage/max_attempts/protection_mode/review_requirement scope."
                    ),
                },
            )
        return self._response(
            "strategy_family_admission_state",
            snap,
            blockers=blockers,
            data={
                **state.model_dump(mode="json", exclude={"generated_at_ms"}),
                "candidate_output": [
                    item.model_dump(mode="json")
                    for item in state.trading_console_candidate_output
                ],
            },
        )

    async def action_entry_readiness(
        self,
        *,
        owner_scope: Optional[dict[str, Any]] = None,
        market_input: Optional[dict[str, Any]] = None,
        include_exchange: bool = False,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(
            symbol=_action_entry_snapshot_symbol(owner_scope),
            include_exchange=include_exchange,
        )
        data, blockers = self._action_entry_readiness_data(
            snap=snap,
            owner_scope=owner_scope,
            market_input=market_input,
        )
        return self._response(
            "action_entry_readiness",
            snap,
            blockers=blockers,
            data=data,
        )

    async def owner_action_flow(
        self,
        *,
        owner_scope: Optional[dict[str, Any]] = None,
        market_input: Optional[dict[str, Any]] = None,
        custom_budget: Optional[dict[str, Any]] = None,
        include_exchange: bool = False,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(
            symbol=_action_entry_snapshot_symbol(owner_scope),
            include_exchange=include_exchange,
        )
        data, blockers = self._action_entry_readiness_data(
            snap=snap,
            owner_scope=owner_scope,
            market_input=market_input,
            custom_budget=custom_budget,
        )
        data = {
            **data,
            "owner_action_flow": _owner_action_flow(data),
        }
        return self._response(
            "owner_action_flow",
            snap,
            blockers=blockers,
            data=data,
        )

    async def operations_cockpit(
        self,
        *,
        symbol: Optional[str] = None,
        include_exchange: bool = False,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(symbol=symbol, include_exchange=include_exchange)
        action_data, action_blockers = self._action_entry_readiness_data(
            snap=snap,
            owner_scope={"symbol": symbol} if symbol else None,
            market_input=None,
            custom_budget=None,
        )
        owner_flow = action_data.get("owner_action_flow") or {}
        budget_summary = owner_flow.get("budget_summary") or {}
        selected_proposal = owner_flow.get("selected_action_proposal") or {}
        post_action = action_data.get("post_action_state") or {}
        protection = self._protection_summary(snap)
        positions = self._merge_positions_for_risk(snap)
        consistency = self._consistency_summary(snap)
        review = _cockpit_review_summary(
            post_action=post_action,
            reviews=snap.review_records,
            live_lifecycle_reviews=snap.live_lifecycle_reviews,
        )
        recovery = _cockpit_recovery_summary(
            snap=snap,
            classified_orders=self._classify_orders(snap),
            consistency=consistency,
        )
        budget = _cockpit_budget_summary(
            owner_flow=owner_flow,
            budget_summary=budget_summary,
            budget_recommendation=action_data.get("budget_recommendation") or {},
            post_action=post_action,
            budget_authorization=snap.budget_authorization_state,
            runtime_control=snap.runtime_control_state,
        )
        active_position = _cockpit_active_position(
            positions=positions,
            protection=protection,
            snap=snap,
        )
        autonomy = _cockpit_autonomy_summary(
            owner_flow=owner_flow,
            authorization=snap.authorization_state,
            protection=protection,
            active_position=active_position,
            recovery=recovery,
            review=review,
            budget=budget,
            runtime_control=snap.runtime_control_state,
        )
        blockers = _cockpit_blockers(
            snap=snap,
            action_blockers=action_blockers,
            protection=protection,
            recovery=recovery,
            review=review,
            budget=budget,
            active_position=active_position,
        )
        overall = _cockpit_overall_status(
            snap=snap,
            autonomy=autonomy,
            active_position=active_position,
            protection=protection,
            recovery=recovery,
            review=review,
            budget=budget,
            blockers=blockers,
        )
        controls = _cockpit_controls(
            overall=overall,
            recovery=recovery,
            review=review,
            budget=budget,
            active_position=active_position,
            autonomy=autonomy,
        )
        runtime_governance = _cockpit_runtime_governance_summary(
            overall=overall,
            autonomy=autonomy,
            budget=budget,
            active_position=active_position,
            protection=_cockpit_protection_summary(protection),
            review=review,
            blockers=blockers,
            post_action=post_action,
            runtime_control=snap.runtime_control_state,
            budget_authorization=snap.budget_authorization_state,
        )
        return self._response(
            "operations_cockpit",
            snap,
            blockers=[
                {
                    "code": item["code"],
                    "message": item["what"],
                    "affected_area": item["area"],
                }
                for item in blockers
                if item.get("severity") in {"hard_blocker", "recovery_required"}
            ],
            data={
                "overall_status": overall,
                "primary_message": overall["message"],
                "primary_next_action": overall["primary_next_action"],
                "autonomy_effective_state": autonomy.get("autonomy_effective_state"),
                "budget_effective_state": budget.get("budget_effective_state"),
                "budget_authorization_status": budget.get("budget_authorization_status"),
                "can_attempt_next_budgeted_action": autonomy.get("can_attempt_next_budgeted_action"),
                "can_pause_autonomy": autonomy.get("can_pause_autonomy"),
                "can_revoke_budget": budget.get("can_revoke_budget"),
                "last_control_operation": _latest_control_operation(
                    snap.runtime_control_state,
                    snap.budget_authorization_state,
                ),
                "autonomy": autonomy,
                "budget": budget,
                "active_position": active_position,
                "protection": _cockpit_protection_summary(protection),
                "runtime_governance": runtime_governance,
                "candidate": _cockpit_candidate_summary(
                    selected_proposal=selected_proposal,
                    owner_flow=owner_flow,
                    action_data=action_data,
                ),
                "blockers": blockers,
                "warnings": _cockpit_warnings(snap),
                "recovery": recovery,
                "review": review,
                "controls": controls,
                "freshness": self._freshness(snap),
                "evidence": {
                    "environment": snap.environment,
                    "guards": snap.guards,
                    "consistency": consistency,
                    "authorization": snap.authorization_state,
                    "runtime_control_state": snap.runtime_control_state,
                    "budget_authorization_state": snap.budget_authorization_state,
                    "runtime_governance": runtime_governance,
                    "budgeted_autonomy_loop": owner_flow.get("budgeted_autonomy_loop") or {},
                    "budgeted_autonomy_v01": owner_flow.get("budgeted_autonomy_v01") or {},
                    "post_action_state": post_action,
                    "read_model_source_policy": "pg_exchange_aggregation_no_write",
                    "raw_debug_sections_available": [
                        "dashboard-state",
                        "order-ledger",
                        "protection-health",
                        "recovery-exception-state",
                        "review-state",
                        "audit-chain",
                    ],
                },
            },
        )

    async def budget_recommendation(
        self,
        *,
        include_exchange: bool = False,
        risk_tier: str = "tiny",
        custom: Optional[dict[str, Any]] = None,
        owner_selection: Optional[dict[str, Any]] = None,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(symbol=None, include_exchange=include_exchange)
        budget = self._budget_recommendation_payload(
            snap=snap,
            risk_tier=risk_tier,
            custom=custom,
            owner_selection=owner_selection,
        )
        blockers = [
            {
                "code": item.get("id"),
                "message": item.get("evidence"),
                "stage": item.get("stage"),
                "path": item.get("path"),
                "severity": item.get("severity"),
                "bridge": item.get("bridge"),
                "retry_condition": item.get("retry_condition"),
            }
            for item in budget.get("blockers", [])
        ]
        return self._response(
            "budget_recommendation",
            snap,
            blockers=blockers,
            data=budget,
        )

    def _action_entry_readiness_data(
        self,
        *,
        snap: TradingConsoleSnapshot,
        owner_scope: Optional[dict[str, Any]] = None,
        market_input: Optional[dict[str, Any]] = None,
        custom_budget: Optional[dict[str, Any]] = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        normalized_market_input = _normalize_action_entry_market_input(market_input)
        state = build_production_strategy_family_admission_state(
            current_authorization_state=snap.authorization_state,
            owner_scope=owner_scope,
            now_ms=snap.generated_at_ms,
        )
        blockers = [
            {
                "code": record.id,
                "message": record.evidence,
                "severity": record.severity,
                "stage": record.stage,
            }
            for record in state.blocker_records
        ]
        candidate_output = [
            item.model_dump(mode="json")
            for item in state.trading_console_candidate_output
        ]
        generic_action_specs = [
            item.model_dump(mode="json") for item in state.generic_action_specs
        ]
        raw_owner_selection = _owner_budget_selection_from(
            owner_scope=owner_scope or {},
            market_input=normalized_market_input,
        )
        budget = self._budget_recommendation_payload(
            snap=snap,
            risk_tier=normalized_market_input.get("risk_tier") or "tiny",
            custom=custom_budget,
            owner_selection=raw_owner_selection,
        )
        budget = _apply_owner_approved_budget_window(budget, custom_budget or {})
        envelope = dict(budget.get("budget_envelope") or {})
        candidate_output = apply_budget_envelope_to_action_candidates(candidate_output, envelope)
        generic_action_specs = apply_budget_envelope_to_generic_action_specs(
            generic_action_specs,
            envelope,
        )
        owner_selection = {
            **raw_owner_selection,
            **dict(budget.get("owner_selection") or {}),
        }
        generic_action_specs = _apply_owner_selection_to_generic_action_specs(
            specs=generic_action_specs,
            owner_selection=owner_selection,
            envelope=envelope,
        )
        candidate_output = _apply_owner_selection_to_action_candidates(
            candidates=candidate_output,
            generic_specs=generic_action_specs,
        )
        payload_contracts = [
            item.model_dump(mode="json")
            for item in state.action_entry_payload_contracts
        ]
        action_entry_output = [
            item.model_dump(mode="json")
            for item in state.trading_console_action_entry_output
        ]
        product_backbone = state.product_backbone.model_dump(mode="json")
        candidate_actionability = [
            item.model_dump(mode="json") for item in state.candidate_actionability
        ]
        final_gate_preview_inputs = [
            item.model_dump(mode="json") for item in state.final_gate_preview_inputs
        ]
        final_gate_adapter_results = [
            item.model_dump(mode="json") for item in state.final_gate_adapter_results
        ]
        protection_templates = [
            item.model_dump(mode="json") for item in state.protection_templates
        ]
        selected_candidate = _select_action_entry_candidate(
            market_input=normalized_market_input,
            owner_scope=owner_scope or {},
            candidate_output=candidate_output,
            generic_action_specs=generic_action_specs,
            payload_contracts=payload_contracts,
            action_entry_output=action_entry_output,
        )
        post_action_state = _action_entry_post_action_state(snap)
        product_loop = build_candidate_action_product_loop(
            owner_market_input=normalized_market_input,
            budget_recommendation=budget,
            selected_candidate=selected_candidate,
            candidate_output=candidate_output,
            generic_action_specs=generic_action_specs,
            action_entry_payload_contracts=payload_contracts,
            action_entry_output=action_entry_output,
            final_gate_adapter_results=final_gate_adapter_results,
            post_action_state=post_action_state,
            fact_context={
                "account": snap.account_snapshot_summary,
                "environment": snap.environment,
                "guards": snap.guards,
                "pg_positions": snap.pg_positions,
                "pg_open_orders": snap.pg_open_orders,
                "completed_intents_today_by_symbol": post_action_state.get(
                    "completed_intents_today_by_symbol",
                    {},
                ),
                "reconciliation_ref": snap.guards.get("reconciliation_ref"),
            },
        ).model_dump(mode="json")
        return {
            "owner_market_input": normalized_market_input,
            "budget_recommendation": budget,
            "selected_candidate": selected_candidate,
            "candidate_action_product_loop": {
                "status": product_loop["status"],
                "loop_version": product_loop["loop_version"],
                "no_action_guarantee": product_loop["no_action_guarantee"],
            },
            "candidate_action_readiness_loop": product_loop[
                "candidate_action_readiness_loop"
            ],
            "selected_candidate_action_readiness_loop": product_loop[
                "selected_candidate_action_readiness_loop"
            ],
            "risk_review": _action_entry_risk_review(
                selected_candidate=selected_candidate,
                adapter_contract=state.generic_final_gate_adapter_contract.model_dump(mode="json"),
                blockers=blockers,
                market_input=normalized_market_input,
            ),
            "authorization_draft_path": _action_entry_authorization_draft_path(
                selected_candidate=selected_candidate,
                state_dump=state.model_dump(mode="json", exclude={"generated_at_ms"}),
            ),
            "final_gate_result": _action_entry_final_gate_result(
                selected_candidate=selected_candidate,
                blockers=blockers,
            ),
            "action_state": _action_entry_action_state(selected_candidate),
            "post_action_state": post_action_state,
            "generic_final_gate_adapter_contract": (
                state.generic_final_gate_adapter_contract.model_dump(mode="json")
            ),
            "product_backbone": product_backbone,
            "candidate_actionability": candidate_actionability,
            "final_gate_preview_inputs": final_gate_preview_inputs,
            "final_gate_adapter_results": final_gate_adapter_results,
            "protection_templates": protection_templates,
            "warning_records": [
                item.model_dump(mode="json") for item in state.warning_records
            ],
            "hard_blocker_records": [
                item.model_dump(mode="json") for item in state.hard_blocker_records
            ],
            "trading_console_candidate_action_read_model": (
                state.trading_console_candidate_action_read_model.model_dump(mode="json")
            ),
            "generic_action_specs": generic_action_specs,
            "action_entry_payload_contracts": payload_contracts,
            "action_entry_output": action_entry_output,
            "candidate_output": candidate_output,
        }, blockers

    def _budget_recommendation_payload(
        self,
        *,
        snap: TradingConsoleSnapshot,
        risk_tier: str = "tiny",
        custom: Optional[dict[str, Any]] = None,
        owner_selection: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        budget = build_budget_recommendation(
            account_summary=snap.account_snapshot_summary,
            positions=self._merge_positions_for_risk(snap),
            open_orders=self._open_orders_for_budget(snap),
            freshness=self._budget_freshness(snap),
            risk_tier=risk_tier,
            custom=custom,
            owner_selection=owner_selection,
        )
        return budget.model_dump(mode="json")

    def _open_orders_for_budget(self, snap: TradingConsoleSnapshot) -> list[dict[str, Any]]:
        return [
            item
            for item in self._classify_orders(snap)
            if str(item.get("status")) in OPEN_ORDER_STATUSES
        ]

    def _budget_freshness(self, snap: TradingConsoleSnapshot) -> dict[str, Any]:
        exchange = snap.exchange
        status = "fresh"
        budget_sources = {"orders", "open_orders", "positions", "account_snapshot", "exchange"}
        budget_unavailable = [
            item
            for item in snap.unavailable
            if str(item.get("source") or "") in budget_sources
        ]
        if budget_unavailable or exchange.get("exchange_error"):
            status = "degraded"
        if snap.warnings:
            status = "warning" if status == "fresh" else "degraded"
        if not snap.include_exchange:
            status = "not_live_connected"
        return {
            "last_updated_at": _iso_ms(snap.generated_at_ms),
            "exchange_snapshot_at": (
                _iso_ms(exchange.get("exchange_snapshot_at"))
                if exchange.get("exchange_snapshot_at")
                else None
            ),
            "freshness_status": status,
            "exchange_error": exchange.get("exchange_error"),
            "ignored_unavailable_sources": [
                item.get("source")
                for item in snap.unavailable
                if str(item.get("source") or "") not in budget_sources
            ],
        }

    async def signal_marker_feed(
        self,
        *,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(symbol=symbol, include_exchange=False, limit=limit)
        markers: list[dict[str, Any]] = []
        for signal in snap.signal_records:
            markers.append(
                {
                    "marker_type": "signal_observed",
                    "timestamp_ms": signal.get("created_at") or signal.get("timestamp"),
                    "symbol": signal.get("symbol"),
                    "side": signal.get("direction"),
                    "source_id": signal.get("signal_id") or signal.get("id"),
                    "payload": signal,
                }
            )
        for intent in snap.pg_intents:
            markers.append(
                {
                    "marker_type": "execution_intent",
                    "timestamp_ms": intent.get("created_at"),
                    "symbol": intent.get("symbol"),
                    "side": intent.get("side"),
                    "source_id": intent.get("intent_id"),
                    "payload": intent,
                }
            )
        for order in snap.pg_orders:
            role = str(order.get("order_role") or "").lower()
            markers.append(
                {
                    "marker_type": f"order_{role or 'unknown'}",
                    "timestamp_ms": order.get("created_at"),
                    "symbol": order.get("symbol"),
                    "side": order.get("direction"),
                    "price": order.get("average_exec_price") or order.get("price") or order.get("trigger_price"),
                    "source_id": order.get("order_id"),
                    "payload": order,
                }
            )
        return self._response(
            "signal_marker_feed",
            snap,
            data={
                "markers": markers[:limit],
                "chart_adapter": {
                    "status": "backend_feed_only",
                    "tradingview_symbol_mapping": "not_available",
                    "lightweight_charts_ready": False,
                },
            },
        )

    def api_classification(self) -> TradingConsoleReadModelResponse:
        generated_at_ms = _now_ms()
        return TradingConsoleReadModelResponse(
            read_model="api_classification",
            generated_at_ms=generated_at_ms,
            freshness_status="fresh",
            data={
                "trading_console_v1_allowed": [
                    "GET /api/trading-console/operations-cockpit",
                    "GET /api/trading-console/dashboard-state",
                    "GET /api/trading-console/account-risk",
                    "GET /api/trading-console/order-ledger",
                    "GET /api/trading-console/protection-health",
                    "GET /api/trading-console/recovery-exception-state",
                    "GET /api/trading-console/authorization-state",
                    "GET /api/trading-console/execution-control-state",
                    "GET /api/trading-console/review-state",
                    "GET /api/trading-console/owner-capital-review",
                    "GET /api/trading-console/right-tail-review",
                    "GET /api/trading-console/audit-chain",
                    "GET /api/trading-console/carrier-availability",
                    "GET /api/trading-console/strategy-family-admission-state",
                    "GET /api/trading-console/action-entry-readiness",
                    "GET /api/trading-console/budget-recommendation",
                    "GET /api/trading-console/signal-marker-feed",
                    "GET /api/trading-console/runtime-signal-watcher-status",
                    "GET /api/trading-console/strategygroup-runtime-pilot-status",
                    "GET /api/trading-console/strategy-group-handoff-intake",
                    "GET /api/trading-console/strategy-group-live-facts-readiness",
                    "GET /api/trading-console/api-classification",
                ],
                "internal_or_legacy": [
                    "/api/brc/*",
                    "/api/runtime/*",
                    "/api/dev/testnet/brc/*",
                ],
                "action_api_policy": "official_brc_operation_layer_required_for_submit",
                "sample_data_policy": "not_allowed_as_trading_console_truth_source",
            },
        )

    def runtime_signal_watcher_status(
        self,
        *,
        stale_after_seconds: int = 180,
    ) -> TradingConsoleReadModelResponse:
        generated_at_ms = _now_ms()
        report_dir = Path(
            os.environ.get("BRC_SIGNAL_WATCHER_REPORT_DIR", DEFAULT_SIGNAL_WATCHER_REPORT_DIR)
        ).expanduser()
        files = {
            "watcher_tick": report_dir / "watcher-tick.json",
            "wakeup_packet": report_dir / "wakeup-packet.json",
            "operator_packet": report_dir / "operator-packet.json",
            "status_packet": report_dir / "status-packet.json",
            "notification_state": report_dir / "notification-state.json",
        }
        payloads = {name: _read_json_file(path) for name, path in files.items()}
        resume_pack_path = report_dir / "post-signal-resume-pack.json"
        resume_pack = _read_json_file(resume_pack_path)
        watcher_tick = payloads["watcher_tick"]
        wakeup_packet = payloads["wakeup_packet"]
        operator_packet = payloads["operator_packet"]
        status_packet = payloads["status_packet"]
        notification_state = payloads["notification_state"]
        file_status = {
            name: {
                "path": str(path),
                "present": path.exists(),
                "mtime_ms": _file_mtime_ms(path),
            }
            for name, path in files.items()
        }
        missing = [name for name, status in file_status.items() if not status["present"]]
        latest_mtime_ms = max(
            [int(status["mtime_ms"] or 0) for status in file_status.values()],
            default=0,
        )
        age_seconds = (
            max(0, int((generated_at_ms - latest_mtime_ms) / 1000))
            if latest_mtime_ms
            else None
        )
        stale = bool(age_seconds is not None and age_seconds > stale_after_seconds)
        safety = watcher_tick.get("safety_invariants") if isinstance(watcher_tick, dict) else {}
        safety = safety if isinstance(safety, dict) else {}
        post_signal_auto_resume = (
            resume_pack.get("post_signal_auto_resume")
            if isinstance(resume_pack.get("post_signal_auto_resume"), dict)
            else watcher_tick.get("post_signal_auto_resume")
            if isinstance(watcher_tick.get("post_signal_auto_resume"), dict)
            else {}
        )
        unsafe_flags = [
            name for name in sorted(SIGNAL_WATCHER_UNSAFE_FLAGS)
            if safety.get(name) not in {False, None}
        ]
        notification = watcher_tick.get("notification") if isinstance(watcher_tick, dict) else {}
        notification = notification if isinstance(notification, dict) else {}
        wakeup_status = str(watcher_tick.get("wakeup_status") or wakeup_packet.get("status") or "unknown")
        operator_status = str(watcher_tick.get("operator_status") or operator_packet.get("status") or "unknown")
        status_packet_status = str(
            watcher_tick.get("status_packet_status") or status_packet.get("status") or "unknown"
        )
        resume_pack_can_continue = resume_pack.get("can_continue_steps_5_8")
        can_resume_steps_5_8 = (
            bool(resume_pack_can_continue)
            if isinstance(resume_pack_can_continue, bool)
            else wakeup_status in SIGNAL_WATCHER_RESUME_READY_STATUSES
            and not unsafe_flags
        )
        if missing:
            readiness_status = "evidence_missing"
        elif stale:
            readiness_status = "evidence_stale"
        elif unsafe_flags:
            readiness_status = "unsafe_watcher_effect_detected"
        elif not notification.get("configured"):
            readiness_status = "notification_not_configured"
        else:
            readiness_status = "ready"
        action_time_resume = _runtime_signal_watcher_action_time_resume(
            resume_pack=resume_pack,
            post_signal_auto_resume=post_signal_auto_resume,
            can_resume_steps_5_8=can_resume_steps_5_8,
        )
        owner_state = resume_pack.get("owner_state")
        if not isinstance(owner_state, dict) or not owner_state:
            owner_state = _runtime_signal_watcher_owner_state(
                post_signal_auto_resume=post_signal_auto_resume,
                readiness_status=readiness_status,
                missing=missing,
                stale=stale,
                unsafe_flags=unsafe_flags,
                can_resume_steps_5_8=can_resume_steps_5_8,
            )
        else:
            owner_state = dict(owner_state)
            blocked_reason = str(owner_state.get("blocked_reason") or "none")
            owner_state.setdefault(
                "why_not_executable",
                [] if blocked_reason == "none" else [blocked_reason],
            )
            owner_state.setdefault(
                "can_continue_without_owner_chat",
                bool(post_signal_auto_resume.get("can_continue_without_owner_chat"))
                or can_resume_steps_5_8,
            )
            owner_state.setdefault(
                "requires_action_time_final_gate",
                bool(action_time_resume.get("requires_action_time_final_gate")),
            )
            owner_state.setdefault(
                "requires_official_operation_layer",
                bool(action_time_resume.get("requires_official_operation_layer")),
            )

        blockers: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        if missing:
            blockers.append(
                {
                    "code": "runtime_signal_watcher_evidence_missing",
                    "message": "Runtime Signal Watcher evidence files are missing.",
                    "affected_area": ",".join(missing),
                }
            )
        if unsafe_flags:
            blockers.append(
                {
                    "code": "runtime_signal_watcher_unsafe_effect",
                    "message": "Watcher evidence contains forbidden effect flags.",
                    "affected_area": ",".join(unsafe_flags),
                }
            )
        if stale:
            warnings.append(
                {
                    "code": "runtime_signal_watcher_evidence_stale",
                    "severity": "warning",
                    "message": "Runtime Signal Watcher evidence is older than the configured freshness window.",
                    "count": 1,
                }
            )
        freshness_status = "fresh"
        if blockers:
            freshness_status = "not_live_connected"
        elif warnings:
            freshness_status = "warning"

        return TradingConsoleReadModelResponse(
            read_model="runtime_signal_watcher_status",
            generated_at_ms=generated_at_ms,
            freshness_status=freshness_status,
            warnings=warnings,
            blockers=blockers,
            unavailable=[],
            data={
                "deployment_readiness": {
                    "status": readiness_status,
                    "report_dir": str(report_dir),
                    "file_status": file_status,
                    "latest_evidence_age_seconds": age_seconds,
                    "stale_after_seconds": stale_after_seconds,
                    "systemd_timer": "verified_by_deployment_readiness_packet",
                    "feishu_configured": bool(notification.get("configured")),
                    "duplicate_suppression": "active"
                    if notification_state.get("last_notified_event_key")
                    else "not_yet_observed",
                },
                "watcher": {
                    "status": watcher_tick.get("status") or "unknown",
                    "wakeup_status": wakeup_status,
                    "operator_status": operator_status,
                    "status_packet_status": status_packet_status,
                    "runtime_signal_summaries": status_packet.get(
                        "runtime_signal_summaries"
                    )
                    or [],
                    "blockers": watcher_tick.get("blockers") or status_packet.get("blockers") or [],
                    "warnings": watcher_tick.get("warnings") or status_packet.get("warnings") or [],
                    "post_signal_auto_resume": post_signal_auto_resume,
                },
                "status_packet": {
                    "status": status_packet.get("status") or "unknown",
                    "latest_status": status_packet.get("latest_status"),
                    "runtime_signal_summaries": status_packet.get(
                        "runtime_signal_summaries"
                    )
                    or [],
                },
                "notification": {
                    "required": bool(notification.get("required")),
                    "configured": bool(notification.get("configured")),
                    "attempted": bool(notification.get("attempted")),
                    "sent": bool(notification.get("sent")),
                    "duplicate_suppressed": bool(notification.get("duplicate_suppressed")),
                    "skipped_reason": notification.get("skipped_reason"),
                },
                "post_signal_resume": {
                    "status": action_time_resume["status"],
                    "can_continue_steps_5_8": can_resume_steps_5_8,
                    "current_gate": (
                        "action_time_final_gate"
                        if action_time_resume["status"]
                        == "ready_for_action_time_final_gate"
                        else "waiting_for_fresh_strategy_signal"
                        if action_time_resume["status"] == "waiting_for_market"
                        else "blocked"
                    ),
                    "post_signal_auto_resume": post_signal_auto_resume,
                    "action_time_resume": action_time_resume,
                    "resume_pack_path": str(resume_pack_path),
                    "resume_pack_present": resume_pack_path.exists(),
                    "raw_resume_pack_status": resume_pack.get("status"),
                    "next_chain": [
                        "fresh candidate",
                        "runtime grant",
                        "fresh authorization evidence",
                        "action-time FinalGate",
                        "official Operation Layer gateway action",
                        "post-submit finalize / reconciliation / budget settlement",
                    ],
                },
                "action_time_resume": action_time_resume,
                "post_signal_auto_resume": post_signal_auto_resume,
                "owner_state": owner_state,
                "why_not_executable": owner_state["why_not_executable"],
                "next_safe_checkpoint": owner_state["automatic_recovery_action"],
                "safety_invariants": {
                    **{name: bool(safety.get(name)) for name in sorted(SIGNAL_WATCHER_UNSAFE_FLAGS)},
                    "forbidden_effect_flags": unsafe_flags,
                    "watcher_status_read_model_only": True,
                    "places_order": False,
                    "mutates_pg": False,
                },
            },
            live_ready=False,
        )

    def strategy_group_handoff_intake(
        self,
        *,
        handoff_dir: Optional[str] = None,
        source_repo: Optional[str] = None,
        source_branch: Optional[str] = None,
        source_commit: Optional[str] = None,
    ) -> TradingConsoleReadModelResponse:
        generated_at_ms = _now_ms()
        configured_packet_path = os.environ.get("BRC_STRATEGY_GROUP_HANDOFF_PACKET_PATH")
        default_packet_path = Path(DEFAULT_STRATEGY_GROUP_HANDOFF_PACKET_PATH).expanduser()
        resolved_packet_path = (
            Path(configured_packet_path).expanduser()
            if configured_packet_path
            else default_packet_path
        )
        latest_packet_path = _latest_existing_path(
            Path(DEFAULT_STRATEGY_GROUP_REPORT_DIR),
            DEFAULT_STRATEGY_GROUP_HANDOFF_PACKET_GLOB,
        )
        packet_path = (
            resolved_packet_path
            if resolved_packet_path.exists()
            else latest_packet_path
        )
        resolved_handoff_dir = Path(
            handoff_dir
            or os.environ.get("BRC_STRATEGY_GROUP_HANDOFF_DIR")
            or str(DEFAULT_STRATEGY_GROUP_HANDOFF_DIR)
        ).expanduser()
        resolved_source_repo = (
            source_repo
            or os.environ.get("BRC_STRATEGY_GROUP_HANDOFF_SOURCE_REPO")
            or DEFAULT_STRATEGY_GROUP_HANDOFF_REPO
        )
        resolved_source_branch = (
            source_branch
            or os.environ.get("BRC_STRATEGY_GROUP_HANDOFF_SOURCE_BRANCH")
            or DEFAULT_STRATEGY_GROUP_HANDOFF_BRANCH
        )
        resolved_source_commit = (
            source_commit
            or os.environ.get("BRC_STRATEGY_GROUP_HANDOFF_SOURCE_COMMIT")
            or DEFAULT_STRATEGY_GROUP_HANDOFF_COMMIT
        )
        if packet_path is not None and handoff_dir is None:
            packet = _read_json_file(packet_path)
            if packet:
                packet["handoff_packet_source"] = {
                    "path": str(packet_path),
                    "present": True,
                    "source": "prebuilt_strategy_group_handoff_intake_packet",
                }
        else:
            packet = {}
        if not packet:
            try:
                packet = build_strategy_group_handoff_intake_packet(
                    handoff_dir=resolved_handoff_dir,
                    source_repo=resolved_source_repo,
                    source_branch=resolved_source_branch,
                    source_commit=resolved_source_commit,
                )
            except Exception as exc:
                packet = {
                    "scope": "strategy_group_handoff_main_control_intake",
                    "status": "blocked_handoff_intake",
                    "generated_at_ms": generated_at_ms,
                    "source_anchor": {
                        "repo": resolved_source_repo,
                        "branch": resolved_source_branch,
                        "commit": resolved_source_commit,
                        "handoff_dir": str(resolved_handoff_dir),
                    },
                    "counts": {
                        "strategy_groups": 0,
                        "armed_observation_intake_ready": 0,
                        "observe_only_intake_ready": 0,
                        "required_fact_rows": 0,
                    },
                    "strategy_picker": [],
                    "required_facts_matrix": [],
                    "watcher_scope": [],
                    "blockers": [f"handoff_intake_build_failed:{type(exc).__name__}"],
                    "safety_invariants": {
                        "reads_research_handoff_only": True,
                        "registers_runtime": False,
                        "creates_candidate": False,
                        "authorizes_execution": False,
                        "places_order": False,
                        "mutates_pg": False,
                    },
                }
        if not packet:
            packet = {
                "scope": "strategy_group_handoff_main_control_intake",
                "status": "blocked_handoff_intake",
                "generated_at_ms": generated_at_ms,
                "source_anchor": {
                    "repo": resolved_source_repo,
                    "branch": resolved_source_branch,
                    "commit": resolved_source_commit,
                    "handoff_dir": str(resolved_handoff_dir),
                },
                "counts": {
                    "strategy_groups": 0,
                    "armed_observation_intake_ready": 0,
                    "observe_only_intake_ready": 0,
                    "required_fact_rows": 0,
                },
                "strategy_picker": [],
                "required_facts_matrix": [],
                "watcher_scope": [],
                "blockers": [f"handoff_intake_build_failed:{type(exc).__name__}"],
                "safety_invariants": {
                    "reads_research_handoff_only": True,
                    "registers_runtime": False,
                    "creates_candidate": False,
                    "authorizes_execution": False,
                    "places_order": False,
                    "mutates_pg": False,
                },
            }
        packet_blockers = list(packet.get("blockers") or [])
        blockers = [
            {
                "code": "strategy_group_handoff_intake_blocked",
                "message": "StrategyGroup handoff intake is not ready for main-control consumption.",
                "affected_area": ",".join(packet_blockers[:8]),
            }
        ] if packet_blockers else []
        freshness_status = "fresh" if not blockers else "not_live_connected"
        return TradingConsoleReadModelResponse(
            read_model="strategy_group_handoff_intake",
            generated_at_ms=generated_at_ms,
            freshness_status=freshness_status,
            warnings=[],
            blockers=blockers,
            unavailable=[],
            data=packet,
            live_ready=False,
        )

    def strategy_group_live_facts_readiness(
        self,
        *,
        live_facts_path: Optional[str] = None,
    ) -> TradingConsoleReadModelResponse:
        generated_at_ms = _now_ms()
        intake = self.strategy_group_handoff_intake().data
        configured_live_facts_path = (
            live_facts_path or os.environ.get("BRC_STRATEGY_GROUP_LIVE_FACTS_PATH")
        )
        resolved_live_facts_path = Path(
            configured_live_facts_path or DEFAULT_STRATEGY_GROUP_LIVE_FACTS_PATH
        ).expanduser()
        if configured_live_facts_path is None and not resolved_live_facts_path.exists():
            latest_live_facts_path = _latest_existing_path(
                Path(DEFAULT_STRATEGY_GROUP_REPORT_DIR),
                DEFAULT_STRATEGY_GROUP_LIVE_FACTS_GLOB,
            )
            if latest_live_facts_path is not None:
                resolved_live_facts_path = latest_live_facts_path
        live_facts = _read_json_file(resolved_live_facts_path)
        packet = build_strategy_group_live_facts_readiness_packet(
            intake_packet=intake,
            live_facts=live_facts,
            generated_at_ms=generated_at_ms,
        )
        packet["live_facts_source"] = {
            "path": str(resolved_live_facts_path),
            "present": resolved_live_facts_path.exists(),
        }
        if not resolved_live_facts_path.exists():
            packet["blockers"] = sorted(
                set(list(packet.get("blockers") or []) + ["live_facts_path_missing"])
            )
            packet["status"] = "strategy_group_live_facts_blocked"
        blockers = [
            {
                "code": "strategy_group_live_facts_blocked",
                "message": "StrategyGroup live facts are not ready for observation.",
                "affected_area": ",".join(list(packet.get("blockers") or [])[:8]),
            }
        ] if packet.get("blockers") else []
        warnings = [
            {
                "code": "strategy_group_candidate_prerequisites_pending",
                "severity": "info",
                "message": (
                    "StrategyGroup observation can continue; candidate preparation "
                    "is waiting for budget, protection, or next-attempt facts."
                ),
                "count": len(packet.get("candidate_prepare_blockers") or []),
            }
        ] if packet.get("candidate_prepare_blockers") else []
        freshness_status = "fresh" if not blockers else "warning"
        return TradingConsoleReadModelResponse(
            read_model="strategy_group_live_facts_readiness",
            generated_at_ms=generated_at_ms,
            freshness_status=freshness_status,
            warnings=warnings,
            blockers=blockers,
            unavailable=[],
            data=packet,
            live_ready=False,
        )

    def strategygroup_runtime_pilot_status(
        self,
        *,
        selected_strategy_group_id: Optional[str] = None,
        max_symbols: int = 3,
        stale_after_seconds: int = 180,
    ) -> TradingConsoleReadModelResponse:
        generated_at_ms = _now_ms()
        intake_response = self.strategy_group_handoff_intake()
        live_facts_response = self.strategy_group_live_facts_readiness()
        watcher_response = self.runtime_signal_watcher_status(
            stale_after_seconds=stale_after_seconds,
        )
        packet = build_strategygroup_runtime_pilot_status_packet(
            intake_packet=intake_response.data,
            live_facts_readiness=live_facts_response.data,
            watcher_status={"data": watcher_response.data},
            selected_strategy_group_id=selected_strategy_group_id,
            max_symbols=max_symbols,
            generated_at_ms=generated_at_ms,
        )
        blocker_class = str((packet.get("owner_state") or {}).get("blocker_class") or "")
        blockers: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        if blocker_class in {
            "hard_safety_stop",
            "active_position_resolution",
            "deployment_issue",
            "runtime_scope_mismatch",
        }:
            blockers.append(
                {
                    "code": f"strategygroup_runtime_pilot_{blocker_class}",
                    "message": "StrategyGroup runtime pilot cannot safely advance to candidate preparation.",
                    "affected_area": str((packet.get("owner_state") or {}).get("blocked_at") or "unknown"),
                }
            )
        elif blocker_class in {"waiting_for_market", "missing_fact", "review_only_warning"}:
            warnings.append(
                {
                    "code": f"strategygroup_runtime_pilot_{blocker_class}",
                    "severity": "info" if blocker_class == "waiting_for_market" else "warning",
                    "message": str((packet.get("owner_state") or {}).get("blocked_reason") or "pending"),
                    "count": 1,
                }
            )
        freshness_status = "fresh"
        if blockers:
            freshness_status = "not_live_connected"
        elif warnings:
            freshness_status = "warning"
        return TradingConsoleReadModelResponse(
            read_model="strategygroup_runtime_pilot_status",
            generated_at_ms=generated_at_ms,
            freshness_status=freshness_status,
            warnings=warnings,
            blockers=blockers,
            unavailable=[],
            data=packet,
            live_ready=False,
        )

    def _response(
        self,
        read_model: str,
        snap: TradingConsoleSnapshot,
        *,
        data: dict[str, Any],
        blockers: Optional[list[dict[str, Any]]] = None,
    ) -> TradingConsoleReadModelResponse:
        return TradingConsoleReadModelResponse(
            read_model=read_model,
            generated_at_ms=snap.generated_at_ms,
            freshness_status=self._freshness(snap)["freshness_status"],
            warnings=snap.warnings,
            blockers=blockers or [],
            unavailable=snap.unavailable,
            data=data,
        )

    def _resolve_symbols(self, symbol: Optional[str]) -> list[str]:
        if symbol:
            return [symbol]
        provider = self._deps.runtime_config_provider
        config = getattr(provider, "resolved_config", None)
        market = getattr(config, "market", None)
        symbols = getattr(market, "symbols", None)
        if isinstance(symbols, list) and symbols:
            return [str(item) for item in symbols]
        return [DEFAULT_SYMBOL]

    def _environment_summary(self) -> dict[str, Any]:
        provider = self._deps.runtime_config_provider
        config = getattr(provider, "resolved_config", None)
        environment = getattr(config, "environment", None)
        market = getattr(config, "market", None)
        startup_summary = self._deps.startup_reconciliation_summary or {}
        env_testnet = _parse_bool_env(os.environ.get("EXCHANGE_TESTNET"))
        return {
            "runtime_bound": self._deps.runtime_bound,
            "profile": (
                getattr(config, "profile_name", None)
                or startup_summary.get("profile")
                or os.environ.get("RUNTIME_PROFILE")
                or os.environ.get("APP_ENV")
                or "unknown"
            ),
            "trading_env": (
                getattr(environment, "trading_env", None)
                or startup_summary.get("trading_env")
                or os.environ.get("TRADING_ENV")
                or "unknown"
            ),
            "exchange_testnet": (
                getattr(environment, "exchange_testnet", None)
                if getattr(environment, "exchange_testnet", None) is not None
                else (
                    startup_summary.get("exchange_testnet")
                    if startup_summary.get("exchange_testnet") is not None
                    else env_testnet
                )
            ),
            "symbols": getattr(market, "symbols", None) or startup_summary.get("symbols") or [DEFAULT_SYMBOL],
            "startup_reconciliation": startup_summary or "not_available",
            "operational_drift": _operational_drift_summary(startup_summary),
            "live_ready": False,
        }

    def _guard_summary(self, unavailable: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "global_kill_switch": self._service_bool(
                self._deps.global_kill_switch_service,
                "is_active",
                unavailable,
                unavailable_code="gks_unavailable",
            ),
            "startup_guard_armed": self._service_bool(
                self._deps.startup_trading_guard_service,
                "is_armed",
                unavailable,
                unavailable_code="startup_guard_unavailable",
            ),
        }

    @staticmethod
    def _service_bool(
        service: Optional[Any],
        method_name: str,
        unavailable: list[dict[str, Any]],
        *,
        unavailable_code: str,
    ) -> Optional[bool]:
        if service is None or not hasattr(service, method_name):
            unavailable.append({"source": method_name, "code": unavailable_code})
            return None
        try:
            return bool(getattr(service, method_name)())
        except Exception as exc:
            unavailable.append({"source": method_name, "code": "read_failed", "error": str(exc)})
            return None

    def _account_snapshot_summary(self) -> dict[str, Any]:
        snapshot = self._deps.account_snapshot
        if snapshot is None:
            return {
                "status": "not_available",
                "total_balance": "not_available",
                "available_balance": "not_available",
                "unrealized_pnl": "not_available",
                "timestamp_ms": None,
                "positions_count": 0,
            }
        positions = getattr(snapshot, "positions", []) or []
        return {
            "status": "available",
            "total_balance": _scalar(getattr(snapshot, "total_balance", None)),
            "available_balance": _scalar(getattr(snapshot, "available_balance", None)),
            "unrealized_pnl": _scalar(getattr(snapshot, "unrealized_pnl", None)),
            "timestamp_ms": getattr(snapshot, "timestamp", None),
            "positions_count": len(positions),
        }

    async def _read_pg_orders(
        self,
        *,
        symbol: Optional[str],
        limit: int,
        unavailable: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        repo = self._deps.order_repo
        if repo is None:
            unavailable.append({"source": "orders", "code": "order_repo_unavailable"})
            return []
        try:
            if hasattr(repo, "get_orders"):
                result = await repo.get_orders(symbol=symbol, limit=limit, offset=0)
                items = result.get("items", []) if isinstance(result, dict) else result
            elif symbol and hasattr(repo, "get_orders_by_symbol"):
                items = await repo.get_orders_by_symbol(symbol, limit=limit)
            elif hasattr(repo, "get_open_orders"):
                items = await repo.get_open_orders(symbol)
            else:
                unavailable.append({"source": "orders", "code": "order_repo_missing_list_method"})
                return []
        except Exception as exc:
            unavailable.append({"source": "orders", "code": "read_failed", "error": str(exc)})
            return []
        return [_order_item(item) for item in list(items)[:limit]]

    async def _read_pg_open_orders(
        self,
        *,
        symbol: Optional[str],
        unavailable: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        repo = self._deps.order_repo
        if repo is None or not hasattr(repo, "get_open_orders"):
            return []
        try:
            return [_order_item(item) for item in await repo.get_open_orders(symbol)]
        except Exception as exc:
            unavailable.append({"source": "open_orders", "code": "read_failed", "error": str(exc)})
            return []

    async def _read_pg_positions(
        self,
        *,
        symbol: Optional[str],
        unavailable: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        repo = self._deps.position_repo
        if repo is None:
            unavailable.append({"source": "positions", "code": "position_repo_unavailable"})
            return []
        try:
            if hasattr(repo, "list_active"):
                positions = await repo.list_active(symbol=symbol, limit=200)
            elif hasattr(repo, "list_positions"):
                positions = await repo.list_positions(symbol=symbol, is_closed=False, limit=200)
            else:
                unavailable.append({"source": "positions", "code": "position_repo_missing_list_method"})
                return []
        except Exception as exc:
            unavailable.append({"source": "positions", "code": "read_failed", "error": str(exc)})
            return []
        return [_position_item(item, source="pg") for item in positions]

    async def _read_intents(
        self,
        *,
        symbol: Optional[str],
        limit: int,
        unavailable: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        repo = self._deps.execution_intent_repo
        if repo is None:
            unavailable.append({"source": "execution_intents", "code": "intent_repo_unavailable"})
            return []
        try:
            if hasattr(repo, "list"):
                intents = await repo.list()
            elif hasattr(repo, "list_unfinished"):
                intents = await repo.list_unfinished()
            else:
                unavailable.append({"source": "execution_intents", "code": "intent_repo_missing_list_method"})
                return []
        except Exception as exc:
            unavailable.append({"source": "execution_intents", "code": "read_failed", "error": str(exc)})
            return []
        items = [_intent_item(item) for item in intents]
        if symbol:
            items = [item for item in items if item.get("symbol") == symbol]
        return items[:limit]

    async def _read_recovery_tasks(self, *, unavailable: list[dict[str, Any]]) -> list[dict[str, Any]]:
        repo = self._deps.execution_recovery_repo
        if repo is None:
            unavailable.append({"source": "recovery_tasks", "code": "recovery_repo_unavailable"})
            return []
        try:
            if hasattr(repo, "list_blocking"):
                tasks = await repo.list_blocking()
            elif hasattr(repo, "list_active"):
                tasks = await repo.list_active()
            else:
                unavailable.append({"source": "recovery_tasks", "code": "recovery_repo_missing_list_method"})
                return []
        except Exception as exc:
            unavailable.append({"source": "recovery_tasks", "code": "read_failed", "error": str(exc)})
            return []
        return [_plain_dict(item) for item in tasks]

    async def _read_audit_events(
        self,
        *,
        limit: int,
        unavailable: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        audit_logger = self._deps.audit_logger
        repo = getattr(audit_logger, "_repository", None) if audit_logger is not None else None
        if repo is None:
            unavailable.append({"source": "order_audit_logs", "code": "audit_repo_unavailable"})
            return []
        try:
            if hasattr(repo, "query"):
                from src.domain.models import OrderAuditLogQuery

                events = await repo.query(OrderAuditLogQuery(limit=limit, offset=0))
            elif hasattr(repo, "get_by_time_range"):
                events = await repo.get_by_time_range(0, _now_ms(), limit=limit)
            else:
                unavailable.append({"source": "order_audit_logs", "code": "audit_repo_missing_query_method"})
                return []
        except Exception as exc:
            unavailable.append({"source": "order_audit_logs", "code": "read_failed", "error": str(exc)})
            return []
        return [_audit_item(item) for item in events]

    async def _read_reviews(
        self,
        *,
        limit: int,
        unavailable: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        service = self._deps.brc_campaign_service
        if service is None or not hasattr(service, "list_review_decisions"):
            unavailable.append({"source": "review_state", "code": "review_service_unavailable"})
            return []
        try:
            return [_plain_dict(item) for item in await service.list_review_decisions(limit=limit)]
        except Exception as exc:
            unavailable.append({"source": "review_state", "code": "read_failed", "error": str(exc)})
            return []

    async def _read_owner_capital_adjustments(
        self,
        *,
        currency: str,
        limit: int,
        unavailable: list[dict[str, Any]],
    ) -> list[OwnerCapitalAdjustmentRecord]:
        repo = self._deps.owner_capital_adjustment_repo
        if repo is None or not hasattr(repo, "list"):
            unavailable.append(
                {
                    "source": "owner_capital_adjustments",
                    "code": "repo_unavailable",
                }
            )
            return []
        try:
            return list(await repo.list(currency=currency, limit=limit))
        except Exception as exc:
            unavailable.append(
                {
                    "source": "owner_capital_adjustments",
                    "code": "read_failed",
                    "error": str(exc),
                }
            )
            return []

    async def _read_owner_capital_baseline_snapshots(
        self,
        *,
        currency: str,
        limit: int,
        unavailable: list[dict[str, Any]],
    ) -> list[OwnerCapitalBaselineSnapshot]:
        repo = self._deps.owner_capital_baseline_snapshot_repo
        if repo is None or not hasattr(repo, "list"):
            unavailable.append(
                {
                    "source": "owner_capital_baseline_snapshots",
                    "code": "repo_unavailable",
                }
            )
            return []
        try:
            return list(await repo.list(currency=currency, limit=limit))
        except Exception as exc:
            unavailable.append(
                {
                    "source": "owner_capital_baseline_snapshots",
                    "code": "read_failed",
                    "error": str(exc),
                }
            )
            return []

    async def _owner_capital_base_review(
        self,
        *,
        snap: TradingConsoleSnapshot,
        previous_account_equity: Decimal | None,
        current_account_equity: Decimal | None,
        starting_capital_base: Decimal | None,
        realized_trading_pnl: Decimal,
        tolerance: Decimal,
        currency: str,
        limit: int,
    ) -> dict[str, Any]:
        records = await self._read_owner_capital_adjustments(
            currency=currency,
            limit=limit,
            unavailable=snap.unavailable,
        )
        baseline_snapshots = await self._read_owner_capital_baseline_snapshots(
            currency=currency,
            limit=1,
            unavailable=snap.unavailable,
        )
        latest_baseline = baseline_snapshots[0] if baseline_snapshots else None
        previous_equity_source = "query" if previous_account_equity is not None else "missing"
        starting_capital_base_source = "query" if starting_capital_base is not None else "missing"
        if previous_account_equity is None and latest_baseline is not None:
            previous_account_equity = latest_baseline.account_equity
            previous_equity_source = "latest_owner_capital_baseline_snapshot"
        if starting_capital_base is None and latest_baseline is not None:
            starting_capital_base = latest_baseline.capital_base
            starting_capital_base_source = "latest_owner_capital_baseline_snapshot"
        current_equity = current_account_equity
        current_equity_source = "query" if current_account_equity is not None else "missing"
        if current_equity is None:
            current_equity = _decimal_or_none(
                snap.account_snapshot_summary.get("total_balance")
            )
            current_equity_source = str(
                snap.account_snapshot_summary.get("status") or "account_snapshot_summary"
            ) if current_equity is not None else "missing"
        required_inputs = []
        if previous_account_equity is None:
            required_inputs.append("previous_account_equity")
        if current_equity is None:
            required_inputs.append("current_account_equity")
        if starting_capital_base is None:
            required_inputs.append("starting_capital_base")

        base_payload: dict[str, Any] = {
            "status": "reviewed" if not required_inputs else "review_inputs_required",
            "currency": currency,
            "record_count": len(records),
            "records": [record.model_dump(mode="json") for record in records],
            "baseline_snapshot": (
                latest_baseline.model_dump(mode="json")
                if latest_baseline is not None
                else None
            ),
            "baseline_snapshot_count": len(baseline_snapshots),
            "required_inputs": required_inputs,
            "input_facts": {
                "previous_account_equity": _scalar(previous_account_equity),
                "current_account_equity": _scalar(current_equity),
                "starting_capital_base": _scalar(starting_capital_base),
                "realized_trading_pnl": _scalar(realized_trading_pnl),
                "tolerance": _scalar(tolerance),
                "previous_account_equity_source": previous_equity_source,
                "current_account_equity_source": current_equity_source,
                "starting_capital_base_source": starting_capital_base_source,
            },
            "review_principle": "owner_capital_events_are_not_strategy_pnl",
            "no_action_guarantee": {
                "creates_withdrawal_instruction": False,
                "creates_transfer_instruction": False,
                "creates_order_instruction": False,
                "calls_exchange": False,
                "mutates_runtime_budget": False,
                "mutates_strategy_pnl": False,
                "creates_risk_event": False,
            },
        }
        if required_inputs:
            base_payload["classification"] = "not_reviewed_missing_inputs"
            base_payload["review_result"] = None
            base_payload["unexplained_account_equity_delta"] = "not_available"
            base_payload["ending_capital_base"] = "not_available"
            return base_payload

        assert previous_account_equity is not None
        assert current_equity is not None
        assert starting_capital_base is not None
        result = review_owner_capital_base_movement(
            OwnerCapitalBaseReviewInput(
                previous_account_equity=previous_account_equity,
                current_account_equity=current_equity,
                starting_capital_base=starting_capital_base,
                realized_trading_pnl=realized_trading_pnl,
                owner_capital_adjustments=records,
                tolerance=tolerance,
            )
        )
        base_payload["classification"] = result.classification.value
        base_payload["review_result"] = result.model_dump(mode="json")
        base_payload["unexplained_account_equity_delta"] = _scalar(
            result.unexplained_account_equity_delta
        )
        base_payload["ending_capital_base"] = _scalar(result.ending_capital_base)
        return base_payload

    def _right_tail_review(self, *, snap: TradingConsoleSnapshot) -> dict[str, Any]:
        lifecycle_records: list[BrcLiveLifecycleReviewRecord] = []
        facts: list[RightTailTradePathFacts] = []
        skipped: list[dict[str, Any]] = []
        for review in snap.live_lifecycle_reviews:
            try:
                lifecycle_record = _live_lifecycle_review_record(review)
            except Exception as exc:
                skipped.append(
                    {
                        "review_id": review.get("review_id"),
                        "reason": "live_lifecycle_review_record_invalid",
                        "error": str(exc),
                    }
                )
                continue
            lifecycle_records.append(lifecycle_record)
            metadata = lifecycle_record.metadata
            if not isinstance(metadata, dict):
                skipped.append(
                    {
                        "review_id": lifecycle_record.review_id,
                        "reason": "metadata_not_object",
                    }
                )
                continue
            raw_facts = metadata.get("right_tail_trade_path")
            if raw_facts is None:
                continue
            if not isinstance(raw_facts, dict):
                skipped.append(
                    {
                        "review_id": lifecycle_record.review_id,
                        "reason": "right_tail_trade_path_not_object",
                    }
                )
                continue
            payload = {
                "trade_id": lifecycle_record.review_id,
                "source_review_id": lifecycle_record.review_id,
                "symbol": lifecycle_record.symbol,
                "side": lifecycle_record.side,
                "strategy_family_id": lifecycle_record.strategy_family_id,
                "strategy_family_version_id": (
                    lifecycle_record.strategy_family_version_id
                ),
                "runtime_instance_id": lifecycle_record.runtime_instance_id,
                "order_candidate_id": lifecycle_record.order_candidate_id,
                **raw_facts,
            }
            try:
                facts.append(RightTailTradePathFacts.model_validate(payload))
            except Exception as exc:
                skipped.append(
                    {
                        "review_id": lifecycle_record.review_id,
                        "reason": "right_tail_trade_path_invalid",
                        "error": str(exc),
                    }
                )
        summary = summarize_right_tail_reviews(facts).model_dump(mode="json")
        semantic_packets = summarize_runtime_semantic_review_packets(
            lifecycle_records
        ).model_dump(mode="json")
        summary["source"] = "live_lifecycle_review.metadata.right_tail_trade_path"
        summary["skipped_sources"] = skipped
        summary["closed_trade_review_packets"] = semantic_packets["packets"]
        summary["closed_trade_review_packet_summary"] = {
            key: value
            for key, value in semantic_packets.items()
            if key != "packets"
        }
        summary["required_metadata_shape"] = {
            "metadata_key": "right_tail_trade_path",
            "required_fields": [
                "entry_price",
                "exit_price",
                "mfe_price",
                "mae_price",
                "realized_pnl",
                "opened_at_ms",
                "closed_at_ms",
                "max_loss_budget_or_protection_stop_price",
            ],
            "source_policy": "explicit_only_no_order_or_exchange_inference",
        }
        return summary

    async def _read_live_lifecycle_reviews(
        self,
        *,
        symbol: Optional[str],
        limit: int,
        unavailable: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        repo = self._deps.live_lifecycle_review_repo
        if repo is None or not hasattr(repo, "list"):
            unavailable.append({"source": "live_lifecycle_reviews", "code": "repo_unavailable"})
            return []
        try:
            return [_plain_dict(item) for item in await repo.list(symbol=symbol, limit=limit)]
        except Exception as exc:
            unavailable.append(
                {"source": "live_lifecycle_reviews", "code": "read_failed", "error": str(exc)}
            )
            return []

    async def _read_signals(
        self,
        *,
        symbol: Optional[str],
        limit: int,
        unavailable: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        repo = self._deps.signal_repo
        if repo is None or not hasattr(repo, "get_signals"):
            unavailable.append({"source": "signals", "code": "signal_repo_unavailable"})
            return []
        try:
            result = await repo.get_signals(symbol=symbol, limit=limit)
        except Exception as exc:
            unavailable.append({"source": "signals", "code": "read_failed", "error": str(exc)})
            return []
        data = result.get("data", []) if isinstance(result, dict) else []
        return [_signal_item(item) for item in data[:limit]]

    async def _read_authorization_state(
        self,
        *,
        carrier_id: str,
        unavailable: list[dict[str, Any]],
    ) -> dict[str, Any]:
        service = self._deps.owner_trial_flow_service
        if service is None or not hasattr(service, "current"):
            unavailable.append({"source": "authorization_state", "code": "owner_trial_flow_service_unavailable"})
            return {
                "carrier_id": carrier_id,
                "status": "unknown",
                "is_actionable": False,
                "blocking_reason": "owner_trial_flow_service_unavailable",
                "future_action_slots": _authorization_future_action_slots(),
            }
        try:
            current = await service.current(carrier_id=carrier_id)
        except Exception as exc:
            unavailable.append({"source": "authorization_state", "code": "read_failed", "error": str(exc)})
            return {
                "carrier_id": carrier_id,
                "status": "unknown",
                "is_actionable": False,
                "blocking_reason": "authorization_state_read_failed",
                "future_action_slots": _authorization_future_action_slots(),
            }
        payload = _plain_dict(current)
        authorization = payload.get("live_authorization") or {}
        if not authorization:
            status = payload.get("authorization_status") or "not_available"
            return {
                "carrier_id": carrier_id,
                "status": status,
                "is_actionable": False,
                "is_consumed": False,
                "is_expired": False,
                "is_cancelled": False,
                "scope_match": "unknown",
                "blocking_reason": "missing_active_authorization",
                "scope": payload.get("carrier") or {},
                "current": payload,
                "future_action_slots": _authorization_future_action_slots(),
            }
        consumed = bool(authorization.get("consumed"))
        expired = _is_expired(authorization.get("expires_at_ms"))
        permission = bool(
            authorization.get("order_permission_granted")
            and authorization.get("execution_permission_granted")
        )
        actionable = bool(
            authorization
            and not consumed
            and not expired
            and permission
            and authorization.get("live_ready") is True
        )
        reason = None
        if consumed:
            reason = "authorization_consumed"
        elif expired:
            reason = "authorization_expired"
        elif not permission:
            reason = "authorization_permission_flags_false"
        elif authorization.get("live_ready") is not True:
            reason = "authorization_live_ready_false"
        return {
            "carrier_id": carrier_id,
            "authorization_id": authorization.get("authorization_id"),
            "status": authorization.get("status") or payload.get("authorization_status"),
            "is_actionable": actionable,
            "is_consumed": consumed,
            "is_expired": expired,
            "is_cancelled": False,
            "scope_match": "not_checked",
            "blocking_reason": reason,
            "scope": {
                "carrier_id": authorization.get("carrier_id"),
                "strategy_family_id": authorization.get("strategy_family_id"),
                "symbol": authorization.get("symbol"),
                "side": authorization.get("side"),
                "max_notional": authorization.get("max_notional"),
                "quantity": authorization.get("quantity"),
                "leverage": authorization.get("leverage"),
                "profile": "not_available",
                "environment": "not_available",
            },
            "current": payload,
            "future_action_slots": _authorization_future_action_slots(),
        }

    def _read_runtime_control_state(self, *, unavailable: list[dict[str, Any]]) -> dict[str, Any]:
        service = self._deps.campaign_state_service
        if service is None or not hasattr(service, "get_state"):
            unavailable.append({"source": "runtime_control_state", "code": "campaign_state_service_unavailable"})
            return {
                "status": "unknown",
                "autonomy_effective_state": "unknown",
                "source": "campaign_state_service_unavailable",
                "can_attempt_next_budgeted_action": False,
                "disabled_reason": "runtime control state is unavailable",
            }
        try:
            state = service.get_state()
        except Exception as exc:
            unavailable.append({"source": "runtime_control_state", "code": "read_failed", "error": str(exc)})
            return {
                "status": "unknown",
                "autonomy_effective_state": "unknown",
                "source": "read_failed",
                "can_attempt_next_budgeted_action": False,
                "disabled_reason": "runtime control state read failed",
            }
        payload = _plain_dict(state)
        status = str(payload.get("status") or "unknown")
        paused = status == "paused"
        return {
            "status": status,
            "autonomy_effective_state": "paused" if paused else status,
            "reason": payload.get("reason"),
            "updated_by": payload.get("updated_by"),
            "updated_at_ms": payload.get("updated_at_ms"),
            "source": payload.get("source") or "runtime_campaign_state",
            "can_attempt_next_budgeted_action": not paused and status not in {"hard_locked", "closed", "loss_locked"},
            "disabled_reason": (
                "Autonomy is paused; future budgeted action attempts are blocked until Owner resumes or resets."
                if paused
                else None
            ),
            "last_control_operation": {
                "operation_type": "enter_pause" if paused else "runtime_state",
                "status": status,
                "operation_id": None,
                "updated_at_ms": payload.get("updated_at_ms"),
                "updated_by": payload.get("updated_by"),
                "source": payload.get("source") or "runtime_campaign_state",
            },
        }

    async def _read_budget_authorization_state(self, *, unavailable: list[dict[str, Any]]) -> dict[str, Any]:
        service = self._deps.multi_carrier_budget_authorization_service
        if service is None or not hasattr(service, "current"):
            unavailable.append({"source": "budget_authorization_state", "code": "budget_authorization_service_unavailable"})
            return {
                "status": "unknown",
                "budget_effective_state": "unknown",
                "source": "budget_authorization_service_unavailable",
                "can_attempt_next_budgeted_action": False,
                "disabled_reason": "budget authorization state is unavailable",
            }
        try:
            current = await service.current()
        except Exception as exc:
            unavailable.append({"source": "budget_authorization_state", "code": "read_failed", "error": str(exc)})
            return {
                "status": "unknown",
                "budget_effective_state": "unknown",
                "source": "read_failed",
                "can_attempt_next_budgeted_action": False,
                "disabled_reason": "budget authorization state read failed",
            }
        payload = _plain_dict(current)
        latest = dict(payload.get("latest_budget_authorization") or {})
        status = str(latest.get("status") or "not_available")
        revoked = status == "revoked"
        return {
            "status": status,
            "budget_authorization_id": latest.get("budget_authorization_id"),
            "budget_effective_state": (
                "revoked" if revoked
                else "available_metadata_only" if latest
                else "not_available"
            ),
            "budget_authorization_status": status,
            "revoked": revoked,
            "revoked_at_ms": latest.get("revoked_at_ms"),
            "revoked_by": latest.get("revoked_by"),
            "revoke_reason": latest.get("revoke_reason"),
            "last_control_operation_id": latest.get("last_control_operation_id"),
            "source": payload.get("budget_scope_source") or "pg_metadata",
            "latest_budget_authorization": latest,
            "disabled_execution_state": payload.get("disabled_execution_state") or {},
            "can_attempt_next_budgeted_action": bool(latest) and not revoked,
            "disabled_reason": (
                "Budget authorization has been revoked; re-authorization is required before future budgeted autonomy attempts."
                if revoked
                else "No current budget authorization metadata exists."
                if not latest
                else None
            ),
            "last_control_operation": {
                "operation_type": "revoke_budget" if revoked else "budget_authorization",
                "status": status,
                "operation_id": latest.get("last_control_operation_id"),
                "updated_at_ms": latest.get("updated_at_ms"),
                "updated_by": latest.get("revoked_by"),
                "source": payload.get("budget_scope_source") or "pg_metadata",
            },
        }

    async def _read_exchange(
        self,
        *,
        symbols: list[str],
        include_exchange: bool,
        unavailable: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not include_exchange:
            return {
                "included": False,
                "positions": [],
                "open_orders": [],
                "exchange_snapshot_at": None,
                "exchange_error": None,
            }
        gateway = self._deps.exchange_gateway
        if gateway is None:
            unavailable.append({"source": "exchange", "code": "exchange_gateway_unavailable"})
            return {
                "included": True,
                "positions": [],
                "open_orders": [],
                "exchange_snapshot_at": None,
                "exchange_error": "exchange_gateway_unavailable",
            }
        positions: list[dict[str, Any]] = []
        open_orders: list[dict[str, Any]] = []
        errors: list[str] = []
        account_snapshot_summary: Optional[dict[str, Any]] = None
        if hasattr(gateway, "fetch_account_balance"):
            try:
                account_snapshot = await asyncio.wait_for(
                    gateway.fetch_account_balance(),
                    timeout=EXCHANGE_READ_TIMEOUT_SECONDS,
                )
                account_snapshot_summary = _account_snapshot_summary_from_snapshot(account_snapshot)
            except Exception as exc:
                errors.append(f"account:{exc}")
        for symbol in symbols:
            try:
                fetched_positions = await asyncio.wait_for(
                    gateway.fetch_positions(symbol),
                    timeout=EXCHANGE_READ_TIMEOUT_SECONDS,
                )
                positions.extend(_position_item(item, source="exchange") for item in fetched_positions)
            except Exception as exc:
                errors.append(f"positions:{symbol}:{exc}")
            try:
                normal_orders = await asyncio.wait_for(
                    gateway.fetch_open_orders(symbol),
                    timeout=EXCHANGE_READ_TIMEOUT_SECONDS,
                )
                open_orders.extend(_exchange_order_item(item, source="exchange_normal") for item in normal_orders)
            except Exception as exc:
                errors.append(f"open_orders:{symbol}:{exc}")
            try:
                stop_orders = await asyncio.wait_for(
                    gateway.fetch_open_orders(symbol, params={"stop": True}),
                    timeout=EXCHANGE_READ_TIMEOUT_SECONDS,
                )
                open_orders.extend(_exchange_order_item(item, source="exchange_stop") for item in stop_orders)
            except Exception as exc:
                errors.append(f"stop_orders:{symbol}:{exc}")
        if errors:
            unavailable.append({"source": "exchange", "code": "read_failed", "error": "; ".join(errors)})
        return {
            "included": True,
            "positions": positions,
            "open_orders": open_orders,
            "account_snapshot_summary": account_snapshot_summary,
            "exchange_snapshot_at": _now_ms(),
            "exchange_error": "; ".join(errors) if errors else None,
        }

    def _append_state_warnings(
        self,
        *,
        warnings: list[dict[str, Any]],
        pg_open_orders: list[dict[str, Any]],
        pg_positions: list[dict[str, Any]],
        exchange: dict[str, Any],
    ) -> None:
        protection_orders = [
            item for item in pg_open_orders
            if str(item.get("order_role")) in PROTECTION_ROLES
        ]
        exchange_positions = exchange.get("positions") or []
        exchange_orders = exchange.get("open_orders") or []
        reduce_only_exchange = [
            item for item in exchange_orders
            if _truthy(item.get("reduce_only")) or str(item.get("position_side") or "").upper() in {"LONG", "SHORT"}
        ]
        if protection_orders and not pg_positions:
            warnings.append(
                {
                    "code": "pg_open_protection_without_pg_position",
                    "severity": "warning",
                    "message": "PG has open protection orders but no active PG position.",
                    "count": len(protection_orders),
                }
            )
        if exchange.get("included") and reduce_only_exchange and not exchange_positions:
            warnings.append(
                {
                    "code": "exchange_orphan_reduce_only_order",
                    "severity": "warning",
                    "message": "Exchange has reduce-only protection orders but no visible position.",
                    "count": len(reduce_only_exchange),
                }
            )
        if exchange.get("included") and protection_orders:
            exchange_ids = {
                str(item.get("exchange_order_id"))
                for item in exchange_orders
                if item.get("exchange_order_id") is not None
            }
            missing = [
                item for item in protection_orders
                if item.get("exchange_order_id") and str(item.get("exchange_order_id")) not in exchange_ids
            ]
            if missing:
                warnings.append(
                    {
                        "code": "pg_protection_missing_on_exchange",
                        "severity": "warning",
                        "message": "Some PG protection orders are not visible in exchange open-order reads.",
                        "order_ids": [item.get("order_id") for item in missing],
                    }
                )

    def _freshness(self, snap: TradingConsoleSnapshot) -> dict[str, Any]:
        exchange = snap.exchange
        status = "fresh"
        if snap.unavailable:
            status = "degraded"
        if snap.warnings:
            status = "warning" if status == "fresh" else "degraded"
        if not snap.include_exchange:
            status = "not_live_connected"
        return {
            "last_updated_at": _iso_ms(snap.generated_at_ms),
            "exchange_snapshot_at": (
                _iso_ms(exchange.get("exchange_snapshot_at"))
                if exchange.get("exchange_snapshot_at")
                else None
            ),
            "freshness_status": status,
            "exchange_error": exchange.get("exchange_error"),
        }

    def _consistency_summary(self, snap: TradingConsoleSnapshot) -> dict[str, Any]:
        classified = self._classify_orders(snap)
        return {
            "order_classification_counts": _count_by(classified, "classification"),
            "pg_open_order_count": len(snap.pg_open_orders),
            "pg_position_count": len(snap.pg_positions),
            "exchange_open_order_count": len(snap.exchange.get("open_orders", [])),
            "exchange_position_count": len(snap.exchange.get("positions", [])),
            "status": "degraded" if snap.warnings or snap.unavailable else "consistent",
        }

    def _classify_orders(self, snap: TradingConsoleSnapshot) -> list[dict[str, Any]]:
        exchange_orders = snap.exchange.get("open_orders", [])
        exchange_by_id = {
            str(item.get("exchange_order_id")): item
            for item in exchange_orders
            if item.get("exchange_order_id") is not None
        }
        pg_by_exchange_id = {
            str(item.get("exchange_order_id")): item
            for item in snap.pg_orders
            if item.get("exchange_order_id") is not None
        }
        exchange_positions = snap.exchange.get("positions", [])
        items: list[dict[str, Any]] = []
        for order in snap.pg_orders:
            exchange_id = order.get("exchange_order_id")
            exchange_match = exchange_by_id.get(str(exchange_id)) if exchange_id is not None else None
            role = str(order.get("order_role") or "")
            classification = "unknown"
            if exchange_match is not None:
                classification = "matched"
                if _normalized_status(order.get("status")) != _normalized_status(exchange_match.get("status")):
                    classification = "mismatch"
            elif snap.include_exchange and str(order.get("status")) in OPEN_ORDER_STATUSES:
                classification = "pg_only"
            elif not snap.include_exchange:
                classification = "pg_unchecked"
            if (
                role in PROTECTION_ROLES
                and snap.include_exchange
                and not exchange_positions
                and str(order.get("status")) in OPEN_ORDER_STATUSES
            ):
                classification = "orphan_protection"
            item = dict(order)
            item["classification"] = classification
            item["exchange_match"] = exchange_match
            item["client_order_id"] = "not_available"
            items.append(item)
        for exchange_id, exchange_order in exchange_by_id.items():
            if exchange_id in pg_by_exchange_id:
                continue
            item = dict(exchange_order)
            item["classification"] = (
                "orphan_protection"
                if not exchange_positions and _truthy(exchange_order.get("reduce_only"))
                else "exchange_only"
            )
            item["pg_match"] = None
            item["client_order_id"] = "not_available"
            items.append(item)
        return items

    def _order_groups(self, orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_parent: dict[str, list[dict[str, Any]]] = {}
        roots: list[dict[str, Any]] = []
        by_id = {str(item.get("order_id")): item for item in orders if item.get("order_id")}
        for order in orders:
            parent = order.get("parent_order_id")
            if parent:
                by_parent.setdefault(str(parent), []).append(order)
            else:
                roots.append(order)
        for order in orders:
            if order.get("order_id") and str(order.get("order_id")) not in {
                str(item.get("order_id")) for item in roots
            } and not order.get("parent_order_id"):
                roots.append(order)
        groups = []
        for root in roots:
            order_id = str(root.get("order_id"))
            children = by_parent.get(order_id, [])
            groups.append(
                {
                    "entry_order": root,
                    "protection_orders": children,
                    "parent_order_id": order_id,
                    "oco_group_ids": sorted({str(item.get("oco_group_id")) for item in children if item.get("oco_group_id")}),
                    "has_entry": order_id in by_id,
                    "tp_count": sum(1 for item in children if str(item.get("order_role", "")).startswith("TP")),
                    "sl_count": sum(1 for item in children if item.get("order_role") == "SL"),
                }
            )
        return groups

    def _protection_summary(self, snap: TradingConsoleSnapshot) -> dict[str, Any]:
        classified = self._classify_orders(snap)
        protection = [
            item for item in classified
            if str(item.get("order_role")) in PROTECTION_ROLES
            or _truthy(item.get("reduce_only"))
        ]
        positions = snap.exchange.get("positions") if snap.include_exchange else snap.pg_positions
        active_position_signal_ids = {
            str(item.get("signal_id"))
            for item in snap.pg_positions
            if item.get("signal_id")
        }
        active_position_symbols = {
            str(item.get("symbol"))
            for item in positions
            if item.get("symbol")
        }
        active_protection = [
            item for item in protection
            if str(item.get("status")) in OPEN_ORDER_STATUSES
        ]
        current_scope_active = [
            item for item in active_protection
            if (
                item.get("signal_id")
                and str(item.get("signal_id")) in active_position_signal_ids
            )
            or (
                not active_position_signal_ids
                and item.get("symbol")
                and str(item.get("symbol")) in active_position_symbols
            )
        ]
        historical_protection = [
            item for item in protection
            if item not in current_scope_active
        ]
        orphan_protection = [
            item for item in active_protection
            if item not in current_scope_active
        ]

        tp = [
            item for item in current_scope_active
            if str(item.get("order_role", "")).startswith("TP")
        ]
        sl = [
            item for item in current_scope_active
            if item.get("order_role") == "SL" or item.get("source") == "exchange_stop"
        ]
        if orphan_protection and not positions:
            status = "orphaned"
        elif positions and tp and sl:
            status = "protected"
        elif positions and (tp or sl):
            status = "partially_protected"
        elif positions:
            status = "unprotected"
        else:
            status = "unknown"
        return {
            "status": status,
            "protection_orders": protection,
            "current_scope_active_protection": current_scope_active,
            "current_scope_protection": current_scope_active,
            "historical_protection_orders": historical_protection,
            "orphan_protection_orders": orphan_protection,
            "active_position_count": len(positions or []),
            "tp_count": len(tp),
            "sl_count": len(sl),
            "historical_tp_count": sum(
                1 for item in historical_protection
                if str(item.get("order_role", "")).startswith("TP")
            ),
            "historical_sl_count": sum(
                1 for item in historical_protection
                if item.get("order_role") == "SL" or item.get("source") == "exchange_stop"
            ),
            "findings": [
                warning for warning in snap.warnings
                if "protection" in warning.get("code", "") or "reduce_only" in warning.get("code", "")
            ],
            "actions_exposed": [],
            "deferred_actions": ["retry_protection", "cancel_protection"],
        }

    def _merge_positions_for_risk(self, snap: TradingConsoleSnapshot) -> list[dict[str, Any]]:
        positions = []
        for item in snap.pg_positions:
            merged = dict(item)
            merged["source"] = "pg"
            merged["system_owned"] = bool(item.get("signal_id"))
            merged["protection_status"] = self._protection_summary(snap).get("status")
            positions.append(merged)
        for item in snap.exchange.get("positions", []):
            merged = dict(item)
            merged["source"] = "exchange"
            merged["system_owned"] = any(
                pg.get("symbol") == item.get("symbol")
                for pg in snap.pg_positions
            )
            merged["protection_status"] = self._protection_summary(snap).get("status")
            positions.append(merged)
        return positions

    @staticmethod
    def _filter_chain_orders(
        orders: list[dict[str, Any]],
        *,
        order_id: Optional[str],
        exchange_order_id: Optional[str],
        runtime_instance_id: Optional[str],
        trial_binding_id: Optional[str],
        strategy_family_id: Optional[str],
        strategy_family_version_id: Optional[str],
        signal_evaluation_id: Optional[str],
        order_candidate_id: Optional[str],
    ) -> list[dict[str, Any]]:
        semantic_filters = {
            "runtime_instance_id": runtime_instance_id,
            "trial_binding_id": trial_binding_id,
            "strategy_family_id": strategy_family_id,
            "strategy_family_version_id": strategy_family_version_id,
            "signal_evaluation_id": signal_evaluation_id,
            "order_candidate_id": order_candidate_id,
        }
        active_semantic_filters = {
            key: value for key, value in semantic_filters.items() if value is not None
        }
        if not order_id and not exchange_order_id and not active_semantic_filters:
            return orders
        matched = []
        parent_ids = set()
        for order in orders:
            if (
                (order_id and order.get("order_id") == order_id)
                or (exchange_order_id and str(order.get("exchange_order_id")) == str(exchange_order_id))
                or any(
                    str(order.get(key)) == str(value)
                    for key, value in active_semantic_filters.items()
                )
            ):
                matched.append(order)
                if order.get("parent_order_id"):
                    parent_ids.add(str(order.get("parent_order_id")))
                if order.get("order_id"):
                    parent_ids.add(str(order.get("order_id")))
        if not parent_ids:
            return matched
        return [
            order for order in orders
            if str(order.get("order_id")) in parent_ids
            or str(order.get("parent_order_id")) in parent_ids
        ]

    @staticmethod
    def _filter_chain_intents(
        intents: list[dict[str, Any]],
        *,
        authorization_id: Optional[str],
        runtime_instance_id: Optional[str],
        trial_binding_id: Optional[str],
        strategy_family_id: Optional[str],
        strategy_family_version_id: Optional[str],
        signal_evaluation_id: Optional[str],
        order_candidate_id: Optional[str],
        intent_id: Optional[str],
        order_ids: set[str],
        exchange_order_ids: set[str],
    ) -> list[dict[str, Any]]:
        semantic_filters = {
            "runtime_instance_id": runtime_instance_id,
            "trial_binding_id": trial_binding_id,
            "strategy_family_id": strategy_family_id,
            "strategy_family_version_id": strategy_family_version_id,
            "signal_evaluation_id": signal_evaluation_id,
            "order_candidate_id": order_candidate_id,
        }
        active_semantic_filters = {
            key: value for key, value in semantic_filters.items() if value is not None
        }
        if (
            not authorization_id
            and not intent_id
            and not order_ids
            and not exchange_order_ids
            and not active_semantic_filters
        ):
            return intents
        return [
            intent for intent in intents
            if (authorization_id and intent.get("authorization_id") == authorization_id)
            or any(
                str(intent.get(key)) == str(value)
                for key, value in active_semantic_filters.items()
            )
            or (intent_id and intent.get("intent_id") == intent_id)
            or (intent.get("order_id") and str(intent.get("order_id")) in order_ids)
            or (
                intent.get("exchange_order_id")
                and str(intent.get("exchange_order_id")) in exchange_order_ids
            )
        ]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _latest_existing_path(directory: Path, pattern: str) -> Optional[Path]:
    try:
        paths = [path for path in directory.expanduser().glob(pattern) if path.is_file()]
    except OSError:
        return None
    if not paths:
        return None
    return max(paths, key=lambda path: path.stat().st_mtime)


def _file_mtime_ms(path: Path) -> Optional[int]:
    if not path.exists():
        return None
    try:
        return int(path.stat().st_mtime * 1000)
    except OSError:
        return None


def _iso_ms(value: Optional[int]) -> Optional[str]:
    if value is None:
        return None
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _is_expired(value: Any) -> bool:
    if value in {None, "", "not_available"}:
        return False
    try:
        return int(value) <= _now_ms()
    except (TypeError, ValueError):
        return False


def _scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in {None, "", "not_available", "unknown"}:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _plain_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    result: dict[str, Any] = {}
    for key in dir(value):
        if key.startswith("_"):
            continue
        try:
            attr = getattr(value, key)
        except Exception:
            continue
        if inspect.ismethod(attr) or inspect.isfunction(attr) or inspect.iscoroutinefunction(attr):
            continue
        if isinstance(attr, (str, int, float, bool, Decimal, Enum, type(None), list, tuple, dict)):
            result[key] = _json_value(attr)
    return result


def _live_lifecycle_review_record(
    review: dict[str, Any],
) -> BrcLiveLifecycleReviewRecord:
    payload = dict(review)
    payload.setdefault("created_at_ms", 0)
    payload.setdefault("updated_at_ms", payload["created_at_ms"])
    return BrcLiveLifecycleReviewRecord.model_validate(payload)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return value


def _authorization_future_action_slots() -> dict[str, str]:
    return {
        "void_authorization": "deferred_not_implemented",
        "cancel_authorization": "deferred_not_implemented",
    }


def _normalize_action_entry_market_input(value: Optional[dict[str, Any]]) -> dict[str, Any]:
    value = value or {}
    regime = _normalized_market_regime(value.get("regime"))
    side = _optional_nonempty_str(value.get("side"))
    symbol_preference = _optional_nonempty_str(value.get("symbol_preference"))
    preferred_strategy_family = _normalized_preferred_strategy_family(
        value.get("preferred_strategy_family")
    )
    risk_tier = _normalized_risk_tier(value.get("risk_tier"))
    owner_risk_acceptance = _normalized_owner_risk_acceptance(
        value.get("owner_risk_acceptance")
    )
    note = _optional_nonempty_str(value.get("note"))
    if note is not None and len(note) > 500:
        note = f"{note[:500]}..."
    mapped_family = _market_regime_family(regime)
    if preferred_strategy_family is not None:
        mapped_family = preferred_strategy_family
    return {
        "regime": regime,
        "mapped_family": mapped_family,
        "symbol_preference": symbol_preference,
        "preferred_strategy_family": preferred_strategy_family,
        "side": side,
        "risk_tier": risk_tier,
        "owner_risk_acceptance": owner_risk_acceptance,
        "owner_risk_acceptance_recorded": owner_risk_acceptance == "accepted",
        "note": note,
        "source": "owner_input_query",
        "persisted": False,
    }


def _action_entry_snapshot_symbol(owner_scope: Optional[dict[str, Any]]) -> str:
    if isinstance(owner_scope, dict) and owner_scope.get("symbol"):
        return str(owner_scope["symbol"])
    return DEFAULT_SYMBOL


def _normalized_market_regime(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "trend": "trend",
        "trending": "trend",
        "volatility": "volatility_expansion",
        "volatility_expansion": "volatility_expansion",
        "vol_expansion": "volatility_expansion",
        "mean_reversion": "mean_reversion",
        "meanreversion": "mean_reversion",
        "range": "mean_reversion",
        "ranging": "mean_reversion",
        "range_bound": "mean_reversion",
        "sideways": "mean_reversion",
        "震荡": "mean_reversion",
        "区间": "mean_reversion",
    }
    return aliases.get(normalized, "not_selected")


def _normalized_risk_tier(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "low": "tiny",
        "micro": "tiny",
        "tiny": "tiny",
        "small": "small",
        "medium": "small",
        "custom": "custom",
    }
    return aliases.get(normalized, "tiny")


def _market_regime_family(regime: str) -> Optional[str]:
    return {
        "trend": "Trend",
        "volatility_expansion": "Volatility expansion",
        "mean_reversion": "Mean reversion",
    }.get(regime)


def _normalized_preferred_strategy_family(value: Any) -> Optional[str]:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "trend": "Trend",
        "tf": "Trend",
        "trend_following": "Trend",
        "mean_reversion": "Mean reversion",
        "mr": "Mean reversion",
        "range": "Mean reversion",
        "ranging": "Mean reversion",
        "sideways": "Mean reversion",
        "volatility": "Volatility expansion",
        "volatility_expansion": "Volatility expansion",
        "vol_expansion": "Volatility expansion",
    }
    return aliases.get(normalized)


def _normalized_owner_risk_acceptance(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"accepted", "accept", "true", "yes", "owner_accepted"}:
        return "accepted"
    if normalized in {"declined", "decline", "false", "no", "rejected"}:
        return "declined"
    return "not_recorded"


def _optional_nonempty_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _owner_budget_selection_from(
    *,
    owner_scope: dict[str, Any],
    market_input: dict[str, Any],
) -> dict[str, Any]:
    return {
        "family": owner_scope.get("family") or market_input.get("mapped_family"),
        "carrier_id": owner_scope.get("carrier_id"),
        "symbol": owner_scope.get("symbol"),
        "symbol_preference": market_input.get("symbol_preference"),
        "side": owner_scope.get("side") or market_input.get("side"),
        "quantity": owner_scope.get("quantity"),
        "target_notional_usdt": owner_scope.get("target_notional_usdt"),
        "current_price": owner_scope.get("current_price"),
        "min_notional": owner_scope.get("min_notional"),
        "min_qty": owner_scope.get("min_qty"),
        "qty_step": owner_scope.get("qty_step"),
        "price_tick": owner_scope.get("price_tick"),
        "max_notional": owner_scope.get("max_notional"),
        "leverage": owner_scope.get("leverage"),
        "max_attempts": owner_scope.get("max_attempts"),
        "protection_mode": owner_scope.get("protection_mode"),
        "review_requirement": owner_scope.get("review_requirement"),
    }


def _apply_owner_selection_to_generic_action_specs(
    *,
    specs: list[dict[str, Any]],
    owner_selection: dict[str, Any],
    envelope: dict[str, Any],
) -> list[dict[str, Any]]:
    selected_symbol = _normalized_action_symbol(
        owner_selection.get("selected_symbol")
        or owner_selection.get("symbol")
        or owner_selection.get("symbol_preference")
    )
    selected_side = _normalized_action_side(owner_selection.get("selected_side") or owner_selection.get("side"))
    selected_quantity = _optional_nonempty_str(
        owner_selection.get("selected_quantity") or owner_selection.get("quantity")
    )
    selected_target_notional = _optional_nonempty_str(
        owner_selection.get("selected_target_notional_usdt")
        or owner_selection.get("target_notional_usdt")
    )
    selected_max_notional = _optional_nonempty_str(
        owner_selection.get("selected_max_notional") or owner_selection.get("max_notional")
    )
    selected_leverage = _optional_nonempty_str(
        owner_selection.get("selected_leverage") or owner_selection.get("leverage")
    )
    selected_max_attempts = _optional_int_value(
        owner_selection.get("selected_max_attempts") or owner_selection.get("max_attempts")
    )
    selected_protection_mode = _optional_nonempty_str(
        owner_selection.get("selected_protection_mode") or owner_selection.get("protection_mode")
    )
    selected_review_requirement = _optional_nonempty_str(
        owner_selection.get("selected_review_requirement") or owner_selection.get("review_requirement")
    )
    has_owner_values = any(
        value is not None
        for value in [
            selected_symbol,
            selected_side,
            selected_quantity,
            selected_target_notional,
            selected_max_notional,
            selected_leverage,
            selected_max_attempts,
            selected_protection_mode,
            selected_review_requirement,
        ]
    )
    if not has_owner_values:
        return specs
    selected_family = _optional_nonempty_str(owner_selection.get("family"))
    selected_carrier_id = _optional_nonempty_str(owner_selection.get("carrier_id"))
    result: list[dict[str, Any]] = []
    for spec in specs:
        item = dict(spec)
        applies_to_spec = (
            bool(selected_carrier_id and item.get("carrier_id") == selected_carrier_id)
            or bool(selected_family and item.get("family") == selected_family)
            or not selected_family and not selected_carrier_id
        )
        if not applies_to_spec:
            result.append(item)
            continue
        catalog_hard_blockers = [
            str(value) for value in item.get("hard_blockers") or []
        ]
        selection_hard_blockers: list[str] = []
        warnings = [str(value) for value in item.get("warnings") or []]
        owner_scope = {
            "symbol": selected_symbol,
            "side": selected_side,
            "quantity": selected_quantity,
            "target_notional_usdt": selected_target_notional,
            "max_notional": selected_max_notional,
            "leverage": selected_leverage,
            "max_attempts": selected_max_attempts,
            "protection_mode": selected_protection_mode,
            "review_requirement": selected_review_requirement,
        }
        if selected_symbol is not None:
            item["symbol"] = selected_symbol
            mapped_carrier_id = owner_action_carrier_id_for_symbol(
                _optional_nonempty_str(item.get("carrier_id")),
                selected_symbol,
            )
            if mapped_carrier_id:
                item["carrier_id"] = mapped_carrier_id
        if selected_side is not None:
            item["side"] = selected_side
        sizing_mode = _optional_nonempty_str(item.get("sizing_mode")) or "fixed_quantity"
        if selected_quantity is not None:
            item["quantity"] = selected_quantity
            item["recommended_quantity"] = selected_quantity
        if selected_target_notional is not None:
            item["target_notional_usdt"] = selected_target_notional
        if selected_max_notional is not None:
            item["max_notional"] = selected_max_notional
            item["recommended_max_notional"] = selected_max_notional
        if selected_leverage is not None:
            item["leverage"] = selected_leverage
        if selected_max_attempts is not None:
            item["max_attempts"] = selected_max_attempts
        if selected_protection_mode is not None:
            item["protection_mode"] = selected_protection_mode
        if selected_review_requirement is not None:
            item["review_requirement"] = selected_review_requirement

        supported_symbols = [str(value) for value in item.get("supported_symbols") or []]
        supported_sides = [str(value).lower() for value in item.get("supported_sides") or []]
        if selected_symbol and supported_symbols and selected_symbol not in supported_symbols:
            selection_hard_blockers.append("owner_symbol_not_supported_by_carrier")
        if selected_side and supported_sides and selected_side not in supported_sides:
            selection_hard_blockers.append("owner_side_not_supported_by_carrier")
        envelope_max_notional = _decimal_or_none(envelope.get("max_notional_per_action"))
        owner_max_notional = _decimal_or_none(selected_max_notional)
        if (
            owner_max_notional is not None
            and envelope_max_notional is not None
            and owner_max_notional > envelope_max_notional
        ):
            selection_hard_blockers.append("owner_max_notional_exceeds_budget_envelope")
        envelope_leverage = _decimal_or_none(envelope.get("max_leverage"))
        owner_leverage = _decimal_or_none(selected_leverage)
        if (
            owner_leverage is not None
            and envelope_leverage is not None
            and owner_leverage > envelope_leverage
        ):
            selection_hard_blockers.append("owner_leverage_exceeds_budget_envelope")
        envelope_max_attempts = _optional_int_value(envelope.get("max_attempts"))
        if (
            selected_max_attempts is not None
            and envelope_max_attempts is not None
            and selected_max_attempts > envelope_max_attempts
        ):
            selection_hard_blockers.append("owner_max_attempts_exceeds_budget_envelope")
        if selected_protection_mode and selected_protection_mode != "single_tp_plus_sl":
            selection_hard_blockers.append("owner_protection_mode_not_supported")
        market_rules = _market_rules_from_owner_selection(owner_selection, selected_symbol or item.get("symbol"))
        if sizing_mode == "notional_derived" and not selected_target_notional:
            selection_hard_blockers.append(
                "target_notional_required_for_notional_sized_carrier"
            )
        if selected_target_notional and market_rules is not None:
            try:
                sizing = compute_notional_sizing(
                    symbol=str(selected_symbol or item.get("symbol") or ""),
                    side=_normalized_action_side(selected_side or item.get("side")) or "long",
                    target_notional_usdt=Decimal(selected_target_notional),
                    max_notional_usdt=owner_max_notional,
                    market_rules=market_rules,
                )
                item["quantity"] = str(sizing.computed_quantity)
                item["computed_quantity"] = str(sizing.computed_quantity)
                item["recommended_quantity"] = str(sizing.computed_quantity)
                item["estimated_notional_usdt"] = str(sizing.estimated_notional_usdt)
                item["suggested_minimum_notional_usdt"] = str(sizing.suggested_minimum_notional_usdt)
                item["suggested_quantity"] = str(sizing.suggested_quantity)
                item["market_rule_snapshot"] = sizing.market_rule_snapshot.model_dump(mode="json")
                item["validation_result"] = sizing.validation.model_dump(mode="json")
                warnings.extend(sizing.warnings)
                selection_hard_blockers.extend(sizing.blockers)
            except Exception:
                selection_hard_blockers.append("notional_sizing_failed")
        elif selected_quantity and market_rules is not None:
            try:
                sizing = validate_fixed_quantity_scope(
                    symbol=str(selected_symbol or item.get("symbol") or ""),
                    side=_normalized_action_side(selected_side or item.get("side")) or "long",
                    quantity=Decimal(selected_quantity),
                    max_notional_usdt=owner_max_notional,
                    market_rules=market_rules,
                )
                item["computed_quantity"] = str(sizing.computed_quantity)
                item["estimated_notional_usdt"] = str(sizing.estimated_notional_usdt)
                item["suggested_minimum_notional_usdt"] = str(sizing.suggested_minimum_notional_usdt)
                item["suggested_quantity"] = str(sizing.suggested_quantity)
                item["market_rule_snapshot"] = sizing.market_rule_snapshot.model_dump(mode="json")
                item["validation_result"] = sizing.validation.model_dump(mode="json")
                warnings.extend(sizing.warnings)
                selection_hard_blockers.extend(sizing.blockers)
            except Exception:
                selection_hard_blockers.append("quantity_market_rule_validation_failed")
        elif selected_target_notional:
            selection_hard_blockers.append("market_rules_missing_for_notional_sizing")
        if not item.get("quantity"):
            warnings.append("owner_quantity_missing")
        if not selected_max_notional:
            warnings.append("owner_max_notional_missing")
        item["owner_selected_scope"] = {
            key: value for key, value in owner_scope.items() if value not in (None, "")
        }
        item["owner_selection_status"] = owner_selection.get("status") or "not_provided"
        item["warnings"] = _dedupe_strings(warnings)
        item["hard_blockers"] = _dedupe_strings(
            [*catalog_hard_blockers, *selection_hard_blockers]
        )
        if (
            item.get("action_registry_supported") is True
            and not selection_hard_blockers
            and all(
                item.get(field) not in (None, "")
                for field in [
                    "carrier_id",
                    "symbol",
                    "side",
                    "quantity",
                    "max_notional",
                    "leverage",
                    "max_attempts",
                    "protection_mode",
                    "review_requirement",
                ]
            )
        ):
            item["status"] = "valid_blocked_final_gate"
        elif selection_hard_blockers:
            item["status"] = "invalid_blocked"
        item["backend_actionable"] = False
        item["frontend_action_enabled"] = False
        item["places_order"] = False
        result.append(item)
    return result


def _apply_owner_selection_to_action_candidates(
    *,
    candidates: list[dict[str, Any]],
    generic_specs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        carrier_id = item.get("carrier_id")
        family = item.get("family")
        spec = (
            _first_match(generic_specs, lambda value: carrier_id and value.get("carrier_id") == carrier_id)
            or _first_match(generic_specs, lambda value: family and value.get("family") == family)
            or {}
        )
        sizing = dict(item.get("recommended_sizing") or {})
        sizing["owner_selected_scope"] = dict(spec.get("owner_selected_scope") or {})
        sizing["owner_selection_status"] = spec.get("owner_selection_status")
        sizing["hard_blockers"] = list(spec.get("hard_blockers") or [])
        sizing["warnings"] = list(spec.get("warnings") or [])
        sizing["action_allowed"] = False
        item["recommended_sizing"] = sizing
        item["frontend_action_enabled"] = False
        item["may_execute_live"] = False
        result.append(item)
    return result


def _normalized_action_symbol(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    aliases = {
        "BTC": "BTC/USDT:USDT",
        "BTCUSDT": "BTC/USDT:USDT",
        "BTC/USDT": "BTC/USDT:USDT",
        "ETH": "ETH/USDT:USDT",
        "ETHUSDT": "ETH/USDT:USDT",
        "ETH/USDT": "ETH/USDT:USDT",
        "SOL": "SOL/USDT:USDT",
        "SOLUSDT": "SOL/USDT:USDT",
        "SOL/USDT": "SOL/USDT:USDT",
        "BNB": "BNB/USDT:USDT",
        "BNBUSDT": "BNB/USDT:USDT",
        "BNB/USDT": "BNB/USDT:USDT",
    }
    return aliases.get(text, text)


def _normalized_action_side(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"buy", "long"}:
        return "long"
    if text in {"sell", "short"}:
        return "short"
    return text or None


def _optional_int_value(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal_or_none(value: Any) -> Optional[Decimal]:
    if value in (None, "", "not_available"):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _market_rules_from_owner_selection(
    owner_selection: dict[str, Any],
    symbol: Any,
) -> ContractMarketRules | None:
    selected_symbol = _optional_nonempty_str(symbol)
    current_price = _decimal_or_none(owner_selection.get("current_price"))
    min_notional = _decimal_or_none(owner_selection.get("min_notional"))
    min_qty = _decimal_or_none(owner_selection.get("min_qty"))
    qty_step = _decimal_or_none(owner_selection.get("qty_step"))
    price_tick = _decimal_or_none(owner_selection.get("price_tick"))
    if (
        selected_symbol is None
        or current_price is None
        or min_notional is None
        or min_qty is None
        or qty_step is None
    ):
        return None
    return ContractMarketRules(
        symbol=selected_symbol,
        min_notional=min_notional,
        min_qty=min_qty,
        qty_step=qty_step,
        price_tick=price_tick,
        current_price=current_price,
        freshness="fresh",
        source="owner_action_flow_market_rule_input",
    )


def _select_action_entry_candidate(
    *,
    market_input: dict[str, Any],
    owner_scope: dict[str, Any],
    candidate_output: list[dict[str, Any]],
    generic_action_specs: list[dict[str, Any]],
    payload_contracts: list[dict[str, Any]],
    action_entry_output: list[dict[str, Any]],
) -> dict[str, Any]:
    family = _optional_nonempty_str(owner_scope.get("family")) or market_input.get("mapped_family")
    carrier_id = _optional_nonempty_str(owner_scope.get("carrier_id"))
    selected_family = family or "Trend"

    def match(item: dict[str, Any]) -> bool:
        if carrier_id and item.get("carrier_id") == carrier_id:
            return True
        return bool(selected_family and item.get("family") == selected_family)

    candidate = _first_match(candidate_output, match) or _first_match(candidate_output, lambda item: item.get("family") == "Trend") or {}
    if candidate.get("family"):
        selected_family = str(candidate["family"])
    if candidate.get("carrier_id"):
        carrier_id = str(candidate["carrier_id"])

    def selected_match(item: dict[str, Any]) -> bool:
        if carrier_id and item.get("carrier_id") == carrier_id:
            return True
        return bool(selected_family and item.get("family") == selected_family)

    action_spec = _first_match(generic_action_specs, selected_match) or {}
    payload_contract = _first_match(payload_contracts, selected_match) or {}
    action_entry = _first_match(action_entry_output, selected_match) or {}
    required_scope = dict(payload_contract.get("required_owner_scope") or {})
    for field in [
        "symbol",
        "side",
        "quantity",
        "max_notional",
        "leverage",
        "max_attempts",
        "protection_mode",
        "review_requirement",
    ]:
        if action_spec.get(field) not in (None, ""):
            required_scope[field] = action_spec.get(field)
    return {
        "family": selected_family,
        "strategy_family_id": (
            candidate.get("strategy_family_id")
            or action_spec.get("strategy_family_id")
            or action_entry.get("strategy_family_id")
        ),
        "carrier_id": carrier_id,
        "candidate": candidate,
        "generic_action_spec": action_spec,
        "payload_contract": payload_contract,
        "action_entry": action_entry,
        "scope_review": _action_entry_scope_review(
            owner_scope=owner_scope,
            required_scope=required_scope,
        ),
    }


def _first_match(items: list[dict[str, Any]], predicate: Any) -> Optional[dict[str, Any]]:
    for item in items:
        if predicate(item):
            return item
    return None


def _action_entry_scope_review(
    *,
    owner_scope: dict[str, Any],
    required_scope: dict[str, Any],
) -> dict[str, Any]:
    required_fields = [
        "symbol",
        "side",
        "quantity",
        "max_notional",
        "leverage",
        "max_attempts",
        "protection_mode",
        "review_requirement",
    ]
    provided = {
        key: owner_scope.get(key)
        for key in required_fields
        if owner_scope.get(key) not in (None, "")
    }
    missing = [key for key in required_fields if required_scope.get(key) in (None, "")]
    if not provided:
        verdict = "not_checked"
        mismatches: list[dict[str, Any]] = []
    else:
        mismatches = [
            {
                "field": key,
                "expected": required_scope.get(key),
                "provided": owner_scope.get(key),
            }
            for key in required_fields
            if required_scope.get(key) not in (None, "")
            and owner_scope.get(key) not in (None, "")
            and str(owner_scope.get(key)) != str(required_scope.get(key))
        ]
        verdict = "matched" if not mismatches and not missing else "mismatch"
    return {
        "verdict": verdict,
        "required_scope": required_scope,
        "provided_scope": provided,
        "missing_required_template_fields": missing,
        "mismatches": mismatches,
    }


def _action_entry_risk_review(
    *,
    selected_candidate: dict[str, Any],
    adapter_contract: dict[str, Any],
    blockers: list[dict[str, Any]],
    market_input: dict[str, Any],
) -> dict[str, Any]:
    action_spec = dict(selected_candidate.get("generic_action_spec") or {})
    risk_classifications = _dedupe_strings(
        [str(item) for item in action_spec.get("risk_disclosure_classifications") or []]
    )
    raw_owner_acceptance = str(market_input.get("owner_risk_acceptance") or "not_recorded")
    owner_acceptance_status = (
        raw_owner_acceptance
        if raw_owner_acceptance in {"accepted", "declined"}
        else str(action_spec.get("owner_risk_acceptance_status") or "required")
    )
    owner_acceptance_recorded = owner_acceptance_status == "accepted"
    warnings = _dedupe_strings(
        [
            *[str(item) for item in action_spec.get("warnings") or []],
            *risk_classifications,
            *[str(item) for item in adapter_contract.get("warning_not_blocker") or []],
        ]
    )
    execution_safety_blockers = [
        item
        for item in blockers
        if item.get("severity", "hard_blocker") == "hard_blocker"
    ]
    hard_blockers = _dedupe_strings(
        [
            *[str(item) for item in action_spec.get("hard_blockers") or []],
            *[
                str(item.get("code") or item.get("message"))
                for item in execution_safety_blockers
            ],
        ]
    )
    return {
        "warning_policy": "warnings_require_owner_review_but_do_not_enable_action",
        "weak_strategy_evidence_policy": "warning_not_hard_blocker",
        "research_quality_status": action_spec.get("research_quality_status") or "warning",
        "risk_disclosure_classifications": risk_classifications,
        "owner_risk_acceptance_required": bool(
            action_spec.get("owner_risk_acceptance_required", True)
        ),
        "owner_risk_acceptance_status": owner_acceptance_status,
        "owner_risk_acceptance_recorded": owner_acceptance_recorded,
        "owner_risk_acceptance_source": "owner_input_query" if owner_acceptance_recorded else "not_recorded",
        "owner_risk_acceptance_disclosure": (
            "Owner accepted strategy-family research weakness as a warning only; "
            "execution safety gates remain hard blockers."
            if owner_acceptance_recorded
            else "Strategy-family research weakness remains disclosed as a warning."
        ),
        "owner_risk_acceptance_may_override": [
            str(item)
            for item in action_spec.get("owner_risk_acceptance_may_override") or []
        ],
        "owner_risk_acceptance_never_overrides": [
            str(item)
            for item in action_spec.get("owner_risk_acceptance_never_overrides") or []
        ],
        "owner_risk_acceptance_cannot_override_execution_safety_gates": bool(
            action_spec.get(
                "owner_risk_acceptance_cannot_override_execution_safety_gates",
                True,
            )
        ),
        "warnings": warnings,
        "hard_blockers": hard_blockers,
        "warning_count": len(warnings),
        "hard_blocker_count": len(hard_blockers),
    }


def _action_entry_authorization_draft_path(
    *,
    selected_candidate: dict[str, Any],
    state_dump: dict[str, Any],
) -> dict[str, Any]:
    flow = dict(state_dump.get("api_backed_authorization_flow") or {})
    action_entry = dict(selected_candidate.get("action_entry") or {})
    return {
        "status": "readiness_only_no_draft_created",
        "official_service_path_available": bool(flow.get("operation_steps")),
        "trading_console_direct_action_api": bool(flow.get("trading_console_direct_action_api")),
        "creates_authorization": False,
        "creates_execution_intent": False,
        "places_order": False,
        "required_owner_scope_fields": action_entry.get("required_owner_scope_fields") or [],
        "operation_steps": flow.get("operation_steps") or [],
        "note": "Trading Console prepares the handoff; authorization submit must use the official API path.",
    }


def _action_entry_final_gate_result(
    *,
    selected_candidate: dict[str, Any],
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    action_entry = dict(selected_candidate.get("action_entry") or {})
    action_state = action_entry.get("action_entry_state")
    if action_state == "ready_for_owner_scope_final_gate":
        status = "blocked_until_official_final_gate_passes"
    elif action_state == "proposal_only":
        status = "proposal_only"
    else:
        status = "blocked"
    return {
        "status": status,
        "adapter_status": action_entry.get("final_gate_adapter_status"),
        "blocker_ids": [item.get("code") for item in blockers if item.get("code")],
        "retry_conditions": [
            action_entry.get("owner_decision_text") or "Provide exact Owner scope and rerun final gate.",
        ],
        "evidence_status": "pre_action_evidence_required",
        "may_execute_live": False,
        "frontend_action_enabled": False,
    }


def _action_entry_action_state(selected_candidate: dict[str, Any]) -> dict[str, Any]:
    action_spec = dict(selected_candidate.get("generic_action_spec") or {})
    action_entry = dict(selected_candidate.get("action_entry") or {})
    backend_actionable = (
        action_spec.get("may_execute_live") is True
        and action_spec.get("frontend_action_enabled") is True
        and action_entry.get("may_execute_live") is True
        and action_entry.get("frontend_action_enabled") is True
    )
    return {
        "action_slot": "bounded_execute",
        "enabled": backend_actionable,
        "label": "有界实盘执行",
        "disabled_reason": None if backend_actionable else _action_entry_disabled_reason(action_entry, action_spec),
        "backend_actionable": backend_actionable,
        "backend_actionable_only": backend_actionable,
        "may_execute_live": False,
        "frontend_action_enabled": False,
        "creates_authorization": False,
        "creates_execution_intent": False,
        "places_order": False,
        "mutates_pg": False,
    }


def _action_entry_disabled_reason(action_entry: dict[str, Any], action_spec: dict[str, Any]) -> str:
    if action_entry.get("action_entry_state") == "proposal_only":
        return "该候选仍是提案状态，后端未开放行动能力。"
    if action_spec.get("status") == "valid_blocked_final_gate":
        return "需要 Owner 授权、最终门禁、保护计划和审计证据全部通过。"
    return "当前候选不可行动。"


def _action_entry_post_action_state(snap: TradingConsoleSnapshot) -> dict[str, Any]:
    entry_orders = [
        item for item in snap.pg_orders
        if str(item.get("order_role") or "").lower() in {"entry", "entry_limit", "entry_market"}
    ]
    protection_orders = [
        item for item in snap.pg_orders
        if str(item.get("order_role") or "").upper() in PROTECTION_ROLES
    ]
    completed_intents = [
        item for item in snap.pg_intents
        if str(item.get("status") or "").lower() == "completed"
    ]
    active_signal_ids = _active_position_signal_ids(snap)
    active_authorization_ids = _authorization_ids_for_signals(active_signal_ids)
    lifecycle_entry_orders = _orders_for_active_lifecycle(entry_orders, active_signal_ids)
    lifecycle_protection_orders = _orders_for_active_lifecycle(protection_orders, active_signal_ids)
    lifecycle_live_reviews = _live_reviews_for_active_lifecycle(
        snap.live_lifecycle_reviews,
        active_authorization_ids,
    )
    day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    exchange_state = _post_action_exchange_state(
        snap=snap,
        entry_orders=lifecycle_entry_orders,
        protection_orders=lifecycle_protection_orders,
    )
    review_ledger = _post_action_review_ledger(
        entry_orders=lifecycle_entry_orders,
        protection_orders=lifecycle_protection_orders,
        reviews=snap.review_records,
        live_lifecycle_reviews=lifecycle_live_reviews,
    )
    next_attempt_gate = _post_action_next_attempt_gate(
        snap=snap,
        exchange_state=exchange_state,
        review_ledger=review_ledger,
    )
    return {
        "status": "available" if (snap.pg_intents or snap.pg_orders or snap.review_records or snap.audit_events) else "empty",
        "intent_count": len(snap.pg_intents),
        "completed_intent_count": len(completed_intents),
        "completed_intents_today_by_symbol": _completed_intent_counts_by_symbol_today(
            intents=snap.pg_intents,
            day_key=day_key,
        ),
        "daily_attempt_day_key": day_key,
        "entry_order_count": len(entry_orders),
        "protection_order_count": len(protection_orders),
        "current_lifecycle_signal_ids": sorted(active_signal_ids),
        "current_lifecycle_authorization_ids": sorted(active_authorization_ids),
        "current_lifecycle_entry_order_count": len(lifecycle_entry_orders),
        "current_lifecycle_protection_order_count": len(lifecycle_protection_orders),
        "active_position_count": len(snap.pg_positions),
        "open_order_count": len(snap.pg_open_orders),
        "review_count": len(snap.review_records),
        "live_lifecycle_review_count": len(snap.live_lifecycle_reviews),
        "audit_event_count": len(snap.audit_events),
        "retry_safety": "consumed_authorization_or_completed_intent_blocks_duplicate_execution",
        "exchange_state": exchange_state,
        "review_ledger": review_ledger,
        "next_attempt_gate": next_attempt_gate,
        "summary": {
            "intents": snap.pg_intents[:5],
            "entry_orders": entry_orders[:5],
            "tp_sl_orders": protection_orders[:5],
            "current_lifecycle_entry_orders": lifecycle_entry_orders[:5],
            "current_lifecycle_tp_sl_orders": lifecycle_protection_orders[:5],
            "current_lifecycle_live_lifecycle_reviews": lifecycle_live_reviews[:5],
            "active_positions": snap.pg_positions[:5],
            "open_orders": snap.pg_open_orders[:5],
            "reviews": snap.review_records[:5],
            "live_lifecycle_reviews": snap.live_lifecycle_reviews[:5],
            "audit_events": snap.audit_events[:5],
        },
    }


def _active_position_signal_ids(snap: TradingConsoleSnapshot) -> set[str]:
    signal_ids: set[str] = set()
    for position in snap.pg_positions:
        signal_id = position.get("signal_id")
        if signal_id is not None and str(signal_id):
            signal_ids.add(str(signal_id))
    return signal_ids


def _orders_for_active_lifecycle(
    orders: list[dict[str, Any]],
    active_signal_ids: set[str],
) -> list[dict[str, Any]]:
    if not active_signal_ids:
        return orders
    scoped = [item for item in orders if str(item.get("signal_id") or "") in active_signal_ids]
    return scoped if scoped else orders


def _authorization_ids_for_signals(signal_ids: set[str]) -> set[str]:
    authorization_ids: set[str] = set()
    for signal_id in signal_ids:
        if signal_id.startswith("owner-live-"):
            authorization_ids.add(signal_id.removeprefix("owner-live-"))
    return authorization_ids


def _live_reviews_for_active_lifecycle(
    reviews: list[dict[str, Any]],
    active_authorization_ids: set[str],
) -> list[dict[str, Any]]:
    if not active_authorization_ids:
        return reviews
    scoped = [
        item for item in reviews
        if str(item.get("authorization_id") or "") in active_authorization_ids
    ]
    return scoped


def _post_action_exchange_state(
    *,
    snap: TradingConsoleSnapshot,
    entry_orders: list[dict[str, Any]],
    protection_orders: list[dict[str, Any]],
) -> dict[str, Any]:
    if not snap.include_exchange:
        return {
            "status": "not_checked",
            "included": False,
            "exchange_position_count": 0,
            "exchange_open_protection_count": 0,
            "pg_entry_order_count": len(entry_orders),
            "pg_open_protection_count": len(protection_orders),
            "cleanup_required": False,
        }
    exchange_positions = [
        item for item in snap.exchange.get("positions", [])
        if item.get("symbol") in set(snap.symbols)
    ]
    exchange_protection_orders = [
        item for item in snap.exchange.get("open_orders", [])
        if item.get("symbol") in set(snap.symbols)
        and (_truthy(item.get("reduce_only")) or item.get("source") == "exchange_stop")
    ]
    pg_open_protection = [
        item for item in protection_orders
        if str(item.get("status") or "").upper() in OPEN_ORDER_STATUSES
    ]
    cleanup_required = bool(
        entry_orders
        and pg_open_protection
        and not exchange_positions
        and not exchange_protection_orders
    )
    if cleanup_required:
        status = "pg_open_exchange_flat_cleanup_needed"
    elif exchange_positions and exchange_protection_orders:
        status = "protected_open_on_exchange"
    elif exchange_positions:
        status = "exchange_position_unprotected_or_partially_protected"
    else:
        status = "exchange_flat"
    return {
        "status": status,
        "included": True,
        "exchange_position_count": len(exchange_positions),
        "exchange_open_protection_count": len(exchange_protection_orders),
        "pg_entry_order_count": len(entry_orders),
        "pg_open_protection_count": len(pg_open_protection),
        "cleanup_required": cleanup_required,
        "exchange_error": snap.exchange.get("exchange_error"),
        "retry_condition": (
            "Run official reconciliation/review cleanup so PG and exchange evidence agree."
            if cleanup_required
            else None
        ),
    }


def _post_action_review_ledger(
    *,
    entry_orders: list[dict[str, Any]],
    protection_orders: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    live_lifecycle_reviews: list[dict[str, Any]],
) -> dict[str, Any]:
    entry_order = entry_orders[0] if entry_orders else None
    closed_live_lifecycle_review = next(
        (
            item for item in live_lifecycle_reviews
            if _live_lifecycle_review_is_closed_reviewed(item)
        ),
        None,
    )
    latest_live_lifecycle_review = (
        closed_live_lifecycle_review
        or (live_lifecycle_reviews[0] if live_lifecycle_reviews else None)
    )
    exit_orders = [
        item for item in protection_orders
        if str(item.get("status") or "").upper() in {"FILLED", "CLOSED"}
    ]
    open_protection_orders = [
        item for item in protection_orders
        if str(item.get("status") or "").upper() in {"OPEN", "SUBMITTED", "NEW"}
    ]
    external_hygiene_orders = [
        item for item in protection_orders
        if str(item.get("exit_reason") or "") == "EXTERNAL_CLOSE_LOCAL_HYGIENE"
        and str(item.get("status") or "").upper() in {"CANCELED", "EXPIRED", "CLOSED"}
    ]
    entry_filled = str((entry_order or {}).get("status") or "").upper() in {"FILLED", "CLOSED"}
    if exit_orders and closed_live_lifecycle_review:
        lifecycle_status = "closed_reviewed"
        tp_sl_status = "tp_or_sl_filled"
    elif exit_orders:
        lifecycle_status = "closed_from_pg_exit_order"
        tp_sl_status = "tp_or_sl_filled"
    elif entry_filled and external_hygiene_orders and not open_protection_orders:
        lifecycle_status = "closed_external_exchange_flat_unresolved"
        tp_sl_status = "external_flat_local_hygiene_terminalized"
    elif entry_filled and open_protection_orders:
        lifecycle_status = "protected_open_from_pg_orders"
        tp_sl_status = "protected_open"
    elif entry_filled:
        lifecycle_status = "entry_filled_protection_state_incomplete"
        tp_sl_status = "protection_state_incomplete"
    else:
        lifecycle_status = "not_started_or_unknown"
        tp_sl_status = "not_available"
    return {
        "ledger_version": "owner_bounded_review_ledger_v0",
        "lifecycle_status": lifecycle_status,
        "entry": _post_action_order_ledger_entry(entry_order),
        "exit": _post_action_exit_ledger_entry(exit_orders, external_hygiene_orders),
        "realized_pnl": _post_action_not_available("position_not_closed"),
        "unrealized_pnl": _post_action_not_available("trading_console_default_read_model_does_not_call_exchange"),
        "costs": {
            "fees": _post_action_not_available("fee_fetch_not_integrated"),
            "funding": _post_action_not_available("funding_fetch_not_integrated"),
            "slippage": _post_action_not_available("entry_quote_snapshot_not_available"),
            "total_cost": _post_action_not_available("cost_components_not_available"),
        },
        "tp_sl_result": {
            "status": tp_sl_status,
            "protection_order_count": len(protection_orders),
            "open_protection_order_count": len(open_protection_orders),
        },
        "strategy_outcome": _post_action_strategy_outcome(
            lifecycle_status=lifecycle_status,
            live_lifecycle_review=latest_live_lifecycle_review,
        ),
        "review_decision": {
            "status": _post_action_review_decision_status(
                lifecycle_status=lifecycle_status,
                reviews=reviews,
                live_lifecycle_review=latest_live_lifecycle_review,
            ),
            "allowed_values": ["promote", "revise", "park"],
            "requires_owner_review": lifecycle_status != "closed_reviewed",
            **(
                {"source": "system_reconciliation_review"}
                if lifecycle_status == "closed_external_exchange_flat_unresolved"
                else {}
            ),
            **(
                {
                    "source": "brc_live_lifecycle_reviews",
                    "review_id": latest_live_lifecycle_review.get("review_id"),
                    "review_status": latest_live_lifecycle_review.get("review_status"),
                    "lifecycle_status": latest_live_lifecycle_review.get("lifecycle_status"),
                    "review_decision": (
                        (latest_live_lifecycle_review.get("metadata") or {}).get("review_decision")
                        if isinstance(latest_live_lifecycle_review.get("metadata"), dict)
                        else None
                    ),
                    "attempt_continuation_quality": (
                        (latest_live_lifecycle_review.get("metadata") or {}).get(
                            "attempt_continuation_quality"
                        )
                        if isinstance(latest_live_lifecycle_review.get("metadata"), dict)
                        else None
                    ),
                }
                if latest_live_lifecycle_review
                and lifecycle_status in {"protected_open_from_pg_orders", "closed_reviewed"}
                else {}
            ),
        },
        "live_lifecycle_review": latest_live_lifecycle_review or {},
        "warnings": [
            "fee_not_available",
            "funding_not_available",
            "slippage_not_available",
        ],
        "hard_blockers": [],
}


def _live_lifecycle_review_is_closed_reviewed(review: dict[str, Any]) -> bool:
    return (
        str(review.get("lifecycle_status") or "") == "closed_reviewed"
        and str(review.get("review_status") or "") == "closed_reviewed"
    )


def _post_action_strategy_outcome(
    *,
    lifecycle_status: str,
    live_lifecycle_review: dict[str, Any] | None,
) -> str:
    metadata = (
        live_lifecycle_review.get("metadata")
        if live_lifecycle_review and isinstance(live_lifecycle_review.get("metadata"), dict)
        else {}
    )
    if lifecycle_status == "closed_reviewed":
        return str(metadata.get("strategy_outcome") or "closed_reviewed")
    if lifecycle_status == "closed_from_pg_exit_order":
        return "pending_closed_trade_review"
    if lifecycle_status == "closed_external_exchange_flat_unresolved":
        return "revise_after_external_flat_reconciliation"
    return "pending_post_action_review"


def _post_action_review_decision_status(
    *,
    lifecycle_status: str,
    reviews: list[dict[str, Any]],
    live_lifecycle_review: dict[str, Any] | None,
) -> str:
    if lifecycle_status == "closed_reviewed":
        return "closed_reviewed"
    if lifecycle_status == "closed_external_exchange_flat_unresolved":
        return "revise"
    if lifecycle_status == "protected_open_from_pg_orders":
        return "pending_open_recorded" if live_lifecycle_review else "pending_open_missing"
    return "pending" if reviews else "not_recorded"


def _post_action_next_attempt_gate(
    *,
    snap: TradingConsoleSnapshot,
    exchange_state: dict[str, Any],
    review_ledger: dict[str, Any],
) -> dict[str, Any]:
    exchange_position_count = int(exchange_state.get("exchange_position_count") or 0)
    exchange_open_protection_count = int(exchange_state.get("exchange_open_protection_count") or 0)
    pg_active_position_count = len(snap.pg_positions)
    pg_open_order_count = len(snap.pg_open_orders)
    lifecycle_status = str(review_ledger.get("lifecycle_status") or "not_started_or_unknown")
    blockers: list[dict[str, Any]] = []
    warnings: list[str] = []
    if exchange_state.get("cleanup_required") is True:
        blockers.append(
            {
                "id": "NEXT-ATTEMPT-PG-EXCHANGE-CLEANUP-REQUIRED",
                "stage": "post_action_reconciliation",
                "path": "Owner Action Flow next attempt gate",
                "evidence": "PG open protection exists while exchange is flat/no protection.",
                "severity": "hard_blocker",
                "bridge": "official_reconciliation_or_hygiene_cleanup",
                "retry_condition": "Run official reconciliation/review cleanup until PG and exchange facts agree.",
            }
        )
    if pg_active_position_count or pg_open_order_count or exchange_position_count or exchange_open_protection_count:
        if (
            pg_active_position_count
            and pg_open_order_count
            and (not snap.include_exchange or exchange_position_count)
            and (not snap.include_exchange or exchange_open_protection_count)
        ):
            lifecycle_gate = "current_lifecycle_open_protected"
            lifecycle_classification = "still_open_protected"
            warnings.append("current_position_or_protection_open_no_next_attempt")
            retry_condition = "Wait for the current scoped lifecycle to close, then reconcile PG/exchange and complete review."
            disabled_reason = "Current lifecycle is still open and protected; next bounded-live attempt is blocked until close and review."
        else:
            lifecycle_gate = "position_order_conflict_requires_recovery"
            lifecycle_classification = "inconsistent_requires_recovery"
            retry_condition = "Resolve active position/open order/protection conflict through official recovery before any new attempt."
            disabled_reason = "Position/order/protection facts are inconsistent; recovery is required before any new attempt."
            blockers.append(
                {
                    "id": "NEXT-ATTEMPT-POSITION-ORDER-CONFLICT",
                    "stage": "pre_next_attempt",
                    "path": "Owner Action Flow next attempt gate",
                    "evidence": (
                        f"pg_active_position_count={pg_active_position_count}, "
                        f"pg_open_order_count={pg_open_order_count}, "
                        f"exchange_position_count={exchange_position_count}, "
                        f"exchange_open_protection_count={exchange_open_protection_count}"
                    ),
                    "severity": "hard_blocker",
                    "bridge": "official_reconciliation_or_lifecycle_review",
                    "retry_condition": "PG/exchange position and order counts must be aligned and flat, or current lifecycle must be proven open-protected.",
                }
            )
    elif lifecycle_status == "closed_reviewed":
        lifecycle_gate = "clear_for_next_preflight"
        lifecycle_classification = "closed_reviewed"
        retry_condition = "Create fresh Owner/Budget authorization and rerun official FinalGate for exactly one scoped attempt."
        disabled_reason = None
    elif (
        lifecycle_status == "closed_from_pg_exit_order"
        and review_ledger.get("live_lifecycle_review")
    ):
        lifecycle_gate = "closed_trade_review_required"
        lifecycle_classification = "review_required"
        retry_condition = "Record closed trade live lifecycle review before the next bounded-live attempt."
        disabled_reason = "Closed trade review is required before another bounded-live attempt."
        blockers.append(
            {
                "id": "NEXT-ATTEMPT-CLOSED-TRADE-REVIEW-REQUIRED",
                "stage": "post_action_review",
                "path": "Owner Action Flow next attempt gate",
                "evidence": "PG exit order is filled but brc_live_lifecycle_reviews has not recorded closed_reviewed.",
                "severity": "hard_blocker",
                "bridge": "create_runtime_closed_trade_lifecycle_review",
                "retry_condition": "Append a closed_reviewed live lifecycle review record from resolved order/position/reconciliation facts.",
            }
        )
    elif lifecycle_status in {
        "closed_from_pg_exit_order",
        "closed_external_exchange_flat_unresolved",
        "not_started_or_unknown",
    }:
        lifecycle_gate = "clear_for_next_preflight"
        lifecycle_classification = (
            "external_flat"
            if lifecycle_status == "closed_external_exchange_flat_unresolved"
            else "legacy_closed_no_runtime_review_required"
            if lifecycle_status == "closed_from_pg_exit_order"
            else "no_current_lifecycle"
        )
        retry_condition = "Create fresh Owner/Budget authorization and rerun official FinalGate for exactly one scoped attempt."
        disabled_reason = None
        if lifecycle_status == "closed_external_exchange_flat_unresolved":
            warnings.append("prior_external_flat_cleanup_reviewed")
    else:
        lifecycle_gate = "review_state_incomplete"
        lifecycle_classification = "review_required"
        retry_condition = "Complete or classify post-action Review Ledger before next bounded-live attempt."
        disabled_reason = "Review Ledger is incomplete; complete or classify review before next bounded-live attempt."
        blockers.append(
            {
                "id": "NEXT-ATTEMPT-REVIEW-STATE-INCOMPLETE",
                "stage": "post_action_review",
                "path": "Owner Action Flow next attempt gate",
                "evidence": f"review_ledger.lifecycle_status={lifecycle_status}",
                "severity": "hard_blocker",
                "bridge": "complete_review_ledger",
                "retry_condition": "Review Ledger lifecycle_status must be closed/reviewed, open-protected, or not-started with flat evidence.",
            }
        )
    blocked = bool(blockers) or lifecycle_gate != "clear_for_next_preflight"
    return {
        "gate": lifecycle_gate,
        "status": "blocked" if blocked else "clear_for_preflight",
        "disabled_reason": disabled_reason if blocked else None,
        "backend_owned_state": True,
        "frontend_must_not_infer": True,
        "lifecycle_classification": lifecycle_classification,
        "current_lifecycle_status": lifecycle_status,
        "next_attempt_allowed_by_lifecycle": not blocked,
        "action_allowed": False,
        "may_execute_live": False,
        "frontend_action_enabled": False,
        "requires_official_final_gate": True,
        "pg_active_position_count": pg_active_position_count,
        "pg_open_order_count": pg_open_order_count,
        "exchange_position_count": exchange_position_count,
        "exchange_open_protection_count": exchange_open_protection_count,
        "review_lifecycle_status": lifecycle_status,
        "warnings": warnings,
        "blockers": blockers,
        "retry_condition": retry_condition,
        "required_next_step": (
            "wait_for_current_tp_or_sl_then_reconcile_and_review"
            if lifecycle_gate == "current_lifecycle_open_protected"
            else "official_recovery_required"
            if lifecycle_gate == "position_order_conflict_requires_recovery"
            else "record_closed_trade_review"
            if lifecycle_gate == "closed_trade_review_required"
            else "complete_review_ledger"
            if lifecycle_gate == "review_state_incomplete"
            else "owner_decision_and_final_gate"
        ),
        "blocking_scope": {
            "single_position_policy": True,
            "current_lifecycle_blocks_new_entry": lifecycle_gate == "current_lifecycle_open_protected",
            "allows_new_entry": False,
            "allows_cancel_active_protection": False,
            "allowed_exchange_write": (
                "residual_sibling_protection_cancel_only_after_exchange_flat"
            ),
        },
    }


def _post_action_order_ledger_entry(order: dict[str, Any] | None) -> dict[str, Any]:
    if order is None:
        return {"status": "not_available", "reason": "entry_order_not_recorded"}
    return {
        "status": str(order.get("status") or "unknown").lower(),
        "order_id": order.get("order_id"),
        "exchange_order_id": order.get("exchange_order_id"),
        "quantity": order.get("filled_qty") or order.get("requested_qty"),
        "requested_quantity": order.get("requested_qty"),
        "average_price": order.get("average_exec_price"),
        "created_at_ms": order.get("created_at"),
    }


def _post_action_exit_ledger_entry(
    exit_orders: list[dict[str, Any]],
    external_hygiene_orders: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not exit_orders:
        hygiene_orders = list(external_hygiene_orders or [])
        if hygiene_orders:
            return {
                "status": "external_exchange_flat_unresolved",
                "reason": "exchange_flat_no_exit_fill_recorded",
                "hard_blocker": False,
                "terminalized_protection_order_ids": [
                    item.get("order_id") for item in hygiene_orders if item.get("order_id")
                ],
                "terminalized_exchange_order_ids": [
                    item.get("exchange_order_id") for item in hygiene_orders if item.get("exchange_order_id")
                ],
            }
        return {
            "status": "not_available",
            "reason": "no_exit_fill_recorded",
            "hard_blocker": False,
        }
    order = exit_orders[-1]
    return {
        "status": str(order.get("status") or "unknown").lower(),
        "order_id": order.get("order_id"),
        "exchange_order_id": order.get("exchange_order_id"),
        "order_role": order.get("order_role"),
        "quantity": order.get("filled_qty") or order.get("requested_qty"),
        "average_price": order.get("average_exec_price") or order.get("price"),
        "created_at_ms": order.get("created_at"),
    }


def _post_action_not_available(reason: str) -> dict[str, Any]:
    return {
        "status": "not_available",
        "value": None,
        "asset": "USDT",
        "reason": reason,
        "hard_blocker": False,
    }


def _owner_action_flow(data: dict[str, Any]) -> dict[str, Any]:
    market_input = dict(data.get("owner_market_input") or {})
    budget = dict(data.get("budget_recommendation") or {})
    envelope = dict(budget.get("budget_envelope") or {})
    account_capacity = dict(budget.get("account_capacity") or {})
    owner_budget_selection = dict(budget.get("owner_selection") or {})
    recommended_symbols = [
        dict(item) for item in budget.get("recommended_symbols") or []
        if isinstance(item, dict)
    ]
    selected_candidate = dict(data.get("selected_candidate") or {})
    selected_spec = dict(selected_candidate.get("generic_action_spec") or {})
    risk_review = dict(data.get("risk_review") or {})
    authorization_path = dict(data.get("authorization_draft_path") or {})
    final_gate = dict(data.get("final_gate_result") or {})
    action_state = dict(data.get("action_state") or {})
    post_action = dict(data.get("post_action_state") or {})
    next_attempt_gate = dict(post_action.get("next_attempt_gate") or {})
    candidate_output = [
        dict(item) for item in data.get("candidate_output") or []
        if isinstance(item, dict)
    ]
    generic_specs = [
        dict(item) for item in data.get("generic_action_specs") or []
        if isinstance(item, dict)
    ]
    action_enabled = action_state.get("enabled") is True
    budget_status = envelope.get("status") or "not_available"
    budget_ready = budget_status == "available"
    candidate_choices = _owner_action_candidate_choices(
        candidate_output=candidate_output,
        generic_specs=generic_specs,
    )
    budgeted_autonomy_loop = _budgeted_autonomy_loop_projection(
        envelope=envelope,
        selected_spec=selected_spec,
        generic_specs=generic_specs,
        post_action=post_action,
    )
    budgeted_autonomy_v01 = _budgeted_autonomy_v01_projection(
        envelope=envelope,
        selected_spec=selected_spec,
        generic_specs=generic_specs,
        post_action=post_action,
    )
    lifecycle_monitoring = _owner_action_lifecycle_monitoring(post_action)
    just_in_time_lifecycle_audit = _owner_action_just_in_time_lifecycle_audit(
        lifecycle_monitoring=lifecycle_monitoring,
        next_attempt_gate=next_attempt_gate,
    )
    capital_selection = _owner_action_capital_selection(
        envelope=envelope,
        owner_budget_selection=owner_budget_selection,
        selected_spec=selected_spec,
    )
    protection_review = _owner_action_protection_review_readiness(
        selected_spec=selected_spec,
        post_action=post_action,
        risk_review=risk_review,
    )
    steps = [
        {
            "step": "market_input",
            "label": "Owner market input",
            "status": "ready" if market_input.get("regime") != "not_selected" else "pending",
            "summary": market_input.get("mapped_family") or "No market regime selected.",
        },
        {
            "step": "candidate_selection",
            "label": "Candidate selection",
            "status": "ready" if selected_candidate.get("carrier_id") else "pending",
            "summary": (
                f"{selected_candidate.get('carrier_id') or 'No candidate selected.'}"
                f" / {selected_spec.get('proposal_role') or 'unknown'}"
            ),
        },
        {
            "step": "risk_disclosure",
            "label": "Risk disclosure",
            "status": "blocked" if risk_review.get("hard_blocker_count", 0) else "warning",
            "summary": (
                f"{risk_review.get('warning_count', 0)} warnings / "
                f"{risk_review.get('hard_blocker_count', 0)} hard blockers"
            ),
        },
        {
            "step": "budget_envelope",
            "label": "Budget envelope",
            "status": "ready" if budget_ready else "blocked",
            "summary": (
                f"{envelope.get('max_notional_per_action') or 'no'} max notional per action; "
                "Owner confirmation still required"
            ),
        },
        {
            "step": "authorization_draft",
            "label": "Authorization draft readiness",
            "status": (
                "ready"
                if authorization_path.get("official_service_path_available")
                else "blocked"
            ),
            "summary": authorization_path.get("status") or "Authorization draft status unavailable.",
        },
        {
            "step": "final_gate",
            "label": "Final-gate result",
            "status": "blocked" if final_gate.get("may_execute_live") is not True else "ready",
            "summary": final_gate.get("status") or "Final gate not checked.",
        },
        {
            "step": "action_state",
            "label": "Action state",
            "status": "ready" if action_enabled else "blocked",
            "summary": (
                action_state.get("label")
                if action_enabled
                else action_state.get("disabled_reason") or "Action disabled."
            ),
        },
        {
            "step": "post_action_evidence",
            "label": "Post-action timeline / evidence",
            "status": next_attempt_gate.get("status") or post_action.get("status") or "empty",
            "summary": (
                f"{post_action.get('intent_count', 0)} intents / "
                f"{post_action.get('entry_order_count', 0)} entries / "
                f"{post_action.get('protection_order_count', 0)} TP-SL / "
                f"{post_action.get('review_count', 0)} reviews / "
                f"{post_action.get('audit_event_count', 0)} audit events; "
                f"{next_attempt_gate.get('gate') or 'lifecycle gate unavailable'}"
            ),
        },
        {
            "step": "budgeted_autonomy_loop",
            "label": "Budgeted autonomy loop",
            "status": budgeted_autonomy_loop.get("outcome"),
            "summary": budgeted_autonomy_loop.get("retry_condition"),
        },
        {
            "step": "budgeted_autonomy_v01",
            "label": "Budgeted autonomy v0.1 policy",
            "status": budgeted_autonomy_v01.get("outcome"),
            "summary": budgeted_autonomy_v01.get("retry_condition"),
        },
    ]
    return {
        "status": "actionable" if action_enabled else "not_actionable",
        "unsafe_action_enabled": False,
        "flow_steps": steps,
        "market_selection": {
            "selected_regime": market_input.get("regime"),
            "mapped_family": market_input.get("mapped_family"),
            "selectable_regimes": [
                {"regime": "trend", "label": "趋势", "family": "Trend"},
                {"regime": "mean_reversion", "label": "区间/震荡", "family": "Mean reversion"},
                {"regime": "volatility_expansion", "label": "波动扩张", "family": "Volatility expansion"},
            ],
            "candidate_choices": candidate_choices,
            "recommended_symbols": recommended_symbols,
            "range_candidate": _first_match(
                candidate_choices,
                lambda item: item.get("proposal_role") == "range_candidate",
            ),
        },
        "budgeted_autonomy_loop": budgeted_autonomy_loop,
        "budgeted_autonomy_v01": budgeted_autonomy_v01,
        "next_attempt_gate": next_attempt_gate,
        "just_in_time_lifecycle_audit": just_in_time_lifecycle_audit,
        "lifecycle_monitoring": lifecycle_monitoring,
        "capital_selection": capital_selection,
        "protection_review_readiness": protection_review,
        "disabled_reason": (
            next_attempt_gate.get("disabled_reason")
            or action_state.get("disabled_reason")
            or final_gate.get("status")
            or "Action is disabled by backend state."
        ),
        "budget_summary": {
            "status": budget_status,
            "owner_selection_status": owner_budget_selection.get("status"),
            "selected_symbol": owner_budget_selection.get("selected_symbol"),
            "selected_side": owner_budget_selection.get("selected_side"),
            "selected_quantity": owner_budget_selection.get("selected_quantity"),
            "selected_target_notional_usdt": owner_budget_selection.get("target_notional_usdt")
            or owner_budget_selection.get("selected_target_notional_usdt"),
            "selected_max_notional": owner_budget_selection.get("selected_max_notional"),
            "selected_leverage": owner_budget_selection.get("selected_leverage"),
            "selected_max_attempts": owner_budget_selection.get("selected_max_attempts"),
            "selected_protection_mode": owner_budget_selection.get("selected_protection_mode"),
            "selected_review_requirement": owner_budget_selection.get("selected_review_requirement"),
            "recommended_symbols": recommended_symbols,
            "account_capacity_status": account_capacity.get("status"),
            "account_equity": account_capacity.get("account_equity"),
            "available_balance": account_capacity.get("available_balance"),
            "max_usable_notional": account_capacity.get("max_usable_notional"),
            "recommended_total_budget": envelope.get("total_budget"),
            "recommended_max_notional_per_action": envelope.get("max_notional_per_action"),
            "recommended_max_daily_loss": envelope.get("max_daily_loss"),
            "recommended_max_attempts": envelope.get("max_attempts"),
            "recommended_leverage": envelope.get("max_leverage"),
            "missing_facts": list(budget.get("missing_facts") or []),
            "warnings": list(budget.get("warnings") or []),
            "hard_blockers": [
                item for item in budget.get("blockers") or []
                if isinstance(item, dict) and item.get("severity") == "hard_blocker"
            ],
            "retry_conditions": [
                item.get("retry_condition")
                for item in budget.get("blockers") or []
                if isinstance(item, dict) and item.get("retry_condition")
            ],
            "owner_confirmation_required": True,
            "action_allowed": False,
        },
        "selected_action_proposal": {
            "family": selected_candidate.get("family"),
            "carrier_id": selected_spec.get("carrier_id") or selected_candidate.get("carrier_id"),
            "owner_selection_status": owner_budget_selection.get("status"),
            "owner_selected_scope": dict(selected_spec.get("owner_selected_scope") or {}),
            "status": selected_spec.get("status"),
            "proposal_role": selected_spec.get("proposal_role"),
            "market_regime": selected_spec.get("market_regime"),
            "sizing_mode": selected_spec.get("sizing_mode"),
            "symbol": selected_spec.get("symbol"),
            "side": selected_spec.get("side"),
            "quantity": selected_spec.get("quantity"),
            "target_notional_usdt": selected_spec.get("target_notional_usdt"),
            "computed_quantity": selected_spec.get("computed_quantity"),
            "estimated_notional_usdt": selected_spec.get("estimated_notional_usdt"),
            "market_rule_snapshot": selected_spec.get("market_rule_snapshot") or {},
            "validation_result": selected_spec.get("validation_result") or {},
            "suggested_minimum_notional_usdt": selected_spec.get("suggested_minimum_notional_usdt"),
            "suggested_quantity": selected_spec.get("suggested_quantity"),
            "recommended_quantity": selected_spec.get("recommended_quantity"),
            "recommended_max_notional": selected_spec.get("recommended_max_notional"),
            "max_notional": selected_spec.get("max_notional"),
            "leverage": selected_spec.get("leverage"),
            "max_attempts": selected_spec.get("max_attempts"),
            "protection_mode": selected_spec.get("protection_mode"),
            "review_requirement": selected_spec.get("review_requirement"),
            "protection_template": selected_spec.get("protection_template") or {},
            "review_template": selected_spec.get("review_template") or {},
            "warnings": list(selected_spec.get("warnings") or []),
            "hard_blockers": list(selected_spec.get("hard_blockers") or []),
            "retry_conditions": [
                item.get("retry_condition")
                for item in budget.get("blockers") or []
                if isinstance(item, dict) and item.get("retry_condition")
            ],
            "capital_selection": capital_selection,
            "protection_review_readiness": protection_review,
            "backend_actionable": action_state.get("backend_actionable") is True,
            "frontend_action_enabled": action_state.get("frontend_action_enabled") is True,
            "places_order": False,
        },
        "timeline": {
            "intent_count": post_action.get("intent_count", 0),
            "entry_order_count": post_action.get("entry_order_count", 0),
            "protection_order_count": post_action.get("protection_order_count", 0),
            "review_count": post_action.get("review_count", 0),
            "audit_event_count": post_action.get("audit_event_count", 0),
            "retry_safety": post_action.get("retry_safety"),
        },
    }


def _apply_owner_approved_budget_window(
    budget: dict[str, Any],
    custom_budget: dict[str, Any],
) -> dict[str, Any]:
    budget_id = _optional_nonempty_str(
        custom_budget.get("budget_authorization_id")
        or custom_budget.get("owner_budget_id")
    )
    attempt_window_start_ms = _optional_int_value(
        custom_budget.get("attempt_window_start_ms")
        or custom_budget.get("owner_budget_approved_at_ms")
    )
    if budget_id is None and attempt_window_start_ms is None:
        return budget
    result = dict(budget)
    envelope = dict(result.get("budget_envelope") or {})
    if budget_id is not None:
        envelope["envelope_id"] = budget_id
    if attempt_window_start_ms is not None:
        envelope["attempt_window_start_ms"] = attempt_window_start_ms
    result["budget_envelope"] = envelope
    result["owner_approved_budget_window"] = {
        "budget_authorization_id": budget_id or envelope.get("envelope_id"),
        "attempt_window_start_ms": attempt_window_start_ms,
        "source": "owner_action_flow_custom_budget_query",
        "creates_authorization": False,
        "creates_execution_intent": False,
        "places_order": False,
        "mutates_pg": False,
    }
    return result


def _owner_action_lifecycle_monitoring(post_action: dict[str, Any]) -> dict[str, Any]:
    gate = dict(post_action.get("next_attempt_gate") or {})
    ledger = dict(post_action.get("review_ledger") or {})
    review_decision = dict(ledger.get("review_decision") or {})
    exchange_state = dict(post_action.get("exchange_state") or {})
    return {
        "status": gate.get("lifecycle_classification") or "unknown_fail_closed",
        "backend_owned_state": True,
        "current_lifecycle_authorization_ids": list(
            post_action.get("current_lifecycle_authorization_ids") or []
        ),
        "current_lifecycle_signal_ids": list(post_action.get("current_lifecycle_signal_ids") or []),
        "pg_active_position_count": gate.get("pg_active_position_count"),
        "pg_open_order_count": gate.get("pg_open_order_count"),
        "exchange_position_count": gate.get("exchange_position_count"),
        "exchange_open_protection_count": gate.get("exchange_open_protection_count"),
        "exchange_state": exchange_state.get("status"),
        "review_status": review_decision.get("review_status") or review_decision.get("status"),
        "review_id": review_decision.get("review_id"),
        "next_attempt_status": gate.get("status"),
        "next_attempt_gate": gate.get("gate"),
        "disabled_reason": gate.get("disabled_reason"),
        "retry_condition": gate.get("retry_condition"),
        "action_allowed": False,
        "frontend_action_enabled": False,
        "places_order": False,
    }


def _owner_action_just_in_time_lifecycle_audit(
    *,
    lifecycle_monitoring: dict[str, Any],
    next_attempt_gate: dict[str, Any],
) -> dict[str, Any]:
    classification = str(lifecycle_monitoring.get("status") or "unknown_fail_closed")
    gate = str(next_attempt_gate.get("gate") or "unknown")
    can_continue = (
        next_attempt_gate.get("next_attempt_allowed_by_lifecycle") is True
        and classification in {
            "closed_reviewed",
            "no_current_lifecycle",
            "external_flat",
            "legacy_closed_no_runtime_review_required",
        }
    )
    if classification == "still_open_protected":
        decision = "block_next_attempt_current_lifecycle_open"
        next_action = "wait_for_tp_or_sl_close"
    elif classification in {"tp_filled_position_closed", "sl_filled_position_closed", "external_flat"}:
        decision = "requires_reconciliation_before_continuing"
        next_action = "reconcile_close_cleanup_and_record_closed_reviewed"
    elif classification == "review_required":
        decision = "block_next_attempt_review_required"
        next_action = "record_closed_trade_review"
    elif classification in {
        "exchange_flat_pg_open",
        "pg_flat_exchange_open",
        "protection_missing",
        "protection_orphaned",
        "inconsistent_requires_recovery",
        "unknown_fail_closed",
    }:
        decision = "block_next_attempt_recovery_required"
        next_action = "official_recovery_required"
    else:
        decision = "continue_to_owner_budget_final_gate" if can_continue else "block_next_attempt"
        next_action = "owner_decision_and_final_gate" if can_continue else next_attempt_gate.get("required_next_step")
    return {
        "audit_stage": "next_attempt_preflight",
        "audit_version": "jit_lifecycle_audit_v1",
        "backend_owned_state": True,
        "frontend_must_not_infer": True,
        "classification": classification,
        "decision": decision,
        "can_continue_to_authorization": can_continue,
        "can_execute_live": False,
        "current_lifecycle_authorization_ids": list(
            lifecycle_monitoring.get("current_lifecycle_authorization_ids") or []
        ),
        "review_status": lifecycle_monitoring.get("review_status"),
        "review_id": lifecycle_monitoring.get("review_id"),
        "pg_active_position_count": lifecycle_monitoring.get("pg_active_position_count"),
        "pg_open_order_count": lifecycle_monitoring.get("pg_open_order_count"),
        "exchange_position_count": lifecycle_monitoring.get("exchange_position_count"),
        "exchange_open_protection_count": lifecycle_monitoring.get("exchange_open_protection_count"),
        "next_attempt_gate": gate,
        "disabled_reason": next_attempt_gate.get("disabled_reason"),
        "retry_condition": next_attempt_gate.get("retry_condition"),
        "next_recommended_action": next_action,
        "allowed_exchange_write": (
            "residual_sibling_protection_cancel_only_after_confirmed_flat"
        ),
        "active_tp_sl_cancel_allowed": False,
        "action_allowed": False,
        "frontend_action_enabled": False,
        "places_order": False,
    }


def _owner_action_capital_selection(
    *,
    envelope: dict[str, Any],
    owner_budget_selection: dict[str, Any],
    selected_spec: dict[str, Any],
) -> dict[str, Any]:
    validation = dict(selected_spec.get("validation_result") or {})
    hard_blockers = list(selected_spec.get("hard_blockers") or [])
    capital_blockers = [
        item for item in hard_blockers
        if any(
            token in str(item)
            for token in [
                "notional",
                "quantity",
                "qty",
                "leverage",
                "max_attempts",
                "market_rule",
                "protection_notional",
            ]
        )
    ]
    warnings = list(selected_spec.get("warnings") or [])
    has_quantity = selected_spec.get("quantity") not in (None, "")
    has_max_notional = selected_spec.get("max_notional") not in (None, "")
    has_leverage = selected_spec.get("leverage") not in (None, "")
    validation_failed = bool(capital_blockers) or validation.get("status") == "invalid"
    return {
        "status": (
            "blocked"
            if validation_failed
            else "ready_for_review"
            if has_quantity and has_max_notional and has_leverage
            else "incomplete"
        ),
        "owner_selection_status": owner_budget_selection.get("status"),
        "selected_symbol": selected_spec.get("symbol"),
        "selected_side": selected_spec.get("side"),
        "selected_quantity": selected_spec.get("quantity"),
        "target_notional_usdt": selected_spec.get("target_notional_usdt"),
        "computed_quantity": selected_spec.get("computed_quantity"),
        "estimated_notional_usdt": selected_spec.get("estimated_notional_usdt"),
        "selected_max_notional": selected_spec.get("max_notional"),
        "selected_leverage": selected_spec.get("leverage"),
        "budget_max_notional_per_action": envelope.get("max_notional_per_action"),
        "budget_max_leverage": envelope.get("max_leverage"),
        "market_rule_snapshot": selected_spec.get("market_rule_snapshot") or {},
        "validation_result": validation,
        "warnings": warnings,
        "hard_blockers": capital_blockers,
        "non_capital_hard_blockers": [
            item for item in hard_blockers if item not in capital_blockers
        ],
        "owner_disclosure_required": True,
        "silent_quantity_repair_allowed": False,
        "action_allowed": False,
        "frontend_action_enabled": False,
        "places_order": False,
    }


def _owner_action_protection_review_readiness(
    *,
    selected_spec: dict[str, Any],
    post_action: dict[str, Any],
    risk_review: dict[str, Any],
) -> dict[str, Any]:
    protection_template = dict(selected_spec.get("protection_template") or {})
    review_template = dict(selected_spec.get("review_template") or {})
    protection_template_blockers = list(protection_template.get("hard_blockers") or [])
    ledger = dict(post_action.get("review_ledger") or {})
    tp_sl = dict(ledger.get("tp_sl_result") or {})
    review_decision = dict(ledger.get("review_decision") or {})
    protection_ready = bool(protection_template) and selected_spec.get("protection_mode") == "single_tp_plus_sl"
    review_ready = bool(review_template) and review_decision.get("status") in {
        "pending_open_recorded",
        "pending",
        "revise",
    }
    execution_template_blocked = bool(protection_template_blockers) or int(
        risk_review.get("hard_blocker_count", 0) or 0
    ) > 0
    return {
        "status": (
            "blocked_for_execution_review_available"
            if protection_ready and review_ready and execution_template_blocked
            else "ready_for_review"
            if protection_ready and review_ready
            else "incomplete"
        ),
        "current_review_ready": review_ready,
        "execution_protection_draft_status": (
            "blocked" if execution_template_blocked else "ready"
        ),
        "protection_template": protection_template,
        "protection_template_hard_blockers": protection_template_blockers,
        "review_template": review_template,
        "current_tp_sl_status": tp_sl.get("status"),
        "current_open_protection_order_count": tp_sl.get("open_protection_order_count"),
        "review_status": review_decision.get("review_status") or review_decision.get("status"),
        "review_id": review_decision.get("review_id"),
        "owner_risk_acceptance_status": risk_review.get("owner_risk_acceptance_status"),
        "owner_risk_acceptance_recorded": risk_review.get("owner_risk_acceptance_recorded") is True,
        "warning_count": risk_review.get("warning_count", 0),
        "hard_blocker_count": risk_review.get("hard_blocker_count", 0),
        "action_allowed": False,
        "frontend_action_enabled": False,
        "places_order": False,
    }


def _owner_action_candidate_choices(
    *,
    candidate_output: list[dict[str, Any]],
    generic_specs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    choices: list[dict[str, Any]] = []
    for candidate in candidate_output:
        carrier_id = candidate.get("carrier_id")
        family = candidate.get("family")
        spec = (
            _first_match(generic_specs, lambda item: carrier_id and item.get("carrier_id") == carrier_id)
            or _first_match(generic_specs, lambda item: family and item.get("family") == family)
            or {}
        )
        choices.append(
            {
                "family": family,
                "carrier_id": carrier_id,
                "proposal_role": spec.get("proposal_role") or "unknown",
                "market_regime": spec.get("market_regime"),
                "candidate_state": candidate.get("candidate_state"),
                "action_candidate_status": candidate.get("action_candidate_status"),
                "generic_action_spec_status": spec.get("status"),
                "supported_symbols": list(spec.get("supported_symbols") or []),
                "supported_sides": list(spec.get("supported_sides") or []),
                "symbol": spec.get("symbol"),
                "side": spec.get("side"),
                "owner_selected_scope": dict(spec.get("owner_selected_scope") or {}),
                "target_notional_usdt": spec.get("target_notional_usdt"),
                "computed_quantity": spec.get("computed_quantity"),
                "estimated_notional_usdt": spec.get("estimated_notional_usdt"),
                "market_rule_snapshot": spec.get("market_rule_snapshot") or {},
                "validation_result": spec.get("validation_result") or {},
                "suggested_minimum_notional_usdt": spec.get("suggested_minimum_notional_usdt"),
                "suggested_quantity": spec.get("suggested_quantity"),
                "recommended_quantity": spec.get("recommended_quantity"),
                "recommended_max_notional": spec.get("recommended_max_notional"),
                "budget_recommendation_status": spec.get("budget_recommendation_status"),
                "owner_selection_status": spec.get("owner_selection_status"),
                "warnings": list(spec.get("warnings") or []),
                "hard_blockers": list(spec.get("hard_blockers") or []),
                "warning_count": candidate.get("warning_count", 0),
                "hard_blocker_count": candidate.get("hard_blocker_count", 0),
                "backend_actionable": False,
                "frontend_action_enabled": False,
                "places_order": False,
            }
        )
    return choices


def _budgeted_autonomy_loop_projection(
    *,
    envelope: dict[str, Any],
    selected_spec: dict[str, Any],
    generic_specs: list[dict[str, Any]],
    post_action: dict[str, Any],
) -> dict[str, Any]:
    max_notional = _decimal_from_any(envelope.get("max_notional_per_action")) or Decimal("0.01")
    max_daily_loss = _decimal_from_any(envelope.get("max_daily_loss")) or Decimal("0")
    max_leverage = _decimal_from_any(envelope.get("max_leverage")) or Decimal("1")
    allowed_symbols = [str(item) for item in envelope.get("allowed_symbols") or []]
    allowed_sides = [
        _normalize_side(item) for item in envelope.get("allowed_sides") or []
        if _normalize_side(item) in {"long", "short"}
    ]
    if not allowed_sides:
        allowed_sides = ["long"]
    selected_carrier = selected_spec.get("carrier_id")
    allowed_carriers = [
        str(item.get("carrier_id"))
        for item in generic_specs
        if isinstance(item, dict) and item.get("carrier_id")
    ]
    if selected_carrier and str(selected_carrier) not in allowed_carriers:
        allowed_carriers.append(str(selected_carrier))
    authorization = BudgetedAutonomyAuthorization(
        budget_authorization_id=str(envelope.get("envelope_id") or "budgeted-autonomy:read-model"),
        allowed_carriers=allowed_carriers,
        allowed_symbols=allowed_symbols,
        allowed_sides=allowed_sides,  # type: ignore[arg-type]
        max_notional_per_action=max_notional,
        daily_loss_cap=max_daily_loss,
        max_active_positions=int(envelope.get("max_active_positions") or 1),
        max_attempts=int(envelope.get("max_attempts") or 1),
        max_leverage=max_leverage,
        review_required="post_action_review_required",
        protection_mode="single_tp_plus_sl",
    )
    review_ledger = dict(post_action.get("review_ledger") or {})
    exchange_state = dict(post_action.get("exchange_state") or {})
    entry = dict(review_ledger.get("entry") or {})
    tp_sl = dict(review_ledger.get("tp_sl_result") or {})
    positions: list[BudgetedAutonomyPositionEvidence] = []
    if review_ledger.get("lifecycle_status") == "protected_open_from_pg_orders":
        position_symbol = (
            str(selected_spec.get("symbol"))
            if selected_spec.get("symbol")
            else (allowed_symbols[0] if allowed_symbols else "unknown")
        )
        open_protection_order_count = int(tp_sl.get("open_protection_order_count") or 0)
        positions.append(
            BudgetedAutonomyPositionEvidence(
                carrier_id=str(selected_carrier) if selected_carrier else None,
                symbol=position_symbol,
                side=_normalize_side(selected_spec.get("side")),
                quantity=_decimal_from_any(entry.get("quantity")),
                entry_price=_decimal_from_any(entry.get("average_price")),
                exchange_position_present=(
                    int(exchange_state.get("exchange_position_count") or 0) > 0
                ),
                exchange_verified_flat=(
                    exchange_state.get("status") == "pg_open_exchange_flat_cleanup_needed"
                ),
                pg_position_count=1,
                open_tp_count=1 if open_protection_order_count > 0 else 0,
                open_sl_count=1 if open_protection_order_count > 1 else 0,
                pg_open_order_count=open_protection_order_count,
                retry_allowed=False,
                review_recorded=bool(post_action.get("review_count")),
                audit_recorded=bool(post_action.get("audit_event_count")),
            )
        )
    candidates = [
        _budgeted_autonomy_candidate_from_spec(item)
        for item in generic_specs
        if isinstance(item, dict) and item.get("carrier_id")
    ]
    evaluation = evaluate_budgeted_autonomy_loop(
        authorization=authorization,
        positions=positions,
        candidates=candidates,
        review_ledger=review_ledger,
    )
    return evaluation.model_dump(mode="json")


def _budgeted_autonomy_v01_projection(
    *,
    envelope: dict[str, Any],
    selected_spec: dict[str, Any],
    generic_specs: list[dict[str, Any]],
    post_action: dict[str, Any],
) -> dict[str, Any]:
    max_notional = _decimal_from_any(envelope.get("max_notional_per_action")) or Decimal("0.01")
    max_daily_loss = _decimal_from_any(envelope.get("max_daily_loss")) or Decimal("0")
    max_leverage = _decimal_from_any(envelope.get("max_leverage")) or Decimal("1")
    allowed_symbols = [str(item) for item in envelope.get("allowed_symbols") or []]
    allowed_sides = [
        _normalize_side(item) for item in envelope.get("allowed_sides") or []
        if _normalize_side(item) in {"long", "short"}
    ]
    if not allowed_sides:
        allowed_sides = ["long"]
    selected_carrier = selected_spec.get("carrier_id")
    allowed_carriers = [
        str(item.get("carrier_id"))
        for item in generic_specs
        if isinstance(item, dict) and item.get("carrier_id")
    ]
    if selected_carrier and str(selected_carrier) not in allowed_carriers:
        allowed_carriers.append(str(selected_carrier))
    max_attempts = int(envelope.get("max_attempts") or 1)
    authorization = BudgetedAutonomyAuthorization(
        budget_authorization_id=str(envelope.get("envelope_id") or "budgeted-autonomy:read-model"),
        allowed_carriers=allowed_carriers,
        allowed_symbols=allowed_symbols,
        allowed_sides=allowed_sides,  # type: ignore[arg-type]
        max_notional_per_action=max_notional,
        daily_loss_cap=max_daily_loss,
        max_active_positions=int(envelope.get("max_active_positions") or 1),
        max_attempts=max_attempts,
        max_leverage=max_leverage,
        review_required="post_action_review_required",
        protection_mode="single_tp_plus_sl",
    )
    attempt_window_start_ms = _optional_int_value(envelope.get("attempt_window_start_ms"))
    review_ledger = _review_ledger_for_budget_window(
        review_ledger=dict(post_action.get("review_ledger") or {}),
        attempt_window_start_ms=attempt_window_start_ms,
    )
    exchange_state = dict(post_action.get("exchange_state") or {})
    entry = dict(review_ledger.get("entry") or {})
    tp_sl = dict(review_ledger.get("tp_sl_result") or {})
    positions: list[BudgetedAutonomyPositionEvidence] = []
    if review_ledger.get("lifecycle_status") == "protected_open_from_pg_orders":
        open_protection_order_count = int(tp_sl.get("open_protection_order_count") or 0)
        positions.append(
            BudgetedAutonomyPositionEvidence(
                carrier_id=str(selected_carrier) if selected_carrier else None,
                symbol=str(selected_spec.get("symbol") or (allowed_symbols[0] if allowed_symbols else "unknown")),
                side=_normalize_side(selected_spec.get("side")),
                quantity=_decimal_from_any(entry.get("quantity")),
                entry_price=_decimal_from_any(entry.get("average_price")),
                exchange_position_present=(
                    int(exchange_state.get("exchange_position_count") or 0) > 0
                ),
                exchange_verified_flat=(
                    exchange_state.get("status") == "pg_open_exchange_flat_cleanup_needed"
                ),
                pg_position_count=1,
                open_tp_count=1 if open_protection_order_count > 0 else 0,
                open_sl_count=1 if open_protection_order_count > 1 else 0,
                pg_open_order_count=open_protection_order_count,
                retry_allowed=False,
                review_recorded=bool(post_action.get("review_count")),
                audit_recorded=bool(post_action.get("audit_event_count")),
            )
        )
    day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_attempts_used = _completed_intents_for_scope_today(
        post_action=post_action,
        symbol=selected_spec.get("symbol"),
        day_key=day_key,
        attempt_window_start_ms=attempt_window_start_ms,
    )
    daily_state = BudgetedAutonomyDailyState(
        day_key=day_key,
        attempts_used=daily_attempts_used,
        attempts_allowed=max_attempts,
        budget_used_notional=Decimal("0"),
        realized_loss=Decimal("0"),
        source=(
            "trading_console_selected_symbol_pg_intents_owner_budget_window"
            if attempt_window_start_ms is not None
            else "trading_console_selected_symbol_pg_intents_current_utc_day"
        ),
    )
    candidates = [
        _budgeted_autonomy_candidate_from_spec(item)
        for item in generic_specs
        if isinstance(item, dict) and item.get("carrier_id")
    ]
    evaluation = evaluate_budgeted_autonomy_v01(
        authorization=authorization,
        positions=positions,
        candidates=candidates,
        daily_state=daily_state,
        review_ledger=review_ledger,
    )
    return evaluation.model_dump(mode="json")


def _completed_intents_for_scope_today(
    *,
    post_action: dict[str, Any],
    symbol: Any,
    day_key: str,
    attempt_window_start_ms: int | None = None,
) -> int:
    selected_symbol = str(symbol or "")
    counts = dict(post_action.get("completed_intents_today_by_symbol") or {})
    if attempt_window_start_ms is None and selected_symbol:
        parsed_count = _optional_int_value(counts.get(selected_symbol))
        if parsed_count is not None:
            return parsed_count
    elif attempt_window_start_ms is None and counts:
        return sum(_optional_int_value(item) or 0 for item in counts.values())
    day_start_ms = _day_start_ms(day_key)
    window_start_ms = max(
        day_start_ms,
        attempt_window_start_ms if attempt_window_start_ms is not None else day_start_ms,
    )
    summary = dict(post_action.get("summary") or {})
    intents = [
        dict(item)
        for item in summary.get("intents") or []
        if isinstance(item, dict)
    ]
    count = 0
    for item in intents:
        if str(item.get("status") or "").lower() != "completed":
            continue
        if selected_symbol and str(item.get("symbol") or "") != selected_symbol:
            continue
        created_at = _optional_int_value(item.get("created_at"))
        if created_at is None or created_at < window_start_ms:
            continue
        count += 1
    return count


def _review_ledger_for_budget_window(
    *,
    review_ledger: dict[str, Any],
    attempt_window_start_ms: int | None,
) -> dict[str, Any]:
    if attempt_window_start_ms is None:
        return review_ledger
    entry = dict(review_ledger.get("entry") or {})
    entry_created_at = _optional_int_value(entry.get("created_at_ms"))
    if entry_created_at is not None and entry_created_at < attempt_window_start_ms:
        return {}
    return review_ledger


def _completed_intent_counts_by_symbol_today(
    *,
    intents: list[dict[str, Any]],
    day_key: str,
) -> dict[str, int]:
    day_start_ms = _day_start_ms(day_key)
    counts: dict[str, int] = {}
    for item in intents:
        if str(item.get("status") or "").lower() != "completed":
            continue
        created_at = _optional_int_value(item.get("created_at"))
        if created_at is None or created_at < day_start_ms:
            continue
        symbol = str(item.get("symbol") or "unknown")
        counts[symbol] = counts.get(symbol, 0) + 1
    return counts


def _day_start_ms(day_key: str) -> int:
    parsed = datetime.strptime(day_key, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _budgeted_autonomy_candidate_from_spec(spec: dict[str, Any]) -> BudgetedAutonomyCandidateInput:
    status = str(spec.get("status") or "invalid_blocked")
    hard_blockers = _budgeted_autonomy_candidate_blockers_for_selection(
        status=status,
        hard_blockers=list(spec.get("hard_blockers") or []),
    )
    return BudgetedAutonomyCandidateInput(
        candidate_id=str(spec.get("action_candidate_ref") or spec.get("carrier_id") or "unknown"),
        family=str(spec.get("family") or "unknown"),
        carrier_id=str(spec.get("carrier_id") or "unknown"),
        symbol=str(spec.get("symbol") or (spec.get("supported_symbols") or ["unknown"])[0]),
        side=_normalize_side(spec.get("side")),
        status=status,
        action_registry_supported=bool(spec.get("action_registry_supported")),
        proposal_role=str(spec.get("proposal_role") or "unknown"),
        quantity=_decimal_from_any(spec.get("quantity") or spec.get("computed_quantity")),
        target_notional_usdt=_decimal_from_any(spec.get("target_notional_usdt")),
        estimated_notional_usdt=_decimal_from_any(spec.get("estimated_notional_usdt")),
        max_notional=_decimal_from_any(spec.get("max_notional") or spec.get("recommended_max_notional")),
        leverage=_decimal_from_any(spec.get("leverage")),
        max_attempts=int(spec["max_attempts"]) if spec.get("max_attempts") is not None else None,
        protection_mode=spec.get("protection_mode"),
        review_requirement=spec.get("review_requirement"),
        warnings=list(spec.get("warnings") or []),
        hard_blockers=hard_blockers,
    )


def _budgeted_autonomy_candidate_blockers_for_selection(
    *,
    status: str,
    hard_blockers: list[Any],
) -> list[str]:
    blockers = [str(item) for item in hard_blockers]
    if status != "valid_blocked_final_gate":
        return blockers
    return [
        item
        for item in blockers
        if not _final_gate_readiness_marker(item)
    ]


def _final_gate_readiness_marker(value: str) -> bool:
    normalized = value.upper()
    return (
        normalized.endswith("-SCOPE")
        or normalized.endswith("-FINAL-GATE")
        or normalized.endswith("-EVIDENCE")
        or normalized.endswith("-PROTECTION")
    )


def _decimal_from_any(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _normalize_side(value: Any) -> str:
    text = str(value or "long").lower()
    if text in {"sell", "short"}:
        return "short"
    return "long"


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = value.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _latest_control_operation(
    runtime_control: dict[str, Any],
    budget_authorization: dict[str, Any],
) -> dict[str, Any]:
    candidates = [
        dict(runtime_control.get("last_control_operation") or {}),
        dict(budget_authorization.get("last_control_operation") or {}),
    ]
    candidates = [item for item in candidates if item.get("status")]
    if not candidates:
        return {"status": "not_available", "source": "not_available"}
    return max(candidates, key=lambda item: int(item.get("updated_at_ms") or 0))


def _cockpit_overall_status(
    *,
    snap: TradingConsoleSnapshot,
    autonomy: dict[str, Any],
    active_position: dict[str, Any],
    protection: dict[str, Any],
    recovery: dict[str, Any],
    review: dict[str, Any],
    budget: dict[str, Any],
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    hard_blockers = [item for item in blockers if item.get("severity") == "hard_blocker"]
    recovery_required = recovery.get("required") is True
    if recovery_required:
        status = "recovery_required"
        message = recovery.get("summary") or "Recovery or cleanup is required before any new action."
    elif active_position.get("exists"):
        status = "active_position"
        if protection.get("status") == "protected":
            message = f"System is waiting for the current {active_position.get('symbol') or ''} position to close."
        else:
            message = "Active position is present and protection is not fully confirmed."
    elif review.get("review_required_before_next_action"):
        status = "review_required"
        message = "Review is required before the next budgeted action."
    elif autonomy.get("state") in {"paused", "revoked"}:
        status = autonomy["state"]
        message = autonomy.get("message") or "Autonomy is not active."
    elif hard_blockers:
        status = "blocked"
        message = hard_blockers[0].get("what") or "Trading is blocked by current safety state."
    elif snap.warnings or snap.unavailable or budget.get("freshness_status") in {"degraded", "not_live_connected"}:
        status = "warning"
        message = "System is safe to inspect, but some operating facts are incomplete or stale."
    else:
        status = "safe"
        message = "No active position or recovery issue is visible in the current cockpit read."
    return {
        "status": status,
        "label": _status_label(status),
        "message": message,
        "primary_next_action": _primary_next_action(
            status=status,
            autonomy=autonomy,
            active_position=active_position,
            recovery=recovery,
            review=review,
            budget=budget,
            blockers=blockers,
        ),
        "safe_to_open_console": True,
        "live_ready": False,
        "source": "operations_cockpit_read_model",
    }


def _primary_next_action(
    *,
    status: str,
    autonomy: dict[str, Any],
    active_position: dict[str, Any],
    recovery: dict[str, Any],
    review: dict[str, Any],
    budget: dict[str, Any],
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    if recovery.get("required"):
        return {
            "action_id": "view_recovery",
            "label": "查看恢复建议",
            "enabled": True,
            "route": "/recovery",
            "confirmation_required": False,
            "owner_action_required": bool(recovery.get("owner_action_required")),
            "system_action_available": False,
            "reason": recovery.get("next_safe_action") or "Recovery state needs inspection.",
        }
    if active_position.get("exists"):
        route = "/protection" if active_position.get("protection_status") != "protected" else "/ledger"
        return {
            "action_id": "monitor_position",
            "label": "查看仓位和保护",
            "enabled": True,
            "route": route,
            "confirmation_required": False,
            "owner_action_required": active_position.get("protection_status") != "protected",
            "system_action_available": False,
            "reason": "Wait for TP/SL close evidence; reconcile if protection is incomplete.",
        }
    if review.get("review_required_before_next_action"):
        return {
            "action_id": "open_review",
            "label": "打开复盘",
            "enabled": True,
            "route": "/review",
            "confirmation_required": False,
            "owner_action_required": True,
            "system_action_available": False,
            "reason": "A closed or unresolved action needs Owner review before another attempt.",
        }
    if autonomy.get("state") == "paused":
        return {
            "action_id": "autonomy_paused",
            "label": "查看暂停状态",
            "enabled": True,
            "route": "/",
            "confirmation_required": False,
            "owner_action_required": True,
            "system_action_available": False,
            "reason": "Autonomy is paused; future budgeted actions are blocked until Owner resumes or resets through an approved path.",
        }
    if autonomy.get("state") == "revoked" or budget.get("revoked") is True:
        return {
            "action_id": "budget_revoked",
            "label": "查看预算授权",
            "enabled": True,
            "route": "/action-entry",
            "confirmation_required": False,
            "owner_action_required": True,
            "system_action_available": False,
            "reason": "Budget authorization is revoked; future budgeted autonomy attempts require a new Owner-approved budget.",
        }
    hard_blockers = [item for item in blockers if item.get("severity") == "hard_blocker"]
    if hard_blockers:
        item = hard_blockers[0]
        return {
            "action_id": "inspect_blocker",
            "label": "查看阻断原因",
            "enabled": True,
            "route": item.get("route") or "/execution",
            "confirmation_required": False,
            "owner_action_required": bool(item.get("owner_action_required")),
            "system_action_available": bool(item.get("system_action_available")),
            "reason": item.get("clears_when") or item.get("why_matters"),
        }
    if budget.get("another_action_allowed") is True and autonomy.get("state") in {"budget_available", "candidate_selected"}:
        return {
            "action_id": "review_candidate",
            "label": "查看候选和预算",
            "enabled": True,
            "route": "/action-entry",
            "confirmation_required": False,
            "owner_action_required": True,
            "system_action_available": False,
            "reason": "Budget appears available, but official Owner confirmation and FinalGate are still required.",
        }
    return {
        "action_id": "refresh_status",
        "label": "刷新状态",
        "enabled": True,
        "route": "/",
        "confirmation_required": False,
        "owner_action_required": False,
        "system_action_available": True,
        "reason": autonomy.get("retry_condition") or "Refresh current PG/exchange facts.",
    }


def _cockpit_autonomy_summary(
    *,
    owner_flow: dict[str, Any],
    authorization: dict[str, Any],
    protection: dict[str, Any],
    active_position: dict[str, Any],
    recovery: dict[str, Any],
    review: dict[str, Any],
    budget: dict[str, Any],
    runtime_control: dict[str, Any],
) -> dict[str, Any]:
    v01 = dict(owner_flow.get("budgeted_autonomy_v01") or {})
    base = dict(v01.get("base_loop") or {})
    policy = dict(v01.get("policy") or {})
    outcome = str(v01.get("outcome") or base.get("outcome") or "blocked_with_retry_condition")
    runtime_status = str(runtime_control.get("status") or "")
    runtime_paused = runtime_status == "paused"
    if recovery.get("required"):
        state = "recovery_required"
    elif authorization.get("is_cancelled"):
        state = "revoked"
    elif runtime_paused or policy.get("pause_state") == "paused":
        state = "paused"
    elif budget.get("revoked") is True or policy.get("revoked") is True:
        state = "revoked"
    elif active_position.get("exists"):
        state = "waiting_position_close"
    elif review.get("review_required_before_next_action"):
        state = "closed_review_pending"
    elif outcome == "closed_reviewed":
        state = "closed_reviewed"
    elif owner_flow.get("selected_action_proposal"):
        state = "candidate_selected"
    elif budget.get("another_action_allowed"):
        state = "budget_available"
    else:
        state = "blocked_with_retry_condition"
    return {
        "state": state,
        "autonomy_effective_state": state,
        "label": _autonomy_label(state),
        "message": _autonomy_message(
            state=state,
            active_position=active_position,
            protection=protection,
            budget=budget,
            authorization=authorization,
        ),
        "loop_outcome": outcome,
        "active_loop": bool(base.get("active_loop")),
        "retry_condition": v01.get("retry_condition") or base.get("retry_condition"),
        "authorization_status": authorization.get("status"),
        "authorization_actionable": bool(authorization.get("is_actionable")),
        "runtime_control_state": runtime_control,
        "can_attempt_next_budgeted_action": (
            state in {"budget_available", "candidate_selected"}
            and budget.get("can_attempt_next_budgeted_action") is True
            and runtime_control.get("can_attempt_next_budgeted_action") is not False
        ),
        "can_pause_autonomy": not runtime_paused,
        "pause_disabled_reason": (
            runtime_control.get("disabled_reason")
            if runtime_paused
            else None
        ),
        "auto_execution_enabled": False,
        "backend_actionable": False,
        "frontend_action_enabled": False,
        "may_execute_live": False,
        "policy": policy,
    }


def _cockpit_budget_summary(
    *,
    owner_flow: dict[str, Any],
    budget_summary: dict[str, Any],
    budget_recommendation: dict[str, Any],
    post_action: dict[str, Any],
    budget_authorization: dict[str, Any],
    runtime_control: dict[str, Any],
) -> dict[str, Any]:
    envelope = dict(budget_recommendation.get("budget_envelope") or {})
    policy = dict((owner_flow.get("budgeted_autonomy_v01") or {}).get("policy") or {})
    policy_budget = dict(policy.get("budget") or {})
    attempts = dict(policy.get("daily_attempts") or {})
    max_attempts = _optional_int_value(
        attempts.get("allowed")
        or budget_summary.get("recommended_max_attempts")
        or envelope.get("max_attempts")
    )
    attempts_used = _optional_int_value(attempts.get("used"))
    if attempts_used is None:
        attempts_used = sum(
            int(value)
            for value in (post_action.get("completed_intents_today_by_symbol") or {}).values()
            if isinstance(value, int)
        )
    remaining_attempts = (
        max(max_attempts - attempts_used, 0)
        if max_attempts is not None
        else None
    )
    remaining_budget = (
        policy_budget.get("remaining_notional")
        or envelope.get("max_notional_per_action")
        or budget_summary.get("recommended_max_notional_per_action")
    )
    total_budget = envelope.get("total_budget") or budget_summary.get("recommended_total_budget")
    per_action = envelope.get("max_notional_per_action") or budget_summary.get("recommended_max_notional_per_action")
    status = envelope.get("status") or budget_summary.get("status") or "not_available"
    paused = policy.get("pause_state") == "paused" or runtime_control.get("status") == "paused"
    revoked = budget_authorization.get("revoked") is True or policy.get("revoked") is True
    budget_authorization_status = budget_authorization.get("budget_authorization_status") or budget_authorization.get("status")
    budget_effective_state = (
        "revoked" if revoked
        else budget_authorization.get("budget_effective_state")
        or ("available" if status == "available" else status)
    )
    another_action_allowed = bool(
        status == "available"
        and not paused
        and not revoked
        and budget_authorization.get("can_attempt_next_budgeted_action") is not False
        and (remaining_attempts is None or remaining_attempts > 0)
    )
    budget_auth_id = budget_authorization.get("budget_authorization_id")
    can_revoke_budget = bool(budget_auth_id and not revoked)
    revoke_disabled_reason = (
        "Budget authorization has already been revoked."
        if revoked
        else "No current budget authorization metadata exists."
        if not budget_auth_id
        else None
    )
    return {
        "status": status,
        "budget_effective_state": budget_effective_state,
        "budget_authorization_status": budget_authorization_status,
        "budget_authorization_id": budget_auth_id,
        "label": _budget_label(status),
        "authorized_scope": {
            "symbols": envelope.get("allowed_symbols") or [],
            "sides": envelope.get("allowed_sides") or [],
            "max_leverage": envelope.get("max_leverage"),
            "review_requirement": envelope.get("review_requirement"),
            "protection_mode": "single_tp_plus_sl",
        },
        "total_budget": total_budget,
        "per_action_max_notional": per_action,
        "used_budget": policy_budget.get("used_notional") or "0",
        "remaining_budget": remaining_budget,
        "daily_attempts_used": attempts_used,
        "daily_max_attempts": max_attempts,
        "daily_attempts_remaining": remaining_attempts,
        "another_action_allowed": another_action_allowed,
        "can_attempt_next_budgeted_action": another_action_allowed,
        "can_revoke_budget": can_revoke_budget,
        "revoke_disabled_reason": revoke_disabled_reason,
        "paused": paused,
        "revoked": revoked,
        "revoked_at_ms": budget_authorization.get("revoked_at_ms"),
        "revoked_by": budget_authorization.get("revoked_by"),
        "last_control_operation": budget_authorization.get("last_control_operation"),
        "last_budget_update_time": None,
        "freshness_status": (budget_recommendation.get("account_capacity") or {}).get("freshness", {}).get("freshness_status"),
        "not_authorization": envelope.get("not_authorization", True),
        "action_allowed": False,
        "grants_trading_permission": False,
    }


def _cockpit_active_position(
    *,
    positions: list[dict[str, Any]],
    protection: dict[str, Any],
    snap: TradingConsoleSnapshot,
) -> dict[str, Any]:
    active = [
        item for item in positions
        if item.get("is_closed") is not True and item.get("quantity") not in {None, "", "0", "0.0", "0E-18"}
    ]
    selected = _first_match(active, lambda item: item.get("source") == "exchange") or (active[0] if active else None)
    if selected is None:
        return {
            "exists": False,
            "status": "none",
            "message": "No active position is visible in PG or exchange reads.",
            "pg_position_count": len(snap.pg_positions),
            "exchange_position_count": len(snap.exchange.get("positions", [])),
            "protection_status": protection.get("status"),
            "last_refreshed_at": _iso_ms(snap.generated_at_ms),
        }
    entry = selected.get("entry_price")
    quantity = selected.get("quantity")
    notional = _position_notional(entry, quantity)
    return {
        "exists": True,
        "status": "open",
        "source": selected.get("source"),
        "symbol": selected.get("symbol"),
        "side": selected.get("side"),
        "entry_price": entry,
        "quantity": quantity,
        "notional": notional,
        "leverage": selected.get("leverage"),
        "current_mark_price": selected.get("mark_price"),
        "unrealized_pnl": selected.get("unrealized_pnl"),
        "realized_pnl": selected.get("realized_pnl"),
        "pg_exchange_consistency": "matched" if snap.pg_positions and snap.exchange.get("positions") else "not_fully_verified",
        "protection_status": protection.get("status"),
        "last_refreshed_at": _iso_ms(snap.generated_at_ms),
        "raw_position": selected,
    }


def _cockpit_protection_summary(protection: dict[str, Any]) -> dict[str, Any]:
    status = protection.get("status") or "unknown"
    tp_count = int(protection.get("tp_count") or 0)
    sl_count = int(protection.get("sl_count") or 0)
    return {
        "status": status,
        "label": _protection_label(status),
        "completeness": (
            "complete" if status == "protected"
            else "partial" if status == "partially_protected"
            else "missing" if status == "unprotected"
            else "orphan_suspected" if status == "orphaned"
            else "unknown"
        ),
        "tp_status": "present" if tp_count > 0 else "not_found",
        "sl_status": "present" if sl_count > 0 else "not_found",
        "tp_count": tp_count,
        "sl_count": sl_count,
        "active_position_count": protection.get("active_position_count") or 0,
        "orphan_protection_count": len(protection.get("orphan_protection_orders") or []),
        "actions_exposed": protection.get("actions_exposed") or [],
        "deferred_actions": protection.get("deferred_actions") or [],
    }


def _cockpit_runtime_governance_summary(
    *,
    overall: dict[str, Any],
    autonomy: dict[str, Any],
    budget: dict[str, Any],
    active_position: dict[str, Any],
    protection: dict[str, Any],
    review: dict[str, Any],
    blockers: list[dict[str, Any]],
    post_action: dict[str, Any],
    runtime_control: dict[str, Any],
    budget_authorization: dict[str, Any],
) -> dict[str, Any]:
    hard_blockers = [
        item for item in blockers
        if item.get("severity") in {"hard_blocker", "recovery_required"}
    ]
    if active_position.get("exists"):
        status = "blocked_by_active_position"
        next_gate_status = "waiting_for_position_resolution"
        next_gate_blocker = "active_position_open"
        next_step = "monitor_position_or_follow_owner_authorized_close_path"
    elif review.get("review_required_before_next_action"):
        status = "blocked_by_review_gate"
        next_gate_status = "waiting_for_closed_review"
        next_gate_blocker = "review_required_before_next_action"
        next_step = "complete_review_ledger_before_fresh_attempt"
    elif hard_blockers:
        status = "blocked_by_runtime_governance"
        next_gate_status = "blocked"
        next_gate_blocker = str(hard_blockers[0].get("code") or "runtime_blocker")
        next_step = "resolve_runtime_governance_blocker"
    elif budget.get("another_action_allowed") is True:
        status = "ready_for_fresh_strategy_signal"
        next_gate_status = "ready_for_strategy_signal"
        next_gate_blocker = None
        next_step = "start_fresh_strategy_signal_observation"
    else:
        status = "waiting_for_budget_or_runtime_gate"
        next_gate_status = "blocked"
        next_gate_blocker = "budget_not_actionable"
        next_step = "refresh_or_reauthorize_budget_before_fresh_attempt"

    latest_settlement = dict(post_action.get("latest_budget_settlement") or {})
    post_submit_finalize = dict(post_action.get("post_submit_finalize") or {})
    if not latest_settlement:
        latest_settlement = {
            "status": post_action.get("budget_settlement_status") or "not_available",
            "settlement_id": post_action.get("post_submit_budget_settlement_id"),
        }
    if not post_submit_finalize:
        post_submit_finalize = {
            "status": post_action.get("post_submit_finalize_status") or "not_available",
            "packet_id": post_action.get("post_submit_finalize_packet_id"),
        }

    budget_auth_id = budget.get("budget_authorization_id") or budget_authorization.get(
        "budget_authorization_id"
    )
    runtime_control_status = runtime_control.get("status") or autonomy.get(
        "runtime_control_state",
        {},
    ).get("status")

    return {
        "status": status,
        "label": _runtime_governance_label(status),
        "current_gate": {
            "status": overall.get("status"),
            "label": overall.get("label"),
            "message": overall.get("message"),
            "source": overall.get("source"),
        },
        "runtime_grant": {
            "status": runtime_control_status or "not_available",
            "budget_authorization_id": budget_auth_id,
            "budget_authorization_status": budget.get("budget_authorization_status"),
            "autonomy_effective_state": autonomy.get("autonomy_effective_state"),
            "grants_trading_permission": False,
        },
        "active_position": {
            "present": bool(active_position.get("exists")),
            "symbol": active_position.get("symbol"),
            "side": active_position.get("side"),
            "quantity": active_position.get("quantity"),
            "notional": active_position.get("notional"),
            "source": active_position.get("source"),
        },
        "protection": {
            "status": protection.get("status"),
            "tp_count": protection.get("tp_count"),
            "sl_count": protection.get("sl_count"),
            "completeness": protection.get("completeness"),
        },
        "budget": {
            "status": budget.get("status"),
            "remaining_budget": budget.get("remaining_budget"),
            "daily_attempts_used": budget.get("daily_attempts_used"),
            "daily_attempts_remaining": budget.get("daily_attempts_remaining"),
            "can_attempt_next_budgeted_action": budget.get(
                "can_attempt_next_budgeted_action"
            ),
        },
        "post_submit_finalize": post_submit_finalize,
        "budget_settlement": latest_settlement,
        "next_attempt_gate": {
            "status": next_gate_status,
            "blocker": next_gate_blocker,
            "next_step": next_step,
            "requires_fresh_strategy_signal": True,
            "requires_fresh_authorization_before_submit": True,
            "legacy_authorization_replay_allowed": False,
            "executable_submit_allowed_by_cockpit": False,
        },
        "hard_blockers": hard_blockers,
        "safety_invariants": {
            "read_model_only": True,
            "places_order": False,
            "calls_order_lifecycle": False,
            "calls_exchange_write": False,
            "mutates_runtime_budget": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _runtime_governance_label(status: str) -> str:
    labels = {
        "blocked_by_active_position": "Active position gate",
        "blocked_by_review_gate": "Review gate",
        "blocked_by_runtime_governance": "Runtime blocker",
        "ready_for_fresh_strategy_signal": "Ready for fresh signal",
        "waiting_for_budget_or_runtime_gate": "Budget or runtime gate",
    }
    return labels.get(status, "Runtime governance")


def _cockpit_candidate_summary(
    *,
    selected_proposal: dict[str, Any],
    owner_flow: dict[str, Any],
    action_data: dict[str, Any],
) -> dict[str, Any]:
    market = dict(owner_flow.get("market_selection") or {})
    choices = [dict(item) for item in market.get("candidate_choices") or [] if isinstance(item, dict)]
    selected_carrier = selected_proposal.get("carrier_id")
    return {
        "selected": {
            "family": selected_proposal.get("family"),
            "carrier_id": selected_carrier,
            "symbol": selected_proposal.get("symbol"),
            "side": selected_proposal.get("side"),
            "reason_selected": selected_proposal.get("proposal_role") or market.get("mapped_family"),
            "warnings": selected_proposal.get("warnings") or [],
            "hard_blockers": selected_proposal.get("hard_blockers") or [],
            "frontend_action_enabled": False,
        },
        "skipped_candidates": [
            {
                "family": item.get("family"),
                "carrier_id": item.get("carrier_id"),
                "reason": (
                    "selected"
                    if item.get("carrier_id") == selected_carrier
                    else item.get("generic_action_spec_status") or item.get("candidate_state")
                ),
                "warnings": item.get("warnings") or [],
                "hard_blockers": item.get("hard_blockers") or [],
            }
            for item in choices
            if item.get("carrier_id") != selected_carrier
        ],
        "market_selection": market,
        "next_action_recommendation": (action_data.get("final_gate_result") or {}).get("status"),
    }


def _cockpit_recovery_summary(
    *,
    snap: TradingConsoleSnapshot,
    classified_orders: list[dict[str, Any]],
    consistency: dict[str, Any],
) -> dict[str, Any]:
    mismatch_orders = [
        item for item in classified_orders
        if item.get("classification") in {"pg_only", "exchange_only", "mismatch", "orphan_protection"}
    ]
    startup = snap.environment.get("startup_reconciliation") or snap.guards.get("startup_reconciliation")
    operational_drift = dict(snap.environment.get("operational_drift") or {})
    runtime_server_version = dict(operational_drift.get("runtime_server_version") or {})
    migration = dict(operational_drift.get("migration") or {})
    operational_drift_required = bool(
        runtime_server_version.get("drift") is True
        or migration.get("mismatch") is True
    )
    required = bool(mismatch_orders or snap.recovery_tasks or operational_drift_required)
    if required:
        if operational_drift_required:
            summary = "Recovery is required because deployment/runtime drift or migration mismatch is visible."
        else:
            summary = "Recovery is required because local and exchange/order evidence is not clean."
    elif snap.unavailable:
        summary = "Recovery state cannot be fully confirmed because some sources are unavailable."
    else:
        summary = "No active recovery issue is visible."
    return {
        "required": required,
        "summary": summary,
        "manual_action_required": required,
        "owner_action_required": required,
        "system_action_available": False,
        "next_safe_action": (
            "Run or inspect official reconciliation before any new entry."
            if required
            else "Refresh status if facts look stale."
        ),
        "recovery_tasks": snap.recovery_tasks,
        "mismatches": mismatch_orders,
        "recovery_task_counts": _count_by(snap.recovery_tasks, "status"),
        "consistency_status": consistency.get("status"),
        "startup_reconciliation": startup or "not_available",
        "operational_drift": operational_drift,
        "detectable_states": {
            "pg_exchange_drift": bool(mismatch_orders),
            "orphan_protection_suspected": any(item.get("classification") == "orphan_protection" for item in mismatch_orders),
            "failed_execute": any(str(item.get("status") or "").lower() == "failed" for item in snap.pg_intents),
            "failed_protection_placement": any("protection" in str(item.get("code") or "") for item in snap.warnings),
            "external_flat": any(item.get("classification") == "orphan_protection" for item in mismatch_orders),
            "stale_account_facts": any(item.get("source") in {"account_snapshot", "exchange"} for item in snap.unavailable),
            "pending_migration_mismatch": (
                migration.get("mismatch")
                if migration.get("detectable") is True
                else "not_detectable"
            ),
            "pending_migration_mismatch_status": migration.get("status") or "not_detectable",
            "runtime_server_version_drift": (
                runtime_server_version.get("drift")
                if runtime_server_version.get("detectable") is True
                else "not_detectable"
            ),
            "runtime_server_version_drift_status": runtime_server_version.get("status") or "not_detectable",
        },
    }


def _cockpit_review_summary(
    *,
    post_action: dict[str, Any],
    reviews: list[dict[str, Any]],
    live_lifecycle_reviews: list[dict[str, Any]],
) -> dict[str, Any]:
    ledger = dict(post_action.get("review_ledger") or {})
    latest = reviews[0] if reviews else None
    latest_live = live_lifecycle_reviews[0] if live_lifecycle_reviews else None
    lifecycle = ledger.get("lifecycle_status") or "not_available"
    decision = dict(ledger.get("review_decision") or {})
    review_required = bool(
        decision.get("requires_owner_review") is True
        and decision.get("status") in {"pending", "not_recorded"}
        and lifecycle not in {"not_started_or_unknown", "protected_open_from_pg_orders"}
    )
    return {
        "pending_review_count": 1 if review_required else 0,
        "latest_closed_trade": {
            "status": lifecycle,
            "entry": ledger.get("entry") or {},
            "exit": ledger.get("exit") or {},
            "tp_sl_result": ledger.get("tp_sl_result") or {},
            "rough_realized_pnl": ledger.get("realized_pnl") or {"status": "not_available"},
            "holding_time": "not_available",
            "strategy_outcome": ledger.get("strategy_outcome") or "pending",
        },
        "review_required_before_next_action": review_required,
        "latest_review": latest or {},
        "review_count": len(reviews),
        "latest_live_lifecycle_review": latest_live or {},
        "live_lifecycle_review_count": len(live_lifecycle_reviews),
        "allowed_outcomes": ["promote", "revise", "park", "pending"],
    }


def _cockpit_blockers(
    *,
    snap: TradingConsoleSnapshot,
    action_blockers: list[dict[str, Any]],
    protection: dict[str, Any],
    recovery: dict[str, Any],
    review: dict[str, Any],
    budget: dict[str, Any],
    active_position: dict[str, Any],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if recovery.get("required"):
        blockers.append(_cockpit_blocker(
            code="recovery_required",
            area="recovery",
            what="Cannot open a new position because recovery or cleanup is required.",
            why="PG/exchange/order evidence must agree before another bounded action.",
            severity="recovery_required",
            clears_when=recovery.get("next_safe_action") or "Reconciliation confirms a clean state.",
            owner_action_required=True,
            system_action_available=False,
            route="/recovery",
            evidence_source="recovery_exception_state",
        ))
    if active_position.get("exists"):
        blockers.append(_cockpit_blocker(
            code="active_position_open",
            area="position",
            what=f"Cannot open a new position because current {active_position.get('symbol') or ''} position is still open.",
            why="The budgeted loop is single-position by default.",
            severity="hard_blocker",
            clears_when="Position closes with PG/exchange evidence and review state is updated.",
            owner_action_required=False,
            system_action_available=False,
            route="/ledger",
            evidence_source=active_position.get("source") or "position_read_model",
        ))
    if protection.get("status") in {"orphaned", "partially_protected", "unprotected"}:
        blockers.append(_cockpit_blocker(
            code=f"protection_{protection.get('status')}",
            area="protection",
            what=f"Cannot confirm protection because protection status is {protection.get('status')}.",
            why="New entries must remain blocked when TP/SL coverage is missing or mismatched.",
            severity="hard_blocker",
            clears_when="Protection health shows TP and SL matched to the active position, or reconciliation clears stale protection.",
            owner_action_required=True,
            system_action_available=False,
            route="/protection",
            evidence_source="protection_health",
        ))
    if review.get("review_required_before_next_action"):
        blockers.append(_cockpit_blocker(
            code="review_required_before_next_action",
            area="review",
            what="Owner review is required before the next budgeted attempt.",
            why="Closed or unresolved trade outcomes must be reviewed before another attempt.",
            severity="hard_blocker",
            clears_when="Review ledger records promote, revise, or park for the latest closed action.",
            owner_action_required=True,
            system_action_available=False,
            route="/review",
            evidence_source="review_state",
        ))
    if budget.get("another_action_allowed") is not True:
        revoked_or_paused = budget.get("revoked") is True or budget.get("paused") is True
        blockers.append(_cockpit_blocker(
            code="budget_not_actionable",
            area="budget",
            what=(
                "Cannot confirm another budgeted action because budget authorization is revoked."
                if budget.get("revoked") is True
                else "Cannot confirm another budgeted action because autonomy is paused."
                if budget.get("paused") is True
                else "Cannot confirm another budgeted action under the current budget envelope."
            ),
            why="Budget, attempts, freshness, pause, and revoke state must allow another action.",
            severity="hard_blocker" if budget.get("status") != "available" or revoked_or_paused else "warning",
            clears_when=(
                "Create a new Owner-approved budget authorization before further budgeted autonomy attempts."
                if budget.get("revoked") is True
                else "Resume or reset autonomy through the approved Operation Layer path before further attempts."
                if budget.get("paused") is True
                else "Budget envelope is available, not paused/revoked, and attempts remain."
            ),
            owner_action_required=True,
            system_action_available=False,
            route="/action-entry",
            evidence_source="budget_recommendation",
        ))
    for item in action_blockers:
        blockers.append(_cockpit_blocker(
            code=str(item.get("code") or "action_entry_blocker"),
            area="candidate",
            what=str(item.get("message") or "Candidate is blocked."),
            why="Candidate cannot reach official FinalGate until this clears.",
            severity="hard_blocker",
            clears_when="Complete Owner scope, authorization, and official preflight evidence.",
            owner_action_required=True,
            system_action_available=False,
            route="/action-entry",
            evidence_source="action_entry_readiness",
        ))
    if snap.unavailable:
        blockers.append(_cockpit_blocker(
            code="freshness_degraded",
            area="freshness",
            what="Some cockpit facts are unavailable or stale.",
            why="The Owner cannot rely on missing state for live-affecting decisions.",
            severity="warning",
            clears_when="Refresh status and restore the unavailable source.",
            owner_action_required=False,
            system_action_available=True,
            route="/",
            evidence_source="freshness",
        ))
    return blockers


def _cockpit_blocker(
    *,
    code: str,
    area: str,
    what: str,
    why: str,
    severity: str,
    clears_when: str,
    owner_action_required: bool,
    system_action_available: bool,
    route: str,
    evidence_source: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "area": area,
        "what": what,
        "why_matters": why,
        "severity": severity,
        "retryable": True,
        "clears_when": clears_when,
        "owner_action_required": owner_action_required,
        "system_action_available": system_action_available,
        "route": route,
        "evidence_source": evidence_source,
    }


def _cockpit_warnings(snap: TradingConsoleSnapshot) -> list[dict[str, Any]]:
    return [
        {
            "code": item.get("code") or "warning",
            "message": item.get("message") or item.get("error") or "Warning needs review.",
            "severity": item.get("severity") or "warning",
            "source": "trading_console_snapshot",
        }
        for item in snap.warnings
    ]


def _cockpit_controls(
    *,
    overall: dict[str, Any],
    recovery: dict[str, Any],
    review: dict[str, Any],
    budget: dict[str, Any],
    active_position: dict[str, Any],
    autonomy: dict[str, Any],
) -> list[dict[str, Any]]:
    can_pause = bool(autonomy.get("can_pause_autonomy", True))
    can_revoke = bool(budget.get("can_revoke_budget"))
    return [
        {
            "control_id": "refresh_status",
            "label": "刷新状态",
            "enabled": True,
            "kind": "frontend_refresh",
            "route": "/",
            "confirmation_required": False,
            "disabled_reason": None,
            "post_action_result": "Cockpit reloads PG/exchange read models.",
        },
        {
            "control_id": "reconcile_now",
            "label": "读取交易所并核对",
            "enabled": True,
            "kind": "read_model_refresh",
            "route": "/recovery",
            "confirmation_required": False,
            "disabled_reason": None,
            "post_action_result": "Refreshes cockpit with include_exchange=true; it does not mutate PG.",
        },
        {
            "control_id": "pause_autonomy",
            "label": "预检暂停自治",
            "enabled": can_pause,
            "kind": "operation_layer_preflight",
            "operation_type": "enter_pause",
            "preflight_endpoint": "POST /api/brc/operations/preflight",
            "confirm_endpoint": "POST /api/brc/operations/{operation_id}/confirm",
            "confirmation_required": True,
            "disabled_reason": autonomy.get("pause_disabled_reason") if not can_pause else None,
            "scope": {"active_position": active_position.get("symbol"), "budget_status": budget.get("status")},
            "requires_confirmation": True,
            "confirmation_summary": [
                "Temporarily prevents further autonomy/action attempts.",
                "Does not close active positions.",
                "Does not cancel TP/SL orders.",
                "Does not transfer or withdraw funds.",
            ],
            "risk_impact": "暂停会临时阻断后续自治/预算动作；不会平仓、撤 TP/SL、下单、转账或提现。",
            "post_action_result": "Cockpit should show Autonomy Paused and next budgeted action blocked after confirmation.",
        },
        {
            "control_id": "revoke_budget",
            "label": "预检撤销预算",
            "enabled": can_revoke,
            "kind": "operation_layer_preflight",
            "operation_type": "revoke_budget",
            "preflight_endpoint": "POST /api/brc/operations/preflight",
            "confirm_endpoint": "POST /api/brc/operations/{operation_id}/confirm",
            "confirmation_required": True,
            "disabled_reason": budget.get("revoke_disabled_reason") if not can_revoke else None,
            "scope": {
                **dict(budget.get("authorized_scope") or {}),
                "budget_authorization_id": budget.get("budget_authorization_id"),
                "budget_authorization_status": budget.get("budget_authorization_status"),
            },
            "requires_confirmation": True,
            "confirmation_summary": [
                "Terminates the current budget authorization for future budgeted autonomy actions.",
                "Does not close active positions.",
                "Does not cancel TP/SL orders.",
                "Does not transfer or withdraw funds.",
                "Current active position/protection must still be monitored separately.",
            ],
            "risk_impact": "撤销预算会终止该预算授权下的后续预算自治动作；不会平仓、撤 TP/SL、转账或提现。",
            "post_action_result": "Cockpit should show Budget Revoked and future budgeted actions blocked after confirmation.",
        },
        {
            "control_id": "view_recovery_recommendation",
            "label": "查看恢复建议",
            "enabled": True,
            "kind": "navigate",
            "route": "/recovery",
            "confirmation_required": False,
            "disabled_reason": None,
            "owner_action_required": bool(recovery.get("owner_action_required")),
        },
        {
            "control_id": "open_review_item",
            "label": "打开复盘",
            "enabled": True,
            "kind": "navigate",
            "route": "/review",
            "confirmation_required": False,
            "disabled_reason": None,
            "owner_action_required": bool(review.get("review_required_before_next_action")),
        },
        {
            "control_id": "view_evidence",
            "label": "查看证据",
            "enabled": True,
            "kind": "expand_details",
            "route": None,
            "confirmation_required": False,
            "disabled_reason": None,
            "current_status": overall.get("status"),
        },
    ]


def _position_notional(entry: Any, quantity: Any) -> Optional[str]:
    price = _decimal_from_any(entry)
    qty = _decimal_from_any(quantity)
    if price is None or qty is None:
        return None
    return str(abs(price * qty))


def _status_label(value: str) -> str:
    return {
        "safe": "Safe",
        "warning": "Warning",
        "blocked": "Blocked",
        "paused": "Paused",
        "active_position": "Active Position",
        "review_required": "Review Required",
        "recovery_required": "Recovery Required",
        "revoked": "Revoked",
    }.get(value, value)


def _autonomy_label(value: str) -> str:
    return {
        "idle": "Idle",
        "budget_available": "Budget available",
        "candidate_selected": "Candidate selected",
        "final_gate_checking": "FinalGate checking",
        "waiting_position_close": "Waiting for position close",
        "closed_review_pending": "Closed, review pending",
        "closed_reviewed": "Closed and reviewed",
        "blocked_with_retry_condition": "Blocked with retry condition",
        "paused": "Paused",
        "revoked": "Revoked",
        "recovery_required": "Recovery required",
    }.get(value, value)


def _autonomy_message(
    *,
    state: str,
    active_position: dict[str, Any],
    protection: dict[str, Any],
    budget: dict[str, Any],
    authorization: dict[str, Any],
) -> str:
    if state == "waiting_position_close":
        return "Autonomy is waiting for the active position to close via TP/SL or verified exit."
    if state == "recovery_required":
        return "Autonomy is blocked until recovery or reconciliation clears."
    if state == "closed_review_pending":
        return "Autonomy is waiting for Owner review before another attempt."
    if state == "budget_available":
        return "Budget appears available, but Owner confirmation and FinalGate remain required."
    if state == "candidate_selected":
        return "A candidate is selected for review; execution remains disabled in this read model."
    if state == "paused":
        return "Autonomy is paused. Budget may still exist but no new action should start."
    if state == "revoked":
        return "Budget authorization is revoked. Future budgeted autonomy actions require re-authorization."
    if authorization.get("blocking_reason"):
        return f"Autonomy is blocked by authorization: {authorization.get('blocking_reason')}."
    if budget.get("status") != "available":
        return "Autonomy is blocked because budget is not currently actionable."
    if protection.get("status") not in {"protected", "unknown"} and active_position.get("exists"):
        return "Autonomy is blocked because protection is not complete."
    return "Autonomy is not executing; current state is controlled by backend gates."


def _budget_label(value: str) -> str:
    return {
        "available": "Budget available",
        "degraded_missing_account_facts": "Budget degraded: missing account facts",
        "blocked_no_capacity": "Budget blocked: no capacity",
        "not_available": "Budget not available",
        "revoked": "Budget revoked",
        "available_metadata_only": "Budget metadata available",
    }.get(str(value), str(value))


def _protection_label(value: str) -> str:
    return {
        "protected": "Protected",
        "partially_protected": "Partially protected",
        "unprotected": "Protection missing",
        "unknown": "Protection unknown",
        "orphaned": "Orphan protection suspected",
        "not_available": "Protection not available",
    }.get(str(value), str(value))


def _order_item(order: Any) -> dict[str, Any]:
    status = _enum_value(getattr(order, "status", None))
    order_type = _enum_value(getattr(order, "order_type", getattr(order, "type", None)))
    order_role = _enum_value(getattr(order, "order_role", None))
    direction = _enum_value(getattr(order, "direction", getattr(order, "side", None)))
    return {
        "order_id": str(getattr(order, "id", getattr(order, "order_id", "unknown"))),
        "signal_id": getattr(order, "signal_id", None),
        "symbol": getattr(order, "symbol", None),
        "direction": direction,
        "side": direction,
        "order_type": order_type,
        "order_role": order_role,
        "status": status,
        "price": _scalar(getattr(order, "price", None)),
        "trigger_price": _scalar(getattr(order, "trigger_price", None)),
        "requested_qty": _scalar(getattr(order, "requested_qty", getattr(order, "qty", None))),
        "filled_qty": _scalar(getattr(order, "filled_qty", None)),
        "average_exec_price": _scalar(getattr(order, "average_exec_price", None)),
        "reduce_only": bool(getattr(order, "reduce_only", False)),
        "exchange_order_id": getattr(order, "exchange_order_id", None),
        "parent_order_id": getattr(order, "parent_order_id", None),
        "oco_group_id": getattr(order, "oco_group_id", None),
        "runtime_instance_id": getattr(order, "runtime_instance_id", None),
        "trial_binding_id": getattr(order, "trial_binding_id", None),
        "strategy_family_id": getattr(order, "strategy_family_id", None),
        "strategy_family_version_id": getattr(order, "strategy_family_version_id", None),
        "signal_evaluation_id": getattr(order, "signal_evaluation_id", None),
        "order_candidate_id": getattr(order, "order_candidate_id", None),
        "exit_reason": getattr(order, "exit_reason", None),
        "filled_at": getattr(order, "filled_at", None),
        "created_at": getattr(order, "created_at", None),
        "updated_at": getattr(order, "updated_at", None),
        "source": "pg",
    }


def _exchange_order_item(order: Any, *, source: str) -> dict[str, Any]:
    if not isinstance(order, dict):
        order = _plain_dict(order)
    info = order.get("info") if isinstance(order.get("info"), dict) else {}
    exchange_order_id = order.get("id") or order.get("orderId") or info.get("orderId")
    return {
        "order_id": None,
        "exchange_order_id": str(exchange_order_id) if exchange_order_id is not None else None,
        "symbol": order.get("symbol") or info.get("symbol"),
        "direction": order.get("side") or info.get("side"),
        "side": order.get("side") or info.get("side"),
        "order_type": order.get("type") or info.get("type"),
        "order_role": "SL" if source == "exchange_stop" else "unknown",
        "status": order.get("status") or info.get("status"),
        "price": _scalar(order.get("price")),
        "trigger_price": _scalar(order.get("stopPrice") or order.get("triggerPrice") or info.get("stopPrice")),
        "requested_qty": _scalar(order.get("amount") or order.get("qty") or info.get("origQty")),
        "filled_qty": _scalar(order.get("filled") or info.get("executedQty")),
        "average_exec_price": _scalar(order.get("average")),
        "reduce_only": _truthy(order.get("reduceOnly") or info.get("reduceOnly")),
        "position_side": info.get("positionSide") or order.get("positionSide"),
        "parent_order_id": None,
        "oco_group_id": None,
        "source": source,
    }


def _position_item(position: Any, *, source: str) -> dict[str, Any]:
    if isinstance(position, dict):
        info = position.get("info") if isinstance(position.get("info"), dict) else {}
        return {
            "position_id": str(position.get("id") or position.get("position_id") or info.get("positionId") or "unknown"),
            "signal_id": position.get("signal_id"),
            "symbol": position.get("symbol") or info.get("symbol"),
            "side": _enum_value(position.get("side") or position.get("direction") or info.get("positionSide")),
            "quantity": _scalar(
                position.get("current_qty")
                or position.get("quantity")
                or position.get("contracts")
                or position.get("size")
                or info.get("positionAmt")
            ),
            "entry_price": _scalar(position.get("entry_price") or position.get("entryPrice") or info.get("entryPrice")),
            "mark_price": _scalar(position.get("mark_price") or position.get("markPrice") or info.get("markPrice")),
            "unrealized_pnl": _scalar(position.get("unrealized_pnl") or position.get("unrealizedPnl") or info.get("unRealizedProfit")),
            "realized_pnl": _scalar(position.get("realized_pnl") or position.get("realizedPnl")),
            "leverage": _scalar(position.get("leverage") or info.get("leverage")),
            "margin_mode": position.get("margin_mode") or position.get("marginMode") or info.get("marginType"),
            "is_closed": position.get("is_closed"),
            "updated_at": position.get("updated_at") or position.get("timestamp"),
            "runtime_instance_id": position.get("runtime_instance_id"),
            "trial_binding_id": position.get("trial_binding_id"),
            "strategy_family_id": position.get("strategy_family_id"),
            "strategy_family_version_id": position.get("strategy_family_version_id"),
            "signal_evaluation_id": position.get("signal_evaluation_id"),
            "order_candidate_id": position.get("order_candidate_id"),
            "source": source,
        }
    return {
        "position_id": str(getattr(position, "id", getattr(position, "position_id", "unknown"))),
        "signal_id": getattr(position, "signal_id", None),
        "symbol": getattr(position, "symbol", None),
        "side": _enum_value(getattr(position, "side", getattr(position, "direction", None))),
        "quantity": _scalar(getattr(position, "current_qty", getattr(position, "quantity", getattr(position, "size", None)))),
        "entry_price": _scalar(getattr(position, "entry_price", None)),
        "mark_price": _scalar(getattr(position, "mark_price", None)),
        "unrealized_pnl": _scalar(getattr(position, "unrealized_pnl", None)),
        "realized_pnl": _scalar(getattr(position, "realized_pnl", None)),
        "leverage": _scalar(getattr(position, "leverage", None)),
        "margin_mode": getattr(position, "margin_mode", None),
        "is_closed": getattr(position, "is_closed", None),
        "updated_at": getattr(position, "updated_at", None),
        "runtime_instance_id": getattr(position, "runtime_instance_id", None),
        "trial_binding_id": getattr(position, "trial_binding_id", None),
        "strategy_family_id": getattr(position, "strategy_family_id", None),
        "strategy_family_version_id": getattr(position, "strategy_family_version_id", None),
        "signal_evaluation_id": getattr(position, "signal_evaluation_id", None),
        "order_candidate_id": getattr(position, "order_candidate_id", None),
        "source": source,
    }


def _account_snapshot_summary_from_snapshot(snapshot: Any) -> Optional[dict[str, Any]]:
    if snapshot is None:
        return None
    positions = getattr(snapshot, "positions", []) or []
    return {
        "status": "available",
        "total_balance": _scalar(getattr(snapshot, "total_balance", None)),
        "available_balance": _scalar(getattr(snapshot, "available_balance", None)),
        "unrealized_pnl": _scalar(getattr(snapshot, "unrealized_pnl", None)),
        "timestamp_ms": getattr(snapshot, "timestamp", None),
        "positions_count": len(positions),
    }


def _intent_item(intent: Any) -> dict[str, Any]:
    signal = getattr(intent, "signal", None)
    signal_payload = (
        signal.model_dump(mode="json")
        if signal is not None and hasattr(signal, "model_dump")
        else getattr(intent, "signal_payload", {}) or {}
    )
    return {
        "intent_id": str(getattr(intent, "id", getattr(intent, "intent_id", "unknown"))),
        "signal_id": getattr(intent, "signal_id", None),
        "symbol": getattr(intent, "symbol", None) or signal_payload.get("symbol"),
        "side": signal_payload.get("direction"),
        "status": _enum_value(getattr(intent, "status", None)),
        "order_id": getattr(intent, "order_id", None),
        "authorization_id": getattr(intent, "authorization_id", None),
        "runtime_instance_id": getattr(intent, "runtime_instance_id", None),
        "trial_binding_id": getattr(intent, "trial_binding_id", None),
        "strategy_family_id": getattr(intent, "strategy_family_id", None),
        "strategy_family_version_id": getattr(intent, "strategy_family_version_id", None),
        "signal_evaluation_id": getattr(intent, "signal_evaluation_id", None),
        "order_candidate_id": getattr(intent, "order_candidate_id", None),
        "exchange_order_id": getattr(intent, "exchange_order_id", None),
        "blocked_reason": getattr(intent, "blocked_reason", None),
        "blocked_message": getattr(intent, "blocked_message", None),
        "failed_reason": getattr(intent, "failed_reason", None),
        "created_at": getattr(intent, "created_at", None),
        "updated_at": getattr(intent, "updated_at", None),
    }


def _audit_item(item: Any) -> dict[str, Any]:
    return {
        "audit_id": str(getattr(item, "id", "unknown")),
        "order_id": getattr(item, "order_id", None),
        "signal_id": getattr(item, "signal_id", None),
        "old_status": getattr(item, "old_status", None),
        "new_status": getattr(item, "new_status", None),
        "event_type": _enum_value(getattr(item, "event_type", None)),
        "triggered_by": _enum_value(getattr(item, "triggered_by", None)),
        "metadata": _json_value(getattr(item, "metadata", None)),
        "created_at": getattr(item, "created_at", None),
    }


def _signal_item(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return _plain_dict(item)
    return _plain_dict(item)


def _enum_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if value is None:
        return None
    return str(value)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_bool_env(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _operational_drift_summary(startup_summary: dict[str, Any]) -> dict[str, Any]:
    runtime_version = _runtime_server_version_summary(startup_summary)
    migration = _migration_drift_summary(startup_summary)
    return {
        "runtime_server_version": runtime_version,
        "migration": migration,
        "requires_recovery": bool(
            runtime_version.get("drift") is True
            or migration.get("mismatch") is True
        ),
    }


def _runtime_server_version_summary(startup_summary: dict[str, Any]) -> dict[str, Any]:
    explicit_drift = _parse_bool_env(
        _string_or_none(
            _mapping_value(
                startup_summary,
                "runtime_server_version_drift",
                "version_drift",
                "server_version_drift",
            )
            or _env_value(
                "BRC_RUNTIME_SERVER_VERSION_DRIFT",
                "RUNTIME_SERVER_VERSION_DRIFT",
                "SERVER_VERSION_DRIFT",
            )
        )
    )
    runtime_version = (
        _mapping_value(
            startup_summary,
            "runtime_git_sha",
            "runtime_commit",
            "runtime_version",
            "git_sha",
            "commit_sha",
        )
        or _env_value(
            "BRC_RUNTIME_COMMIT",
            "BRC_DEPLOY_COMMIT",
            "GIT_COMMIT",
            "GIT_SHA",
            "SOURCE_COMMIT",
            "APP_COMMIT",
            "RENDER_GIT_COMMIT",
        )
    )
    server_version = (
        _mapping_value(
            startup_summary,
            "server_git_sha",
            "server_commit",
            "server_version",
            "deployed_git_sha",
            "deployed_commit",
            "expected_git_sha",
            "expected_commit",
            "release_git_sha",
            "release_commit",
        )
        or _env_value(
            "BRC_SERVER_COMMIT",
            "BRC_EXPECTED_COMMIT",
            "BRC_RELEASE_COMMIT",
            "SERVER_GIT_SHA",
            "DEPLOYED_GIT_SHA",
            "EXPECTED_GIT_SHA",
            "RELEASE_GIT_SHA",
        )
    )
    if explicit_drift is not None:
        drift = explicit_drift
        status = "drift" if drift else "match"
        detectable = True
    elif runtime_version and server_version:
        drift = str(runtime_version) != str(server_version)
        status = "drift" if drift else "match"
        detectable = True
    else:
        drift = None
        status = "not_detectable"
        detectable = False
    return {
        "status": status,
        "detectable": detectable,
        "drift": drift,
        "runtime_version": runtime_version or "not_available",
        "server_version": server_version or "not_available",
        "missing_evidence": [] if detectable else _missing_version_evidence(runtime_version, server_version),
    }


def _migration_drift_summary(startup_summary: dict[str, Any]) -> dict[str, Any]:
    explicit_mismatch = _parse_bool_env(
        _string_or_none(
            _mapping_value(
                startup_summary,
                "pending_migration_mismatch",
                "migration_mismatch",
                "alembic_mismatch",
            )
            or _env_value(
                "BRC_PENDING_MIGRATION_MISMATCH",
                "PENDING_MIGRATION_MISMATCH",
                "ALEMBIC_MISMATCH",
            )
        )
    )
    current_revision = (
        _mapping_value(
            startup_summary,
            "alembic_current_revision",
            "current_alembic_revision",
            "db_revision",
            "db_alembic_revision",
            "migration_current",
        )
        or _env_value(
            "BRC_ALEMBIC_CURRENT",
            "ALEMBIC_CURRENT",
            "DB_ALEMBIC_REVISION",
            "DB_REVISION",
        )
    )
    expected_head = (
        _mapping_value(
            startup_summary,
            "alembic_expected_head",
            "expected_alembic_head",
            "alembic_head",
            "migration_head",
            "migration_expected_head",
        )
        or _env_value(
            "BRC_ALEMBIC_HEAD",
            "ALEMBIC_HEAD",
            "EXPECTED_ALEMBIC_HEAD",
            "MIGRATION_HEAD",
        )
    )
    if explicit_mismatch is not None:
        mismatch = explicit_mismatch
        status = "mismatch" if mismatch else "match"
        detectable = True
    elif current_revision and expected_head:
        mismatch = str(current_revision) != str(expected_head)
        status = "mismatch" if mismatch else "match"
        detectable = True
    else:
        mismatch = None
        status = "not_detectable"
        detectable = False
    return {
        "status": status,
        "detectable": detectable,
        "mismatch": mismatch,
        "current_revision": current_revision or "not_available",
        "expected_head": expected_head or "not_available",
        "missing_evidence": [] if detectable else _missing_migration_evidence(current_revision, expected_head),
    }


def _mapping_value(mapping: dict[str, Any], *keys: str) -> Optional[str]:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        text = _string_or_none(value)
        if text is not None:
            return text
    return None


def _env_value(*names: str) -> Optional[str]:
    for name in names:
        text = _string_or_none(os.environ.get(name))
        if text is not None:
            return text
    return None


def _string_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _missing_version_evidence(runtime_version: Any, server_version: Any) -> list[str]:
    missing: list[str] = []
    if not runtime_version:
        missing.append("runtime_version")
    if not server_version:
        missing.append("server_version")
    return missing


def _missing_migration_evidence(current_revision: Any, expected_head: Any) -> list[str]:
    missing: list[str] = []
    if not current_revision:
        missing.append("current_revision")
    if not expected_head:
        missing.append("expected_head")
    return missing


def _normalized_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts
