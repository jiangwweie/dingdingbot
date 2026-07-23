"""Pure Cross-account ownership classification for new-ENTRY admission."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from src.trading_kernel.domain.entry_admission_snapshot import (
    AdmissionOwnership,
    EntryAdmissionSnapshot,
    canonical_digest,
)
from src.trading_kernel.domain.incident_blocking import (
    EntryBlockScope,
    canonical_entry_block_key,
)


class AccountEntryHealthStatus(StrEnum):
    HEALTHY = "healthy"
    RUNTIME_FENCED = "runtime_fenced"
    ACCOUNT_INCIDENT = "account_incident"
    UNKNOWN_COMMAND_OUTCOME = "unknown_command_outcome"
    UNOWNED_POSITION = "unowned_position"
    UNOWNED_ORDER = "unowned_order"


class AccountEntryHealth(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: AccountEntryHealthStatus
    entry_block_scope: EntryBlockScope
    entry_block_key: str | None
    entry_admission_snapshot_digest: str
    decision_digest: str


def classify_account_entry_health(
    snapshot: EntryAdmissionSnapshot,
    ownership: AdmissionOwnership,
) -> AccountEntryHealth:
    """Classify all account exposure without independently reading venue truth."""

    if EntryBlockScope.RUNTIME in ownership.open_incident_scopes:
        return _health(snapshot, AccountEntryHealthStatus.RUNTIME_FENCED, EntryBlockScope.RUNTIME)
    if ownership.unknown_command_outcome_ticket_ids:
        return _health(
            snapshot,
            AccountEntryHealthStatus.UNKNOWN_COMMAND_OUTCOME,
            EntryBlockScope.ACCOUNT_CAPACITY,
        )
    if EntryBlockScope.ACCOUNT_CAPACITY in ownership.open_incident_scopes:
        return _health(
            snapshot,
            AccountEntryHealthStatus.ACCOUNT_INCIDENT,
            EntryBlockScope.ACCOUNT_CAPACITY,
        )
    if any(
        position.quantity > 0
        and snapshot.position_domain_key(position)
        not in ownership.owned_position_domain_keys
        for position in snapshot.positions
    ):
        return _health(
            snapshot,
            AccountEntryHealthStatus.UNOWNED_POSITION,
            EntryBlockScope.ACCOUNT_CAPACITY,
        )
    if any(
        order.exchange_order_id not in ownership.owned_exchange_order_ids
        for order in snapshot.open_orders
    ):
        return _health(
            snapshot,
            AccountEntryHealthStatus.UNOWNED_ORDER,
            EntryBlockScope.ACCOUNT_CAPACITY,
        )
    return _health(snapshot, AccountEntryHealthStatus.HEALTHY, EntryBlockScope.NONE)


def _health(
    snapshot: EntryAdmissionSnapshot,
    status: AccountEntryHealthStatus,
    scope: EntryBlockScope,
) -> AccountEntryHealth:
    snapshot_digest = snapshot.digest()
    block_key = canonical_entry_block_key(
        scope,
        venue_id=snapshot.venue_id,
        account_id=snapshot.account_id,
    )
    payload = {
        "status": status,
        "entry_block_scope": scope,
        "entry_block_key": block_key,
        "entry_admission_snapshot_digest": snapshot_digest,
    }
    return AccountEntryHealth(
        **payload,
        decision_digest=canonical_digest(payload),
    )
