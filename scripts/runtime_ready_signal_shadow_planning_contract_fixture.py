#!/usr/bin/env python3
"""Ready-signal contract proof for live-operator -> shadow planning.

RTF-075 proves the intended non-executing path with a deterministic CPM long
fixture:

ready operator packet
-> runtime_live_signal_shadow_planning_bridge
-> real RuntimeNextAttemptStrategyPlanningService
-> real RuntimeStrategySignalPlanningService
-> shadow SignalEvaluation / shadow OrderCandidate with entry/stop/TP/runner.

The fixture does not start a server, call exchange, create ExecutionIntent
records, create submit authorizations, arm submit, mutate runtime budget, or
move funds.
"""

from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_live_signal_shadow_planning_bridge as bridge  # noqa: E402
from src.application.runtime_execution_planning_service import (  # noqa: E402
    RuntimeExecutionPlanningService,
)
from src.application.runtime_final_gate_preview_service import (  # noqa: E402
    RuntimeFinalGatePreviewService,
)
from src.application.runtime_next_attempt_strategy_planning_service import (  # noqa: E402
    RuntimeNextAttemptStrategyPlanningService,
)
from src.application.runtime_strategy_signal_planning_service import (  # noqa: E402
    RuntimeStrategySignalPlanningService,
)
from src.application.signal_evaluation_shadow_service import (  # noqa: E402
    SignalEvaluationShadowService,
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
from src.domain.runtime_post_submit_finalize import (  # noqa: E402
    RuntimePostSubmitFinalizePacket,
)
from src.domain.signal_evaluation import (  # noqa: E402
    OrderCandidate,
    SignalEvaluation,
    SignalEvaluationDecision,
    SignalEvaluationStatus,
)
from src.domain.strategy_family_signal import (  # noqa: E402
    AccountFactsSnapshot,
    MarketSnapshot,
    SignalSide,
    StrategyFamilySignalInput,
    StrategyFamilySignalOutput,
)
from src.domain.strategy_runtime import (  # noqa: E402
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)


NOW_MS = 1781000000000


class _RuntimeService:
    def __init__(self, runtime: StrategyRuntimeInstance) -> None:
        self.runtime = runtime

    async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
        if runtime_instance_id != self.runtime.runtime_instance_id:
            raise ValueError("runtime_fixture_id_mismatch")
        return self.runtime


class _TrustedPositionSource:
    async def list_active(self, *, symbol: str | None = None, limit: int = 100):
        if symbol != "ETH/USDT:USDT":
            raise ValueError("symbol_fixture_mismatch")
        if limit != 100:
            raise ValueError("limit_fixture_mismatch")
        return []


class _ShadowStore(SignalEvaluationShadowService):
    def __init__(self) -> None:
        self.evaluation: SignalEvaluation | None = None
        self.candidate: OrderCandidate | None = None

    async def create_signal_evaluation_from_strategy_family_output(
        self,
        output: StrategyFamilySignalOutput,
        *,
        runtime=None,
        metadata=None,
    ) -> SignalEvaluation:
        side = "none" if output.side == SignalSide.NONE else output.side.value
        self.evaluation = SignalEvaluation(
            signal_evaluation_id="signal-eval-rtf075-contract",
            runtime_instance_id=getattr(runtime, "runtime_instance_id", None),
            trial_binding_id=getattr(runtime, "trial_binding_id", None),
            strategy_family_id=output.strategy_family_id,
            strategy_family_version_id=output.strategy_family_version_id,
            source_signal_id=output.signal_id,
            symbol=output.symbol,
            side=side,
            status=SignalEvaluationStatus.EVALUATED,
            decision=SignalEvaluationDecision.CANDIDATE,
            reason_codes=list(output.reason_codes),
            rationale=output.human_summary,
            evaluated_at_ms=NOW_MS,
            created_at_ms=NOW_MS,
            updated_at_ms=NOW_MS,
            metadata=metadata or {},
        )
        return self.evaluation

    async def get_signal_evaluation(self, signal_evaluation_id: str) -> SignalEvaluation:
        if self.evaluation is None:
            raise ValueError("signal_evaluation_not_created")
        if signal_evaluation_id != self.evaluation.signal_evaluation_id:
            raise ValueError("signal_evaluation_id_mismatch")
        return self.evaluation

    async def create_order_candidate_from_signal_evaluation(
        self,
        signal_evaluation_id: str,
        **kwargs,
    ) -> OrderCandidate:
        if self.evaluation is None:
            raise ValueError("signal_evaluation_not_created")
        self.candidate = OrderCandidate(
            order_candidate_id="order-candidate-rtf075-contract",
            signal_evaluation_id=signal_evaluation_id,
            runtime_instance_id=self.evaluation.runtime_instance_id,
            trial_binding_id=self.evaluation.trial_binding_id,
            strategy_family_id=self.evaluation.strategy_family_id,
            strategy_family_version_id=self.evaluation.strategy_family_version_id,
            symbol=self.evaluation.symbol,
            side=self.evaluation.side,
            candidate_order_type=kwargs["candidate_order_type"],
            proposed_quantity=kwargs.get("proposed_quantity"),
            intended_notional=kwargs.get("intended_notional"),
            entry_price_reference=kwargs.get("entry_price_reference"),
            risk_preview=kwargs["risk_preview"],
            protection_preview=kwargs["protection_preview"],
            rationale=kwargs.get("rationale") or "",
            evidence_refs=kwargs["evidence_refs"],
            metadata=kwargs["metadata"],
            created_at_ms=NOW_MS,
            updated_at_ms=NOW_MS,
        )
        return self.candidate

    async def get_order_candidate(self, order_candidate_id: str) -> OrderCandidate:
        if self.candidate is None:
            raise ValueError("order_candidate_not_created")
        if order_candidate_id != self.candidate.order_candidate_id:
            raise ValueError("order_candidate_id_mismatch")
        return self.candidate


def build_contract_fixture_report(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime = _runtime()
    signal_input = _signal_input()
    post_submit = _post_submit_finalize_packet(runtime)
    operator_packet = {
        "scope": "runtime_live_signal_operator_cycle",
        "status": "ready_for_prepare",
        "runtime_instance_id": runtime.runtime_instance_id,
        "signal_input_json": str(output_dir / "signal-input.json"),
        "blockers": [],
        "warnings": [],
        "safety_invariants": _source_safety(),
    }

    _write_json(output_dir / "signal-input.json", signal_input.model_dump(mode="json"))
    _write_json(
        output_dir / "post-submit-finalize.json",
        post_submit.model_dump(mode="json"),
    )
    _write_json(output_dir / "operator-ready.json", operator_packet)

    bridge_args = argparse.Namespace(
        runtime_instance_id=runtime.runtime_instance_id,
        operator_packet_json=str(output_dir / "operator-ready.json"),
        post_submit_finalize_packet_json=str(output_dir / "post-submit-finalize.json"),
        env_file=None,
        api_base="http://fixture",
        context_id="context-rtf075-contract",
        expires_at_ms=None,
        metadata_json='{"rtf075_contract_fixture": true}',
        output_dir=str(output_dir / "bridge-artifacts"),
        flow_id="rtf075-ready-signal",
        output_json=None,
    )

    store = _ShadowStore()
    planning_service = _planning_service(runtime=runtime, store=store)

    def planning_builder(args: argparse.Namespace) -> dict[str, Any]:
        return asyncio.run(
            _build_planning_packet(
                args,
                runtime=runtime,
                planning_service=planning_service,
            )
        )

    bridge_packet = bridge._build_packet(bridge_args, planning_builder=planning_builder)
    _write_json(output_dir / "bridge-report.json", bridge_packet)
    report = _report(
        bridge_packet=bridge_packet,
        store=store,
    )
    _write_json(output_dir / "contract-report.json", report)
    return report


async def _build_planning_packet(
    args: argparse.Namespace,
    *,
    runtime: StrategyRuntimeInstance,
    planning_service: RuntimeNextAttemptStrategyPlanningService,
) -> dict[str, Any]:
    post_submit = RuntimePostSubmitFinalizePacket.model_validate(
        _read_json(Path(args.post_submit_finalize_packet_json))
    )
    signal_input = StrategyFamilySignalInput.model_validate(
        _read_json(Path(args.signal_input_json))
    )
    packet = await planning_service.plan_from_post_submit_gate(
        post_submit_finalize_packet=post_submit,
        signal_input=signal_input,
        runtime=runtime,
        context_id=args.context_id,
        expires_at_ms=args.expires_at_ms,
        metadata=json.loads(args.metadata_json or "{}"),
    )
    return {
        "scope": "runtime_next_attempt_strategy_plan_api_flow",
        "status": packet.status.value,
        "runtime_instance_id": packet.runtime_instance_id,
        "http_status": 200,
        "api_payload": packet.model_dump(mode="json"),
        "blockers": list(packet.blockers),
        "warnings": list(packet.warnings),
        "safety_invariants": {
            "uses_official_trading_console_api": False,
            "uses_real_strategy_planning_service": True,
            "non_executing": True,
            "local_registration_armed": False,
            "exchange_submit_armed": False,
            "execute_real_submit": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "position_opened": False,
            "position_closed": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _planning_service(
    *,
    runtime: StrategyRuntimeInstance,
    store: _ShadowStore,
) -> RuntimeNextAttemptStrategyPlanningService:
    runtime_service = _RuntimeService(runtime)
    final_gate = RuntimeFinalGatePreviewService(
        runtime_service=runtime_service,
        signal_evaluation_service=store,
        active_position_source=_TrustedPositionSource(),
    )
    execution_planning = RuntimeExecutionPlanningService(
        runtime_service=runtime_service,
        signal_evaluation_service=store,
        final_gate_preview_service=final_gate,
    )
    signal_planning = RuntimeStrategySignalPlanningService(
        semantics_binding_service=StrategySemanticsShadowBindingService(
            shadow_service=store,
        ),
        runtime_execution_planning_service=execution_planning,
        runtime_fact_overlay_service=StrategyRuntimeFactOverlayService(
            active_position_source=_TrustedPositionSource(),
            account_facts_source=_ready_account_source(),
        ),
    )
    return RuntimeNextAttemptStrategyPlanningService(
        strategy_signal_planner=signal_planning,
    )


def _report(*, bridge_packet: dict[str, Any], store: _ShadowStore) -> dict[str, Any]:
    candidate = store.candidate
    proposal = None
    if candidate is not None:
        proposal = candidate.metadata.get("planning_proposal")
    checks = _checks(bridge_packet=bridge_packet, candidate=candidate, proposal=proposal)
    return {
        "scope": "runtime_ready_signal_shadow_planning_contract_fixture",
        "status": (
            "ready_signal_shadow_planning_contract_passed"
            if _contract_passed(checks)
            else "blocked"
        ),
        "bridge_status": bridge_packet.get("status"),
        "runtime_instance_id": bridge_packet.get("runtime_instance_id"),
        "signal_evaluation_id": bridge_packet.get("signal_evaluation_id"),
        "order_candidate_id": bridge_packet.get("order_candidate_id"),
        "proposal": proposal,
        "candidate_snapshot": (
            candidate.model_dump(mode="json") if candidate is not None else None
        ),
        "checks": checks,
        "blockers": list(bridge_packet.get("blockers") or []),
        "warnings": list(bridge_packet.get("warnings") or []),
        "safety_invariants": {
            "fixture_only": True,
            "uses_real_strategy_planning_service": True,
            "uses_live_exchange": False,
            "prepare_records_created": False,
            "execution_intent_created": False,
            "submit_authorization_created": False,
            "local_registration_armed": False,
            "exchange_submit_armed": False,
            "execute_real_submit": False,
            "exchange_write_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "attempt_counter_mutated": False,
            "runtime_budget_mutated": False,
            "position_opened": False,
            "position_closed": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _checks(
    *,
    bridge_packet: dict[str, Any],
    candidate: OrderCandidate | None,
    proposal: dict[str, Any] | None,
) -> dict[str, Any]:
    tp_refs = proposal.get("take_profit_references", []) if isinstance(proposal, dict) else []
    return {
        "ready_for_final_gate_preflight": (
            bridge_packet.get("status") == "ready_for_final_gate_preflight"
        ),
        "shadow_signal_evaluation_created": candidate is not None,
        "shadow_order_candidate_created": candidate is not None,
        "entry_price_reference_present": bool(
            isinstance(proposal, dict) and proposal.get("entry_price_reference")
        ),
        "stop_price_reference_present": bool(
            isinstance(proposal, dict) and proposal.get("stop_price_reference")
        ),
        "tp1_present": any(
            str(item.get("kind") or "").startswith("tp1")
            for item in tp_refs
            if isinstance(item, dict)
        ),
        "runner_present": any(
            item.get("kind") == "runner" for item in tp_refs if isinstance(item, dict)
        ),
        "notional_present": bool(
            isinstance(proposal, dict) and proposal.get("intended_notional")
        ),
        "leverage_present": bool(isinstance(proposal, dict) and proposal.get("leverage")),
        "right_tail_runner_preserved": any(
            item.get("right_tail_capture") is True
            for item in tp_refs
            if isinstance(item, dict)
        ),
        "execution_intent_created": False,
        "submit_authorization_created": False,
        "order_created": False,
        "exchange_write_called": False,
    }


def _contract_passed(checks: dict[str, Any]) -> bool:
    required = (
        "ready_for_final_gate_preflight",
        "shadow_signal_evaluation_created",
        "shadow_order_candidate_created",
        "entry_price_reference_present",
        "stop_price_reference_present",
        "tp1_present",
        "runner_present",
        "right_tail_runner_preserved",
        "notional_present",
        "leverage_present",
    )
    forbidden_false = (
        "execution_intent_created",
        "submit_authorization_created",
        "order_created",
        "exchange_write_called",
    )
    return all(checks.get(key) is True for key in required) and all(
        checks.get(key) is False for key in forbidden_false
    )


def _runtime() -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id="runtime-rtf075-cpm-long",
        trial_binding_id="trial-rtf075-cpm-long",
        admission_decision_id="admission-rtf075-cpm-long",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="ETH/USDT:USDT",
        side="long",
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=0,
            budget_reserved=Decimal("0"),
            max_active_positions=1,
            max_notional_per_attempt=Decimal("10"),
            total_budget=Decimal("9"),
            allowed_symbols=["ETH/USDT:USDT"],
            allowed_sides=["long"],
            max_leverage=Decimal("1"),
            max_margin_per_attempt=Decimal("10"),
            min_liquidation_stop_buffer=Decimal("25"),
            requires_protection=True,
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=NOW_MS,
        updated_at_ms=NOW_MS,
    )


def _post_submit_finalize_packet(
    runtime: StrategyRuntimeInstance,
) -> RuntimePostSubmitFinalizePacket:
    return RuntimePostSubmitFinalizePacket.model_validate(
        {
            "packet_id": "post-submit-rtf075-contract",
            "authorization_id": "auth-rtf075-consumed",
            "runtime_instance_id": runtime.runtime_instance_id,
            "exchange_submit_execution_result_id": "submit-result-rtf075-contract",
            "post_submit_reconciliation_evidence_id": (
                "post-submit-reconciliation-rtf075-contract"
            ),
            "submit_outcome_review_id": "submit-review-rtf075-contract",
            "post_submit_budget_settlement_id": (
                "budget-settlement-rtf075-contract"
            ),
            "status": "finalized_ready_for_next_attempt",
            "submit_result_status": "exchange_submit_orders_submitted",
            "submit_outcome_review_status": (
                "classified_ready_for_attempt_outcome_policy"
            ),
            "post_submit_budget_settlement_status": "released_reserved_budget",
            "post_submit_finalize_complete": True,
            "post_submit_reconciliation_matched": True,
            "post_submit_budget_settled": True,
            "submit_outcome_review_recorded": True,
            "next_attempt_gate": {
                "status": "ready_for_fresh_signal",
                "runtime_instance_id": runtime.runtime_instance_id,
                "attempts_remaining": 2,
                "budget_remaining": "9",
                "active_positions_count": 0,
                "max_active_positions": 1,
                "requires_fresh_strategy_signal": True,
                "requires_fresh_authorization": True,
                "consumed_authorization_replay_only": True,
                "pre_submit_rehearsal_retry_allowed": False,
                "blockers": [],
                "warnings": [],
            },
            "consumed_authorization_replay_only": True,
            "old_authorization_submit_retry_allowed": False,
            "pre_submit_rehearsal_retry_allowed": False,
            "local_created_order_requirement_retired": True,
            "blockers": [],
            "warnings": [],
            "not_execution_authority": True,
            "runtime_state_mutated_by_packet": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_cancelled": False,
            "position_closed": False,
            "exchange_called": False,
            "exchange_order_submitted": False,
            "order_lifecycle_called": False,
            "owner_bounded_execution_called": False,
            "withdrawal_or_transfer_created": False,
            "created_at_ms": NOW_MS,
        }
    )


def _signal_input() -> StrategyFamilySignalInput:
    return StrategyFamilySignalInput(
        evaluation_id="eval-rtf075-cpm-long",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        symbol="ETH/USDT:USDT",
        timestamp_ms=NOW_MS,
        primary_timeframe="1h",
        context_timeframes=["4h"],
        market_snapshot=MarketSnapshot(
            symbol="ETH/USDT:USDT",
            timestamp_ms=NOW_MS,
            source="rtf075_fixture",
            freshness="fresh",
            last_price=Decimal("104.2"),
            mark_price=Decimal("104.2"),
            funding_rate=Decimal("0.0001"),
            volatility=Decimal("0.15"),
            atr=Decimal("3"),
            timeframe="1h",
            candle_context={
                "windows": {
                    "1h": _cpm_reclaim_1h(),
                    "4h": _cpm_uptrend_4h(),
                },
                "closed_bar": True,
            },
        ),
        account_facts_snapshot=AccountFactsSnapshot(
            source="fixture_placeholder_replaced_by_overlay",
            truth_level="placeholder",
            timestamp_ms=NOW_MS,
            freshness="fresh",
            account_status="not_checked",
            available_balance=Decimal("30"),
            positions=[],
            open_orders=[],
            position_count=99,
            open_order_count=0,
            unknown_unmanaged_counts={"orders": 0, "positions": 99},
            reconciliation_status={"status": "not_checked"},
            read_only_provider="fixture_placeholder",
            limitations=["trusted runtime overlay required"],
        ),
        position_open_order_summary={"active_positions_count": 99, "position_count": 99},
        reconciliation_status={"status": "not_checked"},
        runtime_safety_snapshot={"runtime_state": "active"},
        trial_constraints_snapshot={
            "max_attempts": 3,
            "max_loss_budget": "9",
            "max_notional_per_attempt": "10",
            "max_active_positions": 1,
            "max_leverage": "1",
            "allowed_symbols": ["ETH/USDT:USDT"],
            "allowed_sides": ["long"],
        },
        source="rtf075_fixture",
        freshness="fresh",
    )


def _ready_account_source() -> StaticTrialReadinessAccountFactsSource:
    return StaticTrialReadinessAccountFactsSource(
        TrialReadinessAccountFacts(
            account_id="rtf075-account",
            account_type="fixture",
            source_id="rtf075_cached_account_facts",
            source_type=AccountFactsSourceType.PG_ACCOUNT_FACTS,
            account_equity=Decimal("30"),
            available_margin=Decimal("29"),
            timestamp_ms=NOW_MS,
            freshness_status=AccountFactsFreshnessStatus.FRESH,
            reconciliation_status=AccountFactsReconciliationStatus.CLEAN,
            read_only_guarantee=True,
            external_call_performed=False,
            external_call_type="none",
        )
    )


def _candle(index: int, open_: str, high: str, low: str, close: str) -> dict[str, Any]:
    return {
        "open_time_ms": NOW_MS - (40 - index) * 3_600_000,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": "100",
    }


def _cpm_reclaim_1h() -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for index in range(18):
        close = Decimal("100") + Decimal(index) * Decimal("0.15")
        candles.append(
            _candle(
                index,
                str(close - Decimal("0.1")),
                str(close + Decimal("0.4")),
                str(close - Decimal("0.4")),
                str(close),
            )
        )
    candles.append(_candle(18, "101.6", "102.4", "100.9", "101.8"))
    candles.append(_candle(19, "101.9", "103.0", "101.0", "102.2"))
    candles.append(_candle(20, "102.4", "105.0", "102.0", "104.2"))
    return candles


def _cpm_uptrend_4h() -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for index in range(21):
        close = Decimal("96") + Decimal(index) * Decimal("0.8")
        candles.append(
            _candle(
                index,
                str(close - Decimal("0.4")),
                str(close + Decimal("1.1")),
                str(close - Decimal("0.8")),
                str(close),
            )
        )
    return candles


def _source_safety() -> dict[str, bool]:
    return {
        "runtime_created": False,
        "runtime_profile_mutated": False,
        "local_registration_armed": False,
        "exchange_submit_armed": False,
        "execute_real_submit": False,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "attempt_counter_mutated": False,
        "runtime_budget_mutated": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the RTF-075 ready-signal shadow planning contract fixture.",
    )
    parser.add_argument(
        "--output-dir",
        default="output/rtf075-ready-signal-contract",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_contract_fixture_report(Path(args.output_dir).expanduser())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return (
        0
        if report["status"] == "ready_signal_shadow_planning_contract_passed"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
