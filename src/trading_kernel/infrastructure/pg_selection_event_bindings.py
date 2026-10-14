"""Decode normalized current-schema Event grants into the SOR typed subtype."""

from pydantic import TypeAdapter

from src.trading_kernel.domain.selection_authority import (
    AuthorityEventBinding,
    AuthorityEventRequirement,
    UniverseAuthorityPair,
    build_event_universe_set,
)


def sor_authority_pair_from_bindings(
    payload: object, *, selection_spec_id: str = "sor-dynamic-selection-v0"
) -> UniverseAuthorityPair | None:
    from src.trading_kernel.domain.orb_session_selection import daily_event_spec_ids

    long_event, short_event = daily_event_spec_ids(selection_spec_id)
    bindings = TypeAdapter(tuple[AuthorityEventBinding, ...]).validate_python(payload)
    shape = build_event_universe_set(
        requirements=(
            AuthorityEventRequirement(event_spec_id=long_event, position_side="long"),
            AuthorityEventRequirement(event_spec_id=short_event, position_side="short"),
        ),
        bindings=bindings,
    )
    if not shape.is_trading:
        return None
    long_id = shape.binding_for(long_event).universe_version_id
    short_id = shape.binding_for(short_event).universe_version_id
    if long_id is None or short_id is None:
        raise ValueError("SOR trading Event set lacks a Universe")
    return UniverseAuthorityPair(
        long_universe_version_id=long_id, short_universe_version_id=short_id
    )
