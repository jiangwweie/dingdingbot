from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.dispatch_exchange_command import (
    DispatchCommandRequest,
    DispatchCommandStatus,
    dispatch_one_command,
)
from src.trading_kernel.application.issue_ticket import (
    IssueTicketStatus,
    issue_ticket,
)
from src.trading_kernel.application.market_ports import ClosedCandleRequest
from src.trading_kernel.application.ports import (
    VenueCommandRequest,
    VenueTruthRequest,
)
from src.trading_kernel.application.reconcile_ticket import (
    ExitTicketRequest,
    ReconcileTicketRequest,
    reconcile_ticket,
    request_exit,
)
from src.trading_kernel.domain.commands import (
    ExchangeCommandKind,
    ExchangeCommandStatus,
    OrderCommandPayload,
)
from src.trading_kernel.domain.identities import (
    NettingDomain,
    TicketIdentity,
)
from src.trading_kernel.domain.position import PositionSnapshot
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts
from src.trading_kernel.domain.strategy_universe import build_strategy_universe
from src.trading_kernel.domain.ticket import build_ticket_id
from src.trading_kernel.domain.venue_truth import VenueLookupStatus
from src.trading_kernel.infrastructure.binance_public_market_source import (
    CcxtBinancePublicMarketSource,
)
from src.trading_kernel.infrastructure.pg_models import (
    exchange_commands,
    instruments,
    runtime_scopes_current,
    strategy_universe_current,
    strategy_universe_members,
    strategy_universe_versions,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.venue_adapter import CcxtVenueAdapter
from tests.trading_kernel.integration.test_command_dispatch import (
    CountingVenue,
    PreflightFacts,
    _commit_passed_post_fill_stress_if_pending,
    _issue,
    _seed_policy,
)
from tests.trading_kernel.integration.test_issue_ticket import (
    _issue_request,
    _seed_ticket_runtime_scope,
    _ticket_for_signal,
)
from tests.trading_kernel.unit.test_ticket import _ticket
from tests.trading_kernel.unit.test_venue_adapter import FakeAsyncExchange

_DYNAMIC_INSTRUMENT_ID = "binance-usdm:OPUSDT:perpetual"
_DYNAMIC_CCXT_SYMBOL = "OP/USDT:USDT"
pytest_plugins = ("tests.trading_kernel.integration.test_command_dispatch",)


class RecordingBinanceExchange(FakeAsyncExchange):
    def __init__(self) -> None:
        super().__init__()
        self.ohlcv_symbols: list[str] = []
        self.created_symbols: list[str] = []
        self.created_order_types: list[str] = []
        self.truth_symbols: list[str] = []

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: object = None,
        limit: int | None = None,
    ) -> list[list[object]]:
        del timeframe, since, limit
        self.ohlcv_symbols.append(symbol)
        return [[3_600_000, "10", "11", "9", "10.5", "20"]]

    async def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: object,
        price: object,
        params: Mapping[str, object],
    ) -> dict[str, object]:
        del side, amount, price, params
        self.created_symbols.append(symbol)
        self.created_order_types.append(order_type)
        return {
            "id": f"venue-order-{len(self.created_symbols)}",
            "status": "open",
        }

    async def fetch_order(
        self,
        order_id: object,
        symbol: str,
        params: Mapping[str, object],
    ) -> dict[str, object]:
        del order_id
        self.truth_symbols.append(symbol)
        return {
            "id": "venue-exit-1",
            "clientOrderId": params["origClientOrderId"],
            "symbol": symbol,
            "status": "open",
            "side": "sell",
            "amount": "1",
            "reduceOnly": True,
            "info": {"positionSide": "LONG"},
        }

    async def fetch_positions(
        self,
        symbols: list[str],
        params: Mapping[str, object],
    ) -> list[object]:
        del symbols, params
        return []

    async def fetch_my_trades(
        self,
        symbol: str,
        since: object,
        limit: int,
        params: Mapping[str, object],
    ) -> list[object]:
        del symbol, since, limit, params
        return []

    async def fetch_open_orders(
        self,
        symbol: str | None,
        since: object,
        limit: int,
        params: Mapping[str, object],
    ) -> list[object]:
        del symbol, since, limit, params
        return []


