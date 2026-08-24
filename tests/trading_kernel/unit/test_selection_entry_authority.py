from __future__ import annotations

import pytest

from src.trading_kernel.application.ingest_signal import (
    SelectionEntryAuthorityFacts,
    SelectionEntryAuthorityStatus,
    evaluate_selection_entry_authority,
)
from src.trading_kernel.domain.selection_authority import (
    AuthorityGrantProof,
    AuthorityGrantProofKind,
    AuthorityOutcome,
    ContinuitySourceKind,
    SelectionControl,
    SelectionMode,
    SelectionSessionAuthority,
    UniverseAuthorityPair,
)

DAY_MS = 86_400_000
INTERVAL_MS = 900_000
SESSION_START_MS = 1_704_067_200_000
FIRST_ELIGIBLE_CLOSE_MS = SESSION_START_MS + 5 * INTERVAL_MS
EXPIRES_AT_MS = SESSION_START_MS + DAY_MS + 4 * INTERVAL_MS
SELECTION_SPEC_ID = "sor-dynamic-selection-v0"
LONG_UNIVERSE_ID = "universe:dynamic:long"
SHORT_UNIVERSE_ID = "universe:dynamic:short"
PAIR = UniverseAuthorityPair(
    long_universe_version_id=LONG_UNIVERSE_ID,
    short_universe_version_id=SHORT_UNIVERSE_ID,
)


def test_dynamic_observation_freezes_exact_current_birth_authority() -> None:
    authority = _continuity_authority(sequence=1)

    decision = evaluate_selection_entry_authority(
        _facts(current_authority=authority, authority_chain=(authority,)),
        birth_selection_authority_id=None,
        observed_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        now_ms=FIRST_ELIGIBLE_CLOSE_MS,
        allow_current_as_birth=True,
    )

    assert decision.status is SelectionEntryAuthorityStatus.VALID
    assert decision.selection_authority_id == authority.selection_authority_id


@pytest.mark.parametrize(
    ("facts_update", "expected_status"),
    [
        pytest.param(
            {"current_pair": UniverseAuthorityPair(
                long_universe_version_id="universe:wrong:long",
                short_universe_version_id=SHORT_UNIVERSE_ID,
            )},
            SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
            id="wrong-pair",
        ),
        pytest.param(
            {"active_generation_pair": UniverseAuthorityPair(
                long_universe_version_id="universe:wrong:long",
                short_universe_version_id=SHORT_UNIVERSE_ID,
            )},
            SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
            id="wrong-generation",
        ),
        pytest.param(
            {"scoped_vacuum_open": True},
            SelectionEntryAuthorityStatus.VACUUM_OPEN,
            id="open-vacuum",
        ),
        pytest.param(
            {"trigger_suppressed": True},
            SelectionEntryAuthorityStatus.TRIGGER_SUPPRESSED,
            id="trigger-suppression",
        ),
        pytest.param(
            {"owner_entry_enabled": False},
            SelectionEntryAuthorityStatus.OWNER_OR_POLICY_BLOCKED,
            id="owner-pause",
        ),
        pytest.param(
            {"global_policy_enabled": False},
            SelectionEntryAuthorityStatus.OWNER_OR_POLICY_BLOCKED,
            id="global-entry-disabled",
        ),
    ],
)
def test_dynamic_authority_fail_closed_boundaries(
    facts_update: dict[str, object],
    expected_status: SelectionEntryAuthorityStatus,
) -> None:
    authority = _active_new_authority(sequence=1)
    facts = _facts(
        current_authority=authority,
        authority_chain=(authority,),
        active_generation_pair=PAIR,
    ).model_copy(update=facts_update)

    decision = evaluate_selection_entry_authority(
        facts,
        birth_selection_authority_id=authority.selection_authority_id,
        observed_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        now_ms=FIRST_ELIGIBLE_CLOSE_MS,
        allow_current_as_birth=False,
    )

    assert decision.status is expected_status


def test_dynamic_authority_rejects_close_before_frozen_eligibility() -> None:
    authority = _continuity_authority(sequence=1)

    decision = evaluate_selection_entry_authority(
        _facts(current_authority=authority, authority_chain=(authority,)),
        birth_selection_authority_id=authority.selection_authority_id,
        observed_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS - INTERVAL_MS,
        now_ms=FIRST_ELIGIBLE_CLOSE_MS,
        allow_current_as_birth=False,
    )

    assert decision.status is SelectionEntryAuthorityStatus.AUTHORITY_INVALID
    assert decision.reason_code == "selection_close_before_first_eligible"


