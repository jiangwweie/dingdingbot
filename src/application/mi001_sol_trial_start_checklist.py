"""Read-only MI-001 SOL trial-start checklist generation.

This module derives readiness from PG-backed registration records plus injected
cached account/safety facts. It does not start trials, grant execution
permission, create orders, create execution intents, call exchanges, or mutate
runtime state.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Literal, Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.domain.brc_admission import (
    AdmissionDecision,
    AdmissionEvidencePacket,
    AdmissionExecutionMode,
    AdmissionRequest,
    AdmissionTrialBinding,
    AdmissionTrialBindingStatus,
    OwnerRiskAcceptance,
    StrategyFamilyVersion,
    TrialConstraintSnapshot,
)
from src.domain.mi001_sol_pg_registration import (
    MI001_CANDIDATE_ID,
    MI001_FAMILY_ID,
    MI001_PLAYBOOK_ID,
    MI001_SIDE,
    MI001_SYMBOL,
    MI001_VERSION_ID,
)
from src.domain.strategy_family_registry import (
    StrategyFamilyMetadata,
    StrategyFamilyPlaybookMetadata,
)
from src.application.trial_readiness_account_facts import (
    AccountFactsReconciliationStatus,
    AccountFactsSourceType,
    TrialReadinessAccountFacts,
    TrialReadinessAccountFactsSource,
)


class TrialStartChecklistModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChecklistStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"
    MISSING = "missing"
    NOT_CHECKED = "not_checked"
    UNSAFE_TO_READ = "unsafe_to_read"


class TrialStartChecklistVerdict(str, Enum):
    BLOCKED_OWNER_TRIAL_START_APPROVAL_REQUIRED = (
        "blocked_owner_trial_start_approval_required"
    )
    BLOCKED_FRESH_ACCOUNT_FACTS_REQUIRED = "blocked_fresh_account_facts_required"
    BLOCKED_OPERATION_LAYER_FACTS_REQUIRED = "blocked_operation_layer_facts_required"
    BLOCKED_KILL_SWITCH_STATE_REQUIRED = "blocked_kill_switch_state_required"
    BLOCKED_PG_REGISTRATION_MISSING = "blocked_pg_registration_missing"
    READY_FOR_OWNER_TRIAL_START_APPROVAL = "ready_for_owner_trial_start_approval"
    READY_FOR_TRIAL_START_AFTER_OWNER_APPROVAL = "ready_for_trial_start_after_owner_approval"


class ChecklistRow(TrialStartChecklistModel):
    check: str = Field(min_length=1, max_length=256)
    status: ChecklistStatus
    evidence: str = Field(default="", max_length=2048)
    blocking: bool = False
    notes: str = Field(default="", max_length=2048)


class ScopeCheckRow(TrialStartChecklistModel):
    check: str = Field(min_length=1, max_length=256)
    expected: str = Field(default="", max_length=1024)
    actual: str = Field(default="", max_length=1024)
    status: ChecklistStatus
    blocking: bool = False
    notes: str = Field(default="", max_length=2048)


class AccountFactsCheckRow(TrialStartChecklistModel):
    check: str = Field(min_length=1, max_length=256)
    status: ChecklistStatus
    source: str = Field(default="", max_length=512)
    timestamp_ms: Optional[int] = None
    blocking: bool = False
    notes: str = Field(default="", max_length=2048)


class CachedAccountFacts(TrialStartChecklistModel):
    available: bool = False
    wallet_equity: Optional[Decimal] = None
    available_margin: Optional[Decimal] = None
    timestamp_ms: Optional[int] = None
    freshness: Literal["fresh", "stale", "missing", "unknown"] = "missing"
    source: str = "not_provided"
    read_method: str = "not_checked"
    read_only: bool = True
    reconciliation_status: Literal["clean", "mismatch", "not_available", "unknown"] = "unknown"
    notes: str = ""


class OperationLayerFacts(TrialStartChecklistModel):
    available: bool = False
    gate_available: bool = False
    notional_cap_available: bool = False
    notional_cap: Optional[Decimal] = None
    evidence_logging_available: bool = False
    no_active_trial_position: Optional[bool] = None
    startup_guard_available: bool = False
    startup_guard_armed: Optional[bool] = None
    source: str = "not_provided"
    notes: str = ""


class KillSwitchFacts(TrialStartChecklistModel):
    available: bool = False
    active: Optional[bool] = None
    source: str = "not_provided"
    updated_at_ms: Optional[int] = None
    notes: str = ""


class TrialStartChecklistInputs(TrialStartChecklistModel):
    generated_at_ms: int
    account_facts: Optional[CachedAccountFacts] = None
    operation_layer_facts: Optional[OperationLayerFacts] = None
    kill_switch_facts: Optional[KillSwitchFacts] = None


class CapitalReadiness(TrialStartChecklistModel):
    status: ChecklistStatus
    current_dedicated_subaccount_equity: Optional[Decimal] = None
    available_margin: Optional[Decimal] = None
    max_leverage: int = 5
    computed_max_notional_candidate: Optional[Decimal] = None
    max_total_loss_rule: str = "current_dedicated_subaccount_equity"
    evidence: str = Field(default="", max_length=2048)
    blocking: bool = False


class TrialStartChecklist(TrialStartChecklistModel):
    checklist_id: str
    candidate_id: str = MI001_CANDIDATE_ID
    strategy_family_id: str = MI001_FAMILY_ID
    symbol: str = MI001_SYMBOL
    side: str = MI001_SIDE
    generated_at_ms: int
    source_inputs: dict[str, str]
    pg_registration_checks: list[ChecklistRow]
    scope_checks: list[ScopeCheckRow]
    account_facts_checks: list[AccountFactsCheckRow]
    capital_readiness: CapitalReadiness
    operation_layer_safety_checks: list[ChecklistRow]
    owner_trial_start_approval_checks: list[ChecklistRow]
    final_verdict: TrialStartChecklistVerdict
    blockers: list[str] = Field(default_factory=list)
    non_permissions: list[str] = Field(default_factory=list)


class StrategyFamilyRegistryReadRepositoryPort(Protocol):
    async def get_family_metadata_version(
        self,
        family_id: str,
        version_id: str,
    ) -> Optional[StrategyFamilyMetadata]: ...

    async def get_playbook_metadata(
        self,
        playbook_id: str,
    ) -> Optional[StrategyFamilyPlaybookMetadata]: ...


class BrcAdmissionReadRepositoryPort(Protocol):
    async def get_strategy_family_version(
        self,
        strategy_family_version_id: str,
    ) -> Optional[StrategyFamilyVersion]: ...

    async def get_evidence_packet(
        self,
        evidence_packet_id: str,
    ) -> Optional[AdmissionEvidencePacket]: ...

    async def get_admission_request(
        self,
        admission_request_id: str,
    ) -> Optional[AdmissionRequest]: ...

    async def get_trial_constraint_snapshot(
        self,
        trial_constraint_snapshot_id: str,
    ) -> Optional[TrialConstraintSnapshot]: ...

    async def get_admission_decision(
        self,
        admission_decision_id: str,
    ) -> Optional[AdmissionDecision]: ...

    async def get_owner_risk_acceptance(
        self,
        owner_risk_acceptance_id: str,
    ) -> Optional[OwnerRiskAcceptance]: ...

    async def get_admission_trial_binding(
        self,
        binding_id: str,
    ) -> Optional[AdmissionTrialBinding]: ...


class Mi001SolTrialStartChecklistGenerator:
    """Build a no-side-effect readiness checklist for MI-001 SOL long."""

    def __init__(
        self,
        *,
        registry_repository: StrategyFamilyRegistryReadRepositoryPort,
        admission_repository: BrcAdmissionReadRepositoryPort,
    ) -> None:
        self._registry_repository = registry_repository
        self._admission_repository = admission_repository

    async def generate(
        self,
        inputs: TrialStartChecklistInputs,
    ) -> TrialStartChecklist:
        family = await self._registry_repository.get_family_metadata_version(
            MI001_FAMILY_ID,
            MI001_VERSION_ID,
        )
        playbook = await self._registry_repository.get_playbook_metadata(MI001_PLAYBOOK_ID)
        version = await self._admission_repository.get_strategy_family_version(
            f"{MI001_CANDIDATE_ID}-admission-v1"
        )
        evidence = await self._admission_repository.get_evidence_packet(
            f"{MI001_CANDIDATE_ID}-broad-smoke-evidence-v1"
        )
        request = await self._admission_repository.get_admission_request(
            f"{MI001_CANDIDATE_ID}-admission-request-v1"
        )
        constraint = await self._admission_repository.get_trial_constraint_snapshot(
            f"{MI001_CANDIDATE_ID}-trial-constraints-v1"
        )
        decision = await self._admission_repository.get_admission_decision(
            f"{MI001_CANDIDATE_ID}-admission-decision-v1"
        )
        acceptance = await self._admission_repository.get_owner_risk_acceptance(
            f"{MI001_CANDIDATE_ID}-owner-risk-acceptance-v1"
        )
        binding = await self._admission_repository.get_admission_trial_binding(
            f"{MI001_CANDIDATE_ID}-planned-binding-v1"
        )

        pg_checks = _pg_checks(
            family=family,
            playbook=playbook,
            version=version,
            evidence=evidence,
            request=request,
            constraint=constraint,
            decision=decision,
            acceptance=acceptance,
            binding=binding,
        )
        scope_checks = _scope_checks(
            version=version,
            constraint=constraint,
            decision=decision,
            binding=binding,
        )
        account_checks = _account_checks(inputs.account_facts)
        capital_readiness = _capital_readiness(
            account_facts=inputs.account_facts,
            operation_layer_facts=inputs.operation_layer_facts,
        )
        safety_checks = _operation_layer_safety_checks(
            operation_layer_facts=inputs.operation_layer_facts,
            kill_switch_facts=inputs.kill_switch_facts,
        )
        owner_checks = _owner_trial_start_checks(
            decision=decision,
            acceptance=acceptance,
        )
        blockers = _blockers(
            pg_checks=pg_checks,
            scope_checks=scope_checks,
            account_checks=account_checks,
            capital_readiness=capital_readiness,
            safety_checks=safety_checks,
            owner_checks=owner_checks,
        )
        return TrialStartChecklist(
            checklist_id=f"{MI001_CANDIDATE_ID}-trial-start-checklist",
            generated_at_ms=inputs.generated_at_ms,
            source_inputs={
                "pg_registration_records": "available" if _all_pass(pg_checks) else "blocked",
                "cached_account_facts": _input_status(inputs.account_facts),
                "operation_layer_facts": _input_status(inputs.operation_layer_facts),
                "kill_switch_facts": _input_status(inputs.kill_switch_facts),
                "owner_trial_start_approval": _owner_input_status(owner_checks),
            },
            pg_registration_checks=pg_checks,
            scope_checks=scope_checks,
            account_facts_checks=account_checks,
            capital_readiness=capital_readiness,
            operation_layer_safety_checks=safety_checks,
            owner_trial_start_approval_checks=owner_checks,
            final_verdict=_final_verdict(
                pg_checks=pg_checks,
                account_checks=account_checks,
                safety_checks=safety_checks,
                owner_checks=owner_checks,
            ),
            blockers=blockers,
            non_permissions=[
                "execution permission",
                "order permission",
                "runtime start",
                "exchange API permission",
                "leverage change permission",
                "symbol/side expansion",
                "automatic trial start",
            ],
        )

    async def generate_with_account_facts_source(
        self,
        *,
        generated_at_ms: int,
        account_facts_source: TrialReadinessAccountFactsSource,
        operation_layer_facts: Optional[OperationLayerFacts] = None,
        kill_switch_facts: Optional[KillSwitchFacts] = None,
    ) -> TrialStartChecklist:
        account_facts = await account_facts_source.read_trial_readiness_account_facts(
            candidate_id=MI001_CANDIDATE_ID,
            symbol=MI001_SYMBOL,
            side=MI001_SIDE,
            generated_at_ms=generated_at_ms,
        )
        return await self.generate(
            TrialStartChecklistInputs(
                generated_at_ms=generated_at_ms,
                account_facts=_cached_account_facts_from_readiness(account_facts),
                operation_layer_facts=operation_layer_facts,
                kill_switch_facts=kill_switch_facts,
            )
        )


def _pg_checks(
    *,
    family: Optional[StrategyFamilyMetadata],
    playbook: Optional[StrategyFamilyPlaybookMetadata],
    version: Optional[StrategyFamilyVersion],
    evidence: Optional[AdmissionEvidencePacket],
    request: Optional[AdmissionRequest],
    constraint: Optional[TrialConstraintSnapshot],
    decision: Optional[AdmissionDecision],
    acceptance: Optional[OwnerRiskAcceptance],
    binding: Optional[AdmissionTrialBinding],
) -> list[ChecklistRow]:
    return [
        _check("MI-001 strategy family record exists", family is not None, "MI-001:MI-001-smoke-v0"),
        _check("MI-001 playbook record exists", playbook is not None, MI001_PLAYBOOK_ID),
        _check("MI-001-SOL-LONG candidate/admission version exists", version is not None, f"{MI001_CANDIDATE_ID}-admission-v1"),
        _check("broad smoke evidence packet exists", evidence is not None, f"{MI001_CANDIDATE_ID}-broad-smoke-evidence-v1"),
        _check("admission request exists", request is not None, f"{MI001_CANDIDATE_ID}-admission-request-v1"),
        _check("Owner plan-preparation approval exists", acceptance is not None, f"{MI001_CANDIDATE_ID}-owner-risk-acceptance-v1"),
        _check("trial constraint snapshot exists", constraint is not None, f"{MI001_CANDIDATE_ID}-trial-constraints-v1"),
        _check("planned binding exists", binding is not None, f"{MI001_CANDIDATE_ID}-planned-binding-v1"),
        _check(
            "binding status is planned or binding_reserved",
            binding is not None
            and binding.binding_status
            in {AdmissionTrialBindingStatus.PLANNED, AdmissionTrialBindingStatus.BINDING_RESERVED},
            binding.binding_status.value if binding is not None else "missing",
        ),
        _check(
            "binding has no campaign_id",
            binding is not None and binding.campaign_id is None,
            str(binding.campaign_id) if binding is not None else "missing",
        ),
        _check(
            "binding has no runtime_carrier_id",
            binding is not None and binding.runtime_carrier_id is None,
            str(binding.runtime_carrier_id) if binding is not None else "missing",
        ),
        _check(
            "Owner trial-start approval is false or absent",
            decision is not None
            and decision.risk_intent_json.get("owner_approved_trial_start") is not True,
            str(decision.risk_intent_json.get("owner_approved_trial_start")) if decision is not None else "missing",
        ),
        _check(
            "automatic execution approval is false",
            decision is not None
            and decision.risk_intent_json.get("automatic_execution_approved") is False,
            str(decision.risk_intent_json.get("automatic_execution_approved")) if decision is not None else "missing",
        ),
        _check(
            "no execution permission record created by this flow",
            decision is not None
            and decision.execution_mode == AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY,
            decision.execution_mode.value if decision is not None else "missing",
        ),
    ]


def _scope_checks(
    *,
    version: Optional[StrategyFamilyVersion],
    constraint: Optional[TrialConstraintSnapshot],
    decision: Optional[AdmissionDecision],
    binding: Optional[AdmissionTrialBinding],
) -> list[ScopeCheckRow]:
    constraints = constraint.constraints_json if constraint is not None else {}
    return [
        _scope("candidate", MI001_FAMILY_ID, constraints.get("allowed_candidate")),
        _scope("symbol", MI001_SYMBOL, constraints.get("allowed_symbol")),
        _scope("side", MI001_SIDE, constraints.get("allowed_side")),
        _scope("allowed_candidate only", MI001_FAMILY_ID, constraints.get("allowed_candidate")),
        _scope("allowed_symbol only", [MI001_SYMBOL], constraints.get("allowed_symbols")),
        _scope("allowed_side only", MI001_SIDE, constraints.get("allowed_side")),
        _scope("max_attempts", "3", constraints.get("max_attempts")),
        _scope("max_leverage", "5", constraints.get("max_leverage")),
        _scope("no symbol expansion", "true", constraints.get("no_symbol_expansion")),
        _scope("no side expansion", "true", constraints.get("no_side_expansion")),
        _scope("no leverage expansion above 5x", "true", constraints.get("no_leverage_expansion_above_5x")),
        _scope("no transfer", "true", constraints.get("no_transfer")),
        _scope("no withdrawal", "true", constraints.get("no_withdrawal")),
        _scope("no auto top-up", "true", constraints.get("no_auto_top_up")),
        _scope(
            "required_execution_capabilities empty",
            "[]",
            version.required_execution_capabilities if version is not None else None,
        ),
        _scope(
            "binding remains non-runtime",
            "campaign_id=null,runtime_carrier_id=null",
            (
                "campaign_id=null,runtime_carrier_id=null"
                if binding is not None
                and binding.campaign_id is None
                and binding.runtime_carrier_id is None
                else (
                    f"campaign_id={binding.campaign_id},runtime_carrier_id={binding.runtime_carrier_id}"
                )
                if binding is not None
                else None
            ),
        ),
        _scope(
            "decision execution mode",
            AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY.value,
            decision.execution_mode.value if decision is not None else None,
        ),
    ]


def _account_checks(account_facts: Optional[CachedAccountFacts]) -> list[AccountFactsCheckRow]:
    if account_facts is None:
        return [
            _account(
                "cached AccountSnapshot exists",
                ChecklistStatus.MISSING,
                "not_provided",
                None,
                True,
                "No cached/local/PG account facts provider was supplied.",
            ),
            _account(
                "wallet_equity/account_equity available",
                ChecklistStatus.BLOCKED,
                "not_provided",
                None,
                True,
                "Cannot derive trial risk capital without cached account equity.",
            ),
            _account(
                "available_margin available",
                ChecklistStatus.BLOCKED,
                "not_provided",
                None,
                True,
                "Cannot compute readiness max_notional candidate without cached available margin.",
            ),
            _account(
                "freshness acceptable",
                ChecklistStatus.BLOCKED,
                "not_provided",
                None,
                True,
                "Freshness cannot be evaluated without a timestamped cached AccountSnapshot.",
            ),
            _account(
                "read-only source",
                ChecklistStatus.NOT_CHECKED,
                "not_provided",
                None,
                True,
                "No safe cache-only account facts read path was invoked.",
            ),
            _account(
                "reconciliation acceptable",
                ChecklistStatus.NOT_CHECKED,
                "not_provided",
                None,
                True,
                "No account reconciliation fact was available.",
            ),
        ]
    if account_facts.read_method == "unsafe_to_read":
        note = account_facts.notes or (
            "Account facts source was intentionally not read because the only visible "
            "path may touch runtime/exchange gateway state."
        )
        return [
            _account("cached AccountSnapshot exists", ChecklistStatus.UNSAFE_TO_READ, account_facts.source, account_facts.timestamp_ms, True, note),
            _account("wallet_equity/account_equity available", ChecklistStatus.BLOCKED, account_facts.source, account_facts.timestamp_ms, True, note),
            _account("available_margin available", ChecklistStatus.BLOCKED, account_facts.source, account_facts.timestamp_ms, True, note),
            _account("freshness acceptable", ChecklistStatus.BLOCKED, account_facts.source, account_facts.timestamp_ms, True, note),
            _account("read-only source", ChecklistStatus.UNSAFE_TO_READ, account_facts.read_method, account_facts.timestamp_ms, True, note),
            _account("reconciliation acceptable", ChecklistStatus.BLOCKED, account_facts.source, account_facts.timestamp_ms, True, note),
        ]
    reconciliation_ok = account_facts.reconciliation_status in {"clean"}
    return [
        _account("cached AccountSnapshot exists", ChecklistStatus.PASS if account_facts.available else ChecklistStatus.MISSING, account_facts.source, account_facts.timestamp_ms, not account_facts.available, account_facts.notes),
        _account("wallet_equity/account_equity available", ChecklistStatus.PASS if account_facts.wallet_equity is not None else ChecklistStatus.BLOCKED, account_facts.source, account_facts.timestamp_ms, account_facts.wallet_equity is None, account_facts.notes),
        _account("available_margin available", ChecklistStatus.PASS if account_facts.available_margin is not None else ChecklistStatus.BLOCKED, account_facts.source, account_facts.timestamp_ms, account_facts.available_margin is None, account_facts.notes),
        _account("freshness acceptable", ChecklistStatus.PASS if account_facts.freshness == "fresh" else ChecklistStatus.BLOCKED, account_facts.source, account_facts.timestamp_ms, account_facts.freshness != "fresh", account_facts.notes),
        _account("read-only source", ChecklistStatus.PASS if account_facts.read_only else ChecklistStatus.BLOCKED, account_facts.read_method, account_facts.timestamp_ms, not account_facts.read_only, account_facts.notes),
        _account("reconciliation acceptable", ChecklistStatus.PASS if reconciliation_ok else ChecklistStatus.BLOCKED, account_facts.source, account_facts.timestamp_ms, not reconciliation_ok, account_facts.notes),
    ]


def _capital_readiness(
    *,
    account_facts: Optional[CachedAccountFacts],
    operation_layer_facts: Optional[OperationLayerFacts],
) -> CapitalReadiness:
    if (
        account_facts is None
        or not account_facts.available
        or account_facts.wallet_equity is None
        or account_facts.available_margin is None
        or account_facts.freshness != "fresh"
        or account_facts.reconciliation_status != "clean"
    ):
        return CapitalReadiness(
            status=ChecklistStatus.BLOCKED,
            evidence="fresh cached account equity and available margin are required",
            blocking=True,
        )
    candidates = [account_facts.wallet_equity * Decimal("5"), account_facts.available_margin * Decimal("5")]
    if operation_layer_facts is not None and operation_layer_facts.notional_cap is not None:
        candidates.append(operation_layer_facts.notional_cap)
    return CapitalReadiness(
        status=ChecklistStatus.PASS,
        current_dedicated_subaccount_equity=account_facts.wallet_equity,
        available_margin=account_facts.available_margin,
        max_leverage=5,
        computed_max_notional_candidate=min(candidates),
        evidence="readiness calculation only; not persisted as execution config",
        blocking=False,
    )


def _operation_layer_safety_checks(
    *,
    operation_layer_facts: Optional[OperationLayerFacts],
    kill_switch_facts: Optional[KillSwitchFacts],
) -> list[ChecklistRow]:
    if operation_layer_facts is None:
        missing_note = "No safe Operation Layer facts provider was supplied; runtime preflight was not invoked."
        operation = [
            ChecklistRow(check="Operation Layer gate available", status=ChecklistStatus.MISSING, evidence="not_provided", blocking=True, notes=missing_note),
            ChecklistRow(check="Operation Layer notional cap available", status=ChecklistStatus.MISSING, evidence="not_provided", blocking=True, notes=missing_note),
            ChecklistRow(check="startup guard state available", status=ChecklistStatus.NOT_CHECKED, evidence="not_provided", blocking=True, notes=missing_note),
            ChecklistRow(check="evidence logging available", status=ChecklistStatus.MISSING, evidence="not_provided", blocking=True, notes=missing_note),
            ChecklistRow(check="no active trial position", status=ChecklistStatus.NOT_CHECKED, evidence="not_provided", blocking=True, notes=missing_note),
        ]
    else:
        operation = [
            _safety("Operation Layer gate available", operation_layer_facts.gate_available, operation_layer_facts.source, operation_layer_facts.notes),
            _safety("Operation Layer notional cap available", operation_layer_facts.notional_cap_available, str(operation_layer_facts.notional_cap), operation_layer_facts.notes),
            _safety("startup guard state available", operation_layer_facts.startup_guard_available, str(operation_layer_facts.startup_guard_armed), operation_layer_facts.notes),
            _safety("evidence logging available", operation_layer_facts.evidence_logging_available, operation_layer_facts.source, operation_layer_facts.notes),
            _safety("no active trial position", operation_layer_facts.no_active_trial_position is True, str(operation_layer_facts.no_active_trial_position), operation_layer_facts.notes),
        ]

    if kill_switch_facts is None:
        operation.append(
            ChecklistRow(check="kill switch state available", status=ChecklistStatus.MISSING, evidence="not_provided", blocking=True, notes="PG GKS state was not supplied.")
        )
    else:
        notes = kill_switch_facts.notes or _kill_switch_interpretation(kill_switch_facts)
        operation.append(
            _safety(
                "kill switch state available",
                kill_switch_facts.available,
                f"active={kill_switch_facts.active},source={kill_switch_facts.source}",
                notes,
            )
        )
    return operation


def _owner_trial_start_checks(
    *,
    decision: Optional[AdmissionDecision],
    acceptance: Optional[OwnerRiskAcceptance],
) -> list[ChecklistRow]:
    plan_preparation_approved = (
        acceptance is not None
        and acceptance.risk_disclosure_snapshot_json.get(
            "owner_approved_bounded_trial_plan_preparation"
        )
        is True
    )
    trial_start_approved = (
        decision is not None
        and decision.risk_intent_json.get("owner_approved_trial_start") is True
    )
    return [
        _check(
            "Owner plan preparation approved",
            plan_preparation_approved,
            str(plan_preparation_approved),
            blocking=False,
        ),
        ChecklistRow(
            check="Owner trial start approved",
            status=ChecklistStatus.PASS if trial_start_approved else ChecklistStatus.BLOCKED,
            evidence=str(trial_start_approved),
            blocking=not trial_start_approved,
        ),
    ]


def _final_verdict(
    *,
    pg_checks: list[ChecklistRow],
    account_checks: list[AccountFactsCheckRow],
    safety_checks: list[ChecklistRow],
    owner_checks: list[ChecklistRow],
) -> TrialStartChecklistVerdict:
    if any(row.blocking for row in pg_checks):
        return TrialStartChecklistVerdict.BLOCKED_PG_REGISTRATION_MISSING
    if any(row.blocking for row in account_checks):
        return TrialStartChecklistVerdict.BLOCKED_FRESH_ACCOUNT_FACTS_REQUIRED
    if any(
        row.blocking
        for row in safety_checks
        if "kill switch" not in row.check.lower()
    ):
        return TrialStartChecklistVerdict.BLOCKED_OPERATION_LAYER_FACTS_REQUIRED
    if any(row.blocking for row in safety_checks if "kill switch" in row.check.lower()):
        return TrialStartChecklistVerdict.BLOCKED_KILL_SWITCH_STATE_REQUIRED
    if any(row.blocking for row in owner_checks):
        return TrialStartChecklistVerdict.BLOCKED_OWNER_TRIAL_START_APPROVAL_REQUIRED
    return TrialStartChecklistVerdict.READY_FOR_OWNER_TRIAL_START_APPROVAL


def _blockers(
    *,
    pg_checks: list[ChecklistRow],
    scope_checks: list[ScopeCheckRow],
    account_checks: list[AccountFactsCheckRow],
    capital_readiness: CapitalReadiness,
    safety_checks: list[ChecklistRow],
    owner_checks: list[ChecklistRow],
) -> list[str]:
    blockers: list[str] = []
    blockers.extend(row.check for row in pg_checks if row.blocking)
    blockers.extend(row.check for row in scope_checks if row.blocking)
    blockers.extend(row.check for row in account_checks if row.blocking)
    if capital_readiness.blocking:
        blockers.append("capital readiness calculation unavailable")
    blockers.extend(row.check for row in safety_checks if row.blocking)
    blockers.extend(row.check for row in owner_checks if row.blocking)
    return blockers


def _check(check: str, passed: bool, evidence: str, *, blocking: bool = True) -> ChecklistRow:
    return ChecklistRow(
        check=check,
        status=ChecklistStatus.PASS if passed else ChecklistStatus.BLOCKED,
        evidence=evidence,
        blocking=(not passed and blocking),
    )


def _scope(check: str, expected: object, actual: object) -> ScopeCheckRow:
    expected_text = _format_value(expected)
    actual_text = _format_value(actual)
    passed = actual_text == expected_text
    return ScopeCheckRow(
        check=check,
        expected=expected_text,
        actual=actual_text,
        status=ChecklistStatus.PASS if passed else ChecklistStatus.BLOCKED,
        blocking=not passed,
    )


def _account(
    check: str,
    status: ChecklistStatus,
    source: str,
    timestamp_ms: Optional[int],
    blocking: bool,
    notes: str = "",
) -> AccountFactsCheckRow:
    return AccountFactsCheckRow(
        check=check,
        status=status,
        source=source,
        timestamp_ms=timestamp_ms,
        blocking=blocking,
        notes=notes,
    )


def _cached_account_facts_from_readiness(
    facts: TrialReadinessAccountFacts,
) -> CachedAccountFacts:
    blockers = facts.readiness_blockers()
    notes = "; ".join([*facts.notes, *blockers])
    if facts.external_call_performed or not facts.read_only_guarantee:
        return CachedAccountFacts(
            available=False,
            timestamp_ms=facts.timestamp_ms,
            freshness=facts.freshness_status.value,
            source=f"{facts.source_type.value}:{facts.source_id}",
            read_method="unsafe_to_read",
            read_only=False,
            reconciliation_status=facts.reconciliation_status.value,
            notes=notes or "Account facts source is not safe for readiness evaluation.",
        )
    return CachedAccountFacts(
        available=facts.source_type != AccountFactsSourceType.UNAVAILABLE,
        wallet_equity=facts.account_equity,
        available_margin=facts.available_margin,
        timestamp_ms=facts.timestamp_ms,
        freshness=facts.freshness_status.value,
        source=f"{facts.source_type.value}:{facts.source_id}",
        read_method=facts.source_type.value,
        read_only=True,
        reconciliation_status=facts.reconciliation_status.value,
        notes=notes,
    )


def _safety(check: str, passed: bool, evidence: str, notes: str = "") -> ChecklistRow:
    return ChecklistRow(
        check=check,
        status=ChecklistStatus.PASS if passed else ChecklistStatus.BLOCKED,
        evidence=evidence,
        blocking=not passed,
        notes=notes,
    )


def _all_pass(rows: list[ChecklistRow]) -> bool:
    return not any(row.blocking for row in rows)


def _input_status(value: object) -> str:
    if value is None:
        return "missing"
    if getattr(value, "read_method", None) == "unsafe_to_read":
        return "unsafe_to_read"
    available = getattr(value, "available", None)
    if available is False:
        return "blocked"
    return "available"


def _kill_switch_interpretation(kill_switch_facts: KillSwitchFacts) -> str:
    if kill_switch_facts.active is True:
        return (
            "active=True means Global Kill Switch blocks all new entries. "
            "This is safe fail-closed state, not trial-start readiness."
        )
    if kill_switch_facts.active is False:
        return (
            "active=False means Global Kill Switch is open for new entries; "
            "this checklist still does not grant trial start or execution permission."
        )
    return "GKS active state is unavailable; readiness remains blocked until clarified."


def _owner_input_status(owner_checks: list[ChecklistRow]) -> str:
    return "available" if not any(row.blocking for row in owner_checks) else "blocked"


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ",".join(str(item) for item in value) + "]"
    if value is None:
        return "missing"
    return str(value)


def render_trial_start_checklist_markdown(checklist: TrialStartChecklist) -> str:
    lines: list[str] = [
        "# Trial Start Checklist MI-001 SOL Long",
        "",
        "Generated: 2026-05-29",
        "",
        "## 1. Summary",
        "",
        "This is a PG-backed trial start readiness checklist for `MI-001 SOL/USDT:USDT long`.",
        "",
        "It does not start a trial, grant execution permission, create orders, connect to an exchange, or call account APIs.",
        "",
        "## 2. Source Inputs",
        "",
        "| input | status |",
        "| --- | --- |",
    ]
    for key, value in checklist.source_inputs.items():
        lines.append(f"| {key} | {value} |")

    lines.extend(["", "## 3. PG Registration Checks", "", "| check | status | evidence | blocking |", "| --- | --- | --- | --- |"])
    for row in checklist.pg_registration_checks:
        lines.append(f"| {row.check} | {row.status.value} | {row.evidence} | {_yes_no(row.blocking)} |")

    lines.extend(["", "## 4. Scope Checks", "", "| check | expected | actual | status | blocking |", "| --- | --- | --- | --- | --- |"])
    for row in checklist.scope_checks:
        lines.append(f"| {row.check} | {row.expected} | {row.actual} | {row.status.value} | {_yes_no(row.blocking)} |")

    lines.extend(["", "## 5. Account Facts Checks", "", "| check | status | source | timestamp | blocking | notes |", "| --- | --- | --- | --- | --- | --- |"])
    for row in checklist.account_facts_checks:
        lines.append(f"| {row.check} | {row.status.value} | {row.source} | {row.timestamp_ms or 'missing'} | {_yes_no(row.blocking)} | {row.notes} |")

    cap = checklist.capital_readiness
    lines.extend([
        "",
        "## 6. Capital Readiness",
        "",
        "| field | value |",
        "| --- | --- |",
        f"| status | {cap.status.value} |",
        f"| current_dedicated_subaccount_equity | {cap.current_dedicated_subaccount_equity if cap.current_dedicated_subaccount_equity is not None else 'blocked'} |",
        f"| available_margin | {cap.available_margin if cap.available_margin is not None else 'blocked'} |",
        f"| max_leverage | {cap.max_leverage} |",
        f"| computed_max_notional_candidate | {cap.computed_max_notional_candidate if cap.computed_max_notional_candidate is not None else 'blocked'} |",
        f"| max_total_loss_rule | {cap.max_total_loss_rule} |",
        f"| evidence | {cap.evidence} |",
    ])

    lines.extend(["", "## 7. Operation Layer / Safety Checks", "", "| check | status | evidence | blocking | notes |", "| --- | --- | --- | --- | --- |"])
    for row in checklist.operation_layer_safety_checks:
        lines.append(f"| {row.check} | {row.status.value} | {row.evidence} | {_yes_no(row.blocking)} | {row.notes} |")

    gks_notes = next(
        (
            row.notes
            for row in checklist.operation_layer_safety_checks
            if "kill switch" in row.check.lower()
        ),
        "GKS state was not interpreted.",
    )
    lines.extend([
        "",
        "## 8. GKS Interpretation",
        "",
        gks_notes,
        "",
        "Checklist consequence:",
        "",
        "- GKS state availability is a readiness fact, not execution permission.",
        "- This checklist does not change GKS state.",
        "- Any future trial start still requires separate Owner trial-start approval and an authorized safety transition.",
    ])

    lines.extend(["", "## 9. Owner Trial-start Approval", "", "| check | status | evidence | blocking |", "| --- | --- | --- | --- |"])
    for row in checklist.owner_trial_start_approval_checks:
        lines.append(f"| {row.check} | {row.status.value} | {row.evidence} | {_yes_no(row.blocking)} |")

    lines.extend([
        "",
        "## 10. Final Verdict",
        "",
        f"Verdict: `{checklist.final_verdict.value}`",
        "",
        "Blockers:",
    ])
    for blocker in checklist.blockers:
        lines.append(f"- {blocker}")

    lines.extend([
        "",
        "## 11. Non-permissions",
        "",
        "This checklist does not grant:",
    ])
    for item in checklist.non_permissions:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
