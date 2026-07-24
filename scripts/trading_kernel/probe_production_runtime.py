#!/usr/bin/env python3
"""Probe the production venue identity, rules, positions, and orders read-only."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.runtime_facts import (  # noqa: E402
    EntryAdmissionSnapshotRequest,
    EntryFactsSource,
    InstrumentRulesRequest,
)
from src.trading_kernel.infrastructure.production_runtime import (  # noqa: E402
    ProductionRuntimeSettings,
    build_binance_usdm_venue_adapter,
    canonical_binance_usdm_instruments,
)


class InstrumentRuleProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    quantity_step: Decimal
    price_tick: Decimal
    min_quantity: Decimal
    min_notional: Decimal
    exchange_max_leverage: int
    configured_leverage: int
    valid_until_ms: int


class ProductionRuntimeProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: Literal["live"]
    venue_id: Literal["binance-usdm"]
    account_id: str
    account_position_mode: Literal["independent_sides"]
    account_margin_mode: Literal["cross"]
    instrument_rule_count: int
    netting_domain_count: int
    non_flat_domain_count: int
    open_order_domain_count: int
    total_wallet_balance: Decimal
    available_margin: Decimal
    rules: tuple[InstrumentRuleProbe, ...]
    observed_at_ms: int


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--now-ms", type=int)
    parser.add_argument("--validity-ms", type=int, default=5_000)
    return parser


async def probe_production_runtime(
    adapter: EntryFactsSource,
    settings: ProductionRuntimeSettings,
    *,
    now_ms: int,
    validity_ms: int,
) -> ProductionRuntimeProbe:
    if now_ms <= 0 or validity_ms <= 0:
        raise ValueError("probe time and validity must be positive")

    rule_rows: list[InstrumentRuleProbe] = []
    netting_domain_count = 0
    non_flat_domain_count = 0
    open_order_domain_count = 0
    admission_snapshot = None

    for exchange_instrument_id in canonical_binance_usdm_instruments():
        rules = await adapter.read_instrument_rules(
            InstrumentRulesRequest(
                venue_id=settings.venue_id,
                account_id=settings.account_id,
                exchange_instrument_id=exchange_instrument_id,
                observed_at_ms=now_ms,
                valid_for_ms=validity_ms,
            )
        )
        instrument_snapshot = await adapter.read_entry_admission_snapshot(
            EntryAdmissionSnapshotRequest(
                venue_id=settings.venue_id,
                account_id=settings.account_id,
                exchange_instrument_id=exchange_instrument_id,
                observed_at_ms=now_ms,
                valid_for_ms=validity_ms,
            )
        )
        if instrument_snapshot.position_mode != settings.account_position_mode:
            raise RuntimeError("production account position mode differs from config")
        if instrument_snapshot.margin_mode != "cross":
            raise RuntimeError("production account margin mode differs from config")
        configured_leverage = instrument_snapshot.instrument_facts_for(
            exchange_instrument_id
        ).configured_leverage
        rule_rows.append(
            InstrumentRuleProbe(
                exchange_instrument_id=rules.exchange_instrument_id,
                quantity_step=rules.quantity_step,
                price_tick=rules.price_tick,
                min_quantity=rules.min_quantity,
                min_notional=rules.min_notional,
                exchange_max_leverage=rules.exchange_max_leverage,
                configured_leverage=configured_leverage,
                valid_until_ms=rules.valid_until_ms,
            )
        )

        if admission_snapshot is None:
            admission_snapshot = instrument_snapshot
    if admission_snapshot is None:
        raise RuntimeError("production probe did not inspect any Netting Domain")
    netting_domain_count = len(canonical_binance_usdm_instruments()) * 2
    non_flat_domain_count = sum(
        position.quantity > 0 for position in admission_snapshot.positions
    )
    open_order_domain_count = len(
        {
            (order.exchange_instrument_id, order.position_side)
            for order in admission_snapshot.open_orders
        }
    )
    return ProductionRuntimeProbe(
        environment=settings.environment,
        venue_id=settings.venue_id,
        account_id=settings.account_id,
        account_position_mode=admission_snapshot.position_mode,
        account_margin_mode=admission_snapshot.margin_mode,
        instrument_rule_count=len(rule_rows),
        netting_domain_count=netting_domain_count,
        non_flat_domain_count=non_flat_domain_count,
        open_order_domain_count=open_order_domain_count,
        total_wallet_balance=admission_snapshot.total_wallet_balance,
        available_margin=admission_snapshot.available_margin,
        rules=tuple(rule_rows),
        observed_at_ms=now_ms,
    )


async def _run(args: argparse.Namespace) -> int:
    settings = ProductionRuntimeSettings.from_environment()
    adapter = build_binance_usdm_venue_adapter()
    try:
        result = await probe_production_runtime(
            adapter,
            settings,
            now_ms=args.now_ms or int(time.time() * 1_000),
            validity_ms=args.validity_ms,
        )
        print(result.model_dump_json())
        return 0
    finally:
        await adapter.close()


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
