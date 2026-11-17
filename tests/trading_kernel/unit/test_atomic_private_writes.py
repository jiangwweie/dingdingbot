"""Installation state must reach stable temporary storage before publication."""

import stat

import pytest

from scripts.trading_kernel import manual_host_bootstrap as host


@pytest.mark.parametrize("name", ["upgrade-progress.json", "trading-kernel.env"])
def test_private_write_syncs_file_before_replace_then_directory(
    tmp_path, monkeypatch, name
):
    target = tmp_path / name
    target.write_text("old")
    events = []
    real_sync = host.os.fsync
    real_replace = host.os.replace

    def sync(fd):
        kind = "file" if stat.S_ISREG(host.os.fstat(fd).st_mode) else "directory"
        if kind == "file":
            assert target.read_text() == "old"
            temporary = list(tmp_path.glob(".brc-*"))
            assert len(temporary) == 1 and temporary[0].read_text() == "new"
        events.append(kind)
        real_sync(fd)

    def replace(source, destination):
        assert events == ["file"]
        from pathlib import Path

        assert source != target and Path(source).read_text() == "new"
        events.append("replace")
        real_replace(source, destination)

    monkeypatch.setattr(host.os, "fsync", sync)
    monkeypatch.setattr(host.os, "replace", replace)
    host.write_private(target, "new", overwrite=True)
    assert events == ["file", "replace", "directory"] and target.read_text() == "new"


def test_file_sync_failure_preserves_old_path_and_cleans_temporary(
    tmp_path, monkeypatch
):
    target = tmp_path / "upgrade-progress.json"
    target.write_text("old")

    def fail(_fd):
        raise OSError("injected fsync failure")

    monkeypatch.setattr(host.os, "fsync", fail)
    with pytest.raises(OSError, match="fsync failure"):
        host.write_private(target, "new", overwrite=True)
    assert target.read_text() == "old"
    assert list(tmp_path.iterdir()) == [target]


def test_replace_failure_preserves_original_and_cleans_temporary(tmp_path, monkeypatch):
    target = tmp_path / "trading-kernel.env"
    target.write_text("old")

    def fail(*args):
        raise OSError("injected replace failure")

    monkeypatch.setattr(host.os, "replace", fail)
    with pytest.raises(OSError, match="replace failure"):
        host.write_private(target, "new", overwrite=True)
    assert target.read_text() == "old" and list(tmp_path.iterdir()) == [target]


def test_directory_sync_failure_is_reported_after_published_complete_content(
    tmp_path, monkeypatch
):
    target = tmp_path / "upgrade-progress.json"
    target.write_text("old")
    real_sync = host.os.fsync

    def sync(fd):
        if stat.S_ISDIR(host.os.fstat(fd).st_mode):
            raise OSError("injected directory sync failure")
        real_sync(fd)

    monkeypatch.setattr(host.os, "fsync", sync)
    with pytest.raises(OSError, match="directory sync failure"):
        host.write_private(target, "new", overwrite=True)
    assert target.read_text() == "new" and list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("operation", ["journal", "environment"])
def test_journal_and_environment_use_the_same_durable_publication(
    tmp_path, monkeypatch, operation
):
    from scripts.trading_kernel.manual_upgrade_journal import UpgradeJournal

    journal = UpgradeJournal(
        tmp_path,
        {"commit": "b" * 40, "schema_revision": "target"},
        {"commit": "a" * 40, "schema": "source"},
    )
    environment = tmp_path / "trading-kernel.env"
    environment.write_text(
        'TRADING_KERNEL_RUNTIME_COMMIT="'
        + "a" * 40
        + '"\nTRADING_KERNEL_SCHEMA_REVISION="source"\n'
    )
    events = []
    real_sync = host.os.fsync
    real_replace = host.os.replace

    def sync(fd):
        events.append(
            "file" if stat.S_ISREG(host.os.fstat(fd).st_mode) else "directory"
        )
        real_sync(fd)

    def replace(src, dst):
        assert events[-1] == "file"
        events.append("replace")
        real_replace(src, dst)

    monkeypatch.setattr(host.os, "fsync", sync)
    monkeypatch.setattr(host.os, "replace", replace)
    if operation == "journal":
        journal.freeze_baseline({"original": ["retained"]})
    else:
        journal.update_environment(environment)
    assert len(events) >= 3 and len(events) % 3 == 0
    assert events == ["file", "replace", "directory"] * (len(events) // 3)


def test_equal_existing_value_retry_syncs_instead_of_silently_acknowledging(
    tmp_path, monkeypatch
):
    target = tmp_path / "already-published"
    target.write_text("new")
    target.chmod(0o600)
    events = []
    real_sync = host.os.fsync

    def sync(fd):
        events.append(
            "file" if stat.S_ISREG(host.os.fstat(fd).st_mode) else "directory"
        )
        real_sync(fd)

    monkeypatch.setattr(host.os, "fsync", sync)
    host.write_private(target, "new")
    assert events == ["file", "directory"]
