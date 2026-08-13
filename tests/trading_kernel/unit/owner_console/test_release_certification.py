from __future__ import annotations

import pytest

from scripts.owner_console.certify_release_candidate import (
    OwnerApiReleaseCertificationManifest,
    build_owner_api_certification_identity,
    validate_owner_api_manifest_identity,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION

COMMIT = "a" * 40


def test_owner_api_certification_binds_commit_schema_and_focused_commands() -> None:
    identity = build_owner_api_certification_identity(COMMIT)

    assert identity["release_commit"] == COMMIT
    assert identity["schema_revision"] == CURRENT_SCHEMA_REVISION
    assert str(identity["command_set_digest"]).startswith("sha256:")


def test_owner_api_certification_rejects_a_different_exact_commit() -> None:
    manifest = OwnerApiReleaseCertificationManifest.model_validate(
        {
            **build_owner_api_certification_identity(COMMIT),
            "status": "pass",
            "certified_at_ms": 1,
            "command_durations_ms": (1, 1, 1),
        }
    )

    with pytest.raises(ValueError, match="release commit differs"):
        validate_owner_api_manifest_identity(manifest, "b" * 40)
