"""Current Owner standing authorization references.

These constants identify the development-stage standing authorization that lets
the runtime advance inside the selected StrategyGroup and risk boundary without
fresh per-event chat confirmation. They do not authorize FinalGate bypass,
Operation Layer bypass, withdrawal, transfer, credential mutation, live profile
mutation, order-sizing default expansion, or runtime-boundary expansion.
"""

from __future__ import annotations


OWNER_STANDING_AUTHORIZATION_REFERENCE = (
    "owner-standing-authorization:strategygroup-runtime-pilot:2026-06-14"
)
OWNER_STANDING_AUTHORIZATION_OPERATOR_ID = "owner-standing-authorization"
OWNER_STANDING_AUTHORIZATION_REASON = (
    "Owner standing authorization for development-stage StrategyGroup runtime "
    "advancement inside the selected runtime and risk boundary"
)


def standing_authorization_metadata(*, scope: str) -> dict[str, str]:
    return {
        "standing_authorization_reference": OWNER_STANDING_AUTHORIZATION_REFERENCE,
        "standing_authorization_scope": scope,
        "standing_authorization_reason": OWNER_STANDING_AUTHORIZATION_REASON,
    }
