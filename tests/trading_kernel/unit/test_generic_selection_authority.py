from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.selection_authority import (
    AuthorityEventBinding,
    AuthorityEventGrantState,
    AuthorityEventRequirement,
    AuthorityEventSetError,
    build_event_universe_set,
    selected_member_set_digest,
    trusted_universe_membership_policy,
)
from src.trading_kernel.domain.strategy_universe import StrategyUniverseSourceKind

CPM_EVENT = "event_spec:CPM-RO-001:CPM-LONG:v3"
BRF2_EVENT = "event_spec:BRF2-001:BRF2-SHORT:v3"
SOR_LONG = "event_spec:SOR-001:SOR-LONG:v4"
SOR_SHORT = "event_spec:SOR-001:SOR-SHORT:v4"


def test_single_event_active_authority_has_one_real_universe() -> None:
    event_set = build_event_universe_set(
        requirements=(AuthorityEventRequirement(event_spec_id=CPM_EVENT, position_side="long"),),
        bindings=(
            AuthorityEventBinding(
                event_spec_id=CPM_EVENT,
                position_side="long",
                grant_state=AuthorityEventGrantState.ACTIVE,
                universe_version_id="universe:CPM:1",
                member_set_digest=selected_member_set_digest(
                    ("binance-usdm:BTCUSDT:perpetual",)
                ),
            ),
        ),
    )

    assert event_set.is_trading is True
    assert event_set.binding_for(CPM_EVENT).universe_version_id == "universe:CPM:1"


def test_valid_empty_has_full_spec_event_shape_without_zero_member_universe() -> None:
    event_set = build_event_universe_set(
        requirements=(
            AuthorityEventRequirement(event_spec_id=SOR_LONG, position_side="long"),
            AuthorityEventRequirement(event_spec_id=SOR_SHORT, position_side="short"),
        ),
        bindings=(
            AuthorityEventBinding.empty(event_spec_id=SOR_LONG, position_side="long"),
            AuthorityEventBinding.empty(event_spec_id=SOR_SHORT, position_side="short"),
        ),
    )

    assert event_set.is_trading is False
    assert len(event_set.bindings) == 2
    assert all(item.universe_version_id is None for item in event_set.bindings)
    assert all(
        item.member_set_digest == selected_member_set_digest(())
        for item in event_set.bindings
    )


def test_event_set_rejects_mixed_active_and_empty_sor_legs() -> None:
    requirements = (
        AuthorityEventRequirement(event_spec_id=SOR_LONG, position_side="long"),
        AuthorityEventRequirement(event_spec_id=SOR_SHORT, position_side="short"),
    )
    bindings = (
        AuthorityEventBinding(
            event_spec_id=SOR_LONG,
            position_side="long",
            grant_state=AuthorityEventGrantState.ACTIVE,
            universe_version_id="universe:SOR-LONG:1",
            member_set_digest=selected_member_set_digest(
                ("binance-usdm:BTCUSDT:perpetual",)
            ),
        ),
        AuthorityEventBinding.empty(event_spec_id=SOR_SHORT, position_side="short"),
    )

    with pytest.raises(AuthorityEventSetError, match="all ACTIVE or all EMPTY"):
        build_event_universe_set(requirements=requirements, bindings=bindings)


def test_empty_binding_rejects_non_null_universe_or_nonempty_digest() -> None:
    with pytest.raises(ValidationError, match="EMPTY"):
        AuthorityEventBinding(
            event_spec_id=BRF2_EVENT,
            position_side="short",
            grant_state=AuthorityEventGrantState.EMPTY,
            universe_version_id="universe:BRF2:1",
            member_set_digest=selected_member_set_digest(()),
        )
    with pytest.raises(ValidationError, match="empty digest"):
        AuthorityEventBinding(
            event_spec_id=BRF2_EVENT,
            position_side="short",
            grant_state=AuthorityEventGrantState.EMPTY,
            universe_version_id=None,
            member_set_digest=selected_member_set_digest(
                ("binance-usdm:BTCUSDT:perpetual",)
            ),
        )


@pytest.mark.parametrize(
    ("source_kind", "strategy_group_id", "event_spec_id", "allowed", "rejected"),
    (
        (StrategyUniverseSourceKind.MANUAL, "CPM-RO-001", CPM_EVENT, 10, 11),
        (StrategyUniverseSourceKind.DYNAMIC_SELECTION, "SOR-001", SOR_LONG, 7, 8),
        (StrategyUniverseSourceKind.DYNAMIC_SELECTION, "CPM-RO-001", CPM_EVENT, 16, 17),
    ),
)
def test_trusted_universe_membership_policy_owns_strategy_limit(
    source_kind: StrategyUniverseSourceKind,
    strategy_group_id: str,
    event_spec_id: str,
    allowed: int,
    rejected: int,
) -> None:
    policy = trusted_universe_membership_policy(
        source_kind=source_kind,
        strategy_group_id=strategy_group_id,
        event_spec_id=event_spec_id,
    )

    policy.require_member_count(allowed)
    with pytest.raises(AuthorityEventSetError, match="member limit"):
        policy.require_member_count(rejected)


def test_trusted_policy_has_no_caller_supplied_maximum() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        trusted_universe_membership_policy(
            source_kind=StrategyUniverseSourceKind.DYNAMIC_SELECTION,
            strategy_group_id="CPM-RO-001",
            event_spec_id=CPM_EVENT,
        ).model_validate(
            {
                "source_kind": "dynamic_selection",
                "strategy_group_id": "CPM-RO-001",
                "event_spec_id": CPM_EVENT,
                "max_members": 999,
            }
        )
