from __future__ import annotations

import importlib
from enum import StrEnum
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

    assert adapter.mutable_units == module.EXPECTED_NEW_BRC_UNITS
    assert adapter.mutable_containers == {"brc-trading-kernel-pg"}
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
async def test_cutover_phase_actions_preserve_entry_fence_and_runtime_workers() -> None:
    module = _production_adapter_module()
    system = FakeTokyoSystem(module, _facts())
    adapter = module.TokyoCutoverAdapter(system)
    plan = _plan()
    await adapter.inspect_preconditions(plan)

    await adapter.apply_phase(CutoverPhase.FENCE_EXCHANGE_WRITES, plan)
    await adapter.apply_phase(CutoverPhase.STOP_RUNTIME_WRITERS, plan)
    await adapter.apply_phase(CutoverPhase.CERTIFY_ENTRY_FENCED, plan)

    assert system.actions == [
        ("fence_new_entry", ()),
        ("stop_units", tuple(sorted(module.EXPECTED_NEW_BRC_WRITER_UNITS))),
        ("certify_entry_fenced", ()),
    ]
    assert await adapter.phase_satisfied(
        CutoverPhase.CERTIFY_ENTRY_FENCED,
        plan,
    )
    assert system.phase_state.exchange_writes_fenced is True
    assert system.phase_state.entry_worker_enabled is False
    assert system.phase_state.exchange_commands_enabled is False


@pytest.mark.asyncio
async def test_cutover_accepts_equivalent_phase_from_cli_main_module() -> None:
    module = _production_adapter_module()
    system = FakeTokyoSystem(module, _facts())
    adapter = module.TokyoCutoverAdapter(system)
    plan = _plan()
    await adapter.inspect_preconditions(plan)

    class MainModulePhase(StrEnum):
        FENCE_EXCHANGE_WRITES = "fence_exchange_writes"

    await adapter.apply_phase(MainModulePhase.FENCE_EXCHANGE_WRITES, plan)

    assert system.actions == [("fence_new_entry", ())]


@pytest.mark.asyncio
async def test_ssh_system_phase_inspection_returns_typed_state() -> None:
    module = _production_adapter_module()
    system = module.SshTokyoSystem(AlwaysMissingRunner(module))

    state = await system.inspect_phase_state(_plan())

    assert isinstance(state, module.TokyoPhaseState)
    assert state.runtime_writers_stopped is True
    assert state.entry_worker_enabled is False
    assert state.exchange_commands_enabled is False


@pytest.mark.asyncio
async def test_static_inactive_service_counts_as_stopped_and_disabled() -> None:
    module = _production_adapter_module()
    system = module.SshTokyoSystem(StaticInactiveUnitRunner(module))

    stopped = await system._units_stopped_and_disabled(
        frozenset(
            {
                "brc-runtime-monitor.service",
                "brc-runtime-monitor.timer",
            }
        )
    )

    assert stopped is True


@pytest.mark.asyncio
async def test_entry_fence_keeps_runtime_directory_traversable_by_brc() -> None:
    module = _production_adapter_module()
    runner = RecordingRunner(module)
    system = module.SshTokyoSystem(runner)

    await system.fence_new_entry(_plan())

    assert runner.commands[0] == (
        "sudo",
        "install",
        "-d",
        "-o",
        "root",
        "-g",
        "brc",
        "-m",
        "0750",
        "/etc/brc",
    )


@pytest.mark.asyncio
async def test_target_database_rebuilds_only_brc_volume_before_bootstrap() -> None:
    module = _production_adapter_module()
    runner = RecordingRunner(module)
    system = module.SshTokyoSystem(runner)

    await system.create_target_database(_plan())

    assert runner.commands[0][-2:] == ("down", "-v")
    assert runner.commands[1][-5:] == (
        "up",
        "-d",
        "--wait",
        "--wait-timeout",
        "60",
    )


@pytest.mark.asyncio
async def test_runtime_identity_env_is_updated_and_verified_exactly() -> None:
    module = _production_adapter_module()
    runner = RecordingRunner(module)
    system = module.SshTokyoSystem(runner)
    plan = _plan()

    await system._install_runtime_identity(plan)

    assert runner.commands == [
        (
            "sudo",
            "sed",
            "-i",
            "s/^TRADING_KERNEL_RUNTIME_COMMIT=.*/"
            f"TRADING_KERNEL_RUNTIME_COMMIT={plan.target_commit}/",
            "/etc/brc/trading-kernel.env",
        ),
        (
            "sudo",
            "sed",
            "-i",
            "s/^TRADING_KERNEL_SCHEMA_REVISION=.*/"
            f"TRADING_KERNEL_SCHEMA_REVISION={plan.target_schema_revision}/",
            "/etc/brc/trading-kernel.env",
        ),
        (
            "sudo",
            "grep",
            "-Fxc",
            f"TRADING_KERNEL_RUNTIME_COMMIT={plan.target_commit}",
            "/etc/brc/trading-kernel.env",
        ),
        (
            "sudo",
            "grep",
            "-Fxc",
            f"TRADING_KERNEL_SCHEMA_REVISION={plan.target_schema_revision}",
            "/etc/brc/trading-kernel.env",
        ),
    ]


