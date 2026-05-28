"""Local BRC live read-only detection runner skeleton.

The runner is intentionally local and evidence-only. It reads market/account
snapshots, drives existing BRC Operation Layer signal-evaluation and
trial-trade-intent recording operations, and never calls execution-intent or
order APIs.
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from typing import Any, Awaitable, Callable, Optional, Protocol

from pydantic import BaseModel, Field, field_validator

from src.application.execution_permission import ExecutionPermission, parse_execution_permission_max


def _now_ms() -> int:
    return int(time.time() * 1000)


class LiveReadOnlyRunnerConfig(BaseModel):
    trading_env: str = "simulation"
    brc_execution_permission_max: ExecutionPermission = ExecutionPermission.READ_ONLY
    campaign_id: Optional[str] = None
    binding_id: Optional[str] = None
    symbols: tuple[str, ...]
    interval_seconds: float = Field(default=60.0, ge=0)
    max_iterations: int = Field(default=1, ge=1)
    intended_action: str = "entry"
    side: Optional[str] = "long"
    requested_by: str = "owner"
    source_ref: str = "brc_live_read_only_detection_runner"

    @field_validator("brc_execution_permission_max", mode="before")
    @classmethod
    def parse_permission(cls, value: Any) -> ExecutionPermission:
        return parse_execution_permission_max(value)

    @field_validator("symbols")
    @classmethod
    def require_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        symbols = tuple(str(item).strip() for item in value if str(item).strip())
        if not symbols:
            raise ValueError("at least one symbol is required")
        return symbols

    @field_validator("campaign_id", "binding_id")
    @classmethod
    def normalize_optional_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def target_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if self.campaign_id:
            params["campaign_id"] = self.campaign_id
        if self.binding_id:
            params["binding_id"] = self.binding_id
        return params


class LiveReadOnlyRunnerError(RuntimeError):
    """Raised when the local read-only detection runner must refuse execution."""


class MarketAccountSnapshotProvider(Protocol):
    async def read_account_facts(self) -> dict[str, Any]:
        ...

    async def read_market_snapshot(self, *, symbol: str) -> dict[str, Any]:
        ...


class ExchangeGatewayReadOnlySnapshotProvider:
    """Read-only market/account snapshot provider for the local runner."""

    def __init__(
        self,
        *,
        gateway: Any,
        symbols: tuple[str, ...],
        account_source: str = "exchange_live",
        truth_level: str = "exchange_read",
    ) -> None:
        self._gateway = gateway
        self._symbols = tuple(symbols)
        self._account_source = account_source
        self._truth_level = truth_level

    async def read_account_facts(self) -> dict[str, Any]:
        balance_snapshot = None
        if hasattr(self._gateway, "fetch_account_balance"):
            balance_snapshot = await self._gateway.fetch_account_balance()
        positions = await self._fetch_positions()
        open_orders = await self._fetch_open_orders()
        timestamp_ms = _now_ms()
        if balance_snapshot is not None and getattr(balance_snapshot, "timestamp", None) is not None:
            timestamp_ms = int(getattr(balance_snapshot, "timestamp"))
        return {
            "source": self._account_source,
            "truth_level": self._truth_level,
            "freshness": "fresh",
            "timestamp_ms": timestamp_ms,
            "balance": _account_snapshot_summary(balance_snapshot),
            "position_count": len(positions),
            "open_order_count": len(open_orders),
            "reconciliation_status": {"status": "clean"},
            "unknown_unmanaged_counts": {
                "orders": len(open_orders),
                "positions": len(positions),
            },
            "read_only_provider": "exchange_gateway_read_only_snapshot_provider",
        }

    async def read_market_snapshot(self, *, symbol: str) -> dict[str, Any]:
        price = await self._gateway.fetch_ticker_price(symbol)
        return {
            "source": "exchange_live_market",
            "symbol": symbol,
            "mark_price": str(price),
            "timestamp_ms": _now_ms(),
            "read_only_provider": "exchange_gateway_read_only_snapshot_provider",
        }

    async def _fetch_positions(self) -> list[Any]:
        if not hasattr(self._gateway, "fetch_positions"):
            return []
        try:
            positions = await self._gateway.fetch_positions(symbol=None)
        except TypeError:
            positions = await self._gateway.fetch_positions()
        return list(positions or [])

    async def _fetch_open_orders(self) -> list[dict[str, Any]]:
        if not hasattr(self._gateway, "fetch_open_orders"):
            return []
        orders: list[dict[str, Any]] = []
        for symbol in self._symbols:
            fetched = await self._gateway.fetch_open_orders(symbol)
            orders.extend(list(fetched or []))
        return orders


class OperationServiceProtocol(Protocol):
    async def preflight(
        self,
        *,
        operation_type: str,
        requested_by: str,
        input_params: dict[str, Any],
        source: Optional[dict[str, Any]] = None,
    ) -> Any:
        ...

    async def confirm(
        self,
        *,
        operation_id: str,
        preflight_id: str,
        confirmation_phrase: str,
        idempotency_key: str,
        confirmed_by: Optional[str] = None,
    ) -> Any:
        ...


class RunnerIterationEvidence(BaseModel):
    iteration_id: str
    iteration_index: int
    symbol: str
    started_at_ms: int
    completed_at_ms: int
    status: str
    skipped_reason: Optional[str] = None
    account_facts_snapshot: dict[str, Any] = Field(default_factory=dict)
    market_snapshot: dict[str, Any] = Field(default_factory=dict)
    runtime_safety_snapshot: dict[str, Any] = Field(default_factory=dict)
    signal_preflight: dict[str, Any] = Field(default_factory=dict)
    signal_result: dict[str, Any] = Field(default_factory=dict)
    trial_trade_intent_preflight: dict[str, Any] = Field(default_factory=dict)
    trial_trade_intent_result: dict[str, Any] = Field(default_factory=dict)
    execution_permission_resolution: dict[str, Any] = Field(default_factory=dict)
    not_executed_reason: Optional[str] = None
    safety: dict[str, Any] = Field(default_factory=dict)


class BrcLiveReadOnlyDetectionRunner:
    """Manual local runner for one campaign/binding and limited symbols."""

    def __init__(
        self,
        *,
        operation_service: OperationServiceProtocol,
        snapshot_provider: MarketAccountSnapshotProvider,
        audit_writable: Callable[[], Awaitable[bool]],
        runtime_safety_reader: Optional[Callable[[], Awaitable[dict[str, Any]]]] = None,
        iteration_recorder: Optional[Callable[[RunnerIterationEvidence], Awaitable[None]]] = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now_ms: Callable[[], int] = _now_ms,
    ) -> None:
        self._operation_service = operation_service
        self._snapshot_provider = snapshot_provider
        self._audit_writable = audit_writable
        self._runtime_safety_reader = runtime_safety_reader
        self._iteration_recorder = iteration_recorder
        self._sleep = sleep
        self._now_ms = now_ms

    async def run(self, config: LiveReadOnlyRunnerConfig) -> list[RunnerIterationEvidence]:
        self._validate_runner_config(config)
        results: list[RunnerIterationEvidence] = []
        for iteration_index in range(config.max_iterations):
            for symbol in config.symbols:
                results.append(
                    await self.run_once(
                        config,
                        symbol=symbol,
                        iteration_index=len(results),
                    )
                )
            if iteration_index + 1 < config.max_iterations and config.interval_seconds > 0:
                await self._sleep(config.interval_seconds)
        return results

    async def run_once(
        self,
        config: LiveReadOnlyRunnerConfig,
        *,
        symbol: Optional[str] = None,
        iteration_index: int = 0,
    ) -> RunnerIterationEvidence:
        self._validate_runner_config(config)
        selected_symbol = symbol or config.symbols[0]
        started_at_ms = self._now_ms()
        iteration_id = f"brc-readonly-{started_at_ms}-{iteration_index}"
        safety_snapshot = await self._runtime_safety_snapshot()
        account_facts = await self._snapshot_provider.read_account_facts()
        market_snapshot = await self._snapshot_provider.read_market_snapshot(symbol=selected_symbol)

        base_evidence = {
            "iteration_id": iteration_id,
            "iteration_index": iteration_index,
            "symbol": selected_symbol,
            "started_at_ms": started_at_ms,
            "account_facts_snapshot": dict(account_facts),
            "market_snapshot": dict(market_snapshot),
            "runtime_safety_snapshot": dict(safety_snapshot),
            "safety": self._no_execution_safety(),
        }

        blocker = await self._pre_iteration_blocker(account_facts, safety_snapshot)
        if blocker is not None:
            evidence = RunnerIterationEvidence(
                **base_evidence,
                completed_at_ms=self._now_ms(),
                status="skipped",
                skipped_reason=blocker,
            )
            await self._record_iteration(evidence)
            return evidence

        signal_preflight = await self._operation_service.preflight(
            operation_type="evaluate_signal_from_admission_strategy",
            requested_by=config.requested_by,
            input_params={
                **config.target_params(),
                "symbol": selected_symbol,
                "signal_snapshot": {
                    "runner": "brc_live_read_only_detection_runner",
                    "iteration_id": iteration_id,
                    "symbol": selected_symbol,
                    "market_snapshot": dict(market_snapshot),
                    "account_facts_snapshot": dict(account_facts),
                    "timestamp_ms": started_at_ms,
                },
                "signal_evaluation_input": {
                    "runner": "brc_live_read_only_detection_runner",
                    "mode": "live_read_only_detection",
                    "symbol": selected_symbol,
                    "market_snapshot": dict(market_snapshot),
                    "account_facts_snapshot": dict(account_facts),
                    "runtime_safety_snapshot": dict(safety_snapshot),
                    "timestamp_ms": started_at_ms,
                },
            },
            source={"kind": "local_runner", "ref": config.source_ref},
        )
        if getattr(signal_preflight, "decision", None) not in {"allow", "warn"}:
            evidence = RunnerIterationEvidence(
                **base_evidence,
                completed_at_ms=self._now_ms(),
                status="skipped",
                skipped_reason=f"signal preflight {getattr(signal_preflight, 'decision', 'unknown')}",
                signal_preflight=_model_summary(signal_preflight),
            )
            await self._record_iteration(evidence)
            return evidence

        signal_result = await self._operation_service.confirm(
            operation_id=signal_preflight.operation_id,
            preflight_id=signal_preflight.preflight_id,
            confirmation_phrase="CONFIRM_EVALUATE_SIGNAL_NO_INTENT",
            idempotency_key=signal_preflight.idempotency_key,
            confirmed_by=config.requested_by,
        )

        intent_preflight = await self._operation_service.preflight(
            operation_type="record_trial_trade_intent_from_signal_evaluation",
            requested_by=config.requested_by,
            input_params={
                **config.target_params(),
                "intended_action": config.intended_action,
                "symbol": selected_symbol,
                "side": config.side,
                "signal_snapshot": {
                    "runner": "brc_live_read_only_detection_runner",
                    "iteration_id": iteration_id,
                    "symbol": selected_symbol,
                    "market_snapshot": dict(market_snapshot),
                    "account_facts_snapshot": dict(account_facts),
                    "timestamp_ms": self._now_ms(),
                },
                "market_snapshot": dict(market_snapshot),
            },
            source={"kind": "local_runner", "ref": config.source_ref},
        )
        permission_resolution = dict(
            getattr(intent_preflight, "after", {}).get("execution_permission_resolution") or {}
        )
        if getattr(intent_preflight, "decision", None) not in {"allow", "warn"}:
            evidence = RunnerIterationEvidence(
                **base_evidence,
                completed_at_ms=self._now_ms(),
                status="intent_skipped",
                skipped_reason=f"trial trade intent preflight {getattr(intent_preflight, 'decision', 'unknown')}",
                signal_preflight=_model_summary(signal_preflight),
                signal_result=_model_summary(signal_result),
                trial_trade_intent_preflight=_model_summary(intent_preflight),
                execution_permission_resolution=permission_resolution,
            )
            await self._record_iteration(evidence)
            return evidence

        intent_result = await self._operation_service.confirm(
            operation_id=intent_preflight.operation_id,
            preflight_id=intent_preflight.preflight_id,
            confirmation_phrase="CONFIRM_RECORD_TRIAL_TRADE_INTENT",
            idempotency_key=intent_preflight.idempotency_key,
            confirmed_by=config.requested_by,
        )
        result_summary = dict(getattr(intent_result, "result_summary", {}) or {})
        evidence = RunnerIterationEvidence(
            **base_evidence,
            completed_at_ms=self._now_ms(),
            status=str(getattr(intent_result, "status", "unknown")),
            signal_preflight=_model_summary(signal_preflight),
            signal_result=_model_summary(signal_result),
            trial_trade_intent_preflight=_model_summary(intent_preflight),
            trial_trade_intent_result=_model_summary(intent_result),
            execution_permission_resolution=permission_resolution,
            not_executed_reason=result_summary.get("not_executed_reason"),
        )
        self._assert_no_execution_artifacts(evidence)
        await self._record_iteration(evidence)
        return evidence

    @staticmethod
    def _validate_runner_config(config: LiveReadOnlyRunnerConfig) -> None:
        if config.trading_env.strip().lower() != "live":
            raise LiveReadOnlyRunnerError("live read-only detection runner requires TRADING_ENV=live")
        if config.brc_execution_permission_max != ExecutionPermission.INTENT_RECORDING:
            raise LiveReadOnlyRunnerError(
                "live read-only detection runner requires BRC_EXECUTION_PERMISSION_MAX=intent_recording"
            )
        if not (config.campaign_id or config.binding_id):
            raise LiveReadOnlyRunnerError("campaign_id or binding_id is required")

    async def _pre_iteration_blocker(
        self,
        account_facts: dict[str, Any],
        runtime_safety: dict[str, Any],
    ) -> Optional[str]:
        if not await self._audit_writable():
            return "audit not writable"
        safety_blocker = _runtime_safety_blocker(runtime_safety)
        if safety_blocker is not None:
            return safety_blocker
        return _account_facts_blocker(account_facts)

    async def _runtime_safety_snapshot(self) -> dict[str, Any]:
        if self._runtime_safety_reader is None:
            return {}
        return dict(await self._runtime_safety_reader())

    async def _record_iteration(self, evidence: RunnerIterationEvidence) -> None:
        self._assert_no_execution_artifacts(evidence)
        if self._iteration_recorder is not None:
            await self._iteration_recorder(evidence)

    @staticmethod
    def _assert_no_execution_artifacts(evidence: RunnerIterationEvidence) -> None:
        summaries = [
            evidence.signal_result,
            evidence.trial_trade_intent_result,
            evidence.safety,
        ]
        for summary in summaries:
            nested = dict(summary.get("result_summary") or {}) if isinstance(summary.get("result_summary"), dict) else {}
            merged = {**nested, **summary}
            if merged.get("execution_intent_created") is True:
                raise LiveReadOnlyRunnerError("runner output attempted to create execution intent")
            if merged.get("order_created") is True or merged.get("orders_placed") is True:
                raise LiveReadOnlyRunnerError("runner output attempted to create order")
            if merged.get("auto_execution_enabled") is True:
                raise LiveReadOnlyRunnerError("runner output attempted to enable auto execution")

    @staticmethod
    def _no_execution_safety() -> dict[str, Any]:
        return {
            "execution_intent_created": False,
            "order_created": False,
            "orders_placed": False,
            "auto_execution_enabled": False,
            "auto_within_budget_enabled": False,
            "cancel_executed": False,
            "close_executed": False,
            "flatten_executed": False,
            "withdrawal_executed": False,
            "transfer_executed": False,
            "llm_authorization_source": False,
        }


def _runtime_safety_blocker(snapshot: dict[str, Any]) -> Optional[str]:
    if snapshot.get("hard_lock_active") is True:
        return "hard lock active"
    if snapshot.get("emergency_stop_active") is True:
        return "emergency stop active"
    if snapshot.get("global_kill_switch_active") is True:
        return "global kill switch active"
    if snapshot.get("paused") is True or snapshot.get("pause_active") is True:
        return "runtime pause active"
    state = str(snapshot.get("runtime_state") or snapshot.get("current_runtime_state") or "").lower()
    if state in {"hard_locked", "hard_lock", "emergency_stopped", "emergency_stop", "stopped", "paused"}:
        return f"runtime state blocks read-only detection: {state}"
    return None


def _account_facts_blocker(account_facts: dict[str, Any]) -> Optional[str]:
    if not account_facts:
        return "account facts unavailable"
    source = str(account_facts.get("source") or "").lower()
    truth_level = str(account_facts.get("truth_level") or "").lower()
    if source in {"", "unavailable"} or truth_level in {"", "unavailable"}:
        return "account facts unavailable"
    if source not in {"exchange_live", "mixed"}:
        return "live read-only detection requires exchange_live or mixed account facts"
    freshness = str(
        account_facts.get("freshness")
        or account_facts.get("freshness_status")
        or account_facts.get("staleness_status")
        or ""
    ).lower()
    if freshness in {"stale", "expired", "too_old"} or account_facts.get("stale") is True:
        return "account facts freshness unacceptable"
    reconciliation = account_facts.get("reconciliation_status")
    reconciliation_status = (
        str(reconciliation.get("status") or "").lower()
        if isinstance(reconciliation, dict)
        else str(account_facts.get("reconciliation_status_value") or "").lower()
    )
    if reconciliation_status == "mismatch":
        return "account reconciliation mismatch"
    unknown_counts = account_facts.get("unknown_unmanaged_counts")
    if isinstance(unknown_counts, dict) and (
        int(unknown_counts.get("orders") or 0) > 0
        or int(unknown_counts.get("positions") or 0) > 0
    ):
        return "unknown unmanaged exposure detected"
    return None


def _model_summary(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return dict(value)
    return dict(getattr(value, "__dict__", {}) or {})


def _account_snapshot_summary(snapshot: Any) -> dict[str, Any]:
    if snapshot is None:
        return {}
    if hasattr(snapshot, "model_dump"):
        return snapshot.model_dump(mode="json")
    result: dict[str, Any] = {}
    for key in ("total_balance", "available_balance", "unrealized_pnl", "timestamp"):
        value = getattr(snapshot, key, None)
        if isinstance(value, Decimal):
            result[key] = str(value)
        elif value is not None:
            result[key] = value
    positions = getattr(snapshot, "positions", None)
    if positions is not None:
        result["positions"] = [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(getattr(item, "__dict__", {}) or {})
            for item in positions
        ]
    return result
