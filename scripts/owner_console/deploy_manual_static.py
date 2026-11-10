#!/usr/bin/env python3
"""Seoul-only certified static release; never modifies API or trading services."""

from __future__ import annotations

import argparse
import base64
import fcntl
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from hashlib import sha256
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_BUNDLE_BYTES = 50 * 1024 * 1024
MAX_FILES = 10000
STATIC_ROOT = Path("/opt/brc/owner-console/releases")
STATIC_CURRENT = Path("/opt/brc/owner-console/current")


def _static_path(name):
    p = PurePosixPath(name)
    if (
        p.is_absolute()
        or ".." in p.parts
        or str(p) != name
        or not (name == "index.html" or name.startswith("assets/"))
    ):
        raise ValueError("archive contains nonstatic or unsafe path")
    return p


def static_bundle(dist):
    manifest = {}
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as archive:
        for p in sorted(dist.rglob("*")):
            if p.is_symlink():
                raise ValueError("static build symlink forbidden")
            if not p.is_file():
                continue
            name = p.relative_to(dist).as_posix()
            _static_path(name)
            content = p.read_bytes()
            manifest[name] = sha256(content).hexdigest()
            info = tarfile.TarInfo("dist/" + name)
            info.size = len(content)
            info.mode = 0o640
            archive.addfile(info, io.BytesIO(content))
    if (
        "index.html" not in manifest
        or len(manifest) > MAX_FILES
        or len(data.getvalue()) > MAX_BUNDLE_BYTES
    ):
        raise ValueError("static artifact incomplete or exceeds bound")
    return data.getvalue(), manifest


def _extract(data, manifest, destination):
    if len(data) > MAX_BUNDLE_BYTES:
        raise ValueError("static archive too large")
    seen = set()
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive:
            if not member.isfile() or not member.name.startswith("dist/"):
                raise ValueError("static archive must contain plain dist files")
            name = member.name[5:]
            _static_path(name)
            total += member.size
            if (
                name in seen
                or name not in manifest
                or len(seen) >= MAX_FILES
                or total > MAX_BUNDLE_BYTES
            ):
                raise ValueError("static archive manifest differs or exceeds bound")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("static archive content missing")
            value = source.read(MAX_BUNDLE_BYTES + 1)
            if sha256(value).hexdigest() != manifest[name]:
                raise ValueError("static archive digest differs")
            target = destination / "dist" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
            seen.add(name)
    if seen != set(manifest) or "index.html" not in seen:
        raise ValueError("static archive manifest incomplete")


def _switch(current, target):
    pending = current.with_name(current.name + ".pending-static")
    if os.path.lexists(pending):
        raise ValueError("pending static switch already exists")
    pending.symlink_to(target, target_is_directory=True)
    os.replace(pending, current)