@pytest.mark.asyncio
async def test_registry_independent_instrument_routes_market_and_existing_ticket_safety() -> None:
    registry_payload = tuple(
        contract.model_dump(mode="json")
        for contract in registered_strategy_contracts()
    )
    assert all(
        _DYNAMIC_INSTRUMENT_ID not in str(contract)
        for contract in registry_payload
    )
    replacement = build_strategy_universe(
        universe_version_id="universe:replacement:2",
        strategy_group_id="SOR-001",
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        universe_version=2,
        exchange_instrument_ids=("binance-usdm:BTCUSDT:perpetual",),
        installed_at_ms=2_000,
    )
    assert _DYNAMIC_INSTRUMENT_ID not in replacement.exchange_instrument_ids

    exchange = RecordingBinanceExchange()
    market = CcxtBinancePublicMarketSource(
        exchange=exchange,
        timeout_seconds=1,
    )
    venue = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        clock_ms=lambda: 3_000,
    )

    candles = await market.fetch_closed_candles(
        ClosedCandleRequest(
            exchange_instrument_id=_DYNAMIC_INSTRUMENT_ID,
            timeframe="1h",
            limit=1,
            closed_at_ms=7_200_000,
        )
    )
    protection = await venue.execute(
        _order_request(
            kind=ExchangeCommandKind.REPLACE_PROTECTION,
            payload=OrderCommandPayload(
                side="sell",
                quantity=Decimal(1),
                order_type="stop_market",
                reduce_only=True,
                stop_price=Decimal(10),
                replaces_exchange_order_id="venue-old-stop",
                source_watermark_ms=2_500,
            ),
        )
    )
    exit_result = await venue.execute(
        _order_request(
            kind=ExchangeCommandKind.EXIT,
            payload=OrderCommandPayload(
                side="sell",
                quantity=Decimal(1),
                order_type="market",
                reduce_only=True,
            ),
        )
    )
    truth = await venue.lookup_command_truth(
        VenueTruthRequest(
            command_id="command:exit",
            kind=ExchangeCommandKind.EXIT,
            venue_id="binance-usdm",
            account_id="experiment-1",
            exchange_instrument_id=_DYNAMIC_INSTRUMENT_ID,
            position_side="long",
            venue_client_order_id="brc-exit",
            payload=OrderCommandPayload(
                side="sell",
                quantity=Decimal(1),
                order_type="market",
                reduce_only=True,
            ),
            observed_at_ms=3_000,
        )
    )

    assert len(candles) == 1
    assert protection.status is ExchangeCommandStatus.ACCEPTED
    assert exit_result.status is ExchangeCommandStatus.ACCEPTED
    assert truth.lookup_status is VenueLookupStatus.VISIBLE
    assert truth.order is not None
    assert truth.order.exchange_instrument_id == _DYNAMIC_INSTRUMENT_ID
    assert exchange.ohlcv_symbols == [_DYNAMIC_CCXT_SYMBOL]
    assert exchange.created_symbols == [
        _DYNAMIC_CCXT_SYMBOL,
        _DYNAMIC_CCXT_SYMBOL,
    ]
    assert exchange.truth_symbols == [_DYNAMIC_CCXT_SYMBOL]


@pytest.mark.asyncio
async def test_pending_certification_alone_creates_no_ticket_command_or_venue_write(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _ticket()
    await _seed_policy(dispatch_engine)
    await _seed_ticket_runtime_scope(dispatch_engine, ticket)
    async with dispatch_engine.begin() as connection:
        await connection.execute(
            sa.update(instruments)
            .where(
                instruments.c.exchange_instrument_id
                == ticket.identity.netting_domain.exchange_instrument_id
            )
            .values(status="pending_certification")
        )
    async with dispatch_engine.connect() as connection:
        current_universe_id = await connection.scalar(
            sa.select(strategy_universe_current.c.universe_version_id).where(
                strategy_universe_current.c.event_spec_id
                == ticket.identity.runtime.event_spec_id
            )
        )
        scope_authority = (
            await connection.execute(
                sa.select(
                    runtime_scopes_current.c.lifecycle_state,
                    runtime_scopes_current.c.entry_enabled,
                ).where(
                    runtime_scopes_current.c.runtime_scope_id
                    == ticket.runtime_scope_id
                )
            )
        ).one()
        instrument_status = await connection.scalar(
            sa.select(instruments.c.status).where(
                instruments.c.exchange_instrument_id
                == ticket.identity.netting_domain.exchange_instrument_id
            )
        )

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        issue_result = await issue_ticket(
            uow,
            _issue_request(
                ticket=ticket,
                now_ms=1_001,
                claim_owner="issuer-uncertified",
            ),
        )
    venue = CountingVenue()
    dispatch_result = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="entry-dispatcher",
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
        ),
    )
    async with dispatch_engine.connect() as connection:
        ticket_count = int(
            (
                await connection.execute(
                    sa.select(sa.func.count()).select_from(trade_tickets)
                )
            ).scalar_one()
        )
        command_count = int(
            (
                await connection.execute(
                    sa.select(sa.func.count()).select_from(exchange_commands)
                )
            ).scalar_one()
        )

    assert issue_result.status is IssueTicketStatus.SCOPE_OR_POLICY_MISMATCH
    assert dispatch_result.status is DispatchCommandStatus.NO_COMMAND
    assert current_universe_id == ticket.universe_version_id
    assert scope_authority == ("active", True)
    assert instrument_status == "pending_certification"
    assert ticket_count == 0
    assert command_count == 0
    assert venue.calls == 0


