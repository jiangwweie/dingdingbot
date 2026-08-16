"""Certify one exact R1 Owner Console static release candidate once."""

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

from scripts.trading_kernel.verification_portfolios import R1_STATIC_COMMANDS

SCHEMA = "brc.owner_console.static_release_certification.v1"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
STATIC_CERTIFICATION_COMMANDS = R1_STATIC_COMMANDS


class OwnerStaticReleaseCertificationManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    manifest_schema: Literal[
        "brc.owner_console.static_release_certification.v1"
    ] = Field(alias="schema", serialization_alias="schema")
    status: Literal["pass"]
    release_commit: str
    command_set_digest: str
    certified_at_ms: int
    command_durations_ms: tuple[int, ...]

    @model_validator(mode="after")
    def _validate_manifest(self) -> OwnerStaticReleaseCertificationManifest:
        if _COMMIT.fullmatch(self.release_commit) is None:
            raise ValueError("Owner static release commit must be exact")
        if self.certified_at_ms <= 0:
            raise ValueError("Owner static certification time must be positive")
        if len(self.command_durations_ms) != len(STATIC_CERTIFICATION_COMMANDS):
            raise ValueError("Owner static certification duration count differs")
        if any(duration < 0 for duration in self.command_durations_ms):
            raise ValueError("Owner static certification durations cannot be negative")
        return self


def build_owner_static_certification_identity(commit: str) -> dict[str, str]:
    if _COMMIT.fullmatch(commit) is None:
        raise ValueError("Owner static release commit must be exact")
    return {
        "schema": SCHEMA,
        "release_commit": commit,
        "command_set_digest": _digest(STATIC_CERTIFICATION_COMMANDS),
    }


def validate_owner_static_manifest_identity(
    manifest: OwnerStaticReleaseCertificationManifest,
    commit: str,
) -> None:
    expected = build_owner_static_certification_identity(commit)
    actual = manifest.model_dump(mode="python", by_alias=True)
    for key, value in expected.items():
        if actual.get(key) != value:
            label = "release commit" if key == "release_commit" else key.replace("_", " ")
            raise ValueError(f"Owner static certification {label} differs")


def owner_static_certification_manifest_path(repo_root: Path, commit: str) -> Path:
    relative = _git(
        repo_root,
        "rev-parse",
        "--git-path",
        f"brc-owner-static-certifications/{commit}.json",
    )
    path = Path(relative)
    return path if path.is_absolute() else repo_root / path


def validate_owner_static_release_certification(repo_root: Path, commit: str) -> None:
    _require_exact_clean_head(repo_root, commit)
    path = owner_static_certification_manifest_path(repo_root, commit)
    if not path.is_file():
        raise ValueError("exact Owner static Release Commit lacks certification")
    manifest = OwnerStaticReleaseCertificationManifest.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    validate_owner_static_manifest_identity(manifest, commit)


def certify_owner_static_release_candidate(
    repo_root: Path,
    commit: str,
) -> OwnerStaticReleaseCertificationManifest:
    _require_exact_clean_head(repo_root, commit)
    durations: list[int] = []
    for index, command in enumerate(STATIC_CERTIFICATION_COMMANDS, start=1):
        print(
            f"owner_static_certification_step={index}/{len(STATIC_CERTIFICATION_COMMANDS)} "
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
                f"Owner static certification command {index} failed:\n{output}"
            )
    _require_exact_clean_head(repo_root, commit)
    manifest = OwnerStaticReleaseCertificationManifest.model_validate(
        {
            **build_owner_static_certification_identity(commit),
            "status": "pass",
            "certified_at_ms": int(time.time() * 1_000),
            "command_durations_ms": tuple(durations),
        }
    )
    path = owner_static_certification_manifest_path(repo_root, commit)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        manifest.model_dump_json(indent=2, by_alias=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _require_exact_clean_head(repo_root: Path, commit: str) -> None:
    if _git(repo_root, "rev-parse", "HEAD") != commit:
        raise ValueError("Owner static certification commit must equal current HEAD")
    if _git(repo_root, "status", "--porcelain"):
        raise ValueError("Owner static certification requires a clean worktree")


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
        raise ValueError("resolved Owner static release commit is invalid")
    return commit


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    commit = _resolve_commit(args.commit)
    manifest = certify_owner_static_release_candidate(REPO_ROOT, commit)
    print(manifest.model_dump_json(by_alias=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
