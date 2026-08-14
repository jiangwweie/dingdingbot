from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import uuid4

import asyncpg
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.trading_kernel.bootstrap_strategy_universes import (
    bootstrap_strategy_universes,
)
from scripts.trading_kernel.certify_readonly import _certify
from scripts.trading_kernel.promote_entry import (
    EntryPromotionBlocked,
    promote_entry,
)
from src.trading_kernel.application.strategy_universe_batch_manifest import (
    APPROVED_UNIVERSE_BATCHES,
)
from src.trading_kernel.domain.product import ProductSessionSnapshot
from src.trading_kernel.infrastructure.pg_models import (
    owner_policy_current,
    owner_policy_events,
    runtime_scopes_current,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RUNTIME_PROFILE_ID,
    TRADFI_RUNTIME_PROFILE_ID,
    ArmAcceptancePolicyRequest,
    RuntimeAuthoritySeedRequest,
    arm_acceptance_policy,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)
from src.trading_kernel.interfaces.observation_worker import (
    ObservationWorkerStatus,
    run_observation_worker_once,
)
from src.trading_kernel.interfaces.reconciliation_worker import (
    ReconciliationWorkerStatus,
    run_reconciliation_worker_once,
)
from tests.trading_kernel.integration.universe_certification_support import (
    NoTicketPositionSource,
    NoTicketVenueTruth,
    RecordingReadonlyCertificationSource,
)
from tests.trading_kernel.support.postgres import (
    SAFE_TEST_DATABASE as SAFE_DATABASE,
)
from tests.trading_kernel.support.postgres import (
    TEST_POSTGRES_ADMIN_DSN as ADMIN_DSN,
)
from tests.trading_kernel.support.postgres import (
    async_database_url as _database_url,
)
from tests.trading_kernel.support.postgres import (
    drop_database as _drop_database,
)
from tests.trading_kernel.support.postgres import (
    run_alembic as _run_alembic,
)
from tests.trading_kernel.support.universe_bootstrap import (
    RUNTIME_COMMIT,
    RecordingWarmMarket,
    VirtualClock,
)
from tests.trading_kernel.support.universe_bootstrap import (
    observation_request as _shared_observation_request,
)
from tests.trading_kernel.support.universe_bootstrap import (
    reconciliation_request as _shared_reconciliation_request,
)
from tests.trading_kernel.unit.detectors.fixtures import NOW_MS


class PromotionWarmMarket(RecordingWarmMarket):
    async def fetch_closed_candles(self, request):
        candles = await super().fetch_closed_candles(request)
        if request.timeframe != "15m":
            return candles
        if not request.exchange_instrument_id.endswith(
            (
                "AAPLUSDT:perpetual",
                "AMZNUSDT:perpetual",
                "GOOGLUSDT:perpetual",
                "METAUSDT:perpetual",
                "MSFTUSDT:perpetual",
                "NVDAUSDT:perpetual",
                "SNDKUSDT:perpetual",
                "TSLAUSDT:perpetual",
            )
        ):
            return candles
        delta_ms = request.closed_at_ms - NOW_MS
        shifted = tuple(
            candle.model_copy(
                update={
                    "open_time_ms": candle.open_time_ms + delta_ms,
                    "close_time_ms": candle.close_time_ms + delta_ms,
                }
            )
            for candle in candles
        )
        latest = shifted[-1]
        return (
            *shifted[:-1],
            latest.model_copy(
                update={
                    "high": Decimal("103.2"),
                    "low": Decimal("100.8"),
                    "close": Decimal(103),
                }
            ),
        )

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
                source_ref="promotion-test",
            )
            for instrument_id in exchange_instrument_ids
        )


