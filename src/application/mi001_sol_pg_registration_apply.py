"""Apply MI-001 SOL registration payloads through injected repositories.

This module maps the deterministic dry-run payload into PG repository calls. It
does not connect to exchanges, start trials, grant execution permission, create
execution intents, create orders, or touch runtime/live runner paths.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal, Optional, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from src.domain.brc_admission import (
    AdmissionDecision,
    AdmissionEvidencePacket,
    AdmissionRequest,
    AdmissionRuleConfig,
    AdmissionTrialBinding,
    OwnerMarketRegimeInput,
    OwnerRiskAcceptance,
    StrategyFamily,
    StrategyFamilyVersion,
    TrialConstraintSnapshot,
)
from src.domain.mi001_sol_pg_registration import Mi001SolPgRegistrationDryRun
from src.domain.strategy_family_registry import (
    StrategyFamilyMetadata,
    StrategyFamilyPlaybookMetadata,
)


class Mi001SolPgRegistrationApplyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Mi001SolPgAppliedRecord(Mi001SolPgRegistrationApplyModel):
    record_type: str = Field(min_length=1, max_length=128)
    record_id: str = Field(min_length=1, max_length=256)
    apply_status: Literal["created", "already_exists", "upserted"]
    repository_or_service: str = Field(min_length=1, max_length=256)
    runtime_effect: Literal["none"] = "none"
    notes: str = Field(default="", max_length=2048)


class Mi001SolPgRegistrationApplyResult(Mi001SolPgRegistrationApplyModel):
    mode: Literal["repository_apply"] = "repository_apply"
    applied_records: list[Mi001SolPgAppliedRecord]
    source_of_truth_status: dict[str, str] = Field(default_factory=dict)
    safety_assertions: dict[str, bool] = Field(default_factory=dict)


class StrategyFamilyRegistryRepositoryPort(Protocol):
    async def upsert_family_metadata(
        self,
        metadata: StrategyFamilyMetadata,
    ) -> StrategyFamilyMetadata: ...

    async def upsert_playbook_metadata(
        self,
        metadata: StrategyFamilyPlaybookMetadata,
    ) -> StrategyFamilyPlaybookMetadata: ...


class BrcAdmissionRegistrationRepositoryPort(Protocol):
    async def get_strategy_family(self, strategy_family_id: str) -> Optional[StrategyFamily]: ...

    async def create_strategy_family(self, family: StrategyFamily) -> StrategyFamily: ...

    async def get_strategy_family_version(
        self,
        strategy_family_version_id: str,
    ) -> Optional[StrategyFamilyVersion]: ...

    async def create_strategy_family_version(
        self,
        version: StrategyFamilyVersion,
    ) -> StrategyFamilyVersion: ...

    async def get_rule_config(
        self,
        admission_rule_config_id: str,
    ) -> Optional[AdmissionRuleConfig]: ...

    async def create_rule_config(self, config: AdmissionRuleConfig) -> AdmissionRuleConfig: ...

    async def get_evidence_packet(
        self,
        evidence_packet_id: str,
    ) -> Optional[AdmissionEvidencePacket]: ...

    async def create_evidence_packet(
        self,
        packet: AdmissionEvidencePacket,
    ) -> AdmissionEvidencePacket: ...

    async def get_owner_regime_input(
        self,
        owner_market_regime_input_id: str,
    ) -> Optional[OwnerMarketRegimeInput]: ...

    async def create_owner_regime_input(
        self,
        regime_input: OwnerMarketRegimeInput,
    ) -> OwnerMarketRegimeInput: ...

    async def get_admission_request(
        self,
        admission_request_id: str,
    ) -> Optional[AdmissionRequest]: ...

    async def create_admission_request(self, request: AdmissionRequest) -> AdmissionRequest: ...

    async def get_trial_constraint_snapshot(
        self,
        trial_constraint_snapshot_id: str,
    ) -> Optional[TrialConstraintSnapshot]: ...

    async def create_trial_constraint_snapshot(
        self,
        snapshot: TrialConstraintSnapshot,
    ) -> TrialConstraintSnapshot: ...

    async def get_admission_decision(
        self,
        admission_decision_id: str,
    ) -> Optional[AdmissionDecision]: ...

    async def create_admission_decision(
        self,
        decision: AdmissionDecision,
    ) -> AdmissionDecision: ...

    async def get_owner_risk_acceptance(
        self,
        owner_risk_acceptance_id: str,
    ) -> Optional[OwnerRiskAcceptance]: ...

    async def create_owner_risk_acceptance(
        self,
        acceptance: OwnerRiskAcceptance,
    ) -> OwnerRiskAcceptance: ...

    async def get_admission_trial_binding(
        self,
        binding_id: str,
    ) -> Optional[AdmissionTrialBinding]: ...

    async def create_admission_trial_binding(
        self,
        binding: AdmissionTrialBinding,
    ) -> AdmissionTrialBinding: ...


T = TypeVar("T")


class Mi001SolPgRegistrationApplyService:
    """Apply dry-run MI-001 records to metadata/admission repositories only."""

    def __init__(
        self,
        *,
        registry_repository: StrategyFamilyRegistryRepositoryPort,
        admission_repository: BrcAdmissionRegistrationRepositoryPort,
    ) -> None:
        self._registry_repository = registry_repository
        self._admission_repository = admission_repository

    async def apply(
        self,
        payload: Mi001SolPgRegistrationDryRun,
    ) -> Mi001SolPgRegistrationApplyResult:
        records: list[Mi001SolPgAppliedRecord] = []

        family_metadata = await self._registry_repository.upsert_family_metadata(
            payload.strategy_family_metadata
        )
        records.append(
            _record(
                record_type="strategy_family_registry",
                record_id=f"{family_metadata.family_id}:{family_metadata.version_id}",
                apply_status="upserted",
                repository_or_service="PgStrategyFamilyRegistryRepository.upsert_family_metadata",
                notes="Metadata only; no capital, order, routing, or runtime authority.",
            )
        )

        playbook_metadata = await self._registry_repository.upsert_playbook_metadata(
            payload.playbook_metadata
        )
        records.append(
            _record(
                record_type="playbook_metadata",
                record_id=playbook_metadata.playbook_id,
                apply_status="upserted",
                repository_or_service="PgStrategyFamilyRegistryRepository.upsert_playbook_metadata",
                notes="Metadata only; parameter_profile excludes execution/order fields.",
            )
        )

        records.extend(
            [
                await self._get_or_create(
                    record_type="admission_strategy_family",
                    record_id=payload.admission_strategy_family.strategy_family_id,
                    repository_or_service="PgBrcAdmissionRepository.create_strategy_family",
                    get=lambda: self._admission_repository.get_strategy_family(
                        payload.admission_strategy_family.strategy_family_id
                    ),
                    create=lambda: self._admission_repository.create_strategy_family(
                        payload.admission_strategy_family
                    ),
                    notes="Admission family metadata only.",
                ),
                await self._get_or_create(
                    record_type="admission_strategy_family_version",
                    record_id=payload.admission_strategy_family_version.strategy_family_version_id,
                    repository_or_service="PgBrcAdmissionRepository.create_strategy_family_version",
                    get=lambda: self._admission_repository.get_strategy_family_version(
                        payload.admission_strategy_family_version.strategy_family_version_id
                    ),
                    create=lambda: self._admission_repository.create_strategy_family_version(
                        payload.admission_strategy_family_version
                    ),
                    notes="Candidate/version metadata only; required_execution_capabilities is empty.",
                ),
                await self._get_or_create(
                    record_type="admission_rule_config",
                    record_id=payload.admission_rule_config.admission_rule_config_id,
                    repository_or_service="PgBrcAdmissionRepository.create_rule_config",
                    get=lambda: self._admission_repository.get_rule_config(
                        payload.admission_rule_config.admission_rule_config_id
                    ),
                    create=lambda: self._admission_repository.create_rule_config(
                        payload.admission_rule_config
                    ),
                    notes="Admission boundaries record; no permission grant.",
                ),
                await self._get_or_create(
                    record_type="evidence_packet",
                    record_id=payload.evidence_packet.evidence_packet_id,
                    repository_or_service="PgBrcAdmissionRepository.create_evidence_packet",
                    get=lambda: self._admission_repository.get_evidence_packet(
                        payload.evidence_packet.evidence_packet_id
                    ),
                    create=lambda: self._admission_repository.create_evidence_packet(
                        payload.evidence_packet
                    ),
                    notes="Broad smoke research evidence only.",
                ),
                await self._get_or_create(
                    record_type="owner_market_regime_input",
                    record_id=payload.owner_market_regime_input.owner_market_regime_input_id,
                    repository_or_service="PgBrcAdmissionRepository.create_owner_regime_input",
                    get=lambda: self._admission_repository.get_owner_regime_input(
                        payload.owner_market_regime_input.owner_market_regime_input_id
                    ),
                    create=lambda: self._admission_repository.create_owner_regime_input(
                        payload.owner_market_regime_input
                    ),
                    notes="Owner review context only.",
                ),
                await self._get_or_create(
                    record_type="admission_request",
                    record_id=payload.admission_request.admission_request_id,
                    repository_or_service="PgBrcAdmissionRepository.create_admission_request",
                    get=lambda: self._admission_repository.get_admission_request(
                        payload.admission_request.admission_request_id
                    ),
                    create=lambda: self._admission_repository.create_admission_request(
                        payload.admission_request
                    ),
                    notes="Request remains owner_confirm_each_entry; no auto execution.",
                ),
                await self._get_or_create(
                    record_type="trial_constraint_snapshot",
                    record_id=payload.trial_constraint_snapshot.trial_constraint_snapshot_id,
                    repository_or_service="PgBrcAdmissionRepository.create_trial_constraint_snapshot",
                    get=lambda: self._admission_repository.get_trial_constraint_snapshot(
                        payload.trial_constraint_snapshot.trial_constraint_snapshot_id
                    ),
                    create=lambda: self._admission_repository.create_trial_constraint_snapshot(
                        payload.trial_constraint_snapshot
                    ),
                    notes="Policy rules only; concrete capital is resolved by trial_start_checklist.",
                ),
                await self._get_or_create(
                    record_type="admission_decision",
                    record_id=payload.admission_decision.admission_decision_id,
                    repository_or_service="PgBrcAdmissionRepository.create_admission_decision",
                    get=lambda: self._admission_repository.get_admission_decision(
                        payload.admission_decision.admission_decision_id
                    ),
                    create=lambda: self._admission_repository.create_admission_decision(
                        payload.admission_decision
                    ),
                    notes="Admit-with-constraints plan-preparation decision, not trial start.",
                ),
                await self._get_or_create(
                    record_type="owner_plan_preparation_approval",
                    record_id=payload.owner_risk_acceptance.owner_risk_acceptance_id,
                    repository_or_service="PgBrcAdmissionRepository.create_owner_risk_acceptance",
                    get=lambda: self._admission_repository.get_owner_risk_acceptance(
                        payload.owner_risk_acceptance.owner_risk_acceptance_id
                    ),
                    create=lambda: self._admission_repository.create_owner_risk_acceptance(
                        payload.owner_risk_acceptance
                    ),
                    notes="Owner accepted plan-preparation risks only; trial start not approved.",
                ),
                await self._get_or_create(
                    record_type="planned_trial_binding",
                    record_id=payload.trial_binding.binding_id,
                    repository_or_service="PgBrcAdmissionRepository.create_admission_trial_binding",
                    get=lambda: self._admission_repository.get_admission_trial_binding(
                        payload.trial_binding.binding_id
                    ),
                    create=lambda: self._admission_repository.create_admission_trial_binding(
                        payload.trial_binding
                    ),
                    notes="Planned binding only; no campaign or runtime carrier.",
                ),
            ]
        )

        return Mi001SolPgRegistrationApplyResult(
            applied_records=records,
            source_of_truth_status={
                "strategy_family": "repository_applied",
                "playbook": "repository_applied",
                "candidate_admission": "repository_applied",
                "broad_smoke_evidence": "repository_applied",
                "owner_plan_preparation_approval": "repository_applied",
                "trial_constraints": "repository_applied_policy_rules_only",
                "planned_binding": "repository_applied",
                "trial_start_approval": "not_granted",
            },
            safety_assertions={
                "trial_started": False,
                "exchange_connected": False,
                "real_account_api_called": False,
                "order_created": False,
                "execution_intent_created": False,
                "execution_permission_granted": False,
                "order_capable_record_created": False,
                "runtime_or_live_runner_touched": False,
                "fresh_account_facts_read": False,
                "concrete_capital_amount_written": False,
            },
        )

    async def _get_or_create(
        self,
        *,
        record_type: str,
        record_id: str,
        repository_or_service: str,
        get: Callable[[], Awaitable[Optional[T]]],
        create: Callable[[], Awaitable[T]],
        notes: str,
    ) -> Mi001SolPgAppliedRecord:
        existing = await get()
        if existing is not None:
            return _record(
                record_type=record_type,
                record_id=record_id,
                apply_status="already_exists",
                repository_or_service=repository_or_service,
                notes=notes,
            )
        await create()
        return _record(
            record_type=record_type,
            record_id=record_id,
            apply_status="created",
            repository_or_service=repository_or_service,
            notes=notes,
        )


def _record(
    *,
    record_type: str,
    record_id: str,
    apply_status: Literal["created", "already_exists", "upserted"],
    repository_or_service: str,
    notes: str,
) -> Mi001SolPgAppliedRecord:
    return Mi001SolPgAppliedRecord(
        record_type=record_type,
        record_id=record_id,
        apply_status=apply_status,
        repository_or_service=repository_or_service,
        runtime_effect="none",
        notes=notes,
    )
