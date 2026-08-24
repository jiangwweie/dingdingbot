from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.selection_authority import (
    AuthorityGrantProof,
    AuthorityGrantProofKind,
    AuthorityOutcome,
    ContinuitySourceKind,
    SelectionMode,
    SelectionSessionAuthority,
    UniverseAuthorityPair,
    authority_successor_is_compatible,
    selection_authority_allows_new_entry,
)

SESSION_START_MS = 1_704_067_200_000
DECISION_BOUNDARY_MS = SESSION_START_MS + 60 * 60 * 1000
FIRST_ELIGIBLE_CLOSE_MS = SESSION_START_MS + 75 * 60 * 1000
EXPIRES_AT_MS = SESSION_START_MS + 25 * 60 * 60 * 1000
_UNSET = object()


def test_pre_fence_continuity_cannot_be_created_at_session_midnight() -> None:
    with pytest.raises(ValidationError, match="decision boundary"):
        _authority(effective_from_ms=SESSION_START_MS)


def test_first_static_fallback_requires_generation_audit_and_static_mode() -> None:
    with pytest.raises(ValidationError, match="generation and audited gap proof"):
        _authority(
            outcome=AuthorityOutcome.FALLBACK_PREVIOUS,
            continuity_source_kind=ContinuitySourceKind.STATIC_BASELINE,
            selection_mode=SelectionMode.STATIC_BASELINE,
            materialization_generation_id=None,
            grant_proof=AuthorityGrantProof(
                kind=AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES,
                predecessor_authority_id="authority:static:previous",
                authority_gap_audit_id=None,
            ),
        )

    with pytest.raises(ValidationError, match="must keep static_baseline mode"):
        _first_static_fallback(selection_mode=SelectionMode.DYNAMIC_SELECTION)

    fallback = _first_static_fallback()
    assert fallback.selection_mode is SelectionMode.STATIC_BASELINE
    assert fallback.first_eligible_close_time_ms == FIRST_ELIGIBLE_CLOSE_MS


def test_valid_empty_is_forward_only_and_cannot_authorize_a_pair() -> None:
    valid_empty = _authority(
        outcome=AuthorityOutcome.VALID_EMPTY,
        authorized_pair=None,
        first_eligible_close_time_ms=None,
        continuity_source_kind=ContinuitySourceKind.NONE,
        selection_snapshot_id="selection:snapshot:valid-empty",
        grant_proof=None,
        reason_code="NO_SELECTION_READY_MEMBERS",
    )

    assert valid_empty.blocks_new_entry is True
    assert valid_empty.allows_existing_ticket_lifecycle is True
    assert valid_empty.rewrites_existing_lineage is False

    with pytest.raises(ValidationError, match="non-trading outcome forbids Universe pair"):
        _authority(
            outcome=AuthorityOutcome.VALID_EMPTY,
            first_eligible_close_time_ms=None,
            continuity_source_kind=ContinuitySourceKind.NONE,
            selection_snapshot_id="selection:snapshot:valid-empty",
            grant_proof=None,
            reason_code="NO_SELECTION_READY_MEMBERS",
        )


def test_authority_requires_exact_long_and_short_pair() -> None:
    with pytest.raises(ValidationError):
        UniverseAuthorityPair.model_validate(
            {
                "long_universe_version_id": "universe:long:1",
                "short_universe_version_id": "",
            }
        )


def test_open_vacuum_overrides_an_existing_current_trading_authority() -> None:
    authority = _authority()

    assert selection_authority_allows_new_entry(
        authority,
        now_ms=FIRST_ELIGIBLE_CLOSE_MS + 1,
        observed_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        scoped_vacuum_open=False,
    )
    assert not selection_authority_allows_new_entry(
        authority,
        now_ms=FIRST_ELIGIBLE_CLOSE_MS + 1,
        observed_close_time_ms=FIRST_ELIGIBLE_CLOSE_MS,
        scoped_vacuum_open=True,
    )


