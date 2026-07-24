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
from pathlib import Path
from typing import Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


SCHEMA_REVISION = "0001_initial"
EXPECTED_CONFIGURED_LEVERAGE = 5
RELEASE_ROOT = "/opt/brc/releases"
CURRENT_RELEASE = "/opt/brc/current"
RUNTIME_ENV = "/etc/brc/trading-kernel.env"
WRITE_FENCE = "/etc/brc/trading-kernel.write-fenced"
ENTRY_SERVICE = "brc-trading-kernel-entry-worker.service"
SAFETY_SERVICES = (
    "brc-trading-kernel-observation-worker.service",
    "brc-trading-kernel-lifecycle-worker.service",
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

    def probe_exchange(self, release: str) -> Mapping[str, object]: ...

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

    def activate_release(
        self,
        release: str,
        commit: str,
        schema_revision: str,
        seed_identity: str,
    ) -> None: ...

    def start_services(self, services: tuple[str, ...]) -> None: ...

    def fence_entry(self) -> None: ...


def deploy_tokyo_release(
    backend: TokyoReleaseBackend,
    plan: DeploymentPlan,
) -> DeploymentResult:
    current_release = backend.read_current_release()
    if current_release == plan.target_release:
        raise DeploymentBlocked("target release is already current")
    backend.install_release(plan.target_commit, plan.target_release)
    current_certification = backend.certify_flat(plan.target_release)
    current_probe = backend.probe_exchange(plan.target_release)
    current_identity = _require_release_facts(
        current_certification,
        current_probe,
        expected_leverage=plan.expected_configured_leverage,
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

        deployment_identity = backend.deploy_identity(
            plan.target_release,
            plan.target_commit,
            plan.schema_revision,
        )
        seed_identity = _require_deployment_identity(
            deployment_identity,
            plan,
        )
        backend.activate_release(
            plan.target_release,
            plan.target_commit,
            plan.schema_revision,
            seed_identity,
        )
        backend.start_services(SAFETY_SERVICES)

        target_certification = backend.certify_flat(plan.target_release)
        target_probe = backend.probe_exchange(plan.target_release)
        target_identity = _require_release_facts(
            target_certification,
            target_probe,
            expected_leverage=plan.expected_configured_leverage,
        )
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

        if plan.enable_entry:
            backend.start_services((ENTRY_SERVICE,))
        expected_services = ALL_SERVICES if plan.enable_entry else SAFETY_SERVICES
        active_services = backend.services_active(ALL_SERVICES)
        if active_services != frozenset(expected_services):
            raise DeploymentBlocked(
                "runtime service state differs from deployment plan"
            )
    except Exception:
        if services_stopped:
            backend.fence_entry()
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
    rules = probe.get("rules")
    if not isinstance(rules, list) or len(rules) != 6:
        raise DeploymentBlocked("production instrument rule set is incomplete")
    configured = {
        int(str(rule.get("configured_leverage", -1)))
        for rule in rules
        if isinstance(rule, Mapping)
    }
    if configured != {expected_leverage}:
        raise DeploymentBlocked(
            "production configured leverage differs from fixed 5x policy"
        )
    return identity


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

    def probe_exchange(self, release: str) -> Mapping[str, object]:
        return self._release_json(
            release,
            "scripts/trading_kernel/probe_production_runtime.py",
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
        if ENTRY_SERVICE in services:
            if services != (ENTRY_SERVICE,):
                raise ValueError("ENTRY must be started as the final isolated phase")
            self._remote(("sudo", "rm", "-f", WRITE_FENCE))
        self._remote(("sudo", "systemctl", "enable", "--now", *services))

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
