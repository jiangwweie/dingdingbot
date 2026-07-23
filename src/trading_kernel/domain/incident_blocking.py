"""Typed new-ENTRY Incident fences and canonical blocking identities."""

from __future__ import annotations

from enum import StrEnum


class EntryBlockScope(StrEnum):
    RUNTIME = "runtime"
    ACCOUNT_CAPACITY = "account_capacity"
    LEVERAGE_DOMAIN = "leverage_domain"
    NONE = "none"


def canonical_entry_block_key(
    scope: EntryBlockScope,
    *,
    venue_id: str,
    account_id: str,
    exchange_instrument_id: str | None = None,
) -> str | None:
    """Build the only legal key for one typed new-ENTRY blocking scope."""

    if scope is EntryBlockScope.RUNTIME:
        return "global"
    if scope is EntryBlockScope.NONE:
        return None
    if not venue_id or not account_id:
        raise ValueError("entry block keys require venue and account identity")
    if scope is EntryBlockScope.ACCOUNT_CAPACITY:
        return f"{venue_id}:{account_id}"
    if not exchange_instrument_id:
        raise ValueError("leverage-domain block keys require instrument identity")
    return f"{venue_id}:{account_id}:{exchange_instrument_id}"
