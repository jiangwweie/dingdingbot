"""Pure exact-instrument ownership and leverage classification for admission."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

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


class InstrumentEntryHealthStatus(StrEnum):
    HEALTHY_FLAT = "healthy_flat"
    HEALTHY_OPPOSITE_SIDE = "healthy_opposite_side"
    SAME_DIRECTION_OCCUPIED = "same_direction_occupied"
    RUNTIME_FENCED = "runtime_fenced"
    UNKNOWN_COMMAND_OUTCOME = "unknown_command_outcome"
    UNOWNED_POSITION = "unowned_position"
    UNOWNED_ORDER = "unowned_order"
    OWNED_RESIDUAL_ORDER = "owned_residual_order"
    LEVERAGE_DOMAIN_INCIDENT = "leverage_domain_incident"


class InstrumentEntryHealth(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: InstrumentEntryHealthStatus
    configured_leverage: int
    leverage_change_allowed: bool
    entry_block_scope: EntryBlockScope
    entry_block_key: str | None
    entry_admission_snapshot_digest: str
    decision_digest: str


def classify_instrument_entry_health(
    snapshot: EntryAdmissionSnapshot,
    ownership: AdmissionOwnership,
    *,
    exchange_instrument_id: str,
    requested_position_side: Literal["long", "short"],
) -> InstrumentEntryHealth:
    """Classify one requested instrument from the same frozen account snapshot."""

    risk_snapshot = snapshot.account_risk_snapshot
    if risk_snapshot.exchange_instrument_id != exchange_instrument_id:
        raise ValueError("admission account risk instrument identity mismatch")
    configured_leverage = risk_snapshot.configured_leverage
    exact_positions = tuple(
        position
        for position in risk_snapshot.account_positions
        if position.exchange_instrument_id == exchange_instrument_id
    )
    exact_orders = tuple(
        order
        for order in snapshot.open_orders
        if order.exchange_instrument_id == exchange_instrument_id
    )
    if EntryBlockScope.RUNTIME in ownership.open_incident_scopes:
        return _health(
            snapshot,
            configured_leverage,
            InstrumentEntryHealthStatus.RUNTIME_FENCED,
            False,
            EntryBlockScope.RUNTIME,
            exchange_instrument_id,
        )
    if ownership.unknown_command_outcome_ticket_ids:
        return _health(
            snapshot,
            configured_leverage,
            InstrumentEntryHealthStatus.UNKNOWN_COMMAND_OUTCOME,
            False,
            EntryBlockScope.ACCOUNT_CAPACITY,
            exchange_instrument_id,
        )
    if EntryBlockScope.LEVERAGE_DOMAIN in ownership.open_incident_scopes:
        return _health(
            snapshot,
            configured_leverage,
            InstrumentEntryHealthStatus.LEVERAGE_DOMAIN_INCIDENT,
            False,
            EntryBlockScope.LEVERAGE_DOMAIN,
            exchange_instrument_id,
        )
    if any(
        position.quantity > 0
        and snapshot.position_domain_key(position)
        not in ownership.owned_position_domain_keys
        for position in exact_positions
    ):
        return _health(
            snapshot,
            configured_leverage,
            InstrumentEntryHealthStatus.UNOWNED_POSITION,
            False,
            EntryBlockScope.ACCOUNT_CAPACITY,
            exchange_instrument_id,
        )
    if any(
        order.exchange_order_id not in ownership.owned_exchange_order_ids
        for order in exact_orders
    ):
        return _health(
            snapshot,
            configured_leverage,
            InstrumentEntryHealthStatus.UNOWNED_ORDER,
            False,
            EntryBlockScope.ACCOUNT_CAPACITY,
            exchange_instrument_id,
        )
    if any(
        position.quantity > 0 and position.position_side == requested_position_side
        for position in exact_positions
    ):
        return _health(
            snapshot,
            configured_leverage,
            InstrumentEntryHealthStatus.SAME_DIRECTION_OCCUPIED,
            False,
            EntryBlockScope.NONE,
            exchange_instrument_id,
        )
    has_exact_position = any(position.quantity > 0 for position in exact_positions)
    if exact_orders and not has_exact_position:
        return _health(
            snapshot,
            configured_leverage,
            InstrumentEntryHealthStatus.OWNED_RESIDUAL_ORDER,
            False,
            EntryBlockScope.LEVERAGE_DOMAIN,
            exchange_instrument_id,
        )
    if has_exact_position:
        return _health(
            snapshot,
            configured_leverage,
            InstrumentEntryHealthStatus.HEALTHY_OPPOSITE_SIDE,
            False,
            EntryBlockScope.NONE,
            exchange_instrument_id,
        )
    return _health(
        snapshot,
        configured_leverage,
        InstrumentEntryHealthStatus.HEALTHY_FLAT,
        True,
        EntryBlockScope.NONE,
        exchange_instrument_id,
    )


def _health(
    snapshot: EntryAdmissionSnapshot,
    configured_leverage: int,
    status: InstrumentEntryHealthStatus,
    leverage_change_allowed: bool,
    scope: EntryBlockScope,
    exchange_instrument_id: str,
) -> InstrumentEntryHealth:
    snapshot_digest = snapshot.digest()
    block_key = canonical_entry_block_key(
        scope,
        venue_id=snapshot.account_risk_snapshot.venue_id,
        account_id=snapshot.account_risk_snapshot.account_id,
        exchange_instrument_id=exchange_instrument_id,
    )
    return InstrumentEntryHealth(
        status=status,
        configured_leverage=configured_leverage,
        leverage_change_allowed=leverage_change_allowed,
        entry_block_scope=scope,
        entry_block_key=block_key,
        entry_admission_snapshot_digest=snapshot_digest,
        decision_digest=canonical_digest(
            {
                "status": status,
                "configured_leverage": configured_leverage,
                "leverage_change_allowed": leverage_change_allowed,
                "entry_block_scope": scope,
                "entry_block_key": block_key,
                "entry_admission_snapshot_digest": snapshot_digest,
            }
        ),
    )
