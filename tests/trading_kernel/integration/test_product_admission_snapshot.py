from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.build_product_admission_snapshot import (
    build_product_admission_context,
)
from src.trading_kernel.domain.corporate_events import CorporateEventCoverage
from src.trading_kernel.domain.product_admission import (
    ProductMarketFacts,
    ProductProfile,
    evaluate_product_admission,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.us_market_calendar_seed import (
    seed_us_market_calendar,
)
from tests.trading_kernel.integration.test_strategy_registry_seed import (
    registry_engine,  # noqa: F401
)


INSTRUMENT_ID = "binance-usdm:MSTRUSDT:perpetual"


@pytest.mark.asyncio
async def test_database_authority_builds_action_time_product_snapshot(
    registry_engine: AsyncEngine,  # noqa: F811
) -> None:
    action_time_ms = _ms(2026, 7, 6, 15, 0)
    profile = _profile(action_time_ms)
    coverage = _coverage(action_time_ms)
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        await seed_us_market_calendar(uow, seeded_at_ms=action_time_ms - 10_000)
        assert await uow.product_admission.upsert_product_profile(
            profile,
            source_payload={"source": "mock_exchange_info"},
            updated_at_ms=action_time_ms - 10_000,
        )
        await uow.product_admission.replace_corporate_event_authority(
            coverage=coverage,
            events=(),
            source_name="mock_corporate_provider",
            observed_at_ms=action_time_ms - 10_000,
        )
        context = await build_product_admission_context(
            uow,
            market_facts=_market_facts(action_time_ms),
            action_time_ms=action_time_ms,
        )

    assert context is not None
    decision = evaluate_product_admission(
        action_time_ms=action_time_ms,
        order_notional=Decimal("100"),
        profile=context.profile,
        market_facts=context.market_facts,
        calendar=context.calendar,
        corporate_event_admission=context.corporate_event_admission,
        policy=context.policy,
    )
    assert decision.allowed is True
    assert decision.session_code == "US_REGULAR"
    assert decision.session_multiplier == Decimal("1")
    assert decision.product_admission_digest.startswith("sha256:")


@pytest.mark.asyncio
async def test_missing_and_stale_corporate_coverage_fail_closed(
    registry_engine: AsyncEngine,  # noqa: F811
) -> None:
    action_time_ms = _ms(2026, 7, 6, 15, 0)
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        await seed_us_market_calendar(uow, seeded_at_ms=action_time_ms - 10_000)
        await uow.product_admission.upsert_product_profile(
            _profile(action_time_ms),
            source_payload={"source": "mock_exchange_info"},
            updated_at_ms=action_time_ms - 10_000,
        )
        missing = await build_product_admission_context(
            uow,
            market_facts=_market_facts(action_time_ms),
            action_time_ms=action_time_ms,
        )
    assert missing is not None
    assert missing.corporate_event_admission.allowed is False
    assert (
        missing.corporate_event_admission.reason_code
        == "corporate_event_coverage_missing"
    )

    stale_coverage = _coverage(action_time_ms).model_copy(
        update={
            "coverage_id": "coverage:mstr:stale",
            "coverage_end_ms": action_time_ms - 1,
            "coverage_digest": "sha256:" + "e" * 64,
        }
    )
    async with PostgresKernelUnitOfWork(registry_engine) as uow:
        await uow.product_admission.replace_corporate_event_authority(
            coverage=stale_coverage,
            events=(),
            source_name="mock_corporate_provider",
            observed_at_ms=action_time_ms - 1,
        )
        stale = await build_product_admission_context(
            uow,
            market_facts=_market_facts(action_time_ms),
            action_time_ms=action_time_ms,
        )
    assert stale is not None
    assert stale.corporate_event_admission.allowed is False
    assert (
        stale.corporate_event_admission.reason_code
        == "corporate_event_coverage_stale_or_incomplete"
    )


def _profile(action_time_ms: int) -> ProductProfile:
    return ProductProfile(
        product_profile_id="product-profile:mstr:v1",
        exchange_instrument_id=INSTRUMENT_ID,
        venue_id="binance-usdm",
        contract_type="TRADIFI_PERPETUAL",
        underlying_type="EQUITY",
        margin_asset="USDT",
        product_status="TRADING",
        configured_leverage=5,
        margin_mode="cross",
        observed_at_ms=action_time_ms - 86_400_000,
        valid_until_ms=action_time_ms + 86_400_000,
        semantic_digest="sha256:" + "a" * 64,
    )


def _coverage(action_time_ms: int) -> CorporateEventCoverage:
    return CorporateEventCoverage(
        coverage_id="coverage:mstr:v1",
        exchange_instrument_id=INSTRUMENT_ID,
        coverage_start_ms=action_time_ms - 86_400_000,
        coverage_end_ms=action_time_ms + 86_400_000,
        coverage_status="complete",
        valid_until_ms=action_time_ms + 86_400_000,
        coverage_digest="sha256:" + "b" * 64,
    )


def _market_facts(action_time_ms: int) -> ProductMarketFacts:
    return ProductMarketFacts(
        exchange_instrument_id=INSTRUMENT_ID,
        best_bid=Decimal("99.9"),
        best_ask=Decimal("100.1"),
        mark_price=Decimal("100"),
        index_price=Decimal("100"),
        top5_bid_depth=Decimal("1000"),
        top5_ask_depth=Decimal("1000"),
        funding_rate=Decimal("0.0001"),
        funding_observed_at_ms=action_time_ms - 1_000,
        observed_at_ms=action_time_ms - 1_000,
    )


def _ms(year: int, month: int, day: int, hour: int, minute: int) -> int:
    return int(
        datetime(
            year,
            month,
            day,
            hour,
            minute,
            tzinfo=UTC,
        ).timestamp()
        * 1_000
    )
