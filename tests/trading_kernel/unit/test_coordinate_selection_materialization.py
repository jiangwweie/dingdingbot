from __future__ import annotations

from src.trading_kernel.application.coordinate_selection_materialization import (
    AuthorityGapAuditWindowDisposition,
    MaterializationDisposition,
    MaterializationPlanningFacts,
    plan_authority_gap_audit_window,
    plan_selection_materialization,
)
from src.trading_kernel.domain.instrument_selection import (
    INTERVAL_MS,
    SelectionSnapshot,
)
from src.trading_kernel.domain.owner_control import StrategyEntryState
from src.trading_kernel.domain.selection_authority import (
    AuthorityGapAuditKind,
    AuthorityGapAuditState,
    SelectionMode,
    build_pending_authority_gap_audit,
    next_canonical_eligible_close,
)

SESSION_START_MS = 1_704_067_200_000
DECISION_BOUNDARY_MS = SESSION_START_MS + 60 * 60 * 1000
FIRST_ELIGIBLE_CLOSE_MS = SESSION_START_MS + 5 * INTERVAL_MS
CURRENT_MEMBERS = (
    "binance-usdm:BTCUSDT:perpetual",
    "binance-usdm:ETHUSDT:perpetual",
)


def test_midnight_is_not_a_selection_authority_boundary() -> None:
    plan = plan_selection_materialization(
        _facts(now_ms=SESSION_START_MS)
    )

    assert plan.disposition is MaterializationDisposition.NOT_DUE


def test_dynamic_period_creates_continuity_before_snapshot() -> None:
    plan = plan_selection_materialization(
        _facts(
            now_ms=DECISION_BOUNDARY_MS + 1,
            selection_mode=SelectionMode.DYNAMIC_SELECTION,
        )
    )

    assert plan.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY
    assert plan.first_eligible_close_time_ms == FIRST_ELIGIBLE_CLOSE_MS
    assert plan.requires_gap_audit is False


def test_late_dynamic_continuity_requires_current_pair_gap_audit() -> None:
    now_ms = FIRST_ELIGIBLE_CLOSE_MS + 1
    plan = plan_selection_materialization(
        _facts(
            now_ms=now_ms,
            selection_mode=SelectionMode.DYNAMIC_SELECTION,
        )
    )

    assert plan.disposition is MaterializationDisposition.PRE_FENCE_CONTINUITY
    assert plan.requires_gap_audit is True
    assert plan.authority_gap_kind is AuthorityGapAuditKind.LATE_PRE_FENCE_CONTINUITY
    assert plan.first_eligible_close_time_ms == FIRST_ELIGIBLE_CLOSE_MS + INTERVAL_MS


def test_first_pending_dynamic_keeps_static_authority_until_terminal_outcome() -> None:
    plan = plan_selection_materialization(
        _facts(
            now_ms=DECISION_BOUNDARY_MS + 1,
            selection_mode=SelectionMode.STATIC_BASELINE,
            pending_selection_mode=SelectionMode.DYNAMIC_SELECTION,
        )
    )

    assert plan.disposition is MaterializationDisposition.KEEP_STATIC_PENDING_DYNAMIC


def test_future_pending_dynamic_does_not_start_in_current_period() -> None:
    plan = plan_selection_materialization(
        _facts(
            now_ms=DECISION_BOUNDARY_MS + 1,
            selection_mode=SelectionMode.STATIC_BASELINE,
            pending_selection_mode=SelectionMode.DYNAMIC_SELECTION,
            pending_effective_session_start_ms=SESSION_START_MS + 86_400_000,
        )
    )

    assert plan.disposition is MaterializationDisposition.STATIC_BASELINE


def test_owner_pause_outranks_continuity_and_snapshot_disposition() -> None:
    plan = plan_selection_materialization(
        _facts(
            now_ms=DECISION_BOUNDARY_MS + 1,
            selection_mode=SelectionMode.DYNAMIC_SELECTION,
            owner_entry_state=StrategyEntryState.PAUSED,
            snapshot=_snapshot(selected_count=0, ready_count=0),
        )
    )

    assert plan.disposition is MaterializationDisposition.OWNER_PAUSED


