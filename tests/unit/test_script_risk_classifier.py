from pathlib import Path

from src.application.script_risk_classifier import (
    ScriptRiskCategory,
    ScriptRiskLevel,
    classify_script_path,
    classify_script_text,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_declared_read_only_research_script_is_allowed_by_default() -> None:
    result = classify_script_text(
        path="scripts/analyze_example.py",
        text=(
            '"""Research-only script. It reads local candles, does not modify PG, '
            'and does not start runtime."""\nprint("ok")\n'
        ),
    )

    assert result.level == ScriptRiskLevel.READ_ONLY
    assert result.default_allowed is True
    assert result.owner_confirmation_required is False
    assert ScriptRiskCategory.DECLARED_READ_ONLY in result.categories
    assert ScriptRiskCategory.RUNTIME_CONTROL not in result.categories


def test_unknown_script_fails_closed_for_review() -> None:
    result = classify_script_text(
        path="scripts/custom_helper.py",
        text="print('no declared safety contract')\n",
    )

    assert result.level == ScriptRiskLevel.UNKNOWN_REVIEW_REQUIRED
    assert result.default_allowed is False
    assert result.owner_confirmation_required is True
    assert result.categories == (ScriptRiskCategory.UNKNOWN,)


def test_live_owner_authorized_close_is_live_action_restricted() -> None:
    result = classify_script_path(REPO_ROOT / "scripts/owner_authorized_bnb_close.py")

    assert result.level == ScriptRiskLevel.LIVE_ACTION_RESTRICTED
    assert result.default_allowed is False
    assert result.owner_confirmation_required is True
    assert result.live_action_possible is True
    assert result.exchange_write_possible is True
    assert result.database_write_possible is True
    assert ScriptRiskCategory.LIVE_SCOPE in result.categories
    assert ScriptRiskCategory.OWNER_AUTH_REQUIRED in result.categories


def test_exchange_credential_preflight_is_review_required_not_write() -> None:
    result = classify_script_path(REPO_ROOT / "scripts/probe_exchange_credential_preflight.py")

    assert result.level == ScriptRiskLevel.REVIEW_REQUIRED
    assert result.default_allowed is False
    assert result.exchange_write_possible is False
    assert result.runtime_control_possible is False
    assert ScriptRiskCategory.EXCHANGE_READ in result.categories
    assert ScriptRiskCategory.CREDENTIAL_SENSITIVE in result.categories
    assert ScriptRiskCategory.LIVE_SCOPE in result.categories
    assert ScriptRiskCategory.RUNTIME_CONTROL not in result.categories


def test_testnet_daily_gate_reset_is_database_mutation_restricted() -> None:
    result = classify_script_path(REPO_ROOT / "scripts/reset_bnb_testnet_daily_gate.py")

    assert result.level == ScriptRiskLevel.MUTATION_RESTRICTED
    assert result.default_allowed is False
    assert result.database_write_possible is True
    assert result.exchange_write_possible is False
    assert ScriptRiskCategory.TESTNET_SCOPE in result.categories


def test_testnet_stress_script_is_exchange_write_restricted() -> None:
    result = classify_script_path(REPO_ROOT / "scripts/run_001d4_multi_cycle_stress.sh")

    assert result.level == ScriptRiskLevel.EXCHANGE_WRITE_RESTRICTED
    assert result.default_allowed is False
    assert result.exchange_write_possible is True
    assert result.runtime_control_possible is True
    assert ScriptRiskCategory.TESTNET_SCOPE in result.categories
