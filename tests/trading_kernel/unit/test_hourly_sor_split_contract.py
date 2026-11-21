from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.application.exit_regime import check_exit_regime
from src.trading_kernel.domain.orb_session_selection import OrbSessionSelectionSpec

LONG = "event_spec:SOR-1H-LONG-001:SOR-1H-LONG:v1"
SHORT = "event_spec:SOR-1H-SHORT-001:SOR-1H-SHORT:v1"


D = 1_704_067_200_000
H = 3_600_000


def candle(index: int, close: int, high: int = 105, low: int = 95):
    from src.trading_kernel.domain.market import ClosedCandle

    return ClosedCandle(
        open_time_ms=D + index * H,
        close_time_ms=D + (index + 1) * H,
        open=Decimal(100),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(100),
    )


def test_directional_selection_specs_share_parameters_but_never_identity():
    from src.trading_kernel.domain.orb_session_selection import (
        daily_entry_interval_ms,
        daily_event_spec_ids,
        directional_orb_spec,
        orb_snapshot_identity,
    )

    long = directional_orb_spec("SOR-1H-LONG-001")
    short = directional_orb_spec("SOR-1H-SHORT-001")
    assert long.event_spec_ids == (LONG,)
    assert short.event_spec_ids == (SHORT,)
    assert long.selection_spec_id != short.selection_spec_id
    assert daily_event_spec_ids(long.selection_spec_id) == (LONG,)
    assert daily_event_spec_ids(short.selection_spec_id) == (SHORT,)
    assert (
        long.entry_interval_ms
        == daily_entry_interval_ms(short.selection_spec_id)
        == 3_600_000
    )
    assert (
        long.candidate_ids
        == short.candidate_ids
        == OrbSessionSelectionSpec().candidate_ids
    )
    assert long.selected_count_max == short.selected_count_max == 7
    with pytest.raises(ValueError, match="identity"):
        OrbSessionSelectionSpec.model_validate(
            dict(long.model_dump(), event_spec_ids=(SHORT,))
        )
    assert (
        len(
            {
                orb_snapshot_identity(
                    "test-epoch",
                    1_704_067_200_000,
                    selection_spec_id=spec.selection_spec_id,
                )
                for spec in (long, short, OrbSessionSelectionSpec())
            }
        )
        == 3
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("configuration", ["missing", "unlisted"])
async def test_new_long_requires_exact_exit_configuration(configuration):
    record = (
        None if configuration == "missing"
        else SimpleNamespace(intent=SimpleNamespace(events=()))
    )
    uow = SimpleNamespace(
        exit_profiles=SimpleNamespace(
            get_current_configuration=AsyncMock(return_value=record)
        ),
        signals=SimpleNamespace(get_runtime_capability=AsyncMock(return_value=None)),
    )
    reason, proof = await check_exit_regime(
        uow, venue_id="binance-usdm", account_id="seoul-test",
        event_spec_id=LONG, now_ms=1000,
    )
    assert reason == "exit_configuration_not_activated" and proof is None


@pytest.mark.asyncio
async def test_disabled_long_ma50_still_requires_matching_current_exit_binding():
    uow = SimpleNamespace(exit_profiles=SimpleNamespace(
        get_current_configuration=AsyncMock(return_value=SimpleNamespace(
            intent=SimpleNamespace(events=(SimpleNamespace(event_spec_id=LONG, ma50_enabled=False),)),
            profiles=(SimpleNamespace(event_spec_id=LONG),),
        )),
        get_current_binding=AsyncMock(return_value=None),
        get_ma50_snapshot=AsyncMock(),
    ))
    reason, proof = await check_exit_regime(
        uow, venue_id="binance-usdm", account_id="seoul-test",
        event_spec_id=LONG, now_ms=1000,
    )
    assert reason == "exit_configuration_binding_drift" and proof is None
    uow.exit_profiles.get_ma50_snapshot.assert_not_awaited()


@pytest.mark.parametrize(("event", "enabled"), [(LONG, True), (LONG, False), (SHORT, False), (SHORT, True)])
def test_directional_sor_ma50_is_configurable_for_long_only(event, enabled):
    from src.trading_kernel.domain.exit_configuration import EventExitParameters

    payload = {
        "event_spec_id": event,
        "expected_binding_id": "binding",
        "expected_binding_revision": 1,
        "reward_multiple": Decimal("1.2"),
        "target_fraction": Decimal(".5"),
        "minimum_lift": False,
        "max_actual_fraction": Decimal(1),
        "ma50_enabled": enabled,
    }
    if event == SHORT and enabled:
        with pytest.raises(ValueError, match="MA50"):
            EventExitParameters.model_validate(payload)
    else:
        assert EventExitParameters.model_validate(payload).ma50_enabled is enabled


@pytest.mark.parametrize(
    ("group", "legacy", "next_close"),
    [
        ("SOR-1H-LONG-001", "event_spec:SOR-1H-001:SOR-1H-LONG:v1", 106),
        ("SOR-1H-SHORT-001", "event_spec:SOR-1H-001:SOR-1H-SHORT:v1", 94),
    ],
)
def test_registered_standalone_event_uses_same_signal_and_exit_clock(
    group, legacy, next_close
):
    from src.trading_kernel.domain.detector import detector_for
    from src.trading_kernel.domain.exit_policy import registered_event_exit_bindings
    from src.trading_kernel.domain.market import MarketSnapshot
    from src.trading_kernel.domain.orb_session_selection import directional_orb_spec
    from src.trading_kernel.domain.product import product_compatibility_for
    from src.trading_kernel.domain.strategy_registry import strategy_contract_for

    (event,) = directional_orb_spec(group).event_spec_ids
    current = strategy_contract_for(event)
    assert current.strategy_group_id == group
    assert (
        current.exposure_family
        == strategy_contract_for(legacy).exposure_family
        == "opening_range"
    )
    assert product_compatibility_for(event).product_family == "crypto_perpetual"
    snapshot = MarketSnapshot(
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        trigger_candle_close_time_ms=D + 2 * H,
        candles_1h=(candle(0, 100), candle(1, next_close, 106, 94)),
    )
    source = detector_for(legacy).evaluate(snapshot)
    result = detector_for(event).evaluate(snapshot)
    assert result.triggered and result.occurred_at_ms == source.occurred_at_ms
    assert {name: fact.value for name, fact in result.facts_by_name.items()} == {
        name: fact.value for name, fact in source.facts_by_name.items()
    }
    # This compares frozen default exit semantics; the live cutover must copy effective parameters.
    profiles = {
        b.event_spec_id: b.exit_profile_id
        for b in registered_event_exit_bindings(include_sor_split=True)
    }
    assert profiles[event] == profiles[legacy]


@pytest.mark.parametrize("group", ["SOR-1H-LONG-001", "SOR-1H-SHORT-001"])
def test_directional_authority_rejects_a_snapshot_from_the_other_side(group):
    from src.trading_kernel.domain.orb_session_selection import (
        OrbSessionSelectionSnapshot,
        build_orb_session_period,
        directional_orb_spec,
        orb_snapshot_identity,
    )

    spec = directional_orb_spec(group)
    opposite = directional_orb_spec(
        "SOR-1H-SHORT-001" if group == "SOR-1H-LONG-001" else "SOR-1H-LONG-001"
    )
    period = build_orb_session_period(1_704_067_200_000)
    cutoff = period.feature_cutoff_at_ms
    payload = {
        "selection_snapshot_id": orb_snapshot_identity(
            "epoch:test",
            period.session_start_ms,
            selection_spec_id=spec.selection_spec_id,
        ),
        "selection_spec_id": spec.selection_spec_id,
        "strategy_group_id": spec.strategy_group_id,
        "strategy_version_id": spec.strategy_version_id,
        "selection_epoch_id": "epoch:test",
        "session_start_ms": period.session_start_ms,
        "decision_at_ms": cutoff,
        "feature_cutoff_at_ms": cutoff,
        "eligibility_not_before_ms": period.eligibility_not_before_ms,
        "expires_at_ms": period.snapshot_expires_at_ms,
        "candidate_count": 24,
        "ready_count": 1,
        "selected_count": 1,
        "source_observed_at_ms": cutoff,
        "source_semantic_digest": "sha256:" + "a" * 64,
        "selection_semantic_digest": "sha256:" + "b" * 64,
        "created_at_ms": cutoff + 1,
    }
    assert (
        OrbSessionSelectionSnapshot.model_validate(payload).selection_spec_id
        == spec.selection_spec_id
    )
    with pytest.raises(ValueError, match="identity"):
        OrbSessionSelectionSnapshot.model_validate(
            {
                **payload,
                "selection_spec_id": opposite.selection_spec_id,
                "strategy_group_id": opposite.strategy_group_id,
                "strategy_version_id": opposite.strategy_version_id,
            }
        )


@pytest.mark.parametrize("group", ["SOR-1H-LONG-001", "SOR-1H-SHORT-001"])
def test_directional_selection_control_owns_daily_clock_and_exact_spec(group):
    from src.trading_kernel.domain.orb_session_selection import directional_orb_spec
    from src.trading_kernel.domain.selection_authority import SelectionControl

    spec = directional_orb_spec(group)
    day = 1_704_067_200_000
    payload = {
        "strategy_group_id": group,
        "selection_spec_id": spec.selection_spec_id,
        "selection_mode": "static_baseline",
        "pending_selection_mode": "dynamic_selection",
        "pending_effective_period_anchor_ms": day,
        "pending_authorization_id": "owner:selection",
        "control_version": 2,
        "rollback_baseline_id": "baseline:directional",
        "selection_epoch_id": "epoch:directional",
        "updated_at_ms": day,
    }
    assert SelectionControl.model_validate(payload).permits_dynamic_period(day)
    with pytest.raises(ValueError, match="Selection Spec"):
        SelectionControl.model_validate(
            {
                **payload,
                "selection_spec_id": OrbSessionSelectionSpec().selection_spec_id,
            }
        )
    with pytest.raises(ValueError, match="UTC period"):
        SelectionControl.model_validate(
            {**payload, "pending_effective_period_anchor_ms": day + 3_600_000}
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("event", [LONG, SHORT])
async def test_mixed_authority_does_not_grant_new_or_retired_hourly_entries(event):
    from src.trading_kernel.domain.orb_session_selection import ORB_EVENT_SPEC_IDS

    installed = SimpleNamespace(
        intent=SimpleNamespace(
            events=(
                SimpleNamespace(event_spec_id=LONG, ma50_enabled=True),
                SimpleNamespace(event_spec_id=SHORT, ma50_enabled=False),
            )
        )
    )
    uow = SimpleNamespace(
        exit_profiles=SimpleNamespace(
            get_current_configuration=AsyncMock(return_value=installed)
        ),
        signals=SimpleNamespace(get_runtime_capability=AsyncMock(return_value=None)),
    )
    kwargs = {
        "uow": uow,
        "venue_id": "binance-usdm",
        "account_id": "seoul-test",
        "now_ms": 1000,
    }
    old = ORB_EVENT_SPEC_IDS[0 if event == LONG else 1]
    assert (await check_exit_regime(**kwargs, event_spec_id=old))[
        0
    ] == "exit_configuration_not_activated"
    uow.exit_profiles.get_current_configuration.return_value = None
    assert (await check_exit_regime(**kwargs, event_spec_id=event))[
        0
    ] == "exit_configuration_not_activated"


def test_normalized_authority_requires_only_the_installed_direction():
    from src.trading_kernel.domain.selection_authority import selected_member_set_digest
    from src.trading_kernel.infrastructure.pg_selection_event_bindings import (
        sor_authority_pair_from_bindings,
    )

    digest = selected_member_set_digest(("binance-usdm:BTCUSDT:perpetual",))
    spec = "SOR_1H_SHORT_OR_ATR_DYNAMIC_V1"
    binding = {
        "event_spec_id": SHORT,
        "position_side": "short",
        "universe_version_id": "universe:short",
        "member_set_digest": digest,
        "grant_state": "ACTIVE",
    }
    grant = sor_authority_pair_from_bindings([binding], selection_spec_id=spec)
    assert grant is not None and grant.short_universe_version_id == "universe:short"
    assert grant.long_universe_version_id is None
    with pytest.raises(ValueError):
        sor_authority_pair_from_bindings(
            [
                binding,
                {**binding, "event_spec_id": LONG, "position_side": "long"},
            ],
            selection_spec_id=spec,
        )
    with pytest.raises(ValueError):
        sor_authority_pair_from_bindings(
            [
                {**binding, "event_spec_id": LONG, "position_side": "long"},
            ],
            selection_spec_id=spec,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("current_pointer", [True, False])
async def test_directional_entry_resolves_only_its_own_event_universe(current_pointer):
    from src.trading_kernel.application.ingest_signal import (
        SelectionEntryAuthorityStatus,
        resolve_selection_entry_authority,
    )
    from src.trading_kernel.domain.orb_session_selection import directional_orb_spec
    from src.trading_kernel.domain.owner_control import StrategyEntryState
    from src.trading_kernel.domain.owner_policy import OwnerPolicyScope
    from src.trading_kernel.domain.selection_authority import SelectionControl

    group = "SOR-1H-SHORT-001"
    spec = directional_orb_spec(group)
    day = 1_704_067_200_000
    control = SelectionControl(
        strategy_group_id=group,
        selection_spec_id=spec.selection_spec_id,
        selection_mode="dynamic_selection",
        pending_selection_mode=None,
        pending_effective_period_anchor_ms=None,
        pending_authorization_id=None,
        control_version=2,
        rollback_baseline_id="baseline:short",
        selection_epoch_id="epoch:short",
        updated_at_ms=day,
    )
    pair = {
        "long_universe_version_id": None,
        "short_universe_version_id": "universe:short",
    }
    from src.trading_kernel.domain.selection_authority import SelectionSessionAuthority

    current = SelectionSessionAuthority(
        selection_authority_id="authority:short",
        selection_spec_id=spec.selection_spec_id,
        selection_epoch_id=control.selection_epoch_id,
        selection_control_version=control.control_version,
        session_start_ms=day,
        decision_boundary_ms=day + 3_600_000,
        authority_sequence=1,
        selection_mode="dynamic_selection",
        selection_snapshot_id="snapshot:short",
        continued_from_selection_authority_id=None,
        continuity_source_kind="AUTHORITY_GAP_AUDIT",
        authority_gap_audit_id="audit:short",
        materialization_generation_id="generation:short",
        owner_control_version=3,
        authority_outcome="ACTIVE_NEW",
        authorized_pair=pair,
        grant_proof={
            "kind": "AUDITED_AUTHORITY_GAP",
            "predecessor_authority_id": None,
            "authority_gap_audit_id": "audit:short",
        },
        effective_from_ms=day + 3_600_000,
        first_eligible_close_time_ms=day + 7_200_000,
        expires_at_ms=day + 86_400_000,
        reason_code="activated",
        created_at_ms=day + 3_600_000,
    )
    from src.trading_kernel.application.advance_strategy_universe import (
        UniverseActivationOperation,
        UniverseActivationRequest,
    )

    activation = {
        "operation": UniverseActivationOperation.ACTIVATE_DYNAMIC_PAIR,
        "materialization_generation_id": "generation:short",
        "attempted_at_ms": current.created_at_ms,
        "selection_authority": current,
    }
    request = UniverseActivationRequest(
        universe_version_id="universe:short", **activation
    )
    assert request.paired_universe_version_id is None
    with pytest.raises(ValueError, match="Authority"):
        UniverseActivationRequest(universe_version_id="universe:other", **activation)
    with pytest.raises(ValueError, match="Authority"):
        UniverseActivationRequest(
            universe_version_id="universe:short",
            paired_universe_version_id="universe:long",
            **activation,
        )

    uow = SimpleNamespace(
        instrument_selection=SimpleNamespace(
            get_selection_control=AsyncMock(return_value=control),
            get_current_authority=AsyncMock(return_value=current),
            get_current_entry_vacuum=AsyncMock(return_value=None),
        ),
        owner_controls=SimpleNamespace(
            get_strategy_control=AsyncMock(
                return_value=SimpleNamespace(
                    entry_state=StrategyEntryState.ENABLED, control_version=3
                )
            )
        ),
        entry_admission=SimpleNamespace(
            get_owner_policy=AsyncMock(
                return_value=SimpleNamespace(
                    enabled=True,
                    new_entry_submit_enabled=True,
                    scope=OwnerPolicyScope(
                        event_runtime_profiles=(
                            {
                                "event_spec_id": SHORT,
                                "runtime_profile_id": "tiny-live-v1",
                            },
                        )
                    ),
                )
            )
        ),
        strategy_universes=SimpleNamespace(
            get_current=AsyncMock(
                return_value=SimpleNamespace(
                    event_spec_id=SHORT, universe_version_id="universe:short"
                )
                if current_pointer
                else None
            )
        ),
        signals=SimpleNamespace(
            get_selection_authority_chain=AsyncMock(return_value=(current,)),
            selection_authority_was_interrupted=AsyncMock(return_value=False),
            selection_generation_matches_pair=AsyncMock(return_value=True),
            is_strategy_trigger_suppressed=AsyncMock(return_value=False),
        ),
    )
    decision = await resolve_selection_entry_authority(
        uow,
        runtime_scope=SimpleNamespace(
            strategy_group_id=group,
            event_spec_id=SHORT,
            owner_policy_id="policy",
            runtime_profile_id="tiny-live-v1",
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        ),
        birth_selection_authority_id=None,
        observed_close_time_ms=day + 7_200_000,
        now_ms=day + 7_200_001,
        allow_current_as_birth=True,
    )
    uow.strategy_universes.get_current.assert_awaited_once_with(SHORT)
    assert decision.status is (
        SelectionEntryAuthorityStatus.VALID
        if current_pointer
        else SelectionEntryAuthorityStatus.AUTHORITY_INVALID
    )


@pytest.mark.parametrize(
    ("group", "side"), [("SOR-1H-LONG-001", "long"), ("SOR-1H-SHORT-001", "short")]
)
def test_generation_preserves_its_exact_previous_universe_and_target(group, side):
    from src.trading_kernel.application.coordinate_selection_materialization import (
        _build_pending_generation,
    )
    from src.trading_kernel.domain.orb_session_selection import (
        OrbSessionSelectionSnapshot,
        build_orb_session_period,
        directional_orb_spec,
        orb_snapshot_identity,
    )
    from src.trading_kernel.domain.selection_authority import (
        SelectionControl,
        UniverseAuthorityPair,
    )

    spec = directional_orb_spec(group)
    period = build_orb_session_period(1_704_067_200_000)
    epoch = "epoch:generation"
    cutoff = period.feature_cutoff_at_ms
    snapshot = OrbSessionSelectionSnapshot(
        selection_snapshot_id=orb_snapshot_identity(
            epoch, period.session_start_ms, selection_spec_id=spec.selection_spec_id
        ),
        selection_spec_id=spec.selection_spec_id,
        strategy_group_id=group,
        strategy_version_id=spec.strategy_version_id,
        selection_epoch_id=epoch,
        session_start_ms=period.session_start_ms,
        decision_at_ms=cutoff,
        feature_cutoff_at_ms=cutoff,
        eligibility_not_before_ms=period.eligibility_not_before_ms,
        expires_at_ms=period.snapshot_expires_at_ms,
        candidate_count=24,
        ready_count=1,
        selected_count=1,
        source_observed_at_ms=cutoff,
        source_semantic_digest="sha256:" + "a" * 64,
        selection_semantic_digest="sha256:" + "b" * 64,
        created_at_ms=cutoff + 1,
    )
    control = SelectionControl(
        strategy_group_id=group,
        selection_spec_id=spec.selection_spec_id,
        selection_mode="dynamic_selection",
        pending_selection_mode=None,
        pending_effective_period_anchor_ms=None,
        pending_authorization_id=None,
        control_version=2,
        rollback_baseline_id="baseline:previous",
        selection_epoch_id=epoch,
        updated_at_ms=cutoff,
    )
    previous = UniverseAuthorityPair(
        **{f"{side}_universe_version_id": "universe:previous"}
    )
    generation, targets = _build_pending_generation(
        snapshot=snapshot,
        selected_members=("binance-usdm:BTCUSDT:perpetual",),
        previous_pair=previous,
        created_at_ms=cutoff + 2,
        selection_control=control,
    )
    assert [target.position_side for target in targets] == [side]
    assert [target.event_spec_id for target in targets] == list(spec.event_spec_ids)
    assert targets[0].materialization_order == (1 if side == "long" else 2)
    assert (
        getattr(generation, f"previous_{side}_universe_version_id")
        == "universe:previous"
    )
    assert generation.model_dump()["selection_epoch_id"] == epoch
    with pytest.raises(ValueError, match="sides"):
        _build_pending_generation(
            snapshot=snapshot,
            selected_members=("binance-usdm:BTCUSDT:perpetual",),
            previous_pair=UniverseAuthorityPair(
                long_universe_version_id="universe:long",
                short_universe_version_id="universe:short",
            ),
            created_at_ms=cutoff + 2,
            selection_control=control,
        )


def test_directional_static_baseline_has_only_its_own_event():
    from src.trading_kernel.domain.orb_session_selection import (
        ORB_SHORT_SPEC_ID,
        OrbStaticRollbackBaseline,
        OrbStaticSourceEvent,
    )

    source = OrbStaticSourceEvent(
        event_spec_id=SHORT,
        position_side="short",
        universe_version_id="universe:short",
        universe_semantic_digest="sha256:" + "c" * 64,
        member_set_digest="sha256:" + "d" * 64,
    )
    baseline = OrbStaticRollbackBaseline.build(
        selection_spec_id=ORB_SHORT_SPEC_ID,
        source_events=(source,),
        captured_at_ms=1000,
    )
    assert baseline.strategy_group_id == "SOR-1H-SHORT-001"
    with pytest.raises(ValueError, match="exact"):
        OrbStaticRollbackBaseline.build(source_events=(source,), captured_at_ms=1000)


@pytest.mark.parametrize(("event", "outside"), [(LONG, 106), (SHORT, 94)])
def test_directional_sor_does_not_reissue_a_consumed_breakout_after_cutover(
    event, outside
):
    from src.trading_kernel.domain.detector import detector_for
    from src.trading_kernel.domain.market import MarketSnapshot

    bars = (
        candle(0, 100),
        candle(1, outside, 106, 94),
        candle(2, 100),
        candle(3, outside, 106, 94),
    )
    result = detector_for(event).evaluate(
        MarketSnapshot(
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            trigger_candle_close_time_ms=D + 4 * H,
            candles_1h=bars,
        )
    )
    assert not result.triggered


@pytest.mark.parametrize(
    ("group", "event"), [("SOR-1H-LONG-001", LONG), ("SOR-1H-SHORT-001", SHORT)]
)
def test_static_bootstrap_manifest_targets_exactly_one_new_direction(group, event):
    from scripts.trading_kernel.bootstrap_strategy_universes import (
        _manifest_for_profile,
        _validate_static_manifest,
    )
    from src.trading_kernel.domain.orb_session_selection import ORB_STATIC_MEMBERS
    from src.trading_kernel.domain.strategy_registry import strategy_contract_for

    events, members = _manifest_for_profile("tiny-live-v1", strategy_group_id=group)
    assert events == ((strategy_contract_for(event).event_id, event),)
    assert members == ORB_STATIC_MEMBERS
    _validate_static_manifest("tiny-live-v1", strategy_group_id=group)
