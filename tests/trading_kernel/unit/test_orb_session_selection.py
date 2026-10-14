from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.orb_session_selection import (
    ORB_EVENT_SPEC_IDS,
    ORB_SELECTION_SPEC_ID,
    ORB_STATIC_MEMBERS,
    ORB_STRATEGY_GROUP_ID,
    OrbSessionPeriod,
    OrbSessionSelectionSpec,
    build_orb_session_period,
    next_orb_eligible_close,
)
from src.trading_kernel.domain.selection_authority import (
    SelectionControl,
    SelectionMode,
)

D = 1_704_067_200_000
H = 3_600_000


def test_orb_daily_period_prepares_before_first_hourly_entry() -> None:
    p = build_orb_session_period(D)
    assert p.feature_cutoff_at_ms == D + H
    assert p.prepare_not_before_ms == D + H
    assert p.eligibility_not_before_ms == D + 2 * H
    assert p.snapshot_expires_at_ms == D + 25 * H
    assert p.trading_expires_at_ms == D + 24 * H
    assert len(ORB_STATIC_MEMBERS) == 7
    assert len(OrbSessionSelectionSpec().candidate_ids) == 24


@pytest.mark.parametrize(
    "now,expected",
    [
        (D + H, D + 2 * H),
        (D + 2 * H - 1, D + 2 * H),
        (D + 2 * H, D + 3 * H),
        (D + 22 * H + 1, D + 23 * H),
        (D + 23 * H, None),
    ],
)
def test_orb_late_grant_uses_strict_future_hour(now: int, expected: int | None) -> None:
    assert next_orb_eligible_close(session_start_ms=D, now_ms=now) == expected


@pytest.mark.parametrize(
    "change",
    [
        {"strategy_group_id": "SOR-001"},
        {
            "event_spec_ids": (
                "event_spec:SOR-001:SOR-LONG:v4",
                "event_spec:SOR-001:SOR-SHORT:v4",
            )
        },
        {"selected_count_max": 8},
        {"candidate_ids": ORB_STATIC_MEMBERS},
    ],
)
def test_orb_spec_rejects_old_sor_identity_and_parameter_drift(change: dict) -> None:
    with pytest.raises(ValidationError):
        OrbSessionSelectionSpec.model_validate(
            {**OrbSessionSelectionSpec().model_dump(), **change}
        )


def test_orb_period_rejects_noncanonical_utc_day_and_time_drift() -> None:
    with pytest.raises(ValidationError):
        build_orb_session_period(D + H)
    with pytest.raises(ValidationError):
        OrbSessionPeriod.model_validate(
            {**build_orb_session_period(D).model_dump(), "feature_cutoff_at_ms": D}
        )


def test_orb_static_pending_intent_survives_later_sessions_and_has_own_epoch() -> None:
    c = SelectionControl(
        strategy_group_id=ORB_STRATEGY_GROUP_ID,
        selection_spec_id=ORB_SELECTION_SPEC_ID,
        selection_mode=SelectionMode.STATIC_BASELINE,
        pending_selection_mode=SelectionMode.DYNAMIC_SELECTION,
        pending_effective_period_anchor_ms=D,
        pending_authorization_id="owner:orb:first",
        control_version=2,
        rollback_baseline_id="baseline:orb",
        selection_epoch_id="epoch:orb:first",
        updated_at_ms=D,
    )
    assert c.permits_dynamic_period(D + 24 * H)
    assert c.permits_dynamic_period(D + 48 * H)
    assert not c.permits_dynamic_period(D - 24 * H)
    assert ORB_EVENT_SPEC_IDS[0].startswith("event_spec:SOR-1H-001:")
    with pytest.raises(ValidationError):
        SelectionControl.model_validate(
            {**c.model_dump(), "selection_epoch_id": "sor-v0"}
        )
    with pytest.raises(ValidationError):
        SelectionControl.model_validate(
            {**c.model_dump(), "selection_spec_id": "sor-dynamic-selection-v0"}
        )


