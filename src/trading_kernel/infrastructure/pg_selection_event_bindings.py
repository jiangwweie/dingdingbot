"""Decode normalized current-schema Event grants into the SOR typed subtype."""

from pydantic import TypeAdapter

from src.trading_kernel.domain.instrument_selection import (
    SOR_LONG_EVENT_SPEC_ID,
    SOR_SHORT_EVENT_SPEC_ID,
)
from src.trading_kernel.domain.selection_authority import (
    AuthorityEventBinding,
    AuthorityEventRequirement,
    UniverseAuthorityPair,
    build_event_universe_set,
)


def sor_authority_pair_from_bindings(payload: object) -> UniverseAuthorityPair | None:
    bindings = TypeAdapter(tuple[AuthorityEventBinding, ...]).validate_python(payload)
    shape = build_event_universe_set(requirements=(
        AuthorityEventRequirement(event_spec_id=SOR_LONG_EVENT_SPEC_ID,position_side="long"),
        AuthorityEventRequirement(event_spec_id=SOR_SHORT_EVENT_SPEC_ID,position_side="short"),
    ), bindings=bindings)
    if not shape.is_trading:
        return None
    long_id = shape.binding_for(SOR_LONG_EVENT_SPEC_ID).universe_version_id
    short_id = shape.binding_for(SOR_SHORT_EVENT_SPEC_ID).universe_version_id
    if long_id is None or short_id is None:
        raise ValueError("SOR trading Event set lacks a Universe")
    return UniverseAuthorityPair(long_universe_version_id=long_id,short_universe_version_id=short_id)
