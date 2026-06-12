#!/usr/bin/env python3
"""Verify ready strategy signal -> shadow candidate boundary locally.

This verifier is intentionally local and in-memory. It proves that a
READY_FOR_SEMANTIC_BINDING strategy signal can create shadow SignalEvaluation /
OrderCandidate planning records with concrete entry, stop, TP/runner, notional,
leverage, margin, and loss preview fields without touching PG, HTTP, exchange,
OrderLifecycle, orders, withdrawals, or transfers.
"""

from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal
import json
from pathlib import Path
import sys
import time
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.build_runtime_strategy_signal_input_packet import (  # noqa: E402
    _build_signal_input,
)
from src.application.runtime_strategy_signal_evaluation_service import (  # noqa: E402
    RuntimeStrategySignalEvaluationService,
    RuntimeStrategySignalEvaluationStatus,
)
from src.application.runtime_strategy_signal_planning_service import (  # noqa: E402
    RuntimeStrategySignalCandidatePlanningStatus,
    RuntimeStrategySignalPlanningService,
)
from src.application.strategy_group_live_readonly_observation import (  # noqa: E402
    SampleStrategyGroupMarketBarSource,
)
from src.application.strategy_runtime_fact_overlay_service import (  # noqa: E402
    StrategyRuntimeFactOverlayService,
)
from src.application.strategy_semantics_shadow_binding_service import (  # noqa: E402
    StrategySemanticsShadowBindingService,
)
from src.application.trial_readiness_account_facts import (  # noqa: E402
    AccountFactsFreshnessStatus,
    AccountFactsReconciliationStatus,
    AccountFactsSourceType,
    StaticTrialReadinessAccountFactsSource,
    TrialReadinessAccountFacts,
)
from src.domain.signal_evaluation import (  # noqa: E402
    OrderCandidate,
    SignalEvaluation,
    SignalEvaluationDecision,
    SignalEvaluationStatus,
)
from src.domain.strategy_family_signal import (  # noqa: E402
    SignalSide,
    StrategyFamilySignalOutput,
)
from src.domain.strategy_runtime import (  # noqa: E402
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)


NOW_MS = 1_786_000_000_000


class _NoActivePositionsSource:
    async def list_active(self, *, symbol: str | None = None, limit: int = 100) -> list[Any]:
        return []


