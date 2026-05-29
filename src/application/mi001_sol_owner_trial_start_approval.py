"""Metadata-only Owner trial-start approval for MI-001 SOL readiness.

This approval record is an admission/owner-review fact only. It does not start
runtime, grant execution permission, create execution intents, or create orders.
"""

from __future__ import annotations

from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.domain.brc_admission import OwnerRiskAcceptance, TrialEnv, TrialStage
from src.domain.mi001_sol_pg_registration import (
    MI001_CANDIDATE_ID,
    MI001_OWNER_TRIAL_START_APPROVAL_ID,
)


class Mi001SolOwnerTrialStartApprovalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval: OwnerRiskAcceptance
    status: str = Field(pattern="^(created|already_exists)$")


class Mi001SolOwnerTrialStartApprovalRepositoryPort(Protocol):
    async def get_owner_risk_acceptance(
        self,
        owner_risk_acceptance_id: str,
    ) -> Optional[OwnerRiskAcceptance]: ...

    async def create_owner_risk_acceptance(
        self,
        acceptance: OwnerRiskAcceptance,
    ) -> OwnerRiskAcceptance: ...


class Mi001SolOwnerTrialStartApprovalService:
    """Record idempotent metadata-only Owner trial-start approval."""

    def __init__(
        self,
        *,
        admission_repository: Mi001SolOwnerTrialStartApprovalRepositoryPort,
    ) -> None:
        self._admission_repository = admission_repository

    async def record_metadata_only_approval(
        self,
        *,
        now_ms: int,
        account_facts_snapshot_ref: str,
    ) -> Mi001SolOwnerTrialStartApprovalResult:
        existing = await self._admission_repository.get_owner_risk_acceptance(
            MI001_OWNER_TRIAL_START_APPROVAL_ID
        )
        if existing is not None:
            return Mi001SolOwnerTrialStartApprovalResult(
                approval=existing,
                status="already_exists",
            )

        approval = OwnerRiskAcceptance(
            owner_risk_acceptance_id=MI001_OWNER_TRIAL_START_APPROVAL_ID,
            admission_request_id=f"{MI001_CANDIDATE_ID}-admission-request-v1",
            admission_decision_id=f"{MI001_CANDIDATE_ID}-admission-decision-v1",
            strategy_family_version_id=f"{MI001_CANDIDATE_ID}-admission-v1",
            trial_env=TrialEnv.LIVE,
            trial_stage=TrialStage.FUNDED_VALIDATION,
            account_facts_snapshot_ref=account_facts_snapshot_ref,
            risk_profile="dedicated_subaccount_micro",
            risk_policy_snapshot_json={
                "approval_scope": "trial_start_metadata_only",
                "capital_source": "dedicated_subaccount",
                "trial_risk_capital_rule": "current_dedicated_subaccount_equity",
                "max_total_loss_rule": "current_dedicated_subaccount_equity",
                "max_leverage": 5,
                "max_notional_rule": (
                    "min(current_dedicated_subaccount_equity * 5, "
                    "available_margin * 5 if available, "
                    "operation_layer_notional_cap_if_exists)"
                ),
            },
            constraint_snapshot_id=f"{MI001_CANDIDATE_ID}-trial-constraints-v1",
            risk_disclosure_snapshot_json={
                "owner_approved_trial_start": True,
                "approval_scope": "trial_start_metadata_only",
                "automatic_execution_approved": False,
                "execution_permission_granted": False,
                "order_permission_granted": False,
                "runtime_start_granted": False,
                "exchange_write_permission_granted": False,
                "leverage_change_permission_granted": False,
                "transfer_permission_granted": False,
                "withdrawal_permission_granted": False,
                "does_not_override_gks": True,
                "does_not_override_startup_guard": True,
                "does_not_bypass_operation_layer": True,
            },
            known_gaps_snapshot_json={
                "operation_layer_facts_required": True,
                "gks_must_allow_new_entries_before_trial_start": True,
                "startup_guard_must_be_ready_before_trial_start": True,
                "no_active_position_or_orders_must_be_verified": True,
            },
            owner_rationale=(
                "Owner approved trial-start readiness metadata for MI-001 SOL long. "
                "This is not runtime start or execution permission."
            ),
            confirmation_phrase="I APPROVE MI-001 SOL TRIAL START METADATA ONLY",
            confirmation_marker="owner_confirmed_trial_start_metadata_only",
            confirmed_at_ms=now_ms,
            created_at_ms=now_ms,
            created_by="owner",
        )
        created = await self._admission_repository.create_owner_risk_acceptance(approval)
        return Mi001SolOwnerTrialStartApprovalResult(
            approval=created,
            status="created",
        )
