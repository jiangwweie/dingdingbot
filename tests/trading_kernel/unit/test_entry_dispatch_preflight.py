"""Pure dispatch-time safety revalidation for new-entry venue mutations."""

from __future__ import annotations

from decimal import Decimal

from src.trading_kernel.application.ports import (
    EventSpecSnapshot,
    OwnerPolicySnapshot,
    RuntimeCapabilitySnapshot,
    RuntimeScopeSnapshot,
    StrategyGroupSnapshot,
    StrategyVersionSnapshot,
)
from src.trading_kernel.application.runtime_facts import InstrumentRulesFacts
from src.trading_kernel.application.revalidate_entry_dispatch import (
    EntryDispatchPreflightRequest,
    EntryDispatchPreflightStatus,
    revalidate_entry_dispatch,
)
from src.trading_kernel.domain.account_entry_health import (
    classify_account_entry_health,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommand,
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
    build_command_id,
    build_venue_client_order_id,
)
from src.trading_kernel.domain.entry_admission_snapshot import AdmissionOwnership
from src.trading_kernel.domain.instrument_entry_health import (
    classify_instrument_entry_health,
)
from tests.trading_kernel.unit.test_capacity import (
    _long_signal,
    _policy,
    _rules,
    _snapshot,
)
from src.trading_kernel.application.build_capacity_claim import build_capacity_claim
from src.trading_kernel.domain.capacity import CapacityUsage
from src.trading_kernel.domain.ticket import EntryOrderType


def test_entry_preflight_refuses_when_frozen_margin_no_longer_fits() -> None:
    request = _preflight_request(
        snapshot=_snapshot().model_copy(update={"available_margin": Decimal("4")})
    )

    decision = revalidate_entry_dispatch(request)

    assert decision.status is EntryDispatchPreflightStatus.MARGIN_DRIFT


def test_entry_preflight_refuses_a_retired_current_strategy_version() -> None:
    base = _preflight_request(snapshot=_snapshot())
    payload = base.model_dump()
    payload.update(
        strategy_group=StrategyGroupSnapshot(
            strategy_group_id=base.ticket.identity.runtime.strategy_group_id,
            active_version_id="strategy-version-replacement",
            status="active",
        ),
        strategy_version=StrategyVersionSnapshot(
            strategy_version_id=base.ticket.identity.runtime.strategy_version_id,
            strategy_group_id=base.ticket.identity.runtime.strategy_group_id,
            status="retired",
        ),
        event_spec=EventSpecSnapshot(
            event_spec_id=base.ticket.identity.runtime.event_spec_id,
            strategy_version_id=base.ticket.identity.runtime.strategy_version_id,
            position_side=base.ticket.identity.netting_domain.position_side,
            entry_order_type=base.ticket.entry_order_type.value,
            status="active",
        ),
    )
    request = EntryDispatchPreflightRequest(**payload)

    decision = revalidate_entry_dispatch(request)

    assert decision.status is EntryDispatchPreflightStatus.SCOPE_DRIFT