def test_open_vacuum_outranks_continuity_and_snapshot_disposition() -> None:
    plan = plan_selection_materialization(
        _facts(
            now_ms=DECISION_BOUNDARY_MS + 1,
            selection_mode=SelectionMode.DYNAMIC_SELECTION,
            snapshot=_snapshot(),
            selected_members=CURRENT_MEMBERS,
            open_vacuum=True,
        )
    )

    assert plan.disposition is MaterializationDisposition.WAITING_VACUUM


def test_zero_selected_opens_valid_empty_intent_without_final_authority() -> None:
    plan = plan_selection_materialization(
        _facts(
            now_ms=DECISION_BOUNDARY_MS + 1,
            selection_mode=SelectionMode.DYNAMIC_SELECTION,
            snapshot=_snapshot(selected_count=0, ready_count=0),
            continuity_exists=True,
        )
    )

    assert plan.disposition is MaterializationDisposition.VALID_EMPTY_INTENT
    assert plan.final_authority_outcome is None


def test_same_members_use_no_change_and_changed_members_create_generation() -> None:
    unchanged = plan_selection_materialization(
        _facts(
            now_ms=DECISION_BOUNDARY_MS + 1,
            selection_mode=SelectionMode.DYNAMIC_SELECTION,
            snapshot=_snapshot(),
            selected_members=CURRENT_MEMBERS,
            continuity_exists=True,
        )
    )
    changed = plan_selection_materialization(
        _facts(
            now_ms=DECISION_BOUNDARY_MS + 1,
            selection_mode=SelectionMode.DYNAMIC_SELECTION,
            snapshot=_snapshot(),
            selected_members=(
                "binance-usdm:BTCUSDT:perpetual",
                "binance-usdm:SOLUSDT:perpetual",
            ),
            continuity_exists=True,
        )
    )

    assert unchanged.disposition is MaterializationDisposition.NO_CHANGE
    assert changed.disposition is MaterializationDisposition.GENERATION_PENDING


def test_pending_gap_audit_has_no_checked_negative_proof_until_complete() -> None:
    audit = build_pending_authority_gap_audit(
        authority_gap_audit_id="gap-audit:test:1",
        selection_spec_id="sor-dynamic-selection-v0",
        session_start_ms=SESSION_START_MS,
        gap_kind=AuthorityGapAuditKind.LATE_PRE_FENCE_CONTINUITY,
        proposed_authority_outcome="PRE_FENCE_CONTINUITY",
        unauthorized_from_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        detector_semantic_digest="sha256:" + "a" * 64,
        created_at_ms=FIRST_ELIGIBLE_CLOSE_MS + 1,
    )

    assert audit.state is AuthorityGapAuditState.PENDING
    assert audit.audit_scope_digest is None
    assert audit.audit_result_digest is None


def test_next_eligible_close_is_strictly_future_and_canonical() -> None:
    assert next_canonical_eligible_close(
        session_start_ms=SESSION_START_MS,
        now_ms=FIRST_ELIGIBLE_CLOSE_MS,
    ) == FIRST_ELIGIBLE_CLOSE_MS + INTERVAL_MS


def test_gap_audit_before_first_sor_close_stays_pending_without_source_call() -> None:
    audit = build_pending_authority_gap_audit(
        authority_gap_audit_id="gap-audit:test:pre-first-close",
        selection_spec_id="sor-dynamic-selection-v0",
        session_start_ms=SESSION_START_MS,
        gap_kind=AuthorityGapAuditKind.ENTRY_VACUUM,
        proposed_authority_outcome="FALLBACK_PREVIOUS",
        unauthorized_from_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        detector_semantic_digest="sha256:" + "a" * 64,
        created_at_ms=DECISION_BOUNDARY_MS + 1,
    )

    plan = plan_authority_gap_audit_window(
        audit,
        now_ms=DECISION_BOUNDARY_MS + 3 * 60 * 1000,
    )

    assert plan.disposition is AuthorityGapAuditWindowDisposition.PENDING
    assert plan.audited_through_close_time_ms is None