@dataclass
class RecordingPromotionBackend:
    """Real disposable-DB authority plus a fake systemd/exchange perimeter."""

    database_url: str
    now_ms: int
    fail_start: bool = False
    fenced: bool = True
    entry_enabled: bool = False
    entry_active: bool = False
    calls: list[str] = field(default_factory=list)
    exchange_mutations: list[str] = field(default_factory=list)

    def certification(self) -> Mapping[str, object]:
        self.calls.append("certification")
        return asyncio.run(
            _certify(
                self.database_url,
                require_flat=True,
                now_ms=self.now_ms,
            )
        )

    def external_state_and_rules_match(
        self,
        certification: Mapping[str, object],
    ) -> bool:
        del certification
        self.calls.append("external")
        return True

    def safety_workers_active_stable(self) -> bool:
        self.calls.append("safety")
        return True

    def entry_is_inactive_disabled_and_fenced(self) -> bool:
        self.calls.append("preflight")
        return self.fenced and not self.entry_enabled and not self.entry_active

    def arm_entry_authority(self) -> Mapping[str, object]:
        self.calls.append("arm")
        return asyncio.run(_arm(self.database_url, self.now_ms)).model_dump()

    def start_entry_while_fenced(self) -> None:
        self.calls.append("start")
        self.entry_enabled = True
        self.entry_active = not self.fail_start

    def entry_is_active_while_fenced(self) -> bool:
        self.calls.append("active_fenced")
        return self.fenced and self.entry_active

    def remove_entry_fence(self) -> None:
        self.calls.append("unfence")
        self.fenced = False

    def entry_is_active(self) -> bool:
        self.calls.append("active")
        return not self.fenced and self.entry_active

    def restore_entry_fence(self) -> None:
        self.calls.append("restore")
        self.fenced = True
        self.entry_enabled = False
        self.entry_active = False


def test_entry_promotion_rehearses_arm_failure_resume_and_idempotence() -> None:
    """Exercise promotion with compatible-upgrade safety capability already on."""

    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    database_url = _database_url(database_name)
    asyncio.run(_seed_and_bootstrap(database_name, database_url))
    promotion_now_ms = NOW_MS + 10_000
    try:
        failed = RecordingPromotionBackend(
            database_url=database_url,
            now_ms=promotion_now_ms,
            fail_start=True,
        )
        with pytest.raises(
            EntryPromotionBlocked,
            match="entry_not_active_while_fenced",
        ):
            promote_entry(failed)

        armed_after_failure = asyncio.run(
            _certify(
                database_url,
                require_flat=True,
                now_ms=promotion_now_ms,
            )
        )
        armed_owner_policy = armed_after_failure["owner_policy"]
        armed_capabilities = armed_after_failure["capabilities"]
        assert isinstance(armed_owner_policy, Mapping)
        assert isinstance(armed_capabilities, Mapping)
        assert armed_owner_policy["policy_version"] == 5
        assert armed_owner_policy["new_entry_submit_enabled"] is True
        assert armed_capabilities["exchange_commands"] is True
        assert failed.fenced is True
        assert failed.entry_active is False
        assert failed.calls[-1] == "restore"

        retry = RecordingPromotionBackend(
            database_url=database_url,
            now_ms=promotion_now_ms,
        )
        assert promote_entry(retry) == "promoted"
        assert "arm" not in retry.calls
        assert retry.exchange_mutations == []

        assert promote_entry(retry) == "already_promoted"
        final = asyncio.run(
            _certify(
                database_url,
                require_flat=True,
                now_ms=promotion_now_ms,
            )
        )
        final_owner_policy = final["owner_policy"]
        final_capabilities = final["capabilities"]
        assert isinstance(final_owner_policy, Mapping)
        assert isinstance(final_capabilities, Mapping)
        assert final_owner_policy["policy_version"] == 5
        assert final_capabilities["exchange_commands"] is True
    finally:
        asyncio.run(_cleanup(database_name))


async def _seed_and_bootstrap(database_name: str, database_url: str) -> None:
    admin = await asyncpg.connect(ADMIN_DSN)
    engine = None
    try:
        await admin.execute(f'CREATE DATABASE "{database_name}"')
        _run_alembic(database_url)
        engine = create_async_engine(database_url)
        async with PostgresKernelUnitOfWork(engine) as uow:
            await seed_runtime_authority(
                uow,
                RuntimeAuthoritySeedRequest(
                    account_id="subaccount-entry-promotion-test",
                    runtime_commit=RUNTIME_COMMIT,
                    schema_revision=CURRENT_SCHEMA_REVISION,
                    seeded_at_ms=NOW_MS - 10_000,
                ),
            )
        await _advance_to_r4_certification_authority(engine)
        clock = VirtualClock()
        market = PromotionWarmMarket()
        certification = RecordingReadonlyCertificationSource(engine)
        await bootstrap_strategy_universes(
            database_url,
            runtime_profile_id=TRADFI_RUNTIME_PROFILE_ID,
            now_ms=clock.read,
            wait_timeout_ms=9_000_000,
            poll_interval_ms=1,
            sleep=_worker_driving_sleep_for_profile(
                engine=engine,
                clock=clock,
                market=market,
                certification=certification,
                runtime_profile_id=TRADFI_RUNTIME_PROFILE_ID,
            ),
        )
        await bootstrap_strategy_universes(
            database_url,
            runtime_profile_id=RUNTIME_PROFILE_ID,
            now_ms=clock.read,
            wait_timeout_ms=60_000,
            poll_interval_ms=1,
            sleep=_worker_driving_sleep_for_profile(
                engine=engine,
                clock=clock,
                market=market,
                certification=certification,
                runtime_profile_id=RUNTIME_PROFILE_ID,
            ),
        )
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "UPDATE brc_runtime_capabilities_current "
                    "SET enabled = true "
                    "WHERE capability_key = 'exchange_commands'"
                )
            )
    finally:
        if engine is not None:
            await engine.dispose()
        await admin.close()