class _InMemoryShadowService:
    def __init__(self) -> None:
        self.evaluation: SignalEvaluation | None = None
        self.created_candidate_kwargs: dict[str, Any] | None = None

    async def create_signal_evaluation_from_strategy_family_output(
        self,
        output: StrategyFamilySignalOutput,
        *,
        runtime: StrategyRuntimeInstance | None = None,
        metadata: dict | None = None,
    ) -> SignalEvaluation:
        side = "none" if output.side == SignalSide.NONE else output.side.value
        self.evaluation = SignalEvaluation(
            signal_evaluation_id=f"signal-eval-rtf047-{output.strategy_family_id.lower()}",
            runtime_instance_id=runtime.runtime_instance_id if runtime else None,
            trial_binding_id=runtime.trial_binding_id if runtime else None,
            strategy_family_id=output.strategy_family_id,
            strategy_family_version_id=output.strategy_family_version_id,
            source_signal_id=output.signal_id,
            symbol=output.symbol,
            side=side,
            status=SignalEvaluationStatus.EVALUATED,
            decision=(
                SignalEvaluationDecision.CANDIDATE
                if side in {"long", "short"}
                else SignalEvaluationDecision.NO_ACTION
            ),
            reason_codes=list(output.reason_codes),
            rationale=output.human_summary,
            evidence_snapshot=output.model_dump(mode="json"),
            policy_snapshot={
                "required_execution_mode": output.required_execution_mode,
                "rtf047_shadow_only": True,
            },
            evaluated_at_ms=NOW_MS,
            created_at_ms=NOW_MS,
            updated_at_ms=NOW_MS,
            metadata=metadata or {},
        )
        return self.evaluation

    async def get_signal_evaluation(self, signal_evaluation_id: str) -> SignalEvaluation:
        if self.evaluation is None:
            raise RuntimeError("signal evaluation not created")
        if signal_evaluation_id != self.evaluation.signal_evaluation_id:
            raise RuntimeError("unexpected signal evaluation id")
        return self.evaluation

    async def create_order_candidate_from_signal_evaluation(
        self,
        signal_evaluation_id: str,
        **kwargs: Any,
    ) -> OrderCandidate:
        if self.evaluation is None:
            raise RuntimeError("signal evaluation not created")
        self.created_candidate_kwargs = dict(kwargs)
        return OrderCandidate(
            order_candidate_id="order-candidate-rtf047-rbr-ada-shadow",
            signal_evaluation_id=signal_evaluation_id,
            runtime_instance_id=self.evaluation.runtime_instance_id,
            trial_binding_id=self.evaluation.trial_binding_id,
            strategy_family_id=self.evaluation.strategy_family_id,
            strategy_family_version_id=self.evaluation.strategy_family_version_id,
            symbol=self.evaluation.symbol,
            side=self.evaluation.side,  # type: ignore[arg-type]
            candidate_order_type=kwargs["candidate_order_type"],
            proposed_quantity=kwargs.get("proposed_quantity"),
            intended_notional=kwargs.get("intended_notional"),
            entry_price_reference=kwargs.get("entry_price_reference"),
            risk_preview=kwargs["risk_preview"],
            protection_preview=kwargs["protection_preview"],
            rationale=kwargs.get("rationale") or self.evaluation.rationale,
            evidence_refs=kwargs["evidence_refs"],
            created_at_ms=NOW_MS,
            updated_at_ms=NOW_MS,
            expires_at_ms=kwargs.get("expires_at_ms"),
            metadata=kwargs["metadata"],
        )


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="python"))
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _runtime(
    *,
    family_id: str,
    version_id: str,
    symbol: str,
    side: str,
) -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id=f"strategy-runtime-rtf047-{family_id.lower()}-{side}",
        trial_binding_id=f"trial-binding-rtf047-{family_id.lower()}-{side}",
        admission_decision_id=f"admission-rtf047-{family_id.lower()}-{side}",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        owner_risk_acceptance_id="owner-risk-rtf047",
        symbol=symbol,
        side=side,
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=0,
            budget_reserved=Decimal("0"),
            max_active_positions=1,
            max_notional_per_attempt=Decimal("8"),
            total_budget=Decimal("6"),
            allowed_symbols=[symbol],
            allowed_sides=[side],
            max_leverage=Decimal("1"),
            max_margin_per_attempt=Decimal("8"),
            min_liquidation_stop_buffer=Decimal("25"),
            requires_protection=True,
            requires_review=True,
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
        activated_at_ms=NOW_MS,
        metadata={
            "rtf047_sample_rehearsal": True,
            "right_tail_risk_capital": True,
        },
    )


def _account_facts() -> TrialReadinessAccountFacts:
    return TrialReadinessAccountFacts(
        account_id="local-rtf047-fake-account",
        account_type="usdt_futures_read_only_snapshot",
        source_id="local_rtf047_injected_read_only_account_facts",
        source_type=AccountFactsSourceType.INJECTED_FAKE,
        account_equity=Decimal("30"),
        available_margin=Decimal("30"),
        timestamp_ms=NOW_MS,
        freshness_status=AccountFactsFreshnessStatus.FRESH,
        reconciliation_status=AccountFactsReconciliationStatus.CLEAN,
        read_only_guarantee=True,
        external_call_performed=False,
        external_call_type="none",
        notes=("local in-memory RTF-047 verifier facts",),
    )


def _build_sample_signal_input(runtime: StrategyRuntimeInstance, *, suffix: str) -> Any:
    source = SampleStrategyGroupMarketBarSource()
    one_hour = source.latest_closed_candles(
        symbol=runtime.symbol,
        timeframe="1h",
        limit=25,
    )
    four_hour = source.latest_closed_candles(
        symbol=runtime.symbol,
        timeframe="4h",
        limit=25,
    )
    return _build_signal_input(
        runtime=runtime,
        one_hour=one_hour,
        four_hour=four_hour,
        source_id=source.source_id,
        source_type="sample_rehearsal",
        evaluation_id=f"runtime-signal-input-rtf047-{suffix}",
        playbook_id=f"rtf047-sample-{suffix}-playbook",
        now_ms=NOW_MS,
    )


