"""Live static deployment must preserve runtime authority and old cached assets."""

import io
import tarfile
from unittest.mock import Mock

import pytest

from scripts.owner_console.deploy_manual_static import activate_static, static_bundle


def dist(tmp_path):
    d = tmp_path / "build"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text(
        '<script type="module" src="/trading/assets/new.js"></script>'
    )
    (d / "assets/new.js").write_text('export const build="new";')
    return d


def test_static_release_switches_only_static_pointer_and_retains_cached_assets(
    tmp_path,
):
    root = tmp_path / "releases"
    old = root / ("a" * 40)
    (old / "dist/assets").mkdir(parents=True)
    (old / "dist/index.html").write_text("old")
    (old / "dist/assets/old.js").write_text("old chunk")
    current = tmp_path / "current"
    current.symlink_to(old, target_is_directory=True)
    bundle, manifest = static_bundle(dist(tmp_path))
    snapshot = Mock(
        return_value={
            "kernel": "same",
            "api": "same",
            "policy": 8,
            "processes": {"entry": 123},
        }
    )
    result = activate_static(
        bundle,
        commit="b" * 40,
        manifest=manifest,
        release_root=root,
        current=current,
        snapshot=snapshot,
        smoke=Mock(),
    )
    assert current.resolve() == root / ("b" * 40)
    assert (current / "dist/assets/old.js").read_text() == "old chunk"
    assert result["runtime_unchanged"] and snapshot.call_count >= 2
    assert (old / "dist/index.html").read_text() == "old"


def test_failed_public_smoke_rolls_back_static_pointer_only(tmp_path):
    root = tmp_path / "releases"
    old = root / ("a" * 40)
    (old / "dist").mkdir(parents=True)
    (old / "dist/index.html").write_text("old")
    current = tmp_path / "current"
    current.symlink_to(old, target_is_directory=True)
    bundle, manifest = static_bundle(dist(tmp_path))
    with pytest.raises(RuntimeError, match="smoke"):
        activate_static(
            bundle,
            commit="b" * 40,
            manifest=manifest,
            release_root=root,
            current=current,
            snapshot=lambda: {"kernel": "same"},
            smoke=Mock(side_effect=RuntimeError("smoke failed")),
        )
    assert current.resolve() == old


def test_changed_runtime_authority_refuses_switch(tmp_path):
    root = tmp_path / "releases"
    old = root / ("a" * 40)
    (old / "dist").mkdir(parents=True)
    current = tmp_path / "current"
    current.symlink_to(old, target_is_directory=True)
    bundle, manifest = static_bundle(dist(tmp_path))
    with pytest.raises(ValueError, match="runtime"):
        activate_static(
            bundle,
            commit="b" * 40,
            manifest=manifest,
            release_root=root,
            current=current,
            snapshot=Mock(side_effect=[{"policy": 8}, {"policy": 9}]),
            smoke=Mock(),
        )
    assert current.resolve() == old


@pytest.mark.parametrize(
    "name",
    ["../escape", "dist/../escape", "/etc/unsafe", "src/trading_kernel/unsafe.py"],
)
def test_unsafe_or_nonstatic_archive_is_rejected_before_switch(tmp_path, name):
    root = tmp_path / "releases"
    old = root / ("a" * 40)
    old.mkdir(parents=True)
    current = tmp_path / "current"
    current.symlink_to(old, target_is_directory=True)
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as t:
        member = tarfile.TarInfo(name)
        member.size = 1
        t.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(ValueError):
        activate_static(
            archive.getvalue(),
            commit="b" * 40,
            manifest={"index.html": "bad"},
            release_root=root,
            current=current,
            snapshot=dict,
            smoke=Mock(),
        )
    assert current.resolve() == old