def _preflight_request(*, snapshot):
    claim_decision = build_capacity_claim(
        signal=_long_signal(),
        runtime_profile_id="tiny-live-v1",
        venue_id="binance-usdm",
        account_id="experiment-1",
        position_mode="independent_sides",
        policy=_policy(),
        usage=CapacityUsage(
            gross_notional=Decimal("0"),
            gross_risk_at_stop=Decimal("0"),
            active_ticket_count=0,
        ),
        instrument_rules=_rules(),
        admission_snapshot=_snapshot(),
        account_entry_health=classify_account_entry_health(
            _snapshot(), AdmissionOwnership()
        ),
        instrument_entry_health=classify_instrument_entry_health(
            _snapshot(),
            AdmissionOwnership(),
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            requested_position_side="long",
        ),
        entry_order_type=EntryOrderType.MARKET,
        netting_domain_occupied=False,
        now_ms=1_010,
    )
    assert claim_decision.claim is not None
    claim = claim_decision.claim
    ticket = claim.to_ticket()
    command_id = build_command_id(
        ticket_id=ticket.identity.ticket_id,
        kind=ExchangeCommandKind.ENTRY,
        generation=1,
    )
    command = ExchangeCommand(
        command_id=command_id,
        ticket_identity=ticket.identity,
        kind=ExchangeCommandKind.ENTRY,
        generation=1,
        idempotency_key=command_id,
        venue_client_order_id=build_venue_client_order_id(command_id),
        payload=OrderCommandPayload(
            side="buy",
            quantity=ticket.quantity,
            order_type="market",
            reduce_only=False,
            required_configured_leverage=ticket.selected_leverage,
            leverage_verification_digest="sha256:" + "a" * 64,
        ),
        status=ExchangeCommandStatus.CLAIMED,
        created_at_ms=1_010,
        deadline_at_ms=ticket.expires_at_ms,
    )
    ownership = AdmissionOwnership()
    return EntryDispatchPreflightRequest(
        command=command,
        ticket=ticket,
        capacity_claim=claim,
        owner_policy=OwnerPolicySnapshot(
            owner_policy_id="policy-main",
            policy_version=7,
            enabled=True,
            new_entry_submit_enabled=True,
            priority_rank=1,
            max_concurrent_tickets=3,
            planned_stop_risk_fraction=Decimal("0.03"),
            max_initial_margin_utilization=Decimal("0.90"),
            max_leverage=10,
            supported_margin_mode="cross",
            min_liquidation_distance_to_stop_distance_ratio=Decimal("2"),
            max_post_fill_stop_risk_overrun_fraction=Decimal("0.10"),
        ),
        runtime_scope=RuntimeScopeSnapshot(
            runtime_scope_id=ticket.runtime_scope_id,
            strategy_group_id=ticket.identity.runtime.strategy_group_id,
            strategy_version_id=ticket.identity.runtime.strategy_version_id,
            event_spec_id=ticket.identity.runtime.event_spec_id,
            runtime_profile_id=ticket.identity.runtime.runtime_profile_id,
            owner_policy_id=ticket.owner_policy_id,
            exchange_instrument_id=(
                ticket.identity.netting_domain.exchange_instrument_id
            ),
            position_side=ticket.identity.netting_domain.position_side,
            enabled=True,
            scope_version=ticket.runtime_scope_version,
        ),
        strategy_group=StrategyGroupSnapshot(
            strategy_group_id=ticket.identity.runtime.strategy_group_id,
            active_version_id=ticket.identity.runtime.strategy_version_id,
            status="active",
        ),
        strategy_version=StrategyVersionSnapshot(
            strategy_version_id=ticket.identity.runtime.strategy_version_id,
            strategy_group_id=ticket.identity.runtime.strategy_group_id,
            status="active",
        ),
        event_spec=EventSpecSnapshot(
            event_spec_id=ticket.identity.runtime.event_spec_id,
            strategy_version_id=ticket.identity.runtime.strategy_version_id,
            position_side=ticket.identity.netting_domain.position_side,
            entry_order_type=ticket.entry_order_type.value,
            status="active",
        ),
        runtime_capability=RuntimeCapabilitySnapshot(
            capability_key="exchange_commands",
            enabled=True,
            certified_commit="commit-1",
            schema_revision="0001_initial",
        ),
        runtime_commit="commit-1",
        schema_revision="0001_initial",
        admission_snapshot=snapshot,
        instrument_rules=InstrumentRulesFacts(
            exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            quantity_step=Decimal("0.1"),
            price_tick=Decimal("0.1"),
            min_quantity=Decimal("0.1"),
            min_notional=Decimal("5"),
            exchange_max_leverage=10,
            maintenance_margin_brackets=_rules().maintenance_margin_brackets,
            maintenance_margin_brackets_digest=(
                _rules().maintenance_margin_brackets_digest
            ),
            observed_at_ms=1_000,
            valid_until_ms=2_000,
        ),
        account_entry_health=classify_account_entry_health(snapshot, ownership),
        instrument_entry_health=classify_instrument_entry_health(
            snapshot,
            ownership,
            exchange_instrument_id=ticket.identity.netting_domain.exchange_instrument_id,
            requested_position_side=ticket.identity.netting_domain.position_side,
        ),
        now_ms=1_010,
    )