def test_authority_grant_proof_is_exclusive_and_complete() -> None:
    with pytest.raises(ValidationError, match="continuous proof requires predecessor"):
        AuthorityGrantProof(
            kind=AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES,
            predecessor_authority_id=None,
            authority_gap_audit_id=None,
        )
    with pytest.raises(ValidationError, match="audited proof requires gap audit"):
        AuthorityGrantProof(
            kind=AuthorityGrantProofKind.AUDITED_AUTHORITY_GAP,
            predecessor_authority_id="authority:previous",
            authority_gap_audit_id=None,
        )
    with pytest.raises(ValidationError, match="forbids continuous predecessor"):
        AuthorityGrantProof(
            kind=AuthorityGrantProofKind.AUDITED_AUTHORITY_GAP,
            predecessor_authority_id="authority:previous",
            authority_gap_audit_id="gap-audit:1",
        )


def test_first_dynamic_no_change_can_inherit_static_baseline_coverage() -> None:
    authority = _authority(
        outcome=AuthorityOutcome.NO_CHANGE,
        selection_snapshot_id="selection:snapshot:first-no-change",
        continuity_source_kind=ContinuitySourceKind.STATIC_BASELINE,
        continued_from_selection_authority_id=None,
        grant_proof=AuthorityGrantProof(
            kind=AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES,
            predecessor_authority_id="authority:static-baseline:previous",
            authority_gap_audit_id=None,
        ),
        reason_code="FIRST_DYNAMIC_MEMBERS_UNCHANGED",
    )

    assert authority.selection_mode is SelectionMode.DYNAMIC_SELECTION
    assert authority.continued_from_selection_authority_id is None


def test_successor_compatibility_accepts_only_uninterrupted_same_pair_chain() -> None:
    birth = _authority(authority_id="authority:continuity:1", sequence=1)
    successor = _authority(
        authority_id="authority:no-change:2",
        sequence=2,
        outcome=AuthorityOutcome.NO_CHANGE,
        selection_snapshot_id="selection:snapshot:no-change",
        continued_from_selection_authority_id=birth.selection_authority_id,
        grant_proof=AuthorityGrantProof(
            kind=AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES,
            predecessor_authority_id=birth.selection_authority_id,
            authority_gap_audit_id=None,
        ),
    )

    assert authority_successor_is_compatible(
        birth=birth,
        successor=successor,
        vacuum_opened=False,
        owner_control_continuous=True,
        global_policy_continuous=True,
        eligible_close_coverage_continuous=True,
    )

    later_first_close = successor.model_copy(
        update={"first_eligible_close_time_ms": FIRST_ELIGIBLE_CLOSE_MS + 15 * 60 * 1000}
    )
    assert authority_successor_is_compatible(
        birth=birth,
        successor=later_first_close,
        vacuum_opened=False,
        owner_control_continuous=True,
        global_policy_continuous=True,
        eligible_close_coverage_continuous=True,
    )

    for broken in (
        {"vacuum_opened": True},
        {"owner_control_continuous": False},
        {"global_policy_continuous": False},
        {"eligible_close_coverage_continuous": False},
    ):
        assert not authority_successor_is_compatible(
            birth=birth,
            successor=successor,
            vacuum_opened=broken.get("vacuum_opened", False),
            owner_control_continuous=broken.get("owner_control_continuous", True),
            global_policy_continuous=broken.get("global_policy_continuous", True),
            eligible_close_coverage_continuous=broken.get(
                "eligible_close_coverage_continuous", True
            ),
        )

    changed_pair = successor.model_copy(
        update={
            "authorized_pair": UniverseAuthorityPair(
                long_universe_version_id="universe:long:2",
                short_universe_version_id="universe:short:1",
            )
        }
    )
    assert not authority_successor_is_compatible(
        birth=birth,
        successor=changed_pair,
        vacuum_opened=False,
        owner_control_continuous=True,
        global_policy_continuous=True,
        eligible_close_coverage_continuous=True,
    )

    reason_revision = _authority(
        authority_id="authority:continuity:2",
        sequence=2,
        outcome=AuthorityOutcome.PRE_FENCE_CONTINUITY,
        continued_from_selection_authority_id=birth.selection_authority_id,
        grant_proof=AuthorityGrantProof(
            kind=AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES,
            predecessor_authority_id=birth.selection_authority_id,
            authority_gap_audit_id=None,
        ),
        reason_code="AWAITING_MATERIALIZATION",
    )
    assert authority_successor_is_compatible(
        birth=birth,
        successor=reason_revision,
        vacuum_opened=False,
        owner_control_continuous=True,
        global_policy_continuous=True,
        eligible_close_coverage_continuous=True,
    )

    next_period = reason_revision.model_copy(
        update={"session_start_ms": SESSION_START_MS + 24 * 60 * 60 * 1000}
    )
    assert not authority_successor_is_compatible(
        birth=birth,
        successor=next_period,
        vacuum_opened=False,
        owner_control_continuous=True,
        global_policy_continuous=True,
        eligible_close_coverage_continuous=True,
    )


