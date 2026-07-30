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
from pathlib import Path
from typing import Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCHEMA_REVISION = "0001_trading_kernel_baseline_v3"
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


@dataclass(frozen=True)
class DeploymentPlan:
    target_commit: str
    target_release: str
    schema_revision: str
    expected_configured_leverage: int
    enable_entry: bool
    protected_ticket_ids: tuple[str, ...] = ()
    closure_ticket_id: str | None = None

    def __post_init__(self) -> None:
        if not _COMMIT.fullmatch(self.target_commit):
            raise ValueError("target commit must be an exact lowercase 40-hex SHA")
        expected_release = (
            f"{RELEASE_ROOT}/brc-trading-kernel-{self.target_commit[:12]}"
        )
        if self.target_release != expected_release:
            raise ValueError("target release path differs from target commit")
        if self.schema_revision != SCHEMA_REVISION:
            raise ValueError("regular deployment cannot change schema revision")
        if self.expected_configured_leverage != EXPECTED_CONFIGURED_LEVERAGE:
            raise ValueError("production configured leverage must remain fixed at 5x")
        if any(not ticket_id.strip() for ticket_id in self.protected_ticket_ids):
            raise ValueError("protected Ticket identities must be non-blank")
        if len(set(self.protected_ticket_ids)) != len(self.protected_ticket_ids):
            raise ValueError("protected Ticket identities must be distinct")
        if self.protected_ticket_ids and self.enable_entry:
            raise ValueError("protected handover must keep ENTRY fenced")
        if self.closure_ticket_id is not None and not self.closure_ticket_id.strip():
            raise ValueError("closure-only Ticket identity must be non-blank")
        if self.closure_ticket_id is not None and self.protected_ticket_ids:
            raise ValueError("closure-only and protected handover are mutually exclusive")
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


