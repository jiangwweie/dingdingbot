#!/usr/bin/env python3
"""Deploy one committed Trading Kernel release through bounded Tokyo gates."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)

SCHEMA_REVISION = CURRENT_SCHEMA_REVISION
COMPATIBLE_SOURCE_SCHEMA_REVISION = "0002_sor_v3_strategy_group_capacity"
EXPECTED_CONFIGURED_LEVERAGE = 5
RELEASE_ROOT = "/opt/brc/releases"
CURRENT_RELEASE = "/opt/brc/current"
RUNTIME_ENV = "/etc/brc/trading-kernel.env"
WRITE_FENCE = "/etc/brc/trading-kernel.write-fenced"
ENTRY_SERVICE = "brc-trading-kernel-entry-worker.service"
LIFECYCLE_SERVICE = "brc-trading-kernel-lifecycle-worker.service"
SAFETY_SERVICES = (
    "brc-trading-kernel-observation-worker.service",
    LIFECYCLE_SERVICE,
    "brc-trading-kernel-reconciliation-worker.service",
)
ALL_SERVICES = (
    "brc-trading-kernel-observation-worker.service",
    ENTRY_SERVICE,
    "brc-trading-kernel-lifecycle-worker.service",
    "brc-trading-kernel-reconciliation-worker.service",
)
SYSTEMD_UNITS = (
    "brc-trading-kernel.slice",
    *ALL_SERVICES,
)
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SEED_IDENTITY = re.compile(r"^sha256:[0-9a-f]{64}$")


class DeploymentBlocked(RuntimeError):
    """Preflight or postflight facts do not satisfy the release contract."""


class DeploymentMode(StrEnum):
    REGULAR = "regular"
    COMPATIBLE_UPGRADE = "compatible_upgrade"


@dataclass(frozen=True)
class DeploymentPlan:
    target_commit: str
    target_release: str
    schema_revision: str
    expected_configured_leverage: int
    enable_entry: bool
    source_schema_revision: str | None = None
    mode: DeploymentMode = DeploymentMode.REGULAR
    closure_ticket_id: str | None = None

    def __post_init__(self) -> None:
        if not _COMMIT.fullmatch(self.target_commit):
            raise ValueError("target commit must be an exact lowercase 40-hex SHA")
        expected_release = (
            f"{RELEASE_ROOT}/brc-trading-kernel-{self.target_commit[:12]}"
        )
        if self.target_release != expected_release:
            raise ValueError("target release path differs from target commit")
        if self.mode is DeploymentMode.REGULAR:
            if self.source_schema_revision is not None:
                raise ValueError("regular deployment cannot change schema revision")
            if self.schema_revision != SCHEMA_REVISION:
                raise ValueError("regular deployment cannot change schema revision")
        elif self.mode is DeploymentMode.COMPATIBLE_UPGRADE:
            if self.source_schema_revision != COMPATIBLE_SOURCE_SCHEMA_REVISION:
                raise ValueError("compatible upgrade requires the exact 0002 source")
            if self.schema_revision != SCHEMA_REVISION:
                raise ValueError("compatible upgrade requires the current schema head")
            if self.closure_ticket_id is not None:
                raise ValueError("compatible upgrade requires fully terminal history")
            if self.enable_entry:
                raise ValueError("compatible upgrade must keep ENTRY disabled")
        else:
            raise ValueError("unsupported deployment mode")
        if self.expected_configured_leverage != EXPECTED_CONFIGURED_LEVERAGE:
            raise ValueError("production configured leverage must remain fixed at 5x")
        if self.closure_ticket_id is not None and not self.closure_ticket_id.strip():
            raise ValueError("closure-only Ticket identity must be non-blank")
        if self.closure_ticket_id is not None and self.enable_entry:
            raise ValueError("closure-only handover must keep ENTRY fenced")


@dataclass(frozen=True)
class DeploymentResult:
    status: str
    target_commit: str
    target_release: str
    schema_revision: str
    configured_leverage: int
    entry_enabled: bool
    mode: DeploymentMode


class TokyoReleaseBackend(Protocol):
    def read_current_release(self) -> str: ...

    def release_exists(self, release: str) -> bool: ...

    def inspect_schema(self, release: str) -> Mapping[str, object]: ...

    def certify_flat(self, release: str) -> Mapping[str, object]: ...

    def certify_closure(
        self,
        release: str,
        ticket_id: str,
    ) -> Mapping[str, object]: ...

    def probe_exchange(self, release: str) -> Mapping[str, object]: ...

    def certify_compatible_source(
        self,
        release: str,
        source_schema_revision: str,
    ) -> Mapping[str, object]: ...

    def read_release_marker(self, release: str, marker: str) -> str: ...

    def stop_services(self, services: tuple[str, ...]) -> None: ...

    def services_active(self, services: tuple[str, ...]) -> frozenset[str]: ...

    def migration_writers_stopped_and_entry_fenced(self) -> bool: ...

    def install_release(self, commit: str, release: str) -> None: ...

    def deploy_identity(
        self,
        release: str,
        commit: str,
        schema_revision: str,
    ) -> Mapping[str, object]: ...

    def migrate_schema(
        self,
        release: str,
        source_schema_revision: str,
        target_schema_revision: str,
    ) -> None: ...

    def verify_preservation(
        self,
        release: str,
        source_schema_revision: str,
        expected_digest: str,
    ) -> Mapping[str, object]: ...

    def persist_preservation_digest(self, release: str, digest: str) -> None: ...

    def read_preservation_digest(self, release: str) -> str: ...

    def mark_preservation_verified(self, release: str, digest: str) -> None: ...

    def preservation_verified(self, release: str, digest: str) -> bool: ...

    def deploy_compatible_identity(
        self,
        release: str,
        commit: str,
        schema_revision: str,
    ) -> Mapping[str, object]: ...

    def deploy_closure_identity(
        self,
        release: str,
        commit: str,
        schema_revision: str,
        ticket_id: str,
    ) -> Mapping[str, object]: ...

    def activate_release(
        self,
        release: str,
        commit: str,
        schema_revision: str,
        seed_identity: str,
    ) -> None: ...

    def start_services(self, services: tuple[str, ...]) -> None: ...

    def bootstrap_strategy_universes(self, release: str) -> None: ...

    def unfence_entry(self) -> None: ...

    def fence_entry(self) -> None: ...

    def entry_is_inactive_disabled_and_fenced(self) -> bool: ...


def deploy_tokyo_release(
    backend: TokyoReleaseBackend,
    plan: DeploymentPlan,
) -> DeploymentResult:
    if plan.mode is DeploymentMode.COMPATIBLE_UPGRADE:
        return _deploy_compatible_upgrade(backend, plan)
    current_release = backend.read_current_release()
    if current_release == plan.target_release:
        raise DeploymentBlocked("target release is already current")
    backend.install_release(plan.target_commit, plan.target_release)
    _, _, current_identity = _read_release_facts(backend, plan)
    _require_marker(
        backend,
        current_release,
        ".brc-runtime-commit",
        str(current_identity["runtime_commit"]),
    )
    _require_marker(
        backend,
        current_release,
        ".brc-schema-revision",
        plan.schema_revision,
    )

    services_stopped = False
    identity_rotated = False
    target_release_activated = False
    try:
        backend.stop_services(ALL_SERVICES)
        services_stopped = True
        backend.fence_entry()
        active_after_stop = backend.services_active(ALL_SERVICES)
        if active_after_stop:
            raise DeploymentBlocked(
                "runtime services did not stop: "
                + ",".join(sorted(active_after_stop))
            )

        if plan.closure_ticket_id is not None:
            _read_release_facts(backend, plan)

        deployment_identity = (
            backend.deploy_closure_identity(
                plan.target_release,
                plan.target_commit,
                plan.schema_revision,
                plan.closure_ticket_id,
            )
            if plan.closure_ticket_id is not None
            else backend.deploy_identity(
                plan.target_release,
                plan.target_commit,
                plan.schema_revision,
            )
        )
        seed_identity = _require_deployment_identity(
            deployment_identity,
            plan,
        )
        identity_rotated = True
        backend.activate_release(
            plan.target_release,
            plan.target_commit,
            plan.schema_revision,
            seed_identity,
        )
        target_release_activated = True
        if backend.read_current_release() != plan.target_release:
            raise DeploymentBlocked("current release symlink differs from target")
        for marker, expected in (
            (".brc-runtime-commit", plan.target_commit),
            (".brc-schema-revision", plan.schema_revision),
            (".brc-seed-identity", seed_identity),
        ):
            _require_marker(backend, plan.target_release, marker, expected)

        backend.start_services(SAFETY_SERVICES)
        _require_target_postflight(backend, plan, seed_identity=seed_identity)
        if plan.enable_entry:
            backend.start_services((ENTRY_SERVICE,))
            active_before_unfence = backend.services_active(ALL_SERVICES)
            if active_before_unfence != frozenset(ALL_SERVICES):
                raise DeploymentBlocked("ENTRY did not become active while write-fenced")
            _require_target_postflight(backend, plan, seed_identity=seed_identity)
            backend.unfence_entry()
        if (
            plan.closure_ticket_id is not None
            and not backend.entry_is_inactive_disabled_and_fenced()
        ):
            raise DeploymentBlocked("closure-only handover did not retain the ENTRY fence")
        expected_services = ALL_SERVICES if plan.enable_entry else SAFETY_SERVICES
        active_services = backend.services_active(ALL_SERVICES)
        if active_services != frozenset(expected_services):
            raise DeploymentBlocked(
                "runtime service state differs from deployment plan"
            )
    except Exception:
        if services_stopped:
            backend.fence_entry()
            if target_release_activated or (
                not identity_rotated
            ):
                backend.start_services(SAFETY_SERVICES)
        raise

    return DeploymentResult(
        status="pass",
        target_commit=plan.target_commit,
        target_release=plan.target_release,
        schema_revision=plan.schema_revision,
        configured_leverage=plan.expected_configured_leverage,
        entry_enabled=plan.enable_entry,
        mode=plan.mode,
    )


def _deploy_compatible_upgrade(
    backend: TokyoReleaseBackend,
    plan: DeploymentPlan,
) -> DeploymentResult:
    current_release = backend.read_current_release()
    if not backend.release_exists(plan.target_release):
        backend.install_release(plan.target_commit, plan.target_release)

    schema_state = backend.inspect_schema(plan.target_release)
    database_revision = str(schema_state.get("alembic_revision", ""))
    if schema_state.get("status") != "pass" or database_revision not in {
        COMPATIBLE_SOURCE_SCHEMA_REVISION,
        plan.schema_revision,
    }:
        raise DeploymentBlocked("compatible source schema revision differs")

    preservation_digest: str
    source_identity: dict[str, str] | None = None
    if database_revision == COMPATIBLE_SOURCE_SCHEMA_REVISION:
        source_certification, _, source_identity = _read_compatible_source_facts(
            backend,
            plan,
            exchange_probe_release=current_release,
        )
        preservation_digest = _require_preservation_digest(source_certification)
        _require_marker(
            backend,
            current_release,
            ".brc-runtime-commit",
            source_identity["runtime_commit"],
        )
        _require_marker(
            backend,
            current_release,
            ".brc-schema-revision",
            COMPATIBLE_SOURCE_SCHEMA_REVISION,
        )
    else:
        preservation_digest = backend.read_preservation_digest(plan.target_release)
        if not _SEED_IDENTITY.fullmatch(preservation_digest):
            raise DeploymentBlocked("persisted preservation digest is invalid")

    transition_started = False
    schema_migrated = database_revision == plan.schema_revision
    identity_rotated = False
    target_release_activated = current_release == plan.target_release
    try:
        backend.fence_entry()
        transition_started = True
        backend.stop_services(SAFETY_SERVICES)
        if not backend.migration_writers_stopped_and_entry_fenced():
            raise DeploymentBlocked(
                "migration writer stop prerequisite is not satisfied"
            )

        if database_revision == COMPATIBLE_SOURCE_SCHEMA_REVISION:
            final_source, _, final_identity = _read_compatible_source_facts(
                backend,
                plan,
                exchange_probe_release=current_release,
            )
            if final_identity != source_identity:
                raise DeploymentBlocked("source runtime identity changed during cutover")
            if _require_preservation_digest(final_source) != preservation_digest:
                raise DeploymentBlocked("source preservation digest changed during cutover")
            backend.persist_preservation_digest(
                plan.target_release,
                preservation_digest,
            )
            backend.migrate_schema(
                plan.target_release,
                COMPATIBLE_SOURCE_SCHEMA_REVISION,
                plan.schema_revision,
            )
            schema_migrated = True

        if not backend.preservation_verified(
            plan.target_release,
            preservation_digest,
        ):
            preservation = backend.verify_preservation(
                plan.target_release,
                COMPATIBLE_SOURCE_SCHEMA_REVISION,
                preservation_digest,
            )
            _require_preservation_verification(
                preservation,
                target_schema_revision=plan.schema_revision,
                expected_digest=preservation_digest,
            )
            backend.mark_preservation_verified(
                plan.target_release,
                preservation_digest,
            )

        deployment_identity = backend.deploy_compatible_identity(
            plan.target_release,
            plan.target_commit,
            plan.schema_revision,
        )
        seed_identity = _require_deployment_identity(deployment_identity, plan)
        identity_rotated = True
        backend.activate_release(
            plan.target_release,
            plan.target_commit,
            plan.schema_revision,
            seed_identity,
        )
        target_release_activated = True
        if backend.read_current_release() != plan.target_release:
            raise DeploymentBlocked("current release symlink differs from target")
        for marker, expected in (
            (".brc-runtime-commit", plan.target_commit),
            (".brc-schema-revision", plan.schema_revision),
            (".brc-seed-identity", seed_identity),
        ):
            _require_marker(backend, plan.target_release, marker, expected)

        backend.bootstrap_strategy_universes(plan.target_release)
        _require_target_postflight(
            backend,
            plan,
            seed_identity=seed_identity,
        )
        backend.start_services(SAFETY_SERVICES)
        active_safety = backend.services_active(ALL_SERVICES)
        if active_safety != frozenset(SAFETY_SERVICES):
            raise DeploymentBlocked("target safety services are not all active")
        if not backend.entry_is_inactive_disabled_and_fenced():
            raise DeploymentBlocked(
                "portfolio admission upgrade did not retain the ENTRY fence"
            )
        active_services = backend.services_active(ALL_SERVICES)
        if active_services != frozenset(SAFETY_SERVICES):
            raise DeploymentBlocked("target safety services differ from release plan")
    except Exception:
        if transition_started:
            backend.fence_entry()
            if target_release_activated or (
                not schema_migrated and not identity_rotated
            ):
                backend.start_services(SAFETY_SERVICES)
        raise

    return DeploymentResult(
        status="pass",
        target_commit=plan.target_commit,
        target_release=plan.target_release,
        schema_revision=plan.schema_revision,
        configured_leverage=plan.expected_configured_leverage,
        entry_enabled=False,
        mode=plan.mode,
    )


def _read_release_facts(
    backend: TokyoReleaseBackend,
    plan: DeploymentPlan,
) -> tuple[Mapping[str, object], Mapping[str, object], dict[str, str]]:
    if plan.closure_ticket_id is not None:
        certification = backend.certify_closure(
            plan.target_release,
            plan.closure_ticket_id,
        )
        probe = backend.probe_exchange(plan.target_release)
        return (
            certification,
            probe,
            _require_closure_release_facts(
                certification,
                probe,
                expected_leverage=plan.expected_configured_leverage,
                closure_ticket_id=plan.closure_ticket_id,
            ),
        )
    certification = backend.certify_flat(plan.target_release)
    probe = backend.probe_exchange(plan.target_release)
    return (
        certification,
        probe,
        _require_release_facts(
            certification,
            probe,
            expected_leverage=plan.expected_configured_leverage,
            compatible_upgrade=(
                plan.mode is DeploymentMode.COMPATIBLE_UPGRADE
            ),
        ),
    )


def _read_compatible_source_facts(
    backend: TokyoReleaseBackend,
    plan: DeploymentPlan,
    *,
    exchange_probe_release: str,
) -> tuple[Mapping[str, object], Mapping[str, object], dict[str, str]]:
    source_schema_revision = plan.source_schema_revision
    if source_schema_revision is None:
        raise DeploymentBlocked("compatible source schema is missing")
    certification = backend.certify_compatible_source(
        plan.target_release,
        source_schema_revision,
    )
    probe = backend.probe_exchange(exchange_probe_release)
    identity = _require_compatible_source_facts(
        certification,
        probe,
        source_schema_revision=source_schema_revision,
        expected_leverage=plan.expected_configured_leverage,
    )
    return certification, probe, identity


def _require_target_postflight(
    backend: TokyoReleaseBackend,
    plan: DeploymentPlan,
    *,
    seed_identity: str,
) -> None:
    certification, _, target_identity = _read_release_facts(backend, plan)
    if target_identity != {
        "runtime_commit": plan.target_commit,
        "schema_revision": plan.schema_revision,
        "seed_identity": seed_identity,
    }:
        raise DeploymentBlocked("deployed runtime identity differs from target")
    if plan.mode is DeploymentMode.COMPATIBLE_UPGRADE:
        _require_portfolio_admission_postflight(
            certification,
            seed_identity=seed_identity,
        )


def _require_portfolio_admission_postflight(
    certification: Mapping[str, object],
    *,
    seed_identity: str,
) -> None:
    owner_policy = certification.get("owner_policy")
    if (
        not isinstance(owner_policy, Mapping)
        or int(str(owner_policy.get("policy_version", -1))) != 4
        or owner_policy.get("new_entry_submit_enabled") is not False
    ):
        raise DeploymentBlocked("exact Policy v4 with ENTRY disabled is missing")
    registry_identity = certification.get("registry_identity")
    if (
        not isinstance(registry_identity, Mapping)
        or registry_identity.get("status") != "pass"
        or registry_identity.get("metadata_semantic_hash")
        != registry_identity.get("expected_semantic_hash")
    ):
        raise DeploymentBlocked("exact Registry identity differs")
    strategy_universe = certification.get("strategy_universe")
    if (
        not isinstance(strategy_universe, Mapping)
        or strategy_universe.get("identity_status") != "pass"
        or strategy_universe.get("semantic_digest_status") != "pass"
    ):
        raise DeploymentBlocked("exact Universe identity differs")
    if strategy_universe.get("deployment_stage") != "warming":
        raise DeploymentBlocked("exact Warming Universe stage is missing")
    if certification.get("compatible_certification_batch_pass") is not True:
        raise DeploymentBlocked("exact Certification Batch identity differs")
    runtime_identity = certification.get("runtime_identity")
    if (
        not isinstance(runtime_identity, Mapping)
        or runtime_identity.get("schema_revision") != SCHEMA_REVISION
    ):
        raise DeploymentBlocked("exact target schema revision differs")
    seed = certification.get("seed_identity")
    if (
        not isinstance(seed, Mapping)
        or seed.get("status") != "pass"
        or seed.get("expected") != seed_identity
        or seed.get("actual") != seed_identity
    ):
        raise DeploymentBlocked("exact Seed identity differs")


def _require_compatible_source_facts(
    certification: Mapping[str, object],
    probe: Mapping[str, object],
    *,
    source_schema_revision: str,
    expected_leverage: int,
) -> dict[str, str]:
    if certification.get("status") != "pass":
        raise DeploymentBlocked("compatible source certification failed")
    if certification.get("alembic_revision") != source_schema_revision:
        raise DeploymentBlocked("compatible source schema revision differs")
    migration_gate = certification.get("migration_gate")
    if not isinstance(migration_gate, Mapping):
        raise DeploymentBlocked("compatible migration gate is missing")
    blockers = (
        ("active_tickets", "active Ticket"),
        ("non_flat_positions", "projected position"),
        ("active_reservations", "Budget Reservation"),
        ("active_domains", "Netting Domain"),
        ("unreviewed_terminal_tickets", "terminal Ticket Review"),
        ("unresolved_commands", "unresolved Exchange Command"),
        ("open_incidents", "open Incident"),
        ("busy_entry_lane", "ENTRY lane"),
        ("nonterminal_aggregates", "Aggregate closure"),
    )
    for key, label in blockers:
        if int(str(migration_gate.get(key, -1))) != 0:
            raise DeploymentBlocked(f"compatible migration requires zero {label}")
    runtime_identity = certification.get("runtime_identity")
    if not isinstance(runtime_identity, Mapping):
        raise DeploymentBlocked("compatible source runtime identity is missing")
    identity = {
        key: str(runtime_identity.get(key, ""))
        for key in ("runtime_commit", "schema_revision", "seed_identity")
    }
    if (
        not _COMMIT.fullmatch(identity["runtime_commit"])
        or identity["schema_revision"] != source_schema_revision
        or not _SEED_IDENTITY.fullmatch(identity["seed_identity"])
    ):
        raise DeploymentBlocked("compatible source runtime identity is invalid")
    _require_preservation_digest(certification)
    _require_flat_exchange_facts(probe, expected_leverage=expected_leverage)
    return identity


def _require_preservation_digest(payload: Mapping[str, object]) -> str:
    manifest = payload.get("preservation_manifest")
    if not isinstance(manifest, Mapping):
        raise DeploymentBlocked("history preservation manifest is missing")
    digest = str(manifest.get("digest", ""))
    if not _SEED_IDENTITY.fullmatch(digest):
        raise DeploymentBlocked("history preservation digest is invalid")
    return digest


def _require_preservation_verification(
    payload: Mapping[str, object],
    *,
    target_schema_revision: str,
    expected_digest: str,
) -> None:
    if payload.get("status") != "pass":
        raise DeploymentBlocked("history preservation digest differs")
    if payload.get("alembic_revision") != target_schema_revision:
        raise DeploymentBlocked("compatible target schema revision differs")
    if _require_preservation_digest(payload) != expected_digest:
        raise DeploymentBlocked("history preservation digest differs")


def _require_release_facts(
    certification: Mapping[str, object],
    probe: Mapping[str, object],
    *,
    expected_leverage: int,
    compatible_upgrade: bool = False,
) -> dict[str, str]:
    if certification.get("status") != "pass":
        raise DeploymentBlocked("database flat certification failed")
    required_gates = (
        (("flatness_pass", "database flatness gate failed"),)
        if compatible_upgrade
        else (
            (
                "universe_bootstrap_pass",
                "StrategyUniverse bootstrap certification failed",
            ),
            (
                "certification_batch_pass",
                "Certification Batch certification failed",
            ),
            ("flatness_pass", "database flatness gate failed"),
        )
    )
    for key, message in required_gates:
        if certification.get(key) is not True:
            raise DeploymentBlocked(message)
    active_counts = certification.get("active_counts")
    if not isinstance(active_counts, Mapping) or any(
        int(str(active_counts.get(key, -1))) != 0
        for key in ("tickets", "commands", "positions", "incidents")
    ):
        raise DeploymentBlocked("database runtime activity is not zero")
    runtime_identity = certification.get("runtime_identity")
    if not isinstance(runtime_identity, Mapping):
        raise DeploymentBlocked("database runtime identity is missing")
    identity = {
        key: str(runtime_identity.get(key, ""))
        for key in ("runtime_commit", "schema_revision", "seed_identity")
    }
    if not _COMMIT.fullmatch(identity["runtime_commit"]):
        raise DeploymentBlocked("database runtime identity is invalid")
    if identity["schema_revision"] != SCHEMA_REVISION:
        raise DeploymentBlocked("exact target schema revision differs")
    if not _SEED_IDENTITY.fullmatch(identity["seed_identity"]):
        raise DeploymentBlocked("database runtime identity is invalid")

    if probe.get("venue_id") != "binance-usdm":
        raise DeploymentBlocked("production venue identity differs from policy")
    if probe.get("account_position_mode") != "independent_sides":
        raise DeploymentBlocked("production account position mode is invalid")
    if probe.get("account_margin_mode") != "cross":
        raise DeploymentBlocked("production account margin mode is invalid")
    if int(str(probe.get("non_flat_domain_count", -1))) != 0:
        raise DeploymentBlocked("exchange position is not flat")
    if int(str(probe.get("open_order_domain_count", -1))) != 0:
        raise DeploymentBlocked("exchange open orders are present")
    _require_probe_rules(
        probe,
        expected_leverage=expected_leverage,
    )
    return identity


def _require_closure_release_facts(
    certification: Mapping[str, object],
    probe: Mapping[str, object],
    *,
    expected_leverage: int,
    closure_ticket_id: str,
) -> dict[str, str]:
    if certification.get("status") != "pass":
        raise DeploymentBlocked("database closure certification failed")
    active_counts = certification.get("active_counts")
    if not isinstance(active_counts, Mapping) or any(
        int(str(active_counts.get(key, -1))) != expected
        for key, expected in (
            ("tickets", 0),
            ("commands", 0),
            ("positions", 0),
            ("incidents", 0),
        )
    ):
        raise DeploymentBlocked("database closure runtime activity differs")
    runtime_identity = certification.get("runtime_identity")
    if not isinstance(runtime_identity, Mapping):
        raise DeploymentBlocked("database runtime identity is missing")
    identity = {
        key: str(runtime_identity.get(key, ""))
        for key in ("runtime_commit", "schema_revision", "seed_identity")
    }
    if (
        not _COMMIT.fullmatch(identity["runtime_commit"])
        or identity["schema_revision"] != SCHEMA_REVISION
        or not _SEED_IDENTITY.fullmatch(identity["seed_identity"])
    ):
        raise DeploymentBlocked("database runtime identity is invalid")
    closure_ticket = certification.get("closure_ticket")
    if not isinstance(closure_ticket, Mapping):
        raise DeploymentBlocked("exact closure Ticket facts are missing")
    if str(closure_ticket.get("ticket_id", "")) != closure_ticket_id:
        raise DeploymentBlocked("exact closure Ticket identity differs")
    if str(closure_ticket.get("aggregate_status", "")) not in {
        "settlement_pending",
        "review_pending",
    }:
        raise DeploymentBlocked("closure Ticket is not pending Settlement or Review")
    try:
        quantities_are_flat = all(
            Decimal(str(closure_ticket.get(key, "-1"))) == 0
            for key in ("position_quantity", "protected_quantity")
        )
    except (InvalidOperation, ValueError):
        quantities_are_flat = False
    if not quantities_are_flat:
        raise DeploymentBlocked("closure Ticket still has position or protection")
    if any(
        int(str(closure_ticket.get(key, -1))) != 0
        for key in (
            "owned_order_residue_count",
            "unresolved_command_count",
            "open_incident_count",
        )
    ):
        raise DeploymentBlocked("closure Ticket has unresolved runtime residue")
    if (
        closure_ticket.get("budget_reservation_status") != "released"
        or closure_ticket.get("account_capacity_released") is not True
        or closure_ticket.get("netting_domain_released") is not True
    ):
        raise DeploymentBlocked("closure Ticket authority has not been released")
    _require_flat_exchange_facts(
        probe,
        expected_leverage=expected_leverage,
    )
    return identity


def _require_flat_exchange_facts(
    probe: Mapping[str, object],
    *,
    expected_leverage: int,
) -> None:
    if probe.get("venue_id") != "binance-usdm":
        raise DeploymentBlocked("production venue identity differs from policy")
    if probe.get("account_position_mode") != "independent_sides":
        raise DeploymentBlocked("production account position mode is invalid")
    if probe.get("account_margin_mode") != "cross":
        raise DeploymentBlocked("production account margin mode is invalid")
    if int(str(probe.get("non_flat_domain_count", -1))) != 0:
        raise DeploymentBlocked("exchange position is not flat")
    if int(str(probe.get("open_order_domain_count", -1))) != 0:
        raise DeploymentBlocked("exchange open orders are present")
    _require_probe_rules(
        probe,
        expected_leverage=expected_leverage,
    )


def _require_probe_rules(
    probe: Mapping[str, object],
    *,
    expected_leverage: int,
) -> None:
    rules = probe.get("rules")
    if not isinstance(rules, list) or not rules:
        raise DeploymentBlocked("production instrument rule set is incomplete")
    if any(not isinstance(rule, Mapping) for rule in rules):
        raise DeploymentBlocked("production instrument rule set is incomplete")
    actual_instrument_ids = tuple(
        sorted(
            str(rule.get("exchange_instrument_id", ""))
            for rule in rules
            if isinstance(rule, Mapping)
        )
    )
    if len(actual_instrument_ids) != len(set(actual_instrument_ids)):
        raise DeploymentBlocked("production instrument rule identity differs")
    manifest = probe.get("probe_manifest")
    if not isinstance(manifest, list):
        raise DeploymentBlocked("database-derived probe manifest is missing")
    expected_instrument_ids = tuple(sorted(str(value) for value in manifest))
    if (
        not expected_instrument_ids
        or len(expected_instrument_ids) != len(set(expected_instrument_ids))
        or actual_instrument_ids != expected_instrument_ids
    ):
        raise DeploymentBlocked("production instrument rule identity differs")
    configured = {
        int(str(rule.get("configured_leverage", -1)))
        for rule in rules
        if isinstance(rule, Mapping)
    }
    if configured != {expected_leverage}:
        raise DeploymentBlocked(
            "production configured leverage differs from fixed 5x policy"
        )


def _require_deployment_identity(
    payload: Mapping[str, object],
    plan: DeploymentPlan,
) -> str:
    if (
        payload.get("runtime_commit") != plan.target_commit
        or payload.get("schema_revision") != plan.schema_revision
    ):
        raise DeploymentBlocked("runtime identity rotation returned wrong target")
    seed_identity = str(payload.get("runtime_seed_semantic_hash", ""))
    if not _SEED_IDENTITY.fullmatch(seed_identity):
        raise DeploymentBlocked("runtime identity rotation returned invalid seed")
    return seed_identity


def _require_marker(
    backend: TokyoReleaseBackend,
    release: str,
    marker: str,
    expected: str,
) -> None:
    if backend.read_release_marker(release, marker) != expected:
        raise DeploymentBlocked(f"release marker differs: {marker}")


@dataclass(frozen=True)
class _CommandResult:
    returncode: int
    stdout: str
    stderr: str


class SshTokyoReleaseBackend:
    def __init__(
        self,
        *,
        target: str,
        repo_root: Path,
        timeout_seconds: float,
    ) -> None:
        normalized = target.strip()
        if not normalized or any(character.isspace() for character in normalized):
            raise ValueError("Tokyo SSH target must be one non-blank token")
        if timeout_seconds <= 0:
            raise ValueError("Tokyo SSH timeout must be positive")
        self._target = normalized
        self._repo_root = repo_root
        self._timeout_seconds = timeout_seconds

    def read_current_release(self) -> str:
        return self._remote(
            ("sudo", "readlink", "-f", CURRENT_RELEASE)
        ).stdout

    def release_exists(self, release: str) -> bool:
        return (
            self._remote(("sudo", "test", "-d", release), check=False).returncode
            == 0
        )

    def inspect_schema(self, release: str) -> Mapping[str, object]:
        return self._release_json(
            release,
            "scripts/trading_kernel/verify_schema.py",
            "--deployment-revision",
            check=False,
        )

    def certify_flat(self, release: str) -> Mapping[str, object]:
        return self._release_json(
            release,
            "scripts/trading_kernel/certify_readonly.py",
            "--require-flat",
        )

    def certify_closure(
        self,
        release: str,
        ticket_id: str,
    ) -> Mapping[str, object]:
        return self._release_json(
            release,
            "scripts/trading_kernel/certify_readonly.py",
            "--closure-ticket-id",
            ticket_id,
        )

    def probe_exchange(self, release: str) -> Mapping[str, object]:
        return self._release_json(
            release,
            "scripts/trading_kernel/probe_production_runtime.py",
        )

    def certify_compatible_source(
        self,
        release: str,
        source_schema_revision: str,
    ) -> Mapping[str, object]:
        return self._release_json(
            release,
            "scripts/trading_kernel/verify_schema.py",
            "--compatible-source-revision",
            source_schema_revision,
        )

    def read_release_marker(self, release: str, marker: str) -> str:
        return self._remote(("sudo", "cat", f"{release}/{marker}")).stdout

    def stop_services(self, services: tuple[str, ...]) -> None:
        self._remote(("sudo", "systemctl", "stop", *services))

    def services_active(self, services: tuple[str, ...]) -> frozenset[str]:
        active = {
            service
            for service in services
            if self._remote(
                ("sudo", "systemctl", "is-active", "--quiet", service),
                check=False,
            ).returncode
            == 0
        }
        return frozenset(active)

    def migration_writers_stopped_and_entry_fenced(self) -> bool:
        return bool(
            not self.services_active(ALL_SERVICES)
            and self._remote(
                ("sudo", "test", "-f", WRITE_FENCE),
                check=False,
            ).returncode
            == 0
            and self._remote(
                ("sudo", "systemctl", "is-enabled", "--quiet", ENTRY_SERVICE),
                check=False,
            ).returncode
            != 0
        )

    def install_release(self, commit: str, release: str) -> None:
        self._remote(("sudo", "rm", "-rf", release))
        self._remote(
            (
                "sudo",
                "install",
                "-d",
                "-o",
                "brc",
                "-g",
                "brc",
                "-m",
                "0755",
                release,
            )
        )
        self._upload_git_archive(commit, release)
        self._remote(
            (
                "sudo",
                "cp",
                "-a",
                f"{CURRENT_RELEASE}/.venv",
                f"{release}/.venv",
            )
        )
        self._remote(("sudo", "chown", "-R", "brc:brc", release))

    def deploy_identity(
        self,
        release: str,
        commit: str,
        schema_revision: str,
    ) -> Mapping[str, object]:
        return self._release_json(
            release,
            "scripts/trading_kernel/seed_runtime_authority.py",
            "deploy-identity",
            "--runtime-commit",
            commit,
            "--schema-revision",
            schema_revision,
        )

    def migrate_schema(
        self,
        release: str,
        source_schema_revision: str,
        target_schema_revision: str,
    ) -> None:
        if source_schema_revision != COMPATIBLE_SOURCE_SCHEMA_REVISION:
            raise ValueError("compatible migration source revision differs")
        self._release_command(
            release,
            "-m",
            "alembic",
            "-c",
            "migrations/trading_kernel/alembic.ini",
            "upgrade",
            target_schema_revision,
        )

    def verify_preservation(
        self,
        release: str,
        source_schema_revision: str,
        expected_digest: str,
    ) -> Mapping[str, object]:
        return self._release_json(
            release,
            "scripts/trading_kernel/verify_schema.py",
            "--preserve-source-revision",
            source_schema_revision,
            "--expected-preservation-digest",
            expected_digest,
        )

    def persist_preservation_digest(self, release: str, digest: str) -> None:
        self._write_release_marker(
            release,
            ".brc-0002-preservation-digest",
            digest,
        )

    def read_preservation_digest(self, release: str) -> str:
        return self.read_release_marker(
            release,
            ".brc-0002-preservation-digest",
        )

    def mark_preservation_verified(self, release: str, digest: str) -> None:
        self._write_release_marker(
            release,
            ".brc-0002-preservation-verified",
            digest,
        )

    def preservation_verified(self, release: str, digest: str) -> bool:
        result = self._remote(
            (
                "sudo",
                "cat",
                f"{release}/.brc-0002-preservation-verified",
            ),
            check=False,
        )
        return result.returncode == 0 and result.stdout == digest

    def deploy_compatible_identity(
        self,
        release: str,
        commit: str,
        schema_revision: str,
    ) -> Mapping[str, object]:
        return self._release_json(
            release,
            "scripts/trading_kernel/seed_runtime_authority.py",
            "deploy-compatible-identity",
            "--runtime-commit",
            commit,
            "--schema-revision",
            schema_revision,
        )

    def deploy_closure_identity(
        self,
        release: str,
        commit: str,
        schema_revision: str,
        ticket_id: str,
    ) -> Mapping[str, object]:
        return self._release_json(
            release,
            "scripts/trading_kernel/seed_runtime_authority.py",
            "deploy-closure-identity",
            "--runtime-commit",
            commit,
            "--schema-revision",
            schema_revision,
            "--closure-ticket-id",
            ticket_id,
        )

    def activate_release(
        self,
        release: str,
        commit: str,
        schema_revision: str,
        seed_identity: str,
    ) -> None:
        for marker, value in (
            (".brc-runtime-commit", commit),
            (".brc-schema-revision", schema_revision),
            (".brc-seed-identity", seed_identity),
        ):
            self._write_release_marker(release, marker, value)
        for key, value in (
            ("TRADING_KERNEL_RUNTIME_COMMIT", commit),
            ("TRADING_KERNEL_SCHEMA_REVISION", schema_revision),
        ):
            self._remote(
                (
                    "sudo",
                    "sed",
                    "-i",
                    f"s/^{key}=.*/{key}={value}/",
                    RUNTIME_ENV,
                )
            )
            self._remote(
                ("sudo", "grep", "-Fxc", f"{key}={value}", RUNTIME_ENV)
            )
        for unit in SYSTEMD_UNITS:
            self._remote(
                (
                    "sudo",
                    "install",
                    "-m",
                    "0644",
                    f"{release}/deploy/systemd/{unit}",
                    f"/etc/systemd/system/{unit}",
                )
            )
        self._remote(("sudo", "ln", "-sfn", release, CURRENT_RELEASE))
        self._remote(("sudo", "systemctl", "daemon-reload"))

    def start_services(self, services: tuple[str, ...]) -> None:
        if ENTRY_SERVICE in services and services != (ENTRY_SERVICE,):
            raise ValueError("ENTRY must be started as the final isolated phase")
        self._remote(("sudo", "systemctl", "enable", "--now", *services))

    def bootstrap_strategy_universes(self, release: str) -> None:
        self._release_command(
            release,
            "scripts/trading_kernel/bootstrap_strategy_universes.py",
            "--runtime-profile-id",
            "tiny-live-v1",
            "--prepare-certification-batch-only",
        )

    def unfence_entry(self) -> None:
        self._remote(("sudo", "rm", "-f", WRITE_FENCE))

    def fence_entry(self) -> None:
        self._remote(
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
            ),
            check=False,
        )
        self._remote(("sudo", "touch", WRITE_FENCE), check=False)
        self._remote(
            ("sudo", "systemctl", "disable", "--now", ENTRY_SERVICE),
            check=False,
        )

    def entry_is_inactive_disabled_and_fenced(self) -> bool:
        return (
            self._remote(("sudo", "test", "-f", WRITE_FENCE), check=False).returncode
            == 0
            and self._remote(
                ("sudo", "systemctl", "is-active", "--quiet", ENTRY_SERVICE),
                check=False,
            ).returncode
            != 0
            and self._remote(
                ("sudo", "systemctl", "is-enabled", "--quiet", ENTRY_SERVICE),
                check=False,
            ).returncode
            != 0
        )

    def _release_json(
        self,
        release: str,
        script: str,
        *args: str,
        check: bool = True,
    ) -> Mapping[str, object]:
        executable = shlex.join(
            (f"{release}/.venv/bin/python", f"{release}/{script}", *args)
        )
        command = (
            f"set -a; . {shlex.quote(RUNTIME_ENV)}; "
            f"set +a; exec {executable}"
        )
        result = self._remote(
            ("sudo", "-u", "brc", "/bin/bash", "-lc", command),
            check=check,
        )
        payload = json.loads(result.stdout)
        if not isinstance(payload, Mapping):
            raise TypeError("Tokyo release command did not return a JSON object")
        return payload

    def _write_release_marker(
        self,
        release: str,
        marker: str,
        value: str,
    ) -> None:
        self._remote(
            (
                "sudo",
                "python3",
                "-c",
                (
                    "from pathlib import Path; import sys; "
                    "Path(sys.argv[1]).write_text(sys.argv[2], encoding='utf-8')"
                ),
                f"{release}/{marker}",
                value,
            )
        )

    def _release_command(
        self,
        release: str,
        *args: str,
    ) -> _CommandResult:
        executable = shlex.join((f"{release}/.venv/bin/python", *args))
        command = (
            f"set -a; . {shlex.quote(RUNTIME_ENV)}; set +a; "
            f"cd {shlex.quote(release)}; exec {executable}"
        )
        return self._remote(
            ("sudo", "-u", "brc", "/bin/bash", "-lc", command)
        )

    def _upload_git_archive(self, commit: str, release: str) -> None:
        archive = subprocess.Popen(
            ("git", "archive", "--format=tar", commit),
            cwd=self._repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if archive.stdout is None:
            raise RuntimeError("git archive stdout pipe is unavailable")
        remote_command = shlex.join(
            ("sudo", "tar", "-xf", "-", "-C", release)
        )
        ssh = subprocess.Popen(
            (*self._ssh_base(), "--", remote_command),
            stdin=archive.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        archive.stdout.close()
        ssh_stdout, ssh_stderr = ssh.communicate(
            timeout=max(self._timeout_seconds, 120)
        )
        archive_stderr = archive.stderr.read() if archive.stderr else b""
        archive_code = archive.wait()
        if archive_code != 0 or ssh.returncode != 0:
            detail = (archive_stderr + ssh_stderr)[-2_000:].decode(
                "utf-8",
                errors="replace",
            )
            raise RuntimeError(f"release archive upload failed: {detail}")
        del ssh_stdout

    def _remote(
        self,
        argv: tuple[str, ...],
        *,
        check: bool = True,
    ) -> _CommandResult:
        remote_command = shlex.join(argv)
        completed = subprocess.run(
            (*self._ssh_base(), "--", remote_command),
            check=False,
            capture_output=True,
            text=True,
            timeout=self._timeout_seconds,
        )
        result = _CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
        )
        if check and result.returncode != 0:
            raise RuntimeError(
                f"Tokyo command failed ({result.returncode}): "
                f"{result.stderr[-2_000:]}"
            )
        return result

    def _ssh_base(self) -> tuple[str, ...]:
        return (
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            self._target,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        default=os.getenv("TRADING_KERNEL_TOKYO_SSH_TARGET", "tokyo"),
    )
    parser.add_argument(
        "--commit",
        default="HEAD",
        help="Committed local git revision to deploy; defaults to HEAD.",
    )
    parser.add_argument(
        "--enable-entry",
        action="store_true",
        help="Enable ENTRY only after all target postflight checks pass.",
    )
    parser.add_argument(
        "--mode",
        choices=tuple(mode.value for mode in DeploymentMode),
        default=DeploymentMode.REGULAR.value,
    )
    parser.add_argument(
        "--source-schema-revision",
        help="Exact source revision for compatible_upgrade mode.",
    )
    parser.add_argument(
        "--closure-ticket-id",
        help="Exact zero-exposure pending Ticket allowed across one closure-only handover.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
    )
    return parser


def _resolve_commit(reference: str) -> str:
    result = subprocess.run(
        ("git", "rev-parse", "--verify", f"{reference}^{{commit}}"),
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if not _COMMIT.fullmatch(commit):
        raise ValueError("resolved git commit is not an exact lowercase SHA")
    return commit


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    commit = _resolve_commit(args.commit)
    plan = DeploymentPlan(
        target_commit=commit,
        target_release=f"{RELEASE_ROOT}/brc-trading-kernel-{commit[:12]}",
        schema_revision=SCHEMA_REVISION,
        expected_configured_leverage=EXPECTED_CONFIGURED_LEVERAGE,
        enable_entry=args.enable_entry,
        source_schema_revision=args.source_schema_revision,
        mode=DeploymentMode(args.mode),
        closure_ticket_id=args.closure_ticket_id,
    )
    backend = SshTokyoReleaseBackend(
        target=args.target,
        repo_root=REPO_ROOT,
        timeout_seconds=args.timeout_seconds,
    )
    result = deploy_tokyo_release(backend, plan)
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
