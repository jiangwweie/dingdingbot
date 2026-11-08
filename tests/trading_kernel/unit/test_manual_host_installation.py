from unittest.mock import Mock

import pytest

from scripts.trading_kernel.install_manual_host import (
    ManualHostTarget,
    install_manual_host,
)
from scripts.trading_kernel.manual_host_bootstrap import (
    check_host_identity,
    extract_plain_archive,
)


def target():
    return ManualHostTarget(
        ssh_target="kr",
        public_ip="43.133.243.174",
        machine_id="f956f502ced4461e9d0fcc0ef637abd6",
    )


@pytest.mark.parametrize("value", ["tokyo", "-oProxyCommand=bad", "user@host bad", ""])
def test_target_rejects_unsafe_or_automatic_alias(value):
    with pytest.raises(ValueError):
        target().model_copy(update={"ssh_target": value}).__class__.model_validate(
            {**target().model_dump(), "ssh_target": value}
        )


def test_wrong_host_prevents_every_mutation_and_upload():
    backend = Mock()
    backend.inspect.return_value = {
        "machine_id": "a" * 32,
        "product_id": "brc-app-manual-v1",
        "public_ip": "43.133.243.174",
        "runtime_present": False,
    }
    with pytest.raises(ValueError, match="identity"):
        install_manual_host(backend, target=target(), phase="database", artifacts=None)
    backend.apply.assert_not_called()
    backend.upload.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [{"product_id": "auto"}, {"public_ip": "43.133.176.150"}, {"machine_id": "a" * 32}],
)
def test_remote_identity_is_checked_before_filesystem_mutation(changes):
    actual = {
        "machine_id": target().machine_id,
        "product_id": "brc-app-manual-v1",
        "public_ip": target().public_ip,
    }
    with pytest.raises(ValueError, match="identity"):
        check_host_identity({**actual, **changes}, target().model_dump())


def test_unknown_phase_cannot_enable_entry():
    backend = Mock()
    with pytest.raises(ValueError):
        install_manual_host(
            backend, target=target(), phase="promote-entry", artifacts=None
        )
    backend.apply.assert_not_called()


@pytest.mark.parametrize("name", ["../escape", "/root/escape", "src/../../escape"])
def test_artifact_extraction_rejects_path_escape(tmp_path, name):
    import io
    import tarfile

    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as t:
        info = tarfile.TarInfo(name)
        info.size = 1
        t.addfile(info, io.BytesIO(b"x"))
    data.seek(0)
    with pytest.raises(ValueError):
        extract_plain_archive(data, tmp_path / "out")
    assert not (tmp_path / "escape").exists()


def test_legacy_host_marker_cannot_be_reassigned(tmp_path):
    expected = target().model_dump()
    with pytest.raises(ValueError):
        check_host_identity({"product_id": "brc-auto-tokyo-v1"}, expected)


def test_existing_symlink_inside_destination_cannot_redirect_archive_write(tmp_path):
    import io
    import tarfile

    dest = tmp_path / "out"
    dest.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (dest / "src").symlink_to(outside, target_is_directory=True)
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as t:
        entry = tarfile.TarInfo("src/escape")
        entry.size = 1
        t.addfile(entry, io.BytesIO(b"x"))
    data.seek(0)
    with pytest.raises(ValueError):
        extract_plain_archive(data, dest)
    assert not (outside / "escape").exists()


def test_secret_file_rejects_existing_public_permissions(tmp_path):
    from scripts.trading_kernel.manual_host_bootstrap import write_private

    p = tmp_path / "secret"
    p.write_text("existing")
    p.chmod(0o644)
    with pytest.raises(ValueError):
        write_private(p, "existing")