def test_continuity_to_continuity_to_no_change_preserves_birth_authority() -> None:
    birth = _continuity_authority(sequence=1)
    revision = _continuity_authority(sequence=2, predecessor=birth)
    current = _no_change_authority(sequence=3, predecessor=revision)

    decision = evaluate_selection_entry_authority(
        _facts(
            current_authority=current,
            authority_chain=(birth, revision, current),
        ),
        birth_selection_authority_id=birth.selection_authority_id,
        observed_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        now_ms=FIRST_ELIGIBLE_CLOSE_MS,
        allow_current_as_birth=False,
    )

    assert decision.status is SelectionEntryAuthorityStatus.VALID
    assert decision.selection_authority_id == birth.selection_authority_id
    assert decision.current_selection_authority_id == current.selection_authority_id


@pytest.mark.parametrize(
    ("facts_update", "expected_status"),
    [
        pytest.param(
            {"authority_interrupted": True},
            SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
            id="vacuum-or-policy-gap",
        ),
        pytest.param(
            {"owner_control_version": 2},
            SelectionEntryAuthorityStatus.OWNER_OR_POLICY_BLOCKED,
            id="owner-version-drift",
        ),
        pytest.param(
            {"current_pair": UniverseAuthorityPair(
                long_universe_version_id=LONG_UNIVERSE_ID,
                short_universe_version_id="universe:wrong:short",
            )},
            SelectionEntryAuthorityStatus.AUTHORITY_INVALID,
            id="pair-drift",
        ),
    ],
)
def test_compatible_successor_chain_breaks_fail_closed(
    facts_update: dict[str, object],
    expected_status: SelectionEntryAuthorityStatus,
) -> None:
    birth = _continuity_authority(sequence=1)
    current = _no_change_authority(sequence=2, predecessor=birth)
    facts = _facts(
        current_authority=current,
        authority_chain=(birth, current),
    ).model_copy(update=facts_update)

    decision = evaluate_selection_entry_authority(
        facts,
        birth_selection_authority_id=birth.selection_authority_id,
        observed_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        now_ms=FIRST_ELIGIBLE_CLOSE_MS,
        allow_current_as_birth=False,
    )

    assert decision.status is expected_status


def test_valid_empty_is_a_forward_only_new_entry_blocker() -> None:
    valid_empty = SelectionSessionAuthority(
        selection_authority_id="authority:valid-empty",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        decision_boundary_ms=SESSION_START_MS + 4 * INTERVAL_MS,
        authority_sequence=1,
        selection_mode=SelectionMode.DYNAMIC_SELECTION,
        selection_snapshot_id="snapshot:valid-empty",
        continued_from_selection_authority_id=None,
        continuity_source_kind=ContinuitySourceKind.NONE,
        authority_gap_audit_id=None,
        materialization_generation_id=None,
        owner_control_version=1,
        authority_outcome=AuthorityOutcome.VALID_EMPTY,
        authorized_pair=None,
        grant_proof=None,
        effective_from_ms=SESSION_START_MS + 4 * INTERVAL_MS,
        first_eligible_close_time_ms=None,
        expires_at_ms=EXPIRES_AT_MS,
        reason_code="NO_SELECTION_READY_MEMBERS",
        created_at_ms=SESSION_START_MS + 4 * INTERVAL_MS,
    )

    decision = evaluate_selection_entry_authority(
        _facts(current_authority=valid_empty, authority_chain=(valid_empty,)),
        birth_selection_authority_id=None,
        observed_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        now_ms=FIRST_ELIGIBLE_CLOSE_MS,
        allow_current_as_birth=True,
    )

    assert decision.status is SelectionEntryAuthorityStatus.AUTHORITY_INVALID
    assert decision.reason_code == "selection_authority_non_trading_outcome"


