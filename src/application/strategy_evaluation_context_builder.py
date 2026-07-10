"""Build B0 StrategyEvaluationContext from read-only strategy facts.

The builder translates existing StrategyFamilySignalInput/Output and optional
StrategyRuntimeInstance snapshots into strategy-semantic facts. It is
non-executing: it does not create SignalEvaluation, OrderCandidate,
ExecutionIntent, orders, or exchange payloads.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from src.domain.strategy_family_signal import (
    SignalSide,
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance
from src.domain.rmr_regime_classifier import (
    RmrRegimeAssessment,
    classify_rmr_regime,
)
from src.domain.strategy_semantics import (
    FactAvailabilityStatus,
    MarketState,
    StrategyEvaluationContext,
    StrategyFactSnapshot,
)


KNOWN_STRATEGY_FACT_KEYS = (
    "ohlcv_15m",
    "ohlcv_1h",
    "ohlcv_4h",
    "price_action_structure",
    "account_facts",
    "runtime_boundary",
    "position_projection",
    "short_squeeze_risk",
    "funding_rate",
    "range_structure",
    "volatility_state",
    "open_interest",
    "crowding_proxy",
)


class StrategyEvaluationContextBuilderError(ValueError):
    """Raised when signal input/output cannot form a coherent context."""


class StrategyEvaluationContextBuilder:
    """Build StrategyEvaluationContext without inventing unavailable facts."""

    def build(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        output: StrategyFamilySignalOutput | None = None,
        runtime: StrategyRuntimeInstance | None = None,
        context_id: str | None = None,
    ) -> StrategyEvaluationContext:
        _assert_signal_shapes_match(signal_input, output, runtime)
        evaluated_at_ms = output.timestamp_ms if output is not None else signal_input.timestamp_ms
        side = _context_side(signal_input, output, runtime)
        facts = {
            fact_key: fact
            for fact_key, fact in (
                self._ohlcv_fact(signal_input, "15m", "ohlcv_15m", evaluated_at_ms),
                self._ohlcv_fact(signal_input, "1h", "ohlcv_1h", evaluated_at_ms),
                self._ohlcv_fact(signal_input, "4h", "ohlcv_4h", evaluated_at_ms),
                self._price_action_fact(signal_input, output, evaluated_at_ms),
                self._account_fact(signal_input, evaluated_at_ms),
                self._runtime_boundary_fact(signal_input, runtime, evaluated_at_ms),
                self._position_projection_fact(signal_input, evaluated_at_ms),
                self._funding_rate_fact(signal_input, evaluated_at_ms),
                self._explicit_output_or_market_fact(
                    signal_input,
                    output,
                    "short_squeeze_risk",
                    evaluated_at_ms,
                ),
                self._explicit_output_or_market_fact(
                    signal_input,
                    output,
                    "range_structure",
                    evaluated_at_ms,
                ),
                self._volatility_state_fact(signal_input, output, evaluated_at_ms),
                self._explicit_output_or_market_fact(
                    signal_input,
                    output,
                    "open_interest",
                    evaluated_at_ms,
                ),
                self._explicit_output_or_market_fact(
                    signal_input,
                    output,
                    "crowding_proxy",
                    evaluated_at_ms,
                ),
            )
        }
        if signal_input.primary_timeframe != "15m":
            facts.pop("ohlcv_15m", None)
        return StrategyEvaluationContext(
            context_id=context_id or _context_id(signal_input.evaluation_id),
            strategy_family_id=(
                output.strategy_family_id if output is not None else signal_input.strategy_family_id
            ),
            strategy_family_version_id=(
                output.strategy_family_version_id
                if output is not None
                else signal_input.strategy_family_version_id
            ),
            symbol=signal_input.symbol,
            side=side,
            evaluated_at_ms=evaluated_at_ms,
            facts=facts,
            market_state=_market_state(signal_input, output),
            metadata={
                "source": "strategy_evaluation_context_builder",
                "signal_input_evaluation_id": signal_input.evaluation_id,
                "strategy_signal_id": output.signal_id if output is not None else None,
                "runtime_instance_id": (
                    runtime.runtime_instance_id if runtime is not None else None
                ),
                "missing_facts": sorted(
                    key
                    for key, fact in facts.items()
                    if fact.status == FactAvailabilityStatus.MISSING
                ),
                "stale_facts": sorted(
                    key
                    for key, fact in facts.items()
                    if fact.status == FactAvailabilityStatus.STALE
                ),
            },
        )

    def _ohlcv_fact(
        self,
        signal_input: StrategyFamilySignalInput,
        timeframe: str,
        fact_key: str,
        evaluated_at_ms: int,
    ) -> tuple[str, StrategyFactSnapshot]:
        window = _candle_window(signal_input, timeframe)
        if window:
            status = _status_for_fact(
                signal_input,
                fact_key,
                available=True,
                explicit_freshness=signal_input.market_snapshot.freshness,
            )
            return fact_key, _fact_snapshot(
                fact_key,
                source="signal_input.market_snapshot",
                observed_at_ms=signal_input.market_snapshot.timestamp_ms,
                evaluated_at_ms=evaluated_at_ms,
                status=status,
                value_snapshot={
                    "timeframe": timeframe,
                    "candle_count": len(window),
                    "closed_bar": signal_input.market_snapshot.candle_context.get(
                        "closed_bar"
                    ),
                    "latest_candle": _jsonable(window[-1]),
                    "market_snapshot_ref": (
                        f"market_snapshot:{signal_input.evaluation_id}"
                    ),
                },
            )
        return fact_key, _missing_fact(
            fact_key,
            evaluated_at_ms,
            reason=f"missing_{timeframe}_candle_window",
        )

    def _price_action_fact(
        self,
        signal_input: StrategyFamilySignalInput,
        output: StrategyFamilySignalOutput | None,
        evaluated_at_ms: int,
    ) -> tuple[str, StrategyFactSnapshot]:
        fact_key = "price_action_structure"
        evidence = _explicit_fact_value(output, fact_key)
        if evidence is None and output is not None and (
            output.reason_codes or output.signal_snapshot or output.evidence_payload
        ):
            evidence = {
                "reason_codes": list(output.reason_codes),
                "signal_snapshot": _jsonable(output.signal_snapshot),
                "evidence_payload": _jsonable(output.evidence_payload),
                "expected_risk_shape": str(output.expected_risk_shape),
            }
        if evidence is not None:
            status = _status_for_fact(
                signal_input,
                fact_key,
                available=True,
                output=output,
            )
            return fact_key, _fact_snapshot(
                fact_key,
                source="strategy_signal_output",
                observed_at_ms=output.timestamp_ms if output is not None else evaluated_at_ms,
                evaluated_at_ms=evaluated_at_ms,
                status=status,
                value_snapshot={"evidence": _jsonable(evidence)},
            )
        return fact_key, _missing_fact(
            fact_key,
            evaluated_at_ms,
            reason="missing_strategy_output_price_action_evidence",
        )

    def _account_fact(
        self,
        signal_input: StrategyFamilySignalInput,
        evaluated_at_ms: int,
    ) -> tuple[str, StrategyFactSnapshot]:
        fact_key = "account_facts"
        account = signal_input.account_facts_snapshot
        available = _account_snapshot_is_usable(signal_input)
        if not available:
            return fact_key, _missing_fact(
                fact_key,
                evaluated_at_ms,
                reason="account_facts_unavailable_or_not_checked",
                value_snapshot={"account_status": account.account_status},
            )
        status = _status_for_fact(
            signal_input,
            fact_key,
            available=True,
            explicit_freshness=account.freshness,
        )
        return fact_key, _fact_snapshot(
            fact_key,
            source="signal_input.account_facts_snapshot",
            observed_at_ms=account.timestamp_ms,
            evaluated_at_ms=evaluated_at_ms,
            status=status,
            value_snapshot=account.model_dump(mode="json"),
        )

    def _runtime_boundary_fact(
        self,
        signal_input: StrategyFamilySignalInput,
        runtime: StrategyRuntimeInstance | None,
        evaluated_at_ms: int,
    ) -> tuple[str, StrategyFactSnapshot]:
        fact_key = "runtime_boundary"
        if runtime is not None:
            status = _status_for_fact(signal_input, fact_key, available=True)
            return fact_key, _fact_snapshot(
                fact_key,
                source="strategy_runtime_instance",
                observed_at_ms=runtime.updated_at_ms,
                evaluated_at_ms=evaluated_at_ms,
                status=status,
                value_snapshot={
                    "runtime_instance_id": runtime.runtime_instance_id,
                    "status": runtime.status.value,
                    "boundary": runtime.boundary.model_dump(mode="json"),
                    "execution_enabled": runtime.execution_enabled,
                    "shadow_mode": runtime.shadow_mode,
                },
            )
        constraints = dict(signal_input.trial_constraints_snapshot or {})
        runtime_snapshot = dict(signal_input.runtime_safety_snapshot or {})
        has_boundary = any(
            key in constraints
            for key in (
                "max_attempts",
                "max_loss_budget",
                "max_notional_per_attempt",
                "total_budget",
                "max_active_positions",
                "max_leverage",
            )
        )
        if has_boundary:
            status = _status_for_fact(signal_input, fact_key, available=True)
            return fact_key, _fact_snapshot(
                fact_key,
                source="signal_input.trial_constraints_snapshot",
                observed_at_ms=signal_input.timestamp_ms,
                evaluated_at_ms=evaluated_at_ms,
                status=status,
                value_snapshot={
                    "trial_constraints_snapshot": _jsonable(constraints),
                    "runtime_safety_snapshot": _jsonable(runtime_snapshot),
                },
            )
        return fact_key, _missing_fact(
            fact_key,
            evaluated_at_ms,
            reason="runtime_boundary_missing",
            value_snapshot={"runtime_safety_snapshot": _jsonable(runtime_snapshot)},
        )

    def _position_projection_fact(
        self,
        signal_input: StrategyFamilySignalInput,
        evaluated_at_ms: int,
    ) -> tuple[str, StrategyFactSnapshot]:
        fact_key = "position_projection"
        summary = dict(signal_input.position_open_order_summary or {})
        has_projection = any(
            key in summary
            for key in (
                "position_count",
                "active_positions_count",
                "open_order_count",
                "positions",
                "open_orders",
            )
        )
        if not has_projection and _account_snapshot_is_usable(signal_input):
            summary = {
                "position_count": signal_input.account_facts_snapshot.position_count,
                "open_order_count": signal_input.account_facts_snapshot.open_order_count,
                "positions": _jsonable(signal_input.account_facts_snapshot.positions),
                "open_orders": _jsonable(signal_input.account_facts_snapshot.open_orders),
                "source": "account_facts_snapshot",
            }
            has_projection = True
        if has_projection:
            status = _status_for_fact(signal_input, fact_key, available=True)
            return fact_key, _fact_snapshot(
                fact_key,
                source="signal_input.position_open_order_summary",
                observed_at_ms=signal_input.timestamp_ms,
                evaluated_at_ms=evaluated_at_ms,
                status=status,
                value_snapshot=_jsonable(summary),
            )
        return fact_key, _missing_fact(
            fact_key,
            evaluated_at_ms,
            reason="position_projection_missing",
        )

    def _funding_rate_fact(
        self,
        signal_input: StrategyFamilySignalInput,
        evaluated_at_ms: int,
    ) -> tuple[str, StrategyFactSnapshot]:
        fact_key = "funding_rate"
        funding_rate = signal_input.market_snapshot.funding_rate
        if funding_rate is None:
            return fact_key, _missing_fact(
                fact_key,
                evaluated_at_ms,
                reason="funding_rate_missing",
            )
        status = _status_for_fact(
            signal_input,
            fact_key,
            available=True,
            explicit_freshness=signal_input.market_snapshot.freshness,
        )
        return fact_key, _fact_snapshot(
            fact_key,
            source="signal_input.market_snapshot",
            observed_at_ms=signal_input.market_snapshot.timestamp_ms,
            evaluated_at_ms=evaluated_at_ms,
            status=status,
            value_snapshot={
                "funding_rate": str(funding_rate),
                "next_funding_time_ms": signal_input.market_snapshot.next_funding_time_ms,
            },
        )

    def _explicit_output_or_market_fact(
        self,
        signal_input: StrategyFamilySignalInput,
        output: StrategyFamilySignalOutput | None,
        fact_key: str,
        evaluated_at_ms: int,
    ) -> tuple[str, StrategyFactSnapshot]:
        value = _explicit_fact_value(output, fact_key)
        source = "strategy_signal_output"
        observed_at_ms = output.timestamp_ms if output is not None else evaluated_at_ms
        if value is None:
            value = _explicit_market_context_value(signal_input, fact_key)
            source = "signal_input.market_snapshot"
            observed_at_ms = signal_input.market_snapshot.timestamp_ms
        if value is None and fact_key == "range_structure":
            assessment = _rmr_assessment(signal_input)
            if assessment is not None and assessment.status == "classified":
                value = {
                    "range_structure": assessment.range_structure,
                    "market_state": assessment.market_state.value,
                    "confidence": str(assessment.confidence),
                    "reason_codes": list(assessment.reason_codes),
                    "strategy_effect": assessment.strategy_effect,
                    "classifier": "RMR-001",
                    "hard_filter": assessment.hard_filter,
                    "execution_authority": assessment.execution_authority,
                }
                source = "rmr_regime_classifier"
                observed_at_ms = signal_input.market_snapshot.timestamp_ms
        if value is None:
            return fact_key, _missing_fact(
                fact_key,
                evaluated_at_ms,
                reason=f"{fact_key}_missing",
            )
        status = _status_for_fact(
            signal_input,
            fact_key,
            available=True,
            output=output,
            explicit_freshness=signal_input.market_snapshot.freshness
            if source == "signal_input.market_snapshot"
            else None,
        )
        return fact_key, _fact_snapshot(
            fact_key,
            source=source,
            observed_at_ms=observed_at_ms,
            evaluated_at_ms=evaluated_at_ms,
            status=status,
            value_snapshot={"value": _jsonable(value)},
        )

    def _volatility_state_fact(
        self,
        signal_input: StrategyFamilySignalInput,
        output: StrategyFamilySignalOutput | None,
        evaluated_at_ms: int,
    ) -> tuple[str, StrategyFactSnapshot]:
        fact_key = "volatility_state"
        value = _explicit_fact_value(output, fact_key)
        if value is None:
            value = _explicit_market_context_value(signal_input, fact_key)
        if value is None and (
            signal_input.market_snapshot.volatility is not None
            or signal_input.market_snapshot.atr is not None
        ):
            value = {
                "volatility": (
                    str(signal_input.market_snapshot.volatility)
                    if signal_input.market_snapshot.volatility is not None
                    else None
                ),
                "atr": (
                    str(signal_input.market_snapshot.atr)
                    if signal_input.market_snapshot.atr is not None
                    else None
                ),
            }
        if value is None:
            assessment = _rmr_assessment(signal_input)
            if assessment is not None and assessment.status == "classified":
                value = {
                    "volatility_state": assessment.volatility_state,
                    "market_state": assessment.market_state.value,
                    "confidence": str(assessment.confidence),
                    "reason_codes": list(assessment.reason_codes),
                    "classifier": "RMR-001",
                    "hard_filter": assessment.hard_filter,
                    "execution_authority": assessment.execution_authority,
                }
        if value is None:
            return fact_key, _missing_fact(
                fact_key,
                evaluated_at_ms,
                reason="volatility_state_missing",
            )
        status = _status_for_fact(
            signal_input,
            fact_key,
            available=True,
            output=output,
            explicit_freshness=signal_input.market_snapshot.freshness,
        )
        return fact_key, _fact_snapshot(
            fact_key,
            source="signal_input.market_snapshot",
            observed_at_ms=signal_input.market_snapshot.timestamp_ms,
            evaluated_at_ms=evaluated_at_ms,
            status=status,
            value_snapshot={"value": _jsonable(value)},
        )


def build_strategy_evaluation_context(
    signal_input: StrategyFamilySignalInput,
    *,
    output: StrategyFamilySignalOutput | None = None,
    runtime: StrategyRuntimeInstance | None = None,
    context_id: str | None = None,
) -> StrategyEvaluationContext:
    return StrategyEvaluationContextBuilder().build(
        signal_input,
        output=output,
        runtime=runtime,
        context_id=context_id,
    )


def _assert_signal_shapes_match(
    signal_input: StrategyFamilySignalInput,
    output: StrategyFamilySignalOutput | None,
    runtime: StrategyRuntimeInstance | None,
) -> None:
    mismatches: list[str] = []
    if output is not None:
        if output.evaluation_id != signal_input.evaluation_id:
            mismatches.append("evaluation_id")
        if output.strategy_family_id != signal_input.strategy_family_id:
            mismatches.append("strategy_family_id")
        if output.strategy_family_version_id != signal_input.strategy_family_version_id:
            mismatches.append("strategy_family_version_id")
        if output.symbol != signal_input.symbol:
            mismatches.append("symbol")
    if runtime is not None:
        if runtime.strategy_family_id != signal_input.strategy_family_id:
            mismatches.append("runtime.strategy_family_id")
        if runtime.strategy_family_version_id != signal_input.strategy_family_version_id:
            mismatches.append("runtime.strategy_family_version_id")
        if runtime.symbol != signal_input.symbol:
            mismatches.append("runtime.symbol")
    if mismatches:
        raise StrategyEvaluationContextBuilderError(
            "strategy evaluation context source mismatch: " + ", ".join(mismatches)
        )


def _context_side(
    signal_input: StrategyFamilySignalInput,
    output: StrategyFamilySignalOutput | None,
    runtime: StrategyRuntimeInstance | None,
) -> str:
    if output is not None:
        return "none" if output.side == SignalSide.NONE else output.side.value
    if runtime is not None:
        return runtime.side
    side = signal_input.trial_constraints_snapshot.get("side")
    return str(side) if side else "none"


def _candle_window(
    signal_input: StrategyFamilySignalInput,
    timeframe: str,
) -> list[Any]:
    windows = dict(signal_input.market_snapshot.candle_context.get("windows") or {})
    raw = windows.get(timeframe)
    if isinstance(raw, list) and raw:
        return raw
    if (
        signal_input.primary_timeframe == timeframe
        and signal_input.market_snapshot.timeframe == timeframe
        and signal_input.market_snapshot.candle_context
    ):
        return [dict(signal_input.market_snapshot.candle_context)]
    return []


def _account_snapshot_is_usable(signal_input: StrategyFamilySignalInput) -> bool:
    account = signal_input.account_facts_snapshot
    lowered = {
        str(account.source).lower(),
        str(account.truth_level).lower(),
        str(account.freshness).lower(),
        str(account.account_status).lower(),
    }
    unavailable_tokens = {
        "unavailable",
        "unknown",
        "not_checked",
        "invalid",
        "stale",
        "missing",
    }
    if lowered & unavailable_tokens:
        return False
    if any("does not require account facts" in item for item in account.limitations):
        return False
    return True


def _status_for_fact(
    signal_input: StrategyFamilySignalInput,
    fact_key: str,
    *,
    available: bool,
    output: StrategyFamilySignalOutput | None = None,
    explicit_freshness: str | None = None,
) -> FactAvailabilityStatus:
    if not available:
        return FactAvailabilityStatus.MISSING
    missing_fields = {
        *signal_input.input_quality.missing_fields,
        *signal_input.market_snapshot.missing_fields,
    }
    if output is not None:
        missing_fields.update(output.data_quality.missing_fields)
    if fact_key in missing_fields:
        return FactAvailabilityStatus.MISSING
    stale_fields = set(signal_input.input_quality.stale_fields)
    if output is not None:
        stale_fields.update(output.data_quality.stale_fields)
    if fact_key in stale_fields:
        return FactAvailabilityStatus.STALE
    if _freshness_is_stale(explicit_freshness or signal_input.freshness):
        return FactAvailabilityStatus.STALE
    return FactAvailabilityStatus.AVAILABLE


def _freshness_is_stale(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip().lower()
    return any(token in normalized for token in ("stale", "expired", "outdated"))


def _fact_snapshot(
    fact_key: str,
    *,
    source: str,
    observed_at_ms: int,
    evaluated_at_ms: int,
    status: FactAvailabilityStatus,
    value_snapshot: dict[str, Any],
) -> StrategyFactSnapshot:
    return StrategyFactSnapshot(
        fact_key=fact_key,
        source=source,
        observed_at_ms=observed_at_ms,
        status=status,
        freshness_ms=max(evaluated_at_ms - observed_at_ms, 0),
        evidence_ref=f"{source}:{fact_key}:{observed_at_ms}",
        value_snapshot=value_snapshot,
    )


def _missing_fact(
    fact_key: str,
    evaluated_at_ms: int,
    *,
    reason: str,
    value_snapshot: dict[str, Any] | None = None,
) -> StrategyFactSnapshot:
    return StrategyFactSnapshot(
        fact_key=fact_key,
        source="strategy_evaluation_context_builder",
        observed_at_ms=evaluated_at_ms,
        status=FactAvailabilityStatus.MISSING,
        freshness_ms=None,
        evidence_ref=f"missing:{fact_key}",
        value_snapshot={"reason": reason, **(value_snapshot or {})},
    )


def _explicit_fact_value(
    output: StrategyFamilySignalOutput | None,
    fact_key: str,
) -> Any | None:
    if output is None:
        return None
    for payload in (output.evidence_payload, output.signal_snapshot):
        value = _nested_value(payload, fact_key)
        if value is not None:
            return value
    return None


def _explicit_market_context_value(
    signal_input: StrategyFamilySignalInput,
    fact_key: str,
) -> Any | None:
    return _nested_value(signal_input.market_snapshot.candle_context, fact_key)


def _nested_value(payload: dict[str, Any], key: str) -> Any | None:
    if key in payload:
        return payload[key]
    for nested_key in ("facts", "market_facts", "risk_facts", "structure"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict) and key in nested:
            return nested[key]
    return None


def _market_state(
    signal_input: StrategyFamilySignalInput,
    output: StrategyFamilySignalOutput | None,
) -> MarketState:
    explicit = _explicit_fact_value(output, "market_state")
    if explicit is None:
        explicit = _explicit_market_context_value(signal_input, "market_state")
    if explicit is None:
        assessment = _rmr_assessment(signal_input)
        if assessment is not None and assessment.status == "classified":
            return assessment.market_state
        return MarketState.UNCERTAIN
    if isinstance(explicit, MarketState):
        return explicit
    try:
        return MarketState(str(explicit).upper())
    except ValueError:
        return MarketState.UNCERTAIN


def _rmr_assessment(
    signal_input: StrategyFamilySignalInput,
) -> RmrRegimeAssessment | None:
    if signal_input.strategy_family_id != "RMR-001":
        return None
    return classify_rmr_regime(_candle_window(signal_input, "1h"))


def _context_id(evaluation_id: str) -> str:
    suffix = evaluation_id[-104:]
    return f"strategy-context:{suffix}"


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _jsonable(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
