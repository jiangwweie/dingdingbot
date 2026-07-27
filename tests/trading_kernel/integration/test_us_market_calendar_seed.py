from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.build_product_admission_snapshot import (
    build_product_admission_context,
)
from src.trading_kernel.domain.corporate_events import CorporateEventCoverage
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.product_admission import (
    ProductMarketFacts,
    ProductProfile,
    evaluate_product_admission,
)
from src.trading_kernel.domain.us_equity_session import (
    USSessionCode,
    classify_us_equity_session,
)
from src.trading_kernel.infrastructure.pg_models import (
    market_calendar_sessions,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.us_market_calendar_seed import (
    NYSE_SOURCE,
    seed_us_market_calendar,
)
from tests.trading_kernel.integration.test_strategy_registry_seed import (
    registry_engine,  # noqa: F401
)


INSTRUMENT = "binance-usdm:MSTRUSDT:perpetual"


@pytest.mark.asyncio
async def test_official_2026_2028_calendar_seed_is_exact_and_idempotent(
    registry_engine: AsyncEngine,  # noqa: F811
) -> None:
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        first = await seed_us_market_calendar(
            uow,
            seeded_at_ms=1_800_000_000_000,
        )
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        second = await seed_us_market_calendar(
            uow,
            seeded_at_ms=1_800_000_000_001,
        )
    async with registry_engine.connect() as connection:
        christmas = (
            await connection.execute(
                sa.select(market_calendar_sessions).where(
                    market_calendar_sessions.c.session_date
                    == date(2026, 12, 25)
                )
            )
        ).mappings().one()
        early = (
            await connection.execute(
                sa.select(market_calendar_sessions).where(
                    market_calendar_sessions.c.session_date
                    == date(2028, 7, 3)
                )
            )
        ).mappings().one()

    assert first == 2
    assert second == 0
    assert christmas["holiday"] is True
    assert early["early_close"] is True
    assert str(early["source_ref"]) == NYSE_SOURCE


@pytest.mark.asyncio
async def test_product_calendar_and_coverage_form_action_time_authority(
    registry_engine: AsyncEngine,  # noqa: F811
) -> None:
    action_time = int(
        datetime(
            2026,
            7,
            6,
            10,
            0,
            tzinfo=ZoneInfo("America/New_York"),
        ).timestamp()
        * 1_000
    )
    profile_payload = {
        "exchange_instrument_id": INSTRUMENT,
        "contract_type": "TRADIFI_PERPETUAL",
        "underlying_type": "EQUITY",
        "margin_asset": "USDT",
        "product_status": "TRADING",
        "configured_leverage": 5,
        "margin_mode": "cross",
    }
    profile = ProductProfile(
        product_profile_id="product-profile:MSTRUSDT:v1",
        exchange_instrument_id=INSTRUMENT,
        venue_id="binance-usdm",
        contract_type="TRADIFI_PERPETUAL",
        underlying_type="EQUITY",
        margin_asset="USDT",
        product_status="TRADING",
        configured_leverage=5,
        margin_mode="cross",
        observed_at_ms=action_time - 1_000,
        valid_until_ms=action_time + 86_400_000,
        semantic_digest=canonical_digest(profile_payload),
    )
    coverage = CorporateEventCoverage(
        coverage_id="coverage:MSTRUSDT:2026H2:v1",
        exchange_instrument_id=INSTRUMENT,
        coverage_start_ms=action_time - 86_400_000,
        coverage_end_ms=action_time + 86_400_000,
        coverage_status="complete",
        valid_until_ms=action_time + 86_400_000,
        coverage_digest=canonical_digest({"coverage": "MSTRUSDT:2026H2"}),
    )
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        await seed_us_market_calendar(uow, seeded_at_ms=action_time - 10_000)
        await uow.product_admission.upsert_product_profile(
            profile,
            source_payload=profile_payload,
            updated_at_ms=action_time - 1_000,
        )
        await uow.product_admission.replace_corporate_event_authority(
            coverage=coverage,
            events=(),
            source_name="test-provider",
            observed_at_ms=action_time - 1_000,
        )
    facts = ProductMarketFacts(
        exchange_instrument_id=INSTRUMENT,
        best_bid=Decimal("99.95"),
        best_ask=Decimal("100.05"),
        mark_price=Decimal("100"),
        index_price=Decimal("100"),
        top5_bid_depth=Decimal("100000"),
        top5_ask_depth=Decimal("100000"),
        funding_rate=Decimal("0.0001"),
        funding_observed_at_ms=action_time - 1_000,
        observed_at_ms=action_time,
    )
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        context = await build_product_admission_context(
            uow,
            market_facts=facts,
            action_time_ms=action_time,
        )

    assert context is not None
    session = classify_us_equity_session(
        calendar=context.calendar,
        action_time_ms=action_time,
    )
    decision = evaluate_product_admission(
        action_time_ms=action_time,
        order_notional=Decimal("1000"),
        profile=context.profile,
        market_facts=context.market_facts,
        calendar=context.calendar,
        corporate_event_admission=context.corporate_event_admission,
        policy=context.policy,
    )
    assert session.session_code is USSessionCode.REGULAR
    assert decision.allowed is True
    assert decision.session_multiplier == Decimal("1")