def test_ordinary_static_path_preserves_legacy_signal_semantics() -> None:
    facts = SelectionEntryAuthorityFacts(
        selection_control=_control(SelectionMode.STATIC_BASELINE),
        current_authority=None,
        authority_chain=(),
        current_pair=PAIR,
        active_generation_pair=None,
        scoped_vacuum_open=False,
        authority_interrupted=False,
        owner_entry_enabled=True,
        owner_control_version=1,
        global_policy_enabled=True,
        trigger_suppressed=False,
    )

    decision = evaluate_selection_entry_authority(
        facts,
        birth_selection_authority_id=None,
        observed_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        now_ms=FIRST_ELIGIBLE_CLOSE_MS,
        allow_current_as_birth=True,
    )

    assert decision.status is SelectionEntryAuthorityStatus.VALID
    assert decision.selection_authority_id is None


def test_first_static_fallback_consumes_transition_authority_and_suppression() -> None:
    fallback = _fallback_static_authority()
    facts = _facts(
        selection_mode=SelectionMode.STATIC_BASELINE,
        current_authority=fallback,
        authority_chain=(fallback,),
    )

    allowed = evaluate_selection_entry_authority(
        facts,
        birth_selection_authority_id=None,
        observed_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        now_ms=FIRST_ELIGIBLE_CLOSE_MS,
        allow_current_as_birth=True,
    )
    suppressed = evaluate_selection_entry_authority(
        facts.model_copy(update={"trigger_suppressed": True}),
        birth_selection_authority_id=fallback.selection_authority_id,
        observed_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS + INTERVAL_MS,
        now_ms=FIRST_ELIGIBLE_CLOSE_MS + INTERVAL_MS,
        allow_current_as_birth=False,
    )

    assert allowed.status is SelectionEntryAuthorityStatus.VALID
    assert allowed.selection_authority_id == fallback.selection_authority_id
    assert suppressed.status is SelectionEntryAuthorityStatus.TRIGGER_SUPPRESSED


def _facts(
    *,
    selection_mode: SelectionMode = SelectionMode.DYNAMIC_SELECTION,
    current_authority: SelectionSessionAuthority,
    authority_chain: tuple[SelectionSessionAuthority, ...],
    active_generation_pair: UniverseAuthorityPair | None = None,
) -> SelectionEntryAuthorityFacts:
    return SelectionEntryAuthorityFacts(
        selection_control=_control(selection_mode),
        current_authority=current_authority,
        authority_chain=authority_chain,
        current_pair=PAIR,
        active_generation_pair=active_generation_pair,
        scoped_vacuum_open=False,
        authority_interrupted=False,
        owner_entry_enabled=True,
        owner_control_version=1,
        global_policy_enabled=True,
        trigger_suppressed=False,
    )


def _control(selection_mode: SelectionMode) -> SelectionControl:
    return SelectionControl(
        strategy_group_id="SOR-001",
        selection_spec_id=SELECTION_SPEC_ID,
        selection_mode=selection_mode,
        pending_selection_mode=None,
        pending_effective_session_start_ms=None,
        pending_authorization_id=None,
        control_version=1,
        rollback_baseline_id=None,
        updated_at_ms=SESSION_START_MS,
    )


def _continuity_authority(
    *,
    sequence: int,
    predecessor: SelectionSessionAuthority | None = None,
) -> SelectionSessionAuthority:
    predecessor_id = (
        None if predecessor is None else predecessor.selection_authority_id
    )
    return SelectionSessionAuthority(
        selection_authority_id=f"authority:continuity:{sequence}",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        decision_boundary_ms=SESSION_START_MS + 4 * INTERVAL_MS,
        authority_sequence=sequence,
        selection_mode=SelectionMode.DYNAMIC_SELECTION,
        selection_snapshot_id=None,
        continued_from_selection_authority_id=predecessor_id,
        continuity_source_kind=(
            ContinuitySourceKind.AUTHORITY_GAP_AUDIT
            if predecessor is None
            else ContinuitySourceKind.SELECTION_AUTHORITY
        ),
        authority_gap_audit_id=("audit:continuity" if predecessor is None else None),
        materialization_generation_id=None,
        owner_control_version=1,
        authority_outcome=AuthorityOutcome.PRE_FENCE_CONTINUITY,
        authorized_pair=PAIR,
        grant_proof=AuthorityGrantProof(
            kind=(
                AuthorityGrantProofKind.AUDITED_AUTHORITY_GAP
                if predecessor is None
                else AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES
            ),
            predecessor_authority_id=predecessor_id,
            authority_gap_audit_id=(
                "audit:continuity" if predecessor is None else None
            ),
        ),
        effective_from_ms=SESSION_START_MS + 4 * INTERVAL_MS,
        first_eligible_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        expires_at_ms=EXPIRES_AT_MS,
        reason_code="CONTINUITY",
        created_at_ms=SESSION_START_MS + 4 * INTERVAL_MS + sequence,
    )


