"""Shared readonly market and request fixtures for Universe bootstrap tests."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.trading_kernel.application.market_ports import ClosedCandleRequest
from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.product import ProductSessionSnapshot
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from src.trading_kernel.interfaces.observation_worker import ObservationWorkerRequest
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerRequest,
)
from tests.trading_kernel.unit.detectors.fixtures import (
    NOW_MS,
    cpm_long_snapshot,
    sor_snapshot,
)

RUNTIME_COMMIT = "strategy-universe-rehearsal"


class RecordingWarmMarket:
    """Readonly market boundary sufficient for local Universe warming tests."""

    def __init__(self) -> None:
        self.requests: list[ClosedCandleRequest] = []
        self.mutation_calls: list[str] = []

    async def fetch_closed_candles(
        self,
        request: ClosedCandleRequest,
    ) -> tuple[ClosedCandle, ...]:
        self.requests.append(request)
        if request.timeframe == "15m":
            return sor_snapshot(side="long").candles_15m
        if request.timeframe == "4h":
            return cpm_long_snapshot().candles_4h
        return cpm_long_snapshot().candles_1h

    async def fetch_product_sessions(
        self,
        exchange_instrument_ids: tuple[str, ...],
        *,
        observed_at_ms: int,
    ) -> tuple[ProductSessionSnapshot, ...]:
        return tuple(
            ProductSessionSnapshot(
                exchange_instrument_id=instrument_id,
                product_family="tradfi_equity_perpetual",
                product_status="active",
                session_state="regular",
                regular_session_open_ms=observed_at_ms - 8 * 900_000,
                regular_session_close_ms=observed_at_ms + 2 * 900_000,
                mark_price=Decimal(100),
                index_price=Decimal(100),
                best_bid=Decimal("99.9"),
                best_ask=Decimal("100.1"),
                best_bid_quantity=Decimal(1),
                best_ask_quantity=Decimal(1),
                observed_at_ms=observed_at_ms,
                valid_until_ms=observed_at_ms + 60_000,
                source_ref="batch-bootstrap-test",
            )
            for instrument_id in exchange_instrument_ids
        )


@dataclass
class VirtualClock:
    now: int = NOW_MS

    def read(self) -> int:
        return self.now

    def advance(self, milliseconds: int = 1) -> int:
        self.now += milliseconds
        return self.now


def observation_request(now_ms: int) -> ObservationWorkerRequest:
    return ObservationWorkerRequest(
        worker_id="batch-bootstrap-observation",
        runtime_commit=RUNTIME_COMMIT,
        schema_revision=CURRENT_SCHEMA_REVISION,
        now_ms=now_ms,
        lease_until_ms=now_ms + 30_000,
        timeout_seconds=1,
        retry_interval_ms=30_000,
    )


def reconciliation_request(now_ms: int) -> ReconciliationWorkerRequest:
    return ReconciliationWorkerRequest(
        worker_id="batch-bootstrap-reconciliation",
        runtime_commit=RUNTIME_COMMIT,
        schema_revision=CURRENT_SCHEMA_REVISION,
        now_ms=now_ms,
        timeout_seconds=1,
        unknown_visibility_grace_ms=30_000,
        idle_poll_interval_ms=2_000,
        certification_lease_ms=60_000,
        certification_max_wait_ms=120_000,
        certification_valid_for_ms=600_000,
        certification_eligible_check_interval_ms=300_000,
        certification_owner_action_check_interval_ms=300_000,
        certification_transient_retry_interval_ms=30_000,
    )
