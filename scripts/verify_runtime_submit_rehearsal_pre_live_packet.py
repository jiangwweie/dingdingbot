#!/usr/bin/env python3
"""Build a local pre-live runtime submit rehearsal packet.

This verifier uses the real runtime execution planning/adapter services with
in-memory repositories. It proves the non-executing chain can reach the submit
adapter boundary while separately reporting first-real-submit blockers such as
current-head deployment and explicit Owner live-submit authorization.

It never connects to a database, mutates Tokyo, starts a runtime, creates an
order, calls OrderLifecycle, or calls exchange APIs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.application.runtime_execution_intent_adapter_service import (
    RuntimeExecutionIntentAdapterService,
)
from src.application.runtime_execution_planning_service import (
    RuntimeExecutionPlanningService,
)
from src.application.runtime_final_gate_preview_service import (
    RuntimeFinalGatePreviewService,
)
from src.domain.execution_intent import ExecutionIntent, ExecutionIntentStatus
from src.domain.runtime_execution_controlled_submit import (
    RuntimeExecutionControlledSubmitPreflightStatus,
)
from src.domain.runtime_execution_intent_adapter import (
    RuntimeExecutionSubmitReadinessStatus,
)
from src.domain.runtime_execution_plan import (
    RuntimeExecutionIntentDraft,
    RuntimeExecutionIntentDraftStatus,
    RuntimeExecutionPlanStatus,
)
from src.domain.runtime_execution_submit_authorization import (
    RuntimeExecutionSubmitAuthorization,
    RuntimeExecutionSubmitAuthorizationStatus,
)
from src.domain.runtime_execution_submit_rehearsal import (
    RuntimeExecutionSubmitRehearsalStatus,
)
from src.domain.runtime_execution_submit_adapter import (
    RuntimeExecutionSubmitAdapterPreviewStatus,
)
from src.domain.signal_evaluation import (
    OrderCandidate,
    OrderCandidateProtectionPreview,
    OrderCandidateRiskPreview,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)


DEFAULT_DEPLOYED_HEAD = "ae9b209e33cd287273491f2e93dfdff3b6a814fd"
DEFAULT_SYMBOL = "BNB/USDT:USDT"
DEFAULT_SIDE = "long"
DEFAULT_RUNTIME_ID = "pre-live-rehearsal-runtime-bnb-long"
DEFAULT_ORDER_CANDIDATE_ID = "pre-live-rehearsal-candidate-bnb-long"
OWNER_AUTHORIZATION_FLAG = "--owner-real-submit-authorized"


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    returncode: int


class _RuntimeService:
    def __init__(self, runtime: StrategyRuntimeInstance) -> None:
        self.runtime = runtime

    async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
        if runtime_instance_id != self.runtime.runtime_instance_id:
            raise ValueError("runtime_not_found")
        return self.runtime


class _CandidateService:
    def __init__(self, candidate: OrderCandidate) -> None:
        self.candidate = candidate

    async def get_order_candidate(self, order_candidate_id: str) -> OrderCandidate:
        if order_candidate_id != self.candidate.order_candidate_id:
            raise ValueError("order_candidate_not_found")
        return self.candidate


class _ActivePositionSource:
    def __init__(self, active_positions: int) -> None:
        self.active_positions = active_positions

    async def list_active(self, *, symbol: str | None = None, limit: int = 100):
        return [object() for _ in range(self.active_positions)]


class _DraftRepository:
    def __init__(self) -> None:
        self.records: dict[str, RuntimeExecutionIntentDraft] = {}

    async def create(
        self,
        draft: RuntimeExecutionIntentDraft,
    ) -> RuntimeExecutionIntentDraft:
        self.records[draft.draft_id] = draft
        return draft

    async def get(self, draft_id: str) -> RuntimeExecutionIntentDraft | None:
        return self.records.get(draft_id)


class _IntentRepository:
    def __init__(self) -> None:
        self.records: dict[str, ExecutionIntent] = {}

    async def get(self, intent_id: str) -> ExecutionIntent | None:
        return self.records.get(intent_id)

    async def save(self, intent: ExecutionIntent) -> None:
        self.records[intent.id] = intent


class _SubmitAuthorizationRepository:
    def __init__(self) -> None:
        self.records: dict[str, RuntimeExecutionSubmitAuthorization] = {}

    async def get(
        self,
        authorization_id: str,
    ) -> RuntimeExecutionSubmitAuthorization | None:
        return self.records.get(authorization_id)

    async def create(
        self,
        authorization: RuntimeExecutionSubmitAuthorization,
    ) -> RuntimeExecutionSubmitAuthorization:
        self.records[authorization.authorization_id] = authorization
        return authorization


async def build_pre_live_packet(
    *,
    deployed_head: str | None,
    owner_real_submit_authorized: bool,
    require_current_head_deployed: bool = True,
    active_positions: int = 0,
    runner: Any | None = None,
) -> dict[str, Any]:
    repo_root = _repo_root(runner=runner)
    local_head = _git(repo_root, "rev-parse", "HEAD", runner=runner).stdout
    short_head = _git(repo_root, "rev-parse", "--short=8", "HEAD", runner=runner).stdout
    runtime = _runtime()
    candidate = _candidate()

    runtime_service = _RuntimeService(runtime)
    candidate_service = _CandidateService(candidate)
    active_position_source = _ActivePositionSource(active_positions)
    final_gate = RuntimeFinalGatePreviewService(
        runtime_service=runtime_service,
        signal_evaluation_service=candidate_service,
        active_position_source=active_position_source,
    )
    draft_repository = _DraftRepository()
    intent_repository = _IntentRepository()
    authorization_repository = _SubmitAuthorizationRepository()
    planning_service = RuntimeExecutionPlanningService(
        runtime_service=runtime_service,
        signal_evaluation_service=candidate_service,
        final_gate_preview_service=final_gate,
        intent_draft_repository=draft_repository,
    )
    adapter_service = RuntimeExecutionIntentAdapterService(
        draft_repository=draft_repository,
        intent_repository=intent_repository,
        submit_authorization_repository=authorization_repository,
        final_gate_preview_service=final_gate,
        runtime_service=runtime_service,
    )

    plan = await planning_service.plan_order_candidate(
        order_candidate_id=candidate.order_candidate_id,
        owner_reviewed=True,
    )
    draft = await planning_service.record_intent_draft_for_order_candidate(
        order_candidate_id=candidate.order_candidate_id,
        owner_reviewed=True,
        owner_confirmed_for_intent=True,
    )
    intent_preview = await adapter_service.preview_from_draft(draft.draft_id)
    intent = await adapter_service.create_recorded_intent_from_draft(draft.draft_id)
    submit_readiness = await adapter_service.submit_readiness_for_intent(intent.id)
    authorization = await adapter_service.create_submit_authorization_for_intent(
        intent.id,
        owner_confirmed_for_submit=True,
    )
    rehearsal = await adapter_service.submit_rehearsal_for_authorization(
        authorization.authorization_id
    )

    technical_blockers = _dedupe(
        list(plan.final_gate_preview.blockers)
        + list(draft.blockers)
        + list(intent_preview.blockers)
        + list(submit_readiness.blockers)
        + list(rehearsal.blockers)
    )
    operational_blockers: list[str] = []
    deployed_head = deployed_head or ""
    current_head_deployed = bool(deployed_head and deployed_head == local_head)
    if require_current_head_deployed and not current_head_deployed:
        operational_blockers.append("current_head_not_deployed_to_tokyo")
    if not owner_real_submit_authorized:
        operational_blockers.append("owner_real_submit_authorization_missing")
    implementation_blockers: list[str] = []
    if runtime.shadow_mode or not runtime.execution_enabled:
        implementation_blockers.append("runtime_not_live_execution_enabled")
    if not rehearsal.submit_adapter_preview.submit_adapter_implemented:
        implementation_blockers.append("controlled_submit_adapter_not_implemented")

    checks = {
        "technical_rehearsal_passed": _technical_rehearsal_passed(
            plan=plan,
            draft=draft,
            intent=intent,
            submit_readiness=submit_readiness,
            authorization=authorization,
            rehearsal=rehearsal,
        ),
        "current_head_deployed": current_head_deployed,
        "owner_real_submit_authorization_present": owner_real_submit_authorized,
        "ready_for_first_real_submit": False,
        "technical_blockers": technical_blockers,
        "operational_blockers": operational_blockers,
        "implementation_blockers": implementation_blockers,
        "forbidden_execution_flags": _forbidden_execution_flags(
            intent=intent,
            authorization=authorization,
            rehearsal=rehearsal,
        ),
    }
    checks["ready_for_first_real_submit"] = (
        checks["technical_rehearsal_passed"]
        and not technical_blockers
        and not operational_blockers
        and not implementation_blockers
        and not checks["forbidden_execution_flags"]
    )

    return {
        "status": (
            "ready_for_owner_controlled_first_real_submit_review"
            if checks["ready_for_first_real_submit"]
            else "blocked_before_first_real_submit"
        ),
        "scope": "runtime_submit_rehearsal_pre_live_packet",
        "repo_root": str(repo_root),
        "local_git": {
            "head": local_head,
            "short_head": short_head,
        },
        "deployment_gate": {
            "deployed_head": deployed_head or None,
            "require_current_head_deployed": require_current_head_deployed,
            "current_head_deployed": current_head_deployed,
        },
        "owner_gate": {
            "owner_real_submit_authorized": owner_real_submit_authorized,
            "authorization_flag": OWNER_AUTHORIZATION_FLAG,
        },
        "pipeline": {
            "plan_status": _enum_value(plan.status),
            "intent_draft_status": _enum_value(draft.status),
            "intent_creation_preview_status": _enum_value(intent_preview.status),
            "recorded_intent_status": _enum_value(intent.status),
            "submit_readiness_status": _enum_value(submit_readiness.status),
            "submit_authorization_status": _enum_value(authorization.status),
            "controlled_submit_preflight_status": (
                _enum_value(rehearsal.controlled_submit_preflight.status)
            ),
            "attempt_reservation_preview_status": (
                _enum_value(rehearsal.attempt_reservation_preview.status)
            ),
            "protection_plan_preview_status": (
                _enum_value(rehearsal.protection_plan_preview.status)
            ),
            "submit_adapter_preview_status": _enum_value(
                rehearsal.submit_adapter_preview.status
            ),
            "submit_rehearsal_status": _enum_value(rehearsal.status),
            "safe_stop_stage": rehearsal.safe_stop_stage,
            "next_required_gate": rehearsal.next_required_gate,
        },
        "checks": checks,
        "rehearsal": rehearsal.model_dump(mode="json"),
        "safety_invariants": {
            "database_connected": False,
            "remote_files_modified": False,
            "services_restarted": False,
            "migrations_run": False,
            "runtime_started": False,
            "runtime_budget_mutated": rehearsal.runtime_budget_mutated,
            "attempt_consumed": rehearsal.attempt_consumed,
            "execution_intent_status_changed": rehearsal.execution_intent_status_changed,
            "order_created": rehearsal.order_created,
            "owner_bounded_execution_called": rehearsal.owner_bounded_execution_called,
            "order_lifecycle_called": rehearsal.order_lifecycle_called,
            "exchange_called": rehearsal.exchange_called,
            "withdrawal_or_transfer_created": False,
        },
        "notes": [
            "This packet uses in-memory repositories for rehearsal evidence only.",
            "The recorded ExecutionIntent is an in-memory audit artifact, not a persistent executable submit.",
            "The submit adapter remains not implemented for order placement.",
        ],
    }


def _runtime() -> StrategyRuntimeInstance:
    return StrategyRuntimeInstance(
        runtime_instance_id=DEFAULT_RUNTIME_ID,
        trial_binding_id="pre-live-trial-binding-bnb-long",
        admission_decision_id="pre-live-admission-bnb-long",
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v0",
        symbol=DEFAULT_SYMBOL,
        side=DEFAULT_SIDE,
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=0,
            max_active_positions=1,
            max_notional_per_attempt=Decimal("10"),
            total_budget=Decimal("3"),
            budget_reserved=Decimal("0"),
            allowed_symbols=[DEFAULT_SYMBOL],
            allowed_sides=[DEFAULT_SIDE],
            max_leverage=Decimal("1"),
            max_margin_per_attempt=Decimal("10"),
            min_liquidation_stop_buffer=Decimal("25"),
            requires_protection=True,
            requires_review=True,
        ),
        created_at_ms=1781079000000,
        updated_at_ms=1781079000000,
        metadata={
            "scope": "pre_live_submit_rehearsal_packet",
            "small_experimental_risk_capital": True,
            "right_tail_objective": True,
        },
    )


def _candidate() -> OrderCandidate:
    return OrderCandidate(
        order_candidate_id=DEFAULT_ORDER_CANDIDATE_ID,
        signal_evaluation_id="pre-live-rehearsal-signal-evaluation-bnb-long",
        runtime_instance_id=DEFAULT_RUNTIME_ID,
        trial_binding_id="pre-live-trial-binding-bnb-long",
        strategy_family_id="CPM-001",
        strategy_family_version_id="CPM-001-v0",
        symbol=DEFAULT_SYMBOL,
        side=DEFAULT_SIDE,
        candidate_order_type="market",
        proposed_quantity=Decimal("0.016"),
        intended_notional=Decimal("9.60"),
        entry_price_reference=Decimal("600"),
        risk_preview=OrderCandidateRiskPreview(
            intended_notional=Decimal("9.60"),
            proposed_quantity=Decimal("0.016"),
            max_loss_reference=Decimal("0.20"),
            leverage=Decimal("1"),
            margin_required=Decimal("9.60"),
            liquidation_price_reference=Decimal("0"),
            liquidation_stop_buffer=Decimal("100"),
            notes=[
                "loss budget basis is max_loss_reference, not full notional",
                "small bounded loss is acceptable inside runtime boundary",
            ],
        ),
        protection_preview=OrderCandidateProtectionPreview(
            requires_protection=True,
            stop_reference="cpm_pullback_low_or_atr_reference",
            stop_price_reference=Decimal("587.50"),
            take_profit_references=[
                {
                    "kind": "tp1_partial",
                    "rr": "1",
                    "position_ratio": "0.5",
                    "non_executing_preview": True,
                },
                {
                    "kind": "runner",
                    "policy": "trailing_atr_or_structure_invalidation",
                    "right_tail_capture": True,
                    "non_executing_preview": True,
                },
            ],
            notes=[
                "hard stop bounds downside",
                "runner metadata preserves right-tail objective",
            ],
        ),
        rationale="pre-live runtime submit rehearsal packet for bounded CPM long",
        evidence_refs=[
            "pre-live-submit-rehearsal",
            "cpm-reference-semantics",
        ],
        created_at_ms=1781079000000,
        updated_at_ms=1781079000000,
        metadata={
            "scope": "pre_live_submit_rehearsal_candidate",
            "not_proven_alpha": True,
            "non_executing_rehearsal": True,
        },
    )


def _technical_rehearsal_passed(
    *,
    plan: Any,
    draft: RuntimeExecutionIntentDraft,
    intent: ExecutionIntent,
    submit_readiness: Any,
    authorization: RuntimeExecutionSubmitAuthorization,
    rehearsal: Any,
) -> bool:
    return (
        plan.status == RuntimeExecutionPlanStatus.READY_FOR_INTENT_DRAFT
        and draft.status == RuntimeExecutionIntentDraftStatus.READY_FOR_INTENT_CREATION
        and intent.status == ExecutionIntentStatus.RECORDED
        and submit_readiness.status
        == RuntimeExecutionSubmitReadinessStatus.OWNER_SUBMIT_AUTHORIZATION_REQUIRED
        and authorization.status
        == RuntimeExecutionSubmitAuthorizationStatus.APPROVED_PENDING_CONTROLLED_SUBMIT
        and rehearsal.controlled_submit_preflight.status
        == RuntimeExecutionControlledSubmitPreflightStatus.READY_FOR_CONTROLLED_SUBMIT_ADAPTER
        and rehearsal.submit_adapter_preview.status
        == RuntimeExecutionSubmitAdapterPreviewStatus.INPUTS_READY_ADAPTER_NOT_IMPLEMENTED
        and rehearsal.status
        == RuntimeExecutionSubmitRehearsalStatus.READY_FOR_NON_EXECUTING_SUBMIT_ADAPTER_BOUNDARY
    )


def _forbidden_execution_flags(
    *,
    intent: ExecutionIntent,
    authorization: RuntimeExecutionSubmitAuthorization,
    rehearsal: Any,
) -> list[str]:
    flags: list[str] = []
    if intent.status != ExecutionIntentStatus.RECORDED:
        flags.append("execution_intent_not_recorded_audit_status")
    if intent.order_id is not None or intent.exchange_order_id is not None:
        flags.append("execution_intent_contains_order_artifact")
    checks = {
        "authorization_submit_executed": authorization.submit_executed,
        "authorization_order_created": authorization.order_created,
        "authorization_exchange_called": authorization.exchange_called,
        "authorization_owner_bounded_execution_called": (
            authorization.owner_bounded_execution_called
        ),
        "authorization_order_lifecycle_called": authorization.order_lifecycle_called,
        "rehearsal_submit_executed": rehearsal.submit_executed,
        "rehearsal_runtime_budget_mutated": rehearsal.runtime_budget_mutated,
        "rehearsal_attempt_consumed": rehearsal.attempt_consumed,
        "rehearsal_execution_intent_status_changed": (
            rehearsal.execution_intent_status_changed
        ),
        "rehearsal_order_created": rehearsal.order_created,
        "rehearsal_exchange_called": rehearsal.exchange_called,
        "rehearsal_owner_bounded_execution_called": (
            rehearsal.owner_bounded_execution_called
        ),
        "rehearsal_order_lifecycle_called": rehearsal.order_lifecycle_called,
    }
    flags.extend(key for key, value in checks.items() if value)
    return flags


def _repo_root(*, runner: Any | None = None) -> Path:
    result = _run(("git", "rev-parse", "--show-toplevel"), cwd=Path.cwd(), runner=runner)
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError("not_inside_git_repository")
    return Path(result.stdout)


def _git(repo_root: Path, *args: str, runner: Any | None = None) -> CommandResult:
    result = _run(("git", *args), cwd=repo_root, runner=runner)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed")
    return result


def _run(
    command: tuple[str, ...],
    *,
    cwd: Path,
    runner: Any | None = None,
) -> CommandResult:
    if runner is not None:
        return runner(command, cwd)
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout = completed.stdout.strip()
    if completed.returncode != 0 and completed.stderr.strip():
        stdout = completed.stderr.strip()
    return CommandResult(stdout=stdout, returncode=completed.returncode)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a local non-executing pre-live runtime submit rehearsal packet."
        )
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--deployed-head",
        default=DEFAULT_DEPLOYED_HEAD,
        help=(
            "Read-only deployed head used for the current-head deployment gate. "
            "Pass the post-deploy probe head when verifying after deployment."
        ),
    )
    parser.add_argument(
        "--skip-current-head-deployed-check",
        action="store_true",
        help="Do not block when local HEAD differs from --deployed-head.",
    )
    parser.add_argument(
        OWNER_AUTHORIZATION_FLAG,
        action="store_true",
        help=(
            "Mark the Owner first-real-submit authorization gate as present for "
            "readiness accounting only. This script still does not submit."
        ),
    )
    parser.add_argument(
        "--active-positions",
        type=int,
        default=0,
        help="Injected local active-position count for the in-memory rehearsal.",
    )
    return parser.parse_args(argv)


def _print_human(report: dict[str, Any]) -> None:
    checks = report["checks"]
    pipeline = report["pipeline"]
    print(f"status={report['status']}")
    print(f"technical_rehearsal_passed={str(checks['technical_rehearsal_passed']).lower()}")
    print(f"current_head_deployed={str(checks['current_head_deployed']).lower()}")
    print(
        "owner_real_submit_authorization_present="
        + str(checks["owner_real_submit_authorization_present"]).lower()
    )
    print(f"ready_for_first_real_submit={str(checks['ready_for_first_real_submit']).lower()}")
    print(f"submit_rehearsal_status={pipeline['submit_rehearsal_status']}")
    print(f"submit_adapter_preview_status={pipeline['submit_adapter_preview_status']}")
    if checks["technical_blockers"]:
        print("technical_blockers=" + ",".join(checks["technical_blockers"]))
    if checks["operational_blockers"]:
        print("operational_blockers=" + ",".join(checks["operational_blockers"]))
    if checks["implementation_blockers"]:
        print(
            "implementation_blockers="
            + ",".join(checks["implementation_blockers"])
        )
    if checks["forbidden_execution_flags"]:
        print("forbidden_execution_flags=" + ",".join(checks["forbidden_execution_flags"]))


async def _amain(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = await build_pre_live_packet(
        deployed_head=args.deployed_head,
        owner_real_submit_authorized=args.owner_real_submit_authorized,
        require_current_head_deployed=not args.skip_current_head_deployed_check,
        active_positions=args.active_positions,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0 if report["checks"]["technical_rehearsal_passed"] else 2


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_amain(argv))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"pre_live_packet_error={exc}", file=sys.stderr)
        raise SystemExit(2)