@pytest.mark.asyncio
async def test_removed_instrument_ticket_still_protects_exits_and_reconciles(
    dispatch_engine: AsyncEngine,
) -> None:
    ticket = _dynamic_ticket()
    second_ticket = _ticket_for_signal(
        "signal-second-during-protection",
        "episode-second-during-protection",
        position_side="short",
    )
    await _seed_policy(dispatch_engine)
    await _seed_ticket_runtime_scope(dispatch_engine, second_ticket)
    await _issue(dispatch_engine, ticket)
    exchange = RecordingBinanceExchange()
    venue = CcxtVenueAdapter(
        exchanges={("binance-usdm", "experiment-1"): exchange},
        clock_ms=lambda: 3_000,
    )

    entry = await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(dispatch_engine),
        venue,
        DispatchCommandRequest(
            worker_id="entry-dispatcher",
            ticket_id=ticket.identity.ticket_id,
            now_ms=1_100,
            lease_until_ms=6_100,
            timeout_seconds=1,
            runtime_commit="kernel-test-head",
            schema_revision="0001_trading_kernel_baseline_v2",
            admission_snapshot_validity_ms=1_000,
        ),
        entry_facts_source=PreflightFacts(),
    )

    async with dispatch_engine.begin() as connection:
        await connection.execute(
            sa.insert(strategy_universe_versions).values(
                universe_version_id="universe:sor-long:replacement",
                strategy_group_id=ticket.identity.runtime.strategy_group_id,
                event_spec_id=ticket.identity.runtime.event_spec_id,
                universe_version=2,
                semantic_digest="sha256:" + "b" * 64,
                lifecycle_state="active",
                installed_at_ms=2_050,
                activated_at_ms=2_050,
            )
        )
        await connection.execute(
            sa.insert(strategy_universe_members).values(
                universe_version_id="universe:sor-long:replacement",
                exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
            )
        )
        await connection.execute(
            sa.update(strategy_universe_current)
            .where(
                strategy_universe_current.c.event_spec_id
                == ticket.identity.runtime.event_spec_id
            )
            .values(
                universe_version_id="universe:sor-long:replacement",
                semantic_digest="sha256:" + "b" * 64,
                activation_generation=2,
                activated_at_ms=2_050,
            )
        )
        await connection.execute(
            sa.update(strategy_universe_versions)
            .where(
                strategy_universe_versions.c.universe_version_id
                == ticket.universe_version_id
            )
            .values(lifecycle_state="retired", retired_at_ms=2_150)
        )
        await connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.runtime_scope_id
                == ticket.runtime_scope_id
            )
            .values(
                lifecycle_state="retired",
                observation_enabled=False,
                entry_enabled=False,
            )
        )

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        lane_before_protection = await uow.entry_admission.get_global_lane()
        second_issue = await issue_ticket(
            uow,
            _issue_request(
                ticket=second_ticket,
                now_ms=2_051,
                claim_owner="issuer-second-during-protection",
            ),
        )

    assert lane_before_protection is not None
    assert lane_before_protection.status == "claimed"
    assert lane_before_protection.ticket_id == ticket.identity.ticket_id
    assert second_issue.status is IssueTicketStatus.ENTRY_LANE_OCCUPIED

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=ticket.quantity,
                    average_entry_price=ticket.entry_reference_price,
                    venue_reported_liquidation_price=Decimal(57000),
                    observed_at_ms=2_100,
                ),
            ),
        )
        commands_after_switch = await uow.exchange_commands.list_for_ticket(
            ticket.identity.ticket_id
        )

    initial_stop_command = next(
        command
        for command in commands_after_switch
        if command.kind is ExchangeCommandKind.INITIAL_STOP
    )
    assert initial_stop_command.status is ExchangeCommandStatus.PREPARED
    assert initial_stop_command.ticket_identity == ticket.identity

    initial_stop = await _dispatch_ticket_command(
        dispatch_engine,
        venue,
        ticket.identity.ticket_id,
        now_ms=2_200,
    )
    await _commit_passed_post_fill_stress_if_pending(
        dispatch_engine,
        ticket.identity.ticket_id,
    )
    take_profit = await _dispatch_ticket_command(
        dispatch_engine,
        venue,
        ticket.identity.ticket_id,
        now_ms=2_300,
    )

    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        await request_exit(
            uow,
            ExitTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                reason="strategy_exit",
                requested_at_ms=3_100,
            ),
        )
    exit_result = await _dispatch_ticket_command(
        dispatch_engine,
        venue,
        ticket.identity.ticket_id,
        now_ms=3_200,
    )
    async with PostgresKernelUnitOfWork(dispatch_engine) as uow:
        reconciliation = await reconcile_ticket(
            uow,
            ReconcileTicketRequest(
                ticket_id=ticket.identity.ticket_id,
                snapshot=PositionSnapshot(
                    netting_domain=ticket.identity.netting_domain,
                    quantity=Decimal(0),
                    average_entry_price=None,
                    open_orders=(),
                    observed_at_ms=3_300,
                ),
            ),
        )

    assert entry.status is DispatchCommandStatus.ACCEPTED
    assert initial_stop.status is DispatchCommandStatus.ACCEPTED
    assert take_profit.status is DispatchCommandStatus.ACCEPTED
    assert exit_result.status is DispatchCommandStatus.ACCEPTED
    assert reconciliation.status.value == "position_flat_recorded"
    assert exchange.created_symbols == [_DYNAMIC_CCXT_SYMBOL] * 4
    assert exchange.created_order_types == [
        "market",
        "stop_market",
        "limit",
        "market",
    ]


