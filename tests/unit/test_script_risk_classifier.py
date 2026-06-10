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


def test_tokyo_runtime_governance_readonly_probe_is_review_required_not_write() -> None:
    result = classify_script_path(
        REPO_ROOT / "scripts/probe_tokyo_runtime_governance_readonly.py"
    )

    assert result.level == ScriptRiskLevel.REVIEW_REQUIRED
    assert result.default_allowed is False
    assert result.owner_confirmation_required is False
    assert result.live_action_possible is False
    assert result.exchange_write_possible is False
    assert result.database_write_possible is False
    assert result.runtime_control_possible is False
    assert ScriptRiskCategory.DECLARED_READ_ONLY in result.categories
    assert ScriptRiskCategory.LIVE_SCOPE in result.categories
    assert ScriptRiskCategory.EXCHANGE_WRITE not in result.categories
    assert ScriptRiskCategory.RUNTIME_CONTROL not in result.categories


def test_tokyo_migration_gap_audit_is_read_only_not_mutating() -> None:
    result = classify_script_path(
        REPO_ROOT / "scripts/audit_tokyo_runtime_governance_migration_gap.py"
    )

    assert result.level == ScriptRiskLevel.READ_ONLY
    assert result.default_allowed is True
    assert result.owner_confirmation_required is False
    assert result.live_action_possible is False
    assert result.exchange_write_possible is False
    assert result.database_write_possible is False
    assert result.runtime_control_possible is False
    assert ScriptRiskCategory.DECLARED_READ_ONLY in result.categories
    assert ScriptRiskCategory.EXCHANGE_WRITE not in result.categories
    assert ScriptRiskCategory.RUNTIME_CONTROL not in result.categories


def test_tokyo_deploy_plan_is_planning_only_not_mutating() -> None:
    result = classify_script_path(
        REPO_ROOT / "scripts/plan_tokyo_runtime_governance_deploy.py"
    )

    assert result.level == ScriptRiskLevel.MUTATION_RESTRICTED
    assert result.default_allowed is False
    assert result.owner_confirmation_required is True
    assert result.live_action_possible is False
    assert result.exchange_write_possible is False
    assert result.database_write_possible is True
    assert result.runtime_control_possible is False
    assert ScriptRiskCategory.DECLARED_READ_ONLY in result.categories
    assert ScriptRiskCategory.DATABASE_WRITE in result.categories
    assert ScriptRiskCategory.LIVE_SCOPE in result.categories
    assert ScriptRiskCategory.OWNER_AUTH_REQUIRED in result.categories
    assert ScriptRiskCategory.REMOTE_DEPLOYMENT in result.categories
    assert ScriptRiskCategory.EXCHANGE_WRITE not in result.categories
    assert ScriptRiskCategory.RUNTIME_CONTROL not in result.categories


def test_remote_deployment_markers_are_mutation_restricted() -> None:
    result = classify_script_text(
        path="scripts/deploy_example.py",
        text=(
            '"""Dry-run by default; explicit Owner confirmation required."""\n'
            "commands = ['scp artifact tokyo:/tmp/a', "
            "'sudo -n systemctl stop svc', "
            "'pg_dump $DATABASE_URL -Fc -f backup.pgdump', "
            "'python -m alembic upgrade head', "
            "'ln -sfn release current']\n"
        ),
    )

    assert result.level == ScriptRiskLevel.MUTATION_RESTRICTED
    assert result.default_allowed is False
    assert result.owner_confirmation_required is True
    assert result.database_write_possible is True
    assert ScriptRiskCategory.REMOTE_DEPLOYMENT in result.categories
    assert ScriptRiskCategory.DATABASE_WRITE in result.categories
    assert ScriptRiskCategory.OWNER_AUTH_REQUIRED in result.categories


def test_tokyo_postdeploy_verifier_is_readonly_review_required_not_write() -> None:
    result = classify_script_path(
        REPO_ROOT / "scripts/verify_tokyo_runtime_governance_postdeploy.py"
    )

    assert result.level == ScriptRiskLevel.REVIEW_REQUIRED
    assert result.default_allowed is False
    assert result.live_action_possible is False
    assert result.exchange_write_possible is False
    assert result.database_write_possible is False
    assert result.runtime_control_possible is False
    assert ScriptRiskCategory.DECLARED_READ_ONLY in result.categories
    assert ScriptRiskCategory.LIVE_SCOPE in result.categories
    assert ScriptRiskCategory.EXCHANGE_WRITE not in result.categories
    assert ScriptRiskCategory.RUNTIME_CONTROL not in result.categories


def test_tokyo_deploy_executor_is_mutation_restricted_without_exchange_write() -> None:
    result = classify_script_path(
        REPO_ROOT / "scripts/execute_tokyo_runtime_governance_deploy.py"
    )

    assert result.level == ScriptRiskLevel.MUTATION_RESTRICTED
    assert result.default_allowed is False
    assert result.owner_confirmation_required is True
    assert result.live_action_possible is False
    assert result.exchange_write_possible is False
    assert result.database_write_possible is True
    assert result.runtime_control_possible is False
    assert ScriptRiskCategory.DATABASE_WRITE in result.categories
    assert ScriptRiskCategory.REMOTE_DEPLOYMENT in result.categories
    assert ScriptRiskCategory.OWNER_AUTH_REQUIRED in result.categories
    assert ScriptRiskCategory.EXCHANGE_WRITE not in result.categories


def test_tokyo_owner_deploy_packet_builder_is_readonly_not_mutating() -> None:
    result = classify_script_path(
        REPO_ROOT / "scripts/build_tokyo_runtime_governance_owner_deploy_packet.py"
    )

    assert result.level == ScriptRiskLevel.READ_ONLY
    assert result.live_action_possible is False
    assert result.exchange_write_possible is False
    assert result.database_write_possible is False
    assert result.runtime_control_possible is False
    assert ScriptRiskCategory.DECLARED_READ_ONLY in result.categories
    assert ScriptRiskCategory.OWNER_AUTH_REQUIRED in result.categories
    assert ScriptRiskCategory.EXCHANGE_WRITE not in result.categories
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
