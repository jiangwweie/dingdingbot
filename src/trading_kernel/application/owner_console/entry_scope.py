"""Pure projection of current effective Entry scope; never grants admission."""

from __future__ import annotations

from collections.abc import Iterable

from src.trading_kernel.application.owner_console.models import (
    EffectiveEntryScope,
    EffectiveEntryScopeFacts,
    EffectiveEntryScopeItem,
    EntryScopeFacts,
    EvidenceRef,
)


def build_effective_entry_scope(
    facts: EffectiveEntryScopeFacts,
    *,
    now_ms: int,
) -> EffectiveEntryScope:
    """Explain current scope eligibility from PostgreSQL projections only.

    ``can_issue_ticket_now`` means a scope has no *current scope-level* blocker.
    Signal validity, live account facts, Netting Domain occupancy and final
    admission remain action-time checks in the normal Entry chain.
    """

    items = tuple(
        _build_item(scope, facts=facts, now_ms=now_ms)
        for scope in sorted(
            facts.scopes,
            key=lambda item: (
                item.strategy_group_id,
                item.exchange_instrument_id,
                item.position_side,
                item.runtime_scope_id,
            ),
        )
    )
    eligible = tuple(item for item in items if item.can_issue_ticket_now)
    blocker = None if eligible else (items[0].first_blocker if items else "scope_missing")
    evidence = _unique_evidence(
        reference
        for item in items
        for reference in item.evidence
    )
    return EffectiveEntryScope(
        owner_policy_id=facts.owner_policy_id,
        policy_version=facts.policy_version,
        can_issue_ticket_now=bool(eligible),
        first_blocker=blocker,
        remaining_ticket_slots=max(
            facts.max_concurrent_tickets - facts.active_ticket_count,
            0,
        ),
        eligible_scope_count=len(eligible),
        scopes=items,
        evidence=evidence,
    )


def _build_item(
    scope: EntryScopeFacts,
    *,
    facts: EffectiveEntryScopeFacts,
    now_ms: int,
) -> EffectiveEntryScopeItem:
    blocker = _first_blocker(scope, facts=facts, now_ms=now_ms)
    evidence = [
        EvidenceRef(
            kind="fact",
            identity=f"runtime_scope:{scope.runtime_scope_id}",
            occurred_at_ms=scope.scope_updated_at_ms,
        )
    ]
    if scope.readiness_updated_at_ms is not None:
        evidence.append(
            EvidenceRef(
                kind="fact",
                identity=f"readiness:{scope.runtime_scope_id}",
                occurred_at_ms=scope.readiness_updated_at_ms,
            )
        )
    if scope.product_observed_at_ms is not None:
        evidence.append(
            EvidenceRef(
                kind="fact",
                identity=f"product:{scope.exchange_instrument_id}",
                occurred_at_ms=scope.product_observed_at_ms,
            )
        )
    return EffectiveEntryScopeItem(
        runtime_scope_id=scope.runtime_scope_id,
        strategy_group_id=scope.strategy_group_id,
        strategy_version_id=scope.strategy_version_id,
        event_spec_id=scope.event_spec_id,
        timeframe=scope.timeframe,
        exchange_instrument_id=scope.exchange_instrument_id,
        position_side=scope.position_side,
        readiness_state=scope.readiness_state,
        can_issue_ticket_now=blocker is None,
        first_blocker=blocker,
        evidence=tuple(evidence),
    )


def _first_blocker(
    scope: EntryScopeFacts,
    *,
    facts: EffectiveEntryScopeFacts,
    now_ms: int,
) -> str | None:
    if not facts.policy_enabled:
        return "owner_policy_disabled"
    if not facts.new_entry_submit_enabled:
        return "global_entry_paused"
    if not facts.runtime_capability_enabled:
        return "runtime_fenced"
    if scope.runtime_profile_status != "active":
        return "runtime_profile_unavailable"
    if scope.strategy_entry_state is None:
        return "strategy_control_missing"
    if scope.strategy_entry_state != "enabled":
        return f"strategy_paused:{scope.strategy_group_id}"
    if scope.lifecycle_state != "active" or not scope.entry_enabled:
        return "scope_not_entry_enabled"
    if scope.product_profile_status != "active":
        return "product_profile_not_entry_capable"
    if scope.product_status != "active":
        return "product_unavailable"
    if scope.product_valid_until_ms is None or scope.product_valid_until_ms <= now_ms:
        return "product_snapshot_stale"
    if scope.entry_session_policy == "regular_only" and scope.session_state != "regular":
        return "session_not_regular"
    if scope.entry_session_policy != "continuous" and scope.entry_session_policy != "regular_only":
        return "product_profile_not_entry_capable"
    if scope.readiness_state != "candidate_ready":
        return scope.readiness_first_blocker or "signal_absent"
    return None


def _unique_evidence(
    evidence: Iterable[EvidenceRef],
) -> tuple[EvidenceRef, ...]:
    unique: dict[tuple[str, str, int], EvidenceRef] = {}
    for item in evidence:
        unique[(item.kind, item.identity, item.occurred_at_ms)] = item
    return tuple(unique.values())
