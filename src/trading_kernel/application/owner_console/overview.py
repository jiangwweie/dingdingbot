"""Pure deterministic assembly for the Owner Console overview."""

from __future__ import annotations

from typing import Literal

from src.trading_kernel.application.owner_console.models import (
    AdmissionAccountSnapshot,
    EvidenceRef,
    Freshness,
    MoneyMetric,
    OverviewFacts,
    OwnerConclusion,
    OwnerOverview,
)


def build_owner_overview(facts: OverviewFacts, now_ms: int) -> OwnerOverview:
    """Classify one immutable PostgreSQL fact snapshot without external I/O."""

    account_snapshot = _account_snapshot(facts)
    conclusion = _conclusion(facts)
    capacity = (
        None
        if facts.max_concurrent_tickets is None
        or facts.active_ticket_count is None
        else facts.max_concurrent_tickets - facts.active_ticket_count
    )
    claim_evidence = (
        ()
        if facts.latest_capacity_claim_id is None
        or facts.latest_claim_created_at_ms is None
        else (
            EvidenceRef(
                kind="admission",
                identity=facts.latest_capacity_claim_id,
                occurred_at_ms=facts.latest_claim_created_at_ms,
            ),
        )
    )
    attention_summary = (
        *facts.contradictory_fact_reasons,
        *facts.evidence_gap_reasons,
        *(f"open_incident:{identity}" for identity in facts.attention_incident_ids),
    )

    return OwnerOverview(
        observed_at_ms=now_ms,
        conclusion=conclusion,
        account_snapshot=account_snapshot,
        ticket_capacity=capacity,
        active_ticket_count=facts.active_ticket_count,
        active_ticket_ids=facts.active_ticket_ids,
        today_net_pnl=facts.today_net_pnl,
        today_net_r=facts.today_net_r,
        today_signal_count=facts.today_signal_count,
        admitted_signal_count=facts.admitted_signal_count,
        rejected_signal_count=facts.rejected_signal_count,
        execution_incident_count=facts.execution_incident_count,
        attention_summary=tuple(attention_summary),
        evidence=_unique_evidence(
            (*conclusion.evidence, *claim_evidence, *facts.evidence)
        ),
    )


def _account_snapshot(facts: OverviewFacts) -> AdmissionAccountSnapshot:
    no_claim = facts.latest_capacity_claim_id is None
    unavailable_reason = (
        "no_capacity_claim" if no_claim else "capacity_claim_metric_missing"
    )
    return AdmissionAccountSnapshot(
        label="Latest Admission Snapshot",
        is_realtime=False,
        captured_at_ms=facts.latest_claim_created_at_ms,
        wallet_balance=MoneyMetric(
            value=facts.latest_wallet_balance_at_claim,
            unit="USDT",
            unavailable_reason=(
                unavailable_reason
                if facts.latest_wallet_balance_at_claim is None
                else None
            ),
        ),
        available_margin=MoneyMetric(
            value=facts.latest_available_margin_at_claim,
            unit="USDT",
            unavailable_reason=(
                unavailable_reason
                if facts.latest_available_margin_at_claim is None
                else None
            ),
        ),
    )


def _conclusion(facts: OverviewFacts) -> OwnerConclusion:
    if facts.open_owner_incident_id is not None:
        return _owner_conclusion(
            level="intervention",
            summary="An open safety Incident requires Owner intervention.",
            owner_action="Review the open Incident and its official recovery path.",
            evidence=EvidenceRef(
                kind="incident",
                identity=facts.open_owner_incident_id,
                occurred_at_ms=(
                    facts.open_owner_incident_opened_at_ms
                    or facts.observed_at_ms
                ),
            ),
        )

    if (
        facts.contradictory_fact_reasons
        or facts.runtime_freshness is Freshness.CONTRADICTORY
    ):
        return _owner_conclusion(
            level="intervention",
            summary="Required PostgreSQL facts are contradictory.",
            owner_action="Review the contradictory fact identities before relying on the overview.",
            evidence=_fact_evidence(
                facts.contradictory_evidence_identity
                or facts.freshness_evidence_identity,
                facts.freshness_evidence_at_ms,
            ),
        )

    for index, status in enumerate(facts.monitor_statuses):
        if status != "needs_intervention":
            continue
        identity = (
            facts.monitor_keys[index]
            if index < len(facts.monitor_keys)
            else f"monitor:{index}"
        )
        occurred_at_ms = (
            facts.monitor_updated_at_ms[index]
            if index < len(facts.monitor_updated_at_ms)
            else facts.observed_at_ms
        )
        return _owner_conclusion(
            level="intervention",
            summary="A current Monitor requires Owner intervention.",
            owner_action="Follow the intervention recorded by the Monitor.",
            evidence=_fact_evidence(identity, occurred_at_ms),
        )

    if facts.runtime_freshness is Freshness.STALE:
        return _owner_conclusion(
            level="attention",
            summary="A required current projection is stale.",
            owner_action=None,
            evidence=_fact_evidence(
                facts.freshness_evidence_identity,
                facts.freshness_evidence_at_ms,
            ),
        )

    if facts.attention_incident_ids:
        return _owner_conclusion(
            level="attention",
            summary="An open non-blocking Incident is available for review.",
            owner_action=None,
            evidence=EvidenceRef(
                kind="incident",
                identity=facts.attention_incident_ids[0],
                occurred_at_ms=(
                    facts.attention_incident_opened_at_ms[0]
                    if facts.attention_incident_opened_at_ms
                    else facts.observed_at_ms
                ),
            ),
        )

    if (
        facts.evidence_gap_reasons
        or facts.runtime_freshness is Freshness.UNAVAILABLE
    ):
        return _owner_conclusion(
            level="attention",
            summary="Required overview evidence is unavailable.",
            owner_action=None,
            evidence=_fact_evidence(
                facts.evidence_gap_identity
                or facts.freshness_evidence_identity,
                facts.freshness_evidence_at_ms,
            ),
        )

    return _owner_conclusion(
        level="no_action",
        summary="Current runtime facts require no Owner action.",
        owner_action=None,
        evidence=_fact_evidence(
            facts.freshness_evidence_identity,
            facts.freshness_evidence_at_ms,
        ),
    )


def _owner_conclusion(
    *,
    level: Literal["intervention", "attention", "no_action"],
    summary: str,
    owner_action: str | None,
    evidence: EvidenceRef,
) -> OwnerConclusion:
    return OwnerConclusion(
        level=level,
        summary=summary,
        owner_action=owner_action,
        evidence=(evidence,),
    )


def _fact_evidence(identity: str, occurred_at_ms: int) -> EvidenceRef:
    kind: Literal["review", "event"] = (
        "review" if identity.startswith("review:") else "event"
    )
    return EvidenceRef(
        kind=kind,
        identity=identity,
        occurred_at_ms=occurred_at_ms,
    )


def _unique_evidence(evidence: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    seen: set[tuple[str, str, int]] = set()
    unique: list[EvidenceRef] = []
    for item in evidence:
        key = (item.kind, item.identity, item.occurred_at_ms)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return tuple(unique)
