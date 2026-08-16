from __future__ import annotations

import pytest

from scripts.owner_console.certify_static_release_candidate import (
    OwnerStaticReleaseCertificationManifest,
    build_owner_static_certification_identity,
    validate_owner_static_manifest_identity,
)

COMMIT = "a" * 40


def test_static_certification_binds_the_exact_commit_and_r1_portfolio() -> None:
    identity = build_owner_static_certification_identity(COMMIT)
    manifest = OwnerStaticReleaseCertificationManifest(
        **identity,
        status="pass",
        certified_at_ms=1,
        command_durations_ms=(1, 1),
    )

    validate_owner_static_manifest_identity(manifest, COMMIT)


def test_static_certification_rejects_a_different_exact_commit() -> None:
    manifest = OwnerStaticReleaseCertificationManifest(
        **build_owner_static_certification_identity(COMMIT),
        status="pass",
        certified_at_ms=1,
        command_durations_ms=(1, 1),
    )

    with pytest.raises(ValueError, match="release commit differs"):
        validate_owner_static_manifest_identity(manifest, "b" * 40)
