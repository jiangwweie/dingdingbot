#!/usr/bin/env python3
"""Local non-executing rehearsal for scheduled observation shadow planning.

This verifier runs entirely in-process with in-memory repositories and static
read-only facts. It does not connect to PG, call exchange APIs, create
ExecutionIntent records, create orders, call OrderLifecycle, or mutate runtime
state.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


async def build_rehearsal_report() -> dict[str, Any]:
    from src.application.runtime_execution_planning_service import (
        RuntimeExecutionPlanningService,
    )
    from src.application.runtime_final_gate_preview_service import (
        RuntimeFinalGatePreviewService,
    )
    from src.application.runtime_strategy_signal_scheduler_assembly import (
        RuntimeStrategySignalSchedulerFactSources,
    )
    from src.application.runtime_strategy_signal_scheduler_planning_service import (
        RuntimeStrategySignalSchedulerPlanningService,
    )
    from src.application.runtime_strategy_signal_planning_service import (
        RuntimeStrategySignalPlanningService,
    )
    from src.application.signal_evaluation_shadow_service import (
        SignalEvaluationShadowService,
    )
    from src.application.strategy_group_live_readonly_observation import (
        SampleStrategyGroupMarketBarSource,
        build_strategy_group_live_readonly_observation_v1,
    )
    from src.application.strategy_group_readonly_observation_scheduler import (
        StrategyRuntimeObservationResolver,
        run_scheduled_readonly_observation_once,
    )
    from src.application.strategy_runtime_fact_overlay_service import (
        StrategyRuntimeFactOverlayService,
    )
    from src.application.strategy_semantics_shadow_binding_service import (
        StrategySemanticsShadowBindingService,
    )
    from src.application.trial_readiness_account_facts import (
        AccountFactsFreshnessStatus,
        AccountFactsReconciliationStatus,
        AccountFactsSourceType,
        StaticTrialReadinessAccountFactsSource,
        TrialReadinessAccountFacts,
    )
    from src.domain.strategy_family_signal import StrategyFamilySignalInput

    preview = build_strategy_group_live_readonly_observation_v1(
        market_source=SampleStrategyGroupMarketBarSource()
    )
    cpm_record = next(
        record
        for record in preview.current_signals
        if record.candidate_id == "CPM-RO-001"
    )
    cpm_signal_input = StrategyFamilySignalInput.model_validate(
        cpm_record.signal_input_snapshot
    )
    runtime = _shadow_runtime_for_signal(
        cpm_signal_input,
        side=cpm_record.side,
        runtime_instance_id="rehearsal-runtime-cpm-long",
    )
    runtime_service = _InMemoryRuntimeService([runtime])
    shadow_repository = _InMemorySignalEvaluationRepository()
    shadow_service = SignalEvaluationShadowService(repository=shadow_repository)
    active_position_source = _EmptyActivePositionSource()
    account_facts_source = StaticTrialReadinessAccountFactsSource(
        TrialReadinessAccountFacts(
            account_id="rehearsal-account",
            account_type="static_read_only",
            source_id="static_rehearsal_account_facts",
            source_type=AccountFactsSourceType.INJECTED_FAKE,
            account_equity=Decimal("30"),
            available_margin=Decimal("30"),
            timestamp_ms=cpm_signal_input.timestamp_ms,
            freshness_status=AccountFactsFreshnessStatus.FRESH,
            reconciliation_status=AccountFactsReconciliationStatus.CLEAN,
            read_only_guarantee=True,
            external_call_performed=False,
            external_call_type="none",
            notes=("local_non_executing_rehearsal",),
        )
    )
    final_gate_preview_service = RuntimeFinalGatePreviewService(
        runtime_service=runtime_service,
        signal_evaluation_service=shadow_service,
        active_position_source=active_position_source,
    )
    runtime_execution_planning_service = RuntimeExecutionPlanningService(
        runtime_service=runtime_service,
        signal_evaluation_service=shadow_service,
        final_gate_preview_service=final_gate_preview_service,
        intent_draft_repository=None,
    )
    signal_planning_service = RuntimeStrategySignalPlanningService(
        semantics_binding_service=StrategySemanticsShadowBindingService(
            shadow_service=shadow_service,
        ),
        runtime_execution_planning_service=runtime_execution_planning_service,
        runtime_fact_overlay_service=StrategyRuntimeFactOverlayService(
            active_position_source=active_position_source,
            account_facts_source=account_facts_source,
        ),
    )
    scheduler_planning_service = RuntimeStrategySignalSchedulerPlanningService(
        planner=signal_planning_service,
        fact_sources=RuntimeStrategySignalSchedulerFactSources(
            trusted_runtime_fact_overlay_configured=True,
            trusted_active_position_source_available=True,
            trusted_account_facts_source_available=True,
            trusted_market_fact_source_available=False,
            source_scope="local_in_memory_rehearsal",
            metadata={
                "non_executing": True,
                "pg_connected": False,
                "exchange_called": False,
            },
        ),
    )
    result = await run_scheduled_readonly_observation_once(
        source_name="local_sqlite_fallback",
        market_source=SampleStrategyGroupMarketBarSource(),
        repository=_InMemoryObservationRepository(),
        runtime_resolver=StrategyRuntimeObservationResolver(
            runtime_service=runtime_service,
            now_ms_source=lambda: cpm_signal_input.timestamp_ms,
        ),
        runtime_signal_planning_service=scheduler_planning_service,
        allow_shadow_candidate_creation=True,
    )
    payload = result.model_dump(mode="json")
    candidate_results = payload["candidate_results"]
    shadow_created = [
        item
        for item in candidate_results
        if item["shadow_planning_action"] == "shadow_candidate_created"
    ]
    forbidden_flags = [
        key
        for item in candidate_results
        for key in (
            "execution_intent_created",
            "order_created",
            "order_lifecycle_called",
            "exchange_called",
        )
        if item[key] is not False
    ]
    checks = {
        "rehearsal_passed": bool(shadow_created) and not forbidden_flags,
        "shadow_candidate_created_count": len(shadow_created),
        "forbidden_execution_flags": forbidden_flags,
        "signal_evaluation_records": len(shadow_repository.signal_evaluations),
        "order_candidate_records": len(shadow_repository.order_candidates),
    }
    return {
        "status": "rehearsal_passed" if checks["rehearsal_passed"] else "blocked",
        "scope": "local_scheduled_observation_shadow_planning_rehearsal",
        "checks": checks,
        "result": payload,
        "safety_invariants": {
            "database_connected": False,
            "exchange_called": False,
            "execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "owner_bounded_execution_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def _shadow_runtime_for_signal(
    signal_input: Any,
    *,
    side: str,
    runtime_instance_id: str,
) -> Any:
    from src.domain.strategy_runtime import (
        StrategyRuntimeBoundary,
        StrategyRuntimeInstance,
        StrategyRuntimeInstanceStatus,
    )

    return StrategyRuntimeInstance(
        runtime_instance_id=runtime_instance_id,
        trial_binding_id="rehearsal-trial-cpm",
        admission_decision_id="rehearsal-admission-cpm",
        strategy_family_id=signal_input.strategy_family_id,
        strategy_family_version_id=signal_input.strategy_family_version_id,
        owner_risk_acceptance_id="rehearsal-risk-acceptance",
        symbol=signal_input.symbol,
        side=side,
        status=StrategyRuntimeInstanceStatus.ACTIVE,
        boundary=StrategyRuntimeBoundary(
            max_attempts=3,
            attempts_used=0,
            budget_reserved=Decimal("0"),
            max_active_positions=1,
            max_notional_per_attempt=Decimal("10"),
            total_budget=Decimal("9"),
            allowed_symbols=[signal_input.symbol],
            allowed_sides=[side],
            max_leverage=Decimal("1"),
            max_margin_per_attempt=Decimal("10"),
            min_liquidation_stop_buffer=Decimal("25"),
            requires_protection=True,
            requires_review=True,
        ),
        execution_enabled=False,
        shadow_mode=True,
        created_at_ms=signal_input.timestamp_ms,
        updated_at_ms=signal_input.timestamp_ms,
        metadata={
            "source": "local_scheduled_observation_shadow_planning_rehearsal",
            "not_live_authority": True,
        },
    )


class _InMemoryObservationRepository:
    def __init__(self) -> None:
        self.records: dict[str, Any] = {}

    async def initialize(self) -> None:
        return None

    async def find_by_observation_identity(
        self,
        *,
        candidate_id: str,
        symbol: str,
        side: str,
        market_bar_timestamp_ms: int,
    ) -> Any | None:
        for record in self.records.values():
            if (
                record.candidate_id == candidate_id
                and record.symbol == symbol
                and record.side == side
                and record.market_bar_timestamp_ms == market_bar_timestamp_ms
            ):
                return record
        return None

    async def record(self, record: Any) -> Any:
        saved = record.model_copy(update={"sink_status": "recorded_in_memory"})
        self.records[saved.record_id] = saved
        return saved


class _InMemoryRuntimeService:
    def __init__(self, runtimes: list[Any]) -> None:
        self._runtimes = {runtime.runtime_instance_id: runtime for runtime in runtimes}

    async def get_runtime(self, runtime_instance_id: str) -> Any:
        runtime = self._runtimes.get(runtime_instance_id)
        if runtime is None:
            raise ValueError(f"runtime not found: {runtime_instance_id}")
        return runtime

    async def list_runtimes(self, *, status: Any = None, limit: int = 100) -> list[Any]:
        values = list(self._runtimes.values())
        if status is not None:
            values = [runtime for runtime in values if runtime.status == status]
        return values[:limit]


class _EmptyActivePositionSource:
    async def list_active(self, *, symbol: str | None = None, limit: int = 100) -> list[Any]:
        return []


class _InMemorySignalEvaluationRepository:
    def __init__(self) -> None:
        self.signal_evaluations: dict[str, Any] = {}
        self.order_candidates: dict[str, Any] = {}

    async def initialize(self) -> None:
        return None

    async def create_signal_evaluation(self, evaluation: Any) -> Any:
        self.signal_evaluations[evaluation.signal_evaluation_id] = evaluation
        return evaluation

    async def get_signal_evaluation(self, signal_evaluation_id: str) -> Any | None:
        return self.signal_evaluations.get(signal_evaluation_id)

    async def list_signal_evaluations(self, **filters: Any) -> list[Any]:
        return _filter_records(list(self.signal_evaluations.values()), filters)

    async def update_signal_evaluation_status(self, evaluation: Any) -> Any:
        self.signal_evaluations[evaluation.signal_evaluation_id] = evaluation
        return evaluation

    async def create_order_candidate(self, candidate: Any) -> Any:
        self.order_candidates[candidate.order_candidate_id] = candidate
        return candidate

    async def get_order_candidate(self, order_candidate_id: str) -> Any | None:
        return self.order_candidates.get(order_candidate_id)

    async def list_order_candidates(self, **filters: Any) -> list[Any]:
        return _filter_records(list(self.order_candidates.values()), filters)

    async def update_order_candidate_status(self, candidate: Any) -> Any:
        self.order_candidates[candidate.order_candidate_id] = candidate
        return candidate


def _filter_records(records: list[Any], filters: dict[str, Any]) -> list[Any]:
    limit = int(filters.pop("limit", 100) or 100)
    filtered = records
    for key, value in filters.items():
        if value is None:
            continue
        filtered = [item for item in filtered if getattr(item, key) == value]
    return filtered[:limit]


async def _async_main(args: argparse.Namespace) -> int:
    report = await build_rehearsal_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"status={report['status']}")
        print(
            "shadow_candidate_created_count="
            f"{report['checks']['shadow_candidate_created_count']}"
        )
        print(
            "forbidden_execution_flags="
            f"{report['checks']['forbidden_execution_flags']}"
        )
    return 0 if report["checks"]["rehearsal_passed"] else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(argv)
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