def _first_static_fallback(
    *, selection_mode: SelectionMode = SelectionMode.STATIC_BASELINE
) -> SelectionSessionAuthority:
    return _authority(
        outcome=AuthorityOutcome.FALLBACK_PREVIOUS,
        continuity_source_kind=ContinuitySourceKind.STATIC_BASELINE,
        selection_mode=selection_mode,
        selection_snapshot_id="selection:snapshot:first-dynamic",
        materialization_generation_id="generation:first-dynamic",
        authority_gap_audit_id="gap-audit:first-dynamic",
        continued_from_selection_authority_id=None,
        grant_proof=AuthorityGrantProof(
            kind=AuthorityGrantProofKind.AUDITED_AUTHORITY_GAP,
            predecessor_authority_id=None,
            authority_gap_audit_id="gap-audit:first-dynamic",
        ),
        reason_code="FIRST_DYNAMIC_MATERIALIZATION_FAILED",
    )


def _authority(
    *,
    authority_id: str = "authority:continuity:1",
    sequence: int = 1,
    outcome: AuthorityOutcome = AuthorityOutcome.PRE_FENCE_CONTINUITY,
    effective_from_ms: int = DECISION_BOUNDARY_MS,
    authorized_pair: UniverseAuthorityPair | None | object = _UNSET,
    first_eligible_close_time_ms: int | None = FIRST_ELIGIBLE_CLOSE_MS,
    continuity_source_kind: ContinuitySourceKind = ContinuitySourceKind.SELECTION_AUTHORITY,
    selection_mode: SelectionMode = SelectionMode.DYNAMIC_SELECTION,
    selection_snapshot_id: str | None = None,
    materialization_generation_id: str | None = None,
    authority_gap_audit_id: str | None = None,
    continued_from_selection_authority_id: str | None = "authority:previous",
    grant_proof: AuthorityGrantProof | None | object = _UNSET,
    reason_code: str = "AWAITING_SELECTION",
) -> SelectionSessionAuthority:
    return SelectionSessionAuthority(
        selection_authority_id=authority_id,
        selection_spec_id="sor-dynamic-selection-v0",
        session_start_ms=SESSION_START_MS,
        decision_boundary_ms=DECISION_BOUNDARY_MS,
        authority_sequence=sequence,
        selection_mode=selection_mode,
        selection_snapshot_id=selection_snapshot_id,
        continued_from_selection_authority_id=continued_from_selection_authority_id,
        continuity_source_kind=continuity_source_kind,
        authority_gap_audit_id=authority_gap_audit_id,
        materialization_generation_id=materialization_generation_id,
        owner_control_version=1,
        authority_outcome=outcome,
        authorized_pair=(
            UniverseAuthorityPair(
                long_universe_version_id="universe:long:1",
                short_universe_version_id="universe:short:1",
            )
            if authorized_pair is _UNSET
            else authorized_pair
        ),
        grant_proof=(
            AuthorityGrantProof(
                kind=AuthorityGrantProofKind.CONTINUOUS_ELIGIBLE_CLOSES,
                predecessor_authority_id="authority:previous",
                authority_gap_audit_id=None,
            )
            if grant_proof is _UNSET
            else grant_proof
        ),
        effective_from_ms=effective_from_ms,
        first_eligible_close_time_ms=first_eligible_close_time_ms,
        expires_at_ms=EXPIRES_AT_MS,
        reason_code=reason_code,
        created_at_ms=effective_from_ms,
    )
