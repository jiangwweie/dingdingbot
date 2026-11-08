#!/usr/bin/env python3
"""Exact-candidate, explicit-target inactive installation for the manual product."""

from __future__ import annotations

import argparse
import hashlib
import io
import ipaddress
import json
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, field_validator

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.owner_console.certify_release_candidate import (
    owner_api_certification_manifest_path,
    validate_owner_api_release_certification,
)
from scripts.owner_console.certify_static_release_candidate import (
    owner_static_certification_manifest_path,
    validate_owner_static_release_certification,
)
from scripts.trading_kernel.certify_release_candidate import (
    ReleaseCertificationLevel,
    load_release_certification_manifest,
)
from scripts.trading_kernel.manual_host_bootstrap import check_host_identity


class ManualHostTarget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    product_id: Literal["brc-app-manual-v1"] = "brc-app-manual-v1"
    ssh_target: str
    public_ip: str
    machine_id: str

    @field_validator("ssh_target")
    @classmethod
    def token(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._@-]{0,127}", value) or value.split(
            "@"
        )[-1] in ("tokyo", "tokyo-server", "43.133.176.150"):
            raise ValueError("explicit independent manual SSH target required")
        return value

    @field_validator("public_ip")
    @classmethod
    def address(cls, value):
        if not ipaddress.ip_address(value).is_global or value == "43.133.176.150":
            raise ValueError("independent public IP required")
        return value

    @field_validator("machine_id")
    @classmethod
    def machine(cls, value):
        if not re.fullmatch(r"[0-9a-f]{32}", value):
            raise ValueError("exact machine identity required")
        return value


class InstallationBackend(Protocol):
    def inspect(self) -> dict: ...
    def apply(self, phase: str) -> dict: ...
    def upload(self, artifacts: bytes) -> dict: ...


def install_manual_host(
    backend: InstallationBackend,
    *,
    target: ManualHostTarget,
    phase: str,
    artifacts: bytes | None,
) -> dict:
    if phase not in ("inspect", "stage", "database"):
        raise ValueError("inactive installation phase required")
    facts = backend.inspect()
    check_host_identity(facts, target.model_dump())
    if phase == "inspect":
        return facts
    if facts.get("runtime_present") or not facts.get("entry_fenced", False):
        raise ValueError("fresh inactive host required")
    if phase == "stage":
        if artifacts is None:
            raise ValueError("exact certified artifacts required")
        return backend.upload(artifacts)
    return backend.apply("database")


class SshManualInstallationBackend:
    def __init__(
        self, target: ManualHostTarget, commit: str, repo_root: Path = REPO_ROOT
    ):
        self.target = target
        self.commit = commit
        self.repo_root = repo_root

    def _call(self, phase: str, data: bytes | None = None) -> dict:
        source = subprocess.check_output(
            (
                "git",
                "show",
                self.commit + ":scripts/trading_kernel/manual_host_bootstrap.py",
            ),
            cwd=self.repo_root,
            text=True,
        )
        args = [
            "sudo",
            "-n",
            "python3",
            "-c",
            source,
            "--machine-id",
            self.target.machine_id,
            "--public-ip",
            self.target.public_ip,
            "--phase",
            phase,
            "--commit",
            self.commit,
        ]
        if phase == "receive":
            args += ["--digest", hashlib.sha256(data or b"").hexdigest()]
        cmd = (
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=10",
            self.target.ssh_target,
            "--",
            shlex.join(args),
        )
        result = subprocess.run(
            cmd, input=data, capture_output=True, timeout=1000, check=False
        )
        if result.returncode:
            raise RuntimeError(
                "manual "
                + phase
                + " failed; remote output withheld to protect credentials"
            )
        return json.loads(result.stdout)

    def inspect(self):
        return self._call("inspect")

    def apply(self, phase):
        return self._call(phase)

    def upload(self, artifacts):
        return self._call("receive", artifacts)


def build_artifacts(repo_root: Path, commit: str) -> bytes:
    kernel = load_release_certification_manifest(
        repo_root, commit, ReleaseCertificationLevel.R4
    )
    validate_owner_api_release_certification(repo_root, commit)
    validate_owner_static_release_certification(repo_root, commit)
    metadata = {
        "kernel": kernel.model_dump(mode="json", by_alias=True),
        "api": json.loads(
            owner_api_certification_manifest_path(repo_root, commit).read_text()
        ),
        "static": json.loads(
            owner_static_certification_manifest_path(repo_root, commit).read_text()
        ),
    }
    release = subprocess.check_output(
        (
            "git",
            "archive",
            "--format=tar.gz",
            commit,
            "src",
            "scripts",
            "migrations",
            "deploy",
            "requirements.txt",
            "requirements-owner-console.txt",
        ),
        cwd=repo_root,
    )
    # Build only the exact committed frontend, never trust a mutable ignored dist.
    with tempfile.TemporaryDirectory(prefix="brc-manual-static-") as directory:
        dest = Path(directory)
        raw = subprocess.check_output(
            ("git", "archive", "--format=tar", commit, "frontend/owner-console-v2"),
            cwd=repo_root,
        )
        from scripts.trading_kernel.manual_host_bootstrap import extract_plain_archive

        extract_plain_archive(io.BytesIO(raw), dest)
        frontend = dest / "frontend/owner-console-v2"
        for args in (("pnpm", "install", "--frozen-lockfile"), ("pnpm", "build")):
            subprocess.run(
                args, cwd=frontend, check=True, capture_output=True, timeout=300
            )
        static_buffer = io.BytesIO()
        with tarfile.open(fileobj=static_buffer, mode="w:gz") as archive:
            archive.add(frontend / "dist", arcname="dist")
        files = {
            "release.tar.gz": release,
            "static.tar.gz": static_buffer.getvalue(),
            "certifications.json": json.dumps(metadata, sort_keys=True).encode(),
        }
    envelope = io.BytesIO()
    with tarfile.open(fileobj=envelope, mode="w:gz") as archive:
        for name, value in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(value)
            info.mode = 0o600
            archive.addfile(info, io.BytesIO(value))
    return envelope.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--public-ip", required=True)
    parser.add_argument("--machine-id", required=True)
    parser.add_argument(
        "--phase", choices=("inspect", "stage", "database"), required=True
    )
    args = parser.parse_args(argv)
    target = ManualHostTarget(
        ssh_target=args.target, public_ip=args.public_ip, machine_id=args.machine_id
    )
    commit = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=REPO_ROOT, text=True
    ).strip()
    # All mutating phases bind the same exact R4/API/Static certified source.
    if args.phase != "inspect":
        load_release_certification_manifest(
            REPO_ROOT, commit, ReleaseCertificationLevel.R4
        )
        validate_owner_api_release_certification(REPO_ROOT, commit)
        validate_owner_static_release_certification(REPO_ROOT, commit)
    backend = SshManualInstallationBackend(target, commit)
    check_host_identity(backend.inspect(), target.model_dump())
    artifacts = build_artifacts(REPO_ROOT, commit) if args.phase == "stage" else None
    result = install_manual_host(
        backend, target=target, phase=args.phase, artifacts=artifacts
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
