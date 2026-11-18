#!/usr/bin/env python3
"""Joint release maintenance prelude; never migrate a live/nonterminal source or enable ENTRY."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.owner_console.certify_release_candidate import (
    validate_owner_api_release_certification,
)
from scripts.owner_console.certify_static_release_candidate import (
    validate_owner_static_release_certification,
)
from scripts.trading_kernel.certify_release_candidate import (
    ReleaseCertificationLevel,
    load_release_certification_manifest,
)
from scripts.trading_kernel.install_manual_host import (
    ManualHostTarget,
    SshManualInstallationBackend,
)
from scripts.trading_kernel.manual_host_bootstrap import check_host_identity


def require_commits(prelude: Path, prelude_commit: str, source_commit: str) -> str:
    for c in [prelude_commit, source_commit]:
        if re.fullmatch(r"[0-9a-f]{40}", c) is None:
            raise ValueError("joint_commit_invalid")
    target = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    load_release_certification_manifest(ROOT, target, ReleaseCertificationLevel.R4)
    validate_owner_api_release_certification(ROOT, target)
    validate_owner_static_release_certification(ROOT, target)
    observed = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=prelude, text=True
    ).strip()
    if (
        observed != prelude_commit
        or subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=prelude, text=True
        ).strip()
    ):
        raise ValueError("recovery_source_not_exact_clean")
    # Validate using the source-schema checkout's own version/Registry/command set.
    subprocess.run(
        [
            str(prelude / ".venv/bin/python"),
            "-c",
            "import sys;from pathlib import Path;from scripts.trading_kernel.certify_release_candidate import load_release_certification_manifest,ReleaseCertificationLevel;load_release_certification_manifest(Path.cwd(),sys.argv[1],ReleaseCertificationLevel.R4)",
            prelude_commit,
        ],
        cwd=prelude,
        check=True,
        capture_output=True,
        timeout=30,
    )
    return target


def remote(
    target: ManualHostTarget, argv: list[str], data: bytes | None = None
) -> dict:
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=10",
            target.ssh_target,
            "--",
            shlex.join(argv),
        ],
        input=data,
        capture_output=True,
        check=False,
        timeout=1000,
    )
    if result.returncode:
        raise RuntimeError("joint_recovery_remote_blocked_sensitive_output_withheld")
    return json.loads(result.stdout)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prelude-worktree", type=Path, required=True)
    p.add_argument("--prelude-commit", required=True)
    p.add_argument("--source-commit", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--machine-id", required=True)
    p.add_argument("--public-ip", required=True)
    p.add_argument(
        "--phase",
        choices=["stage-recovery", "recovery-preview", "recovery-apply"],
        required=True,
    )
    p.add_argument("--ticket-id", action="append", default=[])
    p.add_argument("--expected-digest")
    a = p.parse_args()
    target = ManualHostTarget(
        ssh_target=a.target, machine_id=a.machine_id, public_ip=a.public_ip
    )
    commit = require_commits(a.prelude_worktree, a.prelude_commit, a.source_commit)
    backend = SshManualInstallationBackend(target, commit)
    check_host_identity(backend.inspect(), target.model_dump())
    location = "/opt/brc/maintenance/" + a.prelude_commit
    if a.phase == "stage-recovery":
        with tempfile.TemporaryDirectory(prefix="brc-joint-recovery-") as d:
            capsule = Path(d) / "capsule.tar.gz"
            subprocess.run(
                [
                    str(a.prelude_worktree / ".venv/bin/python"),
                    "-c",
                    "import sys;from pathlib import Path;from scripts.trading_kernel.stage_manual_recovery_capsule import build_capsule;Path(sys.argv[2]).write_bytes(build_capsule(Path.cwd(),sys.argv[1]))",
                    a.prelude_commit,
                    str(capsule),
                ],
                cwd=a.prelude_worktree,
                check=True,
                capture_output=True,
                timeout=60,
            )
            # Stage inert source-schema files; runtime links and services stay unchanged.
            helper = subprocess.check_output(
                [
                    "git",
                    "archive",
                    "--format=tar.gz",
                    a.prelude_commit,
                    "src",
                    "scripts",
                    "migrations",
                    "deploy",
                    "requirements.txt",
                ],
                cwd=a.prelude_worktree,
            )
            stage_program = """import io,json,pathlib,subprocess,sys,tarfile,tempfile
