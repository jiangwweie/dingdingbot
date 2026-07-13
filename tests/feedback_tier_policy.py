"""Deterministic pytest feedback tiers for development and release gates."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any

from sqlalchemy.exc import ArgumentError
from sqlalchemy.engine import make_url


DEFAULT_TEST_POSTGRES_ADMIN_URL = (
    "postgresql+psycopg://dingdingbot:dingdingbot_dev@127.0.0.1:5432/postgres"
)


class FeedbackTier(str, Enum):
    FAST = "fast"
    MAINLINE = "mainline"
    RELEASE = "release"


class FeedbackEnvironmentError(RuntimeError):
    """Raised when a selected test tier cannot start safely."""


FAST_FILES = frozenset(
    {
        "tests/unit/test_action_spec_final_gate_adapter.py",
        "tests/unit/test_action_time_blocker_resolution.py",
        "tests/unit/test_action_time_pricing_sizing.py",
        "tests/unit/test_arch_p4_runtime_context.py",
        "tests/unit/test_b0_strategy_evaluation_context_builder.py",
        "tests/unit/test_b0_strategy_runtime_fact_overlay.py",
        "tests/unit/test_b0_strategy_semantics_binding.py",
        "tests/unit/test_binance_usdm_public_facts.py",
        "tests/unit/test_brf_price_action_evaluator.py",
        "tests/unit/test_comparative_strength.py",
        "tests/unit/test_decision_trace.py",
        "tests/unit/test_dynamic_promotion_sizing.py",
        "tests/unit/test_exchange_gateway_open_order_views.py",
        "tests/unit/test_exchange_gateway_position_rows.py",
        "tests/unit/test_execution_permission.py",
        "tests/unit/test_execution_sizing.py",
        "tests/unit/test_feedback_tier_policy.py",
        "tests/unit/test_l2_l7_mainline_chain_invariants.py",
        "tests/unit/test_live_outcome_ledger.py",
        "tests/unit/test_notional_sizing.py",
        "tests/unit/test_pattern_strategy_signal_adapter.py",
        "tests/unit/test_process_outcome_relevance.py",
        "tests/unit/test_protection_order_planner.py",
        "tests/unit/test_protection_price_planner.py",
        "tests/unit/test_reference_price_action_evaluators.py",
        "tests/unit/test_required_facts_readiness.py",
        "tests/unit/test_right_tail_review.py",
        "tests/unit/test_rmr_regime_classifier.py",
        "tests/unit/test_runtime_readiness_state.py",
        "tests/unit/test_runtime_signal_forensics.py",
        "tests/unit/test_script_risk_classifier.py",
        "tests/unit/test_strategy_candidate_semantics.py",
        "tests/unit/test_strategy_contract_v2_models.py",
        "tests/unit/test_strategy_family_registry.py",
        "tests/unit/test_strategy_family_signal_contract.py",
        "tests/unit/test_strategy_group_runtime_tier_policy.py",
        "tests/unit/test_strategy_runtime_safety_readiness.py",
        "tests/unit/test_strategy_semantic_admission.py",
        "tests/unit/test_ticket_bound_lifecycle_decision_reducer.py",
        "tests/unit/test_ticket_bound_production_lifecycle_certification.py",
    }
)


RELEASE_ONLY_FILES = frozenset(
    {
        "tests/unit/test_action_time_full_chain_impact.py",
        "tests/unit/test_action_time_ticket_materialization.py",
        "tests/unit/test_action_time_ticket_materialization_sequence.py",
        "tests/unit/test_brc_operation_layer.py",
        "tests/unit/test_capital_safety_scope_freeze_gate.py",
        "tests/unit/test_pg_promotion_action_time_lane_materialization.py",
        "tests/unit/test_runtime_control_state_repository.py",
        "tests/unit/test_strategygroup_tradeability_decision.py",
        "tests/unit/test_ticket_bound_exchange_command_worker.py",
        "tests/unit/test_ticket_bound_exchange_scope.py",
        "tests/unit/test_ticket_bound_lifecycle_maintenance_service.py",
        "tests/unit/test_ticket_bound_lifecycle_scheduler.py",
        "tests/unit/test_ticket_bound_post_submit_closure.py",
        "tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py",
        "tests/unit/test_ticket_bound_protected_submit_attempt.py",
        "tests/unit/test_ticket_bound_protection_reconciler.py",
        "tests/unit/test_ticket_bound_runner_protection_adjuster.py",
        "tests/unit/test_ticket_bound_runtime_safety_state_materialization.py",
    }
)


MAINLINE_SENTINELS_BY_FILE = {
    "tests/unit/test_action_time_full_chain_impact.py": frozenset(
        {
            "tests/unit/test_action_time_full_chain_impact.py::"
            "test_raw_pg_input_reaches_real_gateway_submit_boundary"
        }
    ),
    "tests/unit/test_action_time_ticket_materialization.py": frozenset(
        {
            "tests/unit/test_action_time_ticket_materialization.py::"
            "test_materializes_pg_action_time_ticket"
        }
    ),
    "tests/unit/test_action_time_ticket_materialization_sequence.py": frozenset(
        {
            "tests/unit/test_action_time_ticket_materialization_sequence.py::"
            "test_sequence_commits_fact_reservation_lane_and_ticket_as_one_unit"
        }
    ),
    "tests/unit/test_brc_operation_layer.py": frozenset(
        {
            "tests/unit/test_brc_operation_layer.py::"
            "test_operation_capabilities_model_supported_and_forbidden_operations"
        }
    ),
    "tests/unit/test_capital_safety_scope_freeze_gate.py": frozenset(
        {
            "tests/unit/test_capital_safety_scope_freeze_gate.py::"
            "test_scope_freeze_blocks_submit_mode_and_protected_submit"
        }
    ),
    "tests/unit/test_pg_promotion_action_time_lane_materialization.py": frozenset(
        {
            "tests/unit/test_pg_promotion_action_time_lane_materialization.py::"
            "test_materializes_promotion_lane_budget_protection_and_ticket"
        }
    ),
    "tests/unit/test_runtime_control_state_repository.py": frozenset(
        {
            "tests/unit/test_runtime_control_state_repository.py::"
            "test_repository_monitor_read_profile_retains_protected_submit_lineage"
        }
    ),
    "tests/unit/test_strategygroup_tradeability_decision.py": frozenset(
        {
            "tests/unit/test_strategygroup_tradeability_decision.py::"
            "test_tradeability_decision_classifies_first_blockers_without_authority"
        }
    ),
    "tests/unit/test_ticket_bound_exchange_command_worker.py": frozenset(
        {
            "tests/unit/test_ticket_bound_exchange_command_worker.py::"
            "test_worker_commits_claim_before_exchange_io_and_result_after"
        }
    ),
    "tests/unit/test_ticket_bound_exchange_scope.py": frozenset(
        {
            "tests/unit/test_ticket_bound_exchange_scope.py::"
            "test_scope_resolves_canonical_identity_to_pg_exchange_instrument"
        }
    ),
    "tests/unit/test_ticket_bound_lifecycle_maintenance_service.py": frozenset(
        {
            "tests/unit/test_ticket_bound_lifecycle_maintenance_service.py::"
            "test_lifecycle_maintenance_materializes_exit_protection_without_exchange_write"
        }
    ),
    "tests/unit/test_ticket_bound_lifecycle_scheduler.py": frozenset(
        {
            "tests/unit/test_ticket_bound_lifecycle_scheduler.py::"
            "test_exchange_snapshot_provider_normalizes_readonly_gateway_facts"
        }
    ),
    "tests/unit/test_ticket_bound_post_submit_closure.py": frozenset(
        {
            "tests/unit/test_ticket_bound_post_submit_closure.py::"
            "test_lifecycle_closure_records_final_exit_reconciliation_settlement_review"
        }
    ),
    "tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py": frozenset(
        {
            "tests/unit/test_ticket_bound_post_submit_reconciliation_tick.py::"
            "test_first_tick_marks_tp1_missing_as_recovery_required"
        }
    ),
    "tests/unit/test_ticket_bound_protected_submit_attempt.py": frozenset(
        {
            "tests/unit/test_ticket_bound_protected_submit_attempt.py::"
            "test_protected_submit_real_result_marks_ticket_and_handoff_submitted"
        }
    ),
    "tests/unit/test_ticket_bound_protection_reconciler.py": frozenset(
        {
            "tests/unit/test_ticket_bound_protection_reconciler.py::"
            "test_protection_reconciler_marks_complete_set_reconciled"
        }
    ),
    "tests/unit/test_ticket_bound_runner_protection_adjuster.py": frozenset(
        {
            "tests/unit/test_ticket_bound_runner_protection_adjuster.py::"
            "test_runner_adjuster_materializes_runner_sl_after_tp1_fill"
        }
    ),
    "tests/unit/test_ticket_bound_runtime_safety_state_materialization.py": frozenset(
        {
            "tests/unit/test_ticket_bound_runtime_safety_state_materialization.py::"
            "test_runtime_safety_state_materializes_submit_allowed_snapshot"
        }
    ),
}

MAINLINE_SENTINELS = frozenset(
    nodeid
    for sentinels in MAINLINE_SENTINELS_BY_FILE.values()
    for nodeid in sentinels
)


def _normalized_nodeid(nodeid: str) -> str:
    return str(nodeid).replace("\\", "/")


def _test_file(nodeid: str) -> str:
    return _normalized_nodeid(nodeid).split("::", 1)[0]


def classify_nodeid(nodeid: str) -> FeedbackTier:
    normalized = _normalized_nodeid(nodeid)
    test_file = _test_file(normalized)
    if normalized in MAINLINE_SENTINELS:
        return FeedbackTier.MAINLINE
    if test_file.startswith("tests/integration/"):
        return FeedbackTier.RELEASE
    if test_file in RELEASE_ONLY_FILES:
        return FeedbackTier.RELEASE
    if test_file in FAST_FILES:
        return FeedbackTier.FAST
    if test_file.startswith("tests/unit/"):
        return FeedbackTier.MAINLINE
    return FeedbackTier.RELEASE


def selected_for_tier(
    nodeid: str,
    selected_tier: FeedbackTier | str,
) -> bool:
    selected = FeedbackTier(selected_tier)
    item_tier = classify_nodeid(nodeid)
    if selected is FeedbackTier.RELEASE:
        return True
    if selected is FeedbackTier.MAINLINE:
        return item_tier in {FeedbackTier.FAST, FeedbackTier.MAINLINE}
    return item_tier is FeedbackTier.FAST


def marker_names_for_nodeid(nodeid: str) -> tuple[str, ...]:
    item_tier = classify_nodeid(nodeid)
    if item_tier is FeedbackTier.FAST:
        return ("feedback_fast", "feedback_mainline")
    if item_tier is FeedbackTier.MAINLINE:
        return ("feedback_mainline",)
    return ("feedback_release_only",)


def validate_tier_manifest(repo_root: Path) -> tuple[str, ...]:
    issues: set[str] = set()
    root = Path(repo_root)
    for test_file in FAST_FILES:
        if not (root / test_file).is_file():
            issues.add("fast_file_missing")
        if test_file.startswith("tests/integration/"):
            issues.add("fast_file_is_integration")
    for test_file in RELEASE_ONLY_FILES:
        if not (root / test_file).is_file():
            issues.add("release_file_missing")
        if test_file not in MAINLINE_SENTINELS_BY_FILE:
            issues.add("release_file_without_mainline_sentinel")
    for declared_file, sentinels in MAINLINE_SENTINELS_BY_FILE.items():
        if declared_file not in RELEASE_ONLY_FILES:
            issues.add("sentinel_for_non_release_file")
        if not sentinels:
            issues.add("release_file_without_mainline_sentinel")
        source_path = root / declared_file
        source = source_path.read_text(encoding="utf-8") if source_path.is_file() else ""
        for nodeid in sentinels:
            if _test_file(nodeid) != declared_file:
                issues.add("sentinel_file_mismatch")
                continue
            parts = nodeid.split("::", 1)
            test_name = parts[1].split("[", 1)[0] if len(parts) == 2 else ""
            if (
                f"def {test_name}(" not in source
                and f"async def {test_name}(" not in source
            ):
                issues.add("sentinel_test_missing")
    return tuple(sorted(issues))


def preflight_release_postgres(
    admin_url: str | None = None,
    *,
    connect_fn: Callable[..., Any] | None = None,
) -> None:
    try:
        url = make_url(admin_url or DEFAULT_TEST_POSTGRES_ADMIN_URL)
    except ArgumentError as exc:
        raise FeedbackEnvironmentError("release_postgres_url_invalid") from exc
    if url.get_backend_name() != "postgresql":
        raise FeedbackEnvironmentError("release_postgres_url_not_postgresql")
    if connect_fn is None:
        try:
            from psycopg import connect as psycopg_connect
        except ModuleNotFoundError as exc:
            raise FeedbackEnvironmentError(
                "release_postgres_dependency_missing: "
                "run python -m pip install -r requirements.txt"
            ) from exc
        connect_fn = psycopg_connect
    host = url.host or "127.0.0.1"
    port = int(url.port or 5432)
    database = url.database or "postgres"
    safe_target = f"host={host}:{port},database={database}"
    try:
        with connect_fn(
            host=host,
            port=port,
            dbname=database,
            user=url.username,
            password=url.password,
            connect_timeout=3,
        ) as connection:
            row = connection.execute("SELECT 1").fetchone()
    except ModuleNotFoundError as exc:
        raise FeedbackEnvironmentError(
            "release_postgres_dependency_missing: "
            "run python -m pip install -r requirements.txt"
        ) from exc
    except Exception as exc:
        raise FeedbackEnvironmentError(
            f"release_postgres_unavailable:{safe_target}"
        ) from exc
    if row != (1,):
        raise FeedbackEnvironmentError(
            f"release_postgres_probe_invalid:{safe_target}"
        )
