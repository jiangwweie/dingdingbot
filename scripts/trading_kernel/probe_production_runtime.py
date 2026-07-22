#!/usr/bin/env python3
"""Probe the production venue identity, rules, positions, and orders read-only."""

from __future__ import annotations

import argparse
import asyncio
from decimal import Decimal
from pathlib import Path
import sys
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.application.runtime_facts import (  # noqa: E402
    ActionTimeFactsRequest,
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
    valid_until_ms: int


class ProductionRuntimeProbe(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    environment: Literal["live"]
    venue_id: Literal["binance-usdm"]
    account_id: str
    account_position_mode: Literal["independent_sides"]
    instrument_rule_count: int
    netting_domain_count: int
    non_flat_domain_count: int
    open_order_domain_count: int
    account_equity: Decimal
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
    account_equity: Decimal | None = None
    available_margin: Decimal | None = None

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
        rule_rows.append(
            InstrumentRuleProbe(
                exchange_instrument_id=rules.exchange_instrument_id,
                quantity_step=rules.quantity_step,
                price_tick=rules.price_tick,
                min_quantity=rules.min_quantity,
                min_notional=rules.min_notional,
                valid_until_ms=rules.valid_until_ms,
            )
        )

        for position_side in ("long", "short"):
            facts = await adapter.read_action_time_facts(
                ActionTimeFactsRequest(
                    signal_event_id=(
                        f"readonly-probe:{exchange_instrument_id}:{position_side}"
                    ),
                    runtime_scope_id=(
                        f"readonly-probe:{exchange_instrument_id}:{position_side}"
                    ),
                    venue_id=settings.venue_id,
                    account_id=settings.account_id,
                    exchange_instrument_id=exchange_instrument_id,
                    position_side=position_side,
                    observed_at_ms=now_ms,
                    valid_for_ms=validity_ms,
                )
            )
            if facts.account_position_mode != settings.account_position_mode:
                raise RuntimeError("production account position mode differs from config")
            account_equity = (
                facts.account_equity
                if account_equity is None
                else min(account_equity, facts.account_equity)
            )
            available_margin = (
                facts.available_margin
                if available_margin is None
                else min(available_margin, facts.available_margin)
            )
            netting_domain_count += 1
            if facts.netting_domain_position_qty != 0:
                non_flat_domain_count += 1
            if facts.netting_domain_open_order_count != 0:
                open_order_domain_count += 1

    if account_equity is None or available_margin is None:
        raise RuntimeError("production probe did not inspect any Netting Domain")
    return ProductionRuntimeProbe(
        environment=settings.environment,
        venue_id=settings.venue_id,
        account_id=settings.account_id,
        account_position_mode=settings.account_position_mode,
        instrument_rule_count=len(rule_rows),
        netting_domain_count=netting_domain_count,
        non_flat_domain_count=non_flat_domain_count,
        open_order_domain_count=open_order_domain_count,
        account_equity=account_equity,
        available_margin=available_margin,
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
