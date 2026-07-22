from __future__ import annotations

import importlib
from types import ModuleType

import pytest

from scripts.trading_kernel.cutover_tokyo import CutoverPhase
from scripts.trading_kernel.verify_flat_cutover import CutoverFacts, CutoverPlan


def _production_adapter_module() -> ModuleType:
    try:
        return importlib.import_module(
            "src.trading_kernel.infrastructure.tokyo_cutover_adapter"
        )
    except ModuleNotFoundError:
        pytest.fail("production Tokyo cutover adapter is missing")


def test_production_cutover_adapter_module_exists() -> None:
    _production_adapter_module()


def test_cutover_targets_only_exact_brc_allowlist() -> None:
    module = _production_adapter_module()
    adapter = module.TokyoCutoverAdapter(FakeTokyoSystem(module, _facts()))

    assert adapter.mutable_units == (
        module.EXPECTED_OLD_BRC_UNITS | module.EXPECTED_NEW_BRC_UNITS
    )
    assert adapter.mutable_containers == {
        "brc-trading-kernel-pg",
        "dingdingbot-pg",
    }
    assert "nginx.service" not in adapter.mutable_units
    assert "owner_ai_pg" not in adapter.mutable_containers
    assert "owner_ai_cpa" not in adapter.mutable_containers


@pytest.mark.asyncio
async def test_non_quant_baseline_drift_blocks_every_mutating_phase() -> None:
    module = _production_adapter_module()
    system = FakeTokyoSystem(module, _facts())
    adapter = module.TokyoCutoverAdapter(system)
    plan = _plan()

    await adapter.inspect_preconditions(plan)
    system.non_quant_digest = "sha256:changed"
    await adapter.inspect_preconditions(plan)

    assert adapter.non_quant_baseline_matches() is False
    with pytest.raises(RuntimeError, match="non-quantitative baseline changed"):
        await adapter.apply_phase(CutoverPhase.REBUILD_APPLICATION_SCHEMA, plan)
    assert system.actions == []


@pytest.mark.asyncio
async def test_cutover_phase_actions_preserve_entry_fence_and_exact_old_units() -> None:
    module = _production_adapter_module()
    system = FakeTokyoSystem(module, _facts())
    adapter = module.TokyoCutoverAdapter(system)
    plan = _plan()
    await adapter.inspect_preconditions(plan)

    await adapter.apply_phase(CutoverPhase.FENCE_EXCHANGE_WRITES, plan)
    await adapter.apply_phase(CutoverPhase.STOP_OLD_WRITERS, plan)
    await adapter.apply_phase(CutoverPhase.CERTIFY_ENTRY_FENCED, plan)

    assert system.actions == [
        ("fence_new_entry", ()),
        ("stop_units", tuple(sorted(module.EXPECTED_OLD_BRC_UNITS))),
        ("certify_entry_fenced", ()),
    ]
    assert await adapter.phase_satisfied(
        CutoverPhase.CERTIFY_ENTRY_FENCED,
        plan,
    )
    assert system.phase_state.exchange_writes_fenced is True
    assert system.phase_state.entry_timer_enabled is False
    assert system.phase_state.exchange_commands_enabled is False


@pytest.mark.asyncio
async def test_ssh_system_phase_inspection_returns_typed_state() -> None:
    module = _production_adapter_module()
    system = module.SshTokyoSystem(AlwaysMissingRunner(module))

    state = await system.inspect_phase_state(_plan())

    assert isinstance(state, module.TokyoPhaseState)
    assert state.old_writers_stopped is True
    assert state.entry_timer_enabled is False
    assert state.exchange_commands_enabled is False


class AlwaysMissingRunner:
    def __init__(self, module: ModuleType) -> None:
        self.module = module

    async def run(
        self,
        argv: tuple[str, ...],
        *,
        check: bool = True,
    ) -> object:
        del argv, check
        return self.module._RemoteResult(returncode=1, stdout="", stderr="")