def _order_request(
    *,
    kind: ExchangeCommandKind,
    payload: OrderCommandPayload,
) -> VenueCommandRequest:
    return VenueCommandRequest(
        command_id=f"command:{kind.value}",
        kind=kind,
        venue_id="binance-usdm",
        account_id="experiment-1",
        exchange_instrument_id=_DYNAMIC_INSTRUMENT_ID,
        position_side="long",
        venue_client_order_id=f"brc-{kind.value}",
        payload=payload,
        deadline_at_ms=10_000,
    )


def _dynamic_ticket():
    original = _ticket()
    domain = NettingDomain(
        venue_id=original.identity.netting_domain.venue_id,
        account_id=original.identity.netting_domain.account_id,
        exchange_instrument_id=_DYNAMIC_INSTRUMENT_ID,
        position_side=original.identity.netting_domain.position_side,
    )
    identity = TicketIdentity(
        ticket_id=build_ticket_id(
            signal_event_id=original.identity.signal_event_id,
            runtime=original.identity.runtime,
            netting_domain=domain,
        ),
        exposure_episode_id=original.identity.exposure_episode_id,
        signal_event_id=original.identity.signal_event_id,
        runtime=original.identity.runtime,
        netting_domain=domain,
    )
    return original.model_copy(
        update={
            "identity": identity,
            "runtime_scope_id": "scope-sor-op-long",
        }
    )


async def _dispatch_ticket_command(
    engine: AsyncEngine,
    venue: CcxtVenueAdapter,
    ticket_id: str,
    *,
    now_ms: int,
):
    return await dispatch_one_command(
        lambda: PostgresKernelUnitOfWork(engine),
        venue,
        DispatchCommandRequest(
            worker_id=f"lifecycle-{now_ms}",
            ticket_id=ticket_id,
            now_ms=now_ms,
            lease_until_ms=now_ms + 5_000,
            timeout_seconds=1,
        ),
    )
