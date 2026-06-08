"""Read-only Trading Console aggregation models.

This module composes existing repositories and runtime adapters into frontend
read models. It intentionally has no mutation methods and never calls exchange
write APIs.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
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
from src.application.notional_sizing import (
    ContractMarketRules,
    compute_notional_sizing,
    validate_fixed_quantity_scope,
)
from src.application.owner_action_carrier_catalog import owner_action_carrier_id_for_symbol
from src.application.production_strategy_family_admission import (
    build_production_strategy_family_admission_state,
)


DEFAULT_SYMBOL = "BNB/USDT:USDT"
DEFAULT_CARRIER_ID = "MI-001-BNB-LONG"
DEFAULT_STRATEGY_FAMILY_ID = "MI-001"
EXCHANGE_READ_TIMEOUT_SECONDS = 8.0
OPEN_ORDER_STATUSES = {"OPEN", "PARTIALLY_FILLED", "open", "partially_filled"}
PROTECTION_ROLES = {"SL", "TP1", "TP2", "TP3", "TP4", "TP5"}
TERMINAL_INTENT_STATUSES = {"blocked", "failed", "completed"}


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
    owner_trial_flow_service: Optional[Any] = None
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
    signal_records: list[dict[str, Any]]
    authorization_state: dict[str, Any]
    exchange: dict[str, Any]
    warnings: list[dict[str, Any]]
    unavailable: list[dict[str, Any]]


class TradingConsoleReadModelService:
    """Build Trading Console read models from read-only dependencies."""

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
        signal_records = await self._read_signals(symbol=symbol, limit=limit, unavailable=unavailable)
        authorization_state = await self._read_authorization_state(
            carrier_id=DEFAULT_CARRIER_ID,
            unavailable=unavailable,
        )
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
            signal_records=signal_records,
            authorization_state=authorization_state,
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
                    "status": "blocked" if blockers else "read_only_no_execute_endpoint",
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
                    "reason": "read_only_sprint_does_not_wrap_execute",
                },
                "deferred_execute_endpoint": True,
            },
        )

    async def review_state(
        self,
        *,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> TradingConsoleReadModelResponse:
        snap = await self.snapshot(symbol=symbol, include_exchange=False, limit=limit)
        filled_orders = [
            order for order in snap.pg_orders
            if order.get("filled_qty") not in {None, "0", "0E-18", "0.0"}
            or order.get("average_exec_price") is not None
        ]
        return self._response(
            "review_state",
            snap,
            data={
                "reviews": snap.review_records,
                "filled_order_facts": filled_orders,
                "positions": snap.pg_positions,
                "unavailable_fields": {
                    "fills_table": "not_available",
                    "fee": "not_available",
                    "fee_asset": "not_available",
                    "funding": "not_available",
                    "slippage": "not_available",
                },
            },
        )

    async def audit_chain(
        self,
        *,
        authorization_id: Optional[str] = None,
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
        )
        chain_intents = self._filter_chain_intents(
            snap.pg_intents,
            authorization_id=authorization_id,
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
                        "status": "blocked" if blocked_reasons else "read_only_available",
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
            owner_selection=raw_owner_selection,
        )
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
        selected_candidate = _select_action_entry_candidate(
            market_input=normalized_market_input,
            owner_scope=owner_scope or {},
            candidate_output=candidate_output,
            generic_action_specs=generic_action_specs,
            payload_contracts=payload_contracts,
            action_entry_output=action_entry_output,
        )
        return {
            "owner_market_input": normalized_market_input,
            "budget_recommendation": budget,
            "selected_candidate": selected_candidate,
            "risk_review": _action_entry_risk_review(
                selected_candidate=selected_candidate,
                adapter_contract=state.generic_final_gate_adapter_contract.model_dump(mode="json"),
                blockers=blockers,
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
            "post_action_state": _action_entry_post_action_state(snap),
            "generic_final_gate_adapter_contract": (
                state.generic_final_gate_adapter_contract.model_dump(mode="json")
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
                    "GET /api/trading-console/dashboard-state",
                    "GET /api/trading-console/account-risk",
                    "GET /api/trading-console/order-ledger",
                    "GET /api/trading-console/protection-health",
                    "GET /api/trading-console/recovery-exception-state",
                    "GET /api/trading-console/authorization-state",
                    "GET /api/trading-console/execution-control-state",
                    "GET /api/trading-console/review-state",
                    "GET /api/trading-console/audit-chain",
                    "GET /api/trading-console/carrier-availability",
                    "GET /api/trading-console/strategy-family-admission-state",
                    "GET /api/trading-console/action-entry-readiness",
                    "GET /api/trading-console/budget-recommendation",
                    "GET /api/trading-console/signal-marker-feed",
                    "GET /api/trading-console/api-classification",
                ],
                "internal_or_legacy": [
                    "/api/brc/*",
                    "/api/runtime/*",
                    "/api/dev/testnet/brc/*",
                ],
                "action_api_policy": "deferred_not_exposed_in_trading_console_v1",
                "sample_data_policy": "not_allowed_as_trading_console_truth_source",
            },
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
    ) -> list[dict[str, Any]]:
        if not order_id and not exchange_order_id:
            return orders
        matched = []
        parent_ids = set()
        for order in orders:
            if (
                (order_id and order.get("order_id") == order_id)
                or (exchange_order_id and str(order.get("exchange_order_id")) == str(exchange_order_id))
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
        intent_id: Optional[str],
        order_ids: set[str],
        exchange_order_ids: set[str],
    ) -> list[dict[str, Any]]:
        if not authorization_id and not intent_id and not order_ids and not exchange_order_ids:
            return intents
        return [
            intent for intent in intents
            if (authorization_id and intent.get("authorization_id") == authorization_id)
            or (intent_id and intent.get("intent_id") == intent_id)
            or (intent.get("order_id") and str(intent.get("order_id")) in order_ids)
            or (
                intent.get("exchange_order_id")
                and str(intent.get("exchange_order_id")) in exchange_order_ids
            )
        ]


def _now_ms() -> int:
    return int(time.time() * 1000)


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
    risk_tier = _normalized_risk_tier(value.get("risk_tier"))
    note = _optional_nonempty_str(value.get("note"))
    if note is not None and len(note) > 500:
        note = f"{note[:500]}..."
    return {
        "regime": regime,
        "mapped_family": _market_regime_family(regime),
        "symbol_preference": symbol_preference,
        "side": side,
        "risk_tier": risk_tier,
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
) -> dict[str, Any]:
    action_spec = dict(selected_candidate.get("generic_action_spec") or {})
    warnings = _dedupe_strings(
        [
            *[str(item) for item in action_spec.get("warnings") or []],
            *[str(item) for item in adapter_contract.get("warning_not_blocker") or []],
        ]
    )
    hard_blockers = _dedupe_strings(
        [
            *[str(item) for item in action_spec.get("hard_blockers") or []],
            *[str(item.get("code") or item.get("message")) for item in blockers],
        ]
    )
    return {
        "warning_policy": "warnings_require_owner_review_but_do_not_enable_action",
        "weak_strategy_evidence_policy": "warning_not_hard_blocker",
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
        "note": "Authorization draft creation is not performed by this read model.",
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
    day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    exchange_state = _post_action_exchange_state(
        snap=snap,
        entry_orders=entry_orders,
        protection_orders=protection_orders,
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
        "review_count": len(snap.review_records),
        "audit_event_count": len(snap.audit_events),
        "retry_safety": "consumed_authorization_or_completed_intent_blocks_duplicate_execution",
        "exchange_state": exchange_state,
        "review_ledger": _post_action_review_ledger(
            entry_orders=entry_orders,
            protection_orders=protection_orders,
            reviews=snap.review_records,
        ),
        "summary": {
            "intents": snap.pg_intents[:5],
            "entry_orders": entry_orders[:5],
            "tp_sl_orders": protection_orders[:5],
            "reviews": snap.review_records[:5],
            "audit_events": snap.audit_events[:5],
        },
    }


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
) -> dict[str, Any]:
    entry_order = entry_orders[0] if entry_orders else None
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
    if exit_orders:
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
        "strategy_outcome": (
            "pending_closed_trade_review"
            if lifecycle_status == "closed_from_pg_exit_order"
            else "revise_after_external_flat_reconciliation"
            if lifecycle_status == "closed_external_exchange_flat_unresolved"
            else "pending_post_action_review"
        ),
        "review_decision": {
            "status": (
                "revise"
                if lifecycle_status == "closed_external_exchange_flat_unresolved"
                else "pending" if reviews else "not_recorded"
            ),
            "allowed_values": ["promote", "revise", "park"],
            "requires_owner_review": True,
            **(
                {"source": "system_reconciliation_review"}
                if lifecycle_status == "closed_external_exchange_flat_unresolved"
                else {}
            ),
        },
        "warnings": [
            "fee_not_available",
            "funding_not_available",
            "slippage_not_available",
        ],
        "hard_blockers": [],
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
            "status": post_action.get("status") or "empty",
            "summary": (
                f"{post_action.get('intent_count', 0)} intents / "
                f"{post_action.get('entry_order_count', 0)} entries / "
                f"{post_action.get('protection_order_count', 0)} TP-SL / "
                f"{post_action.get('review_count', 0)} reviews / "
                f"{post_action.get('audit_event_count', 0)} audit events"
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
    review_ledger = dict(post_action.get("review_ledger") or {})
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
    )
    daily_state = BudgetedAutonomyDailyState(
        day_key=day_key,
        attempts_used=daily_attempts_used,
        attempts_allowed=max_attempts,
        budget_used_notional=Decimal("0"),
        realized_loss=Decimal("0"),
        source="trading_console_selected_symbol_pg_intents_current_utc_day",
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
) -> int:
    selected_symbol = str(symbol or "")
    counts = dict(post_action.get("completed_intents_today_by_symbol") or {})
    if selected_symbol:
        parsed_count = _optional_int_value(counts.get(selected_symbol))
        if parsed_count is not None:
            return parsed_count
    elif counts:
        return sum(_optional_int_value(item) or 0 for item in counts.values())
    day_start_ms = _day_start_ms(day_key)
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
        if created_at is None or created_at < day_start_ms:
            continue
        count += 1
    return count


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
    return BudgetedAutonomyCandidateInput(
        candidate_id=str(spec.get("action_candidate_ref") or spec.get("carrier_id") or "unknown"),
        family=str(spec.get("family") or "unknown"),
        carrier_id=str(spec.get("carrier_id") or "unknown"),
        symbol=str(spec.get("symbol") or (spec.get("supported_symbols") or ["unknown"])[0]),
        side=_normalize_side(spec.get("side")),
        status=str(spec.get("status") or "invalid_blocked"),
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
        hard_blockers=list(spec.get("hard_blockers") or []),
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


def _normalized_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts
