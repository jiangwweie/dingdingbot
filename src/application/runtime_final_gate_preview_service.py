"""Runtime-aware FinalGate preview service.

This service performs read-only preflight checks for runtime order candidates.
It never creates executable records or mutates runtime/order state.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_final_gate_preview import (
    RuntimeFinalGateAuditSnapshot,
    RuntimeFinalGateCheck,
    RuntimeFinalGatePreview,
    RuntimeFinalGatePreviewVerdict,
    build_runtime_boundary_snapshot,
    build_runtime_candidate_snapshot,
)
from src.domain.signal_evaluation import OrderCandidate
from src.domain.strategy_runtime import (
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
)


class RuntimeFinalGateRuntimePort(Protocol):
    async def get_runtime(self, runtime_instance_id: str) -> StrategyRuntimeInstance:
        ...


class RuntimeFinalGateCandidatePort(Protocol):
    async def get_order_candidate(self, order_candidate_id: str) -> OrderCandidate:
        ...


class RuntimeFinalGateActivePositionPort(Protocol):
    async def list_active(self, *, symbol: str | None = None, limit: int = 100) -> list[Any]:
        ...


class RuntimeFinalGatePreviewService:
    """Build inspection-only runtime FinalGate previews."""

    def __init__(
        self,
        *,
        runtime_service: RuntimeFinalGateRuntimePort,
        signal_evaluation_service: RuntimeFinalGateCandidatePort,
        active_position_source: RuntimeFinalGateActivePositionPort | None = None,
    ) -> None:
        self._runtime_service = runtime_service
        self._signal_evaluation_service = signal_evaluation_service
        self._active_position_source = active_position_source

    async def preview_order_candidate(
        self,
        *,
        order_candidate_id: str,
        active_positions_count: Optional[int] = None,
        owner_reviewed: bool = False,
        metadata: Optional[dict[str, Any]] = None,
    ) -> RuntimeFinalGatePreview:
        candidate = await self._signal_evaluation_service.get_order_candidate(order_candidate_id)
        if not candidate.runtime_instance_id:
            runtime = None
        else:
            runtime = await self._runtime_service.get_runtime(candidate.runtime_instance_id)
        resolved_active_positions_count = active_positions_count
        resolved_metadata = dict(metadata or {})
        if runtime is not None and active_positions_count is None:
            resolved_active_positions_count = await self._local_active_positions_count(
                runtime.symbol
            )
            resolved_metadata["active_positions_count_source"] = (
                "local_position_projection"
                if resolved_active_positions_count is not None
                else "local_position_projection_unavailable"
            )
        elif active_positions_count is not None:
            resolved_metadata["active_positions_count_source"] = (
                "explicit_query_inspection_fact"
            )
        return self.preview(
            candidate=candidate,
            runtime=runtime,
            active_positions_count=resolved_active_positions_count,
            owner_reviewed=owner_reviewed,
            metadata=resolved_metadata,
        )

    async def _local_active_positions_count(self, symbol: str) -> Optional[int]:
        source = self._active_position_source
        if source is None or not hasattr(source, "list_active"):
            return None
        try:
            positions = await source.list_active(symbol=symbol, limit=100)
        except Exception:
            return None
        return len(list(positions))

    def preview(
        self,
        *,
        candidate: OrderCandidate,
        runtime: Optional[StrategyRuntimeInstance],
        active_positions_count: Optional[int] = None,
        owner_reviewed: bool = False,
        metadata: Optional[dict[str, Any]] = None,
    ) -> RuntimeFinalGatePreview:
        if runtime is None:
            raise ValueError("runtime-aware FinalGate preview requires a runtime instance")

        checks: list[RuntimeFinalGateCheck] = []

        def add_check(
            name: str,
            verdict: RuntimeFinalGatePreviewVerdict,
            code: str,
            message: str = "",
            facts: Optional[dict[str, Any]] = None,
        ) -> None:
            checks.append(
                RuntimeFinalGateCheck(
                    name=name,
                    verdict=verdict,
                    code=code,
                    message=message,
                    facts=facts or {},
                )
            )

        self._check_runtime_status(runtime, add_check)
        self._check_shadow_flags(runtime, candidate, add_check)
        self._check_attempts(runtime, add_check)
        self._check_budget(runtime, candidate, add_check)
        self._check_symbol(runtime, candidate, add_check)
        self._check_side(runtime, candidate, add_check)
        self._check_leverage(runtime, candidate, add_check)
        self._check_active_positions(runtime, active_positions_count, add_check)
        self._check_protection(runtime, candidate, add_check)
        self._check_review(runtime, owner_reviewed, add_check)
        audit_snapshot = self._audit_snapshot(runtime, candidate)
        self._check_audit_ids(audit_snapshot, add_check)

        blockers = [
            check.code
            for check in checks
            if check.verdict == RuntimeFinalGatePreviewVerdict.BLOCK
        ]
        warnings = [
            check.code
            for check in checks
            if check.verdict == RuntimeFinalGatePreviewVerdict.WARN
        ]
        if blockers:
            verdict = RuntimeFinalGatePreviewVerdict.BLOCK
        elif warnings:
            verdict = RuntimeFinalGatePreviewVerdict.WARN
        else:
            verdict = RuntimeFinalGatePreviewVerdict.PASS

        return RuntimeFinalGatePreview(
            verdict=verdict,
            blockers=blockers,
            warnings=warnings,
            checks=checks,
            runtime_boundary_snapshot=build_runtime_boundary_snapshot(runtime),
            candidate_snapshot=build_runtime_candidate_snapshot(candidate),
            audit_id_snapshot=audit_snapshot,
            active_positions_count=active_positions_count,
            owner_reviewed=owner_reviewed,
            metadata={
                "scope": "runtime_final_gate_preview",
                "inspection_only": True,
                **(metadata or {}),
            },
        )

    @staticmethod
    def _check_runtime_status(runtime: StrategyRuntimeInstance, add_check: Any) -> None:
        if runtime.status == StrategyRuntimeInstanceStatus.ACTIVE:
            add_check(
                "runtime_status",
                RuntimeFinalGatePreviewVerdict.PASS,
                "runtime_active",
                facts={"status": runtime.status.value},
            )
            return
        add_check(
            "runtime_status",
            RuntimeFinalGatePreviewVerdict.BLOCK,
            "runtime_not_active",
            facts={"status": runtime.status.value},
        )

    @staticmethod
    def _check_shadow_flags(
        runtime: StrategyRuntimeInstance,
        candidate: OrderCandidate,
        add_check: Any,
    ) -> None:
        unsafe_flags = {
            "runtime_shadow_mode": runtime.shadow_mode,
            "runtime_execution_enabled": runtime.execution_enabled,
            "candidate_shadow_mode": candidate.shadow_mode,
            "candidate_execution_enabled": candidate.execution_enabled,
            "candidate_executable": candidate.candidate_executable,
            "candidate_not_order": candidate.not_order,
            "candidate_not_execution_intent": candidate.not_execution_intent,
        }
        safe = (
            runtime.shadow_mode
            and not runtime.execution_enabled
            and candidate.shadow_mode
            and not candidate.execution_enabled
            and not candidate.candidate_executable
            and candidate.not_order
            and candidate.not_execution_intent
        )
        add_check(
            "shadow_and_execution_flags",
            RuntimeFinalGatePreviewVerdict.PASS if safe else RuntimeFinalGatePreviewVerdict.BLOCK,
            "shadow_flags_safe" if safe else "shadow_flags_unsafe",
            facts=unsafe_flags,
        )

    @staticmethod
    def _check_attempts(runtime: StrategyRuntimeInstance, add_check: Any) -> None:
        remaining = runtime.attempts_remaining
        add_check(
            "attempts_remaining",
            RuntimeFinalGatePreviewVerdict.PASS if remaining > 0 else RuntimeFinalGatePreviewVerdict.BLOCK,
            "attempts_available" if remaining > 0 else "attempts_exhausted",
            facts={
                "max_attempts": runtime.boundary.max_attempts,
                "attempts_used": runtime.boundary.attempts_used,
                "attempts_remaining": remaining,
            },
        )

    @staticmethod
    def _check_budget(
        runtime: StrategyRuntimeInstance,
        candidate: OrderCandidate,
        add_check: Any,
    ) -> None:
        intended = candidate.intended_notional
        remaining = runtime.budget_remaining
        per_attempt = runtime.boundary.max_notional_per_attempt
        if intended is None:
            add_check(
                "budget_remaining",
                RuntimeFinalGatePreviewVerdict.WARN,
                "candidate_notional_missing",
            )
            return
        if per_attempt is not None and intended > per_attempt:
            add_check(
                "budget_remaining",
                RuntimeFinalGatePreviewVerdict.BLOCK,
                "candidate_exceeds_max_notional_per_attempt",
                facts={"intended_notional": intended, "max_notional_per_attempt": per_attempt},
            )
            return
        if remaining is not None and intended > remaining:
            add_check(
                "budget_remaining",
                RuntimeFinalGatePreviewVerdict.BLOCK,
                "candidate_exceeds_budget_remaining",
                facts={"intended_notional": intended, "budget_remaining": remaining},
            )
            return
        add_check(
            "budget_remaining",
            (
                RuntimeFinalGatePreviewVerdict.PASS
                if remaining is not None
                else RuntimeFinalGatePreviewVerdict.WARN
            ),
            "budget_available" if remaining is not None else "runtime_budget_unbounded",
            facts={"intended_notional": intended, "budget_remaining": remaining},
        )

    @staticmethod
    def _check_symbol(
        runtime: StrategyRuntimeInstance,
        candidate: OrderCandidate,
        add_check: Any,
    ) -> None:
        allowed = list(runtime.boundary.allowed_symbols)
        matches = candidate.symbol == runtime.symbol and (not allowed or candidate.symbol in allowed)
        add_check(
            "allowed_symbol",
            RuntimeFinalGatePreviewVerdict.PASS if matches else RuntimeFinalGatePreviewVerdict.BLOCK,
            "symbol_allowed" if matches else "symbol_outside_runtime_boundary",
            facts={
                "candidate_symbol": candidate.symbol,
                "runtime_symbol": runtime.symbol,
                "allowed_symbols": allowed,
            },
        )

    @staticmethod
    def _check_side(
        runtime: StrategyRuntimeInstance,
        candidate: OrderCandidate,
        add_check: Any,
    ) -> None:
        candidate_side = candidate.side.lower()
        runtime_side = runtime.side.lower()
        allowed = [side.lower() for side in runtime.boundary.allowed_sides]
        matches = candidate_side == runtime_side and (not allowed or candidate_side in allowed)
        add_check(
            "allowed_side",
            RuntimeFinalGatePreviewVerdict.PASS if matches else RuntimeFinalGatePreviewVerdict.BLOCK,
            "side_allowed" if matches else "side_outside_runtime_boundary",
            facts={"candidate_side": candidate.side, "runtime_side": runtime.side, "allowed_sides": allowed},
        )

    @staticmethod
    def _check_leverage(
        runtime: StrategyRuntimeInstance,
        candidate: OrderCandidate,
        add_check: Any,
    ) -> None:
        max_leverage = runtime.boundary.max_leverage
        leverage = candidate.risk_preview.leverage
        if max_leverage is None:
            add_check(
                "max_leverage",
                RuntimeFinalGatePreviewVerdict.WARN,
                "runtime_max_leverage_missing",
            )
            return
        if leverage is None:
            add_check(
                "max_leverage",
                RuntimeFinalGatePreviewVerdict.WARN,
                "candidate_leverage_missing",
                facts={"max_leverage": max_leverage},
            )
            return
        add_check(
            "max_leverage",
            (
                RuntimeFinalGatePreviewVerdict.PASS
                if leverage <= max_leverage
                else RuntimeFinalGatePreviewVerdict.BLOCK
            ),
            "leverage_allowed" if leverage <= max_leverage else "candidate_exceeds_max_leverage",
            facts={"candidate_leverage": leverage, "max_leverage": max_leverage},
        )

    @staticmethod
    def _check_active_positions(
        runtime: StrategyRuntimeInstance,
        active_positions_count: Optional[int],
        add_check: Any,
    ) -> None:
        max_active = runtime.boundary.max_active_positions
        if active_positions_count is None:
            add_check(
                "active_positions_count",
                RuntimeFinalGatePreviewVerdict.BLOCK,
                "active_positions_count_not_available",
                facts={"max_active_positions": max_active},
            )
            return
        allowed = active_positions_count < max_active
        add_check(
            "active_positions_count",
            RuntimeFinalGatePreviewVerdict.PASS if allowed else RuntimeFinalGatePreviewVerdict.BLOCK,
            "active_position_capacity_available" if allowed else "active_position_capacity_exhausted",
            facts={
                "active_positions_count": active_positions_count,
                "max_active_positions": max_active,
            },
        )

    @staticmethod
    def _check_protection(
        runtime: StrategyRuntimeInstance,
        candidate: OrderCandidate,
        add_check: Any,
    ) -> None:
        protection = candidate.protection_preview
        reference_present = bool(
            protection.stop_reference
            or protection.stop_price_reference is not None
            or protection.take_profit_references
        )
        if not runtime.boundary.requires_protection:
            add_check(
                "protection_requirement",
                RuntimeFinalGatePreviewVerdict.PASS,
                "protection_not_required",
            )
            return
        if not protection.requires_protection:
            add_check(
                "protection_requirement",
                RuntimeFinalGatePreviewVerdict.BLOCK,
                "candidate_protection_disabled",
            )
            return
        add_check(
            "protection_requirement",
            (
                RuntimeFinalGatePreviewVerdict.PASS
                if reference_present
                else RuntimeFinalGatePreviewVerdict.BLOCK
            ),
            "protection_reference_available" if reference_present else "protection_reference_missing",
        )

    @staticmethod
    def _check_review(
        runtime: StrategyRuntimeInstance,
        owner_reviewed: bool,
        add_check: Any,
    ) -> None:
        review_required = runtime.boundary.requires_review
        if not review_required:
            add_check(
                "review_requirement",
                RuntimeFinalGatePreviewVerdict.PASS,
                "review_not_required",
            )
            return
        add_check(
            "review_requirement",
            RuntimeFinalGatePreviewVerdict.PASS if owner_reviewed else RuntimeFinalGatePreviewVerdict.BLOCK,
            "owner_review_confirmed" if owner_reviewed else "owner_review_required",
        )

    @staticmethod
    def _audit_snapshot(
        runtime: StrategyRuntimeInstance,
        candidate: OrderCandidate,
    ) -> RuntimeFinalGateAuditSnapshot:
        ids = BrcSemanticIds(
            runtime_instance_id=candidate.runtime_instance_id,
            trial_binding_id=candidate.trial_binding_id,
            strategy_family_id=candidate.strategy_family_id,
            strategy_family_version_id=candidate.strategy_family_version_id,
            signal_evaluation_id=candidate.signal_evaluation_id,
            order_candidate_id=candidate.order_candidate_id,
        )
        values = ids.model_dump()
        missing = [key for key, value in values.items() if value in {None, ""}]
        mismatches: list[str] = []
        for attr in [
            "runtime_instance_id",
            "trial_binding_id",
            "strategy_family_id",
            "strategy_family_version_id",
        ]:
            if getattr(candidate, attr) != getattr(runtime, attr):
                mismatches.append(attr)
        return RuntimeFinalGateAuditSnapshot(
            ids=ids,
            complete=not missing and not mismatches,
            missing=missing,
            mismatches=mismatches,
        )

    @staticmethod
    def _check_audit_ids(snapshot: RuntimeFinalGateAuditSnapshot, add_check: Any) -> None:
        add_check(
            "audit_id_completeness",
            (
                RuntimeFinalGatePreviewVerdict.PASS
                if snapshot.complete
                else RuntimeFinalGatePreviewVerdict.BLOCK
            ),
            "audit_ids_complete" if snapshot.complete else "audit_ids_incomplete_or_mismatched",
            facts={
                "missing": list(snapshot.missing),
                "mismatches": list(snapshot.mismatches),
            },
        )
