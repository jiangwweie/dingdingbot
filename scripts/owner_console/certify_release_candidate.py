#!/usr/bin/env python3
"""Run one focused certification for an exact Owner API release commit."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)

SCHEMA = "brc.owner_console.release_certification.v1"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
OWNER_API_CERTIFICATION_COMMANDS: tuple[tuple[str, ...], ...] = (
    (
        ".venv/bin/python",
        "-m",
        "pytest",
        "tests/trading_kernel/unit/owner_console",
        "tests/trading_kernel/interfaces/test_owner_console_http.py",
        "tests/trading_kernel/architecture/test_owner_console_deployment.py",
        "-q",
    ),
    (
        ".venv/bin/ruff",
        "check",
        "scripts/owner_console",
        "src/trading_kernel/application/owner_console",
        "src/trading_kernel/interfaces/owner_console_http",
        "src/trading_kernel/infrastructure/owner_market_data.py",
        "src/trading_kernel/infrastructure/pg_owner_control.py",
        "src/trading_kernel/infrastructure/pg_owner_read_repository.py",
        "tests/trading_kernel/unit/owner_console",
        "tests/trading_kernel/interfaces/test_owner_console_http.py",
        "tests/trading_kernel/architecture/test_owner_console_deployment.py",
    ),
    ("git", "diff", "--check"),
)


class OwnerApiReleaseCertificationManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    manifest_schema: Literal["brc.owner_console.release_certification.v1"] = Field(
        alias="schema",
        serialization_alias="schema",
    )
    status: Literal["pass"]
    release_commit: str
    schema_revision: str
    command_set_digest: str
    certified_at_ms: int
    command_durations_ms: tuple[int, ...]

    @model_validator(mode="after")
    def _validate_manifest(self) -> OwnerApiReleaseCertificationManifest:
        if _COMMIT.fullmatch(self.release_commit) is None:
            raise ValueError("Owner API release commit must be exact")
        if self.certified_at_ms <= 0:
            raise ValueError("Owner API certification time must be positive")
        if len(self.command_durations_ms) != len(OWNER_API_CERTIFICATION_COMMANDS):
            raise ValueError("Owner API certification duration count differs")
        if any(duration < 0 for duration in self.command_durations_ms):
            raise ValueError("Owner API certification durations cannot be negative")
        return self


def build_owner_api_certification_identity(commit: str) -> dict[str, object]:
    if _COMMIT.fullmatch(commit) is None:
        raise ValueError("Owner API release commit must be exact")
    return {
        "schema": SCHEMA,
        "release_commit": commit,
        "schema_revision": CURRENT_SCHEMA_REVISION,
        "command_set_digest": _digest(OWNER_API_CERTIFICATION_COMMANDS),
    }


def validate_owner_api_manifest_identity(
    manifest: OwnerApiReleaseCertificationManifest,
    commit: str,
) -> None:
    expected = build_owner_api_certification_identity(commit)
    actual = manifest.model_dump(mode="python", by_alias=True)
    for key, value in expected.items():
        if actual.get(key) != value:
            label = "release commit" if key == "release_commit" else key.replace("_", " ")
            raise ValueError(f"Owner API certification {label} differs")


def owner_api_certification_manifest_path(repo_root: Path, commit: str) -> Path:
    relative = _git(
        repo_root,
        "rev-parse",
        "--git-path",
        f"brc-owner-api-certifications/{commit}.json",
    )
    path = Path(relative)
    return path if path.is_absolute() else repo_root / path


def validate_owner_api_release_certification(repo_root: Path, commit: str) -> None:
    path = owner_api_certification_manifest_path(repo_root, commit)
    if not path.is_file():
        raise ValueError("exact Owner API Release Commit lacks certification")
    manifest = OwnerApiReleaseCertificationManifest.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    validate_owner_api_manifest_identity(manifest, commit)


def certify_owner_api_release_candidate(
    repo_root: Path,
    commit: str,
) -> OwnerApiReleaseCertificationManifest:
    _require_exact_clean_head(repo_root, commit)
    durations: list[int] = []
    for index, command in enumerate(OWNER_API_CERTIFICATION_COMMANDS, start=1):
        print(
            f"owner_api_certification_step={index}/{len(OWNER_API_CERTIFICATION_COMMANDS)} "
            f"command={json.dumps(command)}",
            flush=True,
        )
        started = time.monotonic()
        completed = subprocess.run(
            command,
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        durations.append(max(0, int((time.monotonic() - started) * 1_000)))
        if completed.returncode != 0:
            output = (completed.stdout + "\n" + completed.stderr)[-8_000:]
            raise RuntimeError(
                f"Owner API certification command {index} failed:\n{output}"
            )
    _require_exact_clean_head(repo_root, commit)
    manifest = OwnerApiReleaseCertificationManifest.model_validate(
        {
            **build_owner_api_certification_identity(commit),
            "status": "pass",
            "certified_at_ms": int(time.time() * 1_000),
            "command_durations_ms": tuple(durations),
        }
    )
    path = owner_api_certification_manifest_path(repo_root, commit)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        manifest.model_dump_json(indent=2, by_alias=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _require_exact_clean_head(repo_root: Path, commit: str) -> None:
    if _git(repo_root, "rev-parse", "HEAD") != commit:
        raise ValueError("Owner API certification commit must equal current HEAD")
    if _git(repo_root, "status", "--porcelain"):
        raise ValueError("Owner API certification requires a clean worktree")


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args),
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default="HEAD")
    return parser


def _resolve_commit(reference: str) -> str:
    commit = _git(REPO_ROOT, "rev-parse", "--verify", f"{reference}^{{commit}}")
    if _COMMIT.fullmatch(commit) is None:
        raise ValueError("resolved Owner API release commit is invalid")
    return commit


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    commit = _resolve_commit(args.commit)
    manifest = certify_owner_api_release_candidate(REPO_ROOT, commit)
    print(manifest.model_dump_json(by_alias=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
