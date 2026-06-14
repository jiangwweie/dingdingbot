from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
OVERLAY_PATH = REPO_ROOT / "docs" / "canon" / "STRATEGYGROUP_RUNTIME_PILOT_OVERLAY.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_current_agent_entrypoints_reference_strategygroup_runtime_pilot_overlay():
    overlay_ref = "docs/canon/STRATEGYGROUP_RUNTIME_PILOT_OVERLAY.md"

    entrypoints = [
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / "docs" / "canon" / "AGENT_WORKSPACE_RULES.md",
        REPO_ROOT / "docs" / "ops" / "agent-current-brc-baseline.md",
    ]

    for path in entrypoints:
        text = _read(path)
        assert overlay_ref in text, path


def test_strategygroup_runtime_pilot_overlay_preserves_standing_authorization():
    text = _read(OVERLAY_PATH)

    assert "Owner selects a StrategyGroup" in text
    assert "Deploy apply" in text
    assert "Real order action" in text
    assert "must not wait" in text
    assert "fresh chat phrase" in text
    assert "FinalGate + Operation Layer" in text
    assert "evidence-packet-as-owner-interface" in text
    assert "post_signal_auto_resume" in text
    assert "ready_for_action_time_final_gate" in text


def test_strategygroup_runtime_pilot_overlay_keeps_hard_safety_stops():
    text = _read(OVERLAY_PATH)

    for phrase in [
        "withdrawal or transfer actions",
        "Operation Layer bypass",
        "FinalGate bypass",
        "unauditable exchange write",
        "duplicate-submit risk",
        "conflicting active position or open order",
    ]:
        assert phrase in text


def test_current_agent_baseline_requires_recovery_classification():
    text = _read(REPO_ROOT / "docs" / "ops" / "agent-current-brc-baseline.md")

    for recovery_class in [
        "waiting_for_market",
        "missing_fact",
        "deployment_issue",
        "active_position_resolution",
        "hard_safety_stop",
        "review_only_warning",
    ]:
        assert recovery_class in text
