from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CURRENT_DOCS = [
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "docs" / "README.md",
    REPO_ROOT / "docs" / "current" / "AI_AGENT_CONSTRAINTS.md",
    REPO_ROOT / "docs" / "current" / "OWNER_RUNTIME_OPERATING_MODEL.md",
    REPO_ROOT / "docs" / "current" / "STRATEGY_CONTROL_BOARD_CONTRACT.md",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_current_agent_entrypoints_reference_current_strategygroup_docs():
    for path in CURRENT_DOCS[:4]:
        text = _read(path)
        assert "docs/current/" in text or "StrategyGroup" in text, path


def test_current_agent_constraints_preserve_standing_authorization():
    text = _read(REPO_ROOT / "docs" / "current" / "AI_AGENT_CONSTRAINTS.md")

    for phrase in [
        "Standing Authorization",
        "Tokyo deploy apply inside the active stage",
        "official in-boundary real order action",
        "FinalGate",
        "Operation Layer",
        "Watch Branch Intake",
    ]:
        assert phrase in text


def test_current_docs_keep_hard_safety_stops():
    combined = "\n".join(_read(path) for path in CURRENT_DOCS)

    for phrase in [
        "withdrawal",
        "transfer",
        "Operation Layer bypass",
        "FinalGate bypass",
        "duplicate-submit risk",
        "conflicting active position",
    ]:
        assert phrase in combined


def test_current_owner_interface_stays_simple():
    text = _read(REPO_ROOT / "docs" / "current" / "STRATEGY_CONTROL_BOARD_CONTRACT.md")

    for phrase in [
        "must not become a packet browser",
        "`observing`",
        "`signal_ready`",
        "`candidate_ready`",
        "`submitted`",
        "Stay quiet when all selected runtimes remain observing",
    ]:
        assert phrase in text


def test_current_strategygroup_file_source_retirement_boundary():
    text = _read(
        REPO_ROOT
        / "docs"
        / "current"
        / "strategy-group-handoffs"
        / "main-control-handoff-index.md"
    )

    for phrase in [
        "no longer a StrategyGroup runtime",
        "PG current state",
        "removed from `docs/current` as current inputs",
        "Old handoff/replay/policy files must not be used",
        "docs/current/strategy-group-handoffs/",
        "Historical",
        "material must not be wired back into current runtime decisions",
    ]:
        assert phrase in text


def test_current_gate_classes_are_documented():
    text = _read(REPO_ROOT / "docs" / "current" / "AI_AGENT_CONSTRAINTS.md")

    for recovery_class in [
        "waiting_for_market",
        "missing_fact",
        "deployment_issue",
        "active_position_resolution",
        "hard_safety_stop",
        "review_only_warning",
    ]:
        assert recovery_class in text