def test_gap_audit_becomes_ready_after_first_close_and_expires_at_session_end() -> None:
    audit = build_pending_authority_gap_audit(
        authority_gap_audit_id="gap-audit:test:bounded-session",
        selection_spec_id="sor-dynamic-selection-v0",
        session_start_ms=SESSION_START_MS,
        gap_kind=AuthorityGapAuditKind.ENTRY_VACUUM,
        proposed_authority_outcome="FALLBACK_PREVIOUS",
        unauthorized_from_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        detector_semantic_digest="sha256:" + "a" * 64,
        created_at_ms=DECISION_BOUNDARY_MS + 1,
    )

    ready = plan_authority_gap_audit_window(
        audit,
        now_ms=FIRST_ELIGIBLE_CLOSE_MS,
    )
    expired = plan_authority_gap_audit_window(
        audit,
        now_ms=SESSION_START_MS + 96 * INTERVAL_MS,
    )

    assert ready.disposition is AuthorityGapAuditWindowDisposition.READY
    assert ready.audited_through_close_time_ms == FIRST_ELIGIBLE_CLOSE_MS
    assert expired.disposition is AuthorityGapAuditWindowDisposition.SESSION_EXPIRED


def _facts(
    *,
    now_ms: int,
    selection_mode: SelectionMode = SelectionMode.STATIC_BASELINE,
    pending_selection_mode: SelectionMode | None = None,
    pending_effective_session_start_ms: int | None = None,
    owner_entry_state: StrategyEntryState = StrategyEntryState.ENABLED,
    snapshot: SelectionSnapshot | None = None,
    selected_members: tuple[str, ...] = (),
    continuity_exists: bool = False,
    open_vacuum: bool = False,
) -> MaterializationPlanningFacts:
    return MaterializationPlanningFacts(
        selection_spec_id="sor-dynamic-selection-v0",
        strategy_group_id="SOR-001",
        session_start_ms=SESSION_START_MS,
        now_ms=now_ms,
        selection_mode=selection_mode,
        pending_selection_mode=pending_selection_mode,
        pending_effective_session_start_ms=(
            SESSION_START_MS
            if pending_selection_mode is not None
            and pending_effective_session_start_ms is None
            else pending_effective_session_start_ms
        ),
        owner_entry_state=owner_entry_state,
        current_long_members=CURRENT_MEMBERS,
        current_short_members=CURRENT_MEMBERS,
        snapshot=snapshot,
        selected_members=selected_members,
        continuity_exists=continuity_exists,
        open_vacuum=open_vacuum,
    )


def _snapshot(
    *, selected_count: int = 2, ready_count: int = 2
) -> SelectionSnapshot:
    return SelectionSnapshot(
        selection_snapshot_id=(
            "selection:sor-dynamic-selection-v0:1704067200000"
        ),
        selection_spec_id="sor-dynamic-selection-v0",
        strategy_group_id="SOR-001",
        strategy_version_id="sgv:SOR-001:v4",
        session_start_ms=SESSION_START_MS,
        decision_at_ms=DECISION_BOUNDARY_MS,
        feature_cutoff_at_ms=DECISION_BOUNDARY_MS,
        eligibility_not_before_ms=FIRST_ELIGIBLE_CLOSE_MS,
        expires_at_ms=SESSION_START_MS + 25 * 60 * 60 * 1000,
        candidate_count=24,
        ready_count=ready_count,
        selected_count=selected_count,
        source_observed_at_ms=DECISION_BOUNDARY_MS,
        source_semantic_digest="sha256:" + "b" * 64,
        selection_semantic_digest="sha256:" + "c" * 64,
        created_at_ms=DECISION_BOUNDARY_MS,
    )
