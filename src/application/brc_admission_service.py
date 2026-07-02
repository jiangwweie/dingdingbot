"""Application service for BRC admission gate."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from src.domain.brc_admission import (
    AdmissionAuditEventType,
    AdmissionAuditLog,
    AdmissionDecision,
    AdmissionDecisionValue,
    AdmissionEvidence,
    AdmissionExecutionMode,
    AdmissionRequest,
    AdmissionRuleConfig,
    AdmissionTrialBinding,
    AdmissionTrialBindingStatus,
    OwnerMarketRegimeInput,
    OwnerRiskAcceptance,
    RiskCapitalAdapterResult,
    StrategyFamily,
    StrategyFamilyStatus,
    StrategyFamilyVersion,
    TrialConstraintSnapshot,
    TrialConstraintSnapshotStatus,
    TrialTradeIntent,
    TrialTradeIntentDecision,
    TrialEnv,
    TrialStage,
)


DEFAULT_ADMISSION_RULE_CONFIG_ID = "brc-admission-rules-default-v1"

ACTIVE_ADMISSION_TRIAL_BINDING_STATUSES = {
    AdmissionTrialBindingStatus.PLANNED,
    AdmissionTrialBindingStatus.BINDING_RESERVED,
    AdmissionTrialBindingStatus.CAMPAIGN_CREATED,
    AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED,
    AdmissionTrialBindingStatus.RUNTIME_INSTALLED,
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class AdmissionRuleViolation(ValueError):
    """Raised when admission facts violate a Phase 1 boundary."""


class BrcAdmissionRepositoryPort(Protocol):
    async def initialize(self) -> None:
        ...

    async def create_strategy_family(self, family: StrategyFamily) -> StrategyFamily:
        ...

    async def get_strategy_family(self, strategy_family_id: str) -> Optional[StrategyFamily]:
        ...

    async def list_strategy_families(self, *, limit: int = 100) -> list[StrategyFamily]:
        ...

    async def create_strategy_family_version(
        self,
        version: StrategyFamilyVersion,
    ) -> StrategyFamilyVersion:
        ...

    async def get_strategy_family_version(
        self,
        strategy_family_version_id: str,
    ) -> Optional[StrategyFamilyVersion]:
        ...

    async def create_rule_config(self, config: AdmissionRuleConfig) -> AdmissionRuleConfig:
        ...

    async def get_rule_config(self, admission_rule_config_id: str) -> Optional[AdmissionRuleConfig]:
        ...

    async def get_latest_rule_config(self) -> Optional[AdmissionRuleConfig]:
        ...

    async def create_admission_evidence(
        self,
        admission_evidence: AdmissionEvidence,
    ) -> AdmissionEvidence:
        ...

    async def get_admission_evidence(self, admission_evidence_id: str) -> Optional[AdmissionEvidence]:
        ...

    async def create_owner_regime_input(
        self,
        regime_input: OwnerMarketRegimeInput,
    ) -> OwnerMarketRegimeInput:
        ...

    async def get_owner_regime_input(
        self,
        owner_market_regime_input_id: str,
    ) -> Optional[OwnerMarketRegimeInput]:
        ...

    async def create_admission_request(self, request: AdmissionRequest) -> AdmissionRequest:
        ...

    async def get_admission_request(self, admission_request_id: str) -> Optional[AdmissionRequest]:
        ...

    async def create_trial_constraint_snapshot(
        self,
        snapshot: TrialConstraintSnapshot,
    ) -> TrialConstraintSnapshot:
        ...

    async def get_trial_constraint_snapshot(
        self,
        trial_constraint_snapshot_id: str,
    ) -> Optional[TrialConstraintSnapshot]:
        ...

    async def create_admission_decision(self, decision: AdmissionDecision) -> AdmissionDecision:
        ...

    async def get_admission_decision(self, admission_decision_id: str) -> Optional[AdmissionDecision]:
        ...

    async def list_admission_decisions(self, *, limit: int = 100) -> list[AdmissionDecision]:
        ...

    async def create_owner_risk_acceptance(
        self,
        acceptance: OwnerRiskAcceptance,
    ) -> OwnerRiskAcceptance:
        ...

    async def get_owner_risk_acceptance(
        self,
        owner_risk_acceptance_id: str,
    ) -> Optional[OwnerRiskAcceptance]:
        ...

    async def append_audit_log(self, log: AdmissionAuditLog) -> AdmissionAuditLog:
        ...

    async def create_admission_trial_binding(
        self,
        binding: AdmissionTrialBinding,
    ) -> AdmissionTrialBinding:
        ...

    async def get_admission_trial_binding(
        self,
        binding_id: str,
    ) -> Optional[AdmissionTrialBinding]:
        ...

    async def list_admission_trial_bindings(
        self,
        *,
        limit: int = 100,
    ) -> list[AdmissionTrialBinding]:
        ...

    async def list_admission_trial_bindings_by_decision(
        self,
        admission_decision_id: str,
    ) -> list[AdmissionTrialBinding]:
        ...

    async def list_admission_trial_bindings_by_operation(
        self,
        operation_id: str,
    ) -> list[AdmissionTrialBinding]:
        ...

    async def update_admission_trial_binding(
        self,
        binding: AdmissionTrialBinding,
    ) -> AdmissionTrialBinding:
        ...

    async def create_trial_trade_intent(
        self,
        intent: TrialTradeIntent,
    ) -> TrialTradeIntent:
        ...

    async def get_trial_trade_intent(self, intent_id: str) -> Optional[TrialTradeIntent]:
        ...

    async def list_trial_trade_intents_by_campaign(
        self,
        campaign_id: str,
        *,
        limit: int = 100,
    ) -> list[TrialTradeIntent]:
        ...


class RiskCapitalAdapter(Protocol):
    async def resolve_constraints(
        self,
        *,
        request: AdmissionRequest,
        strategy_family_version: StrategyFamilyVersion,
        admission_evidence: AdmissionEvidence,
        owner_regime_input: OwnerMarketRegimeInput,
        rule_config: AdmissionRuleConfig,
    ) -> RiskCapitalAdapterResult:
        ...


class PendingRiskCapitalAdapter:
    """Phase 1 default adapter.

    It deliberately does not compute or pretend to compute capital constraints.
    """

    async def resolve_constraints(
        self,
        *,
        request: AdmissionRequest,
        strategy_family_version: StrategyFamilyVersion,
        admission_evidence: AdmissionEvidence,
        owner_regime_input: OwnerMarketRegimeInput,
        rule_config: AdmissionRuleConfig,
    ) -> RiskCapitalAdapterResult:
        return RiskCapitalAdapterResult(
            status=TrialConstraintSnapshotStatus.PENDING_RISK_CAPITAL_RESOLUTION,
            risk_profile=request.requested_risk_profile,
            adapter_result_json={
                "adapter": "PendingRiskCapitalAdapter",
                "reason": "risk capital module has not resolved concrete constraints",
                "sizing_computed": False,
            },
        )


@dataclass(frozen=True)
class OwnerRiskAcceptanceInput:
    admission_request_id: str
    constraint_snapshot_id: str
    admission_decision_id: Optional[str]
    owner_rationale: str
    confirmation_phrase: str
    confirmed_by: str = "owner"


class BrcAdmissionService:
    def __init__(
        self,
        repository: BrcAdmissionRepositoryPort,
        risk_capital_adapter: Optional[RiskCapitalAdapter] = None,
    ) -> None:
        self._repo = repository
        if risk_capital_adapter is None:
            from src.application.brc_admission_risk_capital import (
                BrcAdmissionRiskCapitalAdapter,
            )

            risk_capital_adapter = BrcAdmissionRiskCapitalAdapter()
        self._risk_capital_adapter = risk_capital_adapter

    async def initialize(self) -> None:
        await self._repo.initialize()

    async def list_strategy_families(self, *, limit: int = 100) -> list[StrategyFamily]:
        return await self._repo.list_strategy_families(limit=limit)

    async def get_strategy_family(self, strategy_family_id: str) -> StrategyFamily:
        family = await self._repo.get_strategy_family(strategy_family_id)
        if family is None:
            raise AdmissionRuleViolation(f"strategy family not found: {strategy_family_id}")
        return family

    async def get_strategy_family_version(
        self,
        strategy_family_version_id: str,
    ) -> StrategyFamilyVersion:
        return await self._require_strategy_family_version(strategy_family_version_id)

    async def get_admission_request(self, admission_request_id: str) -> AdmissionRequest:
        return await self._require_admission_request(admission_request_id)

    async def get_admission_decision(self, admission_decision_id: str) -> AdmissionDecision:
        return await self._require_admission_decision(admission_decision_id)

    async def list_admission_decisions(self, *, limit: int = 100) -> list[AdmissionDecision]:
        return await self._repo.list_admission_decisions(limit=limit)

    async def get_trial_constraint_snapshot(
        self,
        trial_constraint_snapshot_id: str,
    ) -> TrialConstraintSnapshot:
        return await self._require_constraint_snapshot(trial_constraint_snapshot_id)

    async def get_owner_risk_acceptance(
        self,
        owner_risk_acceptance_id: str,
    ) -> OwnerRiskAcceptance:
        item = await self._repo.get_owner_risk_acceptance(owner_risk_acceptance_id)
        if item is None:
            raise AdmissionRuleViolation(f"owner risk acceptance not found: {owner_risk_acceptance_id}")
        return item

    async def get_admission_trial_binding(
        self,
        binding_id: str,
    ) -> AdmissionTrialBinding:
        item = await self._repo.get_admission_trial_binding(binding_id)
        if item is None:
            raise AdmissionRuleViolation(f"admission trial binding not found: {binding_id}")
        return item

    async def list_admission_trial_bindings(
        self,
        *,
        limit: int = 100,
    ) -> list[AdmissionTrialBinding]:
        return await self._repo.list_admission_trial_bindings(limit=limit)

    async def build_gated_trial_preflight_readiness(
        self,
        input_params: dict[str, Any],
        *,
        now_ms_value: Optional[int] = None,
    ) -> dict[str, Any]:
        now_value = now_ms_value if now_ms_value is not None else _now_ms()
        blockers: list[str] = []
        warnings: list[str] = []
        decision_id = str(input_params.get("admission_decision_id") or "").strip()
        acceptance_id = str(input_params.get("owner_risk_acceptance_id") or "").strip()
        requested_playbook_id = str(input_params.get("playbook_id") or "").strip()
        if not decision_id:
            blockers.append("admission_decision_id required")
            return _gated_trial_readiness_unavailable(blockers=blockers, warnings=warnings)

        decision = await self._repo.get_admission_decision(decision_id)
        if decision is None:
            blockers.append(f"admission decision not found: {decision_id}")
            return _gated_trial_readiness_unavailable(blockers=blockers, warnings=warnings)

        request = await self._repo.get_admission_request(decision.admission_request_id)
        if request is None:
            blockers.append(f"admission request not found: {decision.admission_request_id}")
            return _gated_trial_readiness_from_decision(
                decision=decision,
                blockers=blockers,
                warnings=warnings,
                constraint=None,
                acceptance=None,
                requested_playbook_id=requested_playbook_id,
            )

        constraint = await self._repo.get_trial_constraint_snapshot(
            decision.trial_constraint_snapshot_id
        )
        if constraint is None:
            blockers.append(f"trial constraint snapshot not found: {decision.trial_constraint_snapshot_id}")
        elif constraint.status != TrialConstraintSnapshotStatus.INSTALLABLE:
            blockers.append(
                f"trial constraint snapshot is {constraint.status.value}, not installable"
            )
        elif constraint.expires_at_ms is not None and constraint.expires_at_ms <= now_value:
            blockers.append("trial constraint snapshot expired")

        if decision.decision not in {
            AdmissionDecisionValue.ADMIT,
            AdmissionDecisionValue.ADMIT_WITH_CONSTRAINTS,
        }:
            blockers.append(f"admission decision is {decision.decision.value}, not admissible")
        if decision.expires_at_ms is not None and decision.expires_at_ms <= now_value:
            blockers.append("admission decision expired")

        acceptance: Optional[OwnerRiskAcceptance] = None
        acceptance_required = decision.trial_stage == TrialStage.FUNDED_VALIDATION
        if acceptance_required and not acceptance_id:
            blockers.append("owner_risk_acceptance_id required for funded_validation")
        if acceptance_id:
            acceptance = await self._repo.get_owner_risk_acceptance(acceptance_id)
            if acceptance is None:
                blockers.append(f"owner risk acceptance not found: {acceptance_id}")
            else:
                if acceptance.admission_request_id != decision.admission_request_id:
                    blockers.append("owner risk acceptance request mismatch")
                if acceptance.admission_decision_id != decision.admission_decision_id:
                    blockers.append("owner risk acceptance decision mismatch")
                if acceptance.strategy_family_version_id != decision.strategy_family_version_id:
                    blockers.append("owner risk acceptance strategy family version mismatch")
                if acceptance.constraint_snapshot_id != decision.trial_constraint_snapshot_id:
                    blockers.append("owner risk acceptance constraint snapshot mismatch")
                if acceptance.trial_env != decision.trial_env or acceptance.trial_stage != decision.trial_stage:
                    blockers.append("owner risk acceptance env/stage mismatch")

        playbook_id = decision.playbook_id or requested_playbook_id
        if decision.playbook_id and requested_playbook_id and decision.playbook_id != requested_playbook_id:
            blockers.append("requested playbook_id does not match pinned admission decision playbook")
        if not playbook_id:
            blockers.append("playbook_id is not pinned")

        constraints_json = dict(constraint.constraints_json) if constraint is not None else {}
        account_ref = (
            request.account_facts_snapshot_ref
            or (acceptance.account_facts_snapshot_ref if acceptance is not None else None)
            or constraints_json.get("account_facts_snapshot_ref")
        )
        if not account_ref:
            blockers.append("account facts snapshot ref unavailable")

        account_issue = _account_facts_issue(request.account_facts_snapshot_json)
        if decision.trial_env == TrialEnv.LIVE and decision.trial_stage == TrialStage.FUNDED_VALIDATION:
            if account_issue is not None:
                blockers.append(account_issue)
            if constraints_json.get("source") != "risk_capital_adapter":
                blockers.append("live funded validation requires risk_capital_adapter constraints")
        elif account_issue is not None:
            warnings.append(account_issue)

        for item in constraints_json.get("blockers") or []:
            text = str(item)
            if text and text not in blockers:
                if decision.trial_env == TrialEnv.LIVE and decision.trial_stage == TrialStage.FUNDED_VALIDATION:
                    blockers.append(text)
                else:
                    warnings.append(text)
        for item in constraints_json.get("warnings") or []:
            text = str(item)
            if text and text not in warnings:
                warnings.append(text)

        existing_bindings = await self._repo.list_admission_trial_bindings_by_decision(
            decision.admission_decision_id
        )
        active_binding = _first_active_binding(existing_bindings)
        if active_binding is not None:
            blockers.append(
                f"active admission trial binding already exists: {active_binding.binding_id}"
            )

        return _gated_trial_readiness_from_decision(
            decision=decision,
            blockers=blockers,
            warnings=warnings,
            constraint=constraint,
            acceptance=acceptance,
            requested_playbook_id=requested_playbook_id,
            account_facts_snapshot_ref=account_ref,
            active_binding=active_binding,
        )

    async def reserve_gated_trial_binding(
        self,
        input_params: dict[str, Any],
        *,
        operation_id: str,
        preflight_id: str,
        confirmed_by: str = "owner",
    ) -> AdmissionTrialBinding:
        readiness = await self.build_gated_trial_preflight_readiness(input_params)
        blockers = [str(item) for item in readiness.get("blockers") or []]
        if blockers:
            raise AdmissionRuleViolation("; ".join(blockers))
        decision_id = str(input_params.get("admission_decision_id") or "").strip()
        acceptance_id = str(input_params.get("owner_risk_acceptance_id") or "").strip() or None
        requested_playbook_id = str(input_params.get("playbook_id") or "").strip() or None
        decision = await self._require_admission_decision(decision_id)
        request = await self._require_admission_request(decision.admission_request_id)
        constraint = await self._require_constraint_snapshot(decision.trial_constraint_snapshot_id)
        if constraint.status != TrialConstraintSnapshotStatus.INSTALLABLE:
            raise AdmissionRuleViolation("admission trial binding requires installable constraints")
        acceptance: Optional[OwnerRiskAcceptance] = None
        if acceptance_id is not None:
            acceptance = await self.get_owner_risk_acceptance(acceptance_id)
        if decision.trial_stage == TrialStage.FUNDED_VALIDATION and acceptance is None:
            raise AdmissionRuleViolation("owner risk acceptance required for funded_validation binding")
        playbook_id = decision.playbook_id or requested_playbook_id
        if not playbook_id:
            raise AdmissionRuleViolation("playbook_id is not pinned")

        binding = AdmissionTrialBinding(
            binding_id=_id("admission-binding"),
            admission_decision_id=decision.admission_decision_id,
            owner_risk_acceptance_id=acceptance.owner_risk_acceptance_id if acceptance else None,
            trial_constraint_snapshot_id=constraint.trial_constraint_snapshot_id,
            strategy_family_version_id=decision.strategy_family_version_id,
            playbook_id=playbook_id,
            playbook_catalog_snapshot_json=dict(
                decision.playbook_catalog_snapshot_json
                or request.playbook_catalog_snapshot_json
            ),
            trial_env=decision.trial_env,
            trial_stage=decision.trial_stage,
            execution_mode=decision.execution_mode,
            binding_status=AdmissionTrialBindingStatus.BINDING_RESERVED,
            campaign_id=None,
            runtime_carrier_id=None,
            created_by_operation_id=operation_id,
            created_by_preflight_id=preflight_id,
            created_at_ms=_now_ms(),
            updated_at_ms=_now_ms(),
        )
        saved = await self._repo.create_admission_trial_binding(binding)
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_TRIAL_BINDING_RESERVED,
            ref_type="admission_trial_binding",
            ref_id=saved.binding_id,
            admission_request_id=decision.admission_request_id,
            admission_decision_id=decision.admission_decision_id,
            actor=confirmed_by,
            message=(
                "Admission-trial binding reserved. No campaign, runtime carrier, "
                "runtime constraints, order, live execution, withdrawal, or transfer was created."
            ),
            metadata={
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "binding_status": saved.binding_status.value,
                "trial_env": saved.trial_env.value,
                "trial_stage": saved.trial_stage.value,
            },
        )
        return saved

    async def build_campaign_carrier_preflight_readiness(
        self,
        input_params: dict[str, Any],
        *,
        now_ms_value: Optional[int] = None,
    ) -> dict[str, Any]:
        now_value = now_ms_value if now_ms_value is not None else _now_ms()
        blockers: list[str] = []
        warnings: list[str] = []
        binding_id = str(
            input_params.get("admission_binding_id")
            or input_params.get("binding_id")
            or ""
        ).strip()
        if not binding_id:
            blockers.append("admission_binding_id required")
            return _campaign_carrier_readiness_unavailable(blockers=blockers, warnings=warnings)

        binding = await self._repo.get_admission_trial_binding(binding_id)
        if binding is None:
            blockers.append(f"admission trial binding not found: {binding_id}")
            return _campaign_carrier_readiness_unavailable(blockers=blockers, warnings=warnings)
        if binding.binding_status != AdmissionTrialBindingStatus.BINDING_RESERVED:
            blockers.append(
                f"admission trial binding is {binding.binding_status.value}, not binding_reserved"
            )
        if binding.campaign_id:
            blockers.append("admission trial binding already has campaign_id")

        decision = await self._repo.get_admission_decision(binding.admission_decision_id)
        if decision is None:
            blockers.append(f"admission decision not found: {binding.admission_decision_id}")
            return _campaign_carrier_readiness_from_binding(
                binding=binding,
                blockers=blockers,
                warnings=warnings,
                decision=None,
                constraint=None,
                acceptance=None,
                account_facts_snapshot_ref=None,
            )
        if decision.decision not in {
            AdmissionDecisionValue.ADMIT,
            AdmissionDecisionValue.ADMIT_WITH_CONSTRAINTS,
        }:
            blockers.append(f"admission decision is {decision.decision.value}, not admissible")
        if decision.expires_at_ms is not None and decision.expires_at_ms <= now_value:
            blockers.append("admission decision expired")

        request = await self._repo.get_admission_request(decision.admission_request_id)
        if request is None:
            blockers.append(f"admission request not found: {decision.admission_request_id}")
            return _campaign_carrier_readiness_from_binding(
                binding=binding,
                blockers=blockers,
                warnings=warnings,
                decision=decision,
                constraint=None,
                acceptance=None,
                account_facts_snapshot_ref=None,
            )

        constraint = await self._repo.get_trial_constraint_snapshot(
            binding.trial_constraint_snapshot_id
        )
        if constraint is None:
            blockers.append(f"trial constraint snapshot not found: {binding.trial_constraint_snapshot_id}")
        elif constraint.status != TrialConstraintSnapshotStatus.INSTALLABLE:
            blockers.append(
                f"trial constraint snapshot is {constraint.status.value}, not installable"
            )
        elif constraint.expires_at_ms is not None and constraint.expires_at_ms <= now_value:
            blockers.append("trial constraint snapshot expired")

        acceptance: Optional[OwnerRiskAcceptance] = None
        if binding.trial_stage == TrialStage.FUNDED_VALIDATION and not binding.owner_risk_acceptance_id:
            blockers.append("owner risk acceptance required for funded_validation binding")
        if binding.owner_risk_acceptance_id:
            acceptance = await self._repo.get_owner_risk_acceptance(binding.owner_risk_acceptance_id)
            if acceptance is None:
                blockers.append(f"owner risk acceptance not found: {binding.owner_risk_acceptance_id}")
            else:
                if acceptance.admission_request_id != decision.admission_request_id:
                    blockers.append("owner risk acceptance request mismatch")
                if acceptance.admission_decision_id != decision.admission_decision_id:
                    blockers.append("owner risk acceptance decision mismatch")
                if acceptance.strategy_family_version_id != decision.strategy_family_version_id:
                    blockers.append("owner risk acceptance strategy family version mismatch")
                if acceptance.constraint_snapshot_id != binding.trial_constraint_snapshot_id:
                    blockers.append("owner risk acceptance constraint snapshot mismatch")
                if acceptance.trial_env != binding.trial_env or acceptance.trial_stage != binding.trial_stage:
                    blockers.append("owner risk acceptance env/stage mismatch")

        if not binding.playbook_id:
            blockers.append("playbook_id is not pinned")

        constraints_json = dict(constraint.constraints_json) if constraint is not None else {}
        account_ref = (
            request.account_facts_snapshot_ref
            or (acceptance.account_facts_snapshot_ref if acceptance is not None else None)
            or constraints_json.get("account_facts_snapshot_ref")
        )
        if binding.trial_stage == TrialStage.FUNDED_VALIDATION and not account_ref:
            blockers.append("account facts snapshot ref unavailable")

        account_issue = _account_facts_issue(request.account_facts_snapshot_json)
        if binding.trial_env == TrialEnv.LIVE and binding.trial_stage == TrialStage.FUNDED_VALIDATION:
            if account_issue is not None:
                blockers.append(account_issue)
            if constraints_json.get("source") != "risk_capital_adapter":
                blockers.append("live funded validation requires risk_capital_adapter constraints")
        elif account_issue is not None:
            warnings.append(account_issue)

        for item in constraints_json.get("blockers") or []:
            text = str(item)
            if text and text not in blockers:
                if binding.trial_env == TrialEnv.LIVE and binding.trial_stage == TrialStage.FUNDED_VALIDATION:
                    blockers.append(text)
                else:
                    warnings.append(text)
        for item in constraints_json.get("warnings") or []:
            text = str(item)
            if text and text not in warnings:
                warnings.append(text)

        return _campaign_carrier_readiness_from_binding(
            binding=binding,
            blockers=blockers,
            warnings=warnings,
            decision=decision,
            constraint=constraint,
            acceptance=acceptance,
            account_facts_snapshot_ref=account_ref,
        )

    async def mark_admission_trial_binding_campaign_created(
        self,
        *,
        binding_id: str,
        campaign_id: str,
        operation_id: str,
        preflight_id: str,
        confirmed_by: str = "owner",
    ) -> AdmissionTrialBinding:
        binding = await self.get_admission_trial_binding(binding_id)
        if binding.binding_status != AdmissionTrialBindingStatus.BINDING_RESERVED:
            raise AdmissionRuleViolation(
                f"admission trial binding is {binding.binding_status.value}, not binding_reserved"
            )
        if binding.campaign_id:
            raise AdmissionRuleViolation("admission trial binding already has campaign_id")
        updated = binding.model_copy(
            update={
                "binding_status": AdmissionTrialBindingStatus.CAMPAIGN_CREATED,
                "campaign_id": campaign_id,
                "updated_at_ms": _now_ms(),
            }
        )
        saved = await self._repo.update_admission_trial_binding(updated)
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_TRIAL_CAMPAIGN_CREATED,
            ref_type="admission_trial_binding",
            ref_id=saved.binding_id,
            admission_decision_id=saved.admission_decision_id,
            actor=confirmed_by,
            message=(
                "Admission campaign shell created. Runtime carrier not installed, "
                "strategy not active, constraints not installed, and no order was placed."
            ),
            metadata={
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "campaign_id": campaign_id,
                "binding_status": saved.binding_status.value,
            },
        )
        return saved

    async def build_runtime_constraint_install_preflight_readiness(
        self,
        input_params: dict[str, Any],
        *,
        campaign: Optional[Any] = None,
        runtime_summary: Optional[dict[str, Any]] = None,
        now_ms_value: Optional[int] = None,
    ) -> dict[str, Any]:
        now_value = now_ms_value if now_ms_value is not None else _now_ms()
        blockers: list[str] = []
        warnings: list[str] = []
        binding_id = str(
            input_params.get("admission_binding_id")
            or input_params.get("binding_id")
            or ""
        ).strip()
        campaign_id = str(input_params.get("campaign_id") or "").strip()

        binding: Optional[AdmissionTrialBinding] = None
        if binding_id:
            binding = await self._repo.get_admission_trial_binding(binding_id)
            if binding is None:
                blockers.append(f"admission trial binding not found: {binding_id}")
        elif campaign_id:
            bindings = await self._repo.list_admission_trial_bindings(limit=500)
            binding = next((item for item in bindings if item.campaign_id == campaign_id), None)
            if binding is None:
                blockers.append(f"admission trial binding not found for campaign_id: {campaign_id}")
        else:
            blockers.append("admission_binding_id or campaign_id required")

        if binding is None:
            return _runtime_constraint_install_readiness_unavailable(
                blockers=blockers,
                warnings=warnings,
            )

        if campaign_id and binding.campaign_id != campaign_id:
            blockers.append("admission trial binding campaign_id mismatch")
        if not binding.campaign_id:
            blockers.append("admission trial binding missing campaign_id")
        if binding.binding_status == AdmissionTrialBindingStatus.CAMPAIGN_CREATED:
            idempotent_install = False
        elif binding.binding_status == AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
            idempotent_install = True
        else:
            idempotent_install = False
            blockers.append(
                f"admission trial binding is {binding.binding_status.value}, not campaign_created"
            )

        campaign_metadata = _campaign_metadata(campaign)
        actual_campaign_id = _campaign_id(campaign)
        if campaign is None:
            blockers.append("campaign metadata unavailable")
        elif actual_campaign_id != binding.campaign_id:
            blockers.append("campaign_id does not match admission trial binding")
        elif campaign_metadata.get("created_from_admission") is not True:
            blockers.append("campaign metadata is not admission-created")
        else:
            expected_refs = {
                "admission_binding_id": binding.binding_id,
                "admission_decision_id": binding.admission_decision_id,
                "strategy_family_version_id": binding.strategy_family_version_id,
                "playbook_id": binding.playbook_id,
                "constraint_snapshot_id": binding.trial_constraint_snapshot_id,
            }
            for key, expected in expected_refs.items():
                if campaign_metadata.get(key) != expected:
                    blockers.append(f"campaign metadata {key} mismatch")

        decision = await self._repo.get_admission_decision(binding.admission_decision_id)
        if decision is None:
            blockers.append(f"admission decision not found: {binding.admission_decision_id}")
            return _runtime_constraint_install_readiness_from_binding(
                binding=binding,
                blockers=blockers,
                warnings=warnings,
                decision=None,
                constraint=None,
                acceptance=None,
                campaign=campaign,
                idempotent_install=False,
                account_facts_snapshot_ref=None,
            )
        if decision.strategy_family_version_id != binding.strategy_family_version_id:
            blockers.append("strategy_family_version_id mismatch")
        if decision.playbook_id and decision.playbook_id != binding.playbook_id:
            blockers.append("playbook_id does not match pinned admission decision playbook")
        if not binding.playbook_id:
            blockers.append("playbook_id is not pinned")
        if decision.decision not in {
            AdmissionDecisionValue.ADMIT,
            AdmissionDecisionValue.ADMIT_WITH_CONSTRAINTS,
        }:
            blockers.append(f"admission decision is {decision.decision.value}, not admissible")
        if decision.expires_at_ms is not None and decision.expires_at_ms <= now_value:
            blockers.append("admission decision expired")

        request = await self._repo.get_admission_request(decision.admission_request_id)
        if request is None:
            blockers.append(f"admission request not found: {decision.admission_request_id}")
            return _runtime_constraint_install_readiness_from_binding(
                binding=binding,
                blockers=blockers,
                warnings=warnings,
                decision=decision,
                constraint=None,
                acceptance=None,
                campaign=campaign,
                idempotent_install=False,
                account_facts_snapshot_ref=None,
            )

        constraint = await self._repo.get_trial_constraint_snapshot(
            binding.trial_constraint_snapshot_id
        )
        if constraint is None:
            blockers.append(f"trial constraint snapshot not found: {binding.trial_constraint_snapshot_id}")
        elif constraint.status != TrialConstraintSnapshotStatus.INSTALLABLE:
            blockers.append(
                f"trial constraint snapshot is {constraint.status.value}, not installable"
            )
        elif constraint.expires_at_ms is not None and constraint.expires_at_ms <= now_value:
            blockers.append("trial constraint snapshot expired")

        acceptance: Optional[OwnerRiskAcceptance] = None
        if binding.trial_stage == TrialStage.FUNDED_VALIDATION and not binding.owner_risk_acceptance_id:
            blockers.append("owner risk acceptance required for funded_validation binding")
        if binding.owner_risk_acceptance_id:
            acceptance = await self._repo.get_owner_risk_acceptance(binding.owner_risk_acceptance_id)
            if acceptance is None:
                blockers.append(f"owner risk acceptance not found: {binding.owner_risk_acceptance_id}")
            else:
                if acceptance.admission_request_id != decision.admission_request_id:
                    blockers.append("owner risk acceptance request mismatch")
                if acceptance.admission_decision_id != decision.admission_decision_id:
                    blockers.append("owner risk acceptance decision mismatch")
                if acceptance.strategy_family_version_id != decision.strategy_family_version_id:
                    blockers.append("owner risk acceptance strategy family version mismatch")
                if acceptance.constraint_snapshot_id != binding.trial_constraint_snapshot_id:
                    blockers.append("owner risk acceptance constraint snapshot mismatch")
                if acceptance.trial_env != binding.trial_env or acceptance.trial_stage != binding.trial_stage:
                    blockers.append("owner risk acceptance env/stage mismatch")

        constraints_json = dict(constraint.constraints_json) if constraint is not None else {}
        account_ref = (
            request.account_facts_snapshot_ref
            or (acceptance.account_facts_snapshot_ref if acceptance is not None else None)
            or constraints_json.get("account_facts_snapshot_ref")
        )
        if binding.trial_stage == TrialStage.FUNDED_VALIDATION and not account_ref:
            blockers.append("account facts snapshot ref unavailable")

        account_issue = _account_facts_issue(request.account_facts_snapshot_json)
        freshness_issue = _account_facts_freshness_issue(request.account_facts_snapshot_json)
        if binding.trial_env == TrialEnv.LIVE and binding.trial_stage == TrialStage.FUNDED_VALIDATION:
            if account_issue is not None:
                blockers.append(account_issue)
            if freshness_issue is not None:
                blockers.append(freshness_issue)
            if constraints_json.get("source") != "risk_capital_adapter":
                blockers.append("live funded validation requires risk_capital_adapter constraints")
        else:
            if account_issue is not None:
                warnings.append(account_issue)
            if freshness_issue is not None:
                warnings.append(freshness_issue)

        installed_snapshot_id = campaign_metadata.get("installed_constraint_snapshot_id")
        metadata_idempotent = (
            campaign_metadata.get("constraints_installed") is True
            and installed_snapshot_id == binding.trial_constraint_snapshot_id
            and campaign_metadata.get("runtime_status") == "constraints_installed_not_started"
            and campaign_metadata.get("strategy_status") == "not_active"
        )
        if campaign_metadata.get("constraints_installed") is True and not metadata_idempotent:
            blockers.append("runtime constraints already installed for a different snapshot or state")
        if idempotent_install and not metadata_idempotent:
            blockers.append("binding is runtime_constraints_installed but campaign metadata is not idempotent")
        idempotent_install = idempotent_install or metadata_idempotent

        runtime_summary = dict(runtime_summary or {})
        active_carrier_id = (
            runtime_summary.get("active_runtime_carrier_id")
            or runtime_summary.get("runtime_carrier_id")
        )
        if active_carrier_id and active_carrier_id != binding.campaign_id:
            blockers.append("active conflicting runtime carrier exists")
        if runtime_summary.get("strategy_active") is True:
            blockers.append("active strategy already exists")

        return _runtime_constraint_install_readiness_from_binding(
            binding=binding,
            blockers=blockers,
            warnings=warnings,
            decision=decision,
            constraint=constraint,
            acceptance=acceptance,
            campaign=campaign,
            idempotent_install=idempotent_install,
            account_facts_snapshot_ref=account_ref,
        )

    async def mark_admission_trial_binding_runtime_constraints_installed(
        self,
        *,
        binding_id: str,
        campaign_id: str,
        operation_id: str,
        preflight_id: str,
        confirmed_by: str = "owner",
    ) -> AdmissionTrialBinding:
        binding = await self.get_admission_trial_binding(binding_id)
        if binding.binding_status == AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
            if binding.campaign_id != campaign_id:
                raise AdmissionRuleViolation("runtime constraints installed binding campaign_id mismatch")
            return binding
        if binding.binding_status != AdmissionTrialBindingStatus.CAMPAIGN_CREATED:
            raise AdmissionRuleViolation(
                f"admission trial binding is {binding.binding_status.value}, not campaign_created"
            )
        if binding.campaign_id != campaign_id:
            raise AdmissionRuleViolation("admission trial binding campaign_id mismatch")
        updated = binding.model_copy(
            update={
                "binding_status": AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED,
                "updated_at_ms": _now_ms(),
            }
        )
        saved = await self._repo.update_admission_trial_binding(updated)
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_RUNTIME_CONSTRAINTS_INSTALLED,
            ref_type="admission_trial_binding",
            ref_id=saved.binding_id,
            admission_decision_id=saved.admission_decision_id,
            actor=confirmed_by,
            message=(
                "Admission runtime constraints metadata installed. Runtime not started, "
                "strategy not active, trial inactive, and no order was placed."
            ),
            metadata={
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "campaign_id": campaign_id,
                "binding_status": saved.binding_status.value,
                "runtime_status": "constraints_installed_not_started",
            },
        )
        return saved

    async def build_runtime_carrier_preflight_readiness(
        self,
        input_params: dict[str, Any],
        *,
        campaign: Optional[Any] = None,
        runtime_summary: Optional[dict[str, Any]] = None,
        now_ms_value: Optional[int] = None,
    ) -> dict[str, Any]:
        now_value = now_ms_value if now_ms_value is not None else _now_ms()
        blockers: list[str] = []
        warnings: list[str] = []
        binding_id = str(
            input_params.get("admission_binding_id")
            or input_params.get("binding_id")
            or ""
        ).strip()
        campaign_id = str(input_params.get("campaign_id") or "").strip()

        binding: Optional[AdmissionTrialBinding] = None
        if binding_id:
            binding = await self._repo.get_admission_trial_binding(binding_id)
            if binding is None:
                blockers.append(f"admission trial binding not found: {binding_id}")
        elif campaign_id:
            bindings = await self._repo.list_admission_trial_bindings(limit=500)
            binding = next((item for item in bindings if item.campaign_id == campaign_id), None)
            if binding is None:
                blockers.append(f"admission trial binding not found for campaign_id: {campaign_id}")
        else:
            blockers.append("admission_binding_id or campaign_id required")

        if binding is None:
            return _runtime_carrier_readiness_unavailable(blockers=blockers, warnings=warnings)

        if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
            blockers.append(
                f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
            )
        if campaign_id and binding.campaign_id != campaign_id:
            blockers.append("admission trial binding campaign_id mismatch")
        if not binding.campaign_id:
            blockers.append("admission trial binding missing campaign_id")

        campaign_metadata = _campaign_metadata(campaign)
        actual_campaign_id = _campaign_id(campaign)
        if campaign is None:
            blockers.append("campaign metadata unavailable")
        elif not campaign_metadata:
            blockers.append("campaign metadata missing")
        elif actual_campaign_id != binding.campaign_id:
            blockers.append("campaign_id does not match admission trial binding")
        elif campaign_metadata.get("created_from_admission") is not True:
            blockers.append("campaign metadata is not admission-created")
        else:
            expected_refs = {
                "admission_binding_id": binding.binding_id,
                "admission_decision_id": binding.admission_decision_id,
                "strategy_family_version_id": binding.strategy_family_version_id,
                "playbook_id": binding.playbook_id,
            }
            for key, expected in expected_refs.items():
                if campaign_metadata.get(key) != expected:
                    blockers.append(f"campaign metadata {key} mismatch")

        decision = await self._repo.get_admission_decision(binding.admission_decision_id)
        request: Optional[AdmissionRequest] = None
        if decision is None:
            blockers.append(f"admission decision not found: {binding.admission_decision_id}")
        else:
            request = await self._repo.get_admission_request(decision.admission_request_id)
            if request is None:
                blockers.append(f"admission request not found: {decision.admission_request_id}")
            if decision.strategy_family_version_id != binding.strategy_family_version_id:
                blockers.append("strategy_family_version_id mismatch")
            if not decision.strategy_family_version_id:
                blockers.append("strategy_family_version_id missing")
            if decision.playbook_id and decision.playbook_id != binding.playbook_id:
                blockers.append("playbook_id does not match pinned admission decision playbook")
            if decision.expires_at_ms is not None and decision.expires_at_ms <= now_value:
                blockers.append("admission decision expired")

        if not binding.strategy_family_version_id:
            blockers.append("strategy_family_version_id missing")
        if not binding.playbook_id:
            blockers.append("playbook_id is not pinned")
        try:
            AdmissionExecutionMode(binding.execution_mode.value if hasattr(binding.execution_mode, "value") else str(binding.execution_mode))
        except ValueError:
            blockers.append("execution_mode is not allowed")

        installed_snapshot_id = campaign_metadata.get("installed_constraint_snapshot_id")
        if not installed_snapshot_id:
            blockers.append("installed_constraint_snapshot_id missing")
        elif installed_snapshot_id != binding.trial_constraint_snapshot_id:
            blockers.append("installed_constraint_snapshot_id mismatch")
        constraint = await self._repo.get_trial_constraint_snapshot(binding.trial_constraint_snapshot_id)
        if constraint is None:
            blockers.append(f"trial constraint snapshot not found: {binding.trial_constraint_snapshot_id}")

        required_metadata = {
            "constraints_installed": True,
            "runtime_started": False,
            "strategy_active": False,
            "trial_started": False,
            "orders_placed": False,
        }
        for key, expected in required_metadata.items():
            if campaign_metadata.get(key) is not expected:
                blockers.append(f"campaign metadata {key} is not {str(expected).lower()}")
        if campaign_metadata.get("runtime_active") is True:
            blockers.append("campaign metadata runtime_active is true")
        if campaign_metadata.get("live_ready") is True:
            blockers.append("campaign metadata live_ready is true")
        if campaign_metadata.get("auto_within_budget_enabled") is True:
            blockers.append("campaign metadata auto_within_budget_enabled is true")
        if campaign_metadata.get("owner_confirm_each_entry_enabled") is True:
            blockers.append("campaign metadata owner_confirm_each_entry_enabled is true")

        idempotent_prepare = (
            campaign_metadata.get("carrier_ready") is True
            and campaign_metadata.get("runtime_status") == "carrier_ready_not_started"
            and campaign_metadata.get("runtime_started") is False
            and campaign_metadata.get("strategy_active") is False
            and campaign_metadata.get("trial_started") is False
            and campaign_metadata.get("orders_placed") is False
        )
        if campaign_metadata.get("runtime_status") == "constraints_installed_not_started":
            pass
        elif idempotent_prepare:
            pass
        else:
            blockers.append("campaign metadata runtime_status is not constraints_installed_not_started")

        if request is not None:
            freshness_issue = _account_facts_freshness_issue(request.account_facts_snapshot_json)
            if freshness_issue is not None:
                blockers.append(freshness_issue)
            account_issue = _account_facts_issue(request.account_facts_snapshot_json)
            if binding.trial_env == TrialEnv.LIVE and binding.trial_stage == TrialStage.FUNDED_VALIDATION:
                if account_issue is not None:
                    blockers.append(account_issue)
            elif account_issue is not None:
                warnings.append(account_issue)

        runtime_summary = dict(runtime_summary or {})
        active_carrier_id = (
            runtime_summary.get("active_runtime_carrier_id")
            or runtime_summary.get("runtime_carrier_id")
        )
        if active_carrier_id and active_carrier_id != binding.campaign_id:
            blockers.append("active conflicting runtime carrier exists")
        if _runtime_summary_active(runtime_summary):
            blockers.append("runtime is already active")
        if runtime_summary.get("strategy_active") is True:
            blockers.append("active strategy already exists")

        return _runtime_carrier_readiness_from_binding(
            binding=binding,
            blockers=blockers,
            warnings=warnings,
            decision=decision,
            constraint=constraint,
            campaign=campaign,
            idempotent_prepare=idempotent_prepare,
        )

    async def record_admission_runtime_carrier_ready(
        self,
        *,
        binding_id: str,
        campaign_id: str,
        operation_id: str,
        preflight_id: str,
        confirmed_by: str = "owner",
    ) -> AdmissionTrialBinding:
        binding = await self.get_admission_trial_binding(binding_id)
        if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
            raise AdmissionRuleViolation(
                f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
            )
        if binding.campaign_id != campaign_id:
            raise AdmissionRuleViolation("admission trial binding campaign_id mismatch")
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_RUNTIME_CARRIER_READY,
            ref_type="admission_trial_binding",
            ref_id=binding.binding_id,
            admission_decision_id=binding.admission_decision_id,
            actor=confirmed_by,
            message=(
                "Admission runtime carrier readiness metadata prepared. Runtime not started, "
                "strategy not active, auto execution disabled, trial inactive, and no order was placed."
            ),
            metadata={
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "campaign_id": campaign_id,
                "binding_status": binding.binding_status.value,
                "runtime_status": "carrier_ready_not_started",
                "carrier_ready": True,
            },
        )
        return binding

    async def build_runtime_start_preflight_readiness(
        self,
        input_params: dict[str, Any],
        *,
        campaign: Optional[Any] = None,
        runtime_summary: Optional[dict[str, Any]] = None,
        now_ms_value: Optional[int] = None,
    ) -> dict[str, Any]:
        now_value = now_ms_value if now_ms_value is not None else _now_ms()
        blockers: list[str] = []
        warnings: list[str] = []
        binding_id = str(
            input_params.get("admission_binding_id")
            or input_params.get("binding_id")
            or ""
        ).strip()
        campaign_id = str(input_params.get("campaign_id") or "").strip()

        binding: Optional[AdmissionTrialBinding] = None
        if binding_id:
            binding = await self._repo.get_admission_trial_binding(binding_id)
            if binding is None:
                blockers.append(f"admission trial binding not found: {binding_id}")
        elif campaign_id:
            bindings = await self._repo.list_admission_trial_bindings(limit=500)
            binding = next((item for item in bindings if item.campaign_id == campaign_id), None)
            if binding is None:
                blockers.append(f"admission trial binding not found for campaign_id: {campaign_id}")
        else:
            blockers.append("admission_binding_id or campaign_id required")

        if binding is None:
            return _runtime_start_readiness_unavailable(blockers=blockers, warnings=warnings)

        if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
            blockers.append(
                f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
            )
        if campaign_id and binding.campaign_id != campaign_id:
            blockers.append("admission trial binding campaign_id mismatch")
        if not binding.campaign_id:
            blockers.append("admission trial binding missing campaign_id")

        campaign_metadata = _campaign_metadata(campaign)
        actual_campaign_id = _campaign_id(campaign)
        if campaign is None:
            blockers.append("campaign metadata unavailable")
        elif not campaign_metadata:
            blockers.append("campaign metadata missing")
        elif actual_campaign_id != binding.campaign_id:
            blockers.append("campaign_id does not match admission trial binding")
        elif campaign_metadata.get("created_from_admission") is not True:
            blockers.append("campaign metadata is not admission-created")

        decision = await self._repo.get_admission_decision(binding.admission_decision_id)
        request: Optional[AdmissionRequest] = None
        if decision is None:
            blockers.append(f"admission decision not found: {binding.admission_decision_id}")
        else:
            request = await self._repo.get_admission_request(decision.admission_request_id)
            if request is None:
                blockers.append(f"admission request not found: {decision.admission_request_id}")
            if decision.expires_at_ms is not None and decision.expires_at_ms <= now_value:
                blockers.append("admission decision expired")

        if campaign_metadata.get("carrier_ready") is not True:
            blockers.append("campaign metadata carrier_ready is not true")
        if campaign_metadata.get("constraints_installed") is not True:
            blockers.append("campaign metadata constraints_installed is not true")
        installed_snapshot_id = campaign_metadata.get("installed_constraint_snapshot_id")
        if not installed_snapshot_id:
            blockers.append("installed_constraint_snapshot_id missing")
        elif installed_snapshot_id != binding.trial_constraint_snapshot_id:
            blockers.append("installed_constraint_snapshot_id mismatch")
        constraint = await self._repo.get_trial_constraint_snapshot(binding.trial_constraint_snapshot_id)
        if constraint is None:
            blockers.append(f"trial constraint snapshot not found: {binding.trial_constraint_snapshot_id}")

        required_false_metadata = {
            "runtime_started": False,
            "strategy_active": False,
            "trial_started": False,
            "orders_placed": False,
        }
        for key, expected in required_false_metadata.items():
            if campaign_metadata.get(key) is not expected:
                blockers.append(f"campaign metadata {key} is not false")
        if campaign_metadata.get("runtime_active") is True:
            blockers.append("campaign metadata runtime_active is true")
        if campaign_metadata.get("live_ready") is True:
            blockers.append("campaign metadata live_ready is true")
        if campaign_metadata.get("auto_within_budget_enabled") is True:
            blockers.append("campaign metadata auto_within_budget_enabled is true")
        if campaign_metadata.get("owner_confirm_each_entry_enabled") is True:
            blockers.append("campaign metadata owner_confirm_each_entry_enabled is true")

        idempotent_prepare = (
            campaign_metadata.get("runtime_start_ready") is True
            and campaign_metadata.get("runtime_status") == "runtime_start_ready_not_started"
            and campaign_metadata.get("runtime_started") is False
            and campaign_metadata.get("strategy_active") is False
            and campaign_metadata.get("trial_started") is False
            and campaign_metadata.get("orders_placed") is False
        )
        if campaign_metadata.get("runtime_status") == "carrier_ready_not_started":
            pass
        elif idempotent_prepare:
            pass
        else:
            blockers.append("campaign metadata runtime_status is not carrier_ready_not_started")

        execution_mode_value = (
            binding.execution_mode.value
            if hasattr(binding.execution_mode, "value")
            else str(binding.execution_mode)
        )
        try:
            execution_mode = AdmissionExecutionMode(execution_mode_value)
        except ValueError:
            execution_mode = None
            blockers.append("execution_mode is not allowed")
        constraints_summary = dict(campaign_metadata.get("installed_constraints_summary") or {})
        if execution_mode == AdmissionExecutionMode.AUTO_WITHIN_BUDGET:
            if not constraints_summary:
                blockers.append("installed constraints summary missing for auto_within_budget")
            warnings.append("auto_within_budget execution remains disabled; next phase must enforce execution mode")
        elif execution_mode in {
            AdmissionExecutionMode.OBSERVE_ONLY,
            AdmissionExecutionMode.NO_ENTRY,
            AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY,
        }:
            warnings.append(f"{execution_mode.value} can be prepared; runtime behavior enforcement remains future phase")

        if request is not None:
            freshness_issue = _account_facts_freshness_issue(request.account_facts_snapshot_json)
            if freshness_issue is not None:
                blockers.append(freshness_issue)
            account_issue = _account_facts_issue(request.account_facts_snapshot_json)
            if binding.trial_env == TrialEnv.LIVE and binding.trial_stage == TrialStage.FUNDED_VALIDATION:
                if account_issue is not None:
                    blockers.append(account_issue)
            elif account_issue is not None:
                warnings.append(account_issue)

        runtime_summary = dict(runtime_summary or {})
        active_carrier_id = (
            runtime_summary.get("active_runtime_carrier_id")
            or runtime_summary.get("runtime_carrier_id")
        )
        if active_carrier_id and active_carrier_id != binding.campaign_id:
            blockers.append("active conflicting runtime carrier exists")
        if _runtime_summary_active(runtime_summary):
            blockers.append("runtime is already active")
        if runtime_summary.get("active_trial_id") or runtime_summary.get("trial_started") is True:
            blockers.append("active conflicting runtime trial exists")
        if runtime_summary.get("strategy_active") is True:
            blockers.append("active strategy already exists")

        return _runtime_start_readiness_from_binding(
            binding=binding,
            blockers=blockers,
            warnings=warnings,
            decision=decision,
            constraint=constraint,
            campaign=campaign,
            idempotent_prepare=idempotent_prepare,
        )

    async def record_admission_runtime_start_ready(
        self,
        *,
        binding_id: str,
        campaign_id: str,
        operation_id: str,
        preflight_id: str,
        confirmed_by: str = "owner",
    ) -> AdmissionTrialBinding:
        binding = await self.get_admission_trial_binding(binding_id)
        if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
            raise AdmissionRuleViolation(
                f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
            )
        if binding.campaign_id != campaign_id:
            raise AdmissionRuleViolation("admission trial binding campaign_id mismatch")
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_RUNTIME_START_READY,
            ref_type="admission_trial_binding",
            ref_id=binding.binding_id,
            admission_decision_id=binding.admission_decision_id,
            actor=confirmed_by,
            message=(
                "Admission runtime start readiness metadata prepared. Runtime not started, "
                "strategy not active, auto execution disabled, trial inactive, and no order was placed."
            ),
            metadata={
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "campaign_id": campaign_id,
                "binding_status": binding.binding_status.value,
                "runtime_status": "runtime_start_ready_not_started",
                "runtime_start_ready": True,
            },
        )
        return binding

    async def build_runtime_handoff_preflight_readiness(
        self,
        input_params: dict[str, Any],
        *,
        campaign: Optional[Any] = None,
        runtime_summary: Optional[dict[str, Any]] = None,
        trade_intent_ledger_available: bool = True,
        now_ms_value: Optional[int] = None,
    ) -> dict[str, Any]:
        now_value = now_ms_value if now_ms_value is not None else _now_ms()
        blockers: list[str] = []
        warnings: list[str] = []
        binding_id = str(
            input_params.get("admission_binding_id")
            or input_params.get("binding_id")
            or ""
        ).strip()
        campaign_id = str(input_params.get("campaign_id") or _campaign_id(campaign) or "").strip()

        binding: Optional[AdmissionTrialBinding] = None
        if binding_id:
            binding = await self._repo.get_admission_trial_binding(binding_id)
            if binding is None:
                blockers.append(f"admission trial binding not found: {binding_id}")
        elif campaign_id:
            bindings = await self._repo.list_admission_trial_bindings(limit=500)
            binding = next((item for item in bindings if item.campaign_id == campaign_id), None)
            if binding is None:
                blockers.append(f"admission trial binding not found for campaign_id: {campaign_id}")
        else:
            blockers.append("admission_binding_id or campaign_id required")

        campaign_metadata = _campaign_metadata(campaign)
        actual_campaign_id = _campaign_id(campaign)
        if campaign is None:
            blockers.append("campaign not found")
        elif not campaign_metadata:
            blockers.append("campaign metadata missing")
        elif campaign_id and actual_campaign_id != campaign_id:
            blockers.append("campaign_id does not match current campaign")
        elif campaign_metadata.get("created_from_admission") is not True:
            blockers.append("campaign metadata is not admission-created")
        if not campaign_id and actual_campaign_id:
            campaign_id = actual_campaign_id

        if binding is not None:
            if binding.campaign_id != campaign_id:
                blockers.append("admission trial binding campaign_id mismatch")
            if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
                blockers.append(
                    f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
                )

        if campaign_metadata.get("carrier_ready") is not True:
            blockers.append("campaign metadata carrier_ready is not true")
        if campaign_metadata.get("runtime_start_ready") is not True:
            blockers.append("campaign metadata runtime_start_ready is not true")
        if campaign_metadata.get("constraints_installed") is not True:
            blockers.append("campaign metadata constraints_installed is not true")
        if campaign_metadata.get("runtime_started") is not False:
            blockers.append("campaign metadata runtime_started is not false")
        if campaign_metadata.get("strategy_active") is not False:
            blockers.append("campaign metadata strategy_active is not false")
        if campaign_metadata.get("trial_started") is not False:
            blockers.append("campaign metadata trial_started is not false")
        if campaign_metadata.get("orders_placed") is not False:
            blockers.append("campaign metadata orders_placed is not false")
        if campaign_metadata.get("auto_within_budget_enabled") is True:
            blockers.append("campaign metadata auto_within_budget_enabled is true")
        if campaign_metadata.get("owner_confirm_each_entry_enabled") is True:
            blockers.append("campaign metadata owner_confirm_each_entry_enabled is true")

        idempotent_prepare = (
            campaign_metadata.get("runtime_handoff_ready") is True
            and campaign_metadata.get("runtime_status") == "runtime_handoff_ready_not_started"
            and campaign_metadata.get("runtime_started") is False
            and campaign_metadata.get("strategy_active") is False
            and campaign_metadata.get("trial_started") is False
            and campaign_metadata.get("orders_placed") is False
        )
        if campaign_metadata.get("runtime_status") == "runtime_start_ready_not_started":
            pass
        elif idempotent_prepare:
            pass
        else:
            blockers.append("campaign metadata runtime_status is not runtime_start_ready_not_started")

        installed_snapshot_id = _optional_text(campaign_metadata.get("installed_constraint_snapshot_id"))
        if installed_snapshot_id is None:
            blockers.append("installed_constraint_snapshot_id missing")
        elif binding is not None and installed_snapshot_id != binding.trial_constraint_snapshot_id:
            blockers.append("installed_constraint_snapshot_id mismatch")
        constraint = (
            await self._repo.get_trial_constraint_snapshot(installed_snapshot_id)
            if installed_snapshot_id is not None
            else None
        )
        if constraint is None and installed_snapshot_id is not None:
            blockers.append(f"trial constraint snapshot not found: {installed_snapshot_id}")

        execution_mode_value = str(campaign_metadata.get("execution_mode") or "").strip()
        try:
            execution_mode = AdmissionExecutionMode(execution_mode_value)
        except ValueError:
            execution_mode = None
            blockers.append("campaign metadata execution_mode is missing or invalid")

        constraints_summary = dict(campaign_metadata.get("installed_constraints_summary") or {})
        completeness = _constraints_completeness(constraints_summary)
        if execution_mode in {AdmissionExecutionMode.OBSERVE_ONLY, AdmissionExecutionMode.NO_ENTRY}:
            if not trade_intent_ledger_available:
                blockers.append(f"{execution_mode.value} trade intent ledger support unavailable")
            else:
                warnings.append(f"{execution_mode.value} enforcement contract available as non-executable ledger only")
        elif execution_mode == AdmissionExecutionMode.AUTO_WITHIN_BUDGET:
            if not completeness["complete"]:
                blockers.append(
                    "auto_within_budget constraints incomplete: "
                    + ", ".join(completeness["missing"])
                )
            warnings.append("auto_within_budget actual execution remains disabled")
        elif execution_mode == AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY:
            blockers.append("owner_confirm_each_entry execution is reserved and not implemented")

        decision: Optional[AdmissionDecision] = None
        request: Optional[AdmissionRequest] = None
        if binding is not None:
            decision = await self._repo.get_admission_decision(binding.admission_decision_id)
            if decision is None:
                blockers.append(f"admission decision not found: {binding.admission_decision_id}")
            else:
                request = await self._repo.get_admission_request(decision.admission_request_id)
                if request is None:
                    blockers.append(f"admission request not found: {decision.admission_request_id}")
                if decision.expires_at_ms is not None and decision.expires_at_ms <= now_value:
                    blockers.append("admission decision expired")
        if request is not None:
            freshness_issue = _account_facts_freshness_issue(request.account_facts_snapshot_json)
            if freshness_issue is not None:
                blockers.append(freshness_issue)
            account_issue = _account_facts_issue(request.account_facts_snapshot_json)
            if binding is not None and binding.trial_env == TrialEnv.LIVE and binding.trial_stage == TrialStage.FUNDED_VALIDATION:
                if account_issue is not None:
                    blockers.append(account_issue)
            elif account_issue is not None:
                warnings.append(account_issue)

        runtime_summary = dict(runtime_summary or {})
        active_carrier_id = (
            runtime_summary.get("active_runtime_carrier_id")
            or runtime_summary.get("runtime_carrier_id")
        )
        if active_carrier_id and active_carrier_id != campaign_id:
            blockers.append("active conflicting runtime carrier exists")
        if _runtime_summary_active(runtime_summary):
            blockers.append("runtime is already active")
        if runtime_summary.get("active_trial_id") or runtime_summary.get("trial_started") is True:
            blockers.append("active conflicting runtime trial exists")

        return _runtime_handoff_readiness_from_context(
            campaign_id=campaign_id,
            binding=binding,
            blockers=blockers,
            warnings=warnings,
            decision=decision,
            constraint=constraint,
            campaign=campaign,
            constraints_completeness=completeness,
            execution_mode=execution_mode,
            idempotent_prepare=idempotent_prepare,
            trade_intent_ledger_available=trade_intent_ledger_available,
        )

    async def record_admission_runtime_handoff_ready(
        self,
        *,
        binding_id: str,
        campaign_id: str,
        operation_id: str,
        preflight_id: str,
        confirmed_by: str = "owner",
    ) -> AdmissionTrialBinding:
        binding = await self.get_admission_trial_binding(binding_id)
        if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
            raise AdmissionRuleViolation(
                f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
            )
        if binding.campaign_id != campaign_id:
            raise AdmissionRuleViolation("admission trial binding campaign_id mismatch")
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_RUNTIME_HANDOFF_READY,
            ref_type="admission_trial_binding",
            ref_id=binding.binding_id,
            admission_decision_id=binding.admission_decision_id,
            actor=confirmed_by,
            message=(
                "Admission runtime handoff readiness metadata prepared. Runtime not started, "
                "strategy not active, auto execution disabled, trial inactive, and no order was placed."
            ),
            metadata={
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "campaign_id": campaign_id,
                "binding_status": binding.binding_status.value,
                "runtime_status": "runtime_handoff_ready_not_started",
                "runtime_handoff_ready": True,
            },
        )
        return binding

    async def record_admission_runtime_started(
        self,
        *,
        binding_id: str,
        campaign_id: str,
        operation_id: str,
        preflight_id: str,
        confirmed_by: str = "owner",
    ) -> AdmissionTrialBinding:
        binding = await self.get_admission_trial_binding(binding_id)
        if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
            raise AdmissionRuleViolation(
                f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
            )
        if binding.campaign_id != campaign_id:
            raise AdmissionRuleViolation("admission trial binding campaign_id mismatch")
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_RUNTIME_STARTED,
            ref_type="admission_trial_binding",
            ref_id=binding.binding_id,
            admission_decision_id=binding.admission_decision_id,
            actor=confirmed_by,
            message=(
                "Admission runtime state started. Strategy remains inactive, auto execution disabled, "
                "trial not started, and no order was placed."
            ),
            metadata={
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "campaign_id": campaign_id,
                "binding_status": binding.binding_status.value,
                "runtime_status": "runtime_started_strategy_inactive",
                "runtime_started": True,
                "strategy_active": False,
                "trial_started": False,
                "orders_placed": False,
            },
        )
        return binding

    async def record_admission_strategy_activation_ready(
        self,
        *,
        binding_id: str,
        campaign_id: str,
        operation_id: str,
        preflight_id: str,
        confirmed_by: str = "owner",
    ) -> AdmissionTrialBinding:
        binding = await self.get_admission_trial_binding(binding_id)
        if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
            raise AdmissionRuleViolation(
                f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
            )
        if binding.campaign_id != campaign_id:
            raise AdmissionRuleViolation("admission trial binding campaign_id mismatch")
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_STRATEGY_ACTIVATION_READY,
            ref_type="admission_trial_binding",
            ref_id=binding.binding_id,
            admission_decision_id=binding.admission_decision_id,
            actor=confirmed_by,
            message=(
                "Admission strategy activation readiness metadata prepared. Strategy remains inactive, "
                "signal loop inactive, auto execution disabled, trial not started, and no order was placed."
            ),
            metadata={
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "campaign_id": campaign_id,
                "binding_status": binding.binding_status.value,
                "runtime_status": "strategy_activation_ready_not_active",
                "strategy_activation_ready": True,
                "runtime_started": True,
                "strategy_active": False,
                "trial_started": False,
                "auto_execution_enabled": False,
                "auto_within_budget_enabled": False,
                "orders_placed": False,
            },
        )
        return binding

    async def record_admission_strategy_activated_no_execution(
        self,
        *,
        binding_id: str,
        campaign_id: str,
        operation_id: str,
        preflight_id: str,
        confirmed_by: str = "owner",
    ) -> AdmissionTrialBinding:
        binding = await self.get_admission_trial_binding(binding_id)
        if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
            raise AdmissionRuleViolation(
                f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
            )
        if binding.campaign_id != campaign_id:
            raise AdmissionRuleViolation("admission trial binding campaign_id mismatch")
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_STRATEGY_ACTIVATED_NO_EXECUTION,
            ref_type="admission_trial_binding",
            ref_id=binding.binding_id,
            admission_decision_id=binding.admission_decision_id,
            actor=confirmed_by,
            message=(
                "Admission strategy state activated as non-execution metadata. Signal loop inactive, "
                "auto execution disabled, trial not started, and no order was placed."
            ),
            metadata={
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "campaign_id": campaign_id,
                "binding_status": binding.binding_status.value,
                "runtime_status": "strategy_active_no_execution",
                "strategy_state": "strategy_active_no_execution",
                "strategy_activation_state": "active_no_execution",
                "runtime_started": True,
                "strategy_active": True,
                "strategy_execution_enabled": False,
                "trial_started": False,
                "signal_loop_enabled": False,
                "signal_loop_started": False,
                "auto_execution_enabled": False,
                "auto_within_budget_enabled": False,
                "trade_intent_created": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
            },
        )
        return binding

    async def record_admission_signal_loop_ready(
        self,
        *,
        binding_id: str,
        campaign_id: str,
        operation_id: str,
        preflight_id: str,
        confirmed_by: str = "owner",
    ) -> AdmissionTrialBinding:
        binding = await self.get_admission_trial_binding(binding_id)
        if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
            raise AdmissionRuleViolation(
                f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
            )
        if binding.campaign_id != campaign_id:
            raise AdmissionRuleViolation("admission trial binding campaign_id mismatch")
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_SIGNAL_LOOP_READY,
            ref_type="admission_trial_binding",
            ref_id=binding.binding_id,
            admission_decision_id=binding.admission_decision_id,
            actor=confirmed_by,
            message=(
                "Admission signal loop readiness metadata prepared. Signal loop not started, "
                "no strategy signal generated, auto execution disabled, and no order was placed."
            ),
            metadata={
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "campaign_id": campaign_id,
                "binding_status": binding.binding_status.value,
                "runtime_status": "signal_loop_ready_not_started",
                "signal_loop_ready": True,
                "runtime_started": True,
                "strategy_active": True,
                "strategy_execution_enabled": False,
                "signal_loop_enabled": False,
                "signal_loop_started": False,
                "signal_generated": False,
                "trial_started": False,
                "auto_execution_enabled": False,
                "auto_within_budget_enabled": False,
                "trade_intent_created": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
            },
        )
        return binding

    async def record_admission_signal_loop_started_no_signal(
        self,
        *,
        binding_id: str,
        campaign_id: str,
        operation_id: str,
        preflight_id: str,
        confirmed_by: str = "owner",
    ) -> AdmissionTrialBinding:
        binding = await self.get_admission_trial_binding(binding_id)
        if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
            raise AdmissionRuleViolation(
                f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
            )
        if binding.campaign_id != campaign_id:
            raise AdmissionRuleViolation("admission trial binding campaign_id mismatch")
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_SIGNAL_LOOP_STARTED_NO_SIGNAL,
            ref_type="admission_trial_binding",
            ref_id=binding.binding_id,
            admission_decision_id=binding.admission_decision_id,
            actor=confirmed_by,
            message=(
                "Admission signal loop state started without signal generation. No trade intent, "
                "execution intent, order, auto execution, or trial trading was created."
            ),
            metadata={
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "campaign_id": campaign_id,
                "binding_status": binding.binding_status.value,
                "runtime_status": "signal_loop_started_no_signal",
                "signal_loop_ready": True,
                "signal_loop_enabled": True,
                "signal_loop_enabled_scope": "non_trading_loop_state",
                "signal_loop_started": True,
                "signal_generated": False,
                "runtime_started": True,
                "strategy_active": True,
                "strategy_execution_enabled": False,
                "trial_started": False,
                "auto_execution_enabled": False,
                "auto_within_budget_enabled": False,
                "trade_intent_created": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
            },
        )
        return binding

    async def record_admission_signal_evaluated_no_intent(
        self,
        *,
        binding_id: str,
        campaign_id: str,
        operation_id: str,
        preflight_id: str,
        confirmed_by: str = "owner",
    ) -> AdmissionTrialBinding:
        binding = await self.get_admission_trial_binding(binding_id)
        if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
            raise AdmissionRuleViolation(
                f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
            )
        if binding.campaign_id != campaign_id:
            raise AdmissionRuleViolation("admission trial binding campaign_id mismatch")
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_SIGNAL_EVALUATED_NO_INTENT,
            ref_type="admission_trial_binding",
            ref_id=binding.binding_id,
            admission_decision_id=binding.admission_decision_id,
            actor=confirmed_by,
            message=(
                "Admission strategy signal evaluation recorded without creating a trade intent, "
                "execution intent, order, auto execution, or trial trading."
            ),
            metadata={
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "campaign_id": campaign_id,
                "binding_status": binding.binding_status.value,
                "runtime_status": "signal_evaluated_no_intent",
                "signal_loop_started": True,
                "signal_loop_enabled": True,
                "signal_loop_enabled_scope": "non_trading_loop_state",
                "signal_evaluated": True,
                "signal_generated": True,
                "signal_is_trade_intent": False,
                "runtime_started": True,
                "strategy_active": True,
                "strategy_execution_enabled": False,
                "trial_started": False,
                "auto_execution_enabled": False,
                "auto_within_budget_enabled": False,
                "trade_intent_created": False,
                "execution_intent_created": False,
                "order_created": False,
                "orders_placed": False,
            },
        )
        return binding

    async def build_signal_evaluation_preflight_readiness(
        self,
        input_params: dict[str, Any],
        *,
        campaign: Optional[Any] = None,
        runtime_summary: Optional[dict[str, Any]] = None,
        now_ms_value: Optional[int] = None,
    ) -> dict[str, Any]:
        now_value = now_ms_value if now_ms_value is not None else _now_ms()
        blockers: list[str] = []
        warnings: list[str] = []
        binding_id = str(
            input_params.get("admission_binding_id")
            or input_params.get("binding_id")
            or ""
        ).strip()
        campaign_id = str(input_params.get("campaign_id") or _campaign_id(campaign) or "").strip()
        campaign_metadata = _campaign_metadata(campaign)
        actual_campaign_id = _campaign_id(campaign)

        binding: Optional[AdmissionTrialBinding] = None
        if binding_id:
            binding = await self._repo.get_admission_trial_binding(binding_id)
            if binding is None:
                blockers.append(f"admission trial binding not found: {binding_id}")
        elif campaign_id:
            bindings = await self._repo.list_admission_trial_bindings(limit=500)
            binding = next((item for item in bindings if item.campaign_id == campaign_id), None)
            if binding is None:
                blockers.append(f"admission trial binding not found for campaign_id: {campaign_id}")
        else:
            blockers.append("admission_binding_id or campaign_id required")

        if campaign is None:
            blockers.append("campaign not found")
        elif not campaign_metadata:
            blockers.append("campaign metadata missing")
        elif campaign_id and actual_campaign_id != campaign_id:
            blockers.append("campaign_id does not match current campaign")
        elif campaign_metadata.get("created_from_admission") is not True:
            blockers.append("campaign metadata is not admission-created")
        if not campaign_id and actual_campaign_id:
            campaign_id = actual_campaign_id

        if binding is not None:
            if binding.campaign_id != campaign_id:
                blockers.append("admission trial binding campaign_id mismatch")
            if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
                blockers.append(
                    f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
                )

        idempotent_evaluation = (
            campaign_metadata.get("runtime_status") == "signal_evaluated_no_intent"
            and campaign_metadata.get("signal_evaluated") is True
            and campaign_metadata.get("signal_generated") is True
            and campaign_metadata.get("trade_intent_created") is False
            and campaign_metadata.get("execution_intent_created") is False
            and campaign_metadata.get("order_created") is False
            and campaign_metadata.get("orders_placed") is False
            and campaign_metadata.get("trial_started") is False
            and campaign_metadata.get("auto_execution_enabled") is False
            and campaign_metadata.get("auto_within_budget_enabled") is False
        )

        if campaign_metadata.get("runtime_status") == "signal_loop_started_no_signal":
            pass
        elif idempotent_evaluation:
            pass
        else:
            blockers.append("campaign metadata runtime_status is not signal_loop_started_no_signal")
        if campaign_metadata.get("signal_loop_started") is not True:
            blockers.append("campaign metadata signal_loop_started is not true")
        if campaign_metadata.get("signal_loop_enabled_scope") != "non_trading_loop_state":
            blockers.append("campaign metadata signal_loop_enabled_scope is not non_trading_loop_state")
        if campaign_metadata.get("strategy_state") != "strategy_active_no_execution":
            blockers.append("campaign metadata strategy_state is not strategy_active_no_execution")
        if campaign_metadata.get("strategy_activation_state") != "active_no_execution":
            blockers.append("campaign metadata strategy_activation_state is not active_no_execution")
        if campaign_metadata.get("strategy_active") is not True:
            blockers.append("campaign metadata strategy_active is not true")

        if not idempotent_evaluation:
            required_false = {
                "strategy_execution_enabled": "campaign metadata strategy_execution_enabled is not false",
                "signal_generated": "campaign metadata signal_generated is not false",
                "signal_evaluated": "campaign metadata signal_evaluated is not false",
                "trade_intent_created": "campaign metadata trade_intent_created is not false",
                "execution_intent_created": "campaign metadata execution_intent_created is not false",
                "trial_started": "campaign metadata trial_started is not false",
                "orders_placed": "campaign metadata orders_placed is not false",
                "auto_execution_enabled": "campaign metadata auto_execution_enabled is not false",
                "auto_within_budget_enabled": "campaign metadata auto_within_budget_enabled is not false",
                "order_created": "campaign metadata order_created is not false",
            }
            for key, message in required_false.items():
                if key == "signal_evaluated" and campaign_metadata.get(key) is None:
                    continue
                if campaign_metadata.get(key) is not False:
                    blockers.append(message)
        if campaign_metadata.get("live_ready") is True:
            blockers.append("campaign metadata live_ready is true")

        strategy_family_version_id = _optional_text(campaign_metadata.get("strategy_family_version_id"))
        if strategy_family_version_id is None:
            blockers.append("strategy_family_version_id missing")
        playbook_id = _optional_text(campaign_metadata.get("playbook_id"))
        if playbook_id is None:
            blockers.append("playbook_id missing")
        installed_snapshot_id = _optional_text(campaign_metadata.get("installed_constraint_snapshot_id"))
        if installed_snapshot_id is None:
            blockers.append("installed_constraint_snapshot_id missing")
        constraint = (
            await self._repo.get_trial_constraint_snapshot(installed_snapshot_id)
            if installed_snapshot_id is not None
            else None
        )
        if constraint is None and installed_snapshot_id is not None:
            blockers.append(f"trial constraint snapshot not found: {installed_snapshot_id}")

        execution_mode_value = str(campaign_metadata.get("execution_mode") or "").strip()
        try:
            execution_mode = AdmissionExecutionMode(execution_mode_value)
        except ValueError:
            execution_mode = None
            blockers.append("campaign metadata execution_mode is missing or invalid")
        if execution_mode == AdmissionExecutionMode.AUTO_WITHIN_BUDGET:
            warnings.append("auto_within_budget actual execution remains disabled")
        elif execution_mode in {AdmissionExecutionMode.OBSERVE_ONLY, AdmissionExecutionMode.NO_ENTRY}:
            warnings.append(f"{execution_mode.value} trade intent conversion remains a separate phase")
        elif execution_mode == AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY:
            blockers.append("owner_confirm_each_entry execution is reserved and not implemented")

        decision: Optional[AdmissionDecision] = None
        request: Optional[AdmissionRequest] = None
        if binding is not None:
            decision = await self._repo.get_admission_decision(binding.admission_decision_id)
            if decision is None:
                blockers.append(f"admission decision not found: {binding.admission_decision_id}")
            else:
                request = await self._repo.get_admission_request(decision.admission_request_id)
                if request is None:
                    blockers.append(f"admission request not found: {decision.admission_request_id}")
                if decision.expires_at_ms is not None and decision.expires_at_ms <= now_value:
                    blockers.append("admission decision expired")
        if request is not None:
            freshness_issue = _account_facts_freshness_issue(request.account_facts_snapshot_json)
            if freshness_issue is not None:
                blockers.append(freshness_issue)
            account_issue = _account_facts_issue(request.account_facts_snapshot_json)
            if binding is not None and binding.trial_env == TrialEnv.LIVE and binding.trial_stage == TrialStage.FUNDED_VALIDATION:
                if account_issue is not None:
                    blockers.append(account_issue)
            elif account_issue is not None:
                warnings.append(account_issue)

        runtime_summary = dict(runtime_summary or {})
        if runtime_summary.get("strategy_execution_enabled") is True:
            blockers.append("runtime strategy execution is already enabled")
        if runtime_summary.get("active_trial_id") or runtime_summary.get("trial_started") is True:
            blockers.append("active conflicting runtime trial exists")
        runtime_state = str(
            runtime_summary.get("current_runtime_state")
            or runtime_summary.get("runtime_state")
            or ""
        ).lower()
        if runtime_state in {"hard_locked", "hard_lock", "emergency_stopped", "emergency_stop", "flatten_required"}:
            blockers.append("emergency stop or hard lock is active")
        if runtime_summary.get("live_ready") is True:
            blockers.append("runtime live_ready is true; live execution path is not authorized")

        return _signal_evaluation_readiness_from_context(
            campaign_id=campaign_id,
            binding=binding,
            blockers=blockers,
            warnings=warnings,
            decision=decision,
            constraint=constraint,
            campaign=campaign,
            execution_mode=execution_mode,
            idempotent_evaluation=idempotent_evaluation,
            signal_snapshot=input_params.get("signal_snapshot"),
            signal_evaluation_input=input_params.get("signal_evaluation_input"),
        )

    async def build_signal_loop_start_preflight_readiness(
        self,
        input_params: dict[str, Any],
        *,
        campaign: Optional[Any] = None,
        runtime_summary: Optional[dict[str, Any]] = None,
        now_ms_value: Optional[int] = None,
    ) -> dict[str, Any]:
        now_value = now_ms_value if now_ms_value is not None else _now_ms()
        blockers: list[str] = []
        warnings: list[str] = []
        binding_id = str(
            input_params.get("admission_binding_id")
            or input_params.get("binding_id")
            or ""
        ).strip()
        campaign_id = str(input_params.get("campaign_id") or _campaign_id(campaign) or "").strip()
        campaign_metadata = _campaign_metadata(campaign)
        actual_campaign_id = _campaign_id(campaign)

        binding: Optional[AdmissionTrialBinding] = None
        if binding_id:
            binding = await self._repo.get_admission_trial_binding(binding_id)
            if binding is None:
                blockers.append(f"admission trial binding not found: {binding_id}")
        elif campaign_id:
            bindings = await self._repo.list_admission_trial_bindings(limit=500)
            binding = next((item for item in bindings if item.campaign_id == campaign_id), None)
            if binding is None:
                blockers.append(f"admission trial binding not found for campaign_id: {campaign_id}")
        else:
            blockers.append("admission_binding_id or campaign_id required")

        if campaign is None:
            blockers.append("campaign not found")
        elif not campaign_metadata:
            blockers.append("campaign metadata missing")
        elif campaign_id and actual_campaign_id != campaign_id:
            blockers.append("campaign_id does not match current campaign")
        elif campaign_metadata.get("created_from_admission") is not True:
            blockers.append("campaign metadata is not admission-created")
        if not campaign_id and actual_campaign_id:
            campaign_id = actual_campaign_id

        if binding is not None:
            if binding.campaign_id != campaign_id:
                blockers.append("admission trial binding campaign_id mismatch")
            if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
                blockers.append(
                    f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
                )

        idempotent_start = (
            campaign_metadata.get("runtime_status") == "signal_loop_started_no_signal"
            and campaign_metadata.get("signal_loop_ready") is True
            and campaign_metadata.get("signal_loop_enabled") is True
            and campaign_metadata.get("signal_loop_enabled_scope") == "non_trading_loop_state"
            and campaign_metadata.get("signal_loop_started") is True
            and campaign_metadata.get("signal_generated") is False
            and campaign_metadata.get("trade_intent_created") is False
            and campaign_metadata.get("execution_intent_created") is False
            and campaign_metadata.get("order_created") is False
            and campaign_metadata.get("orders_placed") is False
            and campaign_metadata.get("trial_started") is False
            and campaign_metadata.get("auto_execution_enabled") is False
            and campaign_metadata.get("auto_within_budget_enabled") is False
        )

        if campaign_metadata.get("runtime_status") == "signal_loop_ready_not_started":
            pass
        elif idempotent_start:
            pass
        else:
            blockers.append("campaign metadata runtime_status is not signal_loop_ready_not_started")
        if campaign_metadata.get("signal_loop_ready") is not True:
            blockers.append("campaign metadata signal_loop_ready is not true")
        if campaign_metadata.get("strategy_state") != "strategy_active_no_execution":
            blockers.append("campaign metadata strategy_state is not strategy_active_no_execution")
        if campaign_metadata.get("strategy_activation_state") != "active_no_execution":
            blockers.append("campaign metadata strategy_activation_state is not active_no_execution")
        if campaign_metadata.get("strategy_active") is not True:
            blockers.append("campaign metadata strategy_active is not true")

        if not idempotent_start:
            required_false = {
                "strategy_execution_enabled": "campaign metadata strategy_execution_enabled is not false",
                "signal_loop_enabled": "campaign metadata signal_loop_enabled is not false",
                "signal_loop_started": "campaign metadata signal_loop_started is not false",
                "signal_generated": "campaign metadata signal_generated is not false",
                "trade_intent_created": "campaign metadata trade_intent_created is not false",
                "execution_intent_created": "campaign metadata execution_intent_created is not false",
                "trial_started": "campaign metadata trial_started is not false",
                "orders_placed": "campaign metadata orders_placed is not false",
                "auto_execution_enabled": "campaign metadata auto_execution_enabled is not false",
                "auto_within_budget_enabled": "campaign metadata auto_within_budget_enabled is not false",
                "order_created": "campaign metadata order_created is not false",
            }
            for key, message in required_false.items():
                if campaign_metadata.get(key) is not False:
                    blockers.append(message)
        if campaign_metadata.get("live_ready") is True:
            blockers.append("campaign metadata live_ready is true")

        strategy_family_version_id = _optional_text(campaign_metadata.get("strategy_family_version_id"))
        if strategy_family_version_id is None:
            blockers.append("strategy_family_version_id missing")
        playbook_id = _optional_text(campaign_metadata.get("playbook_id"))
        if playbook_id is None:
            blockers.append("playbook_id missing")
        installed_snapshot_id = _optional_text(campaign_metadata.get("installed_constraint_snapshot_id"))
        if installed_snapshot_id is None:
            blockers.append("installed_constraint_snapshot_id missing")
        constraint = (
            await self._repo.get_trial_constraint_snapshot(installed_snapshot_id)
            if installed_snapshot_id is not None
            else None
        )
        if constraint is None and installed_snapshot_id is not None:
            blockers.append(f"trial constraint snapshot not found: {installed_snapshot_id}")

        execution_mode_value = str(campaign_metadata.get("execution_mode") or "").strip()
        try:
            execution_mode = AdmissionExecutionMode(execution_mode_value)
        except ValueError:
            execution_mode = None
            blockers.append("campaign metadata execution_mode is missing or invalid")
        if execution_mode == AdmissionExecutionMode.AUTO_WITHIN_BUDGET:
            warnings.append("auto_within_budget actual execution remains disabled")
        elif execution_mode in {AdmissionExecutionMode.OBSERVE_ONLY, AdmissionExecutionMode.NO_ENTRY}:
            warnings.append(f"{execution_mode.value} actual intent behavior remains a separate phase")
        elif execution_mode == AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY:
            blockers.append("owner_confirm_each_entry execution is reserved and not implemented")

        decision: Optional[AdmissionDecision] = None
        request: Optional[AdmissionRequest] = None
        if binding is not None:
            decision = await self._repo.get_admission_decision(binding.admission_decision_id)
            if decision is None:
                blockers.append(f"admission decision not found: {binding.admission_decision_id}")
            else:
                request = await self._repo.get_admission_request(decision.admission_request_id)
                if request is None:
                    blockers.append(f"admission request not found: {decision.admission_request_id}")
                if decision.expires_at_ms is not None and decision.expires_at_ms <= now_value:
                    blockers.append("admission decision expired")
        if request is not None:
            freshness_issue = _account_facts_freshness_issue(request.account_facts_snapshot_json)
            if freshness_issue is not None:
                blockers.append(freshness_issue)
            account_issue = _account_facts_issue(request.account_facts_snapshot_json)
            if binding is not None and binding.trial_env == TrialEnv.LIVE and binding.trial_stage == TrialStage.FUNDED_VALIDATION:
                if account_issue is not None:
                    blockers.append(account_issue)
            elif account_issue is not None:
                warnings.append(account_issue)

        runtime_summary = dict(runtime_summary or {})
        if not idempotent_start and (
            runtime_summary.get("signal_loop_enabled") is True
            or runtime_summary.get("signal_loop_started") is True
        ):
            blockers.append("active signal loop conflict exists")
        if runtime_summary.get("strategy_execution_enabled") is True:
            blockers.append("runtime strategy execution is already enabled")
        if runtime_summary.get("active_trial_id") or runtime_summary.get("trial_started") is True:
            blockers.append("active conflicting runtime trial exists")
        runtime_state = str(
            runtime_summary.get("current_runtime_state")
            or runtime_summary.get("runtime_state")
            or ""
        ).lower()
        if runtime_state in {"hard_locked", "hard_lock", "emergency_stopped", "emergency_stop", "flatten_required"}:
            blockers.append("emergency stop or hard lock is active")
        if runtime_summary.get("live_ready") is True:
            blockers.append("runtime live_ready is true; live execution path is not authorized")

        return _signal_loop_start_readiness_from_context(
            campaign_id=campaign_id,
            binding=binding,
            blockers=blockers,
            warnings=warnings,
            decision=decision,
            constraint=constraint,
            campaign=campaign,
            execution_mode=execution_mode,
            idempotent_start=idempotent_start,
        )

    async def build_signal_loop_preflight_readiness(
        self,
        input_params: dict[str, Any],
        *,
        campaign: Optional[Any] = None,
        runtime_summary: Optional[dict[str, Any]] = None,
        now_ms_value: Optional[int] = None,
    ) -> dict[str, Any]:
        now_value = now_ms_value if now_ms_value is not None else _now_ms()
        blockers: list[str] = []
        warnings: list[str] = []
        binding_id = str(
            input_params.get("admission_binding_id")
            or input_params.get("binding_id")
            or ""
        ).strip()
        campaign_id = str(input_params.get("campaign_id") or _campaign_id(campaign) or "").strip()
        campaign_metadata = _campaign_metadata(campaign)
        actual_campaign_id = _campaign_id(campaign)

        binding: Optional[AdmissionTrialBinding] = None
        if binding_id:
            binding = await self._repo.get_admission_trial_binding(binding_id)
            if binding is None:
                blockers.append(f"admission trial binding not found: {binding_id}")
        elif campaign_id:
            bindings = await self._repo.list_admission_trial_bindings(limit=500)
            binding = next((item for item in bindings if item.campaign_id == campaign_id), None)
            if binding is None:
                blockers.append(f"admission trial binding not found for campaign_id: {campaign_id}")
        else:
            blockers.append("admission_binding_id or campaign_id required")

        if campaign is None:
            blockers.append("campaign not found")
        elif not campaign_metadata:
            blockers.append("campaign metadata missing")
        elif campaign_id and actual_campaign_id != campaign_id:
            blockers.append("campaign_id does not match current campaign")
        elif campaign_metadata.get("created_from_admission") is not True:
            blockers.append("campaign metadata is not admission-created")
        if not campaign_id and actual_campaign_id:
            campaign_id = actual_campaign_id

        if binding is not None:
            if binding.campaign_id != campaign_id:
                blockers.append("admission trial binding campaign_id mismatch")
            if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
                blockers.append(
                    f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
                )

        idempotent_prepare = (
            campaign_metadata.get("signal_loop_ready") is True
            and campaign_metadata.get("runtime_status") == "signal_loop_ready_not_started"
            and campaign_metadata.get("runtime_started") is True
            and campaign_metadata.get("strategy_active") is True
            and campaign_metadata.get("strategy_execution_enabled") is False
            and campaign_metadata.get("signal_loop_enabled") is False
            and campaign_metadata.get("signal_loop_started") is False
            and campaign_metadata.get("signal_generated") is False
            and campaign_metadata.get("trial_started") is False
            and campaign_metadata.get("orders_placed") is False
            and campaign_metadata.get("auto_execution_enabled") is False
            and campaign_metadata.get("auto_within_budget_enabled") is False
            and campaign_metadata.get("trade_intent_created") is False
            and campaign_metadata.get("execution_intent_created") is False
            and campaign_metadata.get("order_created") is False
        )

        if campaign_metadata.get("runtime_status") == "strategy_active_no_execution":
            pass
        elif idempotent_prepare:
            pass
        else:
            blockers.append("campaign metadata runtime_status is not strategy_active_no_execution")
        if campaign_metadata.get("strategy_activation_state") != "active_no_execution":
            blockers.append("campaign metadata strategy_activation_state is not active_no_execution")
        if campaign_metadata.get("strategy_state") != "strategy_active_no_execution":
            blockers.append("campaign metadata strategy_state is not strategy_active_no_execution")
        if campaign_metadata.get("strategy_active") is not True:
            blockers.append("campaign metadata strategy_active is not true")

        strict_false = {
            "strategy_execution_enabled": "campaign metadata strategy_execution_enabled is not false",
            "signal_loop_enabled": "campaign metadata signal_loop_enabled is not false",
            "signal_loop_started": "campaign metadata signal_loop_started is not false",
            "trial_started": "campaign metadata trial_started is not false",
            "orders_placed": "campaign metadata orders_placed is not false",
            "execution_intent_created": "campaign metadata execution_intent_created is not false",
            "auto_execution_enabled": "campaign metadata auto_execution_enabled is not false",
            "auto_within_budget_enabled": "campaign metadata auto_within_budget_enabled is not false",
            "trade_intent_created": "campaign metadata trade_intent_created is not false",
            "order_created": "campaign metadata order_created is not false",
        }
        for key, message in strict_false.items():
            if campaign_metadata.get(key) is not False:
                blockers.append(message)
        if campaign_metadata.get("signal_generated") is True:
            blockers.append("campaign metadata signal_generated is true")
        if campaign_metadata.get("live_ready") is True:
            blockers.append("campaign metadata live_ready is true")

        strategy_family_version_id = _optional_text(campaign_metadata.get("strategy_family_version_id"))
        if strategy_family_version_id is None:
            blockers.append("strategy_family_version_id missing")
        playbook_id = _optional_text(campaign_metadata.get("playbook_id"))
        if playbook_id is None:
            blockers.append("playbook_id missing")
        installed_snapshot_id = _optional_text(campaign_metadata.get("installed_constraint_snapshot_id"))
        if installed_snapshot_id is None:
            blockers.append("installed_constraint_snapshot_id missing")
        constraint = (
            await self._repo.get_trial_constraint_snapshot(installed_snapshot_id)
            if installed_snapshot_id is not None
            else None
        )
        if constraint is None and installed_snapshot_id is not None:
            blockers.append(f"trial constraint snapshot not found: {installed_snapshot_id}")

        execution_mode_value = str(campaign_metadata.get("execution_mode") or "").strip()
        try:
            execution_mode = AdmissionExecutionMode(execution_mode_value)
        except ValueError:
            execution_mode = None
            blockers.append("campaign metadata execution_mode is missing or invalid")
        if execution_mode == AdmissionExecutionMode.AUTO_WITHIN_BUDGET:
            warnings.append("auto_within_budget actual execution remains disabled")
        elif execution_mode in {AdmissionExecutionMode.OBSERVE_ONLY, AdmissionExecutionMode.NO_ENTRY}:
            warnings.append(f"{execution_mode.value} actual intent behavior remains a separate phase")
        elif execution_mode == AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY:
            blockers.append("owner_confirm_each_entry execution is reserved and not implemented")

        decision: Optional[AdmissionDecision] = None
        request: Optional[AdmissionRequest] = None
        if binding is not None:
            decision = await self._repo.get_admission_decision(binding.admission_decision_id)
            if decision is None:
                blockers.append(f"admission decision not found: {binding.admission_decision_id}")
            else:
                request = await self._repo.get_admission_request(decision.admission_request_id)
                if request is None:
                    blockers.append(f"admission request not found: {decision.admission_request_id}")
                if decision.expires_at_ms is not None and decision.expires_at_ms <= now_value:
                    blockers.append("admission decision expired")
        if request is not None:
            freshness_issue = _account_facts_freshness_issue(request.account_facts_snapshot_json)
            if freshness_issue is not None:
                blockers.append(freshness_issue)
            account_issue = _account_facts_issue(request.account_facts_snapshot_json)
            if binding is not None and binding.trial_env == TrialEnv.LIVE and binding.trial_stage == TrialStage.FUNDED_VALIDATION:
                if account_issue is not None:
                    blockers.append(account_issue)
            elif account_issue is not None:
                warnings.append(account_issue)

        runtime_summary = dict(runtime_summary or {})
        if runtime_summary.get("signal_loop_enabled") is True or runtime_summary.get("signal_loop_started") is True:
            blockers.append("active signal loop conflict exists")
        if runtime_summary.get("strategy_execution_enabled") is True:
            blockers.append("runtime strategy execution is already enabled")
        if runtime_summary.get("active_trial_id") or runtime_summary.get("trial_started") is True:
            blockers.append("active conflicting runtime trial exists")
        runtime_state = str(
            runtime_summary.get("current_runtime_state")
            or runtime_summary.get("runtime_state")
            or ""
        ).lower()
        if runtime_state in {"hard_locked", "hard_lock", "emergency_stopped", "emergency_stop", "flatten_required"}:
            blockers.append("emergency stop or hard lock is active")
        if runtime_summary.get("live_ready") is True:
            blockers.append("runtime live_ready is true; live execution path is not authorized")

        return _signal_loop_readiness_from_context(
            campaign_id=campaign_id,
            binding=binding,
            blockers=blockers,
            warnings=warnings,
            decision=decision,
            constraint=constraint,
            campaign=campaign,
            execution_mode=execution_mode,
            idempotent_prepare=idempotent_prepare,
        )

    async def build_strategy_state_activation_preflight_readiness(
        self,
        input_params: dict[str, Any],
        *,
        campaign: Optional[Any] = None,
        runtime_summary: Optional[dict[str, Any]] = None,
        now_ms_value: Optional[int] = None,
    ) -> dict[str, Any]:
        now_value = now_ms_value if now_ms_value is not None else _now_ms()
        blockers: list[str] = []
        warnings: list[str] = []
        binding_id = str(
            input_params.get("admission_binding_id")
            or input_params.get("binding_id")
            or ""
        ).strip()
        campaign_id = str(input_params.get("campaign_id") or _campaign_id(campaign) or "").strip()
        campaign_metadata = _campaign_metadata(campaign)
        actual_campaign_id = _campaign_id(campaign)

        binding: Optional[AdmissionTrialBinding] = None
        if binding_id:
            binding = await self._repo.get_admission_trial_binding(binding_id)
            if binding is None:
                blockers.append(f"admission trial binding not found: {binding_id}")
        elif campaign_id:
            bindings = await self._repo.list_admission_trial_bindings(limit=500)
            binding = next((item for item in bindings if item.campaign_id == campaign_id), None)
            if binding is None:
                blockers.append(f"admission trial binding not found for campaign_id: {campaign_id}")
        else:
            blockers.append("admission_binding_id or campaign_id required")

        if campaign is None:
            blockers.append("campaign not found")
        elif not campaign_metadata:
            blockers.append("campaign metadata missing")
        elif campaign_id and actual_campaign_id != campaign_id:
            blockers.append("campaign_id does not match current campaign")
        elif campaign_metadata.get("created_from_admission") is not True:
            blockers.append("campaign metadata is not admission-created")
        if not campaign_id and actual_campaign_id:
            campaign_id = actual_campaign_id

        if binding is not None:
            if binding.campaign_id != campaign_id:
                blockers.append("admission trial binding campaign_id mismatch")
            if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
                blockers.append(
                    f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
                )

        idempotent_activate = (
            campaign_metadata.get("strategy_state") == "strategy_active_no_execution"
            and campaign_metadata.get("strategy_activation_state") == "active_no_execution"
            and campaign_metadata.get("runtime_status") == "strategy_active_no_execution"
            and campaign_metadata.get("runtime_started") is True
            and campaign_metadata.get("strategy_active") is True
            and campaign_metadata.get("strategy_execution_enabled") is False
            and campaign_metadata.get("signal_loop_enabled") is False
            and campaign_metadata.get("signal_loop_started") is False
            and campaign_metadata.get("trial_started") is False
            and campaign_metadata.get("orders_placed") is False
            and campaign_metadata.get("auto_execution_enabled") is False
            and campaign_metadata.get("auto_within_budget_enabled") is False
            and campaign_metadata.get("execution_intent_created") is False
        )

        if campaign_metadata.get("runtime_started") is not True:
            blockers.append("campaign metadata runtime_started is not true")
        if campaign_metadata.get("strategy_activation_ready") is not True:
            blockers.append("campaign metadata strategy_activation_ready is not true")
        if campaign_metadata.get("runtime_status") == "strategy_activation_ready_not_active":
            pass
        elif idempotent_activate:
            pass
        else:
            blockers.append("campaign metadata runtime_status is not strategy_activation_ready_not_active")
        if campaign_metadata.get("strategy_active") is not False and not idempotent_activate:
            blockers.append("campaign metadata strategy_active is not false")

        strict_false = {
            "trial_started": "campaign metadata trial_started is not false",
            "orders_placed": "campaign metadata orders_placed is not false",
            "auto_execution_enabled": "campaign metadata auto_execution_enabled is not false",
            "auto_within_budget_enabled": "campaign metadata auto_within_budget_enabled is not false",
        }
        for key, message in strict_false.items():
            if campaign_metadata.get(key) is not False:
                blockers.append(message)
        order_capable_true = {
            "strategy_execution_enabled": "campaign metadata strategy_execution_enabled is true",
            "signal_loop_enabled": "campaign metadata signal_loop_enabled is true",
            "signal_loop_started": "campaign metadata signal_loop_started is true",
            "trade_intent_created": "campaign metadata trade_intent_created is true",
            "execution_intent_created": "campaign metadata execution_intent_created is true",
            "order_created": "campaign metadata order_created is true",
        }
        for key, message in order_capable_true.items():
            if campaign_metadata.get(key) is True:
                blockers.append(message)
        if campaign_metadata.get("live_ready") is True:
            blockers.append("campaign metadata live_ready is true")

        strategy_family_version_id = _optional_text(campaign_metadata.get("strategy_family_version_id"))
        if strategy_family_version_id is None:
            blockers.append("strategy_family_version_id missing")
        playbook_id = _optional_text(campaign_metadata.get("playbook_id"))
        if playbook_id is None:
            blockers.append("playbook_id missing")
        installed_snapshot_id = _optional_text(campaign_metadata.get("installed_constraint_snapshot_id"))
        if installed_snapshot_id is None:
            blockers.append("installed_constraint_snapshot_id missing")
        constraint = (
            await self._repo.get_trial_constraint_snapshot(installed_snapshot_id)
            if installed_snapshot_id is not None
            else None
        )
        if constraint is None and installed_snapshot_id is not None:
            blockers.append(f"trial constraint snapshot not found: {installed_snapshot_id}")

        execution_mode_value = str(campaign_metadata.get("execution_mode") or "").strip()
        try:
            execution_mode = AdmissionExecutionMode(execution_mode_value)
        except ValueError:
            execution_mode = None
            blockers.append("campaign metadata execution_mode is missing or invalid")
        if execution_mode == AdmissionExecutionMode.AUTO_WITHIN_BUDGET:
            warnings.append("auto_within_budget actual execution remains disabled")
        elif execution_mode in {AdmissionExecutionMode.OBSERVE_ONLY, AdmissionExecutionMode.NO_ENTRY}:
            warnings.append(f"{execution_mode.value} enforcement remains non-executable skeleton")
        elif execution_mode == AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY:
            blockers.append("owner_confirm_each_entry execution is reserved and not implemented")

        decision: Optional[AdmissionDecision] = None
        request: Optional[AdmissionRequest] = None
        if binding is not None:
            decision = await self._repo.get_admission_decision(binding.admission_decision_id)
            if decision is None:
                blockers.append(f"admission decision not found: {binding.admission_decision_id}")
            else:
                request = await self._repo.get_admission_request(decision.admission_request_id)
                if request is None:
                    blockers.append(f"admission request not found: {decision.admission_request_id}")
                if decision.expires_at_ms is not None and decision.expires_at_ms <= now_value:
                    blockers.append("admission decision expired")
        if request is not None:
            freshness_issue = _account_facts_freshness_issue(request.account_facts_snapshot_json)
            if freshness_issue is not None:
                blockers.append(freshness_issue)
            account_issue = _account_facts_issue(request.account_facts_snapshot_json)
            if binding is not None and binding.trial_env == TrialEnv.LIVE and binding.trial_stage == TrialStage.FUNDED_VALIDATION:
                if account_issue is not None:
                    blockers.append(account_issue)
            elif account_issue is not None:
                warnings.append(account_issue)

        runtime_summary = dict(runtime_summary or {})
        if runtime_summary.get("active_strategy_id") and not idempotent_activate:
            blockers.append("active strategy conflict exists")
        if runtime_summary.get("strategy_execution_enabled") is True:
            blockers.append("runtime strategy execution is already enabled")
        if runtime_summary.get("signal_loop_enabled") is True or runtime_summary.get("signal_loop_started") is True:
            blockers.append("runtime signal loop is already enabled")
        if runtime_summary.get("active_trial_id") or runtime_summary.get("trial_started") is True:
            blockers.append("active conflicting runtime trial exists")
        runtime_state = str(
            runtime_summary.get("current_runtime_state")
            or runtime_summary.get("runtime_state")
            or ""
        ).lower()
        if runtime_state in {"hard_locked", "hard_lock", "emergency_stopped", "emergency_stop", "flatten_required"}:
            blockers.append("emergency stop or hard lock is active")
        if runtime_summary.get("live_ready") is True:
            blockers.append("runtime live_ready is true; live execution path is not authorized")

        return _strategy_state_activation_readiness_from_context(
            campaign_id=campaign_id,
            binding=binding,
            blockers=blockers,
            warnings=warnings,
            decision=decision,
            constraint=constraint,
            campaign=campaign,
            execution_mode=execution_mode,
            idempotent_activate=idempotent_activate,
        )

    async def build_strategy_activation_preflight_readiness(
        self,
        input_params: dict[str, Any],
        *,
        campaign: Optional[Any] = None,
        runtime_summary: Optional[dict[str, Any]] = None,
        now_ms_value: Optional[int] = None,
    ) -> dict[str, Any]:
        now_value = now_ms_value if now_ms_value is not None else _now_ms()
        blockers: list[str] = []
        warnings: list[str] = []
        binding_id = str(
            input_params.get("admission_binding_id")
            or input_params.get("binding_id")
            or ""
        ).strip()
        campaign_id = str(input_params.get("campaign_id") or _campaign_id(campaign) or "").strip()
        campaign_metadata = _campaign_metadata(campaign)
        actual_campaign_id = _campaign_id(campaign)

        binding: Optional[AdmissionTrialBinding] = None
        if binding_id:
            binding = await self._repo.get_admission_trial_binding(binding_id)
            if binding is None:
                blockers.append(f"admission trial binding not found: {binding_id}")
        elif campaign_id:
            bindings = await self._repo.list_admission_trial_bindings(limit=500)
            binding = next((item for item in bindings if item.campaign_id == campaign_id), None)
            if binding is None:
                blockers.append(f"admission trial binding not found for campaign_id: {campaign_id}")
        else:
            blockers.append("admission_binding_id or campaign_id required")

        if campaign is None:
            blockers.append("campaign not found")
        elif not campaign_metadata:
            blockers.append("campaign metadata missing")
        elif campaign_id and actual_campaign_id != campaign_id:
            blockers.append("campaign_id does not match current campaign")
        elif campaign_metadata.get("created_from_admission") is not True:
            blockers.append("campaign metadata is not admission-created")
        if not campaign_id and actual_campaign_id:
            campaign_id = actual_campaign_id

        if binding is not None:
            if binding.campaign_id != campaign_id:
                blockers.append("admission trial binding campaign_id mismatch")
            if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
                blockers.append(
                    f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
                )

        idempotent_prepare = (
            campaign_metadata.get("strategy_activation_ready") is True
            and campaign_metadata.get("runtime_status") == "strategy_activation_ready_not_active"
            and campaign_metadata.get("runtime_started") is True
            and campaign_metadata.get("strategy_active") is False
            and campaign_metadata.get("trial_started") is False
            and campaign_metadata.get("orders_placed") is False
            and campaign_metadata.get("auto_execution_enabled") is not True
            and campaign_metadata.get("auto_within_budget_enabled") is not True
        )

        if campaign_metadata.get("runtime_started") is not True:
            blockers.append("campaign metadata runtime_started is not true")
        if campaign_metadata.get("runtime_status") == "runtime_started_strategy_inactive":
            pass
        elif idempotent_prepare:
            pass
        else:
            blockers.append("campaign metadata runtime_status is not runtime_started_strategy_inactive")
        required_false = {
            "strategy_active": "campaign metadata strategy_active is not false",
            "trial_started": "campaign metadata trial_started is not false",
            "orders_placed": "campaign metadata orders_placed is not false",
            "auto_execution_enabled": "campaign metadata auto_execution_enabled is not false",
            "auto_within_budget_enabled": "campaign metadata auto_within_budget_enabled is not false",
        }
        for key, message in required_false.items():
            if campaign_metadata.get(key) is not False:
                blockers.append(message)
        if campaign_metadata.get("live_ready") is True:
            blockers.append("campaign metadata live_ready is true")
        if campaign_metadata.get("signal_loop_started") is True:
            blockers.append("campaign metadata signal_loop_started is true")

        strategy_family_version_id = _optional_text(campaign_metadata.get("strategy_family_version_id"))
        if strategy_family_version_id is None:
            blockers.append("strategy_family_version_id missing")
        playbook_id = _optional_text(campaign_metadata.get("playbook_id"))
        if playbook_id is None:
            blockers.append("playbook_id missing")
        installed_snapshot_id = _optional_text(campaign_metadata.get("installed_constraint_snapshot_id"))
        if installed_snapshot_id is None:
            blockers.append("installed_constraint_snapshot_id missing")
        constraint = (
            await self._repo.get_trial_constraint_snapshot(installed_snapshot_id)
            if installed_snapshot_id is not None
            else None
        )
        if constraint is None and installed_snapshot_id is not None:
            blockers.append(f"trial constraint snapshot not found: {installed_snapshot_id}")

        execution_mode_value = str(campaign_metadata.get("execution_mode") or "").strip()
        try:
            execution_mode = AdmissionExecutionMode(execution_mode_value)
        except ValueError:
            execution_mode = None
            blockers.append("campaign metadata execution_mode is missing or invalid")
        if execution_mode == AdmissionExecutionMode.AUTO_WITHIN_BUDGET:
            warnings.append("auto_within_budget actual execution remains disabled")
        elif execution_mode in {AdmissionExecutionMode.OBSERVE_ONLY, AdmissionExecutionMode.NO_ENTRY}:
            warnings.append(f"{execution_mode.value} enforcement remains non-executable skeleton")
        elif execution_mode == AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY:
            blockers.append("owner_confirm_each_entry execution is reserved and not implemented")

        decision: Optional[AdmissionDecision] = None
        request: Optional[AdmissionRequest] = None
        if binding is not None:
            decision = await self._repo.get_admission_decision(binding.admission_decision_id)
            if decision is None:
                blockers.append(f"admission decision not found: {binding.admission_decision_id}")
            else:
                request = await self._repo.get_admission_request(decision.admission_request_id)
                if request is None:
                    blockers.append(f"admission request not found: {decision.admission_request_id}")
                if decision.expires_at_ms is not None and decision.expires_at_ms <= now_value:
                    blockers.append("admission decision expired")
        if request is not None:
            freshness_issue = _account_facts_freshness_issue(request.account_facts_snapshot_json)
            if freshness_issue is not None:
                blockers.append(freshness_issue)
            account_issue = _account_facts_issue(request.account_facts_snapshot_json)
            if binding is not None and binding.trial_env == TrialEnv.LIVE and binding.trial_stage == TrialStage.FUNDED_VALIDATION:
                if account_issue is not None:
                    blockers.append(account_issue)
            elif account_issue is not None:
                warnings.append(account_issue)

        runtime_summary = dict(runtime_summary or {})
        if runtime_summary.get("strategy_active") is True or runtime_summary.get("active_strategy_id"):
            blockers.append("active strategy conflict exists")
        if runtime_summary.get("active_trial_id") or runtime_summary.get("trial_started") is True:
            blockers.append("active conflicting runtime trial exists")
        runtime_state = str(
            runtime_summary.get("current_runtime_state")
            or runtime_summary.get("runtime_state")
            or ""
        ).lower()
        if runtime_state in {"hard_locked", "hard_lock", "emergency_stopped", "emergency_stop", "flatten_required"}:
            blockers.append("emergency stop or hard lock is active")
        if runtime_summary.get("live_ready") is True:
            blockers.append("runtime live_ready is true; live execution path is not authorized")

        return _strategy_activation_readiness_from_context(
            campaign_id=campaign_id,
            binding=binding,
            blockers=blockers,
            warnings=warnings,
            decision=decision,
            constraint=constraint,
            campaign=campaign,
            execution_mode=execution_mode,
            idempotent_prepare=idempotent_prepare,
        )

    async def build_start_runtime_from_handoff_preflight_readiness(
        self,
        input_params: dict[str, Any],
        *,
        campaign: Optional[Any] = None,
        runtime_summary: Optional[dict[str, Any]] = None,
        trade_intent_ledger_available: bool = True,
        now_ms_value: Optional[int] = None,
    ) -> dict[str, Any]:
        now_value = now_ms_value if now_ms_value is not None else _now_ms()
        blockers: list[str] = []
        warnings: list[str] = []
        binding_id = str(
            input_params.get("admission_binding_id")
            or input_params.get("binding_id")
            or ""
        ).strip()
        campaign_id = str(input_params.get("campaign_id") or _campaign_id(campaign) or "").strip()
        campaign_metadata = _campaign_metadata(campaign)
        actual_campaign_id = _campaign_id(campaign)

        binding: Optional[AdmissionTrialBinding] = None
        if binding_id:
            binding = await self._repo.get_admission_trial_binding(binding_id)
            if binding is None:
                blockers.append(f"admission trial binding not found: {binding_id}")
        elif campaign_id:
            bindings = await self._repo.list_admission_trial_bindings(limit=500)
            binding = next((item for item in bindings if item.campaign_id == campaign_id), None)
            if binding is None:
                blockers.append(f"admission trial binding not found for campaign_id: {campaign_id}")
        else:
            blockers.append("admission_binding_id or campaign_id required")

        if campaign is None:
            blockers.append("campaign not found")
        elif not campaign_metadata:
            blockers.append("campaign metadata missing")
        elif campaign_id and actual_campaign_id != campaign_id:
            blockers.append("campaign_id does not match current campaign")
        elif campaign_metadata.get("created_from_admission") is not True:
            blockers.append("campaign metadata is not admission-created")
        if not campaign_id and actual_campaign_id:
            campaign_id = actual_campaign_id

        if binding is not None:
            if binding.campaign_id != campaign_id:
                blockers.append("admission trial binding campaign_id mismatch")
            if binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
                blockers.append(
                    f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
                )

        idempotent_start = (
            campaign_metadata.get("runtime_started") is True
            and campaign_metadata.get("runtime_status") == "runtime_started_strategy_inactive"
            and campaign_metadata.get("runtime_handoff_ready") is True
            and campaign_metadata.get("strategy_active") is False
            and campaign_metadata.get("trial_started") is False
            and campaign_metadata.get("orders_placed") is False
            and campaign_metadata.get("auto_within_budget_enabled") is not True
            and campaign_metadata.get("auto_execution_enabled") is not True
        )

        required_true = {
            "runtime_handoff_ready": "campaign metadata runtime_handoff_ready is not true",
            "constraints_installed": "campaign metadata constraints_installed is not true",
            "carrier_ready": "campaign metadata carrier_ready is not true",
            "runtime_start_ready": "campaign metadata runtime_start_ready is not true",
        }
        for key, message in required_true.items():
            if campaign_metadata.get(key) is not True:
                blockers.append(message)
        if campaign_metadata.get("runtime_status") == "runtime_handoff_ready_not_started":
            pass
        elif idempotent_start:
            pass
        else:
            blockers.append("campaign metadata runtime_status is not runtime_handoff_ready_not_started")
        required_false = {
            "strategy_active": "campaign metadata strategy_active is not false",
            "trial_started": "campaign metadata trial_started is not false",
            "orders_placed": "campaign metadata orders_placed is not false",
        }
        for key, message in required_false.items():
            if campaign_metadata.get(key) is not False:
                blockers.append(message)
        if campaign_metadata.get("runtime_started") is True and not idempotent_start:
            blockers.append("campaign metadata runtime_started is true outside runtime_started_strategy_inactive noop path")
        elif campaign_metadata.get("runtime_started") is not False and not idempotent_start:
            blockers.append("campaign metadata runtime_started is not false")
        if campaign_metadata.get("auto_within_budget_enabled") is True:
            blockers.append("campaign metadata auto_within_budget_enabled is true")
        if campaign_metadata.get("auto_execution_enabled") is True:
            blockers.append("campaign metadata auto_execution_enabled is true")
        if campaign_metadata.get("owner_confirm_each_entry_enabled") is True:
            blockers.append("campaign metadata owner_confirm_each_entry_enabled is true")

        installed_snapshot_id = _optional_text(campaign_metadata.get("installed_constraint_snapshot_id"))
        if installed_snapshot_id is None:
            blockers.append("installed_constraint_snapshot_id missing")
        elif binding is not None and installed_snapshot_id != binding.trial_constraint_snapshot_id:
            blockers.append("installed_constraint_snapshot_id mismatch")
        constraint = (
            await self._repo.get_trial_constraint_snapshot(installed_snapshot_id)
            if installed_snapshot_id is not None
            else None
        )
        if constraint is None and installed_snapshot_id is not None:
            blockers.append(f"trial constraint snapshot not found: {installed_snapshot_id}")

        execution_mode_value = str(campaign_metadata.get("execution_mode") or "").strip()
        try:
            execution_mode = AdmissionExecutionMode(execution_mode_value)
        except ValueError:
            execution_mode = None
            blockers.append("campaign metadata execution_mode is missing or invalid")

        constraints_summary = dict(campaign_metadata.get("installed_constraints_summary") or {})
        completeness = _constraints_completeness(constraints_summary)
        if execution_mode in {AdmissionExecutionMode.OBSERVE_ONLY, AdmissionExecutionMode.NO_ENTRY}:
            if not trade_intent_ledger_available:
                blockers.append(f"{execution_mode.value} trade intent ledger support unavailable")
            else:
                warnings.append(f"{execution_mode.value} execution-mode contract available as non-executable ledger")
        elif execution_mode == AdmissionExecutionMode.AUTO_WITHIN_BUDGET:
            if not completeness["complete"]:
                blockers.append(
                    "auto_within_budget constraints incomplete: "
                    + ", ".join(completeness["missing"])
                )
            warnings.append("auto_within_budget actual execution remains disabled")
        elif execution_mode == AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY:
            blockers.append("owner_confirm_each_entry execution is reserved and not implemented")

        decision: Optional[AdmissionDecision] = None
        request: Optional[AdmissionRequest] = None
        if binding is not None:
            decision = await self._repo.get_admission_decision(binding.admission_decision_id)
            if decision is None:
                blockers.append(f"admission decision not found: {binding.admission_decision_id}")
            else:
                request = await self._repo.get_admission_request(decision.admission_request_id)
                if request is None:
                    blockers.append(f"admission request not found: {decision.admission_request_id}")
                if decision.expires_at_ms is not None and decision.expires_at_ms <= now_value:
                    blockers.append("admission decision expired")
        if request is not None:
            freshness_issue = _account_facts_freshness_issue(request.account_facts_snapshot_json)
            if freshness_issue is not None:
                blockers.append(freshness_issue)
            account_issue = _account_facts_issue(request.account_facts_snapshot_json)
            if binding is not None and binding.trial_env == TrialEnv.LIVE and binding.trial_stage == TrialStage.FUNDED_VALIDATION:
                if account_issue is not None:
                    blockers.append(account_issue)
            elif account_issue is not None:
                warnings.append(account_issue)

        runtime_summary = dict(runtime_summary or {})
        runtime_state = str(
            runtime_summary.get("current_runtime_state")
            or runtime_summary.get("runtime_state")
            or ""
        ).lower()
        if runtime_summary.get("live_ready") is True:
            blockers.append("runtime live_ready is true; live execution path is not authorized")
        if binding is not None and binding.trial_env == TrialEnv.TESTNET:
            if runtime_summary.get("testnet") is False:
                blockers.append("runtime env mapping is not testnet for testnet admission")
        profile = str(runtime_summary.get("profile") or "").strip()
        if not profile:
            warnings.append("runtime profile unavailable; runtime state start should remain metadata-only")
        elif binding is not None and binding.trial_env == TrialEnv.TESTNET and "testnet" not in profile.lower():
            blockers.append("runtime profile/env mapping is not safe for testnet admission")
        active_carrier_id = (
            runtime_summary.get("active_runtime_carrier_id")
            or runtime_summary.get("runtime_carrier_id")
        )
        if active_carrier_id and active_carrier_id != campaign_id:
            blockers.append("active conflicting runtime carrier exists")
        if _runtime_summary_active(runtime_summary):
            blockers.append("runtime is already active")
        if runtime_summary.get("active_trial_id") or runtime_summary.get("trial_started") is True:
            blockers.append("active conflicting runtime trial exists")
        if runtime_summary.get("strategy_active") is True:
            blockers.append("active strategy already exists")
        if runtime_state in {"hard_locked", "hard_lock", "emergency_stopped", "emergency_stop", "flatten_required"}:
            blockers.append("emergency stop or hard lock is active")

        return _start_runtime_from_handoff_readiness_from_context(
            campaign_id=campaign_id,
            binding=binding,
            blockers=blockers,
            warnings=warnings,
            decision=decision,
            constraint=constraint,
            campaign=campaign,
            runtime_summary=runtime_summary,
            constraints_completeness=completeness,
            execution_mode=execution_mode,
            trade_intent_ledger_available=trade_intent_ledger_available,
            idempotent_start=idempotent_start,
        )

    async def build_trial_trade_intent_preflight_readiness(
        self,
        input_params: dict[str, Any],
        *,
        campaign: Optional[Any] = None,
        now_ms_value: Optional[int] = None,
    ) -> dict[str, Any]:
        now_value = now_ms_value if now_ms_value is not None else _now_ms()
        blockers: list[str] = []
        warnings: list[str] = []
        campaign_metadata = _campaign_metadata(campaign)
        campaign_id = str(input_params.get("campaign_id") or _campaign_id(campaign) or "").strip()
        actual_campaign_id = _campaign_id(campaign)
        intended_action = _normalize_intended_action(input_params.get("intended_action"))
        symbol = str(input_params.get("symbol") or "").strip()
        side = _optional_text(input_params.get("side"))

        if not campaign_id:
            blockers.append("campaign_id required")
        if not symbol:
            blockers.append("symbol required")
        if campaign is None:
            blockers.append("campaign not found")
        elif actual_campaign_id != campaign_id:
            blockers.append("campaign_id does not match current campaign")
        elif not campaign_metadata:
            blockers.append("campaign metadata missing")
        elif campaign_metadata.get("created_from_admission") is not True:
            blockers.append("campaign metadata is not admission-created")

        if campaign_metadata.get("runtime_start_ready") is not True:
            blockers.append("campaign metadata runtime_start_ready is not true")
        if campaign_metadata.get("runtime_status") != "runtime_start_ready_not_started":
            blockers.append("campaign metadata runtime_status is not runtime_start_ready_not_started")
        if campaign_metadata.get("runtime_started") is not False:
            blockers.append("campaign metadata runtime_started is not false")
        if campaign_metadata.get("strategy_active") is not False:
            blockers.append("campaign metadata strategy_active is not false")
        if campaign_metadata.get("trial_started") is True:
            blockers.append("campaign metadata trial_started is true")
        if campaign_metadata.get("orders_placed") is not False:
            blockers.append("campaign metadata orders_placed is not false")
        if campaign_metadata.get("auto_within_budget_enabled") is True:
            blockers.append("campaign metadata auto_within_budget_enabled is true")
        if campaign_metadata.get("owner_confirm_each_entry_enabled") is True:
            blockers.append("campaign metadata owner_confirm_each_entry_enabled is true")

        execution_mode_value = str(campaign_metadata.get("execution_mode") or "").strip()
        try:
            execution_mode = AdmissionExecutionMode(execution_mode_value)
        except ValueError:
            execution_mode = None
            blockers.append("campaign metadata execution_mode is missing or invalid")

        binding_id = _optional_text(campaign_metadata.get("admission_binding_id"))
        binding: Optional[AdmissionTrialBinding] = None
        if binding_id is not None:
            binding = await self._repo.get_admission_trial_binding(binding_id)
            if binding is None:
                blockers.append(f"admission trial binding not found: {binding_id}")
            elif binding.campaign_id != campaign_id:
                blockers.append("admission trial binding campaign_id mismatch")
        else:
            blockers.append("campaign metadata admission_binding_id missing")

        installed_snapshot_id = _optional_text(campaign_metadata.get("installed_constraint_snapshot_id"))
        if installed_snapshot_id is None:
            blockers.append("installed_constraint_snapshot_id missing")
        constraint = (
            await self._repo.get_trial_constraint_snapshot(installed_snapshot_id)
            if installed_snapshot_id is not None
            else None
        )
        if constraint is None and installed_snapshot_id is not None:
            blockers.append(f"trial constraint snapshot not found: {installed_snapshot_id}")

        constraints_summary = dict(campaign_metadata.get("installed_constraints_summary") or {})
        completeness = _constraints_completeness(constraints_summary)
        enforcement_decision = TrialTradeIntentDecision.UNAVAILABLE
        not_executed_reason = "execution mode unavailable"
        intent_would_be_persisted = False
        would_require_runtime_execution = False

        if execution_mode == AdmissionExecutionMode.OBSERVE_ONLY:
            enforcement_decision = TrialTradeIntentDecision.RECORDED
            not_executed_reason = "observe_only records would-have-traded intent only; execution is disabled"
            intent_would_be_persisted = True
        elif execution_mode == AdmissionExecutionMode.NO_ENTRY:
            intent_would_be_persisted = True
            if intended_action in {"entry", "increase"}:
                enforcement_decision = TrialTradeIntentDecision.BLOCKED
                not_executed_reason = "no_entry blocks entry and increase intents"
                warnings.append("no_entry will persist a blocked non-executable intent")
            else:
                enforcement_decision = TrialTradeIntentDecision.RECORDED
                not_executed_reason = "no_entry records non-entry intent only; execution is disabled"
        elif execution_mode == AdmissionExecutionMode.AUTO_WITHIN_BUDGET:
            would_require_runtime_execution = True
            if not completeness["complete"]:
                blockers.append(
                    "auto_within_budget constraints incomplete: "
                    + ", ".join(completeness["missing"])
                )
            enforcement_decision = TrialTradeIntentDecision.UNAVAILABLE
            not_executed_reason = (
                "auto_within_budget constraints checked only; actual auto execution remains disabled"
            )
            warnings.append("auto_within_budget actual execution remains future work")
        elif execution_mode == AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY:
            enforcement_decision = TrialTradeIntentDecision.UNAVAILABLE
            not_executed_reason = "owner_confirm_each_entry execution is reserved and not implemented"
            warnings.append("owner_confirm_each_entry execution is not implemented")

        return _trial_trade_intent_readiness_from_context(
            campaign_id=campaign_id,
            binding=binding,
            campaign_metadata=campaign_metadata,
            constraint=constraint,
            intended_action=intended_action,
            symbol=symbol,
            side=side,
            execution_mode=execution_mode,
            blockers=blockers,
            warnings=warnings,
            constraints_completeness=completeness,
            enforcement_decision=enforcement_decision,
            not_executed_reason=not_executed_reason,
            intent_would_be_persisted=intent_would_be_persisted,
            would_require_runtime_execution=would_require_runtime_execution,
            now_ms_value=now_value,
        )

    async def evaluate_trial_trade_intent(
        self,
        input_params: dict[str, Any],
        *,
        campaign: Optional[Any],
        operation_id: str,
        preflight_id: str,
        confirmed_by: str = "owner",
    ) -> dict[str, Any]:
        readiness = await self.build_trial_trade_intent_preflight_readiness(
            input_params,
            campaign=campaign,
        )
        blockers = [str(item) for item in readiness.get("blockers") or []]
        if blockers:
            raise AdmissionRuleViolation("; ".join(blockers))

        execution_mode = str(readiness.get("execution_mode") or "")
        decision = TrialTradeIntentDecision(str(readiness["enforcement"]["trial_trade_intent_result"]))
        if execution_mode in {
            AdmissionExecutionMode.AUTO_WITHIN_BUDGET.value,
            AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY.value,
        }:
            return {
                "intent": None,
                "intent_persisted": False,
                "trial_trade_intent_result": decision.value,
                "not_executed_reason": readiness["enforcement"]["not_executed_reason"],
                "execution_mode": execution_mode,
                "constraints_check": dict(readiness.get("constraints_check") or {}),
                "would_require_runtime_execution": bool(
                    readiness["enforcement"].get("would_require_runtime_execution")
                ),
                "order_created": False,
                "execution_intent_created": False,
                "runtime_started": False,
                "strategy_active": False,
                "orders_placed": False,
                "live_ready": False,
            }

        now_value = _now_ms()
        intent = TrialTradeIntent(
            intent_id=_id("tti"),
            campaign_id=str(readiness["campaign_id"]),
            binding_id=readiness.get("binding_id"),
            admission_decision_id=readiness.get("admission_decision_id"),
            strategy_family_version_id=readiness.get("strategy_family_version_id"),
            playbook_id=readiness.get("playbook_id"),
            execution_mode=AdmissionExecutionMode(execution_mode),
            intended_action=str(readiness["intended_action"]),
            symbol=str(readiness["symbol"]),
            side=readiness.get("side"),
            signal_snapshot_json=dict(input_params.get("signal_snapshot") or {}),
            market_snapshot_json=dict(input_params.get("market_snapshot") or {}),
            risk_snapshot_json=dict(readiness.get("constraints_check") or {}),
            decision=decision,
            not_executed_reason=str(readiness["enforcement"]["not_executed_reason"]),
            created_at_ms=now_value,
            created_by_operation_id=operation_id,
            audit_refs_json={
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "non_executable_evidence_only": True,
                "not_order": True,
                "not_execution_intent": True,
            },
        )
        saved = await self._repo.create_trial_trade_intent(intent)
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_TRIAL_TRADE_INTENT_EVALUATED,
            ref_type="trial_trade_intent",
            ref_id=saved.intent_id,
            admission_decision_id=saved.admission_decision_id,
            actor=confirmed_by,
            message=(
                "Trial trade intent evaluated as non-executable evidence. "
                "No runtime, strategy, order, execution intent, live action, withdrawal, or transfer was created."
            ),
            metadata={
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "campaign_id": saved.campaign_id,
                "binding_id": saved.binding_id,
                "execution_mode": saved.execution_mode.value,
                "intended_action": saved.intended_action,
                "trial_trade_intent_result": saved.decision.value,
                "not_executed_reason": saved.not_executed_reason,
                "order_created": False,
                "execution_intent_created": False,
                "runtime_started": False,
                "strategy_active": False,
                "orders_placed": False,
                "live_ready": False,
            },
        )
        return {
            "intent": saved.model_dump(mode="json"),
            "intent_id": saved.intent_id,
            "intent_persisted": True,
            "trial_trade_intent_result": saved.decision.value,
            "not_executed_reason": saved.not_executed_reason,
            "execution_mode": saved.execution_mode.value,
            "constraints_check": dict(readiness.get("constraints_check") or {}),
            "would_require_runtime_execution": False,
            "order_created": False,
            "execution_intent_created": False,
            "runtime_started": False,
            "strategy_active": False,
            "orders_placed": False,
            "live_ready": False,
        }

    async def build_signal_trial_trade_intent_preflight_readiness(
        self,
        input_params: dict[str, Any],
        *,
        campaign: Optional[Any] = None,
        now_ms_value: Optional[int] = None,
    ) -> dict[str, Any]:
        now_value = now_ms_value if now_ms_value is not None else _now_ms()
        blockers: list[str] = []
        warnings: list[str] = []
        campaign_metadata = _campaign_metadata(campaign)
        campaign_id = str(input_params.get("campaign_id") or _campaign_id(campaign) or "").strip()
        actual_campaign_id = _campaign_id(campaign)
        intended_action = _normalize_intended_action(input_params.get("intended_action"))
        symbol = str(input_params.get("symbol") or "").strip()
        side = _optional_text(input_params.get("side"))

        if not campaign_id:
            blockers.append("campaign_id required")
        if not symbol:
            blockers.append("symbol required")
        if campaign is None:
            blockers.append("campaign not found")
        elif actual_campaign_id != campaign_id:
            blockers.append("campaign_id does not match current campaign")
        elif not campaign_metadata:
            blockers.append("campaign metadata missing")
        elif campaign_metadata.get("created_from_admission") is not True:
            blockers.append("campaign metadata is not admission-created")

        binding_id = _optional_text(
            input_params.get("admission_binding_id")
            or input_params.get("binding_id")
            or campaign_metadata.get("admission_binding_id")
        )
        binding: Optional[AdmissionTrialBinding] = None
        decision: Optional[AdmissionDecision] = None
        request: Optional[AdmissionRequest] = None
        if binding_id is None:
            blockers.append("admission_binding_id or binding_id required")
        else:
            binding = await self._repo.get_admission_trial_binding(binding_id)
            if binding is None:
                blockers.append(f"admission trial binding not found: {binding_id}")
            elif binding.campaign_id != campaign_id:
                blockers.append("admission trial binding campaign_id mismatch")
            elif binding.binding_status != AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED:
                blockers.append(
                    f"admission trial binding is {binding.binding_status.value}, not runtime_constraints_installed"
                )
            else:
                decision = await self._repo.get_admission_decision(binding.admission_decision_id)
                if decision is None:
                    blockers.append(f"admission decision not found: {binding.admission_decision_id}")
                else:
                    request = await self._repo.get_admission_request(decision.admission_request_id)
                    if request is None:
                        blockers.append(f"admission request not found: {decision.admission_request_id}")
                    if decision.expires_at_ms is not None and decision.expires_at_ms <= now_value:
                        blockers.append("admission decision expired")

        idempotent_intent = (
            campaign_metadata.get("runtime_status") == "trial_trade_intent_recorded_no_execution"
            and campaign_metadata.get("trial_trade_intent_created") is True
            and campaign_metadata.get("execution_intent_created") is False
            and campaign_metadata.get("order_created") is False
            and campaign_metadata.get("orders_placed") is False
            and campaign_metadata.get("trial_started") is False
            and campaign_metadata.get("auto_execution_enabled") is False
            and campaign_metadata.get("auto_within_budget_enabled") is False
        )
        if campaign_metadata.get("runtime_status") == "signal_evaluated_no_intent":
            pass
        elif idempotent_intent:
            pass
        else:
            blockers.append("campaign metadata runtime_status is not signal_evaluated_no_intent")
        if campaign_metadata.get("signal_evaluated") is not True:
            blockers.append("campaign metadata signal_evaluated is not true")
        if campaign_metadata.get("signal_generated") is not True:
            blockers.append("campaign metadata signal_generated is not true")

        if not idempotent_intent:
            required_false = {
                "trade_intent_created": "campaign metadata trade_intent_created is not false",
                "trial_trade_intent_created": "campaign metadata trial_trade_intent_created is not false",
                "execution_intent_created": "campaign metadata execution_intent_created is not false",
                "order_created": "campaign metadata order_created is not false",
                "orders_placed": "campaign metadata orders_placed is not false",
                "trial_started": "campaign metadata trial_started is not false",
                "auto_execution_enabled": "campaign metadata auto_execution_enabled is not false",
                "auto_within_budget_enabled": "campaign metadata auto_within_budget_enabled is not false",
            }
            for key, message in required_false.items():
                if key == "trial_trade_intent_created" and campaign_metadata.get(key) is None:
                    continue
                if campaign_metadata.get(key) is not False:
                    blockers.append(message)
        if campaign_metadata.get("live_ready") is True:
            blockers.append("campaign metadata live_ready is true")

        execution_mode_value = str(campaign_metadata.get("execution_mode") or "").strip()
        try:
            execution_mode = AdmissionExecutionMode(execution_mode_value)
        except ValueError:
            execution_mode = None
            blockers.append("campaign metadata execution_mode is missing or invalid")

        installed_snapshot_id = _optional_text(campaign_metadata.get("installed_constraint_snapshot_id"))
        if installed_snapshot_id is None:
            blockers.append("installed_constraint_snapshot_id missing")
        constraint = (
            await self._repo.get_trial_constraint_snapshot(installed_snapshot_id)
            if installed_snapshot_id is not None
            else None
        )
        if constraint is None and installed_snapshot_id is not None:
            blockers.append(f"trial constraint snapshot not found: {installed_snapshot_id}")

        constraints_summary = dict(campaign_metadata.get("installed_constraints_summary") or {})
        completeness = _constraints_completeness(constraints_summary)
        enforcement_decision = TrialTradeIntentDecision.UNAVAILABLE
        not_executed_reason = "execution mode unavailable"
        intent_would_be_persisted = False

        if execution_mode == AdmissionExecutionMode.OBSERVE_ONLY:
            enforcement_decision = TrialTradeIntentDecision.RECORDED
            not_executed_reason = "observe_only"
            intent_would_be_persisted = True
        elif execution_mode == AdmissionExecutionMode.NO_ENTRY:
            intent_would_be_persisted = True
            if intended_action in {"entry", "increase"}:
                enforcement_decision = TrialTradeIntentDecision.BLOCKED
                not_executed_reason = "no_entry"
                warnings.append("no_entry will persist a blocked non-executable intent")
            else:
                enforcement_decision = TrialTradeIntentDecision.RECORDED
                not_executed_reason = "no_entry_non_entry_evidence_only"
        elif execution_mode == AdmissionExecutionMode.AUTO_WITHIN_BUDGET:
            if not completeness["complete"]:
                blockers.append(
                    "auto_within_budget constraints incomplete: "
                    + ", ".join(completeness["missing"])
                )
            enforcement_decision = TrialTradeIntentDecision.RECORDED
            not_executed_reason = "live_read_only_detection_no_execution"
            intent_would_be_persisted = True
            warnings.append("auto_within_budget actual execution remains disabled")
        elif execution_mode == AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY:
            enforcement_decision = TrialTradeIntentDecision.UNAVAILABLE
            not_executed_reason = "owner_confirm_each_entry execution is reserved and not implemented"
            warnings.append("owner_confirm_each_entry execution is not implemented")

        return _signal_trial_trade_intent_readiness_from_context(
            campaign_id=campaign_id,
            binding=binding,
            campaign_metadata=campaign_metadata,
            constraint=constraint,
            intended_action=intended_action,
            symbol=symbol,
            side=side,
            execution_mode=execution_mode,
            blockers=blockers,
            warnings=warnings,
            constraints_completeness=completeness,
            enforcement_decision=enforcement_decision,
            not_executed_reason=not_executed_reason,
            intent_would_be_persisted=intent_would_be_persisted,
            account_facts=(request.account_facts_snapshot_json if request is not None else None),
            idempotent_intent=idempotent_intent,
            now_ms_value=now_value,
        )

    async def record_trial_trade_intent_from_signal_evaluation(
        self,
        input_params: dict[str, Any],
        *,
        campaign: Optional[Any],
        operation_id: str,
        preflight_id: str,
        execution_permission_resolution: dict[str, Any],
        confirmed_by: str = "owner",
    ) -> dict[str, Any]:
        readiness = await self.build_signal_trial_trade_intent_preflight_readiness(
            input_params,
            campaign=campaign,
        )
        blockers = [str(item) for item in readiness.get("blockers") or []]
        if blockers:
            raise AdmissionRuleViolation("; ".join(blockers))
        if readiness.get("mode_unavailable") is True:
            raise AdmissionRuleViolation("owner_confirm_each_entry execution is reserved and not implemented")
        if readiness.get("idempotent_intent") is True:
            existing_id = _optional_text(readiness.get("trial_trade_intent_id"))
            existing = await self._repo.get_trial_trade_intent(existing_id) if existing_id else None
            return {
                "intent": existing.model_dump(mode="json") if existing is not None else None,
                "intent_id": existing_id,
                "intent_persisted": existing is not None,
                "idempotent": True,
                "trial_trade_intent_result": (
                    existing.decision.value
                    if existing is not None
                    else readiness["enforcement"]["trial_trade_intent_result"]
                ),
                "not_executed_reason": (
                    existing.not_executed_reason if existing is not None else readiness["enforcement"]["not_executed_reason"]
                ),
                "execution_mode": readiness.get("execution_mode"),
                "constraints_check": dict(readiness.get("constraints_check") or {}),
                "execution_permission_resolution": dict(execution_permission_resolution or {}),
                "order_created": False,
                "execution_intent_created": False,
                "orders_placed": False,
                "live_ready": False,
            }

        execution_mode = str(readiness.get("execution_mode") or "")
        decision = TrialTradeIntentDecision(str(readiness["enforcement"]["trial_trade_intent_result"]))
        now_value = _now_ms()
        intent = TrialTradeIntent(
            intent_id=_id("tti"),
            campaign_id=str(readiness["campaign_id"]),
            binding_id=readiness.get("binding_id"),
            admission_decision_id=readiness.get("admission_decision_id"),
            strategy_family_version_id=readiness.get("strategy_family_version_id"),
            playbook_id=readiness.get("playbook_id"),
            execution_mode=AdmissionExecutionMode(execution_mode),
            intended_action=str(readiness["intended_action"]),
            symbol=str(readiness["symbol"]),
            side=readiness.get("side"),
            signal_snapshot_json=dict(input_params.get("signal_snapshot") or {}),
            market_snapshot_json=dict(input_params.get("market_snapshot") or {}),
            risk_snapshot_json={
                "constraints_check": dict(readiness.get("constraints_check") or {}),
                "execution_permission_resolution": dict(execution_permission_resolution or {}),
            },
            decision=decision,
            not_executed_reason=str(readiness["enforcement"]["not_executed_reason"]),
            created_at_ms=now_value,
            created_by_operation_id=operation_id,
            audit_refs_json={
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "execution_permission_resolution": dict(execution_permission_resolution or {}),
                "non_executable_evidence_only": True,
                "not_order": True,
                "not_execution_intent": True,
            },
        )
        saved = await self._repo.create_trial_trade_intent(intent)
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_TRIAL_TRADE_INTENT_EVALUATED,
            ref_type="trial_trade_intent",
            ref_id=saved.intent_id,
            admission_decision_id=saved.admission_decision_id,
            actor=confirmed_by,
            message=(
                "Trial trade intent recorded from signal evaluation as non-executable evidence. "
                "No execution intent, order, auto execution, live action, withdrawal, or transfer was created."
            ),
            metadata={
                "operation_id": operation_id,
                "preflight_id": preflight_id,
                "campaign_id": saved.campaign_id,
                "binding_id": saved.binding_id,
                "execution_mode": saved.execution_mode.value,
                "intended_action": saved.intended_action,
                "trial_trade_intent_result": saved.decision.value,
                "not_executed_reason": saved.not_executed_reason,
                "execution_permission_resolution": dict(execution_permission_resolution or {}),
                "trial_trade_intent_is_order": False,
                "order_created": False,
                "execution_intent_created": False,
                "orders_placed": False,
                "trial_started": False,
                "auto_execution_enabled": False,
                "auto_within_budget_enabled": False,
                "live_ready": False,
            },
        )
        return {
            "intent": saved.model_dump(mode="json"),
            "intent_id": saved.intent_id,
            "intent_persisted": True,
            "idempotent": False,
            "trial_trade_intent_result": saved.decision.value,
            "not_executed_reason": saved.not_executed_reason,
            "execution_mode": saved.execution_mode.value,
            "constraints_check": dict(readiness.get("constraints_check") or {}),
            "execution_permission_resolution": dict(execution_permission_resolution or {}),
            "order_created": False,
            "execution_intent_created": False,
            "orders_placed": False,
            "trial_started": False,
            "auto_execution_enabled": False,
            "auto_within_budget_enabled": False,
            "live_ready": False,
        }

    async def create_strategy_family(
        self,
        *,
        family_key: str,
        name: str,
        strategy_family_id: Optional[str] = None,
        description: str = "",
        status: StrategyFamilyStatus = StrategyFamilyStatus.INTAKE,
        owner: str = "owner",
    ) -> StrategyFamily:
        now = _now_ms()
        family = StrategyFamily(
            strategy_family_id=strategy_family_id or _id("sf"),
            family_key=family_key,
            name=name,
            description=description,
            status=status,
            owner=owner,
            created_at_ms=now,
            updated_at_ms=now,
        )
        saved = await self._repo.create_strategy_family(family)
        await self._audit(
            event_type=AdmissionAuditEventType.FAMILY_CREATED,
            ref_type="strategy_family",
            ref_id=saved.strategy_family_id,
            actor=owner,
            message="Strategy family created.",
        )
        return saved

    async def create_strategy_family_version(
        self,
        *,
        strategy_family_id: str,
        strategy_family_version_id: Optional[str] = None,
        version: int,
        hypothesis: str = "",
        market_structure: str = "",
        entry_logic_family: str = "",
        exit_logic_family: str = "",
        risk_model: str = "",
        supported_symbols: Optional[list[str]] = None,
        supported_timeframes: Optional[list[str]] = None,
        required_data: Optional[list[str]] = None,
        required_execution_capabilities: Optional[list[str]] = None,
        known_failure_modes: Optional[list[str]] = None,
        regime_contract_json: Optional[dict[str, Any]] = None,
        safeguards_json: Optional[dict[str, Any]] = None,
        degradation_policy_json: Optional[dict[str, Any]] = None,
        playbook_id: Optional[str] = None,
        playbook_catalog_snapshot_json: Optional[dict[str, Any]] = None,
        created_by: str = "owner",
    ) -> StrategyFamilyVersion:
        family = await self._repo.get_strategy_family(strategy_family_id)
        if family is None:
            raise AdmissionRuleViolation(f"strategy family not found: {strategy_family_id}")
        now = _now_ms()
        item = StrategyFamilyVersion(
            strategy_family_version_id=strategy_family_version_id or _id("sfv"),
            strategy_family_id=strategy_family_id,
            version=version,
            hypothesis=hypothesis,
            market_structure=market_structure,
            entry_logic_family=entry_logic_family,
            exit_logic_family=exit_logic_family,
            risk_model=risk_model,
            supported_symbols=list(supported_symbols or []),
            supported_timeframes=list(supported_timeframes or []),
            required_data=list(required_data or []),
            required_execution_capabilities=list(required_execution_capabilities or []),
            known_failure_modes=list(known_failure_modes or []),
            regime_contract_json=dict(regime_contract_json or {}),
            safeguards_json=dict(safeguards_json or {}),
            degradation_policy_json=dict(degradation_policy_json or {}),
            playbook_id=playbook_id,
            playbook_catalog_snapshot_json=dict(playbook_catalog_snapshot_json or {}),
            created_at_ms=now,
            created_by=created_by,
        )
        saved = await self._repo.create_strategy_family_version(item)
        await self._audit(
            event_type=AdmissionAuditEventType.FAMILY_VERSION_CREATED,
            ref_type="strategy_family_version",
            ref_id=saved.strategy_family_version_id,
            actor=created_by,
            message="Strategy family version created.",
            metadata={"strategy_family_id": strategy_family_id},
        )
        return saved

    async def create_admission_evidence(
        self,
        *,
        strategy_family_version_id: str,
        payload_json: dict[str, Any],
        mandatory_complete: bool = False,
        created_by: str = "owner",
    ) -> AdmissionEvidence:
        version = await self._repo.get_strategy_family_version(strategy_family_version_id)
        if version is None:
            raise AdmissionRuleViolation(
                f"strategy family version not found: {strategy_family_version_id}"
            )
        admission_evidence = AdmissionEvidence(
            admission_evidence_id=_id("evidence"),
            strategy_family_version_id=strategy_family_version_id,
            payload_json=dict(payload_json),
            mandatory_complete=mandatory_complete,
            created_at_ms=_now_ms(),
            created_by=created_by,
        )
        saved = await self._repo.create_admission_evidence(admission_evidence)
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_EVIDENCE_CREATED,
            ref_type="admission_evidence",
            ref_id=saved.admission_evidence_id,
            actor=created_by,
            message="Admission evidence created.",
            metadata={"strategy_family_version_id": strategy_family_version_id},
        )
        return saved

    async def create_owner_regime_input(
        self,
        *,
        current_regime: str,
        confidence: str = "unknown",
        rationale: str = "",
        market_facts_snapshot_json: Optional[dict[str, Any]] = None,
        created_by: str = "owner",
    ) -> OwnerMarketRegimeInput:
        regime = OwnerMarketRegimeInput(
            owner_market_regime_input_id=_id("regime"),
            current_regime=current_regime,
            confidence=confidence,
            rationale=rationale,
            market_facts_snapshot_json=dict(market_facts_snapshot_json or {}),
            created_at_ms=_now_ms(),
            created_by=created_by,
        )
        saved = await self._repo.create_owner_regime_input(regime)
        await self._audit(
            event_type=AdmissionAuditEventType.OWNER_REGIME_INPUT_CREATED,
            ref_type="owner_market_regime_input",
            ref_id=saved.owner_market_regime_input_id,
            actor=created_by,
            message="Owner market regime input created.",
        )
        return saved

    async def create_admission_request(
        self,
        *,
        strategy_family_version_id: str,
        admission_evidence_id: str,
        owner_market_regime_input_id: str,
        trial_env: TrialEnv,
        trial_stage: TrialStage,
        requested_execution_mode: Optional[AdmissionExecutionMode] = None,
        requested_risk_profile: str = "micro",
        admission_rule_config_id: Optional[str] = None,
        account_facts_snapshot_ref: Optional[str] = None,
        account_facts_snapshot_json: Optional[dict[str, Any]] = None,
        playbook_id: Optional[str] = None,
        playbook_catalog_snapshot_json: Optional[dict[str, Any]] = None,
        requested_by: str = "owner",
    ) -> AdmissionRequest:
        await self._require_strategy_family_version(strategy_family_version_id)
        evidence = await self._require_admission_evidence(admission_evidence_id)
        if evidence.strategy_family_version_id != strategy_family_version_id:
            raise AdmissionRuleViolation(
                "admission evidence is not pinned to requested strategy family version"
            )
        await self._require_owner_regime_input(owner_market_regime_input_id)
        if admission_rule_config_id is not None:
            await self._require_rule_config(admission_rule_config_id)
        request = AdmissionRequest(
            admission_request_id=_id("admission-req"),
            strategy_family_version_id=strategy_family_version_id,
            admission_evidence_id=admission_evidence_id,
            owner_market_regime_input_id=owner_market_regime_input_id,
            trial_env=trial_env,
            trial_stage=trial_stage,
            requested_execution_mode=requested_execution_mode,
            requested_risk_profile=requested_risk_profile,
            admission_rule_config_id=admission_rule_config_id,
            account_facts_snapshot_ref=account_facts_snapshot_ref,
            account_facts_snapshot_json=dict(account_facts_snapshot_json or {}),
            playbook_id=playbook_id,
            playbook_catalog_snapshot_json=dict(playbook_catalog_snapshot_json or {}),
            created_at_ms=_now_ms(),
            requested_by=requested_by,
        )
        saved = await self._repo.create_admission_request(request)
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_REQUEST_CREATED,
            ref_type="admission_request",
            ref_id=saved.admission_request_id,
            admission_request_id=saved.admission_request_id,
            actor=requested_by,
            message="Admission request created.",
        )
        return saved

    async def evaluate(self, admission_request_id: str) -> AdmissionDecision:
        request = await self._require_admission_request(admission_request_id)
        strategy_version = await self._require_strategy_family_version(
            request.strategy_family_version_id
        )
        evidence = await self._require_admission_evidence(
            request.admission_evidence_id
        )
        regime = await self._require_owner_regime_input(
            request.owner_market_regime_input_id
        )
        rule_config = await self._resolve_rule_config(request.admission_rule_config_id)

        adapter_result = await self._risk_capital_adapter.resolve_constraints(
            request=request,
            strategy_family_version=strategy_version,
            admission_evidence=evidence,
            owner_regime_input=regime,
            rule_config=rule_config,
        )
        constraint_snapshot = TrialConstraintSnapshot(
            trial_constraint_snapshot_id=_id("constraint"),
            admission_request_id=request.admission_request_id,
            status=adapter_result.status,
            risk_profile=adapter_result.risk_profile,
            risk_policy_version=adapter_result.risk_policy_version,
            constraints_json=dict(adapter_result.constraints_json),
            risk_policy_snapshot_json=dict(adapter_result.risk_policy_snapshot_json),
            adapter_result_json=dict(adapter_result.adapter_result_json),
            created_at_ms=_now_ms(),
        )
        constraint_snapshot = await self._repo.create_trial_constraint_snapshot(
            constraint_snapshot
        )

        decision, blockers, warnings, execution_mode = self._evaluate_decision(
            request=request,
            evidence=evidence,
            constraint_snapshot=constraint_snapshot,
        )
        playbook_id = request.playbook_id or strategy_version.playbook_id
        playbook_snapshot = (
            request.playbook_catalog_snapshot_json
            or strategy_version.playbook_catalog_snapshot_json
        )
        admission_decision = AdmissionDecision(
            admission_decision_id=_id("admission-decision"),
            admission_request_id=request.admission_request_id,
            decision=decision,
            trial_env=request.trial_env,
            trial_stage=request.trial_stage,
            strategy_family_version_id=strategy_version.strategy_family_version_id,
            playbook_id=playbook_id,
            playbook_catalog_snapshot_json=dict(playbook_snapshot or {}),
            owner_market_regime_input_id=regime.owner_market_regime_input_id,
            admission_evidence_id=evidence.admission_evidence_id,
            admission_rule_config_id=rule_config.admission_rule_config_id,
            trial_constraint_snapshot_id=constraint_snapshot.trial_constraint_snapshot_id,
            risk_profile=request.requested_risk_profile,
            execution_mode=execution_mode,
            degradation_applied=decision == AdmissionDecisionValue.ADMIT_WITH_CONSTRAINTS,
            risk_intent_json={
                "requested_risk_profile": request.requested_risk_profile,
                "trial_env": request.trial_env.value,
                "trial_stage": request.trial_stage.value,
            },
            degradation_intent_json=self._degradation_intent(
                decision=decision,
                execution_mode=execution_mode,
                constraint_snapshot=constraint_snapshot,
            ),
            blockers_json=blockers,
            warnings_json=warnings,
            risk_disclosure_json={
                "funded_validation_requires_owner_risk_acceptance": (
                    request.trial_stage == TrialStage.FUNDED_VALIDATION
                ),
                "admission_is_not_strategy_approval": True,
                "sizing_computed_by_admission": False,
            },
            known_gaps_json={
                "mandatory_evidence_complete": evidence.mandatory_complete,
                "risk_capital_status": constraint_snapshot.status.value,
            },
            constraints_snapshot_json=constraint_snapshot.model_dump(mode="json"),
            created_at_ms=_now_ms(),
        )
        saved = await self._repo.create_admission_decision(admission_decision)
        await self._audit(
            event_type=AdmissionAuditEventType.ADMISSION_EVALUATED,
            ref_type="admission_decision",
            ref_id=saved.admission_decision_id,
            admission_request_id=request.admission_request_id,
            admission_decision_id=saved.admission_decision_id,
            actor="system",
            message="Admission request evaluated.",
            metadata={
                "decision": saved.decision.value,
                "constraint_snapshot_status": constraint_snapshot.status.value,
            },
        )
        return saved

    async def create_owner_risk_acceptance(
        self,
        payload: OwnerRiskAcceptanceInput,
    ) -> OwnerRiskAcceptance:
        request = await self._require_admission_request(payload.admission_request_id)
        snapshot = await self._require_constraint_snapshot(payload.constraint_snapshot_id)
        if snapshot.status != TrialConstraintSnapshotStatus.INSTALLABLE:
            raise AdmissionRuleViolation(
                "owner risk acceptance requires installable trial constraints"
            )
        decision: Optional[AdmissionDecision] = None
        if payload.admission_decision_id is not None:
            decision = await self._require_admission_decision(payload.admission_decision_id)
            if decision.admission_request_id != request.admission_request_id:
                raise AdmissionRuleViolation("risk acceptance decision/request mismatch")
            if decision.trial_constraint_snapshot_id != snapshot.trial_constraint_snapshot_id:
                raise AdmissionRuleViolation("risk acceptance constraint snapshot mismatch")

        if request.trial_stage != TrialStage.FUNDED_VALIDATION:
            raise AdmissionRuleViolation("owner risk acceptance is required only for funded_validation")
        if not request.account_facts_snapshot_ref:
            raise AdmissionRuleViolation("funded_validation risk acceptance requires account facts ref")
        confirmation = OwnerRiskAcceptance(
            owner_risk_acceptance_id=_id("risk-acceptance"),
            admission_request_id=request.admission_request_id,
            admission_decision_id=payload.admission_decision_id,
            strategy_family_version_id=request.strategy_family_version_id,
            trial_env=request.trial_env,
            trial_stage=request.trial_stage,
            account_facts_snapshot_ref=request.account_facts_snapshot_ref,
            risk_profile=snapshot.risk_profile,
            risk_policy_snapshot_json=dict(snapshot.risk_policy_snapshot_json),
            constraint_snapshot_id=snapshot.trial_constraint_snapshot_id,
            risk_disclosure_snapshot_json=(
                dict(decision.risk_disclosure_json) if decision is not None else {}
            ),
            known_gaps_snapshot_json=(
                dict(decision.known_gaps_json) if decision is not None else {}
            ),
            owner_rationale=payload.owner_rationale,
            confirmation_phrase=payload.confirmation_phrase,
            confirmed_at_ms=_now_ms(),
            created_at_ms=_now_ms(),
            created_by=payload.confirmed_by,
        )
        saved = await self._repo.create_owner_risk_acceptance(confirmation)
        await self._audit(
            event_type=AdmissionAuditEventType.OWNER_RISK_ACCEPTANCE_CREATED,
            ref_type="owner_risk_acceptance",
            ref_id=saved.owner_risk_acceptance_id,
            admission_request_id=saved.admission_request_id,
            admission_decision_id=saved.admission_decision_id,
            actor=saved.created_by,
            message="Owner risk acceptance created.",
            metadata={"constraint_snapshot_id": saved.constraint_snapshot_id},
        )
        return saved

    def _evaluate_decision(
        self,
        *,
        request: AdmissionRequest,
        evidence: AdmissionEvidence,
        constraint_snapshot: TrialConstraintSnapshot,
    ) -> tuple[AdmissionDecisionValue, list[str], list[str], AdmissionExecutionMode]:
        blockers: list[str] = []
        warnings: list[str] = []
        execution_mode = request.requested_execution_mode
        if execution_mode is None:
            execution_mode = (
                AdmissionExecutionMode.AUTO_WITHIN_BUDGET
                if request.trial_stage == TrialStage.FUNDED_VALIDATION
                else AdmissionExecutionMode.OBSERVE_ONLY
            )

        account_issue = _account_facts_issue(request.account_facts_snapshot_json)
        if (
            request.trial_env == TrialEnv.LIVE
            and request.trial_stage == TrialStage.FUNDED_VALIDATION
            and not request.account_facts_snapshot_ref
            and account_issue is None
        ):
            account_issue = "account facts snapshot ref unavailable"
        if (
            request.trial_env == TrialEnv.LIVE
            and request.trial_stage == TrialStage.FUNDED_VALIDATION
            and account_issue is not None
        ):
            blockers.append(account_issue)
            return AdmissionDecisionValue.REJECT, blockers, warnings, AdmissionExecutionMode.NO_ENTRY

        if account_issue is not None:
            warnings.append(account_issue)
            if request.trial_env == TrialEnv.TESTNET:
                execution_mode = AdmissionExecutionMode.OBSERVE_ONLY

        if not evidence.mandatory_complete:
            warnings.append("mandatory evidence incomplete; admit with constraints bias applies")

        if constraint_snapshot.status == TrialConstraintSnapshotStatus.PENDING_RISK_CAPITAL_RESOLUTION:
            warnings.append("risk capital constraints pending resolution")
        warnings.extend(
            [
                str(item)
                for item in constraint_snapshot.constraints_json.get("warnings", [])
                if str(item) not in warnings
            ]
        )
        blockers.extend(
            [
                str(item)
                for item in constraint_snapshot.constraints_json.get("blockers", [])
                if (
                    request.trial_env == TrialEnv.LIVE
                    and request.trial_stage == TrialStage.FUNDED_VALIDATION
                    and str(item) not in blockers
                )
            ]
        )

        if blockers:
            return AdmissionDecisionValue.REJECT, blockers, warnings, execution_mode
        return AdmissionDecisionValue.ADMIT_WITH_CONSTRAINTS, blockers, warnings, execution_mode

    def _degradation_intent(
        self,
        *,
        decision: AdmissionDecisionValue,
        execution_mode: AdmissionExecutionMode,
        constraint_snapshot: TrialConstraintSnapshot,
    ) -> dict[str, Any]:
        if decision == AdmissionDecisionValue.REJECT:
            return {"intent": "no_entry", "execution_mode": AdmissionExecutionMode.NO_ENTRY.value}
        if constraint_snapshot.status == TrialConstraintSnapshotStatus.PENDING_RISK_CAPITAL_RESOLUTION:
            return {
                "intent": "pending_constraints",
                "execution_mode": execution_mode.value,
                "operation_confirm_allowed": False,
            }
        return {"intent": "bounded_trial", "execution_mode": execution_mode.value}

    async def _resolve_rule_config(self, rule_config_id: Optional[str]) -> AdmissionRuleConfig:
        if rule_config_id is not None:
            return await self._require_rule_config(rule_config_id)
        existing = await self._repo.get_latest_rule_config()
        if existing is not None:
            return existing
        config = AdmissionRuleConfig(
            admission_rule_config_id=DEFAULT_ADMISSION_RULE_CONFIG_ID,
            config_key="brc_admission_default",
            version=1,
            status="active",
            rule_details_json={
                "default_decision_bias": AdmissionDecisionValue.ADMIT_WITH_CONSTRAINTS.value,
                "reject_only_for_system_boundaries": True,
            },
            system_boundaries_json={
                "no_withdrawal_transfer": True,
                "no_llm_direct_execution": True,
                "operation_layer_required": True,
                "live_funded_validation_requires_account_facts": True,
            },
            relaxable_safeguards_json={
                "evidence_incomplete": "admit_with_constraints_or_observe_only",
            },
            created_at_ms=_now_ms(),
            created_by="system",
        )
        return await self._repo.create_rule_config(config)

    async def _audit(
        self,
        *,
        event_type: AdmissionAuditEventType,
        ref_type: str,
        ref_id: str,
        actor: str,
        message: str,
        admission_request_id: Optional[str] = None,
        admission_decision_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AdmissionAuditLog:
        return await self._repo.append_audit_log(
            AdmissionAuditLog(
                audit_id=_id("admission-audit"),
                event_type=event_type,
                ref_type=ref_type,
                ref_id=ref_id,
                admission_request_id=admission_request_id,
                admission_decision_id=admission_decision_id,
                actor=actor,
                message=message,
                metadata_json=dict(metadata or {}),
                created_at_ms=_now_ms(),
            )
        )

    async def _require_strategy_family_version(self, item_id: str) -> StrategyFamilyVersion:
        item = await self._repo.get_strategy_family_version(item_id)
        if item is None:
            raise AdmissionRuleViolation(f"strategy family version not found: {item_id}")
        return item

    async def _require_admission_evidence(self, item_id: str) -> AdmissionEvidence:
        item = await self._repo.get_admission_evidence(item_id)
        if item is None:
            raise AdmissionRuleViolation(f"admission evidence not found: {item_id}")
        return item

    async def _require_owner_regime_input(self, item_id: str) -> OwnerMarketRegimeInput:
        item = await self._repo.get_owner_regime_input(item_id)
        if item is None:
            raise AdmissionRuleViolation(f"owner regime input not found: {item_id}")
        return item

    async def _require_rule_config(self, item_id: str) -> AdmissionRuleConfig:
        item = await self._repo.get_rule_config(item_id)
        if item is None:
            raise AdmissionRuleViolation(f"admission rule config not found: {item_id}")
        return item

    async def _require_admission_request(self, item_id: str) -> AdmissionRequest:
        item = await self._repo.get_admission_request(item_id)
        if item is None:
            raise AdmissionRuleViolation(f"admission request not found: {item_id}")
        return item

    async def _require_constraint_snapshot(self, item_id: str) -> TrialConstraintSnapshot:
        item = await self._repo.get_trial_constraint_snapshot(item_id)
        if item is None:
            raise AdmissionRuleViolation(f"trial constraint snapshot not found: {item_id}")
        return item

    async def _require_admission_decision(self, item_id: str) -> AdmissionDecision:
        item = await self._repo.get_admission_decision(item_id)
        if item is None:
            raise AdmissionRuleViolation(f"admission decision not found: {item_id}")
        return item


def _account_facts_issue(account_facts: dict[str, Any]) -> Optional[str]:
    if not account_facts:
        return "account facts unavailable"
    source = str(account_facts.get("source") or "").lower()
    truth_level = str(account_facts.get("truth_level") or "").lower()
    if source == "unavailable" or truth_level == "unavailable":
        return "account facts unavailable"
    reconciliation = account_facts.get("reconciliation_status")
    reconciliation_status = (
        str(reconciliation.get("status") or "").lower()
        if isinstance(reconciliation, dict)
        else str(account_facts.get("reconciliation_status_value") or "").lower()
    )
    if reconciliation_status == "mismatch":
        return "account reconciliation mismatch"
    unknown_counts = account_facts.get("unknown_unmanaged_counts")
    if isinstance(unknown_counts, dict):
        if int(unknown_counts.get("orders") or 0) > 0:
            return "unknown unmanaged exposure detected"
        if int(unknown_counts.get("positions") or 0) > 0:
            return "unknown unmanaged exposure detected"
    return None


def _first_active_binding(
    bindings: list[AdmissionTrialBinding],
) -> Optional[AdmissionTrialBinding]:
    for binding in bindings:
        if binding.binding_status in ACTIVE_ADMISSION_TRIAL_BINDING_STATUSES:
            return binding
    return None


def _gated_trial_readiness_unavailable(
    *,
    blockers: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "available": False,
        "ready": False,
        "blockers": list(blockers),
        "warnings": list(warnings),
        "admission_summary": {},
        "strategy_family_summary": {},
        "constraints_summary": {},
        "owner_risk_acceptance_summary": {"required": False, "provided": False, "valid": False},
        "binding_summary": {
            "reservation_available": False,
            "binding_would_create": False,
            "existing_active_binding_id": None,
        },
        "next_step": "Fix admission inputs before Operation preflight can continue.",
    }


def _gated_trial_readiness_from_decision(
    *,
    decision: AdmissionDecision,
    blockers: list[str],
    warnings: list[str],
    constraint: Optional[TrialConstraintSnapshot],
    acceptance: Optional[OwnerRiskAcceptance],
    requested_playbook_id: str,
    account_facts_snapshot_ref: Optional[str] = None,
    active_binding: Optional[AdmissionTrialBinding] = None,
) -> dict[str, Any]:
    constraints_json = dict(constraint.constraints_json) if constraint is not None else {}
    acceptance_required = decision.trial_stage == TrialStage.FUNDED_VALIDATION
    playbook_id = decision.playbook_id or requested_playbook_id or None
    return {
        "available": True,
        "ready": not blockers,
        "trial_env": decision.trial_env.value,
        "trial_stage": decision.trial_stage.value,
        "execution_mode": decision.execution_mode.value,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "admission_summary": {
            "admission_decision_id": decision.admission_decision_id,
            "admission_request_id": decision.admission_request_id,
            "admission_result": decision.decision.value,
            "expires_at_ms": decision.expires_at_ms,
            "created_at_ms": decision.created_at_ms,
        },
        "strategy_family_summary": {
            "strategy_family_version_id": decision.strategy_family_version_id,
            "playbook_id": playbook_id,
            "playbook_pinned": bool(playbook_id),
            "playbook_catalog_snapshot": decision.playbook_catalog_snapshot_json,
        },
        "constraints_summary": {
            "trial_constraint_snapshot_id": (
                constraint.trial_constraint_snapshot_id if constraint is not None else None
            ),
            "status": constraint.status.value if constraint is not None else None,
            "source": constraints_json.get("source"),
            "risk_profile": decision.risk_profile,
            "risk_policy_version": constraint.risk_policy_version if constraint is not None else None,
            "account_facts_snapshot_ref": account_facts_snapshot_ref,
            "max_loss_budget": constraints_json.get("max_loss_budget"),
            "max_notional": constraints_json.get("max_notional"),
            "max_leverage": constraints_json.get("max_leverage"),
            "max_attempts": constraints_json.get("max_attempts"),
            "allowed_symbols": list(constraints_json.get("allowed_symbols") or []),
            "allowed_timeframes": list(constraints_json.get("allowed_timeframes") or []),
            "review_requirements": dict(constraints_json.get("review_requirements") or {}),
            "cooldowns": dict(constraints_json.get("cooldowns") or {}),
            "limitations": list(constraints_json.get("limitations") or []),
        },
        "owner_risk_acceptance_summary": {
            "required": acceptance_required,
            "provided": acceptance is not None,
            "valid": acceptance is not None and not blockers,
            "owner_risk_acceptance_id": (
                acceptance.owner_risk_acceptance_id if acceptance is not None else None
            ),
            "confirmed_at_ms": acceptance.confirmed_at_ms if acceptance is not None else None,
            "account_facts_snapshot_ref": (
                acceptance.account_facts_snapshot_ref if acceptance is not None else None
            ),
        },
        "binding_summary": {
            "reservation_available": not blockers,
            "binding_would_create": not blockers,
            "existing_active_binding_id": (
                active_binding.binding_id if active_binding is not None else None
            ),
            "existing_active_binding_status": (
                active_binding.binding_status.value if active_binding is not None else None
            ),
            "binding_status_on_confirm": AdmissionTrialBindingStatus.BINDING_RESERVED.value,
            "campaign_will_be_created": False,
            "runtime_carrier_will_be_created": False,
            "runtime_constraints_will_be_installed": False,
            "orders_will_be_placed": False,
        },
        "next_step": (
            "Operation confirm can reserve an admission-trial binding only; trial runtime remains inactive."
            if not blockers
            else "Resolve blockers before admission-trial binding can be reserved."
        ),
    }


def _campaign_carrier_readiness_unavailable(
    *,
    blockers: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "available": False,
        "ready": False,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "admission_summary": {},
        "strategy_family_summary": {},
        "constraints_summary": {},
        "owner_risk_acceptance_summary": {"required": False, "provided": False, "valid": False},
        "binding_summary": {
            "binding_id": None,
            "binding_status": None,
            "campaign_creation_available": False,
            "campaign_would_create": False,
            "campaign_id": None,
        },
        "campaign_shell_summary": {
            "would_create_campaign_shell": False,
            "runtime_will_start": False,
            "constraints_will_be_installed": False,
            "orders_will_be_placed": False,
        },
        "next_step": "Fix admission binding inputs before campaign shell preflight can continue.",
    }


def _campaign_carrier_readiness_from_binding(
    *,
    binding: AdmissionTrialBinding,
    blockers: list[str],
    warnings: list[str],
    decision: Optional[AdmissionDecision],
    constraint: Optional[TrialConstraintSnapshot],
    acceptance: Optional[OwnerRiskAcceptance],
    account_facts_snapshot_ref: Optional[str],
) -> dict[str, Any]:
    constraints_json = dict(constraint.constraints_json) if constraint is not None else {}
    acceptance_required = binding.trial_stage == TrialStage.FUNDED_VALIDATION
    unique_blockers = list(dict.fromkeys(blockers))
    unique_warnings = list(dict.fromkeys(warnings))
    return {
        "available": True,
        "ready": not unique_blockers,
        "trial_env": binding.trial_env.value,
        "trial_stage": binding.trial_stage.value,
        "execution_mode": binding.execution_mode.value,
        "blockers": unique_blockers,
        "warnings": unique_warnings,
        "admission_summary": {
            "admission_decision_id": binding.admission_decision_id,
            "admission_request_id": decision.admission_request_id if decision is not None else None,
            "admission_result": decision.decision.value if decision is not None else None,
            "expires_at_ms": decision.expires_at_ms if decision is not None else None,
            "created_at_ms": decision.created_at_ms if decision is not None else None,
        },
        "strategy_family_summary": {
            "strategy_family_version_id": binding.strategy_family_version_id,
            "playbook_id": binding.playbook_id,
            "playbook_pinned": bool(binding.playbook_id),
            "playbook_catalog_snapshot": binding.playbook_catalog_snapshot_json,
        },
        "constraints_summary": {
            "trial_constraint_snapshot_id": binding.trial_constraint_snapshot_id,
            "status": constraint.status.value if constraint is not None else None,
            "source": constraints_json.get("source"),
            "risk_profile": constraint.risk_profile if constraint is not None else None,
            "risk_policy_version": constraint.risk_policy_version if constraint is not None else None,
            "account_facts_snapshot_ref": account_facts_snapshot_ref,
            "max_loss_budget": constraints_json.get("max_loss_budget"),
            "max_notional": constraints_json.get("max_notional"),
            "max_leverage": constraints_json.get("max_leverage"),
            "max_attempts": constraints_json.get("max_attempts"),
            "allowed_symbols": list(constraints_json.get("allowed_symbols") or []),
            "allowed_timeframes": list(constraints_json.get("allowed_timeframes") or []),
            "review_requirements": dict(constraints_json.get("review_requirements") or {}),
            "cooldowns": dict(constraints_json.get("cooldowns") or {}),
            "limitations": list(constraints_json.get("limitations") or []),
        },
        "owner_risk_acceptance_summary": {
            "required": acceptance_required,
            "provided": acceptance is not None,
            "valid": acceptance is not None and not unique_blockers,
            "owner_risk_acceptance_id": (
                acceptance.owner_risk_acceptance_id if acceptance is not None else None
            ),
            "confirmed_at_ms": acceptance.confirmed_at_ms if acceptance is not None else None,
            "account_facts_snapshot_ref": (
                acceptance.account_facts_snapshot_ref if acceptance is not None else None
            ),
        },
        "binding_summary": {
            "binding_id": binding.binding_id,
            "binding_status": binding.binding_status.value,
            "campaign_creation_available": not unique_blockers,
            "campaign_would_create": not unique_blockers,
            "campaign_id": binding.campaign_id,
            "runtime_carrier_id": binding.runtime_carrier_id,
            "created_by_operation_id": binding.created_by_operation_id,
            "created_by_preflight_id": binding.created_by_preflight_id,
            "created_at_ms": binding.created_at_ms,
        },
        "campaign_shell_summary": {
            "would_create_campaign_shell": not unique_blockers,
            "created_from_admission": True,
            "runtime_status": "not_installed",
            "strategy_status": "not_active",
            "constraints_installed": False,
            "orders_will_be_placed": False,
            "live_ready": False,
            "planned_result_status": AdmissionTrialBindingStatus.CAMPAIGN_CREATED.value,
        },
        "next_step": (
            "Operation confirm can create a campaign shell only; runtime remains not installed."
            if not unique_blockers
            else "Resolve blockers before admission binding can create a campaign shell."
        ),
    }


def _campaign_id(campaign: Optional[Any]) -> Optional[str]:
    if campaign is None:
        return None
    if isinstance(campaign, dict):
        value = campaign.get("campaign_id")
    else:
        value = getattr(campaign, "campaign_id", None)
    return str(value) if value is not None else None


def _campaign_metadata(campaign: Optional[Any]) -> dict[str, Any]:
    if campaign is None:
        return {}
    if isinstance(campaign, dict):
        value = campaign.get("metadata_json") or campaign.get("metadata") or {}
    else:
        value = getattr(campaign, "metadata_json", {}) or {}
    return dict(value) if isinstance(value, dict) else {}


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_intended_action(value: Any) -> str:
    action = str(value or "unknown").strip().lower()
    if action in {"enter", "open", "buy", "sell", "short", "long"}:
        return "entry"
    if action in {"add", "scale_in"}:
        return "increase"
    if action in {"close", "flatten"}:
        return "exit"
    if action in {"decrease", "trim", "scale_out"}:
        return "reduce"
    if action in {"entry", "increase", "exit", "reduce", "hold"}:
        return action
    return "unknown"


def _constraints_completeness(constraints_summary: dict[str, Any]) -> dict[str, Any]:
    required = ["max_loss_budget", "max_notional", "max_leverage", "max_attempts"]
    missing = [key for key in required if constraints_summary.get(key) in (None, "", [])]
    if not constraints_summary.get("allowed_symbols"):
        missing.append("allowed_symbols")
    return {
        "complete": not missing,
        "missing": missing,
        "required": required + ["allowed_symbols"],
        "source": constraints_summary.get("source"),
        "risk_profile": constraints_summary.get("risk_profile"),
        "max_loss_budget": constraints_summary.get("max_loss_budget"),
        "max_notional": constraints_summary.get("max_notional"),
        "max_leverage": constraints_summary.get("max_leverage"),
        "max_attempts": constraints_summary.get("max_attempts"),
        "allowed_symbols": list(constraints_summary.get("allowed_symbols") or []),
    }


def _account_facts_freshness_issue(account_facts: dict[str, Any]) -> Optional[str]:
    freshness = str(
        account_facts.get("freshness")
        or account_facts.get("freshness_status")
        or account_facts.get("staleness_status")
        or ""
    ).lower()
    if freshness in {"stale", "expired", "too_old"}:
        return "account facts freshness unacceptable"
    if account_facts.get("stale") is True:
        return "account facts freshness unacceptable"
    max_age_ms = account_facts.get("max_age_ms")
    age_ms = account_facts.get("age_ms") or account_facts.get("snapshot_age_ms")
    if max_age_ms is not None and age_ms is not None:
        try:
            if int(age_ms) > int(max_age_ms):
                return "account facts freshness unacceptable"
        except (TypeError, ValueError):
            return "account facts freshness unknown"
    return None


def _runtime_constraint_install_readiness_unavailable(
    *,
    blockers: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "available": False,
        "ready": False,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "admission_summary": {},
        "strategy_family_summary": {},
        "constraints_summary": {},
        "owner_risk_acceptance_summary": {"required": False, "provided": False, "valid": False},
        "binding_summary": {},
        "campaign_shell_summary": {
            "constraints_would_be_installed": False,
            "runtime_will_start": False,
            "strategy_will_activate": False,
            "orders_will_be_placed": False,
            "trial_remains_inactive_after_install": True,
        },
        "next_step": "Fix admission campaign inputs before runtime constraint installation can continue.",
    }


def _runtime_constraint_install_readiness_from_binding(
    *,
    binding: AdmissionTrialBinding,
    blockers: list[str],
    warnings: list[str],
    decision: Optional[AdmissionDecision],
    constraint: Optional[TrialConstraintSnapshot],
    acceptance: Optional[OwnerRiskAcceptance],
    campaign: Optional[Any],
    idempotent_install: bool,
    account_facts_snapshot_ref: Optional[str],
) -> dict[str, Any]:
    constraints_json = dict(constraint.constraints_json) if constraint is not None else {}
    acceptance_required = binding.trial_stage == TrialStage.FUNDED_VALIDATION
    unique_blockers = list(dict.fromkeys(blockers))
    unique_warnings = list(dict.fromkeys(warnings))
    campaign_metadata = _campaign_metadata(campaign)
    installation_available = not unique_blockers
    return {
        "available": True,
        "ready": installation_available,
        "idempotent_install": idempotent_install,
        "trial_env": binding.trial_env.value,
        "trial_stage": binding.trial_stage.value,
        "execution_mode": binding.execution_mode.value,
        "blockers": unique_blockers,
        "warnings": unique_warnings,
        "admission_summary": {
            "admission_decision_id": binding.admission_decision_id,
            "admission_request_id": decision.admission_request_id if decision is not None else None,
            "admission_result": decision.decision.value if decision is not None else None,
            "expires_at_ms": decision.expires_at_ms if decision is not None else None,
            "created_at_ms": decision.created_at_ms if decision is not None else None,
        },
        "strategy_family_summary": {
            "strategy_family_version_id": binding.strategy_family_version_id,
            "playbook_id": binding.playbook_id,
            "playbook_pinned": bool(binding.playbook_id),
            "playbook_catalog_snapshot": binding.playbook_catalog_snapshot_json,
        },
        "constraints_summary": {
            "trial_constraint_snapshot_id": binding.trial_constraint_snapshot_id,
            "status": constraint.status.value if constraint is not None else None,
            "source": constraints_json.get("source"),
            "risk_profile": constraint.risk_profile if constraint is not None else None,
            "risk_policy_version": constraint.risk_policy_version if constraint is not None else None,
            "account_facts_snapshot_ref": account_facts_snapshot_ref,
            "max_loss_budget": constraints_json.get("max_loss_budget"),
            "max_notional": constraints_json.get("max_notional"),
            "max_leverage": constraints_json.get("max_leverage"),
            "max_attempts": constraints_json.get("max_attempts"),
            "allowed_symbols": list(constraints_json.get("allowed_symbols") or []),
            "allowed_timeframes": list(constraints_json.get("allowed_timeframes") or []),
            "review_requirements": dict(constraints_json.get("review_requirements") or {}),
            "cooldowns": dict(constraints_json.get("cooldowns") or {}),
            "limitations": list(constraints_json.get("limitations") or []),
            "would_install": installation_available and not idempotent_install,
            "already_installed_idempotent": idempotent_install,
        },
        "owner_risk_acceptance_summary": {
            "required": acceptance_required,
            "provided": acceptance is not None,
            "valid": acceptance is not None and not unique_blockers,
            "owner_risk_acceptance_id": (
                acceptance.owner_risk_acceptance_id if acceptance is not None else None
            ),
            "confirmed_at_ms": acceptance.confirmed_at_ms if acceptance is not None else None,
            "account_facts_snapshot_ref": (
                acceptance.account_facts_snapshot_ref if acceptance is not None else None
            ),
        },
        "binding_summary": {
            "binding_id": binding.binding_id,
            "binding_status": binding.binding_status.value,
            "campaign_id": binding.campaign_id,
            "runtime_carrier_id": binding.runtime_carrier_id,
            "created_by_operation_id": binding.created_by_operation_id,
            "created_by_preflight_id": binding.created_by_preflight_id,
            "created_at_ms": binding.created_at_ms,
            "planned_result_status": AdmissionTrialBindingStatus.RUNTIME_CONSTRAINTS_INSTALLED.value,
        },
        "campaign_shell_summary": {
            "campaign_id": _campaign_id(campaign),
            "created_from_admission": campaign_metadata.get("created_from_admission") is True,
            "constraints_would_be_installed": installation_available and not idempotent_install,
            "runtime_will_start": False,
            "strategy_will_activate": False,
            "orders_will_be_placed": False,
            "trial_remains_inactive_after_install": True,
            "runtime_status_after_install": "constraints_installed_not_started",
            "strategy_status_after_install": "not_active",
            "auto_within_budget_enabled": False,
            "owner_confirm_each_entry_enabled": False,
            "live_ready": False,
        },
        "next_step": (
            "Operation confirm can install constraints metadata only; runtime remains not started."
            if installation_available and not idempotent_install
            else "Constraints metadata is already installed; confirm is idempotent and runtime remains not started."
            if installation_available
            else "Resolve blockers before installing runtime constraints metadata."
        ),
    }


def _runtime_summary_active(runtime_summary: dict[str, Any]) -> bool:
    if runtime_summary.get("runtime_active") is True:
        return True
    state = str(
        runtime_summary.get("current_runtime_state")
        or runtime_summary.get("runtime_state")
        or runtime_summary.get("status")
        or ""
    ).lower()
    return state in {"active", "running", "trade", "trading", "live_trade", "strategy_active"}


def _runtime_carrier_readiness_unavailable(
    *,
    blockers: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "available": False,
        "ready": False,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "admission_summary": {},
        "strategy_family_summary": {},
        "constraints_summary": {},
        "owner_risk_acceptance_summary": {"required": False, "provided": False, "valid": False},
        "binding_summary": {},
        "campaign_shell_summary": {},
        "runtime_carrier_summary": {
            "carrier_readiness_would_be_prepared": False,
            "runtime_will_start": False,
            "strategy_will_activate": False,
            "auto_execution_will_be_enabled": False,
            "orders_will_be_placed": False,
            "trial_remains_inactive_after_readiness_preparation": True,
        },
        "next_step": "Fix admission campaign inputs before runtime carrier readiness can continue.",
    }


def _runtime_carrier_readiness_from_binding(
    *,
    binding: AdmissionTrialBinding,
    blockers: list[str],
    warnings: list[str],
    decision: Optional[AdmissionDecision],
    constraint: Optional[TrialConstraintSnapshot],
    campaign: Optional[Any],
    idempotent_prepare: bool,
) -> dict[str, Any]:
    campaign_metadata = _campaign_metadata(campaign)
    unique_blockers = list(dict.fromkeys(blockers))
    unique_warnings = list(dict.fromkeys(warnings))
    preparation_available = not unique_blockers
    return {
        "available": True,
        "ready": preparation_available,
        "idempotent_prepare": idempotent_prepare,
        "trial_env": binding.trial_env.value,
        "trial_stage": binding.trial_stage.value,
        "execution_mode": binding.execution_mode.value,
        "blockers": unique_blockers,
        "warnings": unique_warnings,
        "admission_summary": {
            "admission_decision_id": binding.admission_decision_id,
            "admission_request_id": decision.admission_request_id if decision is not None else None,
            "admission_result": decision.decision.value if decision is not None else None,
            "expires_at_ms": decision.expires_at_ms if decision is not None else None,
            "created_at_ms": decision.created_at_ms if decision is not None else None,
        },
        "strategy_family_summary": {
            "strategy_family_version_id": binding.strategy_family_version_id,
            "playbook_id": binding.playbook_id,
            "playbook_pinned": bool(binding.playbook_id),
            "playbook_catalog_snapshot": binding.playbook_catalog_snapshot_json,
        },
        "constraints_summary": {
            "trial_constraint_snapshot_id": binding.trial_constraint_snapshot_id,
            "installed_constraint_snapshot_id": campaign_metadata.get("installed_constraint_snapshot_id"),
            "constraints_installed": campaign_metadata.get("constraints_installed") is True,
            "status": constraint.status.value if constraint is not None else None,
            "risk_profile": constraint.risk_profile if constraint is not None else None,
            "risk_policy_version": constraint.risk_policy_version if constraint is not None else None,
        },
        "owner_risk_acceptance_summary": {
            "required": binding.trial_stage == TrialStage.FUNDED_VALIDATION,
            "provided": bool(binding.owner_risk_acceptance_id),
            "owner_risk_acceptance_id": binding.owner_risk_acceptance_id,
        },
        "binding_summary": {
            "binding_id": binding.binding_id,
            "binding_status": binding.binding_status.value,
            "campaign_id": binding.campaign_id,
            "runtime_carrier_id": binding.runtime_carrier_id,
            "created_by_operation_id": binding.created_by_operation_id,
            "created_by_preflight_id": binding.created_by_preflight_id,
            "created_at_ms": binding.created_at_ms,
            "planned_result_status": "carrier_ready",
            "binding_status_after_prepare": binding.binding_status.value,
        },
        "campaign_shell_summary": {
            "campaign_id": _campaign_id(campaign),
            "created_from_admission": campaign_metadata.get("created_from_admission") is True,
            "runtime_status": campaign_metadata.get("runtime_status"),
            "carrier_ready": campaign_metadata.get("carrier_ready") is True,
            "runtime_started": campaign_metadata.get("runtime_started") is True,
            "strategy_active": campaign_metadata.get("strategy_active") is True,
            "trial_started": campaign_metadata.get("trial_started") is True,
            "orders_placed": campaign_metadata.get("orders_placed") is True,
            "auto_within_budget_enabled": campaign_metadata.get("auto_within_budget_enabled") is True,
        },
        "runtime_carrier_summary": {
            "carrier_readiness_would_be_prepared": preparation_available and not idempotent_prepare,
            "already_prepared_idempotent": idempotent_prepare,
            "runtime_status_after_prepare": "carrier_ready_not_started",
            "carrier_ready": preparation_available,
            "runtime_will_start": False,
            "strategy_will_activate": False,
            "auto_execution_will_be_enabled": False,
            "orders_will_be_placed": False,
            "trial_remains_inactive_after_readiness_preparation": True,
            "auto_within_budget_enabled": False,
            "owner_confirm_each_entry_enabled": False,
            "live_ready": False,
        },
        "next_step": (
            "Operation confirm can prepare runtime carrier readiness metadata only; runtime remains not started."
            if preparation_available and not idempotent_prepare
            else "Runtime carrier readiness metadata is already prepared; confirm is idempotent and runtime remains not started."
            if preparation_available
            else "Resolve blockers before preparing runtime carrier readiness metadata."
        ),
    }


def _runtime_start_readiness_unavailable(
    *,
    blockers: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "available": False,
        "ready": False,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "admission_summary": {},
        "strategy_family_summary": {},
        "constraints_summary": {},
        "owner_risk_acceptance_summary": {"required": False, "provided": False, "valid": False},
        "binding_summary": {},
        "campaign_shell_summary": {},
        "runtime_carrier_summary": {},
        "runtime_start_summary": {
            "runtime_start_readiness_would_be_prepared": False,
            "runtime_will_start": False,
            "strategy_will_activate": False,
            "auto_execution_will_be_enabled": False,
            "orders_will_be_placed": False,
            "next_phase_must_handle_execution_mode_enforcement": True,
        },
        "next_step": "Fix admission carrier inputs before runtime start readiness can continue.",
    }


def _runtime_start_readiness_from_binding(
    *,
    binding: AdmissionTrialBinding,
    blockers: list[str],
    warnings: list[str],
    decision: Optional[AdmissionDecision],
    constraint: Optional[TrialConstraintSnapshot],
    campaign: Optional[Any],
    idempotent_prepare: bool,
) -> dict[str, Any]:
    campaign_metadata = _campaign_metadata(campaign)
    unique_blockers = list(dict.fromkeys(blockers))
    unique_warnings = list(dict.fromkeys(warnings))
    preparation_available = not unique_blockers
    execution_mode_value = (
        binding.execution_mode.value
        if hasattr(binding.execution_mode, "value")
        else str(binding.execution_mode)
    )
    constraints_summary = dict(campaign_metadata.get("installed_constraints_summary") or {})
    return {
        "available": True,
        "ready": preparation_available,
        "idempotent_prepare": idempotent_prepare,
        "trial_env": binding.trial_env.value,
        "trial_stage": binding.trial_stage.value,
        "execution_mode": execution_mode_value,
        "blockers": unique_blockers,
        "warnings": unique_warnings,
        "admission_summary": {
            "admission_decision_id": binding.admission_decision_id,
            "admission_request_id": decision.admission_request_id if decision is not None else None,
            "admission_result": decision.decision.value if decision is not None else None,
            "expires_at_ms": decision.expires_at_ms if decision is not None else None,
            "created_at_ms": decision.created_at_ms if decision is not None else None,
        },
        "strategy_family_summary": {
            "strategy_family_version_id": binding.strategy_family_version_id,
            "playbook_id": binding.playbook_id,
            "playbook_pinned": bool(binding.playbook_id),
            "playbook_catalog_snapshot": binding.playbook_catalog_snapshot_json,
        },
        "constraints_summary": {
            "trial_constraint_snapshot_id": binding.trial_constraint_snapshot_id,
            "installed_constraint_snapshot_id": campaign_metadata.get("installed_constraint_snapshot_id"),
            "constraints_installed": campaign_metadata.get("constraints_installed") is True,
            "installed_constraints_summary_exists": bool(constraints_summary),
            "status": constraint.status.value if constraint is not None else None,
            "risk_profile": constraint.risk_profile if constraint is not None else None,
            "risk_policy_version": constraint.risk_policy_version if constraint is not None else None,
        },
        "owner_risk_acceptance_summary": {
            "required": binding.trial_stage == TrialStage.FUNDED_VALIDATION,
            "provided": bool(binding.owner_risk_acceptance_id),
            "owner_risk_acceptance_id": binding.owner_risk_acceptance_id,
        },
        "binding_summary": {
            "binding_id": binding.binding_id,
            "binding_status": binding.binding_status.value,
            "campaign_id": binding.campaign_id,
            "runtime_carrier_id": binding.runtime_carrier_id,
            "planned_result_status": "runtime_start_ready",
            "binding_status_after_prepare": binding.binding_status.value,
        },
        "campaign_shell_summary": {
            "campaign_id": _campaign_id(campaign),
            "created_from_admission": campaign_metadata.get("created_from_admission") is True,
            "runtime_status": campaign_metadata.get("runtime_status"),
            "carrier_ready": campaign_metadata.get("carrier_ready") is True,
            "runtime_start_ready": campaign_metadata.get("runtime_start_ready") is True,
            "runtime_started": campaign_metadata.get("runtime_started") is True,
            "strategy_active": campaign_metadata.get("strategy_active") is True,
            "trial_started": campaign_metadata.get("trial_started") is True,
            "orders_placed": campaign_metadata.get("orders_placed") is True,
            "auto_within_budget_enabled": campaign_metadata.get("auto_within_budget_enabled") is True,
        },
        "runtime_carrier_summary": {
            "carrier_ready": campaign_metadata.get("carrier_ready") is True,
            "runtime_status": campaign_metadata.get("runtime_status"),
            "runtime_will_start": False,
            "strategy_will_activate": False,
            "auto_execution_will_be_enabled": False,
            "orders_will_be_placed": False,
        },
        "runtime_start_summary": {
            "runtime_start_readiness_would_be_prepared": preparation_available and not idempotent_prepare,
            "already_prepared_idempotent": idempotent_prepare,
            "runtime_status_after_prepare": "runtime_start_ready_not_started",
            "runtime_start_ready": preparation_available,
            "runtime_will_start": False,
            "strategy_will_activate": False,
            "auto_execution_will_be_enabled": False,
            "orders_will_be_placed": False,
            "next_phase_must_handle_execution_mode_enforcement": True,
            "auto_within_budget_enabled": False,
            "owner_confirm_each_entry_enabled": False,
            "live_ready": False,
        },
        "next_step": (
            "Operation confirm can prepare runtime start readiness metadata only; runtime remains not started."
            if preparation_available and not idempotent_prepare
            else "Runtime start readiness metadata is already prepared; confirm is idempotent and runtime remains not started."
            if preparation_available
            else "Resolve blockers before preparing runtime start readiness metadata."
        ),
    }


def _trial_trade_intent_readiness_from_context(
    *,
    campaign_id: str,
    binding: Optional[AdmissionTrialBinding],
    campaign_metadata: dict[str, Any],
    constraint: Optional[TrialConstraintSnapshot],
    intended_action: str,
    symbol: str,
    side: Optional[str],
    execution_mode: Optional[AdmissionExecutionMode],
    blockers: list[str],
    warnings: list[str],
    constraints_completeness: dict[str, Any],
    enforcement_decision: TrialTradeIntentDecision,
    not_executed_reason: str,
    intent_would_be_persisted: bool,
    would_require_runtime_execution: bool,
    now_ms_value: int,
) -> dict[str, Any]:
    unique_blockers = list(dict.fromkeys(blockers))
    unique_warnings = list(dict.fromkeys(warnings))
    execution_mode_value = execution_mode.value if execution_mode is not None else None
    available = execution_mode not in {AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY}
    ready = not unique_blockers and available
    mode_unavailable = execution_mode == AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY
    return {
        "available": available,
        "ready": ready,
        "mode_unavailable": mode_unavailable,
        "blockers": unique_blockers,
        "warnings": unique_warnings,
        "phase": "BRC-R5-002 Phase 9",
        "campaign_id": campaign_id,
        "binding_id": binding.binding_id if binding is not None else campaign_metadata.get("admission_binding_id"),
        "admission_decision_id": (
            binding.admission_decision_id
            if binding is not None
            else campaign_metadata.get("admission_decision_id")
        ),
        "strategy_family_version_id": (
            binding.strategy_family_version_id
            if binding is not None
            else campaign_metadata.get("strategy_family_version_id")
        ),
        "playbook_id": binding.playbook_id if binding is not None else campaign_metadata.get("playbook_id"),
        "execution_mode": execution_mode_value,
        "intended_action": intended_action,
        "symbol": symbol,
        "side": side,
        "constraints_check": {
            **constraints_completeness,
            "trial_constraint_snapshot_id": (
                constraint.trial_constraint_snapshot_id if constraint is not None else None
            ),
            "constraint_snapshot_status": constraint.status.value if constraint is not None else None,
            "constraints_snapshot_exists": constraint is not None,
        },
        "enforcement": {
            "trial_trade_intent_result": enforcement_decision.value,
            "not_executed_reason": not_executed_reason,
            "intent_would_be_persisted": ready and intent_would_be_persisted,
            "would_require_runtime_execution": would_require_runtime_execution,
            "order_would_be_created": False,
            "execution_intent_would_be_created": False,
            "runtime_will_start": False,
            "strategy_will_activate": False,
            "auto_execution_will_be_enabled": False,
            "orders_will_be_placed": False,
            "trial_trade_intent_is_order": False,
            "auto_within_budget_check_is_execution_enablement": False,
        },
        "trade_intent_summary": {
            "evaluated_at_ms": now_ms_value,
            "non_executable_evidence_only": True,
            "intent_would_be_recorded": ready and intent_would_be_persisted,
            "trial_trade_intent_result": enforcement_decision.value,
            "not_executed_reason": not_executed_reason,
            "runtime_started": False,
            "strategy_active": False,
            "orders_placed": False,
            "live_ready": False,
        },
        "next_step": (
            "Confirm can record a non-executable trial trade intent only."
            if ready and intent_would_be_persisted
            else "Confirm can return an auto-within-budget constraints check only; execution remains future work."
            if ready and execution_mode == AdmissionExecutionMode.AUTO_WITHIN_BUDGET
            else "owner_confirm_each_entry is reserved and not implemented."
            if mode_unavailable
            else "Resolve blockers before evaluating trial trade intent."
        ),
    }


def _signal_trial_trade_intent_readiness_from_context(
    *,
    campaign_id: str,
    binding: Optional[AdmissionTrialBinding],
    campaign_metadata: dict[str, Any],
    constraint: Optional[TrialConstraintSnapshot],
    intended_action: str,
    symbol: str,
    side: Optional[str],
    execution_mode: Optional[AdmissionExecutionMode],
    blockers: list[str],
    warnings: list[str],
    constraints_completeness: dict[str, Any],
    enforcement_decision: TrialTradeIntentDecision,
    not_executed_reason: str,
    intent_would_be_persisted: bool,
    account_facts: Optional[dict[str, Any]],
    idempotent_intent: bool,
    now_ms_value: int,
) -> dict[str, Any]:
    unique_blockers = list(dict.fromkeys(blockers))
    unique_warnings = list(dict.fromkeys(warnings))
    execution_mode_value = execution_mode.value if execution_mode is not None else None
    mode_unavailable = execution_mode == AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY
    available = execution_mode is not None and not mode_unavailable
    ready = not unique_blockers and available
    return {
        "available": available,
        "ready": ready,
        "mode_unavailable": mode_unavailable,
        "idempotent_intent": idempotent_intent,
        "blockers": unique_blockers,
        "warnings": unique_warnings,
        "phase": "BRC-R5-002 Phase 18",
        "campaign_id": campaign_id,
        "binding_id": binding.binding_id if binding is not None else campaign_metadata.get("admission_binding_id"),
        "admission_decision_id": (
            binding.admission_decision_id
            if binding is not None
            else campaign_metadata.get("admission_decision_id")
        ),
        "strategy_family_version_id": (
            binding.strategy_family_version_id
            if binding is not None
            else campaign_metadata.get("strategy_family_version_id")
        ),
        "playbook_id": binding.playbook_id if binding is not None else campaign_metadata.get("playbook_id"),
        "execution_mode": execution_mode_value,
        "intended_action": intended_action,
        "symbol": symbol,
        "side": side,
        "campaign_metadata": dict(campaign_metadata),
        "account_facts": dict(account_facts or {}),
        "trial_trade_intent_id": campaign_metadata.get("trial_trade_intent_id"),
        "constraints_check": {
            **constraints_completeness,
            "trial_constraint_snapshot_id": (
                constraint.trial_constraint_snapshot_id if constraint is not None else None
            ),
            "constraint_snapshot_status": constraint.status.value if constraint is not None else None,
            "constraints_snapshot_exists": constraint is not None,
        },
        "enforcement": {
            "trial_trade_intent_result": enforcement_decision.value,
            "not_executed_reason": not_executed_reason,
            "intent_would_be_persisted": ready and intent_would_be_persisted and not idempotent_intent,
            "already_recorded_idempotent": idempotent_intent,
            "order_would_be_created": False,
            "execution_intent_would_be_created": False,
            "runtime_will_start": False,
            "strategy_will_activate": False,
            "auto_execution_will_be_enabled": False,
            "orders_will_be_placed": False,
            "trial_trade_intent_is_order": False,
        },
        "trade_intent_summary": {
            "evaluated_at_ms": now_ms_value,
            "non_executable_evidence_only": True,
            "intent_would_be_recorded": ready and intent_would_be_persisted and not idempotent_intent,
            "already_recorded_idempotent": idempotent_intent,
            "trial_trade_intent_result": enforcement_decision.value,
            "not_executed_reason": not_executed_reason,
            "runtime_status_after_confirm": "trial_trade_intent_recorded_no_execution",
            "execution_intent_created": False,
            "order_created": False,
            "orders_placed": False,
            "trial_started": False,
            "auto_execution_enabled": False,
            "auto_within_budget_enabled": False,
            "live_ready": False,
        },
        "next_step": (
            "Confirm can record a non-executable trial trade intent from signal evaluation."
            if ready and intent_would_be_persisted and not idempotent_intent
            else "Trial trade intent is already recorded without execution; confirm is idempotent."
            if ready and idempotent_intent
            else "owner_confirm_each_entry is reserved and not implemented."
            if mode_unavailable
            else "Resolve blockers before recording trial trade intent evidence."
        ),
    }


def _runtime_handoff_readiness_from_context(
    *,
    campaign_id: str,
    binding: Optional[AdmissionTrialBinding],
    blockers: list[str],
    warnings: list[str],
    decision: Optional[AdmissionDecision],
    constraint: Optional[TrialConstraintSnapshot],
    campaign: Optional[Any],
    constraints_completeness: dict[str, Any],
    execution_mode: Optional[AdmissionExecutionMode],
    idempotent_prepare: bool,
    trade_intent_ledger_available: bool,
) -> dict[str, Any]:
    campaign_metadata = _campaign_metadata(campaign)
    unique_blockers = list(dict.fromkeys(blockers))
    unique_warnings = list(dict.fromkeys(warnings))
    preparation_available = not unique_blockers
    execution_mode_value = execution_mode.value if execution_mode is not None else None
    return {
        "available": True,
        "ready": preparation_available,
        "idempotent_prepare": idempotent_prepare,
        "phase": "BRC-R5-002 Phase 10",
        "trial_env": binding.trial_env.value if binding is not None else campaign_metadata.get("trial_env"),
        "trial_stage": binding.trial_stage.value if binding is not None else campaign_metadata.get("trial_stage"),
        "execution_mode": execution_mode_value,
        "blockers": unique_blockers,
        "warnings": unique_warnings,
        "admission_summary": {
            "admission_decision_id": (
                binding.admission_decision_id
                if binding is not None
                else campaign_metadata.get("admission_decision_id")
            ),
            "admission_request_id": decision.admission_request_id if decision is not None else None,
            "admission_result": decision.decision.value if decision is not None else None,
            "expires_at_ms": decision.expires_at_ms if decision is not None else None,
            "created_at_ms": decision.created_at_ms if decision is not None else None,
        },
        "strategy_family_summary": {
            "strategy_family_version_id": (
                binding.strategy_family_version_id
                if binding is not None
                else campaign_metadata.get("strategy_family_version_id")
            ),
            "playbook_id": binding.playbook_id if binding is not None else campaign_metadata.get("playbook_id"),
            "playbook_pinned": bool(
                binding.playbook_id if binding is not None else campaign_metadata.get("playbook_id")
            ),
            "playbook_catalog_snapshot": (
                binding.playbook_catalog_snapshot_json if binding is not None else {}
            ),
        },
        "constraints_summary": {
            "trial_constraint_snapshot_id": (
                binding.trial_constraint_snapshot_id
                if binding is not None
                else campaign_metadata.get("installed_constraint_snapshot_id")
            ),
            "installed_constraint_snapshot_id": campaign_metadata.get("installed_constraint_snapshot_id"),
            "constraints_installed": campaign_metadata.get("constraints_installed") is True,
            "installed_constraints_summary_exists": bool(campaign_metadata.get("installed_constraints_summary") or {}),
            "status": constraint.status.value if constraint is not None else None,
            "risk_profile": constraint.risk_profile if constraint is not None else None,
            "risk_policy_version": constraint.risk_policy_version if constraint is not None else None,
            "completeness": constraints_completeness,
        },
        "binding_summary": {
            "binding_id": binding.binding_id if binding is not None else campaign_metadata.get("admission_binding_id"),
            "binding_status": binding.binding_status.value if binding is not None else None,
            "campaign_id": campaign_id,
            "runtime_carrier_id": binding.runtime_carrier_id if binding is not None else None,
            "planned_result_status": "runtime_handoff_ready",
            "binding_status_after_prepare": (
                binding.binding_status.value if binding is not None else None
            ),
        },
        "campaign_shell_summary": {
            "campaign_id": _campaign_id(campaign),
            "created_from_admission": campaign_metadata.get("created_from_admission") is True,
            "runtime_status": campaign_metadata.get("runtime_status"),
            "carrier_ready": campaign_metadata.get("carrier_ready") is True,
            "runtime_start_ready": campaign_metadata.get("runtime_start_ready") is True,
            "runtime_handoff_ready": campaign_metadata.get("runtime_handoff_ready") is True,
            "runtime_started": campaign_metadata.get("runtime_started") is True,
            "strategy_active": campaign_metadata.get("strategy_active") is True,
            "trial_started": campaign_metadata.get("trial_started") is True,
            "orders_placed": campaign_metadata.get("orders_placed") is True,
            "auto_within_budget_enabled": campaign_metadata.get("auto_within_budget_enabled") is True,
        },
        "runtime_handoff_summary": {
            "runtime_handoff_readiness_would_be_prepared": preparation_available and not idempotent_prepare,
            "already_prepared_idempotent": idempotent_prepare,
            "runtime_status_after_prepare": "runtime_handoff_ready_not_started",
            "runtime_handoff_ready": preparation_available,
            "runtime_will_start": False,
            "strategy_will_activate": False,
            "auto_execution_will_be_enabled": False,
            "orders_will_be_placed": False,
            "trial_started_after_prepare": False,
            "next_phase_must_explicitly_start_runtime": True,
            "execution_mode_contract_available": preparation_available,
            "trade_intent_ledger_available": trade_intent_ledger_available,
            "auto_within_budget_enabled": False,
            "owner_confirm_each_entry_enabled": False,
            "live_ready": False,
        },
        "next_step": (
            "Operation confirm can prepare runtime handoff readiness metadata only; a separate future Operation must start runtime."
            if preparation_available and not idempotent_prepare
            else "Runtime handoff readiness metadata is already prepared; confirm is idempotent and runtime remains not started."
            if preparation_available
            else "Resolve blockers before preparing runtime handoff readiness metadata."
        ),
    }


def _start_runtime_from_handoff_readiness_from_context(
    *,
    campaign_id: str,
    binding: Optional[AdmissionTrialBinding],
    blockers: list[str],
    warnings: list[str],
    decision: Optional[AdmissionDecision],
    constraint: Optional[TrialConstraintSnapshot],
    campaign: Optional[Any],
    runtime_summary: dict[str, Any],
    constraints_completeness: dict[str, Any],
    execution_mode: Optional[AdmissionExecutionMode],
    trade_intent_ledger_available: bool,
    idempotent_start: bool,
) -> dict[str, Any]:
    campaign_metadata = _campaign_metadata(campaign)
    unique_blockers = list(dict.fromkeys(blockers))
    unique_warnings = list(dict.fromkeys(warnings))
    start_conditions_met = not unique_blockers
    execution_mode_value = execution_mode.value if execution_mode is not None else None
    return {
        "available": True,
        "ready": start_conditions_met,
        "phase": "BRC-R5-002 Phase 12",
        "preflight_only": False,
        "idempotent_start": idempotent_start,
        "trial_env": binding.trial_env.value if binding is not None else campaign_metadata.get("trial_env"),
        "trial_stage": binding.trial_stage.value if binding is not None else campaign_metadata.get("trial_stage"),
        "execution_mode": execution_mode_value,
        "blockers": unique_blockers,
        "warnings": unique_warnings,
        "admission_summary": {
            "admission_decision_id": (
                binding.admission_decision_id
                if binding is not None
                else campaign_metadata.get("admission_decision_id")
            ),
            "admission_request_id": decision.admission_request_id if decision is not None else None,
            "admission_result": decision.decision.value if decision is not None else None,
            "expires_at_ms": decision.expires_at_ms if decision is not None else None,
        },
        "strategy_family_summary": {
            "strategy_family_version_id": (
                binding.strategy_family_version_id
                if binding is not None
                else campaign_metadata.get("strategy_family_version_id")
            ),
            "playbook_id": binding.playbook_id if binding is not None else campaign_metadata.get("playbook_id"),
            "playbook_pinned": bool(
                binding.playbook_id if binding is not None else campaign_metadata.get("playbook_id")
            ),
        },
        "constraints_summary": {
            "trial_constraint_snapshot_id": (
                binding.trial_constraint_snapshot_id
                if binding is not None
                else campaign_metadata.get("installed_constraint_snapshot_id")
            ),
            "installed_constraint_snapshot_id": campaign_metadata.get("installed_constraint_snapshot_id"),
            "constraints_installed": campaign_metadata.get("constraints_installed") is True,
            "status": constraint.status.value if constraint is not None else None,
            "risk_profile": constraint.risk_profile if constraint is not None else None,
            "completeness": constraints_completeness,
        },
        "binding_summary": {
            "binding_id": binding.binding_id if binding is not None else campaign_metadata.get("admission_binding_id"),
            "binding_status": binding.binding_status.value if binding is not None else None,
            "campaign_id": campaign_id,
            "planned_result_status": "runtime_started_strategy_inactive",
            "binding_status_after_start": (
                binding.binding_status.value if binding is not None else None
            ),
        },
        "campaign_shell_summary": {
            "campaign_id": _campaign_id(campaign),
            "runtime_status": campaign_metadata.get("runtime_status"),
            "carrier_ready": campaign_metadata.get("carrier_ready") is True,
            "runtime_start_ready": campaign_metadata.get("runtime_start_ready") is True,
            "runtime_handoff_ready": campaign_metadata.get("runtime_handoff_ready") is True,
            "runtime_started": campaign_metadata.get("runtime_started") is True,
            "strategy_active": campaign_metadata.get("strategy_active") is True,
            "trial_started": campaign_metadata.get("trial_started") is True,
            "orders_placed": campaign_metadata.get("orders_placed") is True,
        },
        "runtime_start_summary": {
            "start_conditions_met": start_conditions_met,
            "start_would_be_possible": start_conditions_met,
            "runtime_state_can_be_started": start_conditions_met and not idempotent_start,
            "already_started_idempotent": idempotent_start,
            "runtime_status_after_start": "runtime_started_strategy_inactive",
            "runtime_will_start": start_conditions_met and not idempotent_start,
            "runtime_started_after_confirm": start_conditions_met,
            "strategy_will_activate": False,
            "strategy_active_after_start": False,
            "trial_started_after_start": False,
            "auto_execution_will_be_enabled": False,
            "orders_will_be_placed": False,
            "execution_intent_will_be_created": False,
            "runtime_start_confirm_implemented": True,
            "next_required_implementation": "strategy activation / execution mode runtime enforcement Operation",
            "execution_mode_contract_present": execution_mode is not None,
            "trade_intent_ledger_available": trade_intent_ledger_available,
            "runtime_profile": runtime_summary.get("profile"),
            "runtime_env_testnet": runtime_summary.get("testnet"),
            "runtime_state": runtime_summary.get("current_runtime_state")
            or runtime_summary.get("runtime_state"),
            "emergency_stop_or_hard_lock_active": str(
                runtime_summary.get("current_runtime_state")
                or runtime_summary.get("runtime_state")
                or ""
            ).lower()
            in {"hard_locked", "hard_lock", "emergency_stopped", "emergency_stop", "flatten_required"},
        },
        "next_step": (
            "Runtime state is already started with strategy inactive; confirm is idempotent and should return noop."
            if start_conditions_met and idempotent_start
            else "Operation confirm can start runtime state only. A separate future Operation must activate strategy / execution-mode runtime."
            if start_conditions_met
            else "Resolve blockers before starting runtime state."
        ),
    }


def _strategy_activation_readiness_from_context(
    *,
    campaign_id: str,
    binding: Optional[AdmissionTrialBinding],
    blockers: list[str],
    warnings: list[str],
    decision: Optional[AdmissionDecision],
    constraint: Optional[TrialConstraintSnapshot],
    campaign: Optional[Any],
    execution_mode: Optional[AdmissionExecutionMode],
    idempotent_prepare: bool,
) -> dict[str, Any]:
    campaign_metadata = _campaign_metadata(campaign)
    unique_blockers = list(dict.fromkeys(blockers))
    unique_warnings = list(dict.fromkeys(warnings))
    preparation_available = not unique_blockers
    execution_mode_value = execution_mode.value if execution_mode is not None else None
    return {
        "available": True,
        "ready": preparation_available,
        "idempotent_prepare": idempotent_prepare,
        "phase": "BRC-R5-002 Phase 13",
        "trial_env": binding.trial_env.value if binding is not None else campaign_metadata.get("trial_env"),
        "trial_stage": binding.trial_stage.value if binding is not None else campaign_metadata.get("trial_stage"),
        "execution_mode": execution_mode_value,
        "blockers": unique_blockers,
        "warnings": unique_warnings,
        "admission_summary": {
            "admission_decision_id": (
                binding.admission_decision_id
                if binding is not None
                else campaign_metadata.get("admission_decision_id")
            ),
            "admission_request_id": decision.admission_request_id if decision is not None else None,
            "admission_result": decision.decision.value if decision is not None else None,
            "expires_at_ms": decision.expires_at_ms if decision is not None else None,
        },
        "strategy_family_summary": {
            "strategy_family_version_id": (
                binding.strategy_family_version_id
                if binding is not None
                else campaign_metadata.get("strategy_family_version_id")
            ),
            "playbook_id": binding.playbook_id if binding is not None else campaign_metadata.get("playbook_id"),
            "playbook_pinned": bool(
                binding.playbook_id if binding is not None else campaign_metadata.get("playbook_id")
            ),
        },
        "constraints_summary": {
            "trial_constraint_snapshot_id": (
                binding.trial_constraint_snapshot_id
                if binding is not None
                else campaign_metadata.get("installed_constraint_snapshot_id")
            ),
            "installed_constraint_snapshot_id": campaign_metadata.get("installed_constraint_snapshot_id"),
            "constraints_installed": campaign_metadata.get("constraints_installed") is True,
            "status": constraint.status.value if constraint is not None else None,
            "risk_profile": constraint.risk_profile if constraint is not None else None,
        },
        "binding_summary": {
            "binding_id": binding.binding_id if binding is not None else campaign_metadata.get("admission_binding_id"),
            "binding_status": binding.binding_status.value if binding is not None else None,
            "campaign_id": campaign_id,
            "planned_result_status": "strategy_activation_ready",
            "binding_status_after_prepare": (
                binding.binding_status.value if binding is not None else None
            ),
        },
        "campaign_shell_summary": {
            "campaign_id": _campaign_id(campaign),
            "runtime_status": campaign_metadata.get("runtime_status"),
            "runtime_started": campaign_metadata.get("runtime_started") is True,
            "strategy_activation_ready": campaign_metadata.get("strategy_activation_ready") is True,
            "strategy_active": campaign_metadata.get("strategy_active") is True,
            "trial_started": campaign_metadata.get("trial_started") is True,
            "signal_loop_started": campaign_metadata.get("signal_loop_started") is True,
            "orders_placed": campaign_metadata.get("orders_placed") is True,
            "auto_execution_enabled": campaign_metadata.get("auto_execution_enabled") is True,
            "auto_within_budget_enabled": campaign_metadata.get("auto_within_budget_enabled") is True,
        },
        "strategy_activation_summary": {
            "strategy_activation_readiness_would_be_prepared": preparation_available and not idempotent_prepare,
            "already_prepared_idempotent": idempotent_prepare,
            "runtime_status_after_prepare": "strategy_activation_ready_not_active",
            "strategy_activation_ready": preparation_available,
            "strategy_will_activate": False,
            "signal_loop_will_start": False,
            "trial_started_after_prepare": False,
            "auto_execution_will_be_enabled": False,
            "auto_within_budget_will_be_enabled": False,
            "execution_intent_will_be_created": False,
            "orders_will_be_placed": False,
            "live_ready": False,
            "next_phase_must_explicitly_activate_strategy": True,
        },
        "next_step": (
            "Operation confirm can prepare strategy activation readiness metadata only; a separate future Operation must activate strategy."
            if preparation_available and not idempotent_prepare
            else "Strategy activation readiness metadata is already prepared; confirm is idempotent and strategy remains inactive."
            if preparation_available
            else "Resolve blockers before preparing strategy activation readiness metadata."
        ),
    }


def _strategy_state_activation_readiness_from_context(
    *,
    campaign_id: str,
    binding: Optional[AdmissionTrialBinding],
    blockers: list[str],
    warnings: list[str],
    decision: Optional[AdmissionDecision],
    constraint: Optional[TrialConstraintSnapshot],
    campaign: Optional[Any],
    execution_mode: Optional[AdmissionExecutionMode],
    idempotent_activate: bool,
) -> dict[str, Any]:
    campaign_metadata = _campaign_metadata(campaign)
    unique_blockers = list(dict.fromkeys(blockers))
    unique_warnings = list(dict.fromkeys(warnings))
    activation_available = not unique_blockers
    execution_mode_value = execution_mode.value if execution_mode is not None else None
    return {
        "available": True,
        "ready": activation_available,
        "idempotent_activate": idempotent_activate,
        "phase": "BRC-R5-002 Phase 14",
        "trial_env": binding.trial_env.value if binding is not None else campaign_metadata.get("trial_env"),
        "trial_stage": binding.trial_stage.value if binding is not None else campaign_metadata.get("trial_stage"),
        "execution_mode": execution_mode_value,
        "blockers": unique_blockers,
        "warnings": unique_warnings,
        "admission_summary": {
            "admission_decision_id": (
                binding.admission_decision_id
                if binding is not None
                else campaign_metadata.get("admission_decision_id")
            ),
            "admission_request_id": decision.admission_request_id if decision is not None else None,
            "admission_result": decision.decision.value if decision is not None else None,
            "expires_at_ms": decision.expires_at_ms if decision is not None else None,
        },
        "strategy_family_summary": {
            "strategy_family_version_id": (
                binding.strategy_family_version_id
                if binding is not None
                else campaign_metadata.get("strategy_family_version_id")
            ),
            "playbook_id": binding.playbook_id if binding is not None else campaign_metadata.get("playbook_id"),
            "playbook_pinned": bool(
                binding.playbook_id if binding is not None else campaign_metadata.get("playbook_id")
            ),
        },
        "constraints_summary": {
            "trial_constraint_snapshot_id": (
                binding.trial_constraint_snapshot_id
                if binding is not None
                else campaign_metadata.get("installed_constraint_snapshot_id")
            ),
            "installed_constraint_snapshot_id": campaign_metadata.get("installed_constraint_snapshot_id"),
            "constraints_installed": campaign_metadata.get("constraints_installed") is True,
            "status": constraint.status.value if constraint is not None else None,
            "risk_profile": constraint.risk_profile if constraint is not None else None,
        },
        "binding_summary": {
            "binding_id": binding.binding_id if binding is not None else campaign_metadata.get("admission_binding_id"),
            "binding_status": binding.binding_status.value if binding is not None else None,
            "campaign_id": campaign_id,
            "planned_result_status": "strategy_active_no_execution",
            "binding_status_after_activation": (
                binding.binding_status.value if binding is not None else None
            ),
        },
        "campaign_shell_summary": {
            "campaign_id": _campaign_id(campaign),
            "runtime_status": campaign_metadata.get("runtime_status"),
            "runtime_started": campaign_metadata.get("runtime_started") is True,
            "strategy_activation_ready": campaign_metadata.get("strategy_activation_ready") is True,
            "strategy_active": campaign_metadata.get("strategy_active") is True,
            "strategy_state": campaign_metadata.get("strategy_state"),
            "strategy_execution_enabled": campaign_metadata.get("strategy_execution_enabled") is True,
            "trial_started": campaign_metadata.get("trial_started") is True,
            "signal_loop_enabled": campaign_metadata.get("signal_loop_enabled") is True,
            "signal_loop_started": campaign_metadata.get("signal_loop_started") is True,
            "orders_placed": campaign_metadata.get("orders_placed") is True,
            "auto_execution_enabled": campaign_metadata.get("auto_execution_enabled") is True,
            "auto_within_budget_enabled": campaign_metadata.get("auto_within_budget_enabled") is True,
        },
        "strategy_activation_summary": {
            "strategy_metadata_activation_would_occur": activation_available and not idempotent_activate,
            "already_activated_idempotent": idempotent_activate,
            "runtime_status_after_activation": "strategy_active_no_execution",
            "strategy_state_after_activation": "strategy_active_no_execution",
            "strategy_activation_state_after_activation": "active_no_execution",
            "strategy_active_after_confirm": activation_available,
            "strategy_execution_enabled_after_confirm": False,
            "strategy_runner_will_start": False,
            "signal_loop_will_start": False,
            "signal_loop_will_be_enabled": False,
            "trial_started_after_confirm": False,
            "auto_execution_will_be_enabled": False,
            "auto_within_budget_will_be_enabled": False,
            "trade_intent_will_be_created": False,
            "execution_intent_will_be_created": False,
            "orders_will_be_placed": False,
            "live_ready": False,
            "next_phase_must_explicitly_enable_signal_loop_or_observe_gate": True,
        },
        "next_step": (
            "Operation confirm can activate strategy metadata in non-execution state only; a separate future Operation must enable signal loop / observe gate."
            if activation_available and not idempotent_activate
            else "Strategy metadata is already active in non-execution state; confirm is idempotent and order capability remains disabled."
            if activation_available
            else "Resolve blockers before activating strategy metadata."
        ),
    }


def _signal_loop_readiness_from_context(
    *,
    campaign_id: str,
    binding: Optional[AdmissionTrialBinding],
    blockers: list[str],
    warnings: list[str],
    decision: Optional[AdmissionDecision],
    constraint: Optional[TrialConstraintSnapshot],
    campaign: Optional[Any],
    execution_mode: Optional[AdmissionExecutionMode],
    idempotent_prepare: bool,
) -> dict[str, Any]:
    campaign_metadata = _campaign_metadata(campaign)
    unique_blockers = list(dict.fromkeys(blockers))
    unique_warnings = list(dict.fromkeys(warnings))
    preparation_available = not unique_blockers
    execution_mode_value = execution_mode.value if execution_mode is not None else None
    return {
        "available": True,
        "ready": preparation_available,
        "idempotent_prepare": idempotent_prepare,
        "phase": "BRC-R5-002 Phase 15",
        "trial_env": binding.trial_env.value if binding is not None else campaign_metadata.get("trial_env"),
        "trial_stage": binding.trial_stage.value if binding is not None else campaign_metadata.get("trial_stage"),
        "execution_mode": execution_mode_value,
        "blockers": unique_blockers,
        "warnings": unique_warnings,
        "admission_summary": {
            "admission_decision_id": (
                binding.admission_decision_id
                if binding is not None
                else campaign_metadata.get("admission_decision_id")
            ),
            "admission_request_id": decision.admission_request_id if decision is not None else None,
            "admission_result": decision.decision.value if decision is not None else None,
            "expires_at_ms": decision.expires_at_ms if decision is not None else None,
        },
        "strategy_family_summary": {
            "strategy_family_version_id": (
                binding.strategy_family_version_id
                if binding is not None
                else campaign_metadata.get("strategy_family_version_id")
            ),
            "playbook_id": binding.playbook_id if binding is not None else campaign_metadata.get("playbook_id"),
            "playbook_pinned": bool(
                binding.playbook_id if binding is not None else campaign_metadata.get("playbook_id")
            ),
        },
        "constraints_summary": {
            "trial_constraint_snapshot_id": (
                binding.trial_constraint_snapshot_id
                if binding is not None
                else campaign_metadata.get("installed_constraint_snapshot_id")
            ),
            "installed_constraint_snapshot_id": campaign_metadata.get("installed_constraint_snapshot_id"),
            "constraints_installed": campaign_metadata.get("constraints_installed") is True,
            "status": constraint.status.value if constraint is not None else None,
            "risk_profile": constraint.risk_profile if constraint is not None else None,
        },
        "binding_summary": {
            "binding_id": binding.binding_id if binding is not None else campaign_metadata.get("admission_binding_id"),
            "binding_status": binding.binding_status.value if binding is not None else None,
            "campaign_id": campaign_id,
            "planned_result_status": "signal_loop_ready_not_started",
            "binding_status_after_prepare": (
                binding.binding_status.value if binding is not None else None
            ),
        },
        "campaign_shell_summary": {
            "campaign_id": _campaign_id(campaign),
            "runtime_status": campaign_metadata.get("runtime_status"),
            "runtime_started": campaign_metadata.get("runtime_started") is True,
            "strategy_active": campaign_metadata.get("strategy_active") is True,
            "strategy_state": campaign_metadata.get("strategy_state"),
            "strategy_activation_state": campaign_metadata.get("strategy_activation_state"),
            "signal_loop_ready": campaign_metadata.get("signal_loop_ready") is True,
            "strategy_execution_enabled": campaign_metadata.get("strategy_execution_enabled") is True,
            "signal_loop_enabled": campaign_metadata.get("signal_loop_enabled") is True,
            "signal_loop_started": campaign_metadata.get("signal_loop_started") is True,
            "signal_generated": campaign_metadata.get("signal_generated") is True,
            "trial_started": campaign_metadata.get("trial_started") is True,
            "orders_placed": campaign_metadata.get("orders_placed") is True,
            "execution_intent_created": campaign_metadata.get("execution_intent_created") is True,
            "auto_execution_enabled": campaign_metadata.get("auto_execution_enabled") is True,
            "auto_within_budget_enabled": campaign_metadata.get("auto_within_budget_enabled") is True,
        },
        "signal_loop_summary": {
            "signal_loop_readiness_would_be_prepared": preparation_available and not idempotent_prepare,
            "already_prepared_idempotent": idempotent_prepare,
            "runtime_status_after_prepare": "signal_loop_ready_not_started",
            "signal_loop_ready": preparation_available,
            "signal_loop_will_start": False,
            "signal_loop_will_be_enabled": False,
            "signal_will_be_generated": False,
            "trade_intent_will_be_created": False,
            "execution_intent_will_be_created": False,
            "orders_will_be_placed": False,
            "trial_started_after_prepare": False,
            "auto_execution_will_be_enabled": False,
            "auto_within_budget_will_be_enabled": False,
            "live_ready": False,
            "next_phase_must_explicitly_start_observe_gate_or_signal_loop": True,
        },
        "next_step": (
            "Operation confirm can prepare signal loop readiness metadata only; a separate future Operation must start observe gate / signal loop."
            if preparation_available and not idempotent_prepare
            else "Signal loop readiness metadata is already prepared; confirm is idempotent and signal loop remains not started."
            if preparation_available
            else "Resolve blockers before preparing signal loop readiness metadata."
        ),
    }


def _signal_loop_start_readiness_from_context(
    *,
    campaign_id: str,
    binding: Optional[AdmissionTrialBinding],
    blockers: list[str],
    warnings: list[str],
    decision: Optional[AdmissionDecision],
    constraint: Optional[TrialConstraintSnapshot],
    campaign: Optional[Any],
    execution_mode: Optional[AdmissionExecutionMode],
    idempotent_start: bool,
) -> dict[str, Any]:
    campaign_metadata = _campaign_metadata(campaign)
    unique_blockers = list(dict.fromkeys(blockers))
    unique_warnings = list(dict.fromkeys(warnings))
    start_available = not unique_blockers
    execution_mode_value = execution_mode.value if execution_mode is not None else None
    return {
        "available": True,
        "ready": start_available,
        "idempotent_start": idempotent_start,
        "phase": "BRC-R5-002 Phase 16",
        "trial_env": binding.trial_env.value if binding is not None else campaign_metadata.get("trial_env"),
        "trial_stage": binding.trial_stage.value if binding is not None else campaign_metadata.get("trial_stage"),
        "execution_mode": execution_mode_value,
        "blockers": unique_blockers,
        "warnings": unique_warnings,
        "admission_summary": {
            "admission_decision_id": (
                binding.admission_decision_id
                if binding is not None
                else campaign_metadata.get("admission_decision_id")
            ),
            "admission_request_id": decision.admission_request_id if decision is not None else None,
            "admission_result": decision.decision.value if decision is not None else None,
            "expires_at_ms": decision.expires_at_ms if decision is not None else None,
        },
        "strategy_family_summary": {
            "strategy_family_version_id": (
                binding.strategy_family_version_id
                if binding is not None
                else campaign_metadata.get("strategy_family_version_id")
            ),
            "playbook_id": binding.playbook_id if binding is not None else campaign_metadata.get("playbook_id"),
            "playbook_pinned": bool(
                binding.playbook_id if binding is not None else campaign_metadata.get("playbook_id")
            ),
        },
        "constraints_summary": {
            "trial_constraint_snapshot_id": (
                binding.trial_constraint_snapshot_id
                if binding is not None
                else campaign_metadata.get("installed_constraint_snapshot_id")
            ),
            "installed_constraint_snapshot_id": campaign_metadata.get("installed_constraint_snapshot_id"),
            "constraints_installed": campaign_metadata.get("constraints_installed") is True,
            "status": constraint.status.value if constraint is not None else None,
            "risk_profile": constraint.risk_profile if constraint is not None else None,
        },
        "binding_summary": {
            "binding_id": binding.binding_id if binding is not None else campaign_metadata.get("admission_binding_id"),
            "binding_status": binding.binding_status.value if binding is not None else None,
            "campaign_id": campaign_id,
            "planned_result_status": "signal_loop_started_no_signal",
            "binding_status_after_start": (
                binding.binding_status.value if binding is not None else None
            ),
        },
        "campaign_shell_summary": {
            "campaign_id": _campaign_id(campaign),
            "runtime_status": campaign_metadata.get("runtime_status"),
            "runtime_started": campaign_metadata.get("runtime_started") is True,
            "strategy_active": campaign_metadata.get("strategy_active") is True,
            "strategy_state": campaign_metadata.get("strategy_state"),
            "strategy_activation_state": campaign_metadata.get("strategy_activation_state"),
            "signal_loop_ready": campaign_metadata.get("signal_loop_ready") is True,
            "signal_loop_enabled": campaign_metadata.get("signal_loop_enabled") is True,
            "signal_loop_enabled_scope": campaign_metadata.get("signal_loop_enabled_scope"),
            "signal_loop_started": campaign_metadata.get("signal_loop_started") is True,
            "signal_generated": campaign_metadata.get("signal_generated") is True,
            "trial_started": campaign_metadata.get("trial_started") is True,
            "trade_intent_created": campaign_metadata.get("trade_intent_created") is True,
            "execution_intent_created": campaign_metadata.get("execution_intent_created") is True,
            "order_created": campaign_metadata.get("order_created") is True,
            "orders_placed": campaign_metadata.get("orders_placed") is True,
            "auto_execution_enabled": campaign_metadata.get("auto_execution_enabled") is True,
            "auto_within_budget_enabled": campaign_metadata.get("auto_within_budget_enabled") is True,
        },
        "signal_loop_summary": {
            "signal_loop_state_would_start": start_available and not idempotent_start,
            "already_started_idempotent": idempotent_start,
            "runtime_status_after_start": "signal_loop_started_no_signal",
            "signal_loop_ready_after_confirm": start_available,
            "signal_loop_enabled_after_confirm": start_available,
            "signal_loop_enabled_scope": "non_trading_loop_state",
            "signal_loop_started_after_confirm": start_available,
            "signal_will_be_generated": False,
            "trade_intent_will_be_created": False,
            "execution_intent_will_be_created": False,
            "orders_will_be_placed": False,
            "trial_started_after_confirm": False,
            "auto_execution_will_be_enabled": False,
            "auto_within_budget_will_be_enabled": False,
            "live_ready": False,
            "next_phase_must_explicitly_generate_or_evaluate_signals": True,
        },
        "next_step": (
            "Operation confirm can start signal loop state metadata only; a separate future Operation must generate or evaluate signals."
            if start_available and not idempotent_start
            else "Signal loop state metadata is already started without signal generation; confirm is idempotent and order capability remains disabled."
            if start_available
            else "Resolve blockers before starting signal loop state metadata."
        ),
    }


def _signal_evaluation_readiness_from_context(
    *,
    campaign_id: str,
    binding: Optional[AdmissionTrialBinding],
    blockers: list[str],
    warnings: list[str],
    decision: Optional[AdmissionDecision],
    constraint: Optional[TrialConstraintSnapshot],
    campaign: Optional[Any],
    execution_mode: Optional[AdmissionExecutionMode],
    idempotent_evaluation: bool,
    signal_snapshot: Any = None,
    signal_evaluation_input: Any = None,
) -> dict[str, Any]:
    campaign_metadata = _campaign_metadata(campaign)
    unique_blockers = list(dict.fromkeys(blockers))
    unique_warnings = list(dict.fromkeys(warnings))
    evaluation_available = not unique_blockers
    execution_mode_value = execution_mode.value if execution_mode is not None else None
    return {
        "available": True,
        "ready": evaluation_available,
        "idempotent_evaluation": idempotent_evaluation,
        "phase": "BRC-R5-002 Phase 17",
        "trial_env": binding.trial_env.value if binding is not None else campaign_metadata.get("trial_env"),
        "trial_stage": binding.trial_stage.value if binding is not None else campaign_metadata.get("trial_stage"),
        "execution_mode": execution_mode_value,
        "blockers": unique_blockers,
        "warnings": unique_warnings,
        "admission_summary": {
            "admission_decision_id": (
                binding.admission_decision_id
                if binding is not None
                else campaign_metadata.get("admission_decision_id")
            ),
            "admission_request_id": decision.admission_request_id if decision is not None else None,
            "admission_result": decision.decision.value if decision is not None else None,
            "expires_at_ms": decision.expires_at_ms if decision is not None else None,
        },
        "strategy_family_summary": {
            "strategy_family_version_id": (
                binding.strategy_family_version_id
                if binding is not None
                else campaign_metadata.get("strategy_family_version_id")
            ),
            "playbook_id": binding.playbook_id if binding is not None else campaign_metadata.get("playbook_id"),
            "playbook_pinned": bool(
                binding.playbook_id if binding is not None else campaign_metadata.get("playbook_id")
            ),
        },
        "constraints_summary": {
            "trial_constraint_snapshot_id": (
                binding.trial_constraint_snapshot_id
                if binding is not None
                else campaign_metadata.get("installed_constraint_snapshot_id")
            ),
            "installed_constraint_snapshot_id": campaign_metadata.get("installed_constraint_snapshot_id"),
            "constraints_installed": campaign_metadata.get("constraints_installed") is True,
            "status": constraint.status.value if constraint is not None else None,
            "risk_profile": constraint.risk_profile if constraint is not None else None,
        },
        "binding_summary": {
            "binding_id": binding.binding_id if binding is not None else campaign_metadata.get("admission_binding_id"),
            "binding_status": binding.binding_status.value if binding is not None else None,
            "campaign_id": campaign_id,
            "planned_result_status": "signal_evaluated_no_intent",
            "binding_status_after_evaluation": (
                binding.binding_status.value if binding is not None else None
            ),
        },
        "campaign_shell_summary": {
            "campaign_id": _campaign_id(campaign),
            "runtime_status": campaign_metadata.get("runtime_status"),
            "runtime_started": campaign_metadata.get("runtime_started") is True,
            "strategy_active": campaign_metadata.get("strategy_active") is True,
            "strategy_state": campaign_metadata.get("strategy_state"),
            "strategy_activation_state": campaign_metadata.get("strategy_activation_state"),
            "signal_loop_ready": campaign_metadata.get("signal_loop_ready") is True,
            "signal_loop_enabled": campaign_metadata.get("signal_loop_enabled") is True,
            "signal_loop_enabled_scope": campaign_metadata.get("signal_loop_enabled_scope"),
            "signal_loop_started": campaign_metadata.get("signal_loop_started") is True,
            "signal_evaluated": campaign_metadata.get("signal_evaluated") is True,
            "signal_generated": campaign_metadata.get("signal_generated") is True,
            "trial_started": campaign_metadata.get("trial_started") is True,
            "trade_intent_created": campaign_metadata.get("trade_intent_created") is True,
            "execution_intent_created": campaign_metadata.get("execution_intent_created") is True,
            "order_created": campaign_metadata.get("order_created") is True,
            "orders_placed": campaign_metadata.get("orders_placed") is True,
            "auto_execution_enabled": campaign_metadata.get("auto_execution_enabled") is True,
            "auto_within_budget_enabled": campaign_metadata.get("auto_within_budget_enabled") is True,
        },
        "signal_evaluation_summary": {
            "signal_evaluation_would_be_recorded": evaluation_available and not idempotent_evaluation,
            "already_evaluated_idempotent": idempotent_evaluation,
            "runtime_status_after_evaluation": "signal_evaluated_no_intent",
            "signal_evaluated_after_confirm": evaluation_available,
            "signal_generated_after_confirm": evaluation_available,
            "signal_is_trade_intent": False,
            "signal_snapshot_present": bool(signal_snapshot or {}),
            "signal_evaluation_input_present": bool(signal_evaluation_input or {}),
            "trade_intent_will_be_created": False,
            "execution_intent_will_be_created": False,
            "orders_will_be_placed": False,
            "trial_started_after_confirm": False,
            "auto_execution_will_be_enabled": False,
            "auto_within_budget_will_be_enabled": False,
            "live_ready": False,
            "next_phase_must_explicitly_convert_signal_to_trial_trade_intent": True,
        },
        "next_step": (
            "Operation confirm can record signal evaluation metadata only; a separate future Operation must convert signal to trial trade intent."
            if evaluation_available and not idempotent_evaluation
            else "Signal evaluation metadata is already recorded without intent; confirm is idempotent and order capability remains disabled."
            if evaluation_available
            else "Resolve blockers before recording signal evaluation metadata."
        ),
    }
