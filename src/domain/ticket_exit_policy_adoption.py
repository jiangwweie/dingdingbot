"""Pure domain contract for adopting an exit policy onto an active Ticket."""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TicketExitPolicyAdoptionEligibilitySnapshot(BaseModel):
    """Immutable facts whose canonical digest guards preview/apply CAS."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_version: Literal["brc.ticket_exit_policy_adoption_eligibility.v1"] = Field(
        default="brc.ticket_exit_policy_adoption_eligibility.v1",
        alias="schema",
    )
    ticket_id: str = Field(min_length=1, max_length=192)
    ticket_created_at_ms: int = Field(ge=0)
    ticket_exit_policy_id: str = Field(min_length=1, max_length=192)
    ticket_exit_policy_version: str = Field(min_length=1, max_length=96)
    ticket_exit_policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    ticket_status: str = Field(min_length=1, max_length=64)
    lifecycle_state: str = Field(min_length=1, max_length=64)
    ticket_strategy_group_id: str = Field(min_length=1, max_length=128)
    ticket_strategy_version: str = Field(min_length=1, max_length=160)
    ticket_event_spec_id: str = Field(min_length=1, max_length=160)
    ticket_event_spec_version: str = Field(min_length=1, max_length=160)
    ticket_side: Literal["long", "short"]

    to_exit_policy_id: str = Field(min_length=1, max_length=192)
    to_exit_policy_version: str = Field(min_length=1, max_length=96)
    to_exit_policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_status: str = Field(min_length=1, max_length=32)
    policy_approved_at_ms: int = Field(ge=0)
    policy_strategy_group_id: str = Field(min_length=1, max_length=128)
    policy_strategy_version: str = Field(min_length=1, max_length=160)
    policy_event_spec_id: str = Field(min_length=1, max_length=160)
    policy_event_spec_version: str = Field(min_length=1, max_length=160)
    policy_side: Literal["long", "short"]

    owner_authorization_ref: str = Field(min_length=1, max_length=256)
    owner_authorization_ticket_id: str | None = Field(
        default=None,
        max_length=192,
    )
    runtime_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    migration_revision: int = Field(ge=0)

    account_id: str = Field(min_length=1, max_length=192)
    exchange_id: str = Field(min_length=1, max_length=64)
    exchange_instrument_id: str = Field(min_length=1, max_length=192)
    position_mode: Literal["one_way", "hedge"]
    position_side: Literal["BOTH", "LONG", "SHORT"]
    pg_position_qty: Decimal = Field(ge=0)
    exchange_position_qty: Decimal = Field(ge=0)
    entry_avg_fill_price: Decimal = Field(gt=0)
    minimum_price_tick: Decimal = Field(gt=0)
    quantity_step: Decimal = Field(gt=0)
    entry_fee_amount: Decimal = Field(ge=0)
    entry_fee_asset: str = Field(min_length=1, max_length=32)
    quote_asset: str = Field(min_length=1, max_length=32)
    fee_asset_quote_conversion_rate: Decimal | None = Field(default=None, gt=0)
    certified_exit_taker_fee_rate: Decimal = Field(ge=0, lt=1)

    exit_protection_set_id: str = Field(min_length=1, max_length=192)
    protection_state: str = Field(min_length=1, max_length=64)
    sl_order_id: str = Field(min_length=1, max_length=192)
    sl_order_type: str = Field(min_length=1, max_length=32)
    sl_qty: Decimal = Field(ge=0)
    sl_trigger_price: Decimal = Field(gt=0)
    sl_reduce_only: bool
    sl_side: Literal["buy", "sell"]
    sl_position_side: Literal["BOTH", "LONG", "SHORT"]
    tp1_order_id: str = Field(min_length=1, max_length=192)
    tp1_order_type: str = Field(min_length=1, max_length=32)
    tp1_qty: Decimal = Field(ge=0)
    tp1_price: Decimal = Field(gt=0)
    tp1_filled_qty: Decimal = Field(ge=0)
    tp1_reduce_only: bool
    tp1_market_fallback_allowed: bool
    tp1_side: Literal["buy", "sell"]
    tp1_position_side: Literal["BOTH", "LONG", "SHORT"]
    unsafe_command_count: int = Field(ge=0)
    evaluated_at_ms: int = Field(ge=0)


class TicketExitPolicyAdoptionEligibilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["eligible", "blocked"]
    blockers: tuple[str, ...]
    eligibility_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot: TicketExitPolicyAdoptionEligibilitySnapshot


def canonical_eligibility_hash(
    snapshot: TicketExitPolicyAdoptionEligibilitySnapshot,
) -> str:
    canonical = _canonical(snapshot.model_dump(mode="json", by_alias=True))
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def evaluate_ticket_exit_policy_adoption_snapshot(
    snapshot: TicketExitPolicyAdoptionEligibilitySnapshot,
) -> TicketExitPolicyAdoptionEligibilityResult:
    blockers: list[str] = []
    if snapshot.ticket_exit_policy_id != "legacy_unbound" or (
        snapshot.ticket_exit_policy_version != "legacy_unbound"
    ):
        blockers.append("adoption_ticket_not_legacy_unbound")
    if snapshot.ticket_status != "submitted":
        blockers.append("adoption_ticket_not_submitted")
    if snapshot.lifecycle_state != "position_protected":
        blockers.append("adoption_lifecycle_not_position_protected")
    if snapshot.policy_status != "current":
        blockers.append("adoption_policy_not_current")
    if (
        snapshot.policy_approved_at_ms > snapshot.ticket_created_at_ms
        and snapshot.owner_authorization_ticket_id != snapshot.ticket_id
    ):
        blockers.append("adoption_policy_approved_after_ticket")

    identity_pairs = (
        (
            snapshot.ticket_strategy_group_id,
            snapshot.policy_strategy_group_id,
            "adoption_strategy_group_mismatch",
        ),
        (
            snapshot.ticket_strategy_version,
            snapshot.policy_strategy_version,
            "adoption_strategy_version_mismatch",
        ),
        (
            snapshot.ticket_event_spec_id,
            snapshot.policy_event_spec_id,
            "adoption_event_spec_mismatch",
        ),
        (
            snapshot.ticket_event_spec_version,
            snapshot.policy_event_spec_version,
            "adoption_event_spec_version_mismatch",
        ),
        (
            snapshot.ticket_side,
            snapshot.policy_side,
            "adoption_side_mismatch",
        ),
    )
    for ticket_value, policy_value, blocker in identity_pairs:
        if ticket_value != policy_value:
            blockers.append(blocker)

    if snapshot.migration_revision < 125:
        blockers.append("adoption_migration_125_not_active")
    if snapshot.pg_position_qty <= 0 or snapshot.exchange_position_qty <= 0:
        blockers.append("adoption_position_not_active")
    if snapshot.pg_position_qty != snapshot.exchange_position_qty:
        blockers.append("adoption_position_quantity_mismatch")
    if (
        snapshot.entry_fee_asset.upper() != snapshot.quote_asset.upper()
        and snapshot.fee_asset_quote_conversion_rate is None
    ):
        blockers.append("adoption_entry_fee_conversion_missing")
    if snapshot.protection_state != "complete_reconciled":
        blockers.append("adoption_protection_not_reconciled")

    close_side = "sell" if snapshot.ticket_side == "long" else "buy"
    expected_position_side = (
        snapshot.ticket_side.upper()
        if snapshot.position_mode == "hedge"
        else "BOTH"
    )
    if snapshot.position_side != expected_position_side:
        blockers.append("adoption_position_side_mismatch")
    if snapshot.sl_order_type.upper() != "STOP_MARKET":
        blockers.append("adoption_sl_not_stop_market")
    if not snapshot.sl_reduce_only:
        blockers.append("adoption_sl_not_reduce_only")
    if snapshot.sl_qty != snapshot.exchange_position_qty:
        blockers.append("adoption_sl_quantity_mismatch")
    if snapshot.sl_side != close_side:
        blockers.append("adoption_sl_close_side_mismatch")
    if snapshot.sl_position_side != expected_position_side:
        blockers.append("adoption_sl_position_side_mismatch")

    if snapshot.tp1_order_type.upper() != "LIMIT":
        blockers.append("adoption_tp1_not_limit")
    if not snapshot.tp1_reduce_only:
        blockers.append("adoption_tp1_not_reduce_only")
    if snapshot.tp1_market_fallback_allowed:
        blockers.append("adoption_tp1_market_fallback_present")
    if snapshot.tp1_side != close_side:
        blockers.append("adoption_tp1_close_side_mismatch")
    if snapshot.tp1_position_side != expected_position_side:
        blockers.append("adoption_tp1_position_side_mismatch")
    if snapshot.tp1_qty > snapshot.exchange_position_qty:
        blockers.append("adoption_tp1_quantity_exceeds_position")
    if snapshot.tp1_filled_qty > snapshot.tp1_qty:
        blockers.append("adoption_tp1_fill_exceeds_target")
    if snapshot.unsafe_command_count:
        blockers.append("adoption_unsafe_command_pending")

    deduped = tuple(dict.fromkeys(blockers))
    return TicketExitPolicyAdoptionEligibilityResult(
        status="blocked" if deduped else "eligible",
        blockers=deduped,
        eligibility_hash=canonical_eligibility_hash(snapshot),
        snapshot=snapshot,
    )


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonical(child)
            for key, child in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list):
        return [_canonical(child) for child in value]
    return value
