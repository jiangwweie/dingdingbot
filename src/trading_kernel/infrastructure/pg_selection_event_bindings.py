"""Decode normalized current-schema Event grants into the SOR typed subtype."""

from pydantic import TypeAdapter

from src.trading_kernel.domain.selection_authority import (
    AuthorityEventBinding,
    AuthorityEventRequirement,
    UniverseAuthorityPair,
    build_event_universe_set,
)
from src.trading_kernel.domain.strategy_registry import strategy_contract_for


def sor_authority_pair_from_bindings(
    payload: object, *, selection_spec_id: str = "sor-dynamic-selection-v0"
) -> UniverseAuthorityPair | None:
    from src.trading_kernel.domain.orb_session_selection import daily_event_spec_ids

    events = tuple(strategy_contract_for(event) for event in daily_event_spec_ids(selection_spec_id))
    bindings = TypeAdapter(tuple[AuthorityEventBinding, ...]).validate_python(payload)
    shape = build_event_universe_set(
        requirements=tuple(
            AuthorityEventRequirement(event_spec_id=event.event_spec_id, position_side=event.position_side)
            for event in events
        ),
        bindings=bindings,
    )
    if not shape.is_trading:
        return None
    universes = {
        event.position_side: shape.binding_for(event.event_spec_id).universe_version_id
        for event in events
    }
    return UniverseAuthorityPair(
        long_universe_version_id=universes.get("long"),
        short_universe_version_id=universes.get("short"),
    )
