from __future__ import annotations

from pathlib import Path

import pytest

from scripts.owner_console import deploy_release as release_module
from scripts.owner_console.deploy_release import (
    OwnerConsoleReleaseKind,
    OwnerConsoleReleasePlan,
    SshOwnerConsoleReleaseBackend,
    deploy_owner_console_release,
)

TARGET_COMMIT = "a" * 40


@pytest.mark.parametrize(
    ("kind", "release", "expected_level"),
    (
        (
            OwnerConsoleReleaseKind.STATIC,
            f"/opt/brc/owner-console/releases/{TARGET_COMMIT}",
            "R1",
        ),
        (
            OwnerConsoleReleaseKind.API,
            f"/opt/brc/owner-console-api/releases/{TARGET_COMMIT}",
            "R2",
        ),
    ),
)
def test_owner_console_release_changes_only_its_selected_surface(
    kind: OwnerConsoleReleaseKind,
    release: str,
    expected_level: str,
) -> None:
    backend = FakeOwnerConsoleReleaseBackend()
    plan = OwnerConsoleReleasePlan(
        kind=kind,
        target_commit=TARGET_COMMIT,
        target_release=release,
        static_dist=Path("/tmp/dist") if kind is OwnerConsoleReleaseKind.STATIC else None,
    )

    result = deploy_owner_console_release(backend, plan)

    assert result.status == "pass"
    assert result.release_level == expected_level
    assert backend.calls == [
        ("read_current_release", kind),
        ("install_release", plan),
        ("activate_release", plan),
        ("smoke_release", plan),
    ]


def test_owner_console_release_restores_only_its_previous_symlink_on_smoke_failure() -> None:
    backend = FakeOwnerConsoleReleaseBackend(fail_smoke=True)
    plan = OwnerConsoleReleasePlan(
        kind=OwnerConsoleReleaseKind.API,
        target_commit=TARGET_COMMIT,
        target_release=f"/opt/brc/owner-console-api/releases/{TARGET_COMMIT}",
    )

    with pytest.raises(RuntimeError, match="smoke failed"):
        deploy_owner_console_release(backend, plan)

    assert backend.calls[-1] == (
        "restore_release",
        OwnerConsoleReleaseKind.API,
        "/opt/brc/owner-console-api/releases/previous",
    )


def test_owner_console_release_plan_rejects_kernel_or_cross_surface_paths() -> None:
    with pytest.raises(ValueError, match="release path differs"):
        OwnerConsoleReleasePlan(
            kind=OwnerConsoleReleaseKind.API,
            target_commit=TARGET_COMMIT,
            target_release=f"/opt/brc/releases/brc-trading-kernel-{TARGET_COMMIT[:12]}",
        )


def test_repeated_exact_owner_console_release_runs_only_smoke() -> None:
    target = f"/opt/brc/owner-console-api/releases/{TARGET_COMMIT}"
    backend = FakeOwnerConsoleReleaseBackend(current_release=target)
    plan = OwnerConsoleReleasePlan(
        kind=OwnerConsoleReleaseKind.API,
        target_commit=TARGET_COMMIT,
        target_release=target,
    )

    deploy_owner_console_release(backend, plan)

    assert backend.calls == [
        ("read_current_release", OwnerConsoleReleaseKind.API),
        ("smoke_release", plan),
    ]


def test_api_release_bootstraps_pip_through_its_target_venv_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A copied production venv may deliberately omit the pip console script."""

    backend = SshOwnerConsoleReleaseBackend(
        target="tokyo",
        repo_root=Path("/repo"),
        timeout_seconds=30,
    )
    plan = OwnerConsoleReleasePlan(
        kind=OwnerConsoleReleaseKind.API,
        target_commit=TARGET_COMMIT,
        target_release=f"/opt/brc/owner-console-api/releases/{TARGET_COMMIT}",
    )
    commands: list[tuple[str, ...]] = []

    monkeypatch.setattr(backend, "_upload_git_archive", lambda *_: None)
    monkeypatch.setattr(backend, "_write_marker", lambda *_: None)

    def _remote(
        argv: tuple[str, ...],
        *,
        check: bool = True,
        input_text: str | None = None,
    ) -> release_module._CommandResult:
        del check, input_text
        commands.append(argv)
        return release_module._CommandResult(0, "", "")

    monkeypatch.setattr(backend, "_remote", _remote)

    backend._install_api_release(plan)

    target_python = f"{plan.target_release}/.venv-owner-console/bin/python"
    expected_prefix = ("sudo", "-u", "brc", "/bin/bash", "-lc")
    shell_commands = [command[-1] for command in commands if command[:5] == expected_prefix]
    assert f"cd {plan.target_release}" in shell_commands[0]
    assert f"{target_python} -m ensurepip --upgrade" in shell_commands[0]
    assert f"cd {plan.target_release}" in shell_commands[1]
    assert (
        f"{target_python} -m pip install --disable-pip-version-check --requirement "
        f"{plan.target_release}/requirements-owner-console.txt"
    ) in shell_commands[1]
    assert not any(command[-1].endswith("/bin/pip") for command in commands)


def test_api_health_smoke_retries_until_the_unix_socket_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = SshOwnerConsoleReleaseBackend(
        target="tokyo",
        repo_root=Path("/repo"),
        timeout_seconds=30,
    )
    attempts = 0

    def _remote(
        argv: tuple[str, ...],
        *,
        check: bool = True,
        input_text: str | None = None,
    ) -> release_module._CommandResult:
        nonlocal attempts
        del check, input_text
        if argv[:3] == ("sudo", "curl", "--fail"):
            attempts += 1
            return release_module._CommandResult(
                7 if attempts == 1 else 0,
                "" if attempts == 1 else '{"status":"ok"}',
                "",
            )
        return release_module._CommandResult(0, "", "")

    monkeypatch.setattr(backend, "_remote", _remote)
    monkeypatch.setattr(release_module.time, "sleep", lambda _: None)

    backend._wait_for_api_health()

    assert attempts == 2


class FakeOwnerConsoleReleaseBackend:
    def __init__(
        self,
        *,
        fail_smoke: bool = False,
        current_release: str | None = None,
    ) -> None:
        self.fail_smoke = fail_smoke
        self.current_release = current_release
        self.calls: list[tuple[object, ...]] = []

    def read_current_release(self, kind: OwnerConsoleReleaseKind) -> str:
        self.calls.append(("read_current_release", kind))
        if self.current_release is not None:
            return self.current_release
        return f"/opt/brc/owner-console{'-api' if kind is OwnerConsoleReleaseKind.API else ''}/releases/previous"

    def install_release(self, plan: OwnerConsoleReleasePlan) -> None:
        self.calls.append(("install_release", plan))

    def activate_release(self, plan: OwnerConsoleReleasePlan) -> None:
        self.calls.append(("activate_release", plan))

    def smoke_release(self, plan: OwnerConsoleReleasePlan) -> None:
        self.calls.append(("smoke_release", plan))
        if self.fail_smoke:
            raise RuntimeError("smoke failed")

    def restore_release(
        self,
        kind: OwnerConsoleReleaseKind,
        previous_release: str,
    ) -> None:
        self.calls.append(("restore_release", kind, previous_release))