import os
if os.geteuid()!=0 or pathlib.Path('/etc/machine-id').read_text().strip()!=sys.argv[2] or pathlib.Path('/etc/brc/product-id').read_text().strip()!='brc-app-manual-v1':raise ValueError('helper_host_identity')
if not pathlib.Path('/etc/brc/trading-kernel.write-fenced').is_file():raise ValueError('helper_maintenance_fence')
if pathlib.Path('/opt/brc/current/.brc-runtime-commit').read_text().strip()!=sys.argv[3]:raise ValueError('helper_source_identity')
r=pathlib.Path('/opt/brc/maintenance/bootstrap-'+sys.argv[1])
if r.is_symlink():raise ValueError('helper_root_symlink')
r.mkdir(parents=True,exist_ok=True)
data=sys.stdin.buffer.read(80*1024*1024+1)
with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
 members=archive.getmembers()
 if len(members)>20000 or sum(m.size for m in members)>300*1024*1024:raise ValueError('helper_bound')
 for m in members:
  q=pathlib.PurePosixPath(m.name)
  if q.is_absolute() or '..' in q.parts or not(m.isfile() or m.isdir()):raise ValueError('helper_archive_type')
 for m in members:
  path=r.joinpath(*pathlib.PurePosixPath(m.name).parts)
  for part in [path,*path.parents]:
   if part==r.parent:break
   if part.is_symlink():raise ValueError('helper_existing_symlink')
  if m.isdir():path.mkdir(parents=True,exist_ok=True)
  else:
   path.parent.mkdir(parents=True,exist_ok=True)
   path.write_bytes(archive.extractfile(m).read())
print(json.dumps({'status':'helper_staged'}))
"""
            remote(
                target,
                [
                    "sudo",
                    "-n",
                    "python3",
                    "-c",
                    stage_program,
                    a.prelude_commit,
                    a.machine_id,
                    a.source_commit,
                ],
                helper,
            )
            helper_root = "/opt/brc/maintenance/bootstrap-" + a.prelude_commit
            # Use the installed runtime interpreter to load Pydantic/SQLAlchemy,
            # but never reuse its code or schema authority.
            result = remote(
                target,
                [
                    "sudo",
                    "-n",
                    "/opt/brc/current/.venv/bin/python",
                    helper_root
                    + "/scripts/trading_kernel/stage_manual_recovery_capsule.py",
                    "--commit",
                    a.prelude_commit,
                    "--machine-id",
                    a.machine_id,
                ],
                capsule.read_bytes(),
            )
    else:
        if not 1 <= len(a.ticket_id) <= 16 or len(set(a.ticket_id)) != len(a.ticket_id):
            raise ValueError("joint_recovery_ticket_bound")
        argv = [
            "sudo",
            "-n",
            location + "/.venv/bin/python",
            location + "/scripts/trading_kernel/recover_manual_trade_batch.py",
            "--tool-commit",
            a.prelude_commit,
            "--source-commit",
            a.source_commit,
            "--machine-id",
            a.machine_id,
        ]
        for tid in a.ticket_id:
            if re.fullmatch(r"[A-Za-z0-9:_-]{1,160}", tid) is None:
                raise ValueError("joint_ticket_invalid")
            argv += ["--ticket-id", tid]
        if a.phase == "recovery-apply":
            if (
                a.expected_digest is None
                or re.fullmatch(r"sha256:[0-9a-f]{64}", a.expected_digest) is None
            ):
                raise ValueError("joint_preview_digest_required")
            argv += ["--apply", "--expected-digest", a.expected_digest]
        result = remote(target, argv)
    print(
        json.dumps(
            {"target_commit": commit, "recovery_commit": a.prelude_commit, **result}
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - never reveal credentials from child output.
        print(json.dumps({"status": "blocked", "error_type": type(exc).__name__}))
        raise SystemExit(1) from None