def test_database_phase_receives_the_exact_committed_candidate(monkeypatch):
    import json
    from types import SimpleNamespace

    from scripts.trading_kernel import install_manual_host as module

    commands = []
    monkeypatch.setattr(
        module.subprocess, "check_output", lambda args, **kw: 'print("bootstrap")'
    )

    def run(args, **kw):
        commands.append(args)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"machine_id": target().machine_id}).encode(),
        )

    monkeypatch.setattr(module.subprocess, "run", run)
    backend = module.SshManualInstallationBackend(target(), "a" * 40)
    backend.apply("database")
    assert "--commit " + ("a" * 40) in commands[0][-1]
    assert "StrictHostKeyChecking=yes" in commands[0]


def test_artifact_validation_rejects_wrong_surface_commit():
    from scripts.trading_kernel.manual_host_bootstrap import validate_certificates

    commit = "a" * 40
    common = {
        "product_id": "brc-app-manual-v1",
        "status": "pass",
        "release_commit": commit,
        "schema_revision": "head",
    }
    certificates = {name: {**common} for name in ("kernel", "api", "static")}
    certificates["kernel"]["release_level"] = "R4"
    validate_certificates(certificates, commit)
    certificates["api"]["release_commit"] = "b" * 40
    with pytest.raises(ValueError):
        validate_certificates(certificates, commit)


def test_missing_fence_fact_does_not_authorize_database_phase():
    backend = Mock()
    backend.inspect.return_value = {
        "machine_id": target().machine_id,
        "public_ip": target().public_ip,
        "product_id": "brc-app-manual-v1",
        "runtime_present": False,
    }
    with pytest.raises(ValueError):
        install_manual_host(backend, target=target(), phase="database", artifacts=None)
    backend.apply.assert_not_called()


@pytest.mark.parametrize("phase", ["initialize", "install-console"])
def test_account_and_console_phases_are_exact_explicit_operations(phase):
    backend = Mock()
    backend.inspect.return_value = {
        "machine_id": target().machine_id,
        "product_id": "brc-app-manual-v1",
        "public_ip": target().public_ip,
        "runtime_present": False,
        "entry_fenced": True,
    }
    install_manual_host(backend, target=target(), phase=phase, artifacts=None)
    backend.apply.assert_called_once_with(phase)
    backend.upload.assert_not_called()


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "commit",
        "schema",
        "paused",
        "tickets",
        "commands",
        "positions",
        "incidents",
        "active_writer",
    ],
)
def test_stopped_manual_upgrade_refuses_every_identity_or_activity_fault(
    tmp_path, monkeypatch, fault
):
    import json
    from types import SimpleNamespace

    from scripts.trading_kernel import manual_host_bootstrap as module

    etc = tmp_path / "etc/brc"
    etc.mkdir(parents=True)
    (etc / "trading-kernel.write-fenced").touch()
    (etc / "trading-kernel.env").touch()
    release = tmp_path / "release"
    release.mkdir()
    (release / ".brc-runtime-commit").write_text("a" * 40)
    (release / ".brc-schema-revision").write_text("head")
    current = tmp_path / "opt/brc/current"
    current.parent.mkdir(parents=True)
    current.symlink_to(release, target_is_directory=True)
    state = {
        "commit": "a" * 40,
        "schema": "head",
        "paused": True,
        "tickets": False,
        "commands": False,
        "positions": False,
        "incidents": False,
    }
    if fault in {"commit", "schema"}:
        state[fault] = "wrong"
    elif fault == "paused":
        state[fault] = False
    elif fault and fault != "active_writer":
        state[fault] = True
    monkeypatch.setattr(module, "read_database", lambda query: json.dumps(state))
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=0 if fault == "active_writer" else 3
        ),
    )
    if fault:
        with pytest.raises(ValueError):
            module.require_stopped_upgrade(filesystem_root=tmp_path)
    else:
        assert module.require_stopped_upgrade(filesystem_root=tmp_path) == state


def test_stopped_upgrade_requires_fence_before_any_database_read(tmp_path, monkeypatch):
    from scripts.trading_kernel import manual_host_bootstrap as module

    read = Mock()
    monkeypatch.setattr(module, "read_database", read)
    with pytest.raises(ValueError):
        module.require_stopped_upgrade(filesystem_root=tmp_path)
    read.assert_not_called()