def _no_change_authority(
    *,
    sequence: int,
    predecessor: SelectionSessionAuthority,
) -> SelectionSessionAuthority:
    return SelectionSessionAuthority(
        selection_authority_id=f"authority:no-change:{sequence}",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        decision_boundary_ms=SESSION_START_MS + 4 * INTERVAL_MS,
        authority_sequence=sequence,
        selection_mode=SelectionMode.DYNAMIC_SELECTION,
        selection_snapshot_id="snapshot:no-change",
        continued_from_selection_authority_id=predecessor.selection_authority_id,
        continuity_source_kind=ContinuitySourceKind.SELECTION_AUTHORITY,
        authority_gap_audit_id=None,
        materialization_generation_id=None,
        owner_control_version=1,
        authority_outcome=AuthorityOutcome.NO_CHANGE,
        authorized_pair=PAIR,
        grant_proof=AuthorityGrantProof(
            kind=AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES,
            predecessor_authority_id=predecessor.selection_authority_id,
            authority_gap_audit_id=None,
        ),
        effective_from_ms=SESSION_START_MS + 4 * INTERVAL_MS,
        first_eligible_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        expires_at_ms=EXPIRES_AT_MS,
        reason_code="NO_CHANGE",
        created_at_ms=SESSION_START_MS + 4 * INTERVAL_MS + sequence,
    )


def _active_new_authority(*, sequence: int) -> SelectionSessionAuthority:
    return SelectionSessionAuthority(
        selection_authority_id=f"authority:active-new:{sequence}",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        decision_boundary_ms=SESSION_START_MS + 4 * INTERVAL_MS,
        authority_sequence=sequence,
        selection_mode=SelectionMode.DYNAMIC_SELECTION,
        selection_snapshot_id="snapshot:active-new",
        continued_from_selection_authority_id=None,
        continuity_source_kind=ContinuitySourceKind.AUTHORITY_GAP_AUDIT,
        authority_gap_audit_id="audit:active-new",
        materialization_generation_id="generation:active-new",
        owner_control_version=1,
        authority_outcome=AuthorityOutcome.ACTIVE_NEW,
        authorized_pair=PAIR,
        grant_proof=AuthorityGrantProof(
            kind=AuthorityGrantProofKind.AUDITED_AUTHORITY_GAP,
            predecessor_authority_id=None,
            authority_gap_audit_id="audit:active-new",
        ),
        effective_from_ms=SESSION_START_MS + 4 * INTERVAL_MS,
        first_eligible_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        expires_at_ms=EXPIRES_AT_MS,
        reason_code="ACTIVE_NEW",
        created_at_ms=SESSION_START_MS + 4 * INTERVAL_MS + sequence,
    )


def _fallback_static_authority() -> SelectionSessionAuthority:
    return SelectionSessionAuthority(
        selection_authority_id="authority:fallback-static:1",
        selection_spec_id=SELECTION_SPEC_ID,
        session_start_ms=SESSION_START_MS,
        decision_boundary_ms=SESSION_START_MS + 4 * INTERVAL_MS,
        authority_sequence=1,
        selection_mode=SelectionMode.STATIC_BASELINE,
        selection_snapshot_id="snapshot:fallback-static",
        continued_from_selection_authority_id=None,
        continuity_source_kind=ContinuitySourceKind.STATIC_BASELINE,
        authority_gap_audit_id="audit:fallback-static",
        materialization_generation_id="generation:failed-first-dynamic",
        owner_control_version=1,
        authority_outcome=AuthorityOutcome.FALLBACK_PREVIOUS,
        authorized_pair=PAIR,
        grant_proof=AuthorityGrantProof(
            kind=AuthorityGrantProofKind.AUDITED_AUTHORITY_GAP,
            predecessor_authority_id=None,
            authority_gap_audit_id="audit:fallback-static",
        ),
        effective_from_ms=SESSION_START_MS + 4 * INTERVAL_MS,
        first_eligible_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        expires_at_ms=EXPIRES_AT_MS,
        reason_code="materialization_timeout",
        created_at_ms=SESSION_START_MS + 4 * INTERVAL_MS + 1,
    )
