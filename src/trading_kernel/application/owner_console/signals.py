"""Pure assembly for bounded Signal list and exact admission detail."""

from __future__ import annotations

from src.trading_kernel.application.owner_console.models import (
    EvidenceRef,
    PageCursor,
    ShadowOutcomeSummary,
    SignalAdmissionDetail,
    SignalDetailFacts,
    SignalItemFacts,
    SignalListItem,
    SignalListPage,
    SignalPageFacts,
    encode_cursor,
)


class SignalNotFound(LookupError):
    """The exact persisted Signal identity does not exist."""


class SignalFactsContradiction(ValueError):
    """Persisted Signal, Decision, fact, or Shadow identities disagree."""


def build_signal_item(facts: SignalItemFacts) -> SignalListItem:
    """Build one item from immutable persisted Signal admission facts."""

    shadow = _shadow_summary(facts)
    if facts.decision_status == "admitted":
        if (
            facts.admission_decision_id is None
            or facts.decided_at_ms is None
            or facts.first_blocker is not None
            or facts.ticket_id is None
        ):
            raise SignalFactsContradiction("admitted signal decision shape mismatch")
        if shadow is not None and shadow.source_kind != "strategy_observation":
            raise SignalFactsContradiction(
                "admitted signal can own only a strategy Observation"
            )
    elif facts.decision_status == "rejected":
        if (
            facts.admission_decision_id is None
            or facts.decided_at_ms is None
            or facts.first_blocker is None
            or facts.ticket_id is not None
        ):
            raise SignalFactsContradiction("rejected signal decision shape mismatch")
    elif (
        facts.admission_decision_id is not None
        or facts.decided_at_ms is not None
        or facts.first_blocker is not None
        or facts.binding_constraint is not None
        or facts.ticket_id is not None
        or (shadow is not None and shadow.source_kind != "strategy_observation")
    ):
        raise SignalFactsContradiction("not-evaluated signal shape mismatch")

    evidence = [
        EvidenceRef(
            kind="signal",
            identity=facts.signal_event_id,
            occurred_at_ms=facts.occurred_at_ms,
        ),
    ]
    if facts.admission_decision_id is not None and facts.decided_at_ms is not None:
        evidence.append(
            EvidenceRef(
                kind="admission",
                identity=facts.admission_decision_id,
                occurred_at_ms=facts.decided_at_ms,
            )
        )
    if shadow is not None:
        evidence.extend(shadow.evidence)

    return SignalListItem(
        signal_event_id=facts.signal_event_id,
        exposure_episode_id=facts.exposure_episode_id,
        strategy_group_id=facts.strategy_group_id,
        strategy_version_id=facts.strategy_version_id,
        event_spec_id=facts.event_spec_id,
        exchange_instrument_id=facts.exchange_instrument_id,
        position_side=facts.position_side,
        occurred_at_ms=facts.occurred_at_ms,
        expires_at_ms=facts.expires_at_ms,
        admission_decision_id=facts.admission_decision_id,
        decision_status=facts.decision_status,
        first_blocker=facts.first_blocker,
        binding_constraint=facts.binding_constraint,
        ticket_id=facts.ticket_id,
        shadow_summary=shadow,
        evidence=tuple(evidence),
    )


def build_signal_page(facts: SignalPageFacts) -> SignalListPage:
    """Trim the limit+1 row and encode the exact last-returned keyset."""

    ordered_keys = [
        (item.occurred_at_ms, item.signal_event_id) for item in facts.items
    ]
    if ordered_keys != sorted(ordered_keys, reverse=True):
        raise SignalFactsContradiction("signal page ordering mismatch")
    if len(ordered_keys) != len(set(ordered_keys)):
        raise SignalFactsContradiction("signal page contains duplicate identity")

    has_more = len(facts.items) > facts.requested_limit
    returned_facts = facts.items[: facts.requested_limit]
    items = tuple(build_signal_item(item) for item in returned_facts)
    next_cursor = None
    if has_more:
        boundary = returned_facts[-1]
        next_cursor = encode_cursor(
            PageCursor(
                sort_ms=boundary.occurred_at_ms,
                identity=boundary.signal_event_id,
            )
        )
    return SignalListPage(items=items, next_cursor=next_cursor)