class FakeTokyoSystem:
    def __init__(self, module: ModuleType, facts: CutoverFacts) -> None:
        self.module = module
        self.facts = facts
        self.non_quant_digest = "sha256:baseline"
        self.persisted_non_quant_digest: str | None = None
        self.actions: list[tuple[str, tuple[str, ...]]] = []
        self.phase_state = module.TokyoPhaseState()

    async def inspect_preconditions(
        self,
        plan: CutoverPlan,
        *,
        old_units: frozenset[str],
        new_units: frozenset[str],
    ) -> object:
        del plan, old_units, new_units
        return self.module.TokyoInspection(
            facts=self.facts,
            non_quant_digest=self.non_quant_digest,
        )

    async def inspect_phase_state(self, plan: CutoverPlan) -> object:
        del plan
        return self.phase_state

    async def read_non_quant_digest(self) -> str:
        return self.non_quant_digest

    async def read_persisted_non_quant_baseline(
        self,
        plan: CutoverPlan,
    ) -> str | None:
        del plan
        return self.persisted_non_quant_digest

    async def persist_non_quant_baseline(
        self,
        plan: CutoverPlan,
        digest: str,
    ) -> None:
        del plan
        self.persisted_non_quant_digest = digest

    async def fence_new_entry(self, plan: CutoverPlan) -> None:
        del plan
        self.actions.append(("fence_new_entry", ()))
        self.phase_state = self.phase_state.model_copy(
            update={
                "exchange_writes_fenced": True,
                "entry_timer_enabled": False,
                "exchange_commands_enabled": False,
            }
        )

    async def stop_units(
        self,
        plan: CutoverPlan,
        units: tuple[str, ...],
    ) -> None:
        del plan
        self.actions.append(("stop_units", units))
        self.phase_state = self.phase_state.model_copy(
            update={"old_writers_stopped": True}
        )

    async def create_snapshot(self, plan: CutoverPlan) -> None:
        del plan
        self.actions.append(("create_snapshot", ()))
        self.phase_state = self.phase_state.model_copy(
            update={"snapshot_exists": True}
        )

    async def create_target_database(self, plan: CutoverPlan) -> None:
        del plan
        self.actions.append(("create_target_database", ()))
        self.phase_state = self.phase_state.model_copy(
            update={"target_schema_ready": True}
        )

    async def seed_target_authority(self, plan: CutoverPlan) -> None:
        del plan
        self.actions.append(("seed_target_authority", ()))
        self.phase_state = self.phase_state.model_copy(
            update={"seed_identity_matches": True}
        )

    async def activate_release(self, plan: CutoverPlan) -> None:
        del plan
        self.actions.append(("activate_release", ()))
        self.phase_state = self.phase_state.model_copy(
            update={"release_active": True}
        )

    async def certify_readonly(self, plan: CutoverPlan) -> None:
        del plan
        self.actions.append(("certify_readonly", ()))
        self.phase_state = self.phase_state.model_copy(
            update={"readonly_certified": True}
        )

    async def enable_observation(self, plan: CutoverPlan) -> None:
        del plan
        self.actions.append(("enable_observation", ()))
        self.phase_state = self.phase_state.model_copy(
            update={"observation_enabled": True}
        )

    async def certify_signal_to_ticket_no_write(self, plan: CutoverPlan) -> None:
        del plan
        self.actions.append(("certify_signal_to_ticket_no_write", ()))
        self.phase_state = self.phase_state.model_copy(
            update={"signal_to_ticket_no_write_certified": True}
        )

    async def certify_entry_fenced(self, plan: CutoverPlan) -> None:
        del plan
        self.actions.append(("certify_entry_fenced", ()))

    async def close(self) -> None:
        return None


def _plan() -> CutoverPlan:
    return CutoverPlan(
        cutover_id="tokyo-kernel-production",
        server_id="VM-0-11-ubuntu",
        database_identity="brc_trading_kernel",
        venue_id="binance-usdm",
        account_id="subaccount-main",
        runtime_profile_id="tiny-live-v1",
        application_schema="public",
        target_commit="a" * 40,
        target_schema_revision="0001_initial",
        target_seed_identity="sha256:" + "b" * 64,
        target_release_id="brc-trading-kernel-aaaaaaaaaaaa",
    )


def _facts() -> CutoverFacts:
    plan = _plan()
    return CutoverFacts(
        server_id=plan.server_id,
        database_identity=plan.database_identity,
        venue_id=plan.venue_id,
        account_id=plan.account_id,
        account_mode="independent_sides",
        target_commit=plan.target_commit,
        target_schema_revision=plan.target_schema_revision,
        target_seed_identity=plan.target_seed_identity,
        non_flat_positions=0,
        open_orders=0,
        protection_orders=0,
        nonterminal_tickets=0,
        active_budgets=0,
        unresolved_outcomes=0,
        open_incidents=0,
        active_old_writers=("brc-runtime-monitor.timer",),
        active_new_writers=(),
        exchange_writes_fenced=False,
    )
