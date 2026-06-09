"""Trusted read-only runtime fact overlay for strategy signal inputs.

This service prepares StrategyFamilySignalInput for B0 semantics by replacing
caller-provided account/position allow facts with facts read from injected
trusted local/read-only sources. It never creates candidates, execution
intents, orders, exchange payloads, or runtime mutations.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol

from pydantic import BaseModel, Field

from src.application.trial_readiness_account_facts import (
    AccountFactsFreshnessStatus,
    AccountFactsReconciliationStatus,
    TrialReadinessAccountFacts,
    TrialReadinessAccountFactsSource,
)
from src.domain.strategy_family_signal import (
    AccountFactsSnapshot,
    SignalDataQuality,
    SignalDataQualityStatus,
    SignalSide,
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance


class StrategyRuntimeFactActivePositionSource(Protocol):
    async def list_active(self, *, symbol: str | None = None, limit: int = 100) -> list[Any]:
        ...


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
        position_limit: int = 100,
        require_trusted_position_source: bool = True,
        require_trusted_account_source: bool = True,
    ) -> None:
        self._active_position_source = active_position_source
        self._account_facts_source = account_facts_source
        self._position_limit = position_limit
        self._require_trusted_position_source = require_trusted_position_source
        self._require_trusted_account_source = require_trusted_account_source

    async def apply(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        output: StrategyFamilySignalOutput | None = None,
        runtime: StrategyRuntimeInstance | None = None,
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
        }
        updated_runtime_safety = {
            **signal_input.runtime_safety_snapshot,
            "trusted_runtime_fact_overlay": metadata,
        }
        return StrategyRuntimeFactOverlayResult(
            signal_input=signal_input.model_copy(
                update={
                    "account_facts_snapshot": account_snapshot,
                    "position_open_order_summary": position_summary,
                    "reconciliation_status": account_snapshot.reconciliation_status,
                    "runtime_safety_snapshot": updated_runtime_safety,
                    "input_quality": updated_quality,
                    "source": "trusted_runtime_fact_overlay",
                    "freshness": _overlay_freshness(signal_input, account_snapshot),
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


def _overlay_freshness(
    signal_input: StrategyFamilySignalInput,
    account_snapshot: AccountFactsSnapshot,
) -> str:
    if account_snapshot.freshness in {"stale", "missing"}:
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
