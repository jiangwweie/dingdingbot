#!/usr/bin/env python3
"""Certify one exact committed Trading Kernel release candidate once."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.trading_kernel.verification_portfolios import (
    R3_SAME_SCHEMA_KERNEL_COMMANDS,
)
from src.trading_kernel.domain.strategy_registry import (
    build_registry_semantic_hash,
    registered_strategy_contracts,
)
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    DYNAMIC_POLICY,
    OWNER_POLICY_ID,
    POSITION_MODE,
    RUNTIME_PROFILE_ID,
    VENUE_ID,
)
from src.trading_kernel.infrastructure.runtime_identity import (
    CURRENT_SCHEMA_REVISION,
)

SCHEMA = "brc.trading_kernel.release_certification.v1"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
CERTIFICATION_COMMANDS = R3_SAME_SCHEMA_KERNEL_COMMANDS


class ReleaseCertificationManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    manifest_schema: Literal["brc.trading_kernel.release_certification.v1"] = Field(
        alias="schema",
        serialization_alias="schema",
    )
    status: Literal["pass"]
    release_commit: str
    schema_revision: str
    registry_semantic_hash: str
    owner_policy_semantic_digest: str
    runtime_authority_semantic_digest: str
    command_set_digest: str
    certified_at_ms: int
    command_durations_ms: tuple[int, ...]

    @model_validator(mode="after")
    def _validate_manifest(self) -> ReleaseCertificationManifest:
        if _COMMIT.fullmatch(self.release_commit) is None:
            raise ValueError("certified release commit must be exact")
        if self.certified_at_ms <= 0:
            raise ValueError("certification time must be positive")
        if len(self.command_durations_ms) != len(CERTIFICATION_COMMANDS):
            raise ValueError("certification duration count differs from command set")
        if any(duration < 0 for duration in self.command_durations_ms):
            raise ValueError("certification durations cannot be negative")
        return self


def build_certification_identity(commit: str) -> dict[str, str]:
    if _COMMIT.fullmatch(commit) is None:
        raise ValueError("release commit must be an exact lowercase 40-hex SHA")
    registry_hash = build_registry_semantic_hash(registered_strategy_contracts())
    policy_digest = _digest(DYNAMIC_POLICY)
    authority_digest = _digest(
        {
            "schema_revision": CURRENT_SCHEMA_REVISION,
            "registry_semantic_hash": registry_hash,
            "owner_policy_id": OWNER_POLICY_ID,
            "owner_policy_semantic_digest": policy_digest,
            "runtime_profile_id": RUNTIME_PROFILE_ID,
            "venue_id": VENUE_ID,
            "position_mode": POSITION_MODE,
        }
    )
    return {
        "schema": SCHEMA,
        "release_commit": commit,
        "schema_revision": CURRENT_SCHEMA_REVISION,
        "registry_semantic_hash": registry_hash,
        "owner_policy_semantic_digest": policy_digest,
        "runtime_authority_semantic_digest": authority_digest,
        "command_set_digest": _digest(CERTIFICATION_COMMANDS),
    }


def validate_manifest_identity(
    manifest: ReleaseCertificationManifest,
    commit: str,
) -> None:
    expected = build_certification_identity(commit)
    actual = manifest.model_dump(mode="python", by_alias=True)
    for key, value in expected.items():
        if actual.get(key) != value:
            label = (
                "command set" if key == "command_set_digest" else key.replace("_", " ")
            )
            raise ValueError(f"release certification {label} differs")


def certification_manifest_path(repo_root: Path, commit: str) -> Path:
    relative = _git(
        repo_root,
        "rev-parse",
        "--git-path",
        f"brc-release-certifications/{commit}.json",
    )
    path = Path(relative)
    return path if path.is_absolute() else repo_root / path


def validate_release_certification(repo_root: Path, commit: str) -> None:
    _require_exact_clean_head(repo_root, commit)
    path = certification_manifest_path(repo_root, commit)
    if not path.is_file():
        raise ValueError("exact Release Commit lacks local certification manifest")
    manifest = ReleaseCertificationManifest.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    validate_manifest_identity(manifest, commit)


def certify_release_candidate(
    repo_root: Path, commit: str
) -> ReleaseCertificationManifest:
    _require_exact_clean_head(repo_root, commit)
    durations: list[int] = []
    for index, command in enumerate(CERTIFICATION_COMMANDS, start=1):
        print(
            f"certification_step={index}/{len(CERTIFICATION_COMMANDS)} "
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
            print(output, file=sys.stderr)
            raise RuntimeError(f"release certification command {index} failed")
    _require_exact_clean_head(repo_root, commit)
    manifest = ReleaseCertificationManifest.model_validate(
        {
            **build_certification_identity(commit),
            "status": "pass",
            "certified_at_ms": int(time.time() * 1_000),
            "command_durations_ms": tuple(durations),
        }
    )
    path = certification_manifest_path(repo_root, commit)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        manifest.model_dump_json(indent=2, by_alias=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _require_exact_clean_head(repo_root: Path, commit: str) -> None:
    if _git(repo_root, "rev-parse", "HEAD") != commit:
        raise ValueError("certification commit must equal current HEAD")
    status = _git(repo_root, "status", "--porcelain")
    if status:
        raise ValueError("release certification requires a clean worktree")


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
        _jsonable(value),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def _jsonable(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default="HEAD")
    return parser


def _resolve_commit(reference: str) -> str:
    commit = _git(REPO_ROOT, "rev-parse", "--verify", f"{reference}^{{commit}}")
    if _COMMIT.fullmatch(commit) is None:
        raise ValueError("resolved release commit is invalid")
    return commit


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    commit = _resolve_commit(args.commit)
    manifest = certify_release_candidate(REPO_ROOT, commit)
    print(manifest.model_dump_json(by_alias=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
