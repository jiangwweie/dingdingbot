"""An interrupted exact upgrade resumes forward with its original baseline."""

from pathlib import Path

import pytest


def candidate(tmp_path):
    root = tmp_path / "etc/brc/manual-install"
    root.mkdir(parents=True)
    source = {
        "commit": "a" * 40,
        "schema": "0023_management_recovery",
        "paused": True,
        "tickets": False,
        "commands": False,
        "positions": False,
        "incidents": False,
    }
    receipt = {"commit": "b" * 40, "schema_revision": "0024_owner_cooperation"}
    for kind in ("kernel", "api", "static"):
        old = tmp_path / f"old-{kind}"
        new = tmp_path / f"new-{kind}"
        old.mkdir()
        new.mkdir()
        for p, commit, schema in [
            (old, "a" * 40, source["schema"]),
            (new, "b" * 40, receipt["schema_revision"]),
        ]:
            (p / ".brc-runtime-commit").write_text(commit)
            (p / ".brc-schema-revision").write_text(schema)
        link = tmp_path / f"current-{kind}"
        link.symlink_to(old)
        receipt[kind + "_release"] = str(new)
    return root, source, receipt


def test_upgrade_journal_freezes_original_source_and_baseline(tmp_path):
    from scripts.trading_kernel.manual_upgrade_journal import UpgradeJournal

    root, source, receipt = candidate(tmp_path)
    journal = UpgradeJournal(root, receipt, source)
    baseline = {
        "policy": [{"new_entry_submit_enabled": False}],
        "preserved_columns": {"table": ["id"]},
    }
    journal.freeze_baseline(baseline)
    journal.complete_step("migration")
    restored = UpgradeJournal(root, receipt, source)
    assert restored.baseline == baseline and restored.done("migration")
    with pytest.raises(ValueError, match="baseline"):
        restored.freeze_baseline({"changed": True})
    with pytest.raises(ValueError, match="candidate"):
        UpgradeJournal(root, {**receipt, "commit": "c" * 40}, source)


def test_surface_switch_is_idempotent_after_replace_before_stage_record(tmp_path):
    from scripts.trading_kernel.manual_upgrade_journal import UpgradeJournal

    root, source, receipt = candidate(tmp_path)
    journal = UpgradeJournal(root, receipt, source)
    links = {kind: tmp_path / f"current-{kind}" for kind in ("kernel", "api", "static")}
    journal.freeze_surfaces(links)
    journal.switch_surface("kernel", links["kernel"])
    restored = UpgradeJournal(root, receipt, source)
    restored.switch_surface("kernel", links["kernel"])
    assert links["kernel"].resolve() == Path(receipt["kernel_release"])
    assert links["api"].resolve() != Path(receipt["api_release"])


@pytest.mark.parametrize("fault", [None, "commit", "schema", "paused", "positions"])
def test_official_resume_preflight_checks_actual_database_binding(
    tmp_path, monkeypatch, fault
):
    import json
    from types import SimpleNamespace

    from scripts.trading_kernel import manual_host_bootstrap as host
    from scripts.trading_kernel.manual_upgrade_journal import UpgradeJournal

    root, source, receipt = candidate(tmp_path)
    etc = tmp_path / "etc/brc"
    (etc / "trading-kernel.write-fenced").touch()
    (etc / "trading-kernel.env").touch()
    link = tmp_path / "opt/brc/current"
    link.parent.mkdir(parents=True)
    link.symlink_to((tmp_path / "current-kernel").resolve())
    journal = UpgradeJournal(root, receipt, source)
    journal.freeze_baseline({"policy": [{"new_entry_submit_enabled": False}]})
    journal.freeze_surfaces(
        {kind: tmp_path / f"current-{kind}" for kind in ("kernel", "api", "static")}
    )
    observed = {**source, "schema": receipt["schema_revision"]}
    if fault == "commit":
        observed["commit"] = "c" * 40
    if fault == "schema":
        observed["schema"] = "wrong"
    if fault == "paused":
        observed["paused"] = False
    if fault == "positions":
        observed["positions"] = True
    monkeypatch.setattr(host, "read_database", lambda _: json.dumps(observed))
    monkeypatch.setattr(
        host.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=3)
    )
    if fault:
        with pytest.raises(ValueError):
            host.require_stopped_upgrade(
                filesystem_root=tmp_path, resume_binding=journal.resume_binding()
            )
    else:
        assert (
            host.require_stopped_upgrade(
                filesystem_root=tmp_path, resume_binding=journal.resume_binding()
            )
            == observed
        )