class TokyoReleaseBackend(Protocol):
    def read_current_release(self) -> str: ...

    def certify_flat(self, release: str) -> Mapping[str, object]: ...

    def certify_protected(self, release: str) -> Mapping[str, object]: ...

    def certify_closure(
        self,
        release: str,
        ticket_id: str,
    ) -> Mapping[str, object]: ...

    def probe_exchange(self, release: str) -> Mapping[str, object]: ...

    def probe_protected_exchange(
        self,
        release: str,
        protected_tickets: list[object],
    ) -> Mapping[str, object]: ...

    def read_release_marker(self, release: str, marker: str) -> str: ...

    def stop_services(self, services: tuple[str, ...]) -> None: ...

    def services_active(self, services: tuple[str, ...]) -> frozenset[str]: ...

    def install_release(self, commit: str, release: str) -> None: ...

    def deploy_identity(
        self,
        release: str,
        commit: str,
        schema_revision: str,
    ) -> Mapping[str, object]: ...

    def deploy_protected_identity(
        self,
        release: str,
        commit: str,
        schema_revision: str,
        ticket_ids: tuple[str, ...],
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

    def unfence_entry(self) -> None: ...

    def fence_entry(self) -> None: ...

    def entry_is_inactive_disabled_and_fenced(self) -> bool: ...


def deploy_tokyo_release(
    backend: TokyoReleaseBackend,
    plan: DeploymentPlan,
) -> DeploymentResult:
    current_release = backend.read_current_release()
    if current_release == plan.target_release:
        raise DeploymentBlocked("target release is already current")
    backend.install_release(plan.target_commit, plan.target_release)
    _, _, current_identity = _read_release_facts(
        backend,
        plan,
    )
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
            else backend.deploy_protected_identity(
                plan.target_release,
                plan.target_commit,
                plan.schema_revision,
                plan.protected_ticket_ids,
            )
            if plan.protected_ticket_ids
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
        _, _, target_identity = _read_release_facts(backend, plan)
        if target_identity != {
            "runtime_commit": plan.target_commit,
            "schema_revision": plan.schema_revision,
            "seed_identity": seed_identity,
        }:
            raise DeploymentBlocked("deployed runtime identity differs from target")
        if backend.read_current_release() != plan.target_release:
            raise DeploymentBlocked("current release symlink differs from target")
        for marker, expected in (
            (".brc-runtime-commit", plan.target_commit),
            (".brc-schema-revision", plan.schema_revision),
            (".brc-seed-identity", seed_identity),
        ):
            _require_marker(backend, plan.target_release, marker, expected)

        backend.start_services(SAFETY_SERVICES)
        if plan.enable_entry:
            backend.start_services((ENTRY_SERVICE,))
            active_before_unfence = backend.services_active(ALL_SERVICES)
            if active_before_unfence != frozenset(ALL_SERVICES):
                raise DeploymentBlocked("ENTRY did not become active while write-fenced")
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
            if target_release_activated or not identity_rotated:
                backend.start_services(SAFETY_SERVICES)
        raise

    return DeploymentResult(
        status="pass",
        target_commit=plan.target_commit,
        target_release=plan.target_release,
        schema_revision=plan.schema_revision,
        configured_leverage=plan.expected_configured_leverage,
        entry_enabled=plan.enable_entry,
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
    if plan.protected_ticket_ids:
        certification = backend.certify_protected(plan.target_release)
        probe = backend.probe_protected_exchange(
            plan.target_release,
            _require_protected_ticket_rows(certification),
        )
        return (
            certification,
            probe,
            _require_protected_release_facts(
                certification,
                probe,
                expected_leverage=plan.expected_configured_leverage,
                protected_ticket_ids=plan.protected_ticket_ids,
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
        ),
    )


def _require_release_facts(
    certification: Mapping[str, object],
    probe: Mapping[str, object],
    *,
    expected_leverage: int,
) -> dict[str, str]:
    if certification.get("status") != "pass":
        raise DeploymentBlocked("database flat certification failed")
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
    if (
        not _COMMIT.fullmatch(identity["runtime_commit"])
        or identity["schema_revision"] != SCHEMA_REVISION
        or not _SEED_IDENTITY.fullmatch(identity["seed_identity"])
    ):
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


def _require_protected_release_facts(
    certification: Mapping[str, object],
    probe: Mapping[str, object],
    *,
    expected_leverage: int,
    protected_ticket_ids: tuple[str, ...],
) -> dict[str, str]:
    protected_ticket_count = len(protected_ticket_ids)
    if certification.get("status") != "pass":
        raise DeploymentBlocked("database protected certification failed")
    active_counts = certification.get("active_counts")
    if not isinstance(active_counts, Mapping) or any(
        int(str(active_counts.get(key, -1))) != expected
        for key, expected in (
            ("tickets", protected_ticket_count),
            ("commands", 0),
            ("positions", protected_ticket_count),
            ("incidents", 0),
        )
    ):
        raise DeploymentBlocked("database protected runtime activity differs")
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
    if probe.get("venue_id") != "binance-usdm":
        raise DeploymentBlocked("production venue identity differs from policy")
    if probe.get("account_position_mode") != "independent_sides":
        raise DeploymentBlocked("production account position mode is invalid")
    if probe.get("account_margin_mode") != "cross":
        raise DeploymentBlocked("production account margin mode is invalid")
    if int(str(probe.get("non_flat_domain_count", -1))) != protected_ticket_count:
        raise DeploymentBlocked("exchange protected position count differs")
    if int(str(probe.get("open_order_domain_count", -1))) != protected_ticket_count:
        raise DeploymentBlocked("exchange protected order count differs")
    _require_exact_protected_exchange_facts(
        certification,
        probe,
        protected_ticket_ids=protected_ticket_ids,
    )
    _require_probe_rules(
        probe,
        expected_leverage=expected_leverage,
    )
    return identity


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


def _require_exact_protected_exchange_facts(
    certification: Mapping[str, object],
    probe: Mapping[str, object],
    *,
    protected_ticket_ids: tuple[str, ...],
) -> None:
    certification_tickets = certification.get("protected_tickets")
    probe_tickets = probe.get("protected_tickets")
    if not isinstance(certification_tickets, list) or not isinstance(
        probe_tickets,
        list,
    ):
        raise DeploymentBlocked("exact protected exchange facts are missing")
    expected_ids = set(protected_ticket_ids)
    certification_by_ticket = _protected_ticket_facts_by_ticket(
        certification_tickets,
        expected_ids=expected_ids,
    )
    probe_by_ticket = _protected_ticket_facts_by_ticket(
        probe_tickets,
        expected_ids=expected_ids,
    )
    if certification_by_ticket != probe_by_ticket:
        raise DeploymentBlocked("exact protected exchange facts differ")


def _require_protected_ticket_rows(
    certification: Mapping[str, object],
) -> list[object]:
    rows = certification.get("protected_tickets")
    if not isinstance(rows, list):
        raise DeploymentBlocked("exact protected exchange facts are missing")
    return rows


def _protected_ticket_facts_by_ticket(
    rows: list[object],
    *,
    expected_ids: set[str],
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise DeploymentBlocked("exact protected exchange facts are invalid")
        canonical_row = dict(row)
        if canonical_row.get("recorded_tp1_fill_quantity") is None:
            canonical_row.pop("recorded_tp1_fill_quantity", None)
        ticket_id = str(canonical_row.get("ticket_id", "")).strip()
        if not ticket_id or ticket_id in normalized:
            raise DeploymentBlocked("exact protected exchange facts are invalid")
        normalized[ticket_id] = json.dumps(
            canonical_row,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    if set(normalized) != expected_ids:
        raise DeploymentBlocked("exact protected exchange facts differ")
    return normalized


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

    def certify_flat(self, release: str) -> Mapping[str, object]:
        return self._release_json(
            release,
            "scripts/trading_kernel/certify_readonly.py",
            "--require-flat",
        )

    def certify_protected(self, release: str) -> Mapping[str, object]:
        return self._release_json(
            release,
            "scripts/trading_kernel/certify_readonly.py",
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

    def probe_protected_exchange(
        self,
        release: str,
        protected_tickets: list[object],
    ) -> Mapping[str, object]:
        encoded_rows: list[str] = []
        for row in protected_tickets:
            if not isinstance(row, Mapping):
                raise TypeError("protected certification row must be a mapping")
            encoded_rows.append(
                json.dumps(
                    row,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
        return self._release_json(
            release,
            "scripts/trading_kernel/probe_production_runtime.py",
            *(argument for row in encoded_rows for argument in ("--protected-ticket-json", row)),
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

    def deploy_protected_identity(
        self,
        release: str,
        commit: str,
        schema_revision: str,
        ticket_ids: tuple[str, ...],
    ) -> Mapping[str, object]:
        return self._release_json(
            release,
            "scripts/trading_kernel/seed_runtime_authority.py",
            "deploy-protected-identity",
            "--runtime-commit",
            commit,
            "--schema-revision",
            schema_revision,
            *(
                argument
                for ticket_id in ticket_ids
                for argument in ("--protected-ticket-id", ticket_id)
            ),
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
            self._remote(
                (
                    "sudo",
                    "python3",
                    "-c",
                    (
                        "from pathlib import Path; import sys; "
                        "Path(sys.argv[1]).write_text(sys.argv[2], "
                        "encoding='utf-8')"
                    ),
                    f"{release}/{marker}",
                    value,
                )
            )
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
    ) -> Mapping[str, object]:
        executable = shlex.join(
            (f"{release}/.venv/bin/python", f"{release}/{script}", *args)
        )
        command = (
            f"set -a; . {shlex.quote(RUNTIME_ENV)}; "
            f"set +a; exec {executable}"
        )
        result = self._remote(
            ("sudo", "-u", "brc", "/bin/bash", "-lc", command)
        )
        payload = json.loads(result.stdout)
        if not isinstance(payload, Mapping):
            raise TypeError("Tokyo release command did not return a JSON object")
        return payload

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
        "--protected-ticket-id",
        action="append",
        default=[],
        help=(
            "Exact fully protected Ticket allowed across this one guarded "
            "identity handover; repeat once per active Ticket."
        ),
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
        protected_ticket_ids=tuple(args.protected_ticket_id),
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
