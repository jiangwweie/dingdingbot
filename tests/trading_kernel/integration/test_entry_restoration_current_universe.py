"""Actual current Universe / Owner proof, not historical bootstrap assumptions."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.trading_kernel.certify_readonly import _certify
from scripts.trading_kernel.promote_entry import EntryPromotionBlocked, promote_entry
from src.trading_kernel.application.advance_strategy_universe import (
    UniverseActivationRequest,
    advance_strategy_universe,
)
from src.trading_kernel.application.install_strategy_universe import (
    UniverseInstallRequest,
    install_strategy_universe,
)
from src.trading_kernel.domain.instrument_selection import (
    CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS,
)
from src.trading_kernel.domain.product import InstrumentProductProfile
from src.trading_kernel.infrastructure.entry_restoration_certification import (
    read_entry_restoration_state,
)
from src.trading_kernel.infrastructure.pg_models import (
    instrument_certification_current,
    instrument_product_profiles,
    instruments,
    owner_authorizations,
    runtime_capabilities_current,
    strategy_entry_controls_current,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from tests.trading_kernel.integration.universe_activation_support import (
    make_warming_ready,
)
from tests.trading_kernel.support.postgres import async_database_url
from tests.trading_kernel.support.promotion_rehearsal import (
    RecordingPromotionBackend,
    _cleanup,
    _owner_resume,
    _seed_and_bootstrap,
)
from tests.trading_kernel.unit.detectors.fixtures import NOW_MS


async def _replace_cpm_with_seven_distinct_members(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as c:
            old = set((await c.execute(sa.text("SELECT DISTINCT exchange_instrument_id FROM brc_runtime_scopes_current WHERE runtime_profile_id='tiny-live-v1'"))).scalars())
            members = tuple(m for m in CANONICAL_CANDIDATE_EXCHANGE_INSTRUMENT_IDS if m not in old)[:7]
            for member in members:
                await c.execute(pg_insert(instruments).values(exchange_instrument_id=member,
                    venue_id="binance-usdm", asset_class="crypto", venue_symbol=member.split(":")[1],
                    contract_kind="perpetual", status="pending_certification").on_conflict_do_nothing())
                product = InstrumentProductProfile(exchange_instrument_id=member,product_family="crypto_perpetual",
                    asset_class="crypto",contract_type="PERPETUAL",underlying_type="CRYPTO",
                    entry_session_policy="continuous",status="candidate")
                await c.execute(pg_insert(instrument_product_profiles).values(**product.model_dump(),
                    semantic_digest=product.semantic_digest,updated_at_ms=NOW_MS).on_conflict_do_nothing())
        async with PostgresKernelUnitOfWork(engine) as uow:
            target = await install_strategy_universe(uow,UniverseInstallRequest(
                event_spec_id="event_spec:CPM-RO-001:CPM-LONG:v3",runtime_profile_id="tiny-live-v1",
                owner_policy_id="policy-main",exchange_instrument_ids=members,installed_at_ms=NOW_MS+1000))
            assert target.universe is not None
            uid = target.universe.universe_version_id
        await make_warming_ready(engine,universe_version_id=uid,
            warm_closed_bar_time_ms=NOW_MS+1001,valid_until_ms=NOW_MS+60000)
        async with PostgresKernelUnitOfWork(engine) as uow:
            activated = await advance_strategy_universe(uow,UniverseActivationRequest(
                universe_version_id=uid,attempted_at_ms=NOW_MS+1002))
            assert activated.status.value == "activated"
        async with engine.begin() as c:
            await c.execute(sa.update(strategy_entry_controls_current)
                .where(strategy_entry_controls_current.c.strategy_group_id == "SOR-001")
                .values(entry_state="paused"))
    finally:
        await engine.dispose()


@pytest.mark.parametrize("fault", [None,"expired","future","wrong_leverage","wrong_mode",
                                   "missing_rules","unavailable","wrong_capability_identity",
                                   "weak_owner_proof","wrong_owner_scope","owner_time_mismatch"])
def test_current_22_member_restore_is_readonly_owner_scoped_and_fail_closed(fault):
    name = "brc_kernel_test_"+uuid4().hex[:12]
    url = async_database_url(name)
    asyncio.run(_seed_and_bootstrap(name,url))
    try:
        asyncio.run(_replace_cpm_with_seven_distinct_members(url))
        before = asyncio.run(_certify(url,require_flat=True,now_ms=NOW_MS+10000))
        assert len(before["entry_recovery_members"]) == 22
        assert before["entry_recovery_ready"]
        assert not before["universe_bootstrap_pass"]
        assert not before["owner_entry_resume_authorized"]
        paused = RecordingPromotionBackend(database_url=url,now_ms=NOW_MS+10000)
        with pytest.raises(EntryPromotionBlocked): promote_entry(paused)
        assert paused.fenced and "unfence" not in paused.calls
        asyncio.run(_owner_resume(url,NOW_MS+10000))
        if fault:
            asyncio.run(_corrupt_current_certification(url,fault))
        evidence = asyncio.run(_certify(url,require_flat=True,now_ms=NOW_MS+10000))
        proof_fault = fault in {"weak_owner_proof","wrong_owner_scope","owner_time_mismatch"}
        assert evidence["entry_recovery_ready"] is (fault is None or proof_fault)
        assert evidence["owner_entry_resume_authorized"] is (not proof_fault)
        backend = RecordingPromotionBackend(database_url=url,now_ms=NOW_MS+10000)
        if fault:
            with pytest.raises(EntryPromotionBlocked): promote_entry(backend)
            assert backend.fenced and "unfence" not in backend.calls
        else:
            assert promote_entry(backend) == "promoted"
            assert "arm" not in backend.calls
            assert backend.exchange_mutations == []
            assert evidence["owner_policy"]["policy_version"] == 5
            assert evidence["active_counts"]["tickets"] == 0
            assert asyncio.run(_sor_paused(url))
    finally:
        asyncio.run(_cleanup(name))


async def _corrupt_current_certification(url: str, fault: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as c:
            if fault in {"weak_owner_proof","wrong_owner_scope","owner_time_mismatch"}:
                values = {"weak_owner_proof":{"authentication_strength":"session"},
                          "wrong_owner_scope":{"target_scope":{"owner_policy_id":"other"}},
                          "owner_time_mismatch":{"authorized_at_ms":NOW_MS+9999}}[fault]
                await c.execute(sa.update(owner_authorizations).where(
                    owner_authorizations.c.purpose=="entry_resume").values(**values))
                return
            if fault == "wrong_capability_identity":
                await c.execute(sa.update(runtime_capabilities_current).values(certified_commit="wrong"))
                return
            values = {"expired":{"valid_until_ms":NOW_MS+9999,"observed_at_ms":NOW_MS+9998,
                                 "next_check_at_ms":NOW_MS+9998},
                      "future":{"observed_at_ms":NOW_MS+20000,"valid_until_ms":NOW_MS+60000,
                                "next_check_at_ms":NOW_MS+20000},
                      "wrong_leverage":{"configured_leverage":10},
                      "wrong_mode":{"position_mode":"one_way"},
                      "missing_rules":{"product_rules_digest":None},
                      "unavailable":{"status":"temporarily_unavailable","blocker_code":"readonly_unavailable"}}[fault]
            await c.execute(sa.update(instrument_certification_current).values(**values))
    finally:
        await engine.dispose()


async def _sor_paused(url: str) -> bool:
    engine=create_async_engine(url)
    try:
        async with engine.connect() as c:
            await c.execute(sa.text("SET TRANSACTION READ ONLY"))
            state=await read_entry_restoration_state(c,now_ms=NOW_MS+10000)
            assert state.ready
            return await c.scalar(sa.select(strategy_entry_controls_current.c.entry_state)
                .where(strategy_entry_controls_current.c.strategy_group_id=="SOR-001"))=="paused"
    finally:
        await engine.dispose()