def test_stale_journal_does_not_block_next_completed_release(tmp_path):
    from scripts.trading_kernel.manual_upgrade_journal import UpgradeJournal

    root, source, receipt = candidate(tmp_path)
    old = UpgradeJournal(root, receipt, source)
    old.freeze_baseline({"original": True})
    old.complete_step("complete")
    next_source = {
        **source,
        "commit": receipt["commit"],
        "schema": receipt["schema_revision"],
    }
    new = UpgradeJournal(root, {**receipt, "commit": "c" * 40}, next_source)
    assert (
        new.baseline is None
        and (root / "upgrade-history" / receipt["commit"]).is_file()
    )


@pytest.mark.parametrize(
    "unit",
    [
        "brc-trading-kernel-entry-worker.service",
        "brc-trading-kernel-lifecycle-worker.service",
    ],
)
def test_resume_never_accepts_unapproved_active_writers(tmp_path, monkeypatch, unit):
    import json
    from types import SimpleNamespace

    from scripts.trading_kernel import manual_host_bootstrap as host
    from scripts.trading_kernel.manual_upgrade_journal import UpgradeJournal

    root, source, receipt = candidate(tmp_path)
    etc = tmp_path / "etc/brc"
    (etc / "trading-kernel.write-fenced").touch()
    (etc / "trading-kernel.env").touch()
    link = tmp_path / "opt/brc/current"
    link.parent.mkdir(parents=True)
    link.symlink_to((tmp_path / "current-kernel").resolve())
    journal = UpgradeJournal(root, receipt, source)
    journal.freeze_baseline({"original": True})
    journal.freeze_surfaces(
        {kind: tmp_path / f"current-{kind}" for kind in ("kernel", "api", "static")}
    )
    monkeypatch.setattr(
        host,
        "read_database",
        lambda _: json.dumps(
            {
                **source,
                "commit": receipt["commit"],
                "schema": receipt["schema_revision"],
            }
        ),
    )
    monkeypatch.setattr(
        host.subprocess,
        "run",
        lambda argv, **k: SimpleNamespace(returncode=0 if argv[-1] == unit else 3),
    )
    with pytest.raises(ValueError, match="active writer"):
        host.require_stopped_upgrade(
            filesystem_root=tmp_path, resume_binding=journal.resume_binding()
        )


def test_resume_stops_only_previously_started_exact_candidate_services(
    tmp_path, monkeypatch
):
    import json
    from types import SimpleNamespace

    from scripts.trading_kernel import manual_host_bootstrap as host
    from scripts.trading_kernel.manual_upgrade_journal import UpgradeJournal

    root, source, receipt = candidate(tmp_path)
    etc = tmp_path / "etc/brc"
    (etc / "trading-kernel.write-fenced").touch()
    (etc / "trading-kernel.env").touch()
    journal = UpgradeJournal(root, receipt, source)
    journal.freeze_baseline({"original": True})
    links = {kind: tmp_path / f"current-{kind}" for kind in ("kernel", "api", "static")}
    journal.freeze_surfaces(links)
    for kind, relative in [
        ("kernel", "opt/brc/current"),
        ("api", "opt/brc/owner-console-api/current"),
        ("static", "opt/brc/owner-console/current"),
    ]:
        journal.switch_surface(kind, links[kind])
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(links[kind].resolve())
    journal.complete_step("starting_services")
    observed = {
        **source,
        "commit": receipt["commit"],
        "schema": receipt["schema_revision"],
    }
    monkeypatch.setattr(host, "read_database", lambda _: json.dumps(observed))
    active = [True]
    monkeypatch.setattr(
        host.subprocess,
        "run",
        lambda argv, **k: SimpleNamespace(
            returncode=0
            if active[0] and argv[-1] == "brc-owner-console-api.service"
            else 3
        ),
    )
    calls = []

    def stop(argv):
        calls.append(argv)
        active[0] = False

    monkeypatch.setattr(host, "run", stop)
    assert (
        host.require_stopped_upgrade(
            filesystem_root=tmp_path, resume_binding=journal.resume_binding()
        )
        == observed
    )
    assert calls == [["systemctl", "stop", "brc-owner-console-api.service"]]
