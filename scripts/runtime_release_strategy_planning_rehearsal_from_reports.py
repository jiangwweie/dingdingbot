#!/usr/bin/env python3
"""Rehearse release-gated strategy planning from report JSON files.

Inputs are existing non-executing reports:

- runtime_next_attempt_release_from_reports.py output
- StrategyFamilySignalInput JSON

The script uses a non-persistent rehearsal planner. It verifies whether
RuntimeNextAttemptStrategyPlanningService.plan_from_release_gate would call a
shadow planner after the release gate. It never talks to PG, exchange,
OrderLifecycle, or runtime mutation services.
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

from src.application.runtime_next_attempt_strategy_planning_service import (  # noqa: E402
    RuntimeNextAttemptStrategyPlanningService,
)
from src.application.runtime_strategy_signal_evaluation_service import (  # noqa: E402
    RuntimeStrategySignalEvaluationResult,
    RuntimeStrategySignalEvaluationStatus,
)
from src.application.runtime_strategy_signal_planning_service import (  # noqa: E402
    RuntimeStrategySignalCandidatePlanningResult,
    RuntimeStrategySignalCandidatePlanningStatus,
)
from src.domain.runtime_next_attempt_release import (  # noqa: E402
    RuntimeNextAttemptReleaseEvidence,
)
from src.domain.signal_evaluation import OrderCandidate  # noqa: E402
from src.domain.strategy_family_signal import (  # noqa: E402
    SignalSide,
    StrategyFamilySignalInput,
)
from src.domain.strategy_runtime import (  # noqa: E402
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)


def _load_report(path: str) -> dict[str, Any]:
    text = Path(path).expanduser().read_text(encoding="utf-8")
    start = text.find("{")
    if start < 0:
        raise ValueError(f"{path} does not contain a JSON object")
    value = json.loads(text[start:])
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _payload(report: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = report.get(key)
        if isinstance(value, dict):
            return value
    return report


def _decimal_from_snapshot(
    snapshot: dict[str, Any],
    key: str,
    default: str,
) -> Decimal:
    value = snapshot.get(key, default)
    return Decimal(str(value))


def _int_from_snapshot(
    snapshot: dict[str, Any],
    key: str,
    default: int,
) -> int:
    value = snapshot.get(key, default)
    return int(value)


def _runtime_from_release_and_signal(
    release: RuntimeNextAttemptReleaseEvidence,
    signal_input: StrategyFamilySignalInput,
) -> StrategyRuntimeInstance:
    constraints = dict(signal_input.trial_constraints_snapshot or {})
    side = release.side if release.side in {"long", "short"} else SignalSide.LONG.value
    return StrategyRuntimeInstance(
        runtime_instance_id=release.runtime_instance_id,
        trial_binding_id=f"trial-{release.runtime_instance_id}",
        admission_decision_id=f"admission-{release.runtime_instance_id}",
        strategy_family_id=signal_input.strategy_family_id,
        strategy_family_version_id=signal_input.strategy_family_version_id,
        symbol=release.symbol,
        side=side,
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=_int_from_snapshot(constraints, "max_attempts", 3),
            attempts_used=0,
            budget_reserved=Decimal("0"),
            max_active_positions=_int_from_snapshot(
                constraints,
                "max_active_positions",
                1,
            ),
            max_notional_per_attempt=_decimal_from_snapshot(
                constraints,
                "max_notional_per_attempt",
                "30",
            ),
            total_budget=_decimal_from_snapshot(
                constraints,
                "max_loss_budget",
                "30",
            ),
            allowed_symbols=list(
                constraints.get("allowed_symbols") or [release.symbol],
            ),
            allowed_sides=list(constraints.get("allowed_sides") or [side]),
            max_leverage=_decimal_from_snapshot(constraints, "max_leverage", "1"),
            requires_protection=True,
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=release.created_at_ms,
        updated_at_ms=release.created_at_ms,
        metadata={"runtime_release_strategy_planning_rehearsal": True},
    )


class _RehearsalPlanner:
    def __init__(
        self,
        *,
        planning_status: RuntimeStrategySignalCandidatePlanningStatus,
        now_ms: int,
    ) -> None:
        self.planning_status = planning_status
        self.now_ms = now_ms
        self.calls = 0
        self.last_metadata: dict[str, Any] | None = None

    async def plan_shadow_candidate_from_signal_input(
        self,
        signal_input: StrategyFamilySignalInput,
        *,
        runtime: StrategyRuntimeInstance,
        context_id: str | None = None,
        expires_at_ms: int | None = None,
        metadata: dict | None = None,
    ) -> RuntimeStrategySignalCandidatePlanningResult:
        self.calls += 1
        self.last_metadata = metadata
        candidate = (
            _candidate(signal_input, runtime=runtime, now_ms=self.now_ms)
            if self.planning_status
            == RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED
            else None
        )
        evaluation_status = (
            RuntimeStrategySignalEvaluationStatus.READY_FOR_SEMANTIC_BINDING
            if candidate is not None
            else RuntimeStrategySignalEvaluationStatus.OBSERVE_ONLY
        )
        return RuntimeStrategySignalCandidatePlanningResult(
            planning_id=f"release-rehearsal-planning-{signal_input.evaluation_id}",
            runtime_instance_id=runtime.runtime_instance_id,
            strategy_family_id=signal_input.strategy_family_id,
            strategy_family_version_id=signal_input.strategy_family_version_id,
            symbol=signal_input.symbol,
            status=self.planning_status,
            evaluation_result=RuntimeStrategySignalEvaluationResult(
                evaluation_id=signal_input.evaluation_id,
                strategy_family_id=signal_input.strategy_family_id,
                strategy_family_version_id=signal_input.strategy_family_version_id,
                symbol=signal_input.symbol,
                status=evaluation_status,
                output=None,
                blockers=[] if candidate is not None else ["rehearsal_observe_only"],
                warnings=[],
                semantics_binding_found=True,
                strategy_candidate_mode="shadow_order_candidate_allowed",
                runtime_confirmation_mode="owner_confirm_each_attempt_initially",
                evaluator_id="ReleaseGateRehearsalPlanner",
                evaluator_called=False,
                can_call_semantic_binding=candidate is not None,
            ),
            candidate=candidate,
            blockers=[] if candidate is not None else ["rehearsal_observe_only"],
            warnings=[],
            signal_evaluation_created=candidate is not None,
            order_candidate_created=candidate is not None,
            metadata={
                "scope": "runtime_release_strategy_planning_rehearsal",
                "context_id": context_id,
                "expires_at_ms": expires_at_ms,
                "not_persistent": True,
            },
        )


def _candidate(
    signal_input: StrategyFamilySignalInput,
    *,
    runtime: StrategyRuntimeInstance,
    now_ms: int,
) -> OrderCandidate:
    side = runtime.side if runtime.side in {"long", "short"} else SignalSide.LONG.value
    return OrderCandidate(
        order_candidate_id=f"rehearsal-order-candidate-{signal_input.evaluation_id}",
        signal_evaluation_id=signal_input.evaluation_id,
        runtime_instance_id=runtime.runtime_instance_id,
        trial_binding_id=runtime.trial_binding_id,
        strategy_family_id=signal_input.strategy_family_id,
        strategy_family_version_id=signal_input.strategy_family_version_id,
        symbol=signal_input.symbol,
        side=side,
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
        metadata={
            "runtime_release_strategy_planning_rehearsal": True,
            "not_persistent": True,
        },
    )


async def _build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    release_report = _load_report(args.next_attempt_release_json)
    signal_report = _load_report(args.signal_input_json)
    release = RuntimeNextAttemptReleaseEvidence.model_validate(
        _payload(release_report, "release_evidence"),
    )
    signal_input = StrategyFamilySignalInput.model_validate(
        _payload(signal_report, "signal_input"),
    )
    now_ms = args.now_ms if args.now_ms is not None else int(time.time() * 1000)
    planner = _RehearsalPlanner(
        planning_status=RuntimeStrategySignalCandidatePlanningStatus(
            args.planning_status,
        ),
        now_ms=now_ms,
    )
    service = RuntimeNextAttemptStrategyPlanningService(
        strategy_signal_planner=planner,
    )
    runtime = _runtime_from_release_and_signal(release, signal_input)
    planning_artifact = await service.plan_from_release_gate(
        next_attempt_release_evidence=release,
        signal_input=signal_input,
        runtime=runtime,
        context_id=args.context_id,
        expires_at_ms=args.expires_at_ms,
        metadata={
            "runtime_release_strategy_planning_rehearsal_from_reports": True,
            "non_persistent_rehearsal_planner": True,
        },
    )
    return {
        "scope": "runtime_release_strategy_planning_rehearsal_from_reports",
        "status": planning_artifact.status.value,
        "planning_artifact": planning_artifact.model_dump(mode="json"),
        "planner_called": planner.calls > 0,
        "planner_call_count": planner.calls,
        "planner_metadata": planner.last_metadata or {},
        "source_reports": {
            "next_attempt_release_json": args.next_attempt_release_json,
            "signal_input_json": args.signal_input_json,
        },
        "safety_invariants": {
            "release_strategy_planning_rehearsal_evidence_only": True,
            "uses_rehearsal_planner": True,
            "pg_read_called": False,
            "pg_write_called": False,
            "exchange_called": False,
            "exchange_write_called": False,
            "execution_intent_created": False,
            "executable_execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "position_opened": False,
            "position_closed": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rehearse release-gated runtime strategy planning from reports.",
    )
    parser.add_argument("--next-attempt-release-json", required=True)
    parser.add_argument("--signal-input-json", required=True)
    parser.add_argument(
        "--planning-status",
        choices=[item.value for item in RuntimeStrategySignalCandidatePlanningStatus],
        default=RuntimeStrategySignalCandidatePlanningStatus.SHADOW_CANDIDATE_CREATED.value,
    )
    parser.add_argument("--context-id")
    parser.add_argument("--expires-at-ms", type=int)
    parser.add_argument("--now-ms", type=int)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    artifact = asyncio.run(_build_artifact(args))
    print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