async def _advance_to_r4_certification_authority(engine) -> None:
    """Model the already-paused R4 authority that production batches certify."""

    async with engine.begin() as connection:
        await connection.execute(
            sa.insert(owner_policy_events),
            [
                {
                    "owner_policy_event_id": f"policy-event:policy-main:v{version}",
                    "owner_policy_id": "policy-main",
                    "policy_version": version,
                    "operation": "fixture_pre_certification_authority",
                    "payload": {"fixture": True},
                    "created_at_ms": NOW_MS - 10_000 + version,
                }
                for version in range(2, 5)
            ],
        )
        updated = await connection.execute(
            sa.update(owner_policy_current)
            .where(
                owner_policy_current.c.owner_policy_id == "policy-main",
                owner_policy_current.c.policy_version == 1,
                owner_policy_current.c.new_entry_submit_enabled.is_(False),
            )
            .values(
                policy_version=4,
                updated_at_ms=NOW_MS - 9_996,
            )
        )
    assert updated.rowcount == 1


async def _arm(database_url: str, now_ms: int):
    engine = create_async_engine(database_url)
    try:
        async with PostgresKernelUnitOfWork(engine) as uow:
            return await arm_acceptance_policy(
                uow,
                ArmAcceptancePolicyRequest(armed_at_ms=now_ms),
            )
    finally:
        await engine.dispose()


def _worker_driving_sleep_for_profile(
    *,
    engine,
    clock: VirtualClock,
    market: RecordingWarmMarket,
    certification: RecordingReadonlyCertificationSource,
    runtime_profile_id: str,
) -> Callable[[float], Awaitable[None]]:
    _event_specs, members = APPROVED_UNIVERSE_BATCHES[runtime_profile_id]

    async def sleep(_delay_seconds: float) -> None:
        del _delay_seconds
        async with engine.connect() as connection:
            warming_profile_count = int(
                await connection.scalar(
                    sa.select(sa.func.count())
                    .select_from(runtime_scopes_current)
                    .where(
                        runtime_scopes_current.c.lifecycle_state == "warming",
                        runtime_scopes_current.c.runtime_profile_id
                        == runtime_profile_id,
                    )
                )
                or 0
            )
        if warming_profile_count == 0:
            return
        for _member in members:
            certification_result = await run_reconciliation_worker_once(
                lambda: PostgresKernelUnitOfWork(engine),
                NoTicketVenueTruth(),
                NoTicketPositionSource(),
                _reconciliation_request(clock.advance()),
                instrument_certification_source=certification,
            )
            assert certification_result.status in {
                ReconciliationWorkerStatus.INSTRUMENT_CERTIFIED,
                ReconciliationWorkerStatus.NO_WORK,
            }
        observations = []
        for _member in members:
            observation_result = await run_observation_worker_once(
                lambda: PostgresKernelUnitOfWork(engine),
                market,
                _observation_request(clock.advance()),
            )
            observations.append(observation_result.status)
            if observation_result.status is ObservationWorkerStatus.NO_WORK:
                continue
            assert observation_result.status is ObservationWorkerStatus.OBSERVED
        assert observations.count(ObservationWorkerStatus.OBSERVED) == len(members)

    return sleep


def _observation_request(now_ms: int):
    return _shared_observation_request(now_ms)


def _reconciliation_request(now_ms: int):
    return _shared_reconciliation_request(now_ms)


async def _cleanup(database_name: str) -> None:
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        await _drop_database(admin, database_name)
    finally:
        await admin.close()
