"""BRC-only Tokyo cutover adapter with exact mutation allowlists."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from hashlib import sha256
import json
import os
from pathlib import PurePosixPath
import shlex
from typing import Protocol

from pydantic import BaseModel, ConfigDict, field_validator

from scripts.trading_kernel.cutover_tokyo import CutoverPhase
from scripts.trading_kernel.verify_flat_cutover import CutoverFacts, CutoverPlan


EXPECTED_NEW_BRC_UNITS = frozenset(
    {
        "brc-trading-kernel.slice",
        "brc-trading-kernel-entry-worker.service",
        "brc-trading-kernel-lifecycle-worker.service",
        "brc-trading-kernel-observation-worker.service",
        "brc-trading-kernel-reconciliation-worker.service",
    }
)
EXPECTED_NEW_BRC_WRITER_UNITS = frozenset(
    unit for unit in EXPECTED_NEW_BRC_UNITS if unit.endswith(".service")
)
MUTABLE_CONTAINERS = frozenset({"brc-trading-kernel-pg"})
PROTECTED_CONTAINERS = (
    "owner_ai_cpa",
    "owner_ai_new_api",
    "owner_ai_pg",
    "owner_ai_redis",
)
ENTRY_WORKER = "brc-trading-kernel-entry-worker.service"
OBSERVATION_WORKERS = (
    "brc-trading-kernel-observation-worker.service",
)
WRITE_FENCE = PurePosixPath("/etc/brc/trading-kernel.write-fenced")
RUNTIME_ENV = PurePosixPath("/etc/brc/trading-kernel.env")
RELEASE_ROOT = PurePosixPath("/opt/brc/releases")
CURRENT_RELEASE = PurePosixPath("/opt/brc/current")
TARGET_DATABASE_CONTAINER = "brc-trading-kernel-pg"
TARGET_DATABASE_USER = "brc_kernel"
TARGET_DATABASE_NAME = "brc_trading_kernel"


class TokyoInspection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    facts: CutoverFacts
    non_quant_digest: str

    @field_validator("non_quant_digest", mode="before")
    @classmethod
    def _require_digest(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("non-quantitative baseline digest must be non-blank")
        return normalized


class TokyoPhaseState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_writes_fenced: bool = False
    runtime_writers_stopped: bool = False
    snapshot_exists: bool = False
    target_schema_ready: bool = False
    seed_identity_matches: bool = False
    release_active: bool = False
    readonly_certified: bool = False
    observation_enabled: bool = False
    signal_to_ticket_no_write_certified: bool = False
    entry_worker_enabled: bool = False
    exchange_commands_enabled: bool = False


class TokyoSystem(Protocol):
    async def inspect_preconditions(
        self,
        plan: CutoverPlan,
        *,
        old_units: frozenset[str],
        new_units: frozenset[str],
    ) -> TokyoInspection: ...

    async def inspect_phase_state(self, plan: CutoverPlan) -> TokyoPhaseState: ...

    async def read_non_quant_digest(self) -> str: ...

    async def read_persisted_non_quant_baseline(
        self,
        plan: CutoverPlan,
    ) -> str | None: ...

    async def persist_non_quant_baseline(
        self,
        plan: CutoverPlan,
        digest: str,
    ) -> None: ...

    async def fence_new_entry(self, plan: CutoverPlan) -> None: ...

    async def stop_units(
        self,
        plan: CutoverPlan,
        units: tuple[str, ...],
    ) -> None: ...

    async def create_snapshot(self, plan: CutoverPlan) -> None: ...

    async def create_target_database(self, plan: CutoverPlan) -> None: ...

    async def seed_target_authority(self, plan: CutoverPlan) -> None: ...

    async def activate_release(self, plan: CutoverPlan) -> None: ...

    async def certify_readonly(self, plan: CutoverPlan) -> None: ...

    async def enable_observation(self, plan: CutoverPlan) -> None: ...

    async def certify_signal_to_ticket_no_write(self, plan: CutoverPlan) -> None: ...

    async def certify_entry_fenced(self, plan: CutoverPlan) -> None: ...

    async def close(self) -> None: ...


class TokyoCutoverAdapter:
    """Map state-machine phases to one explicit BRC-only Tokyo system boundary."""

    def __init__(self, system: TokyoSystem) -> None:
        self.system = system
        self.mutable_units = EXPECTED_NEW_BRC_UNITS
        self.mutable_containers = set(MUTABLE_CONTAINERS)
        self._non_quant_baseline: str | None = None
        self._latest_non_quant_digest: str | None = None

    async def inspect_preconditions(self, plan: CutoverPlan) -> CutoverFacts:
        inspection = await self.system.inspect_preconditions(
            plan,
            old_units=frozenset(),
            new_units=EXPECTED_NEW_BRC_WRITER_UNITS,
        )
        persisted = await self.system.read_persisted_non_quant_baseline(plan)
        if persisted is not None:
            self._non_quant_baseline = persisted
        elif self._non_quant_baseline is None:
            self._non_quant_baseline = inspection.non_quant_digest
        self._latest_non_quant_digest = inspection.non_quant_digest
        return inspection.facts

    def non_quant_baseline_matches(self) -> bool:
        return (
            self._non_quant_baseline is not None
            and self._latest_non_quant_digest == self._non_quant_baseline
        )

    async def apply_phase(self, phase: CutoverPhase, plan: CutoverPlan) -> None:
        await self._require_non_quant_baseline(plan)
        phase_value = phase.value
        if phase_value == CutoverPhase.FENCE_EXCHANGE_WRITES.value:
            if await self.system.read_persisted_non_quant_baseline(plan) is None:
                baseline = self._non_quant_baseline
                if baseline is None:
                    raise RuntimeError("non-quantitative baseline is unavailable")
                await self.system.persist_non_quant_baseline(plan, baseline)
            await self.system.fence_new_entry(plan)
        elif phase_value == CutoverPhase.STOP_RUNTIME_WRITERS.value:
            await self.system.stop_units(
                plan,
                tuple(sorted(EXPECTED_NEW_BRC_WRITER_UNITS)),
            )
        elif phase_value == CutoverPhase.CREATE_SHORT_LIVED_SNAPSHOT.value:
            await self.system.create_snapshot(plan)
        elif phase_value == CutoverPhase.REBUILD_APPLICATION_SCHEMA.value:
            await self.system.create_target_database(plan)
        elif phase_value == CutoverPhase.SEED_CURRENT_AUTHORITY.value:
            await self.system.seed_target_authority(plan)
        elif phase_value == CutoverPhase.DEPLOY_EXACT_RELEASE.value:
            await self.system.activate_release(plan)
        elif phase_value == CutoverPhase.CERTIFY_SCHEMA_AND_READONLY.value:
            await self.system.certify_readonly(plan)
        elif phase_value == CutoverPhase.ENABLE_OBSERVATION_MONITOR.value:
            await self.system.enable_observation(plan)
        elif phase_value == CutoverPhase.CERTIFY_SIGNAL_TO_TICKET_NO_WRITE.value:
            await self.system.certify_signal_to_ticket_no_write(plan)
        elif phase_value == CutoverPhase.CERTIFY_ENTRY_FENCED.value:
            await self.system.certify_entry_fenced(plan)
        else:
            raise RuntimeError(f"unsupported production cutover phase: {phase.value}")

    async def phase_satisfied(
        self,
        phase: CutoverPhase,
        plan: CutoverPlan,
    ) -> bool:
        await self._require_non_quant_baseline(plan)
        state = await self.system.inspect_phase_state(plan)
        phase_value = phase.value
        if phase_value == CutoverPhase.FENCE_EXCHANGE_WRITES.value:
            return (
                state.exchange_writes_fenced
                and not state.entry_worker_enabled
                and not state.exchange_commands_enabled
            )
        if phase_value == CutoverPhase.STOP_RUNTIME_WRITERS.value:
            return state.runtime_writers_stopped
        if phase_value == CutoverPhase.CREATE_SHORT_LIVED_SNAPSHOT.value:
            return state.snapshot_exists
        if phase_value == CutoverPhase.REBUILD_APPLICATION_SCHEMA.value:
            return state.target_schema_ready
        if phase_value == CutoverPhase.SEED_CURRENT_AUTHORITY.value:
            return state.seed_identity_matches
        if phase_value == CutoverPhase.DEPLOY_EXACT_RELEASE.value:
            return state.release_active
        if phase_value == CutoverPhase.CERTIFY_SCHEMA_AND_READONLY.value:
            return state.readonly_certified
        if phase_value == CutoverPhase.ENABLE_OBSERVATION_MONITOR.value:
            return state.observation_enabled and state.exchange_writes_fenced
        if phase_value == CutoverPhase.CERTIFY_SIGNAL_TO_TICKET_NO_WRITE.value:
            return (
                state.signal_to_ticket_no_write_certified
                and not state.exchange_commands_enabled
            )
        if phase_value == CutoverPhase.CERTIFY_ENTRY_FENCED.value:
            return (
                state.exchange_writes_fenced
                and not state.entry_worker_enabled
                and not state.exchange_commands_enabled
            )
        return False

    async def _require_non_quant_baseline(self, plan: CutoverPlan) -> None:
        persisted = await self.system.read_persisted_non_quant_baseline(plan)
        if persisted is not None:
            self._non_quant_baseline = persisted
        current = await self.system.read_non_quant_digest()
        self._latest_non_quant_digest = current
        if not self.non_quant_baseline_matches():
            raise RuntimeError("non-quantitative baseline changed")

    async def close(self) -> None:
        await self.system.close()


class _RemoteResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    returncode: int
    stdout: str
    stderr: str


class SshCommandRunner:
    def __init__(self, *, target: str, timeout_seconds: float) -> None:
        normalized = target.strip()
        if not normalized or any(character.isspace() for character in normalized):
            raise ValueError("Tokyo SSH target must be one non-blank token")
        if timeout_seconds <= 0:
            raise ValueError("Tokyo SSH timeout must be positive")
        self._target = normalized
        self._timeout_seconds = timeout_seconds

    async def run(
        self,
        argv: tuple[str, ...],
        *,
        check: bool = True,
    ) -> _RemoteResult:
        if not argv or any("\x00" in value for value in argv):
            raise ValueError("remote command arguments must be bounded strings")
        remote_command = shlex.join(argv)
        process = await asyncio.create_subprocess_exec(
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            self._target,
            "--",
            remote_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            raise
        result = _RemoteResult(
            returncode=int(process.returncode or 0),
            stdout=stdout.decode("utf-8", errors="replace").strip(),
            stderr=stderr.decode("utf-8", errors="replace").strip(),
        )
        if check and result.returncode != 0:
            raise RuntimeError(
                f"Tokyo command failed ({result.returncode}): "
                f"{_bounded_error(result.stderr)}"
            )
        return result


class SshTokyoSystem:
    """Production SSH implementation; every mutation target is a fixed constant."""

    def __init__(self, runner: SshCommandRunner) -> None:
        self._runner = runner

    async def inspect_preconditions(
        self,
        plan: CutoverPlan,
        *,
        old_units: frozenset[str],
        new_units: frozenset[str],
    ) -> TokyoInspection:
        release = _release_path(plan)
        manifest = await self._release_manifest(release)
        probe = await self._release_json(
            release,
            "scripts/trading_kernel/probe_production_runtime.py",
        )
        current_counts = await self._current_kernel_counts()
        active_new = await self._active_units(new_units)
        fenced = await self._path_exists(WRITE_FENCE)
        server_id = (await self._runner.run(("hostname",))).stdout
        non_flat_positions = int(str(probe["non_flat_domain_count"]))
        open_orders = int(str(probe["open_order_domain_count"]))
        facts = CutoverFacts(
            server_id=server_id,
            database_identity=(
                TARGET_DATABASE_NAME
                if await self._path_exists(
                    release / "deploy/docker/brc-trading-kernel-postgres.compose.yml"
                )
                else "target-database-definition-missing"
            ),
            venue_id=str(probe["venue_id"]),
            account_id=str(probe["account_id"]),
            account_mode=str(probe["account_position_mode"]),
            target_commit=manifest.get("runtime_commit", "missing"),
            target_schema_revision=manifest.get("schema_revision", "missing"),
            target_seed_identity=manifest.get("seed_identity", "missing"),
            non_flat_positions=non_flat_positions,
            open_orders=open_orders,
            protection_orders=0 if open_orders == 0 else open_orders,
            nonterminal_tickets=current_counts["nonterminal_tickets"],
            active_budgets=current_counts["active_budgets"],
            unresolved_outcomes=current_counts["unresolved_outcomes"],
            open_incidents=current_counts["open_incidents"],
            active_old_writers=(),
            active_new_writers=active_new,
            exchange_writes_fenced=fenced,
        )
        return TokyoInspection(
            facts=facts,
            non_quant_digest=await self._non_quant_digest(),
        )

    async def inspect_phase_state(self, plan: CutoverPlan) -> TokyoPhaseState:
        release = _release_path(plan)
        entry_enabled = (
            await self._unit_enabled(ENTRY_WORKER)
            or await self._unit_active(ENTRY_WORKER)
        )
        exchange_commands_enabled = await self._target_boolean(
            "SELECT enabled FROM brc_runtime_capabilities_current "
            "WHERE capability_key = 'exchange_commands'"
        )
        return TokyoPhaseState(
            exchange_writes_fenced=await self._path_exists(WRITE_FENCE),
            runtime_writers_stopped=await self._units_stopped_and_disabled(
                EXPECTED_NEW_BRC_WRITER_UNITS
            ),
            snapshot_exists=await self._path_exists(_snapshot_path(plan)),
            target_schema_ready=await self._target_schema_ready(release),
            seed_identity_matches=(
                await self._target_authority_identity_matches(plan)
            ),
            release_active=(await self._readlink(CURRENT_RELEASE)) == str(release),
            readonly_certified=await self._readonly_certified(release, plan),
            observation_enabled=all(
                [
                    await self._unit_enabled(unit)
                    and await self._unit_active(unit)
                    for unit in OBSERVATION_WORKERS
                ]
            ),
            signal_to_ticket_no_write_certified=(
                await self._target_schema_ready(release)
                and await self._target_int("SELECT count(*) FROM brc_trade_tickets")
                == 0
                and await self._target_int(
                    "SELECT count(*) FROM brc_exchange_commands"
                )
                == 0
            ),
            entry_worker_enabled=entry_enabled,
            exchange_commands_enabled=exchange_commands_enabled,
        )

    async def read_non_quant_digest(self) -> str:
        return await self._non_quant_digest()

    async def read_persisted_non_quant_baseline(
        self,
        plan: CutoverPlan,
    ) -> str | None:
        result = await self._runner.run(
            ("sudo", "cat", str(_non_quant_baseline_path(plan))),
            check=False,
        )
        return result.stdout if result.returncode == 0 and result.stdout else None

    async def persist_non_quant_baseline(
        self,
        plan: CutoverPlan,
        digest: str,
    ) -> None:
        if not digest.startswith("sha256:") or len(digest) != 71:
            raise ValueError("non-quantitative baseline must be a sha256 identity")
        path = _non_quant_baseline_path(plan)
        await self._runner.run(
            ("sudo", "install", "-d", "-m", "0700", str(path.parent))
        )
        await self._runner.run(
            (
                "sudo",
                "python3",
                "-c",
                (
                    "from pathlib import Path; import sys; "
                    "Path(sys.argv[1]).write_text(sys.argv[2], encoding='utf-8')"
                ),
                str(path),
                digest,
            )
        )
        await self._runner.run(("sudo", "chmod", "0600", str(path)))

    async def fence_new_entry(self, plan: CutoverPlan) -> None:
        del plan
        await self._runner.run(
            (
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
        )
        await self._runner.run(
            ("sudo", "touch", str(WRITE_FENCE))
        )
        await self._runner.run(
            ("sudo", "systemctl", "disable", "--now", ENTRY_WORKER),
            check=False,
        )

    async def stop_units(
        self,
        plan: CutoverPlan,
        units: tuple[str, ...],
    ) -> None:
        del plan
        if set(units) != set(EXPECTED_NEW_BRC_WRITER_UNITS):
            raise RuntimeError("runtime writer stop target differs from exact allowlist")
        for unit in units:
            await self._runner.run(
                ("sudo", "systemctl", "stop", unit),
                check=False,
            )
            await self._runner.run(
                ("sudo", "systemctl", "disable", unit),
                check=False,
            )

    async def create_snapshot(self, plan: CutoverPlan) -> None:
        snapshot = _snapshot_path(plan)
        container_snapshot = f"/tmp/{plan.cutover_id}.pgdump"
        await self._runner.run(
            ("sudo", "install", "-d", "-m", "0700", str(snapshot.parent))
        )
        await self._runner.run(
            (
                "sudo",
                "docker",
                "exec",
                TARGET_DATABASE_CONTAINER,
                "pg_dump",
                "-U",
                TARGET_DATABASE_USER,
                "-d",
                TARGET_DATABASE_NAME,
                "-Fc",
                "-f",
                container_snapshot,
            )
        )
        await self._runner.run(
            (
                "sudo",
                "docker",
                "cp",
                f"{TARGET_DATABASE_CONTAINER}:{container_snapshot}",
                str(snapshot),
            )
        )
        await self._runner.run(
            (
                "sudo",
                "docker",
                "exec",
                TARGET_DATABASE_CONTAINER,
                "rm",
                "-f",
                container_snapshot,
            )
        )
        await self._runner.run(("sudo", "chmod", "0600", str(snapshot)))

    async def create_target_database(self, plan: CutoverPlan) -> None:
        release = _release_path(plan)
        await self._runner.run(
            (
                "sudo",
                "docker",
                "exec",
                TARGET_DATABASE_CONTAINER,
                "psql",
                "-U",
                TARGET_DATABASE_USER,
                "-d",
                TARGET_DATABASE_NAME,
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                "DROP SCHEMA public CASCADE; "
                "CREATE SCHEMA public AUTHORIZATION brc_kernel",
            )
        )
        await self._release_python(
            release,
            "scripts/trading_kernel/bootstrap_schema.py",
        )

    async def seed_target_authority(self, plan: CutoverPlan) -> None:
        release = _release_path(plan)
        await self._install_runtime_identity(plan)
        result = await self._release_python(
            release,
            "scripts/trading_kernel/seed_runtime_authority.py",
            "deploy-identity",
            "--account-id",
            plan.account_id,
            "--runtime-commit",
            plan.target_commit,
            "--schema-revision",
            plan.target_schema_revision,
        )
        payload = json.loads(result.stdout)
        if payload.get("runtime_seed_semantic_hash") != plan.target_seed_identity:
            raise RuntimeError("runtime authority seed identity differs from plan")

    async def activate_release(self, plan: CutoverPlan) -> None:
        release = _release_path(plan)
        await self._install_runtime_identity(plan)
        for unit in sorted(EXPECTED_NEW_BRC_UNITS):
            await self._runner.run(
                (
                    "sudo",
                    "install",
                    "-m",
                    "0644",
                    str(release / f"deploy/systemd/{unit}"),
                    f"/etc/systemd/system/{unit}",
                )
            )
        await self._runner.run(("sudo", "ln", "-sfn", str(release), str(CURRENT_RELEASE)))
        await self._runner.run(("sudo", "systemctl", "daemon-reload"))
        await self._runner.run(
            ("sudo", "systemctl", "disable", "--now", ENTRY_WORKER),
            check=False,
        )

    async def certify_readonly(self, plan: CutoverPlan) -> None:
        release = _release_path(plan)
        for script, args in (
            ("scripts/trading_kernel/verify_schema.py", ()),
            ("scripts/trading_kernel/certify_readonly.py", ("--require-flat",)),
            ("scripts/trading_kernel/probe_production_runtime.py", ()),
        ):
            result = await self._release_python(release, script, *args)
            payload = json.loads(result.stdout)
            if payload.get("status", "pass") != "pass":
                raise RuntimeError(f"readonly certification failed: {script}")
            if script.endswith("certify_readonly.py"):
                runtime_identity = payload.get("runtime_identity")
                if not isinstance(runtime_identity, Mapping):
                    raise RuntimeError(
                        "readonly certification omitted runtime identity"
                    )
                _require_runtime_identity(runtime_identity, plan)
            if script.endswith("probe_production_runtime.py"):
                if (
                    payload.get("venue_id") != plan.venue_id
                    or payload.get("account_id") != plan.account_id
                    or payload.get("account_position_mode")
                    != "independent_sides"
                ):
                    raise RuntimeError(
                        "readonly production identity differs from plan"
                    )

    async def enable_observation(self, plan: CutoverPlan) -> None:
        del plan
        for unit in OBSERVATION_WORKERS:
            await self._runner.run(
                ("sudo", "systemctl", "enable", "--now", unit)
            )
        await self._runner.run(
            ("sudo", "systemctl", "disable", "--now", ENTRY_WORKER),
            check=False,
        )

    async def certify_signal_to_ticket_no_write(self, plan: CutoverPlan) -> None:
        await self.certify_entry_fenced(plan)
        release = _release_path(plan)
        await self._release_python(
            release,
            "scripts/trading_kernel/run_observation_worker_once.py",
            "--market-source-factory",
            "src.trading_kernel.infrastructure.production_runtime:build_binance_usdm_market_source",
            "--worker-id",
            "cutover-observation-certifier",
            "--runtime-commit",
            plan.target_commit,
            "--schema-revision",
            plan.target_schema_revision,
        )
        if await self._target_int("SELECT count(*) FROM brc_trade_tickets") != 0:
            raise RuntimeError("no-write certification created a Ticket")
        if await self._target_int("SELECT count(*) FROM brc_exchange_commands") != 0:
            raise RuntimeError("no-write certification created an Exchange Command")

    async def certify_entry_fenced(self, plan: CutoverPlan) -> None:
        del plan
        if not await self._path_exists(WRITE_FENCE):
            raise RuntimeError("new ENTRY write fence is missing")
        if await self._unit_enabled(ENTRY_WORKER) or await self._unit_active(
            ENTRY_WORKER
        ):
            raise RuntimeError("ENTRY worker is enabled during readonly cutover")
        if await self._target_boolean(
            "SELECT new_entry_submit_enabled FROM brc_owner_policy_current "
            "WHERE owner_policy_id = 'policy-main'"
        ):
            raise RuntimeError("Owner Policy grants new ENTRY submit during cutover")
        if await self._target_boolean(
            "SELECT enabled FROM brc_runtime_capabilities_current "
            "WHERE capability_key = 'exchange_commands'"
        ):
            raise RuntimeError("exchange command capability is enabled during cutover")

    async def close(self) -> None:
        return None

    async def _release_manifest(
        self,
        release: PurePosixPath,
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, filename in (
            ("runtime_commit", ".brc-runtime-commit"),
            ("schema_revision", ".brc-schema-revision"),
            ("seed_identity", ".brc-seed-identity"),
        ):
            value = await self._runner.run(
                ("sudo", "cat", str(release / filename)),
                check=False,
            )
            if value.returncode == 0:
                result[key] = value.stdout
        return result

    async def _current_kernel_counts(self) -> dict[str, int]:
        queries = {
            "nonterminal_tickets": (
                "SELECT count(*) FROM brc_trade_tickets "
                "WHERE terminal_at_ms IS NULL"
            ),
            "active_budgets": (
                "SELECT count(*) FROM brc_budget_reservations "
                "WHERE status = 'active'"
            ),
            "unresolved_outcomes": (
                "SELECT count(*) FROM brc_exchange_commands "
                "WHERE status IN "
                "('prepared','dispatch_started','claimed','outcome_unknown') "
            ),
            "open_incidents": (
                "SELECT count(*) FROM brc_runtime_incidents "
                "WHERE status <> 'resolved'"
            ),
        }
        return {
            key: int((await self._target_scalar(query)) or "0")
            for key, query in queries.items()
        }

    async def _target_scalar(self, query: str) -> str | None:
        result = await self._runner.run(
            (
                "sudo",
                "docker",
                "exec",
                TARGET_DATABASE_CONTAINER,
                "psql",
                "-U",
                TARGET_DATABASE_USER,
                "-d",
                TARGET_DATABASE_NAME,
                "-Atqc",
                query,
            ),
            check=False,
        )
        return result.stdout if result.returncode == 0 and result.stdout else None

    async def _target_int(self, query: str) -> int:
        return int((await self._target_scalar(query)) or "0")

    async def _target_boolean(self, query: str) -> bool:
        return (await self._target_scalar(query)) in {"t", "true", "1"}

    async def _target_schema_ready(self, release: PurePosixPath) -> bool:
        if not await self._container_running(TARGET_DATABASE_CONTAINER):
            return False
        result = await self._release_python(
            release,
            "scripts/trading_kernel/verify_schema.py",
            check=False,
        )
        if result.returncode != 0:
            return False
        return json.loads(result.stdout).get("status") == "pass"

    async def _readonly_certified(
        self,
        release: PurePosixPath,
        plan: CutoverPlan,
    ) -> bool:
        result = await self._release_python(
            release,
            "scripts/trading_kernel/certify_readonly.py",
            "--require-flat",
            check=False,
        )
        if result.returncode != 0:
            return False
        payload = json.loads(result.stdout)
        runtime_identity = payload.get("runtime_identity")
        if payload.get("status") != "pass" or not isinstance(
            runtime_identity,
            Mapping,
        ):
            return False
        try:
            _require_runtime_identity(runtime_identity, plan)
        except RuntimeError:
            return False
        return True

    async def _install_runtime_identity(self, plan: CutoverPlan) -> None:
        replacements = (
            ("TRADING_KERNEL_RUNTIME_COMMIT", plan.target_commit),
            ("TRADING_KERNEL_SCHEMA_REVISION", plan.target_schema_revision),
        )
        for key, value in replacements:
            await self._runner.run(
                (
                    "sudo",
                    "sed",
                    "-i",
                    f"s/^{key}=.*/{key}={value}/",
                    str(RUNTIME_ENV),
                )
            )
        for key, value in replacements:
            await self._runner.run(
                (
                    "sudo",
                    "grep",
                    "-Fxc",
                    f"{key}={value}",
                    str(RUNTIME_ENV),
                )
            )

    async def _target_authority_identity_matches(
        self,
        plan: CutoverPlan,
    ) -> bool:
        runtime_commit = await self._target_scalar(
            "SELECT metadata_value AS runtime_commit "
            "FROM brc_schema_metadata "
            "WHERE metadata_key = 'runtime_commit'"
        )
        schema_revision = await self._target_scalar(
            "SELECT metadata_value AS schema_revision "
            "FROM brc_schema_metadata "
            "WHERE metadata_key = 'schema_revision'"
        )
        seed_identity = await self._target_scalar(
            "SELECT metadata_value AS seed_identity "
            "FROM brc_schema_metadata "
            "WHERE metadata_key = 'seed_identity'"
        )
        capability_mismatch_count = await self._target_scalar(
            "SELECT count(*) AS capability_mismatch_count "
            "FROM brc_runtime_capabilities_current "
            f"WHERE certified_commit <> '{plan.target_commit}' "
            f"OR schema_revision <> '{plan.target_schema_revision}'"
        )
        return (
            runtime_commit == plan.target_commit
            and schema_revision == plan.target_schema_revision
            and seed_identity == plan.target_seed_identity
            and capability_mismatch_count == "0"
            and await self._runtime_identity_env_matches(plan)
        )

    async def _runtime_identity_env_matches(self, plan: CutoverPlan) -> bool:
        for key, value in (
            ("TRADING_KERNEL_RUNTIME_COMMIT", plan.target_commit),
            ("TRADING_KERNEL_SCHEMA_REVISION", plan.target_schema_revision),
        ):
            result = await self._runner.run(
                (
                    "sudo",
                    "grep",
                    "-Fxc",
                    f"{key}={value}",
                    str(RUNTIME_ENV),
                ),
                check=False,
            )
            if result.returncode != 0 or result.stdout != "1":
                return False
        return True

    async def _release_json(
        self,
        release: PurePosixPath,
        script: str,
    ) -> Mapping[str, object]:
        result = await self._release_python(release, script)
        payload = json.loads(result.stdout)
        if not isinstance(payload, Mapping):
            raise RuntimeError("Tokyo release command did not return a JSON object")
        return payload

    async def _release_python(
        self,
        release: PurePosixPath,
        script: str,
        *args: str,
        check: bool = True,
    ) -> _RemoteResult:
        executable = shlex.join(
            (
                str(release / ".venv/bin/python"),
                str(release / script),
                *args,
            )
        )
        command = (
            f"set -a; . {shlex.quote(str(RUNTIME_ENV))}; "
            f"set +a; exec {executable}"
        )
        return await self._runner.run(
            ("sudo", "-u", "brc", "/bin/bash", "-lc", command),
            check=check,
        )

    async def _active_units(self, units: frozenset[str]) -> tuple[str, ...]:
        active: list[str] = []
        for unit in sorted(units):
            result = await self._runner.run(
                ("sudo", "systemctl", "is-active", "--quiet", unit),
                check=False,
            )
            if result.returncode == 0:
                active.append(unit)
        return tuple(active)

    async def _unit_enabled(self, unit: str) -> bool:
        result = await self._runner.run(
            ("sudo", "systemctl", "is-enabled", unit),
            check=False,
        )
        return result.stdout in {"enabled", "enabled-runtime"}

    async def _unit_active(self, unit: str) -> bool:
        result = await self._runner.run(
            ("sudo", "systemctl", "is-active", "--quiet", unit),
            check=False,
        )
        return result.returncode == 0

    async def _units_stopped_and_disabled(
        self,
        units: frozenset[str],
    ) -> bool:
        for unit in units:
            if await self._unit_active(unit) or await self._unit_enabled(unit):
                return False
        return True

    async def _path_exists(self, path: PurePosixPath) -> bool:
        return (
            await self._runner.run(("sudo", "test", "-e", str(path)), check=False)
        ).returncode == 0

    async def _readlink(self, path: PurePosixPath) -> str | None:
        result = await self._runner.run(
            ("sudo", "readlink", "-f", str(path)),
            check=False,
        )
        return result.stdout if result.returncode == 0 else None

    async def _container_running(self, container: str) -> bool:
        if container not in MUTABLE_CONTAINERS and container not in PROTECTED_CONTAINERS:
            raise RuntimeError("container inspection target is outside allowlist")
        result = await self._runner.run(
            (
                "sudo",
                "docker",
                "inspect",
                "--format",
                "{{.State.Running}}",
                container,
            ),
            check=False,
        )
        return result.returncode == 0 and result.stdout == "true"

    async def _non_quant_digest(self) -> str:
        values: list[str] = []
        for container in PROTECTED_CONTAINERS:
            result = await self._runner.run(
                (
                    "sudo",
                    "docker",
                    "inspect",
                    "--format",
                    "{{.Name}}|{{.Id}}|{{.Image}}|{{.State.Running}}|{{.RestartCount}}",
                    container,
                )
            )
            values.append(result.stdout)
        for service in ("docker.service", "nginx.service", "ssh.service"):
            result = await self._runner.run(
                ("sudo", "systemctl", "is-active", service)
            )
            values.append(f"{service}:{result.stdout}")
        nginx = await self._runner.run(
            (
                "sudo",
                "sha256sum",
                "/etc/nginx/sites-enabled/owner-ai-gateway",
            )
        )
        values.append(nginx.stdout)
        canonical = "\n".join(sorted(values)).encode("utf-8")
        return f"sha256:{sha256(canonical).hexdigest()}"


def build_tokyo_cutover_adapter() -> TokyoCutoverAdapter:
    target = os.getenv("TRADING_KERNEL_TOKYO_SSH_TARGET", "tokyo").strip()
    raw_timeout = os.getenv("TRADING_KERNEL_TOKYO_SSH_TIMEOUT_SECONDS", "30").strip()
    try:
        timeout_seconds = float(raw_timeout)
    except ValueError as exc:
        raise ValueError("Tokyo SSH timeout must be numeric") from exc
    return TokyoCutoverAdapter(
        SshTokyoSystem(
            SshCommandRunner(target=target, timeout_seconds=timeout_seconds)
        )
    )


def _release_path(plan: CutoverPlan) -> PurePosixPath:
    if "/" in plan.target_release_id or ".." in plan.target_release_id:
        raise ValueError("target release identity must not contain a path")
    return RELEASE_ROOT / plan.target_release_id


def _require_runtime_identity(
    runtime_identity: Mapping[str, object],
    plan: CutoverPlan,
) -> None:
    expected = {
        "runtime_commit": plan.target_commit,
        "schema_revision": plan.target_schema_revision,
        "seed_identity": plan.target_seed_identity,
    }
    actual = {key: str(runtime_identity.get(key) or "") for key in expected}
    if actual != expected or set(runtime_identity) != set(expected):
        raise RuntimeError("readonly runtime identity differs from cutover plan")


def _snapshot_path(plan: CutoverPlan) -> PurePosixPath:
    return PurePosixPath("/opt/brc/cutover") / plan.cutover_id / "legacy-brc.pgdump"


def _non_quant_baseline_path(plan: CutoverPlan) -> PurePosixPath:
    return (
        PurePosixPath("/opt/brc/cutover")
        / plan.cutover_id
        / "non-quant-baseline.sha256"
    )


def _bounded_error(value: str) -> str:
    return value.replace("\n", " ")[:1_000]