def activate_static(
    data, *, commit, manifest, release_root, current, snapshot, smoke, prepare=None
):
    if not _SHA.fullmatch(commit) or not current.is_symlink():
        raise ValueError("exact existing static identity required")
    previous = current.resolve(strict=True)
    root = release_root.resolve()
    if previous.parent != root:
        raise ValueError("source static release outside independent root")
    before = snapshot()
    target = root / commit
    if target.exists():
        raise ValueError("static target already exists; refusing overwrite")
    staging = Path(tempfile.mkdtemp(prefix=".static-", dir=root))
    switched = False
    try:
        _extract(data, manifest, staging)
        # Old browser tabs may lazy-load a content-hashed asset after the switch.
        old_assets = previous / "dist/assets"
        if old_assets.exists():
            count = 0
            for old in old_assets.rglob("*"):
                if old.is_symlink():
                    raise ValueError("old static asset symlink forbidden")
                if not old.is_file():
                    continue
                count += 1
                if count > MAX_FILES:
                    raise ValueError("retained static assets exceed bound")
                name = old.relative_to(old_assets)
                new = staging / "dist/assets" / name
                if new.exists():
                    if (
                        sha256(new.read_bytes()).digest()
                        != sha256(old.read_bytes()).digest()
                    ):
                        raise ValueError("immutable static asset name collision")
                else:
                    new.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(old, new)
        (staging / ".brc-owner-console-static-commit").write_text(commit + "\n")
        (staging / ".brc-static-manifest.json").write_text(
            json.dumps(manifest, sort_keys=True) + "\n"
        )
        if snapshot() != before:
            raise ValueError("runtime authority changed before static switch")
        if prepare is not None:
            prepare(staging)
        os.replace(staging, target)
        _switch(current, target)
        switched = True
        smoke(target, manifest)
        after = snapshot()
        if after != before:
            raise ValueError("runtime authority changed during static release")
        return {
            "status": "pass",
            "commit": commit,
            "previous_static_release": str(previous),
            "static_release": str(target),
            "runtime_unchanged": True,
            "runtime_before": before,
            "runtime_after": after,
            "service_restarts": 0,
            "new_artifact_files": len(manifest),
            "index_sha256": manifest["index.html"],
        }
    except BaseException:
        if switched:
            _switch(current, previous)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _runtime_snapshot(expected_commit):
    for path in ["/opt/brc/current", "/opt/brc/owner-console-api/current"]:
        if (Path(path) / ".brc-runtime-commit").read_text().strip() != expected_commit:
            raise ValueError("installed kernel/API identity differs")
    if Path("/etc/brc/trading-kernel.write-fenced").exists():
        raise ValueError("unexpected trading maintenance fence")
    units = {}
    for role in ["observation", "entry", "lifecycle", "reconciliation", "api"]:
        unit = (
            "brc-owner-console-api.service"
            if role == "api"
            else "brc-trading-kernel-" + role + "-worker.service"
        )
        p = subprocess.run(
            ["systemctl", "show", unit, "--property=ActiveState,MainPID,NRestarts"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        row = dict(line.split("=", 1) for line in p.stdout.splitlines())
        if row["ActiveState"] != "active" or row["MainPID"] == "0":
            raise ValueError("required runtime service not active")
        units[role] = row
    query = """BEGIN READ ONLY; SET LOCAL statement_timeout='5s'; SELECT json_build_object(
    'system',(SELECT system_identifier::text FROM pg_control_system()),
    'account',(SELECT account_id FROM brc_runtime_profiles WHERE runtime_profile_id='tiny-live-v1'),
    'identity',(SELECT json_agg(to_jsonb(t) ORDER BY metadata_key) FROM brc_schema_metadata t WHERE metadata_key IN ('runtime_commit','schema_revision','seed_identity')),
    'policy',(SELECT json_agg(to_jsonb(t) ORDER BY owner_policy_id) FROM brc_owner_policy_current t),
    'controls',(SELECT json_agg(to_jsonb(t) ORDER BY strategy_group_id) FROM brc_strategy_entry_controls_current t),
    'capability',(SELECT json_agg(to_jsonb(t) ORDER BY capability_key) FROM brc_runtime_capabilities_current t)); COMMIT;"""
    p = subprocess.run(
        [
            "docker",
            "exec",
            "brc-manual-runtime-pg",
            "psql",
            "-XqAt",
            "-U",
            "brc_manual_admin",
            "-d",
            "brc_manual_kernel",
            "-c",
            query,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    facts = json.loads(p.stdout)
    if (
        facts["system"] != "7705780580898177062"
        or facts["account"] != "binance-manual-1290716840"
    ):
        raise ValueError("production database/account binding differs")
    identity = {row["metadata_key"]: row["metadata_value"] for row in facts["identity"]}
    if (
        identity.get("runtime_commit") != expected_commit
        or identity.get("schema_revision") != "0019_management_evidence_v2"
    ):
        raise ValueError("current database runtime identity differs")
    if any(
        row["certified_commit"] != expected_commit
        or row["schema_revision"] != identity["schema_revision"]
        or row["certification"].get("product_id") != "brc-app-manual-v1"
        for row in facts["capability"]
    ):
        raise ValueError("current capability identity differs")
    return {
        "policy_version": facts["policy"][0]["policy_version"],
        "new_entry_submit_enabled": facts["policy"][0]["new_entry_submit_enabled"],
        "kernel": str(Path("/opt/brc/current").resolve()),
        "api": str(Path("/opt/brc/owner-console-api/current").resolve()),
        "processes": units,
        "authority_digest": sha256(
            json.dumps(facts, sort_keys=True).encode()
        ).hexdigest(),
    }


def receive(payload):
    from scripts.trading_kernel.manual_host_bootstrap import (
        check_host_identity,
        host_facts,
    )

    if os.geteuid() != 0:
        raise ValueError("root static installer required")
    check_host_identity(host_facts(), payload["target"])

    def prepare(path):
        import grp

        gid = grp.getgrnam("www-data").gr_gid
        for p in [path, *path.rglob("*")]:
            os.chown(p, 0, gid)
            p.chmod(0o750 if p.is_dir() else 0o640)

    def smoke(target, manifest):
        checks = {**manifest, "": manifest["index.html"]}
        for name, digest in checks.items():
            p = subprocess.run(
                [
                    "curl",
                    "--silent",
                    "--show-error",
                    "--fail",
                    "--max-time",
                    "15",
                    "--resolve",
                    "manual.jiaoyingpan.cloud:443:127.0.0.1",
                    "https://manual.jiaoyingpan.cloud/trading/" + name,
                ],
                check=True,
                capture_output=True,
                timeout=20,
            )
            if sha256(p.stdout).hexdigest() != digest:
                raise ValueError("HTTPS static smoke digest differs")

    with open("/run/brc-manual-install.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = activate_static(
            base64.b64decode(payload["archive"], validate=True),
            commit=payload["commit"],
            manifest=payload["manifest"],
            release_root=STATIC_ROOT,
            current=STATIC_CURRENT,
            snapshot=lambda: _runtime_snapshot(payload["expected_runtime_commit"]),
            smoke=smoke,
            prepare=prepare,
        )
        (
            Path(result["static_release"]) / ".brc-static-release-receipt.json"
        ).write_text(json.dumps(result, sort_keys=True) + "\n")
        return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--commit", required=True)
    p.add_argument("--expected-runtime-commit", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--machine-id", required=True)
    p.add_argument("--public-ip", required=True)
    args = p.parse_args()
    from scripts.owner_console.certify_static_release_candidate import (
        validate_owner_static_release_certification,
    )
    from scripts.owner_console.deploy_release import _build_static_dist
    from scripts.trading_kernel.install_manual_host import ManualHostTarget

    target = ManualHostTarget(
        ssh_target=args.target, machine_id=args.machine_id, public_ip=args.public_ip
    )
    if not _SHA.fullmatch(args.expected_runtime_commit):
        raise ValueError("exact current runtime identity required")
    validate_owner_static_release_certification(REPO_ROOT, args.commit)
    changed = subprocess.check_output(
        [
            "git",
            "diff",
            "--name-only",
            args.expected_runtime_commit,
            args.commit,
            "--",
            "src/trading_kernel",
            "migrations/trading_kernel",
            "frontend/owner-console-v2/src/api",
            "frontend/owner-console-v2/src/types/api.ts",
        ],
        cwd=REPO_ROOT,
        text=True,
    )
    if changed.strip():
        raise ValueError(
            "static release cannot include runtime/schema/API contract changes"
        )
    with _build_static_dist(args.commit) as dist:
        archive, manifest = static_bundle(dist)
        payload = {
            "commit": args.commit,
            "expected_runtime_commit": args.expected_runtime_commit,
            "target": target.model_dump(),
            "manifest": manifest,
            "archive": base64.b64encode(archive).decode(),
        }
    source = subprocess.check_output(
        ["git", "show", args.commit + ":scripts/owner_console/deploy_manual_static.py"],
        cwd=REPO_ROOT,
        text=True,
    )
    program = (
        "import os,sys,json\nos.chdir('/opt/brc/current');sys.path.insert(0,'/opt/brc/current')\n"
        "__name__='manual_static_receiver';__file__='/opt/brc/current/scripts/owner_console/deploy_manual_static.py'\n"
        "exec(compile(" + repr(source) + ",__file__,'exec'))\n"
        "try:\n payload=json.loads(sys.stdin.buffer.read(75000000));print(json.dumps(receive(payload)))\n"
        "except Exception as exc:\n print(json.dumps({'status':'blocked','error_type':type(exc).__name__,'detail':'static switch refused or rolled back; runtime untouched'}));raise SystemExit(1) from None\n"
    )
    compile(program, "<remote-static-controller>", "exec")
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            target.ssh_target,
            shlex.join(
                ["sudo", "-n", "/opt/brc/current/.venv/bin/python", "-c", program]
            ),
        ],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "manual static deployment refused; sensitive output withheld"
        )
    print(result.stdout.strip())


if __name__ == "__main__":
    main()