def build_signal_detail(facts: SignalDetailFacts) -> SignalAdmissionDetail:
    """Assemble exact admission causality without inferring current authority."""

    signal_event_id = facts.signal.signal_event_id
    fact_ids: list[str] = []
    for snapshot in facts.fact_snapshots:
        if snapshot.signal_event_id != signal_event_id:
            raise SignalFactsContradiction(
                "fact snapshot signal identity mismatch"
            )
        fact_ids.append(snapshot.fact_definition_id)
    if fact_ids != sorted(fact_ids):
        raise SignalFactsContradiction("fact snapshots are not exactly ordered")
    if len(fact_ids) != len(set(fact_ids)):
        raise SignalFactsContradiction("fact snapshots contain duplicate identity")

    signal = build_signal_item(facts.signal)
    if signal.decision_status == "admitted":
        what_happened = (
            "The persisted AdmissionDecision admitted this Signal and linked "
            "its exact Ticket."
        )
        why_no_ticket = None
    elif signal.decision_status == "rejected":
        what_happened = (
            "The persisted AdmissionDecision rejected this Signal; no Ticket "
            "was created."
        )
        why_no_ticket = signal.first_blocker
    else:
        what_happened = (
            "This Signal was retained for Observation while production Entry "
            "admission was not evaluated."
        )
        why_no_ticket = "observation_only"

    fact_evidence = tuple(
        EvidenceRef(
            kind="fact",
            identity=(
                f"signal-fact:{signal_event_id}:{snapshot.fact_definition_id}"
            ),
            occurred_at_ms=snapshot.observed_at_ms,
        )
        for snapshot in facts.fact_snapshots
    )
    return SignalAdmissionDetail(
        signal=signal,
        what_happened=what_happened,
        why_no_ticket=why_no_ticket,
        fact_snapshots=facts.fact_snapshots,
        shadow_summary=signal.shadow_summary,
        evidence=(*signal.evidence, *fact_evidence),
    )


def _shadow_summary(facts: SignalItemFacts) -> ShadowOutcomeSummary | None:
    shadow_values = (
        facts.shadow_source_kind,
        facts.shadow_evaluation_kind,
        facts.shadow_status,
        facts.shadow_mfe_r,
        facts.shadow_mae_r,
        facts.shadow_completion_reason,
        facts.shadow_observed_through_ms,
        facts.shadow_completed_at_ms,
        facts.shadow_first_path,
        facts.shadow_first_path_at_ms,
        facts.shadow_observed_bar_count,
        facts.shadow_spread_bps,
        facts.shadow_mark_index_deviation_bps,
    )
    if facts.shadow_outcome_id is None:
        if any(value is not None for value in shadow_values):
            raise SignalFactsContradiction("Shadow Outcome identity is missing")
        return None
    if facts.shadow_status is None:
        raise SignalFactsContradiction("Shadow Outcome status is missing")
    if facts.shadow_source_kind is None or facts.shadow_evaluation_kind is None:
        raise SignalFactsContradiction("Shadow Outcome semantics are missing")
    pending_or_claimed_shape = (
        facts.shadow_completed_at_ms is None
        and facts.shadow_completion_reason is None
        and facts.shadow_observed_through_ms is None
        and facts.shadow_mfe_r is None
        and facts.shadow_mae_r is None
    )
    completed_shape = (
        facts.shadow_completed_at_ms is not None
        and facts.shadow_completion_reason is not None
        and facts.shadow_observed_through_ms is not None
        and facts.shadow_mfe_r is not None
        and facts.shadow_mae_r is not None
    )
    unavailable_shape = (
        facts.shadow_completed_at_ms is not None
        and facts.shadow_completion_reason is not None
        and facts.shadow_observed_through_ms is None
        and facts.shadow_mfe_r is None
        and facts.shadow_mae_r is None
    )
    valid_shape = (
        facts.shadow_status in {"pending", "claimed"}
        and pending_or_claimed_shape
    ) or (
        facts.shadow_status == "completed" and completed_shape
    ) or (
        facts.shadow_status == "unavailable" and unavailable_shape
    )
    if not valid_shape:
        raise SignalFactsContradiction(
            "Shadow Outcome status shape mismatch"
        )
    if facts.shadow_evaluation_kind == "fixed_horizon_excursion_v1":
        if facts.shadow_source_kind != "portfolio_rejection" or any(
            value is not None
            for value in (
                facts.shadow_first_path,
                facts.shadow_first_path_at_ms,
                facts.shadow_observed_bar_count,
            )
        ):
            raise SignalFactsContradiction("fixed-horizon Shadow semantics mismatch")
    elif facts.shadow_source_kind != "strategy_observation":
        raise SignalFactsContradiction("SOR Observation semantics mismatch")
    elif facts.shadow_status == "completed" and (
        facts.shadow_first_path is None
        or facts.shadow_first_path_at_ms is None
        or facts.shadow_observed_bar_count is None
    ):
        raise SignalFactsContradiction("completed SOR Observation path is missing")

    shadow_evidence = EvidenceRef(
        kind="shadow",
        identity=facts.shadow_outcome_id,
        occurred_at_ms=(
            facts.shadow_completed_at_ms
            or facts.decided_at_ms
            or facts.occurred_at_ms
        ),
    )
    return ShadowOutcomeSummary(
        shadow_outcome_id=facts.shadow_outcome_id,
        source_kind=facts.shadow_source_kind,
        evaluation_kind=facts.shadow_evaluation_kind,
        status=facts.shadow_status,
        mfe_r=facts.shadow_mfe_r,
        mae_r=facts.shadow_mae_r,
        first_path=facts.shadow_first_path,
        first_path_at_ms=facts.shadow_first_path_at_ms,
        observed_bar_count=facts.shadow_observed_bar_count,
        spread_bps=facts.shadow_spread_bps,
        mark_index_deviation_bps=facts.shadow_mark_index_deviation_bps,
        completion_reason=facts.shadow_completion_reason,
        observed_through_ms=facts.shadow_observed_through_ms,
        completed_at_ms=facts.shadow_completed_at_ms,
        evidence=(shadow_evidence,),
    )