def test_orb_selection_reuses_old_numerics_but_has_independent_epoch_lineage() -> None:
    from decimal import Decimal

    from src.trading_kernel.domain.instrument_selection import (
        SelectionKline,
        SelectionSourceWindow,
        build_sor_dynamic_selection_period,
        build_sor_dynamic_selection_spec_v0,
        run_sor_dynamic_selection_v0,
    )
    from src.trading_kernel.domain.orb_session_selection import compute_orb_selection

    spec = OrbSessionSelectionSpec()
    windows = tuple(
        SelectionSourceWindow(
            exchange_instrument_id=member,
            input_window_start_ms=D - 23 * H,
            feature_cutoff_at_ms=D + H,
            klines=tuple(
                SelectionKline(
                    open_time_ms=D - 23 * H + i * 900000,
                    close_time_ms=D - 23 * H + (i + 1) * 900000,
                    open=Decimal(100),
                    close=Decimal(100),
                    high=Decimal(100 + (n % 3 + 1 if i >= 92 else 1)),
                    low=Decimal(100 - (n % 3 + 1 if i >= 92 else 1)),
                    quote_volume=Decimal(1_000_000 + n * 1000),
                )
                for i in range(96)
            ),
        )
        for n, member in enumerate(spec.candidate_ids)
    )
    old_spec = build_sor_dynamic_selection_spec_v0(
        selection_spec_id="sor-dynamic-selection-v0",
        strategy_group_id="SOR-001",
        strategy_version_id="sgv:SOR-001:v4",
        event_spec_ids=(
            "event_spec:SOR-001:SOR-LONG:v4",
            "event_spec:SOR-001:SOR-SHORT:v4",
        ),
        candidate_exchange_instrument_ids=spec.candidate_ids,
        installed_at_ms=D,
    )
    old = run_sor_dynamic_selection_v0(
        spec=old_spec,
        period=build_sor_dynamic_selection_period(session_start_ms=D),
        source_windows=windows,
        decision_at_ms=D + H,
        source_observed_at_ms=D + H + 1,
        created_at_ms=D + H + 2,
    )
    new = compute_orb_selection(
        spec=spec,
        period=build_orb_session_period(D),
        selection_epoch_id="epoch:orb:one",
        source_windows=windows,
        decision_at_ms=D + H,
        source_observed_at_ms=D + H + 1,
        created_at_ms=D + H + 2,
    )
    for a, b in zip(old.member_decisions, new.member_decisions, strict=True):
        for key in (
            "exchange_instrument_id",
            "or_high",
            "or_low",
            "pre_or_atr14",
            "pre_or_width_atr14",
            "trailing_24h_quote_volume",
            "stable_rank",
            "member_state",
            "selected",
            "primary_reason",
        ):
            assert getattr(a, key) == getattr(b, key)
        assert a.member_decision_id != b.member_decision_id
    assert new.snapshot.eligibility_not_before_ms == D + 2 * H
    assert new.snapshot.selection_epoch_id == "epoch:orb:one"
    assert new.snapshot.selection_snapshot_id != old.snapshot.selection_snapshot_id
    other = compute_orb_selection(
        spec=spec,
        period=build_orb_session_period(D),
        selection_epoch_id="epoch:orb:two",
        source_windows=windows,
        decision_at_ms=D + H,
        source_observed_at_ms=D + H + 1,
        created_at_ms=D + H + 2,
    )
    assert other.snapshot.selection_snapshot_id != new.snapshot.selection_snapshot_id
    with pytest.raises(ValueError, match="epoch"):
        compute_orb_selection(
            spec=spec,
            period=build_orb_session_period(D),
            selection_epoch_id="sor-v0",
            source_windows=windows,
            decision_at_ms=D + H,
            source_observed_at_ms=D + H + 1,
            created_at_ms=D + H + 2,
        )


def test_hourly_authority_rejects_legacy_clock_epoch_and_accepts_explicit_new_pair() -> (
    None
):
    from src.trading_kernel.domain.selection_authority import (
        AuthorityGrantProof,
        AuthorityGrantProofKind,
        AuthorityOutcome,
        ContinuitySourceKind,
        SelectionSessionAuthority,
        UniverseAuthorityPair,
    )

    payload = {
        "selection_authority_id": "authority:orb:test",
        "selection_spec_id": ORB_SELECTION_SPEC_ID,
        "selection_epoch_id": "epoch:orb:first",
        "selection_control_version": 3,
        "activation_authorization_id": "owner:orb:first",
        "session_start_ms": D,
        "decision_boundary_ms": D + H,
        "authority_sequence": 1,
        "selection_mode": SelectionMode.DYNAMIC_SELECTION,
        "selection_snapshot_id": "selection:orb:test",
        "continued_from_selection_authority_id": None,
        "continuity_source_kind": ContinuitySourceKind.AUTHORITY_GAP_AUDIT,
        "authority_gap_audit_id": "gap:orb:first",
        "materialization_generation_id": "generation:orb:first",
        "owner_control_version": 2,
        "authority_outcome": AuthorityOutcome.ACTIVE_NEW,
        "authorized_pair": UniverseAuthorityPair(
            long_universe_version_id="universe:orb:long",
            short_universe_version_id="universe:orb:short",
        ),
        "grant_proof": AuthorityGrantProof(
            kind=AuthorityGrantProofKind.AUDITED_AUTHORITY_GAP,
            predecessor_authority_id=None,
            authority_gap_audit_id="gap:orb:first",
        ),
        "effective_from_ms": D + H + 1,
        "first_eligible_close_time_ms": D + 2 * H,
        "expires_at_ms": D + 24 * H,
        "reason_code": "FIRST_DYNAMIC",
        "created_at_ms": D + H + 1,
    }
    a = SelectionSessionAuthority.model_validate(payload)
    assert not a.blocks_new_entry
    for updates in (
        {"selection_epoch_id": "sor-v0"},
        {"selection_control_version": None},
        {"first_eligible_close_time_ms": D + 75 * 60 * 1000},
        {"expires_at_ms": D + 25 * H},
    ):
        with pytest.raises(ValidationError):
            SelectionSessionAuthority.model_validate({**payload, **updates})
    with pytest.raises(ValidationError):
        SelectionSessionAuthority.model_validate(
            {**payload, "selection_spec_id": "sor-dynamic-selection-v0"}
        )


def test_retired_sor_never_gets_entry_from_an_enabled_control():
    from src.trading_kernel.application.owner_control import strategy_entry_is_enabled
    from src.trading_kernel.domain.owner_control import (
        StrategyEntryControl,
        StrategyEntryState,
    )
    control=StrategyEntryControl(strategy_group_id='SOR-001',entry_state=StrategyEntryState.ENABLED,control_version=1,last_event_id='historical:enabled',reason='historical',updated_at_ms=D)
    assert not strategy_entry_is_enabled(control)