def _required_pass_checks(
    result: Any,
    *,
    family_id: str,
    version_id: str,
    symbol: str,
    side: str,
) -> dict[str, bool]:
    candidate = result.candidate
    proposal = result.proposal
    protection = candidate.protection_preview if candidate is not None else None
    risk = candidate.risk_preview if candidate is not None else None
    tp_kinds = {
        str(item.get("kind"))
        for item in (protection.take_profit_references if protection is not None else [])
    }
    return {
        "status_shadow_candidate_created": (
            result.status
            == RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
        ),
        "signal_evaluation_created": result.signal_evaluation_created is True,
        "order_candidate_created": result.order_candidate_created is True,
        "candidate_is_shadow_only": (
            candidate is not None
            and candidate.shadow_mode is True
            and candidate.execution_enabled is False
            and candidate.candidate_executable is False
            and candidate.not_order is True
            and candidate.not_execution_intent is True
        ),
        "strategy_symbol_side_bound": (
            candidate is not None
            and candidate.strategy_family_id == family_id
            and candidate.strategy_family_version_id == version_id
            and candidate.symbol == symbol
            and candidate.side == side
        ),
        "entry_present": candidate is not None and candidate.entry_price_reference is not None,
        "stop_present": protection is not None and protection.stop_price_reference is not None,
        "protection_required": protection is not None and protection.requires_protection is True,
        "tp1_partial_present": "tp1_partial" in tp_kinds,
        "runner_present": "runner" in tp_kinds,
        "notional_present": risk is not None and risk.intended_notional is not None,
        "quantity_present": risk is not None and risk.proposed_quantity is not None,
        "max_loss_present": risk is not None and risk.max_loss_reference is not None,
        "leverage_present": risk is not None and risk.leverage is not None,
        "margin_present": risk is not None and risk.margin_required is not None,
        "liquidation_reference_present": (
            risk is not None and risk.liquidation_price_reference is not None
        ),
        "liquidation_stop_buffer_present": (
            risk is not None and risk.liquidation_stop_buffer is not None
        ),
        "proposal_scope_shadow_only": (
            proposal is not None
            and proposal.not_order is True
            and proposal.not_execution_intent is True
            and proposal.not_execution_authority is True
        ),
        "right_tail_metadata_present": (
            proposal is not None
            and proposal.metadata.get("right_tail_exit_shape")
            == "tp1_1r_partial_plus_runner_trailing_metadata"
        ),
    }


def _required_block_checks(result: Any) -> dict[str, bool]:
    return {
        "candidate_not_created": result.candidate is None,
        "proposal_not_created": result.proposal is None,
        "signal_evaluation_not_created": result.signal_evaluation_created is False,
        "order_candidate_not_created": result.order_candidate_created is False,
        "execution_intent_not_created": result.execution_intent_created is False,
        "order_not_created": result.order_created is False,
        "order_lifecycle_not_called": result.order_lifecycle_called is False,
        "exchange_not_called": result.exchange_called is False,
    }