def test_wrong_host_identity_prevents_static_activation(monkeypatch):
    import scripts.owner_console.deploy_manual_static as release
    import scripts.trading_kernel.manual_host_bootstrap as host

    monkeypatch.setattr(release.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        host,
        "host_facts",
        lambda: {
            "machine_id": "wrong",
            "product_id": "brc-app-manual-v1",
            "public_ip": "43.133.243.174",
        },
    )
    activate = Mock()
    monkeypatch.setattr(release, "activate_static", activate)
    with pytest.raises(ValueError, match="identity"):
        release.receive(
            {
                "target": {
                    "machine_id": "f956f502ced4461e9d0fcc0ef637abd6",
                    "public_ip": "43.133.243.174",
                }
            }
        )
    activate.assert_not_called()


def test_mobile_shell_is_in_same_exact_static_artifact(tmp_path):
    d=dist(tmp_path)
    (d/'mobile').mkdir()
    for name in ('index.html','app.js','styles.css','sw.js','manifest.webmanifest','icon.svg'):
        (d/'mobile'/name).write_text(name)
    bundle,manifest=static_bundle(d)
    assert len(bundle)>0 and 'mobile/app.js' in manifest
    assert 'mobile/sw.js' in manifest and 'index.html' in manifest


@pytest.mark.parametrize('path',['mobile/.env','mobile/../unsafe.py','mobile/secrets.json','mobile/asset.py'])
def test_mobile_bundle_rejects_files_outside_shell_allowlist(tmp_path,path):
    d=dist(tmp_path)
    target=d/path
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text('should not be published')
    with pytest.raises(ValueError):static_bundle(d)


@pytest.mark.parametrize('fault', [None, 'api_schema', 'kernel_schema', 'db_schema', 'alembic', 'empty_capability'])
def test_static_preflight_binds_installed_kernel_api_database_and_capabilities(monkeypatch, fault):
    import json
    from pathlib import Path
    from types import SimpleNamespace

    import scripts.owner_console.deploy_manual_static as release
    from src.trading_kernel.infrastructure.runtime_identity import (
        CURRENT_SCHEMA_REVISION,
    )

    commit = 'a' * 40
    schemas = {'kernel': CURRENT_SCHEMA_REVISION, 'api': CURRENT_SCHEMA_REVISION}
    if fault in {'api_schema', 'kernel_schema'}:
        schemas[fault.split('_')[0]] = '0019_management_evidence_v2'
    original_read = Path.read_text

    def read(path, *args, **kwargs):
        if str(path).startswith('/opt/brc/'):
            if path.name == '.brc-runtime-commit':
                return commit
            if path.name == '.brc-schema-revision':
                return schemas['api' if 'owner-console-api' in str(path) else 'kernel']
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', read)
    original_exists = Path.exists
    monkeypatch.setattr(Path, 'exists', lambda path: False if str(path).startswith('/etc/brc/') else original_exists(path))
    schema = '0019_management_evidence_v2' if fault == 'db_schema' else CURRENT_SCHEMA_REVISION
    facts = {'system': '7705780580898177062', 'account': 'binance-manual-1290716840',
        'alembic_revision': '0019_management_evidence_v2' if fault == 'alembic' else CURRENT_SCHEMA_REVISION,
        'identity': [{'metadata_key': 'runtime_commit', 'metadata_value': commit},
                     {'metadata_key': 'schema_revision', 'metadata_value': schema}],
        'policy': [{'policy_version': 18, 'new_entry_submit_enabled': True}], 'controls': [],
        'capability': [] if fault == 'empty_capability' else [{'certified_commit': commit,
            'schema_revision': schema, 'certification': {'product_id': 'brc-app-manual-v1'}}]}

    def run(args, **kwargs):
        return SimpleNamespace(stdout='ActiveState=active\nMainPID=10\nNRestarts=0\n' if args[0] == 'systemctl' else json.dumps(facts))

    monkeypatch.setattr(release.subprocess, 'run', run)
    if fault is None:
        assert release._runtime_snapshot(commit)['new_entry_submit_enabled']
    else:
        with pytest.raises(ValueError, match='identity|schema|capability'):
            release._runtime_snapshot(commit)
