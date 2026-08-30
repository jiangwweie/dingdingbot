#!/usr/bin/env python3
"""Deploy one independent Owner Console static or API release to Tokyo."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.owner_console.certify_release_candidate import (
    validate_owner_api_release_certification,
)
from scripts.owner_console.certify_static_release_candidate import (
    validate_owner_static_release_certification,
)

STATIC_RELEASE_ROOT = "/opt/brc/owner-console/releases"
STATIC_CURRENT_RELEASE = "/opt/brc/owner-console/current"
API_RELEASE_ROOT = "/opt/brc/owner-console-api/releases"
API_CURRENT_RELEASE = "/opt/brc/owner-console-api/current"
LEGACY_KERNEL_RELEASE = "/opt/brc/current"
API_SERVICE = "brc-owner-console-api.service"
API_UNIT = "/etc/systemd/system/brc-owner-console-api.service"
API_UNIT_BACKUP = "/run/brc-owner-console-api.service.before-release"
API_SOCKET = "/run/brc-owner-console/api.sock"
DEFAULT_PUBLIC_URL = "https://jiaoyingpan.cloud/trading/"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class OwnerConsoleReleaseKind(StrEnum):
    STATIC = "static"
    API = "api"


@dataclass(frozen=True)
class OwnerConsoleReleasePlan:
    kind: OwnerConsoleReleaseKind
    target_commit: str
    target_release: str
    static_dist: Path | None = None
    public_url: str = DEFAULT_PUBLIC_URL

    def __post_init__(self) -> None:
        if _COMMIT.fullmatch(self.target_commit) is None:
            raise ValueError("target commit must be an exact lowercase 40-hex SHA")
        expected_release = (
            f"{STATIC_RELEASE_ROOT}/{self.target_commit}"
            if self.kind is OwnerConsoleReleaseKind.STATIC
            else f"{API_RELEASE_ROOT}/{self.target_commit}"
        )
        if self.target_release != expected_release:
            raise ValueError("Owner Console release path differs from target commit")
        if self.kind is OwnerConsoleReleaseKind.STATIC:
            if self.static_dist is None:
                raise ValueError("static release requires one local dist directory")
            if not self.public_url.startswith("https://"):
                raise ValueError("static release smoke URL must use HTTPS")
        elif self.static_dist is not None:
            raise ValueError("API release cannot include a static dist directory")


@dataclass(frozen=True)
class ReleasePhaseDuration:
    phase: str
    duration_ms: int


@dataclass(frozen=True)
class OwnerConsoleReleaseResult:
    status: str
    release_level: str
    kind: OwnerConsoleReleaseKind
    target_commit: str
    target_release: str
    phase_durations_ms: tuple[ReleasePhaseDuration, ...]


class OwnerConsoleReleaseBackend(Protocol):
    def read_current_release(self, kind: OwnerConsoleReleaseKind) -> str: ...

    def install_release(self, plan: OwnerConsoleReleasePlan) -> None: ...

    def activate_release(self, plan: OwnerConsoleReleasePlan) -> None: ...

    def smoke_release(self, plan: OwnerConsoleReleasePlan) -> None: ...

    def restore_release(
        self,
        kind: OwnerConsoleReleaseKind,
        previous_release: str,
    ) -> None: ...


def deploy_owner_console_release(
    backend: OwnerConsoleReleaseBackend,
    plan: OwnerConsoleReleasePlan,
) -> OwnerConsoleReleaseResult:
    previous_release = backend.read_current_release(plan.kind)
    durations: list[ReleasePhaseDuration] = []
    if previous_release == plan.target_release:
        _timed(durations, "smoke", lambda: backend.smoke_release(plan))
        return _release_result(plan, durations)
    activated = False
    try:
        _timed(durations, "install", lambda: backend.install_release(plan))
        activated = True
        _timed(durations, "activate", lambda: backend.activate_release(plan))
        _timed(durations, "smoke", lambda: backend.smoke_release(plan))
    except Exception:
        if activated:
            backend.restore_release(plan.kind, previous_release)
        raise
    return _release_result(plan, durations)


def _release_result(
    plan: OwnerConsoleReleasePlan,
    durations: list[ReleasePhaseDuration],
) -> OwnerConsoleReleaseResult:
    return OwnerConsoleReleaseResult(
        status="pass",
        release_level="R1" if plan.kind is OwnerConsoleReleaseKind.STATIC else "R2",
        kind=plan.kind,
        target_commit=plan.target_commit,
        target_release=plan.target_release,
        phase_durations_ms=tuple(durations),
    )


def _timed(
    durations: list[ReleasePhaseDuration],
    phase: str,
    action: Callable[[], None],
) -> None:
    started = time.monotonic()
    try:
        action()
    finally:
        durations.append(
            ReleasePhaseDuration(
                phase=phase,
                duration_ms=max(0, int((time.monotonic() - started) * 1_000)),
            )
        )


@dataclass(frozen=True)
class _CommandResult:
    returncode: int
    stdout: str
    stderr: str


class SshOwnerConsoleReleaseBackend:
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

    def read_current_release(self, kind: OwnerConsoleReleaseKind) -> str:
        current = _current_release(kind)
        result = self._remote(("sudo", "readlink", "-f", current), check=False)
        if result.returncode == 0:
            return result.stdout
        if result.returncode == 1:
            return ""
        raise RuntimeError(f"Owner Console current-release preflight failed: {result.stderr}")

    def install_release(self, plan: OwnerConsoleReleasePlan) -> None:
        self._remove_and_create_release(plan)
        if plan.kind is OwnerConsoleReleaseKind.STATIC:
            self._install_static_release(plan)
        else:
            self._install_api_release(plan)

    def activate_release(self, plan: OwnerConsoleReleasePlan) -> None:
        if plan.kind is OwnerConsoleReleaseKind.STATIC:
            self._remote(
                (
                    "sudo",
                    "ln",
                    "-sfn",
                    plan.target_release,
                    STATIC_CURRENT_RELEASE,
                )
            )
            return
        self._backup_api_unit()
        self._remote(
            (
                "sudo",
                "ln",
                "-sfn",
                plan.target_release,
                API_CURRENT_RELEASE,
            )
        )
        self._install_api_unit(plan.target_release)
        self._remote(("sudo", "systemctl", "daemon-reload"))
        self._remote(("sudo", "systemctl", "restart", API_SERVICE))

    def smoke_release(self, plan: OwnerConsoleReleasePlan) -> None:
        current = _current_release(plan.kind)
        if self.read_current_release(plan.kind) != plan.target_release:
            raise RuntimeError("Owner Console current symlink differs from target")
        marker = _marker_name(plan.kind)
        if self._remote(("sudo", "cat", f"{current}/{marker}")).stdout != plan.target_commit:
            raise RuntimeError("Owner Console release marker differs from target")
        if plan.kind is OwnerConsoleReleaseKind.STATIC:
            dist = plan.static_dist
            if dist is None:
                raise RuntimeError("static dist disappeared before smoke")
            expected_hash = sha256((dist / "index.html").read_bytes()).hexdigest()
            remote_hash = self._remote(
                ("sudo", "sha256sum", f"{current}/dist/index.html")
            ).stdout.split()[0]
            if remote_hash != expected_hash:
                raise RuntimeError("Owner Console static index hash differs")
            status = self._remote(
                (
                    "curl",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    "10",
                    "--output",
                    "/dev/null",
                    "--write-out",
                    "%{http_code}",
                    plan.public_url,
                )
            ).stdout
            if status != "200":
                raise RuntimeError("Owner Console public static smoke failed")
            return
        if self._remote(
            ("sudo", "systemctl", "is-active", "--quiet", API_SERVICE),
            check=False,
        ).returncode != 0:
            raise RuntimeError("Owner Console API service is not active")
        self._wait_for_api_health()

    def _wait_for_api_health(self) -> None:
        deadline = time.monotonic() + self._timeout_seconds
        while True:
            payload = self._remote(
                (
                    "sudo",
                    "curl",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    "10",
                    "--unix-socket",
                    API_SOCKET,
                    "http://localhost/healthz",
                ),
                check=False,
            )
            if payload.returncode == 0:
                try:
                    if json.loads(payload.stdout) == {"status": "ok"}:
                        return
                except json.JSONDecodeError:
                    pass
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("Owner Console API health smoke timed out")
            time.sleep(min(1.0, remaining))

    def restore_release(
        self,
        kind: OwnerConsoleReleaseKind,
        previous_release: str,
    ) -> None:
        current = _current_release(kind)
        if kind is OwnerConsoleReleaseKind.STATIC:
            if previous_release:
                self._remote(("sudo", "ln", "-sfn", previous_release, current))
            else:
                self._remote(("sudo", "unlink", current), check=False)
            return
        if previous_release:
            self._remote(("sudo", "ln", "-sfn", previous_release, current))
            self._install_api_unit(previous_release)
        else:
            self._remote(("sudo", "unlink", current), check=False)
            if self._remote(("sudo", "test", "-f", API_UNIT_BACKUP), check=False).returncode == 0:
                self._remote(("sudo", "cp", "-a", API_UNIT_BACKUP, API_UNIT))
        self._remote(("sudo", "systemctl", "daemon-reload"))
        self._remote(("sudo", "systemctl", "restart", API_SERVICE))

    def _remove_and_create_release(self, plan: OwnerConsoleReleasePlan) -> None:
        self._remote(("sudo", "rm", "-rf", plan.target_release))
        owner = "root" if plan.kind is OwnerConsoleReleaseKind.STATIC else "brc"
        group = "www-data" if plan.kind is OwnerConsoleReleaseKind.STATIC else "brc"
        self._remote(
            (
                "sudo",
                "install",
                "-d",
                "-o",
                owner,
                "-g",
                group,
                "-m",
                "0750",
                plan.target_release,
            )
        )

    def _install_static_release(self, plan: OwnerConsoleReleasePlan) -> None:
        dist = plan.static_dist
        if dist is None or not dist.is_dir() or not (dist / "index.html").is_file():
            raise ValueError("Owner Console static dist is incomplete")
        target_dist = f"{plan.target_release}/dist"
        self._remote(
            (
                "sudo",
                "install",
                "-d",
                "-o",
                "root",
                "-g",
                "www-data",
                "-m",
                "0750",
                target_dist,
            )
        )
        self._upload_directory(dist, target_dist)
        self._write_marker(plan)
        self._remote(("sudo", "chown", "-R", "root:www-data", plan.target_release))
        self._remote(
            ("sudo", "find", plan.target_release, "-type", "d", "-exec", "chmod", "0750", "{}", "+")
        )
        self._remote(
            ("sudo", "find", plan.target_release, "-type", "f", "-exec", "chmod", "0640", "{}", "+")
        )

    def _install_api_release(self, plan: OwnerConsoleReleasePlan) -> None:
        self._upload_git_archive(plan.target_commit, plan.target_release)
        target_venv = f"{plan.target_release}/.venv-owner-console"
        sources = (
            f"{API_CURRENT_RELEASE}/.venv-owner-console",
            f"{LEGACY_KERNEL_RELEASE}/.venv-owner-console",
        )
        source_venv = next(
            (
                source
                for source in sources
                if self._remote(("sudo", "test", "-d", source), check=False).returncode == 0
            ),
            None,
        )
        if source_venv is None:
            self._remote(("sudo", "-u", "brc", "python3", "-m", "venv", target_venv))
        else:
            self._remote(("sudo", "cp", "-a", source_venv, target_venv))
        self._remote(("sudo", "chown", "-R", "brc:brc", plan.target_release))
        target_python = f"{target_venv}/bin/python"
        self._run_api_venv_module(
            release=plan.target_release,
            target_python=target_python,
            module_args=("ensurepip", "--upgrade"),
        )
        self._run_api_venv_module(
            release=plan.target_release,
            target_python=target_python,
            module_args=(
                "pip",
                "install",
                "--disable-pip-version-check",
                "--requirement",
                f"{plan.target_release}/requirements-owner-console.txt",
            ),
        )
        self._write_marker(plan)

    def _run_api_venv_module(
        self,
        *,
        release: str,
        target_python: str,
        module_args: tuple[str, ...],
    ) -> None:
        command = (
            f"cd {shlex.quote(release)} && exec "
            f"{shlex.join((target_python, '-m', *module_args))}"
        )
        self._remote(("sudo", "-u", "brc", "/bin/bash", "-lc", command))

    def _backup_api_unit(self) -> None:
        if self._remote(("sudo", "test", "-f", API_UNIT), check=False).returncode == 0:
            self._remote(("sudo", "cp", "-a", API_UNIT, API_UNIT_BACKUP))

    def _install_api_unit(self, release: str) -> None:
        self._remote(
            (
                "sudo",
                "install",
                "-o",
                "root",
                "-g",
                "root",
                "-m",
                "0644",
                f"{release}/deploy/owner-console/systemd/{API_SERVICE}",
                API_UNIT,
            )
        )
        self._remote(("sudo", "systemd-analyze", "verify", API_UNIT))

    def _write_marker(self, plan: OwnerConsoleReleasePlan) -> None:
        marker = f"{plan.target_release}/{_marker_name(plan.kind)}"
        self._remote(
            ("sudo", "tee", marker),
            input_text=plan.target_commit + "\n",
        )

    def _upload_git_archive(self, commit: str, release: str) -> None:
        archive = subprocess.Popen(
            ("git", "archive", "--format=tar", commit),
            cwd=self._repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._stream_archive(archive, release)

    def _upload_directory(self, source: Path, release: str) -> None:
        archive = subprocess.Popen(
            ("tar", "-cf", "-", "."),
            cwd=source,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._stream_archive(archive, release)

    def _stream_archive(self, archive: subprocess.Popen[bytes], release: str) -> None:
        if archive.stdout is None:
            raise RuntimeError("release archive stdout pipe is unavailable")
        remote_command = shlex.join(("sudo", "tar", "-xf", "-", "-C", release))
        ssh = subprocess.Popen(
            (*self._ssh_base(), "--", remote_command),
            stdin=archive.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        archive.stdout.close()
        _, ssh_stderr = ssh.communicate(timeout=max(self._timeout_seconds, 120))
        archive_stderr = archive.stderr.read() if archive.stderr else b""
        archive_code = archive.wait()
        if archive_code != 0 or ssh.returncode != 0:
            detail = (archive_stderr + ssh_stderr)[-2_000:].decode(
                "utf-8", errors="replace"
            )
            raise RuntimeError(f"Owner Console release upload failed: {detail}")

    def _remote(
        self,
        argv: tuple[str, ...],
        *,
        check: bool = True,
        input_text: str | None = None,
    ) -> _CommandResult:
        completed = subprocess.run(
            (*self._ssh_base(), "--", shlex.join(argv)),
            check=False,
            capture_output=True,
            text=True,
            input=input_text,
            timeout=self._timeout_seconds,
        )
        result = _CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout.strip(),
            stderr=completed.stderr.strip(),
        )
        if check and result.returncode != 0:
            raise RuntimeError(
                f"Tokyo Owner Console command failed ({result.returncode}): "
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


def _current_release(kind: OwnerConsoleReleaseKind) -> str:
    return (
        STATIC_CURRENT_RELEASE
        if kind is OwnerConsoleReleaseKind.STATIC
        else API_CURRENT_RELEASE
    )


def _marker_name(kind: OwnerConsoleReleaseKind) -> str:
    return (
        ".brc-owner-console-static-commit"
        if kind is OwnerConsoleReleaseKind.STATIC
        else ".brc-owner-console-api-commit"
    )


def _resolve_commit(reference: str) -> str:
    completed = subprocess.run(
        ("git", "rev-parse", "--verify", f"{reference}^{{commit}}"),
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    commit = completed.stdout.strip()
    if _COMMIT.fullmatch(commit) is None:
        raise ValueError("resolved Owner Console release commit is invalid")
    return commit


def _require_clean_control_worktree() -> None:
    status = subprocess.run(
        ("git", "status", "--porcelain"),
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if status:
        raise ValueError("Owner Console release control worktree must be clean")


@contextmanager
def _build_static_dist(commit: str) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="brc-owner-console-static-") as raw:
        build_root = Path(raw)
        archive = subprocess.Popen(
            ("git", "archive", "--format=tar", commit),
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if archive.stdout is None:
            raise RuntimeError("static release archive pipe is unavailable")
        extracted = subprocess.run(
            ("tar", "-xf", "-", "-C", str(build_root)),
            stdin=archive.stdout,
            check=False,
            capture_output=True,
        )
        archive.stdout.close()
        archive_stderr = archive.stderr.read() if archive.stderr else b""
        archive_code = archive.wait()
        if archive_code != 0 or extracted.returncode != 0:
            detail = (archive_stderr + extracted.stderr)[-2_000:].decode(
                "utf-8", errors="replace"
            )
            raise RuntimeError(f"static release checkout failed: {detail}")
        subprocess.run(
            (
                "pnpm",
                "--dir",
                "frontend/owner-console",
                "install",
                "--frozen-lockfile",
            ),
            cwd=build_root,
            check=True,
        )
        subprocess.run(
            ("pnpm", "--dir", "frontend/owner-console", "build"),
            cwd=build_root,
            check=True,
        )
        dist = build_root / "frontend/owner-console/dist"
        if not (dist / "index.html").is_file():
            raise RuntimeError("Owner Console frontend build did not produce index.html")
        yield dist


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=tuple(kind.value for kind in OwnerConsoleReleaseKind), required=True)
    parser.add_argument("--commit", default="HEAD")
    parser.add_argument(
        "--target",
        default=os.getenv("TRADING_KERNEL_TOKYO_SSH_TARGET", "tokyo"),
    )
    parser.add_argument("--public-url", default=DEFAULT_PUBLIC_URL)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    kind = OwnerConsoleReleaseKind(args.kind)
    commit = _resolve_commit(args.commit)
    _require_clean_control_worktree()
    if kind is OwnerConsoleReleaseKind.STATIC:
        validate_owner_static_release_certification(REPO_ROOT, commit)
    else:
        validate_owner_api_release_certification(REPO_ROOT, commit)
    root = STATIC_RELEASE_ROOT if kind is OwnerConsoleReleaseKind.STATIC else API_RELEASE_ROOT
    backend = SshOwnerConsoleReleaseBackend(
        target=args.target,
        repo_root=REPO_ROOT,
        timeout_seconds=args.timeout_seconds,
    )
    if kind is OwnerConsoleReleaseKind.STATIC:
        with _build_static_dist(commit) as static_dist:
            result = deploy_owner_console_release(
                backend,
                OwnerConsoleReleasePlan(
                    kind=kind,
                    target_commit=commit,
                    target_release=f"{root}/{commit}",
                    static_dist=static_dist,
                    public_url=args.public_url,
                ),
            )
    else:
        result = deploy_owner_console_release(
            backend,
            OwnerConsoleReleasePlan(
                kind=kind,
                target_commit=commit,
                target_release=f"{root}/{commit}",
                public_url=args.public_url,
            ),
        )
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
