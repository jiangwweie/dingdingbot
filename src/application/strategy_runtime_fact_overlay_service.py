"""Trusted read-only runtime fact overlay for strategy signal inputs.

This service prepares StrategyFamilySignalInput for B0 semantics by replacing
caller-provided account/position allow facts with facts read from injected
trusted local/read-only sources. It never creates candidates, execution
intents, orders, exchange payloads, or runtime mutations.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.application.trial_readiness_account_facts import (
    AccountFactsFreshnessStatus,
    AccountFactsReconciliationStatus,
    TrialReadinessAccountFacts,
    TrialReadinessAccountFactsSource,
)
from src.domain.strategy_family_signal import (
    AccountFactsSnapshot,
    MarketSnapshot,
    SignalDataQuality,
    SignalDataQualityStatus,
    SignalSide,
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
    reject_forbidden_execution_fields,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance


class StrategyRuntimeFactActivePositionSource(Protocol):
    async def list_active(self, *, symbol: str | None = None, limit: int = 100) -> list[Any]:
        ...


class StrategyRuntimeMarketFactSource(Protocol):
    async def read_strategy_market_facts(
        self,
        *,
        symbol: str,
        generated_at_ms: int,
    ) -> "StrategyRuntimeMarketFacts":
        ...


class StrategyRuntimeMarketFacts(BaseModel):
    """Read-only derivative/market facts used by B0 strategy semantics."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=128)
    timestamp_ms: int = Field(ge=0)
    freshness: str = Field(default="fresh", max_length=64)
    funding_rate: Decimal | None = None
    next_funding_time_ms: int | None = Field(default=None, ge=0)
    open_interest: Decimal | None = None
    open_interest_notional: Decimal | None = None
    open_interest_change_pct: Decimal | None = None
    crowding_proxy: dict[str, Any] | None = None
    missing_fields: list[str] = Field(default_factory=list)
    stale_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    read_only_guarantee: bool = True
    external_call_type: str = Field(default="read_only_market_facts", max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)
    not_order: Literal[True] = True
    not_execution_intent: Literal[True] = True
    not_execution_authority: Literal[True] = True

    @model_validator(mode="after")
    def _reject_execution_fields(self) -> "StrategyRuntimeMarketFacts":
        reject_forbidden_execution_fields(self.model_dump(mode="python"), root="strategy_runtime_market_facts")
        return self