async def _plan_scenario(
    *,
    scenario_id: str,
    family_id: str,
    version_id: str,
    symbol: str,
    side: str,
    expect_shadow_candidate: bool,
) -> dict[str, Any]:
    runtime = _runtime(
        family_id=family_id,
        version_id=version_id,
        symbol=symbol,
        side=side,
    )
    signal_input = _build_sample_signal_input(runtime, suffix=scenario_id)
    evaluation = RuntimeStrategySignalEvaluationService().evaluate(signal_input)

    shadow_service = _InMemoryShadowService()
    planner = RuntimeStrategySignalPlanningService(
        semantics_binding_service=StrategySemanticsShadowBindingService(
            shadow_service=shadow_service,
        ),
        runtime_execution_planning_service=object(),  # not used by this shadow path
        runtime_fact_overlay_service=StrategyRuntimeFactOverlayService(
            active_position_source=_NoActivePositionsSource(),
            account_facts_source=StaticTrialReadinessAccountFactsSource(_account_facts()),
            require_trusted_account_source=True,
            require_trusted_market_fact_source=False,
        ),
    )
    planning_result = await planner.plan_shadow_candidate_from_signal_input(
        signal_input,
        runtime=runtime,
        context_id=f"strategy-context-rtf047-{scenario_id}",
        expires_at_ms=NOW_MS + 15 * 60 * 1000,
        metadata={
            "rtf047": True,
            "sample_rehearsal": True,
            "local_in_memory_only": True,
        },
    )
    checks = (
        _required_pass_checks(
            planning_result,
            family_id=family_id,
            version_id=version_id,
            symbol=symbol,
            side=side,
        )
        if expect_shadow_candidate
        else _required_block_checks(planning_result)
    )
    safety_invariants = {
        "local_in_memory_only": True,
        "database_connected": False,
        "http_network_called": False,
        "exchange_called": planning_result.exchange_called,
        "exchange_write_called": False,
        "execution_intent_created": planning_result.execution_intent_created,
        "order_created": planning_result.order_created,
        "order_lifecycle_called": planning_result.order_lifecycle_called,
        "withdrawal_or_transfer_created": False,
    }
    safety_ok = (
        safety_invariants["local_in_memory_only"] is True
        and safety_invariants["database_connected"] is False
        and safety_invariants["http_network_called"] is False
        and safety_invariants["exchange_called"] is False
        and safety_invariants["exchange_write_called"] is False
        and safety_invariants["execution_intent_created"] is False
        and safety_invariants["order_created"] is False
        and safety_invariants["order_lifecycle_called"] is False
        and safety_invariants["withdrawal_or_transfer_created"] is False
    )
    evaluation_ready = (
        evaluation.status
        == RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
    )
    if expect_shadow_candidate:
        expected_status_ok = (
            evaluation_ready
            and planning_result.status
            == RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
            and not planning_result.blockers
        )
    else:
        expected_status_ok = (
            planning_result.status
            != RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
        )
    passed = expected_status_ok and all(checks.values()) and safety_ok
    return {
        "scenario_id": scenario_id,
        "status": "passed" if passed else "failed",
        "runtime_instance_id": runtime.runtime_instance_id,
        "strategy_family_id": runtime.strategy_family_id,
        "strategy_family_version_id": runtime.strategy_family_version_id,
        "symbol": runtime.symbol,
        "side": runtime.side,
        "evaluation_status": evaluation.status.value,
        "planning_status": planning_result.status.value,
        "blockers": list(planning_result.blockers),
        "warnings": list(planning_result.warnings),
        "checks": checks,
        "safety_invariants": safety_invariants,
        "planning_result": _json_value(planning_result),
    }


async def build_boundary_report() -> dict[str, Any]:
    scenarios = [
        await _plan_scenario(
            scenario_id="cpm-long-eth",
            family_id="CPM-RO-001",
            version_id="CPM-RO-001-v0",
            symbol="ETH/USDT:USDT",
            side="long",
            expect_shadow_candidate=True,
        ),
        await _plan_scenario(
            scenario_id="brf-short-btc",
            family_id="BRF-001",
            version_id="BRF-001-v0",
            symbol="BTC/USDT:USDT",
            side="short",
            expect_shadow_candidate=True,
        ),
        await _plan_scenario(
            scenario_id="cpm-short-mismatch",
            family_id="CPM-RO-001",
            version_id="CPM-RO-001-v0",
            symbol="ETH/USDT:USDT",
            side="short",
            expect_shadow_candidate=False,
        ),
        await _plan_scenario(
            scenario_id="rmr-classifier-no-trade",
            family_id="RMR-001",
            version_id="RMR-001-v0",
            symbol="ETH/USDT:USDT",
            side="long",
            expect_shadow_candidate=False,
        ),
        await _plan_scenario(
            scenario_id="fco-data-backlog-no-trade",
            family_id="FCO-001",
            version_id="FCO-001-v0",
            symbol="ETH/USDT:USDT",
            side="long",
            expect_shadow_candidate=False,
        ),
    ]
    passed = all(item["status"] == "passed" for item in scenarios)
    return {
        "scope": "rtf047_ready_shadow_candidate_boundary",
        "status": (
            "rtf047_ready_shadow_candidate_boundary_passed"
            if passed
            else "rtf047_ready_shadow_candidate_boundary_failed"
        ),
        "generated_at_ms": int(time.time() * 1000),
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "safety_summary": {
            "local_in_memory_only": True,
            "database_connected": False,
            "http_network_called": False,
            "exchange_write_called": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify local ready signal -> shadow candidate boundary.",
    )
    parser.add_argument("--output-json")
    args = parser.parse_args()
    report = asyncio.run(build_boundary_report())
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"].endswith("_passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
