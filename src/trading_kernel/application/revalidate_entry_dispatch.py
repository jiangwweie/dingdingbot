"""Pure fresh revalidation immediately before a new-entry venue mutation."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.ports import (
    OwnerPolicySnapshot,
    RuntimeCapabilitySnapshot,
    RuntimeScopeSnapshot,
)
from src.trading_kernel.application.runtime_facts import InstrumentRulesFacts
from src.trading_kernel.domain.account_entry_health import (
    AccountEntryHealth,
    AccountEntryHealthStatus,
)
from src.trading_kernel.domain.capacity import CapacityClaim
from src.trading_kernel.domain.capacity_sizing import MaintenanceMarginBracket
from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
    SetLeverageCommandPayload,
)
from src.trading_kernel.domain.entry_admission_snapshot import EntryAdmissionSnapshot
from src.trading_kernel.domain.instrument_entry_health import (
    InstrumentEntryHealth,
    InstrumentEntryHealthStatus,
)
from src.trading_kernel.domain.ticket import TradeTicket


class EntryDispatchPreflightStatus(StrEnum):
    ALLOWED = "allowed"
    COMMAND_MISMATCH = "command_mismatch"
    DEADLINE_EXPIRED = "deadline_expired"
    POLICY_DRIFT = "policy_drift"
    NEW_ENTRY_DISABLED = "new_entry_disabled"
    SCOPE_DRIFT = "scope_drift"
    RUNTIME_FENCED = "runtime_fenced"
    STALE_SNAPSHOT = "stale_snapshot"
    ACCOUNT_MODE_INVALID = "account_mode_invalid"
    INCIDENT_FENCED = "incident_fenced"
    OWNERSHIP_CONFLICT = "ownership_conflict"
    WALLET_RISK_DRIFT = "wallet_risk_drift"
    MARGIN_DRIFT = "margin_drift"
    QUOTE_RISK = "quote_risk"
    LIQUIDATION_FAILED = "liquidation_failed"
    LEVERAGE_MISMATCH = "leverage_mismatch"
    SET_LEVERAGE_INSTRUMENT_NOT_FLAT = "set_leverage_instrument_not_flat"


class EntryDispatchPreflightRequest(BaseModel):
    """All immutable and current facts needed for one fresh write decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    command: ExchangeCommand
    ticket: TradeTicket
    capacity_claim: CapacityClaim
    owner_policy: OwnerPolicySnapshot | None
    runtime_scope: RuntimeScopeSnapshot | None
    runtime_capability: RuntimeCapabilitySnapshot | None
    runtime_commit: str
    schema_revision: str
    admission_snapshot: EntryAdmissionSnapshot
    instrument_rules: InstrumentRulesFacts
    account_entry_health: AccountEntryHealth
    instrument_entry_health: InstrumentEntryHealth
    now_ms: int

    @field_validator("runtime_commit", "schema_revision", mode="before")
    @classmethod
    def _require_runtime_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("dispatch runtime identity must be non-blank")
        return normalized

    @field_validator("now_ms")
    @classmethod
    def _require_now(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("dispatch preflight time must be positive")
        return value


class EntryDispatchPreflightDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: EntryDispatchPreflightStatus

    @property
    def allowed(self) -> bool:
        return self.status is EntryDispatchPreflightStatus.ALLOWED


def revalidate_entry_dispatch(
    request: EntryDispatchPreflightRequest,
) -> EntryDispatchPreflightDecision:
    """Fail closed without resizing or repricing a frozen Ticket."""

    command = request.command
    ticket = request.ticket
    claim = request.capacity_claim
    snapshot = request.admission_snapshot
    domain = ticket.identity.netting_domain

    if not _command_matches_ticket_and_claim(command, ticket, claim):
        return _refused(EntryDispatchPreflightStatus.COMMAND_MISMATCH)
    if request.now_ms >= command.deadline_at_ms or request.now_ms >= claim.expires_at_ms:
        return _refused(EntryDispatchPreflightStatus.DEADLINE_EXPIRED)
    if not _policy_matches(request.owner_policy, ticket):
        return _refused(EntryDispatchPreflightStatus.POLICY_DRIFT)
    assert request.owner_policy is not None
    if not request.owner_policy.new_entry_submit_enabled:
        return _refused(EntryDispatchPreflightStatus.NEW_ENTRY_DISABLED)
    if not _scope_matches(request.runtime_scope, ticket):
        return _refused(EntryDispatchPreflightStatus.SCOPE_DRIFT)
    if not _runtime_is_certified(
        request.runtime_capability,
        runtime_commit=request.runtime_commit,
        schema_revision=request.schema_revision,
    ):
        return _refused(EntryDispatchPreflightStatus.RUNTIME_FENCED)
    if not _snapshot_and_rules_are_current(request):
        return _refused(EntryDispatchPreflightStatus.STALE_SNAPSHOT)
    if (
        snapshot.venue_id != domain.venue_id
        or snapshot.account_id != domain.account_id
        or snapshot.position_mode != "independent_sides"
        or snapshot.margin_mode != request.owner_policy.supported_margin_mode
    ):
        return _refused(EntryDispatchPreflightStatus.ACCOUNT_MODE_INVALID)
    if not _health_digest_matches(request):
        return _refused(EntryDispatchPreflightStatus.STALE_SNAPSHOT)
    if request.account_entry_health.status is not AccountEntryHealthStatus.HEALTHY:
        return _refused(
            EntryDispatchPreflightStatus.INCIDENT_FENCED
            if request.account_entry_health.entry_block_scope.value != "none"
            else EntryDispatchPreflightStatus.OWNERSHIP_CONFLICT
        )
    if request.instrument_entry_health.status not in {
        InstrumentEntryHealthStatus.HEALTHY_FLAT,
        InstrumentEntryHealthStatus.HEALTHY_OPPOSITE_SIDE,
    }:
        return _refused(
            EntryDispatchPreflightStatus.INCIDENT_FENCED
            if request.instrument_entry_health.entry_block_scope.value != "none"
            else EntryDispatchPreflightStatus.OWNERSHIP_CONFLICT
        )
    if not _netting_domain_is_flat_and_order_free(snapshot, ticket):
        return _refused(EntryDispatchPreflightStatus.OWNERSHIP_CONFLICT)
    if ticket.risk_at_stop > (
        snapshot.total_wallet_balance
        * request.owner_policy.planned_stop_risk_fraction
    ):
        return _refused(EntryDispatchPreflightStatus.WALLET_RISK_DRIFT)
    executable_margin = min(
        snapshot.available_margin,
        max(
            snapshot.total_margin_balance
            * request.owner_policy.max_initial_margin_utilization
            - snapshot.total_initial_margin,
            Decimal("0"),
        ),
    )
    if ticket.reserved_margin > executable_margin:
        return _refused(EntryDispatchPreflightStatus.MARGIN_DRIFT)
    entry_price = (
        snapshot.best_ask_price
        if domain.position_side == "long"
        else snapshot.best_bid_price
    )
    if not _quote_preserves_protection(ticket, entry_price):
        return _refused(EntryDispatchPreflightStatus.QUOTE_RISK)
    if (
        ticket.quantity * abs(entry_price - ticket.initial_stop_price)
        > ticket.post_fill_stop_risk_limit
    ):
        return _refused(EntryDispatchPreflightStatus.QUOTE_RISK)
    if not _liquidation_safety_passes(
        ticket=ticket,
        snapshot=snapshot,
        brackets=request.instrument_rules.maintenance_margin_brackets,
    ):
        return _refused(EntryDispatchPreflightStatus.LIQUIDATION_FAILED)

    facts = snapshot.instrument_facts_for(domain.exchange_instrument_id)
    if command.kind is ExchangeCommandKind.SET_LEVERAGE:
        if not _exact_instrument_is_flat_and_order_free(snapshot, ticket):
            return _refused(
                EntryDispatchPreflightStatus.SET_LEVERAGE_INSTRUMENT_NOT_FLAT
            )
        return _allowed()
    if facts.configured_leverage != ticket.selected_leverage:
        return _refused(EntryDispatchPreflightStatus.LEVERAGE_MISMATCH)
    return _allowed()


def _command_matches_ticket_and_claim(
    command: ExchangeCommand,
    ticket: TradeTicket,
    claim: CapacityClaim,
) -> bool:
    if command.kind not in {
        ExchangeCommandKind.SET_LEVERAGE,
        ExchangeCommandKind.ENTRY,
    }:
        return False
    if command.status is not ExchangeCommandStatus.CLAIMED or command.generation != 1:
        return False
    if command.ticket_identity != ticket.identity or claim.to_ticket() != ticket:
        return False
    if ticket.capacity_claim_id != claim.capacity_claim_id:
        return False
    if command.kind is ExchangeCommandKind.SET_LEVERAGE:
        return (
            isinstance(command.payload, SetLeverageCommandPayload)
            and command.payload.desired_leverage == ticket.selected_leverage
            and command.payload.owner_policy_version == ticket.owner_policy_version
        )
    return (
        isinstance(command.payload, OrderCommandPayload)
        and command.payload.required_configured_leverage == ticket.selected_leverage
    )


def _policy_matches(
    policy: OwnerPolicySnapshot | None,
    ticket: TradeTicket,
) -> bool:
    return bool(
        policy
        and policy.owner_policy_id == ticket.owner_policy_id
        and policy.policy_version == ticket.owner_policy_version
        and policy.enabled
        and ticket.selected_leverage <= policy.max_leverage
        and ticket.margin_mode == policy.supported_margin_mode
    )


def _scope_matches(
    scope: RuntimeScopeSnapshot | None,
    ticket: TradeTicket,
) -> bool:
    if scope is None or not scope.enabled:
        return False
    identity = ticket.identity
    return (
        scope.runtime_scope_id == ticket.runtime_scope_id
        and scope.scope_version == ticket.runtime_scope_version
        and scope.strategy_group_id == identity.runtime.strategy_group_id
        and scope.strategy_version_id == identity.runtime.strategy_version_id
        and scope.event_spec_id == identity.runtime.event_spec_id
        and scope.runtime_profile_id == identity.runtime.runtime_profile_id
        and scope.owner_policy_id == ticket.owner_policy_id
        and scope.exchange_instrument_id == identity.netting_domain.exchange_instrument_id
        and scope.position_side == identity.netting_domain.position_side
    )


def _runtime_is_certified(
    capability: RuntimeCapabilitySnapshot | None,
    *,
    runtime_commit: str,
    schema_revision: str,
) -> bool:
    return bool(
        capability
        and capability.capability_key == "exchange_commands"
        and capability.enabled
        and capability.certified_commit == runtime_commit
        and capability.schema_revision == schema_revision
    )


def _snapshot_and_rules_are_current(
    request: EntryDispatchPreflightRequest,
) -> bool:
    snapshot = request.admission_snapshot
    rules = request.instrument_rules
    domain = request.ticket.identity.netting_domain
    return (
        snapshot.observed_at_ms <= request.now_ms < snapshot.valid_until_ms
        and rules.exchange_instrument_id == domain.exchange_instrument_id
        and rules.observed_at_ms <= request.now_ms < rules.valid_until_ms
        and request.ticket.selected_leverage <= rules.exchange_max_leverage
    )


def _health_digest_matches(request: EntryDispatchPreflightRequest) -> bool:
    digest = request.admission_snapshot.digest()
    return (
        request.account_entry_health.entry_admission_snapshot_digest == digest
        and request.instrument_entry_health.entry_admission_snapshot_digest == digest
    )


def _netting_domain_is_flat_and_order_free(
    snapshot: EntryAdmissionSnapshot,
    ticket: TradeTicket,
) -> bool:
    domain = ticket.identity.netting_domain
    return not any(
        position.exchange_instrument_id == domain.exchange_instrument_id
        and position.position_side == domain.position_side
        and position.quantity > 0
        for position in snapshot.positions
    ) and not any(
        order.exchange_instrument_id == domain.exchange_instrument_id
        and order.position_side == domain.position_side
        for order in snapshot.open_orders
    )


def _exact_instrument_is_flat_and_order_free(
    snapshot: EntryAdmissionSnapshot,
    ticket: TradeTicket,
) -> bool:
    instrument_id = ticket.identity.netting_domain.exchange_instrument_id
    return not any(
        position.exchange_instrument_id == instrument_id and position.quantity > 0
        for position in snapshot.positions
    ) and not any(
        order.exchange_instrument_id == instrument_id for order in snapshot.open_orders
    )


def _quote_preserves_protection(ticket: TradeTicket, entry_price: Decimal) -> bool:
    if ticket.identity.netting_domain.position_side == "long":
        return ticket.initial_stop_price < entry_price
    return ticket.initial_stop_price > entry_price


def _liquidation_safety_passes(
    *,
    ticket: TradeTicket,
    snapshot: EntryAdmissionSnapshot,
    brackets: tuple[MaintenanceMarginBracket, ...],
) -> bool:
    bracket = _bracket_for_notional(brackets, ticket.notional)
    if bracket is None:
        return False
    mark_price = snapshot.instrument_facts_for(
        ticket.identity.netting_domain.exchange_instrument_id
    ).mark_price
    maintenance_at_liquidation = (
        ticket.quantity * entry_price_for(ticket, snapshot) * bracket.maintenance_margin_rate
        + bracket.maintenance_amount
    )
    if ticket.identity.netting_domain.position_side == "long":
        denominator = ticket.quantity * (Decimal("1") - bracket.maintenance_margin_rate)
        if denominator <= 0:
            return False
        liquidation_price = max(
            (
                snapshot.total_maintenance_margin
                + maintenance_at_liquidation
                - snapshot.total_margin_balance
                + ticket.quantity * mark_price
            )
            / denominator,
            Decimal("0"),
        )
        directional = liquidation_price < ticket.initial_stop_price < entry_price_for(
            ticket, snapshot
        )
        liquidation_distance = ticket.initial_stop_price - liquidation_price
    else:
        denominator = ticket.quantity * (Decimal("1") + bracket.maintenance_margin_rate)
        if denominator <= 0:
            return False
        liquidation_price = (
            snapshot.total_margin_balance
            + ticket.quantity * mark_price
            - snapshot.total_maintenance_margin
            - maintenance_at_liquidation
        ) / denominator
        directional = (
            liquidation_price.is_finite()
            and liquidation_price > 0
            and entry_price_for(ticket, snapshot) < ticket.initial_stop_price < liquidation_price
        )
        liquidation_distance = liquidation_price - ticket.initial_stop_price
    stop_distance = abs(entry_price_for(ticket, snapshot) - ticket.initial_stop_price)
    return bool(
        directional
        and liquidation_distance >= 0
        and stop_distance > 0
        and liquidation_distance / stop_distance
        >= ticket.min_liquidation_distance_to_stop_distance_ratio
    )


def entry_price_for(ticket: TradeTicket, snapshot: EntryAdmissionSnapshot) -> Decimal:
    return (
        snapshot.best_ask_price
        if ticket.identity.netting_domain.position_side == "long"
        else snapshot.best_bid_price
    )


def _bracket_for_notional(
    brackets: tuple[MaintenanceMarginBracket, ...],
    notional: Decimal,
) -> MaintenanceMarginBracket | None:
    matches = tuple(
        bracket
        for bracket in brackets
        if notional >= bracket.notional_floor
        and (bracket.notional_cap is None or notional < bracket.notional_cap)
    )
    return matches[0] if len(matches) == 1 else None


def _allowed() -> EntryDispatchPreflightDecision:
    return EntryDispatchPreflightDecision(status=EntryDispatchPreflightStatus.ALLOWED)


def _refused(status: EntryDispatchPreflightStatus) -> EntryDispatchPreflightDecision:
    return EntryDispatchPreflightDecision(status=status)