class StrategyRuntimeFactOverlayResult(BaseModel):
    signal_input: StrategyFamilySignalInput
    applied: bool = True
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyRuntimeFactOverlayService:
    """Overlay trusted account/position facts onto a strategy signal input."""

    def __init__(
        self,
        *,
        active_position_source: StrategyRuntimeFactActivePositionSource | None = None,
        account_facts_source: TrialReadinessAccountFactsSource | None = None,
        market_fact_source: StrategyRuntimeMarketFactSource | None = None,
        position_limit: int = 100,
        require_trusted_position_source: bool = True,
        require_trusted_account_source: bool = True,
        require_trusted_market_fact_source: bool = False,
        market_fact_keys: tuple[str, ...] = (
            "funding_rate",
            "open_interest",
            "crowding_proxy",
        ),
    ) -> None:
        self._active_position_source = active_position_source
        self._account_facts_source = account_facts_source
        self._market_fact_source = market_fact_source
        self._position_limit = position_limit
        self._require_trusted_position_source = require_trusted_position_source
        self._require_trusted_account_source = require_trusted_account_source
        self._require_trusted_market_fact_source = require_trusted_market_fact_source
        self._market_fact_keys = tuple(dict.fromkeys(market_fact_keys))

    async def apply(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        output: StrategyFamilySignalOutput | None = None,
        runtime: StrategyRuntimeInstance | None = None,
        required_market_fact_keys: tuple[str, ...] | None = None,
        require_trusted_market_fact_source: bool | None = None,
    ) -> StrategyRuntimeFactOverlayResult:
        blockers: list[str] = []
        warnings: list[str] = []
        missing_fields: set[str] = set(signal_input.input_quality.missing_fields)
        stale_fields: set[str] = set(signal_input.input_quality.stale_fields)
        notes: list[str] = list(signal_input.input_quality.notes)

        position_summary, position_metadata = await self._position_summary(
            signal_input,
            blockers=blockers,
            missing_fields=missing_fields,
        )
        account_snapshot, account_metadata = await self._account_snapshot(
            signal_input,
            output=output,
            runtime=runtime,
            blockers=blockers,
            warnings=warnings,
            missing_fields=missing_fields,
            stale_fields=stale_fields,
        )
        market_snapshot, market_metadata = await self._market_snapshot(
            signal_input,
            blockers=blockers,
            warnings=warnings,
            missing_fields=missing_fields,
            stale_fields=stale_fields,
            required_market_fact_keys=required_market_fact_keys,
            require_trusted_market_fact_source=require_trusted_market_fact_source,
        )
        notes.append("trusted_runtime_fact_overlay_applied")

        updated_quality = SignalDataQuality(
            status=(
                SignalDataQualityStatus.DEGRADED
                if missing_fields or stale_fields or blockers or warnings
                else signal_input.input_quality.status
            ),
            missing_fields=sorted(missing_fields),
            stale_fields=sorted(stale_fields),
            warnings=sorted({*signal_input.input_quality.warnings, *warnings}),
            source_latency_ms=signal_input.input_quality.source_latency_ms,
            notes=notes,
        )
        metadata = {
            "source": "trusted_runtime_fact_overlay",
            "non_executing": True,
            "does_not_call_order_lifecycle": True,
            "does_not_call_exchange_write": True,
            "position_fact_overlay": position_metadata,
            "account_fact_overlay": account_metadata,
            "market_fact_overlay": market_metadata,
        }
        updated_runtime_safety = {
            **signal_input.runtime_safety_snapshot,
            "trusted_runtime_fact_overlay": metadata,
        }
        return StrategyRuntimeFactOverlayResult(
            signal_input=signal_input.model_copy(
                update={
                    "account_facts_snapshot": account_snapshot,
                    "market_snapshot": market_snapshot,
                    "position_open_order_summary": position_summary,
                    "reconciliation_status": account_snapshot.reconciliation_status,
                    "runtime_safety_snapshot": updated_runtime_safety,
                    "input_quality": updated_quality,
                    "source": "trusted_runtime_fact_overlay",
                    "freshness": _overlay_freshness(
                        signal_input,
                        account_snapshot,
                        missing_fields=missing_fields,
                        stale_fields=stale_fields,
                    ),
                },
                deep=True,
            ),
            blockers=blockers,
            warnings=warnings,
            metadata=metadata,
        )

    async def _position_summary(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        blockers: list[str],
        missing_fields: set[str],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        source = self._active_position_source
        if source is None or not hasattr(source, "list_active"):
            if self._require_trusted_position_source:
                blockers.append("trusted_position_projection_source_unavailable")
                missing_fields.add("position_projection")
            return {}, {
                "status": "missing",
                "reason": "trusted_position_projection_source_unavailable",
            }
        try:
            positions = list(
                await source.list_active(
                    symbol=signal_input.symbol,
                    limit=self._position_limit,
                )
            )
        except Exception as exc:
            blockers.append("trusted_position_projection_read_failed")
            missing_fields.add("position_projection")
            return {}, {
                "status": "read_failed",
                "error_type": type(exc).__name__,
            }

        summary = {
            "source": "trusted_local_position_projection",
            "symbol": signal_input.symbol,
            "active_positions_count": len(positions),
            "position_count": len(positions),
            "positions": [_position_snapshot(position) for position in positions],
            "limit": self._position_limit,
            "caller_supplied_active_position_count_used": False,
        }
        return summary, {
            "status": "available",
            "source": "trusted_local_position_projection",
            "active_positions_count": len(positions),
        }

    async def _account_snapshot(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        output: StrategyFamilySignalOutput | None,
        runtime: StrategyRuntimeInstance | None,
        blockers: list[str],
        warnings: list[str],
        missing_fields: set[str],
        stale_fields: set[str],
    ) -> tuple[AccountFactsSnapshot, dict[str, Any]]:
        source = self._account_facts_source
        if source is None or not hasattr(source, "read_trial_readiness_account_facts"):
            if self._require_trusted_account_source:
                blockers.append("trusted_account_facts_source_unavailable")
                missing_fields.add("account_facts")
                return _unavailable_account_snapshot(
                    signal_input,
                    reason="trusted_account_facts_source_unavailable",
                ), {"status": "missing", "reason": "trusted_account_facts_source_unavailable"}
            return signal_input.account_facts_snapshot, {
                "status": "unchanged",
                "reason": "trusted_account_facts_source_not_required",
            }

        side = _side_for_account_read(signal_input, output, runtime)
        candidate_id = output.signal_id if output is not None else signal_input.evaluation_id
        try:
            facts = await source.read_trial_readiness_account_facts(
                candidate_id=candidate_id,
                symbol=signal_input.symbol,
                side=side,
                generated_at_ms=signal_input.timestamp_ms,
            )
        except Exception as exc:
            blockers.append("trusted_account_facts_read_failed")
            missing_fields.add("account_facts")
            return _unavailable_account_snapshot(
                signal_input,
                reason="trusted_account_facts_read_failed",
            ), {"status": "read_failed", "error_type": type(exc).__name__}

        snapshot = _account_snapshot_from_trial_facts(signal_input, facts)
        readiness_blockers = list(facts.readiness_blockers())
        if readiness_blockers:
            blockers.append("trusted_account_facts_not_ready")
            missing_fields.add("account_facts")
            warnings.extend(f"account_fact:{blocker}" for blocker in readiness_blockers)
        if facts.freshness_status == AccountFactsFreshnessStatus.STALE:
            stale_fields.add("account_facts")
        if facts.reconciliation_status == AccountFactsReconciliationStatus.MISMATCH:
            blockers.append("trusted_account_reconciliation_mismatch")
            stale_fields.add("account_facts")

        return snapshot, {
            "status": "available" if facts.is_ready else "not_ready",
            "source_type": facts.source_type.value,
            "source_id": facts.source_id,
            "freshness_status": facts.freshness_status.value,
            "reconciliation_status": facts.reconciliation_status.value,
            "read_only_guarantee": facts.read_only_guarantee,
            "external_call_type": facts.external_call_type,
            "readiness_blockers": readiness_blockers,
        }

    async def _market_snapshot(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        blockers: list[str],
        warnings: list[str],
        missing_fields: set[str],
        stale_fields: set[str],
        required_market_fact_keys: tuple[str, ...] | None,
        require_trusted_market_fact_source: bool | None,
    ) -> tuple[MarketSnapshot, dict[str, Any]]:
        source = self._market_fact_source
        market_fact_keys = tuple(dict.fromkeys(required_market_fact_keys or self._market_fact_keys))
        trusted_source_required = (
            self._require_trusted_market_fact_source
            if require_trusted_market_fact_source is None
            else require_trusted_market_fact_source
        )
        if source is None or not hasattr(source, "read_strategy_market_facts"):
            if trusted_source_required:
                blockers.append("trusted_market_fact_source_unavailable")
                missing_fields.update(market_fact_keys)
                return _market_snapshot_without_trusted_facts(
                    signal_input,
                    missing_keys=market_fact_keys,
                    reason="trusted_market_fact_source_unavailable",
                ), {
                    "status": "missing",
                    "reason": "trusted_market_fact_source_unavailable",
                    "required_keys": list(market_fact_keys),
                    "required_by_strategy_semantics": required_market_fact_keys is not None,
                }
            return signal_input.market_snapshot, {
                "status": "unchanged",
                "reason": "trusted_market_fact_source_not_required",
            }

        try:
            facts = await source.read_strategy_market_facts(
                symbol=signal_input.symbol,
                generated_at_ms=signal_input.timestamp_ms,
            )
        except Exception as exc:
            blockers.append("trusted_market_fact_read_failed")
            missing_fields.update(market_fact_keys)
            return _market_snapshot_without_trusted_facts(
                signal_input,
                missing_keys=market_fact_keys,
                reason="trusted_market_fact_read_failed",
            ), {
                "status": "read_failed",
                "error_type": type(exc).__name__,
                "required_keys": list(market_fact_keys),
                "required_by_strategy_semantics": required_market_fact_keys is not None,
            }

        if not facts.read_only_guarantee:
            blockers.append("trusted_market_fact_source_not_read_only")
            missing_fields.update(market_fact_keys)
            warnings.append("market_fact:source_not_read_only")
            return _market_snapshot_without_trusted_facts(
                signal_input,
                missing_keys=market_fact_keys,
                reason="trusted_market_fact_source_not_read_only",
            ), {
                "status": "not_read_only",
                "source_id": facts.source_id,
                "external_call_type": facts.external_call_type,
                "required_by_strategy_semantics": required_market_fact_keys is not None,
            }

        inferred_missing = _missing_market_fact_keys(facts, market_fact_keys)
        missing_fields.update(inferred_missing)
        missing_fields.update(facts.missing_fields)
        stale_market_fields = set(facts.stale_fields)
        if _freshness_is_stale(facts.freshness):
            stale_market_fields.update(
                key for key in market_fact_keys if key not in inferred_missing
            )
        stale_fields.update(stale_market_fields)
        warnings.extend(f"market_fact:{warning}" for warning in facts.warnings)

        return _market_snapshot_from_strategy_market_facts(
            signal_input,
            facts,
            missing_keys=sorted({*inferred_missing, *facts.missing_fields}),
        ), {
            "status": "available" if not inferred_missing else "partial",
            "source_id": facts.source_id,
            "freshness": facts.freshness,
            "read_only_guarantee": facts.read_only_guarantee,
            "external_call_type": facts.external_call_type,
            "missing_fields": sorted({*inferred_missing, *facts.missing_fields}),
            "stale_fields": sorted(stale_market_fields),
            "warnings": list(facts.warnings),
            "required_keys": list(market_fact_keys),
            "required_by_strategy_semantics": required_market_fact_keys is not None,
        }


def _account_snapshot_from_trial_facts(
    signal_input: StrategyFamilySignalInput,
    facts: TrialReadinessAccountFacts,
) -> AccountFactsSnapshot:
    is_ready = facts.is_ready
    reconciliation_status = {
        "status": facts.reconciliation_status.value,
        "source": facts.source_id,
    }
    limitations = list(facts.notes)
    limitations.extend(f"account readiness blocker: {item}" for item in facts.readiness_blockers())
    return AccountFactsSnapshot(
        source=facts.source_type.value,
        truth_level="read_only_verified" if is_ready else "unavailable",
        timestamp_ms=facts.timestamp_ms or signal_input.timestamp_ms,
        freshness=(
            facts.freshness_status.value
            if is_ready
            else "stale"
            if facts.freshness_status == AccountFactsFreshnessStatus.STALE
            else "missing"
        ),
        account_status="normal" if is_ready else "unavailable",
        available_balance=facts.available_margin,
        position_count=0,
        open_order_count=0,
        unknown_unmanaged_counts={"orders": 0, "positions": 0},
        reconciliation_status=reconciliation_status,
        read_only_provider=facts.source_id,
        limitations=limitations,
    )


def _unavailable_account_snapshot(
    signal_input: StrategyFamilySignalInput,
    *,
    reason: str,
) -> AccountFactsSnapshot:
    return AccountFactsSnapshot(
        source="unavailable",
        truth_level="unavailable",
        timestamp_ms=signal_input.timestamp_ms,
        freshness="missing",
        account_status="unavailable",
        reconciliation_status={"status": "not_available", "reason": reason},
        read_only_provider="trusted_runtime_fact_overlay",
        limitations=[reason],
    )


def _market_snapshot_from_strategy_market_facts(
    signal_input: StrategyFamilySignalInput,
    facts: StrategyRuntimeMarketFacts,
    *,
    missing_keys: list[str],
) -> MarketSnapshot:
    context = _market_context_without_overlay_facts(signal_input.market_snapshot.candle_context)
    market_facts = dict(context.get("market_facts") or {})
    if facts.open_interest is not None:
        market_facts["open_interest"] = {
            "open_interest": str(facts.open_interest),
            "open_interest_notional": (
                str(facts.open_interest_notional)
                if facts.open_interest_notional is not None
                else None
            ),
            "open_interest_change_pct": (
                str(facts.open_interest_change_pct)
                if facts.open_interest_change_pct is not None
                else None
            ),
            "source_id": facts.source_id,
        }
    if facts.crowding_proxy is not None:
        market_facts["crowding_proxy"] = {
            **_jsonable(facts.crowding_proxy),
            "source_id": facts.source_id,
        }
    if market_facts:
        context["market_facts"] = market_facts
    context["trusted_market_fact_overlay"] = {
        "source_id": facts.source_id,
        "timestamp_ms": facts.timestamp_ms,
        "freshness": facts.freshness,
        "read_only_guarantee": facts.read_only_guarantee,
        "external_call_type": facts.external_call_type,
        "missing_fields": list(missing_keys),
        "stale_fields": list(facts.stale_fields),
        "non_executing": True,
        "does_not_create_orders": True,
        "does_not_call_exchange_write": True,
    }
    return signal_input.market_snapshot.model_copy(
        update={
            "timestamp_ms": facts.timestamp_ms,
            "source": "trusted_runtime_market_fact_overlay",
            "freshness": facts.freshness,
            "funding_rate": facts.funding_rate,
            "next_funding_time_ms": facts.next_funding_time_ms,
            "candle_context": context,
            "missing_fields": sorted(
                {
                    *signal_input.market_snapshot.missing_fields,
                    *missing_keys,
                }
            ),
        },
        deep=True,
    )


def _market_snapshot_without_trusted_facts(
    signal_input: StrategyFamilySignalInput,
    *,
    missing_keys: tuple[str, ...],
    reason: str,
) -> MarketSnapshot:
    context = _market_context_without_overlay_facts(signal_input.market_snapshot.candle_context)
    context["trusted_market_fact_overlay"] = {
        "status": "missing",
        "reason": reason,
        "missing_fields": list(missing_keys),
        "non_executing": True,
        "does_not_create_orders": True,
        "does_not_call_exchange_write": True,
    }
    return signal_input.market_snapshot.model_copy(
        update={
            "source": "trusted_runtime_market_fact_overlay",
            "freshness": "missing",
            "funding_rate": None,
            "next_funding_time_ms": None,
            "candle_context": context,
            "missing_fields": sorted(
                {
                    *signal_input.market_snapshot.missing_fields,
                    *missing_keys,
                }
            ),
        },
        deep=True,
    )


def _market_context_without_overlay_facts(raw_context: dict[str, Any]) -> dict[str, Any]:
    context = dict(raw_context or {})
    market_facts = dict(context.get("market_facts") or {})
    for key in ("open_interest", "crowding_proxy"):
        market_facts.pop(key, None)
    if market_facts:
        context["market_facts"] = market_facts
    else:
        context.pop("market_facts", None)
    for key in ("open_interest", "crowding_proxy", "trusted_market_fact_overlay"):
        context.pop(key, None)
    return context


def _missing_market_fact_keys(
    facts: StrategyRuntimeMarketFacts,
    required_keys: tuple[str, ...],
) -> set[str]:
    missing: set[str] = set()
    for key in required_keys:
        if key == "funding_rate" and facts.funding_rate is None:
            missing.add(key)
        elif key == "open_interest" and facts.open_interest is None:
            missing.add(key)
        elif key == "crowding_proxy" and facts.crowding_proxy is None:
            missing.add(key)
    return missing


def _freshness_is_stale(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip().lower()
    return any(token in normalized for token in ("stale", "expired", "outdated"))


def _overlay_freshness(
    signal_input: StrategyFamilySignalInput,
    account_snapshot: AccountFactsSnapshot,
    *,
    missing_fields: set[str],
    stale_fields: set[str],
) -> str:
    if account_snapshot.freshness in {"stale", "missing"} or missing_fields or stale_fields:
        return "degraded"
    return signal_input.freshness


def _side_for_account_read(
    signal_input: StrategyFamilySignalInput,
    output: StrategyFamilySignalOutput | None,
    runtime: StrategyRuntimeInstance | None,
) -> str:
    if output is not None and output.side != SignalSide.NONE:
        return output.side.value
    if runtime is not None:
        return runtime.side
    side = signal_input.trial_constraints_snapshot.get("side")
    return str(side or "none")


def _position_snapshot(position: Any) -> dict[str, Any]:
    if isinstance(position, BaseModel):
        return _jsonable(position.model_dump(mode="json"))
    fields = {
        "id": getattr(position, "id", None),
        "signal_id": getattr(position, "signal_id", None),
        "symbol": getattr(position, "symbol", None),
        "direction": getattr(position, "direction", None),
        "entry_price": getattr(position, "entry_price", None),
        "current_qty": getattr(position, "current_qty", None),
        "watermark_price": getattr(position, "watermark_price", None),
        "realized_pnl": getattr(position, "realized_pnl", None),
        "is_closed": getattr(position, "is_closed", None),
        "opened_at": getattr(position, "opened_at", None),
    }
    return {key: _jsonable(value) for key, value in fields.items() if value is not None}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _jsonable(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        return getattr(value, "value")
    return value
