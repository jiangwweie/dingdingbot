from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.trading_kernel.bootstrap_strategy_universes import (
    bootstrap_strategy_universes,
)
from scripts.trading_kernel.certify_readonly import _certify
from scripts.trading_kernel.promote_entry import (
    EntryPromotionBlocked,
    promote_entry,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RUNTIME_PROFILE_ID,
    ArmAcceptancePolicyRequest,
    RuntimeAuthoritySeedRequest,
    arm_acceptance_policy,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)
from tests.trading_kernel.integration.test_strategy_universe_batch_bootstrap import (
    ADMIN_DSN,
    RUNTIME_COMMIT,
    SAFE_DATABASE,
    RecordingWarmMarket,
    VirtualClock,
    _database_url,
    _drop_database,
    _run_alembic,
    _worker_driving_sleep,
)
from tests.trading_kernel.integration.universe_certification_support import (
    RecordingReadonlyCertificationSource,
)
from tests.trading_kernel.unit.detectors.fixtures import NOW_MS


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
    """Exercise the exact Entry promotion order against a six-Event local DB."""

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
        assert armed_owner_policy["policy_version"] == 2
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
        assert final_owner_policy["policy_version"] == 2
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
        clock = VirtualClock()
        market = RecordingWarmMarket()
        certification = RecordingReadonlyCertificationSource(engine)
        await bootstrap_strategy_universes(
            database_url,
            runtime_profile_id=RUNTIME_PROFILE_ID,
            now_ms=clock.read,
            wait_timeout_ms=60_000,
            poll_interval_ms=1,
            sleep=_worker_driving_sleep(
                engine=engine,
                clock=clock,
                market=market,
                certification=certification,
            ),
        )
    finally:
        if engine is not None:
            await engine.dispose()
        await admin.close()


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


async def _cleanup(database_name: str) -> None:
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        await _drop_database(admin, database_name)
    finally:
        await admin.close()
