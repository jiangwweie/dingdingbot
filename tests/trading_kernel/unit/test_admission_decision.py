from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.admission_decision import (
    AdmissionDecision,
    AdmissionDecisionStatus,
    AdmissionPortfolioUsage,
    freeze_admission_decision,
)
from src.trading_kernel.domain.arbitration import EntryCandidate, freeze_candidate_set
from tests.trading_kernel.unit.test_signal import _signal


def test_rejected_decision_forbids_ticket_identity() -> None:
    decision = _rejected_decision()

    with pytest.raises(ValidationError, match="rejected"):
        AdmissionDecision.model_validate(
            {
                **decision.model_dump(mode="python"),
                "ticket_id": "ticket:x",
            }
        )


def test_admission_decision_digest_binds_policy_usage_and_candidate_set() -> None:
    decision = _rejected_decision()
    changed_policy = _rejected_decision(owner_policy_version=4)
    changed_usage = _rejected_decision(
        usage=_usage().model_copy(
            update={"gross_risk_at_stop": Decimal(7)}
        )
    )
    changed_candidates = _rejected_decision(
        include_second_candidate=True
    )

    assert len(
        {
            decision.decision_digest,
            changed_policy.decision_digest,
            changed_usage.decision_digest,
            changed_candidates.decision_digest,
        }
    ) == 4


def test_admitted_decision_requires_claim_ticket_and_snapshot_digest() -> None:
    signal = _signal()
    candidate_set = freeze_candidate_set(
        (EntryCandidate(signal=signal, owner_policy_priority=1),)
    )

    with pytest.raises(ValueError, match="admitted"):
        freeze_admission_decision(
            signal=signal,
            candidate_set=candidate_set,
            exposure_family="opening_range",
            runtime_profile_id="tiny-live-v1",
            owner_policy_id="policy-live-v3",
            owner_policy_version=3,
            venue_id="binance-usdm",
            account_id="acct-live",
            portfolio_usage=_usage(),
            decision_status=AdmissionDecisionStatus.ADMITTED,
            first_blocker=None,
            binding_constraint=None,
            capacity_claim_id=None,
            ticket_id=None,
            entry_admission_snapshot_digest=None,
            decided_at_ms=1_100,
        )


def _rejected_decision(
    *,
    owner_policy_version: int = 3,
    usage: AdmissionPortfolioUsage | None = None,
    include_second_candidate: bool = False,
) -> AdmissionDecision:
    signal = _signal()
    candidates = [EntryCandidate(signal=signal, owner_policy_priority=1)]
    if include_second_candidate:
        candidates.append(
            EntryCandidate(
                signal=_signal(
                    signal_event_id="signal-2",
                    exposure_episode_id="episode:" + "c" * 64,
                    occurred_at_ms=1_001,
                    observed_at_ms=1_002,
                    expires_at_ms=2_000,
                ),
                owner_policy_priority=2,
            )
        )
    return freeze_admission_decision(
        signal=signal,
        candidate_set=freeze_candidate_set(tuple(candidates)),
        exposure_family="opening_range",
        runtime_profile_id="tiny-live-v1",
        owner_policy_id="policy-live-v3",
        owner_policy_version=owner_policy_version,
        venue_id="binance-usdm",
        account_id="acct-live",
        portfolio_usage=usage or _usage(),
        decision_status=AdmissionDecisionStatus.REJECTED,
        first_blocker="budget_exhausted",
        binding_constraint="gross_stop_risk",
        capacity_claim_id=None,
        ticket_id=None,
        entry_admission_snapshot_digest="sha256:" + "d" * 64,
        decided_at_ms=1_100,
    )


def _usage() -> AdmissionPortfolioUsage:
    return AdmissionPortfolioUsage(
        active_ticket_count=1,
        active_family_ticket_count=1,
        gross_risk_at_stop=Decimal(6),
        directional_risk_at_stop=Decimal(6),
        current_reserved_margin=Decimal(20),
        remaining_ticket_slots=2,
        remaining_family_slots=1,
        remaining_gross_stop_risk=Decimal(12),
        remaining_directional_stop_risk=Decimal(6),
        remaining_initial_margin=Decimal(80),
    )
