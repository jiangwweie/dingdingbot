from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_PATH = REPO_ROOT / "docs" / "history-archive-2026-06-15-pre-governance.tar.gz"


def test_historical_tokyo_deploy_docs_are_compressed_out_of_current_entrypoints():
    """Old deploy docs remain recoverable but are no longer current authority."""

    docs_readme = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    agent_guide = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert ARCHIVE_PATH.exists()
    assert "recovery material only" in docs_readme
    assert "recovery material only" in agent_guide
    assert "docs/current/OWNER_RUNTIME_OPERATING_MODEL.md" in docs_readme
    assert "tokyo-runtime-governance-owner-deploy-authorization-packet" not in docs_readme