@pytest.mark.asyncio
async def test_seed_uses_explicit_plan_identity_not_stale_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _production_adapter_module()
    system = module.SshTokyoSystem(RecordingRunner(module))
    plan = _plan()
    calls: list[tuple[str, ...]] = []

    async def install_identity(received_plan: CutoverPlan) -> None:
        assert received_plan == plan

    async def release_python(
        release,
        script: str,
        *args: str,
        check: bool = True,
    ) -> object:
        del release, check
        calls.append((script, *args))
        return module._RemoteResult(
            returncode=0,
            stdout=(
                '{"runtime_seed_semantic_hash":"'
                f'{plan.target_seed_identity}'
                '"}'
            ),
            stderr="",
        )

    monkeypatch.setattr(system, "_install_runtime_identity", install_identity)
    monkeypatch.setattr(system, "_release_python", release_python)

    await system.seed_target_authority(plan)

    assert calls == [
        (
            "scripts/trading_kernel/seed_runtime_authority.py",
            "deploy-identity",
            "--account-id",
            plan.account_id,
            "--runtime-commit",
            plan.target_commit,
            "--schema-revision",
            plan.target_schema_revision,
        )
    ]


def test_readonly_certification_requires_exact_plan_identity() -> None:
    module = _production_adapter_module()
    plan = _plan()
    exact = {
        "runtime_commit": plan.target_commit,
        "schema_revision": plan.target_schema_revision,
        "seed_identity": plan.target_seed_identity,
    }

    module._require_runtime_identity(exact, plan)

    with pytest.raises(RuntimeError, match="runtime identity differs"):
        module._require_runtime_identity(
            {**exact, "runtime_commit": "c" * 40},
            plan,
        )


@pytest.mark.asyncio
async def test_current_kernel_counts_never_read_retired_database() -> None:
    module = _production_adapter_module()
    runner = RecordingRunner(module)
    system = module.SshTokyoSystem(runner)

    counts = await system._current_kernel_counts()

    assert counts == {
        "nonterminal_tickets": 0,
        "active_budgets": 0,
        "unresolved_outcomes": 0,
        "open_incidents": 0,
    }
    commands = "\n".join(" ".join(command) for command in runner.commands)
    assert "brc-trading-kernel-pg" in commands
    assert "brc_prelive_dryrun" not in commands
    assert "dingdingbot-pg" not in commands


@pytest.mark.asyncio
async def test_seed_phase_identity_requires_metadata_capabilities_and_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _production_adapter_module()
    system = module.SshTokyoSystem(RecordingRunner(module))
    plan = _plan()
    values = {
        "runtime_commit": plan.target_commit,
        "schema_revision": plan.target_schema_revision,
        "seed_identity": plan.target_seed_identity,
        "capability_mismatch_count": "0",
    }

    async def target_scalar(query: str) -> str | None:
        for key in (
            "capability_mismatch_count",
            "seed_identity",
            "schema_revision",
            "runtime_commit",
        ):
            if key in query:
                return values[key]
        raise AssertionError(f"unexpected identity query: {query}")

    async def env_matches(received_plan: CutoverPlan) -> bool:
        assert received_plan == plan
        return True

    monkeypatch.setattr(system, "_target_scalar", target_scalar)
    monkeypatch.setattr(system, "_runtime_identity_env_matches", env_matches)

    assert await system._target_authority_identity_matches(plan) is True

    values["runtime_commit"] = "c" * 40
    assert await system._target_authority_identity_matches(plan) is False


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


class StaticInactiveUnitRunner:
    def __init__(self, module: ModuleType) -> None:
        self.module = module

    async def run(
        self,
        argv: tuple[str, ...],
        *,
        check: bool = True,
    ) -> object:
        del check
        if "is-active" in argv:
            return self.module._RemoteResult(
                returncode=1,
                stdout="inactive",
                stderr="",
            )
        if "is-enabled" in argv and argv[-1].endswith(".service"):
            return self.module._RemoteResult(
                returncode=0,
                stdout="static",
                stderr="",
            )
        if "is-enabled" in argv:
            return self.module._RemoteResult(
                returncode=1,
                stdout="disabled",
                stderr="",
            )
        raise AssertionError(f"unexpected command: {argv!r}")


class RecordingRunner:
    def __init__(self, module: ModuleType) -> None:
        self.module = module
        self.commands: list[tuple[str, ...]] = []

    async def run(
        self,
        argv: tuple[str, ...],
        *,
        check: bool = True,
    ) -> object:
        del check
        self.commands.append(argv)
        return self.module._RemoteResult(returncode=0, stdout="", stderr="")


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
                "entry_worker_enabled": False,
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
            update={"runtime_writers_stopped": True}
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
        active_old_writers=(),
        active_new_writers=("brc-trading-kernel-entry-worker.service",),
        exchange_writes_fenced=False,
    )
