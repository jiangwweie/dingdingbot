from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_DOCS = [
    REPO_ROOT / "docs" / "ops" / "tokyo-runtime-governance-owner-deploy-authorization-packet-2026-06-10.md",
    REPO_ROOT / "docs" / "ops" / "tokyo-runtime-governance-controlled-deployment-runbook-2026-06-10.md",
]


def test_tokyo_deploy_docs_do_not_pin_local_release_artifact_candidates():
    """Tracked deploy docs must defer local candidate identity to the manifest."""

    local_candidate_artifact_pattern = re.compile(
        r"output/tokyo-runtime-governance-release/"
        r"brc-runtime-governance-[0-9a-f]{8}-20[0-9]{6}T[0-9]{6}Z"
    )
    for path in DEPLOY_DOCS:
        text = path.read_text()

        assert local_candidate_artifact_pattern.search(text) is None, path
        assert "candidate archive:" not in text
        assert "candidate manifest:" not in text
        assert "Last locally verified candidate" not in text
        assert "release-readiness-manifest.json" in text
        assert "current HEAD" in text or "newer HEAD" in text
