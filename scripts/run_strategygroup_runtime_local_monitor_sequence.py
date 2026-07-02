#!/usr/bin/env python3
"""Run local StrategyGroup runtime monitor artifacts in a strict sequence.

This helper is for goal-mode and manual status review. It prevents false
completion-audit gaps caused by running goal-progress and completion-audit
commands in parallel. The default mode is cache-only and does not contact Tokyo.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable
from datetime import datetime, timezone

try:
    from scripts.runtime_monitor_refresh import (
        DEPLOYMENT_ISSUE_STATUS,
        MONITOR_REFRESH_STATUS,
        TEMPORARILY_UNAVAILABLE_MONITOR_REFRESH_STATUS,
        combined_artifact_monitor_status,
        combined_artifact_monitor_refresh_reasons,
        monitor_owner_runtime_state,
        monitor_owner_action_label_for,
        monitor_owner_state_label_for,
        monitor_notification_projection,
        monitor_owner_status_for,
        monitor_refresh_sequence_status,
        monitor_status_projection,
        monitor_runtime_status_for,
        monitor_step_returncode_is_deployment_issue,
        monitor_step_returncode_is_refresh,
        owner_intervention_required_from_sources,
        artifact_monitor_refresh_reasons,
        artifact_monitor_refresh_needed,
        artifact_monitor_status,
        artifact_owner_runtime_issues,
        artifact_declared_runtime_status,
        first_artifact_declared_runtime_status,
        owner_runtime_issues_projection,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution fallback
    from runtime_monitor_refresh import (
        DEPLOYMENT_ISSUE_STATUS,
        MONITOR_REFRESH_STATUS,
        TEMPORARILY_UNAVAILABLE_MONITOR_REFRESH_STATUS,
        combined_artifact_monitor_status,
        combined_artifact_monitor_refresh_reasons,
        monitor_owner_runtime_state,
        monitor_owner_action_label_for,
        monitor_owner_state_label_for,
        monitor_notification_projection,
        monitor_owner_status_for,
        monitor_refresh_sequence_status,
        monitor_status_projection,
        monitor_runtime_status_for,
        monitor_step_returncode_is_deployment_issue,
        monitor_step_returncode_is_refresh,
        owner_intervention_required_from_sources,
        artifact_monitor_refresh_reasons,
        artifact_monitor_refresh_needed,
        artifact_monitor_status,
        artifact_owner_runtime_issues,
        artifact_declared_runtime_status,
        first_artifact_declared_runtime_status,
        owner_runtime_issues_projection,
    )


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.domain.runtime_readiness_state import ReadinessSeparation  # noqa: E402
try:
    from scripts.strategygroup_non_executing_projection import (  # noqa: E402
        review_outcome_default_next_step,
        review_outcome_string_list,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution fallback
    from strategygroup_non_executing_projection import (  # noqa: E402
        review_outcome_default_next_step,
        review_outcome_string_list,
    )

DEFAULT_DAILY_CHECK_JSON = REPO_ROOT / "output/runtime-monitor/latest-daily-check.json"
DEFAULT_DAILY_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-owner-progress.md"
)
OWNER_PROGRESS_STATE_LABELS = {
    "complete": "已完成",
    "processing": "处理中",
}
OWNER_PROGRESS_ACTION_LABELS = {
    "complete": "归档第一笔边界内真实订单闭环",
    "processing": "等待系统完成当前链路",
}
DEFAULT_GOAL_PROGRESS_JSON = REPO_ROOT / "output/runtime-monitor/latest-goal-progress.json"
DEFAULT_GOAL_PROGRESS_MD = REPO_ROOT / "output/runtime-monitor/latest-goal-progress.md"
DEFAULT_LIVE_CUTOVER_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-live-cutover-readiness.json"
)
DEFAULT_LIVE_CUTOVER_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-live-cutover-readiness.md"
)
DEFAULT_COMPLETION_AUDIT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-p0-live-order-closure-completion-audit.json"
)
DEFAULT_COMPLETION_AUDIT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-p0-live-order-closure-completion-audit.md"
)
DEFAULT_DRY_RUN_AUDIT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-runtime-dry-run-audit-chain.json"
)
DEFAULT_DRY_RUN_AUDIT_DIR = (
    REPO_ROOT / "output/runtime-monitor/runtime-dry-run-audit-chain"
)
DEFAULT_REPLAY_LAB_JSON = REPO_ROOT / "output/runtime-monitor/latest-runtime-replay-lab.json"
DEFAULT_REPLAY_LAB_MD = REPO_ROOT / "output/runtime-monitor/latest-runtime-replay-lab.md"
DEFAULT_SIGNAL_COVERAGE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-signal-coverage-diagnostic.json"
)
DEFAULT_SIGNAL_COVERAGE_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-signal-coverage-diagnostic.md"
)
DEFAULT_SIGNAL_COVERAGE_EXPANSION_REVIEW_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-signal-coverage-expansion-review.json"
)
DEFAULT_SIGNAL_COVERAGE_EXPANSION_REVIEW_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-signal-coverage-expansion-review.md"
)
DEFAULT_L2_READINESS_REVIEW_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-l2-readiness-review.json"
)
DEFAULT_L2_READINESS_REVIEW_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-l2-readiness-review.md"
)
DEFAULT_L2_INTAKE_DRY_RUN_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-l2-intake-dry-run.json"
)
DEFAULT_L2_INTAKE_DRY_RUN_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-l2-intake-dry-run.md"
)
DEFAULT_L2_TIER_POLICY_REVIEW_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-l2-tier-policy-review.json"
)
DEFAULT_L2_TIER_POLICY_REVIEW_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-l2-tier-policy-review.md"
)
DEFAULT_POST_REVISION_REPLAY_REVIEW_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-post-revision-replay-review.json"
)
DEFAULT_POST_REVISION_REPLAY_REVIEW_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-post-revision-replay-review.md"
)
DEFAULT_OPPORTUNITY_REVIEW_WORK_LOOP_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-opportunity-review-work-loop.json"
)
DEFAULT_OPPORTUNITY_REVIEW_WORK_LOOP_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-opportunity-review-work-loop.md"
)
DEFAULT_BTPC_L2_SHADOW_FACT_QUALITY_REVIEW_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-l2-shadow-fact-quality-review.json"
)
DEFAULT_BTPC_L2_SHADOW_FACT_QUALITY_REVIEW_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-l2-shadow-fact-quality-review.md"
)
DEFAULT_BTPC_LOCAL_FACT_PROXY_REVIEW_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-local-fact-proxy-review.json"
)
DEFAULT_BTPC_LOCAL_FACT_PROXY_REVIEW_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-local-fact-proxy-review.md"
)
DEFAULT_BTPC_PROXY_REPLAY_QUALITY_REVIEW_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-proxy-replay-quality-review.json"
)
DEFAULT_BTPC_PROXY_REPLAY_QUALITY_REVIEW_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-proxy-replay-quality-review.md"
)
DEFAULT_BTPC_L2_KEEP_REVISE_FACT_SOURCE_REVIEW_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-l2-keep-revise-fact-source-review.json"
)
DEFAULT_BTPC_L2_KEEP_REVISE_FACT_SOURCE_REVIEW_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-l2-keep-revise-fact-source-review.md"
)
DEFAULT_BTPC_LIVE_DERIVATIVES_FACT_SOURCE_MAPPING_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-live-derivatives-fact-source-mapping.json"
)
DEFAULT_BTPC_LIVE_DERIVATIVES_FACT_SOURCE_MAPPING_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-live-derivatives-fact-source-mapping.md"
)
DEFAULT_BTPC_CLASSIFIER_RULE_REVIEW_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-classifier-rule-review.json"
)
DEFAULT_BTPC_CLASSIFIER_RULE_REVIEW_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-btpc-classifier-rule-review.md"
)
DEFAULT_STRATEGY_ASSET_STATE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-asset-state.json"
)
DEFAULT_STRATEGY_ASSET_STATE_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-asset-state.md"
)
DEFAULT_STRATEGYGROUP_QUALITY_WAVE_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.json"
)
DEFAULT_STRATEGYGROUP_QUALITY_WAVE_MD = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-quality-wave-current.md"
)
DEFAULT_STRATEGYGROUP_HANDOFF_BOUNDARY_CLOSURE_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-handoff-boundary-closure-current.json"
)
DEFAULT_STRATEGYGROUP_HANDOFF_BOUNDARY_CLOSURE_MD = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-handoff-boundary-closure-current.md"
)
DEFAULT_STRATEGYGROUP_BTPC_FACT_CLASSIFIER_GUARD_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-btpc-fact-classifier-guard-current.json"
)
DEFAULT_STRATEGYGROUP_BTPC_FACT_CLASSIFIER_GUARD_MD = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-btpc-fact-classifier-guard-current.md"
)
DEFAULT_STRATEGYGROUP_LIFECYCLE_REHEARSAL_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-lifecycle-rehearsal-current.json"
)
DEFAULT_STRATEGYGROUP_LIFECYCLE_REHEARSAL_MD = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-lifecycle-rehearsal-current.md"
)
DEFAULT_STRATEGYGROUP_PRE_LIVE_REHEARSAL_READINESS_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-pre-live-rehearsal-readiness-current.json"
)
DEFAULT_STRATEGYGROUP_PRE_LIVE_REHEARSAL_READINESS_MD = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-pre-live-rehearsal-readiness-current.md"
)
DEFAULT_STRATEGYGROUP_RUNTIME_SAFETY_STATE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-runtime-safety-state.json"
)
DEFAULT_STRATEGYGROUP_RUNTIME_SAFETY_STATE_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-runtime-safety-state.md"
)
DEFAULT_STRATEGYGROUP_PORTFOLIO_BOARD_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-portfolio-board.json"
)
DEFAULT_STRATEGYGROUP_PORTFOLIO_BOARD_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-portfolio-board.md"
)
DEFAULT_STRATEGYGROUP_REVIEW_ONLY_DEEP_DIVE_WAVE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-review-only-deep-dive-wave.json"
)
DEFAULT_STRATEGYGROUP_OWNER_POLICY_PACKAGE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-owner-policy-package.json"
)
DEFAULT_STRATEGYGROUP_QUALITY_CLOSURE_WAVE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-quality-closure-wave.json"
)
DEFAULT_STRATEGYGROUP_TRIAL_CANDIDATE_POOL_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-trial-candidate-pool.md"
)
DEFAULT_STRATEGY_CAPTURE_GAP_AUDIT_JSON = (
    REPO_ROOT / "output/runtime-monitor/strategy-capture-gap-audit-20260622.json"
)
DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_ENVELOPE_PROJECTION_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-projection.json"
)
DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_ENVELOPE_PROJECTION_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-projection.md"
)
DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_ENVELOPE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-v0.json"
)
DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_ENVELOPE_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-capital-trial-envelope-v0.md"
)
DEFAULT_STRATEGYGROUP_RESEARCH_INTAKE_REVIEW_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-research-intake-review.json"
)
DEFAULT_STRATEGYGROUP_RESEARCH_INTAKE_REVIEW_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-research-intake-review.md"
)
DEFAULT_STRATEGYGROUP_TRIAL_ASSET_ADMISSION_PROPOSAL_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.json"
)
DEFAULT_STRATEGYGROUP_TRIAL_ASSET_ADMISSION_PROPOSAL_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-trial-asset-admission-proposal.md"
)
DEFAULT_BRF2_OWNER_TRIAL_POLICY_SCOPE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-owner-trial-policy-scope.json"
)
DEFAULT_BRF2_OWNER_TRIAL_POLICY_SCOPE_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-owner-trial-policy-scope.md"
)
DEFAULT_BRF2_REQUIRED_FACTS_MAPPING_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-required-facts-mapping.json"
)
DEFAULT_BRF2_REQUIRED_FACTS_MAPPING_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-required-facts-mapping.md"
)
DEFAULT_BRF2_RUNTIME_SIGNAL_FACTS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-runtime-signal-facts.json"
)
DEFAULT_BRF2_RUNTIME_SIGNAL_FACTS_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-runtime-signal-facts.md"
)
DEFAULT_BRF2_RUNTIME_SIGNAL_CAPTURE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-runtime-signal-capture.json"
)
DEFAULT_BRF2_RUNTIME_SIGNAL_CAPTURE_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-runtime-signal-capture.md"
)
DEFAULT_BRF2_SHADOW_CANDIDATE_EVIDENCE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-shadow-candidate-evidence.json"
)
DEFAULT_BRF2_SHADOW_CANDIDATE_EVIDENCE_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-brf2-shadow-candidate-evidence.md"
)
DEFAULT_CPM_IDENTITY_ROUTING_DECISION_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-identity-routing-decision.json"
)
DEFAULT_CPM_IDENTITY_ROUTING_DECISION_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-identity-routing-decision.md"
)
DEFAULT_CPM_OWNER_TRIAL_POLICY_SCOPE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-owner-trial-policy-scope.json"
)
DEFAULT_CPM_OWNER_TRIAL_POLICY_SCOPE_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-owner-trial-policy-scope.md"
)
DEFAULT_CPM_REQUIRED_FACTS_MAPPING_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-required-facts-mapping.json"
)
DEFAULT_CPM_REQUIRED_FACTS_MAPPING_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-required-facts-mapping.md"
)
DEFAULT_CPM_RUNTIME_SIGNAL_FACTS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-facts.json"
)
DEFAULT_CPM_RUNTIME_SIGNAL_FACTS_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-facts.md"
)
DEFAULT_CPM_RUNTIME_SIGNAL_CAPTURE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-capture.json"
)
DEFAULT_CPM_RUNTIME_SIGNAL_CAPTURE_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-capture.md"
)
DEFAULT_CPM_SHADOW_CANDIDATE_EVIDENCE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-shadow-candidate-evidence.json"
)
DEFAULT_CPM_SHADOW_CANDIDATE_EVIDENCE_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-shadow-candidate-evidence.md"
)
DEFAULT_CPM_DRY_RUN_SUBMIT_REHEARSAL_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-dry-run-submit-rehearsal.json"
)
DEFAULT_CPM_DRY_RUN_SUBMIT_REHEARSAL_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-dry-run-submit-rehearsal.md"
)
DEFAULT_FOUR_CANDIDATE_RECENT_LIVE_SUBMIT_REPLAY_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-four-candidate-recent-live-submit-replay.json"
)
DEFAULT_BINANCE_USDM_PUBLIC_FACTS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-binance-usdm-public-facts.json"
)
DEFAULT_BINANCE_USDM_PUBLIC_FACTS_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-binance-usdm-public-facts.md"
)
DEFAULT_MPG_RUNTIME_ACTIVATION_EVIDENCE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-mpg-runtime-activation-evidence.json"
)
DEFAULT_SOR_RUNTIME_ACTIVATION_EVIDENCE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-sor-runtime-activation-evidence.json"
)
DEFAULT_FOUR_CANDIDATE_SCOPE_REVIEW_DECISION_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-four-candidate-scope-review-decision.json"
)
DEFAULT_CPM_FRESH_SIGNAL_LIVE_PATH_READINESS_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-cpm-fresh-signal-live-path-readiness.json"
)
DEFAULT_MPG_ACTION_TIME_FACTS_READINESS_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-mpg-action-time-facts-readiness.json"
)
DEFAULT_MPG_EXPANDED_WATCHER_FACTS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-mpg-expanded-watcher-facts.json"
)
DEFAULT_STRATEGY_FRESH_SIGNAL_ACTION_TIME_BOUNDARY_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategy-fresh-signal-action-time-boundary.json"
)
DEFAULT_STRATEGY_FRESH_SIGNAL_ACTION_TIME_BOUNDARY_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategy-fresh-signal-action-time-boundary.md"
)
DEFAULT_REPLAY_LIVE_PARITY_AUDIT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-replay-live-parity-audit.json"
)
DEFAULT_REPLAY_LIVE_PARITY_AUDIT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-replay-live-parity-audit.md"
)
DEFAULT_MI_TRIAL_ADMISSION_DECISION_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-mi-trial-admission-decision.json"
)
DEFAULT_MI_TRIAL_ADMISSION_DECISION_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-mi-trial-admission-decision.md"
)
DEFAULT_SOR_SESSION_DETECTOR_FACTS_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-sor-session-detector-facts.json"
)
DEFAULT_SOR_SESSION_DETECTOR_FACTS_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-sor-session-detector-facts.md"
)
DEFAULT_FOUR_CANDIDATE_RUNTIME_ACTIVATION_CLOSURE_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-four-candidate-runtime-activation-closure.json"
)
DEFAULT_FOUR_CANDIDATE_RUNTIME_ACTIVATION_CLOSURE_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-four-candidate-runtime-activation-closure.md"
)
DEFAULT_STRATEGYGROUP_TRIAL_GRADE_SIGNAL_GATE_AUDIT_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-trial-grade-signal-gate-audit.json"
)
DEFAULT_STRATEGYGROUP_TRIAL_GRADE_SIGNAL_GATE_AUDIT_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-strategygroup-trial-grade-signal-gate-audit.md"
)
DEFAULT_THREE_STRATEGY_LIVE_TRIAL_PORTFOLIO_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-three-strategy-live-trial-portfolio.json"
)
DEFAULT_THREE_STRATEGY_LIVE_TRIAL_PORTFOLIO_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-three-strategy-live-trial-portfolio.md"
)
DEFAULT_STRATEGYGROUP_TRADEABILITY_DECISION_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-tradeability-decision.json"
)
DEFAULT_STRATEGYGROUP_TRADEABILITY_DECISION_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-tradeability-decision.md"
)
DEFAULT_DAILY_LIVE_ENABLEMENT_TABLE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-daily-live-enablement-table.json"
)
DEFAULT_DAILY_LIVE_ENABLEMENT_TABLE_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-daily-live-enablement-table.md"
)
DEFAULT_SINGLE_LANE_TASK_PACKET_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-single-lane-task-packet.json"
)
DEFAULT_SINGLE_LANE_TASK_PACKET_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-single-lane-task-packet.md"
)
DEFAULT_STRATEGY_LIVE_CANDIDATE_POOL_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-live-candidate-pool.json"
)
DEFAULT_STRATEGY_LIVE_CANDIDATE_POOL_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategy-live-candidate-pool.md"
)
DEFAULT_RUNTIME_ACTIVE_MONITOR_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-runtime-active-observation-status.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-local-monitor-sequence.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-local-monitor-sequence.md"
)
CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = build_local_monitor_sequence_report(
        daily_check_mode=args.daily_check_mode,
        daily_check_json=Path(args.daily_check_json),
        daily_owner_progress=Path(args.daily_owner_progress),
        live_cutover_json=Path(args.live_cutover_json),
        live_cutover_md=Path(args.live_cutover_md),
        goal_progress_json=Path(args.goal_progress_json),
        goal_progress_md=Path(args.goal_progress_md),
        completion_audit_json=Path(args.completion_audit_json),
        completion_audit_md=Path(args.completion_audit_md),
        dry_run_audit_json=Path(args.dry_run_audit_json),
        dry_run_audit_dir=Path(args.dry_run_audit_dir),
        replay_lab_json=Path(args.replay_lab_json),
        replay_lab_md=Path(args.replay_lab_md),
        signal_coverage_json=Path(args.signal_coverage_json),
        signal_coverage_md=Path(args.signal_coverage_md),
        signal_coverage_source=args.signal_coverage_source,
        signal_coverage_expansion_review_json=Path(
            args.signal_coverage_expansion_review_json
        ),
        signal_coverage_expansion_review_md=Path(
            args.signal_coverage_expansion_review_md
        ),
        l2_readiness_review_json=Path(args.l2_readiness_review_json),
        l2_readiness_review_md=Path(args.l2_readiness_review_md),
        l2_intake_dry_run_json=Path(args.l2_intake_dry_run_json),
        l2_intake_dry_run_md=Path(args.l2_intake_dry_run_md),
        l2_tier_policy_review_json=Path(args.l2_tier_policy_review_json),
        l2_tier_policy_review_md=Path(args.l2_tier_policy_review_md),
        post_revision_replay_review_json=Path(
            args.post_revision_replay_review_json
        ),
        post_revision_replay_review_md=Path(args.post_revision_replay_review_md),
        opportunity_review_work_loop_json=Path(args.opportunity_review_work_loop_json),
        opportunity_review_work_loop_md=Path(args.opportunity_review_work_loop_md),
        btpc_l2_shadow_fact_quality_review_json=Path(
            args.btpc_l2_shadow_fact_quality_review_json
        ),
        btpc_l2_shadow_fact_quality_review_md=Path(
            args.btpc_l2_shadow_fact_quality_review_md
        ),
        btpc_local_fact_proxy_review_json=Path(args.btpc_local_fact_proxy_review_json),
        btpc_local_fact_proxy_review_md=Path(args.btpc_local_fact_proxy_review_md),
        btpc_proxy_replay_quality_review_json=Path(
            args.btpc_proxy_replay_quality_review_json
        ),
        btpc_proxy_replay_quality_review_md=Path(
            args.btpc_proxy_replay_quality_review_md
        ),
        btpc_l2_keep_revise_fact_source_review_json=Path(
            args.btpc_l2_keep_revise_fact_source_review_json
        ),
        btpc_l2_keep_revise_fact_source_review_md=Path(
            args.btpc_l2_keep_revise_fact_source_review_md
        ),
        btpc_live_derivatives_fact_source_mapping_json=Path(
            args.btpc_live_derivatives_fact_source_mapping_json
        ),
        btpc_live_derivatives_fact_source_mapping_md=Path(
            args.btpc_live_derivatives_fact_source_mapping_md
        ),
        btpc_classifier_rule_review_json=Path(args.btpc_classifier_rule_review_json),
        btpc_classifier_rule_review_md=Path(args.btpc_classifier_rule_review_md),
        strategy_asset_state_json=Path(
            args.strategy_asset_state_json
        ),
        strategy_asset_state_md=Path(args.strategy_asset_state_md),
        strategygroup_quality_wave_json=Path(args.strategygroup_quality_wave_json),
        strategygroup_quality_wave_md=Path(args.strategygroup_quality_wave_md),
        strategygroup_handoff_boundary_closure_json=Path(
            args.strategygroup_handoff_boundary_closure_json
        ),
        strategygroup_handoff_boundary_closure_md=Path(
            args.strategygroup_handoff_boundary_closure_md
        ),
        strategygroup_btpc_fact_classifier_guard_json=Path(
            args.strategygroup_btpc_fact_classifier_guard_json
        ),
        strategygroup_btpc_fact_classifier_guard_md=Path(
            args.strategygroup_btpc_fact_classifier_guard_md
        ),
        strategygroup_lifecycle_rehearsal_json=Path(
            args.strategygroup_lifecycle_rehearsal_json
        ),
        strategygroup_lifecycle_rehearsal_md=Path(
            args.strategygroup_lifecycle_rehearsal_md
        ),
        strategygroup_pre_live_rehearsal_readiness_json=Path(
            args.strategygroup_pre_live_rehearsal_readiness_json
        ),
        strategygroup_pre_live_rehearsal_readiness_md=Path(
            args.strategygroup_pre_live_rehearsal_readiness_md
        ),
        strategygroup_runtime_safety_state_json=Path(
            args.strategygroup_runtime_safety_state_json
        ),
        strategygroup_runtime_safety_state_md=Path(
            args.strategygroup_runtime_safety_state_md
        ),
        strategygroup_portfolio_board_json=Path(
            args.strategygroup_portfolio_board_json
        ),
        strategygroup_portfolio_board_md=Path(args.strategygroup_portfolio_board_md),
        strategygroup_review_only_deep_dive_wave_json=Path(
            args.strategygroup_review_only_deep_dive_wave_json
        ),
        strategygroup_owner_policy_package_json=Path(
            args.strategygroup_owner_policy_package_json
        ),
        strategygroup_quality_closure_wave_json=Path(
            args.strategygroup_quality_closure_wave_json
        ),
        strategygroup_trial_candidate_pool_md=Path(
            args.strategygroup_trial_candidate_pool_md
        ),
        strategy_capture_gap_audit_json=Path(args.strategy_capture_gap_audit_json),
        strategygroup_capital_trial_envelope_projection_json=Path(
            args.strategygroup_capital_trial_envelope_projection_json
        ),
        strategygroup_capital_trial_envelope_projection_md=Path(
            args.strategygroup_capital_trial_envelope_projection_md
        ),
        strategygroup_capital_trial_envelope_json=Path(
            args.strategygroup_capital_trial_envelope_json
        ),
        strategygroup_capital_trial_envelope_md=Path(
            args.strategygroup_capital_trial_envelope_md
        ),
        strategygroup_research_intake_review_json=Path(
            args.strategygroup_research_intake_review_json
        ),
        strategygroup_research_intake_review_md=Path(
            args.strategygroup_research_intake_review_md
        ),
        strategygroup_trial_asset_admission_proposal_json=Path(
            args.strategygroup_trial_asset_admission_proposal_json
        ),
        strategygroup_trial_asset_admission_proposal_md=Path(
            args.strategygroup_trial_asset_admission_proposal_md
        ),
        brf2_owner_trial_policy_scope_json=Path(
            args.brf2_owner_trial_policy_scope_json
        ),
        brf2_owner_trial_policy_scope_md=Path(
            args.brf2_owner_trial_policy_scope_md
        ),
        brf2_required_facts_mapping_json=Path(
            args.brf2_required_facts_mapping_json
        ),
        brf2_required_facts_mapping_md=Path(args.brf2_required_facts_mapping_md),
        brf2_runtime_signal_facts_json=Path(
            args.brf2_runtime_signal_facts_json
        ),
        brf2_runtime_signal_facts_md=Path(args.brf2_runtime_signal_facts_md),
        brf2_runtime_signal_capture_json=Path(
            args.brf2_runtime_signal_capture_json
        ),
        brf2_runtime_signal_capture_md=Path(args.brf2_runtime_signal_capture_md),
        brf2_shadow_candidate_evidence_json=Path(
            args.brf2_shadow_candidate_evidence_json
        ),
        brf2_shadow_candidate_evidence_md=Path(
            args.brf2_shadow_candidate_evidence_md
        ),
        cpm_identity_routing_decision_json=Path(
            args.cpm_identity_routing_decision_json
        ),
        cpm_identity_routing_decision_md=Path(args.cpm_identity_routing_decision_md),
        cpm_owner_trial_policy_scope_json=Path(
            args.cpm_owner_trial_policy_scope_json
        ),
        cpm_owner_trial_policy_scope_md=Path(args.cpm_owner_trial_policy_scope_md),
        cpm_required_facts_mapping_json=Path(args.cpm_required_facts_mapping_json),
        cpm_required_facts_mapping_md=Path(args.cpm_required_facts_mapping_md),
        cpm_runtime_signal_facts_json=Path(args.cpm_runtime_signal_facts_json),
        cpm_runtime_signal_facts_md=Path(args.cpm_runtime_signal_facts_md),
        cpm_runtime_signal_capture_json=Path(args.cpm_runtime_signal_capture_json),
        cpm_runtime_signal_capture_md=Path(args.cpm_runtime_signal_capture_md),
        cpm_shadow_candidate_evidence_json=Path(
            args.cpm_shadow_candidate_evidence_json
        ),
        cpm_shadow_candidate_evidence_md=Path(args.cpm_shadow_candidate_evidence_md),
        cpm_dry_run_submit_rehearsal_json=Path(
            args.cpm_dry_run_submit_rehearsal_json
        ),
        cpm_dry_run_submit_rehearsal_md=Path(args.cpm_dry_run_submit_rehearsal_md),
        four_candidate_recent_live_submit_replay_json=Path(
            args.four_candidate_recent_live_submit_replay_json
        ),
        four_candidate_runtime_activation_closure_json=Path(
            args.four_candidate_runtime_activation_closure_json
        ),
        four_candidate_runtime_activation_closure_md=Path(
            args.four_candidate_runtime_activation_closure_md
        ),
        strategygroup_trial_grade_signal_gate_audit_json=Path(
            args.strategygroup_trial_grade_signal_gate_audit_json
        ),
        strategygroup_trial_grade_signal_gate_audit_md=Path(
            args.strategygroup_trial_grade_signal_gate_audit_md
        ),
        three_strategy_live_trial_portfolio_json=Path(
            args.three_strategy_live_trial_portfolio_json
        ),
        three_strategy_live_trial_portfolio_md=Path(
            args.three_strategy_live_trial_portfolio_md
        ),
        strategygroup_tradeability_decision_json=Path(
            args.strategygroup_tradeability_decision_json
        ),
        strategygroup_tradeability_decision_md=Path(
            args.strategygroup_tradeability_decision_md
        ),
        daily_live_enablement_table_json=Path(args.daily_live_enablement_table_json),
        daily_live_enablement_table_md=Path(args.daily_live_enablement_table_md),
        single_lane_task_packet_json=Path(args.single_lane_task_packet_json),
        single_lane_task_packet_md=Path(args.single_lane_task_packet_md),
        strategy_live_candidate_pool_json=Path(
            args.strategy_live_candidate_pool_json
        ),
        strategy_live_candidate_pool_md=Path(args.strategy_live_candidate_pool_md),
        runtime_active_monitor_json=Path(args.runtime_active_monitor_json),
        binance_public_facts_ssh_host=args.binance_public_facts_ssh_host,
    )
    owner_progress_text = _owner_progress_text(report)
    if args.output_json:
        _write_json(Path(args.output_json), report)
    if args.output_owner_progress:
        _write_text(Path(args.output_owner_progress), owner_progress_text + "\n")
    if args.owner_progress:
        print(owner_progress_text)
    elif args.json:
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        _print_human_report(report)
    return 0 if _sequence_report_is_success(report) else 2


def _sequence_report_is_success(report: dict[str, Any]) -> bool:
    owner_runtime_issues = artifact_owner_runtime_issues(report)
    owner_runtime_state = (
        report.get("owner_runtime_state")
        if isinstance(report.get("owner_runtime_state"), dict)
        else {}
    )
    notification = (
        report.get("notification") if isinstance(report.get("notification"), dict) else {}
    )
    blockers = owner_runtime_issues["blockers"]
    non_market_gaps = owner_runtime_issues["non_market_gaps"]
    if blockers:
        return False
    if non_market_gaps:
        return False
    if (
        owner_runtime_state.get("owner_intervention_required") is True
        or notification.get("owner_intervention_required") is True
    ):
        return False
    if report.get("monitor_status") == "deployment_issue":
        return False
    status = str(report.get("status") or "")
    runtime_status = str(report.get("runtime_status") or "")
    return status in {"waiting_for_market", "processing", "complete"} or (
        status == MONITOR_REFRESH_STATUS
        and runtime_status == "waiting_for_market"
    ) or (
        status == TEMPORARILY_UNAVAILABLE_MONITOR_REFRESH_STATUS
        and runtime_status == "temporarily_unavailable"
    )


def build_local_monitor_sequence_report(
    *,
    daily_check_mode: str = "cache",
    daily_check_json: Path = DEFAULT_DAILY_CHECK_JSON,
    daily_owner_progress: Path = DEFAULT_DAILY_OWNER_PROGRESS,
    live_cutover_json: Path = DEFAULT_LIVE_CUTOVER_JSON,
    live_cutover_md: Path = DEFAULT_LIVE_CUTOVER_MD,
    goal_progress_json: Path = DEFAULT_GOAL_PROGRESS_JSON,
    goal_progress_md: Path = DEFAULT_GOAL_PROGRESS_MD,
    completion_audit_json: Path = DEFAULT_COMPLETION_AUDIT_JSON,
    completion_audit_md: Path = DEFAULT_COMPLETION_AUDIT_MD,
    dry_run_audit_json: Path = DEFAULT_DRY_RUN_AUDIT_JSON,
    dry_run_audit_dir: Path = DEFAULT_DRY_RUN_AUDIT_DIR,
    replay_lab_json: Path = DEFAULT_REPLAY_LAB_JSON,
    replay_lab_md: Path = DEFAULT_REPLAY_LAB_MD,
    signal_coverage_json: Path = DEFAULT_SIGNAL_COVERAGE_JSON,
    signal_coverage_md: Path = DEFAULT_SIGNAL_COVERAGE_MD,
    signal_coverage_source: str = "local_sqlite_read_only",
    signal_coverage_expansion_review_json: Path = (
        DEFAULT_SIGNAL_COVERAGE_EXPANSION_REVIEW_JSON
    ),
    signal_coverage_expansion_review_md: Path = (
        DEFAULT_SIGNAL_COVERAGE_EXPANSION_REVIEW_MD
    ),
    l2_readiness_review_json: Path = DEFAULT_L2_READINESS_REVIEW_JSON,
    l2_readiness_review_md: Path = DEFAULT_L2_READINESS_REVIEW_MD,
    l2_intake_dry_run_json: Path = DEFAULT_L2_INTAKE_DRY_RUN_JSON,
    l2_intake_dry_run_md: Path = DEFAULT_L2_INTAKE_DRY_RUN_MD,
    l2_tier_policy_review_json: Path = DEFAULT_L2_TIER_POLICY_REVIEW_JSON,
    l2_tier_policy_review_md: Path = DEFAULT_L2_TIER_POLICY_REVIEW_MD,
    post_revision_replay_review_json: Path = (
        DEFAULT_POST_REVISION_REPLAY_REVIEW_JSON
    ),
    post_revision_replay_review_md: Path = DEFAULT_POST_REVISION_REPLAY_REVIEW_MD,
    opportunity_review_work_loop_json: Path = DEFAULT_OPPORTUNITY_REVIEW_WORK_LOOP_JSON,
    opportunity_review_work_loop_md: Path = DEFAULT_OPPORTUNITY_REVIEW_WORK_LOOP_MD,
    btpc_l2_shadow_fact_quality_review_json: Path = (
        DEFAULT_BTPC_L2_SHADOW_FACT_QUALITY_REVIEW_JSON
    ),
    btpc_l2_shadow_fact_quality_review_md: Path = (
        DEFAULT_BTPC_L2_SHADOW_FACT_QUALITY_REVIEW_MD
    ),
    btpc_local_fact_proxy_review_json: Path = (
        DEFAULT_BTPC_LOCAL_FACT_PROXY_REVIEW_JSON
    ),
    btpc_local_fact_proxy_review_md: Path = DEFAULT_BTPC_LOCAL_FACT_PROXY_REVIEW_MD,
    btpc_proxy_replay_quality_review_json: Path = (
        DEFAULT_BTPC_PROXY_REPLAY_QUALITY_REVIEW_JSON
    ),
    btpc_proxy_replay_quality_review_md: Path = (
        DEFAULT_BTPC_PROXY_REPLAY_QUALITY_REVIEW_MD
    ),
    btpc_l2_keep_revise_fact_source_review_json: Path = (
        DEFAULT_BTPC_L2_KEEP_REVISE_FACT_SOURCE_REVIEW_JSON
    ),
    btpc_l2_keep_revise_fact_source_review_md: Path = (
        DEFAULT_BTPC_L2_KEEP_REVISE_FACT_SOURCE_REVIEW_MD
    ),
    btpc_live_derivatives_fact_source_mapping_json: Path = (
        DEFAULT_BTPC_LIVE_DERIVATIVES_FACT_SOURCE_MAPPING_JSON
    ),
    btpc_live_derivatives_fact_source_mapping_md: Path = (
        DEFAULT_BTPC_LIVE_DERIVATIVES_FACT_SOURCE_MAPPING_MD
    ),
    btpc_classifier_rule_review_json: Path = (
        DEFAULT_BTPC_CLASSIFIER_RULE_REVIEW_JSON
    ),
    btpc_classifier_rule_review_md: Path = DEFAULT_BTPC_CLASSIFIER_RULE_REVIEW_MD,
    strategy_asset_state_json: Path = (
        DEFAULT_STRATEGY_ASSET_STATE_JSON
    ),
    strategy_asset_state_md: Path = DEFAULT_STRATEGY_ASSET_STATE_MD,
    strategygroup_quality_wave_json: Path = DEFAULT_STRATEGYGROUP_QUALITY_WAVE_JSON,
    strategygroup_quality_wave_md: Path = DEFAULT_STRATEGYGROUP_QUALITY_WAVE_MD,
    strategygroup_handoff_boundary_closure_json: Path = (
        DEFAULT_STRATEGYGROUP_HANDOFF_BOUNDARY_CLOSURE_JSON
    ),
    strategygroup_handoff_boundary_closure_md: Path = (
        DEFAULT_STRATEGYGROUP_HANDOFF_BOUNDARY_CLOSURE_MD
    ),
    strategygroup_btpc_fact_classifier_guard_json: Path = (
        DEFAULT_STRATEGYGROUP_BTPC_FACT_CLASSIFIER_GUARD_JSON
    ),
    strategygroup_btpc_fact_classifier_guard_md: Path = (
        DEFAULT_STRATEGYGROUP_BTPC_FACT_CLASSIFIER_GUARD_MD
    ),
    strategygroup_lifecycle_rehearsal_json: Path = (
        DEFAULT_STRATEGYGROUP_LIFECYCLE_REHEARSAL_JSON
    ),
    strategygroup_lifecycle_rehearsal_md: Path = (
        DEFAULT_STRATEGYGROUP_LIFECYCLE_REHEARSAL_MD
    ),
    strategygroup_pre_live_rehearsal_readiness_json: Path = (
        DEFAULT_STRATEGYGROUP_PRE_LIVE_REHEARSAL_READINESS_JSON
    ),
    strategygroup_pre_live_rehearsal_readiness_md: Path = (
        DEFAULT_STRATEGYGROUP_PRE_LIVE_REHEARSAL_READINESS_MD
    ),
    strategygroup_runtime_safety_state_json: Path = (
        DEFAULT_STRATEGYGROUP_RUNTIME_SAFETY_STATE_JSON
    ),
    strategygroup_runtime_safety_state_md: Path = (
        DEFAULT_STRATEGYGROUP_RUNTIME_SAFETY_STATE_MD
    ),
    strategygroup_portfolio_board_json: Path = (
        DEFAULT_STRATEGYGROUP_PORTFOLIO_BOARD_JSON
    ),
    strategygroup_portfolio_board_md: Path = DEFAULT_STRATEGYGROUP_PORTFOLIO_BOARD_MD,
    strategygroup_review_only_deep_dive_wave_json: Path = (
        DEFAULT_STRATEGYGROUP_REVIEW_ONLY_DEEP_DIVE_WAVE_JSON
    ),
    strategygroup_owner_policy_package_json: Path = (
        DEFAULT_STRATEGYGROUP_OWNER_POLICY_PACKAGE_JSON
    ),
    strategygroup_quality_closure_wave_json: Path = (
        DEFAULT_STRATEGYGROUP_QUALITY_CLOSURE_WAVE_JSON
    ),
    strategygroup_trial_candidate_pool_md: Path = (
        DEFAULT_STRATEGYGROUP_TRIAL_CANDIDATE_POOL_MD
    ),
    strategy_capture_gap_audit_json: Path = DEFAULT_STRATEGY_CAPTURE_GAP_AUDIT_JSON,
    strategygroup_capital_trial_envelope_projection_json: Path = (
        DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_ENVELOPE_PROJECTION_JSON
    ),
    strategygroup_capital_trial_envelope_projection_md: Path = (
        DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_ENVELOPE_PROJECTION_MD
    ),
    strategygroup_capital_trial_envelope_json: Path = (
        DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_ENVELOPE_JSON
    ),
    strategygroup_capital_trial_envelope_md: Path = (
        DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_ENVELOPE_MD
    ),
    strategygroup_research_intake_review_json: Path = (
        DEFAULT_STRATEGYGROUP_RESEARCH_INTAKE_REVIEW_JSON
    ),
    strategygroup_research_intake_review_md: Path = (
        DEFAULT_STRATEGYGROUP_RESEARCH_INTAKE_REVIEW_MD
    ),
    strategygroup_trial_asset_admission_proposal_json: Path = (
        DEFAULT_STRATEGYGROUP_TRIAL_ASSET_ADMISSION_PROPOSAL_JSON
    ),
    strategygroup_trial_asset_admission_proposal_md: Path = (
        DEFAULT_STRATEGYGROUP_TRIAL_ASSET_ADMISSION_PROPOSAL_MD
    ),
    brf2_owner_trial_policy_scope_json: Path = (
        DEFAULT_BRF2_OWNER_TRIAL_POLICY_SCOPE_JSON
    ),
    brf2_owner_trial_policy_scope_md: Path = (
        DEFAULT_BRF2_OWNER_TRIAL_POLICY_SCOPE_MD
    ),
    brf2_required_facts_mapping_json: Path = DEFAULT_BRF2_REQUIRED_FACTS_MAPPING_JSON,
    brf2_required_facts_mapping_md: Path = DEFAULT_BRF2_REQUIRED_FACTS_MAPPING_MD,
    brf2_runtime_signal_facts_json: Path = DEFAULT_BRF2_RUNTIME_SIGNAL_FACTS_JSON,
    brf2_runtime_signal_facts_md: Path = DEFAULT_BRF2_RUNTIME_SIGNAL_FACTS_MD,
    brf2_runtime_signal_capture_json: Path = DEFAULT_BRF2_RUNTIME_SIGNAL_CAPTURE_JSON,
    brf2_runtime_signal_capture_md: Path = DEFAULT_BRF2_RUNTIME_SIGNAL_CAPTURE_MD,
    brf2_shadow_candidate_evidence_json: Path = (
        DEFAULT_BRF2_SHADOW_CANDIDATE_EVIDENCE_JSON
    ),
    brf2_shadow_candidate_evidence_md: Path = (
        DEFAULT_BRF2_SHADOW_CANDIDATE_EVIDENCE_MD
    ),
    cpm_identity_routing_decision_json: Path = (
        DEFAULT_CPM_IDENTITY_ROUTING_DECISION_JSON
    ),
    cpm_identity_routing_decision_md: Path = (
        DEFAULT_CPM_IDENTITY_ROUTING_DECISION_MD
    ),
    cpm_owner_trial_policy_scope_json: Path = (
        DEFAULT_CPM_OWNER_TRIAL_POLICY_SCOPE_JSON
    ),
    cpm_owner_trial_policy_scope_md: Path = (
        DEFAULT_CPM_OWNER_TRIAL_POLICY_SCOPE_MD
    ),
    cpm_required_facts_mapping_json: Path = DEFAULT_CPM_REQUIRED_FACTS_MAPPING_JSON,
    cpm_required_facts_mapping_md: Path = DEFAULT_CPM_REQUIRED_FACTS_MAPPING_MD,
    cpm_runtime_signal_facts_json: Path = DEFAULT_CPM_RUNTIME_SIGNAL_FACTS_JSON,
    cpm_runtime_signal_facts_md: Path = DEFAULT_CPM_RUNTIME_SIGNAL_FACTS_MD,
    cpm_runtime_signal_capture_json: Path = DEFAULT_CPM_RUNTIME_SIGNAL_CAPTURE_JSON,
    cpm_runtime_signal_capture_md: Path = DEFAULT_CPM_RUNTIME_SIGNAL_CAPTURE_MD,
    cpm_shadow_candidate_evidence_json: Path = (
        DEFAULT_CPM_SHADOW_CANDIDATE_EVIDENCE_JSON
    ),
    cpm_shadow_candidate_evidence_md: Path = (
        DEFAULT_CPM_SHADOW_CANDIDATE_EVIDENCE_MD
    ),
    cpm_dry_run_submit_rehearsal_json: Path = (
        DEFAULT_CPM_DRY_RUN_SUBMIT_REHEARSAL_JSON
    ),
    cpm_dry_run_submit_rehearsal_md: Path = (
        DEFAULT_CPM_DRY_RUN_SUBMIT_REHEARSAL_MD
    ),
    strategy_fresh_signal_action_time_boundary_json: Path = (
        DEFAULT_STRATEGY_FRESH_SIGNAL_ACTION_TIME_BOUNDARY_JSON
    ),
    strategy_fresh_signal_action_time_boundary_md: Path = (
        DEFAULT_STRATEGY_FRESH_SIGNAL_ACTION_TIME_BOUNDARY_MD
    ),
    replay_live_parity_audit_json: Path = DEFAULT_REPLAY_LIVE_PARITY_AUDIT_JSON,
    replay_live_parity_audit_md: Path = DEFAULT_REPLAY_LIVE_PARITY_AUDIT_MD,
    mi_trial_admission_decision_json: Path = DEFAULT_MI_TRIAL_ADMISSION_DECISION_JSON,
    mi_trial_admission_decision_md: Path = DEFAULT_MI_TRIAL_ADMISSION_DECISION_MD,
    four_candidate_recent_live_submit_replay_json: Path = (
        DEFAULT_FOUR_CANDIDATE_RECENT_LIVE_SUBMIT_REPLAY_JSON
    ),
    four_candidate_runtime_activation_closure_json: Path = (
        DEFAULT_FOUR_CANDIDATE_RUNTIME_ACTIVATION_CLOSURE_JSON
    ),
    four_candidate_runtime_activation_closure_md: Path = (
        DEFAULT_FOUR_CANDIDATE_RUNTIME_ACTIVATION_CLOSURE_MD
    ),
    strategygroup_trial_grade_signal_gate_audit_json: Path = (
        DEFAULT_STRATEGYGROUP_TRIAL_GRADE_SIGNAL_GATE_AUDIT_JSON
    ),
    strategygroup_trial_grade_signal_gate_audit_md: Path = (
        DEFAULT_STRATEGYGROUP_TRIAL_GRADE_SIGNAL_GATE_AUDIT_MD
    ),
    three_strategy_live_trial_portfolio_json: Path = (
        DEFAULT_THREE_STRATEGY_LIVE_TRIAL_PORTFOLIO_JSON
    ),
    three_strategy_live_trial_portfolio_md: Path = (
        DEFAULT_THREE_STRATEGY_LIVE_TRIAL_PORTFOLIO_MD
    ),
    strategygroup_tradeability_decision_json: Path = (
        DEFAULT_STRATEGYGROUP_TRADEABILITY_DECISION_JSON
    ),
    strategygroup_tradeability_decision_md: Path = (
        DEFAULT_STRATEGYGROUP_TRADEABILITY_DECISION_MD
    ),
    daily_live_enablement_table_json: Path = (
        DEFAULT_DAILY_LIVE_ENABLEMENT_TABLE_JSON
    ),
    daily_live_enablement_table_md: Path = DEFAULT_DAILY_LIVE_ENABLEMENT_TABLE_MD,
    single_lane_task_packet_json: Path = DEFAULT_SINGLE_LANE_TASK_PACKET_JSON,
    single_lane_task_packet_md: Path = DEFAULT_SINGLE_LANE_TASK_PACKET_MD,
    strategy_live_candidate_pool_json: Path = DEFAULT_STRATEGY_LIVE_CANDIDATE_POOL_JSON,
    strategy_live_candidate_pool_md: Path = DEFAULT_STRATEGY_LIVE_CANDIDATE_POOL_MD,
    runtime_active_monitor_json: Path = DEFAULT_RUNTIME_ACTIVE_MONITOR_JSON,
    binance_public_facts_ssh_host: str = "",
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    if (
        brf2_runtime_signal_capture_json.parent
        != DEFAULT_BRF2_RUNTIME_SIGNAL_CAPTURE_JSON.parent
    ):
        cpm_parent = brf2_runtime_signal_capture_json.parent
        if cpm_identity_routing_decision_json == DEFAULT_CPM_IDENTITY_ROUTING_DECISION_JSON:
            cpm_identity_routing_decision_json = (
                cpm_parent / DEFAULT_CPM_IDENTITY_ROUTING_DECISION_JSON.name
            )
        if cpm_identity_routing_decision_md == DEFAULT_CPM_IDENTITY_ROUTING_DECISION_MD:
            cpm_identity_routing_decision_md = (
                cpm_parent / DEFAULT_CPM_IDENTITY_ROUTING_DECISION_MD.name
            )
        if cpm_owner_trial_policy_scope_json == DEFAULT_CPM_OWNER_TRIAL_POLICY_SCOPE_JSON:
            cpm_owner_trial_policy_scope_json = (
                cpm_parent / DEFAULT_CPM_OWNER_TRIAL_POLICY_SCOPE_JSON.name
            )
        if cpm_owner_trial_policy_scope_md == DEFAULT_CPM_OWNER_TRIAL_POLICY_SCOPE_MD:
            cpm_owner_trial_policy_scope_md = (
                cpm_parent / DEFAULT_CPM_OWNER_TRIAL_POLICY_SCOPE_MD.name
            )
        if cpm_required_facts_mapping_json == DEFAULT_CPM_REQUIRED_FACTS_MAPPING_JSON:
            cpm_required_facts_mapping_json = (
                cpm_parent / DEFAULT_CPM_REQUIRED_FACTS_MAPPING_JSON.name
            )
        if cpm_required_facts_mapping_md == DEFAULT_CPM_REQUIRED_FACTS_MAPPING_MD:
            cpm_required_facts_mapping_md = (
                cpm_parent / DEFAULT_CPM_REQUIRED_FACTS_MAPPING_MD.name
            )
        if cpm_runtime_signal_facts_json == DEFAULT_CPM_RUNTIME_SIGNAL_FACTS_JSON:
            cpm_runtime_signal_facts_json = (
                cpm_parent / DEFAULT_CPM_RUNTIME_SIGNAL_FACTS_JSON.name
            )
        if cpm_runtime_signal_facts_md == DEFAULT_CPM_RUNTIME_SIGNAL_FACTS_MD:
            cpm_runtime_signal_facts_md = (
                cpm_parent / DEFAULT_CPM_RUNTIME_SIGNAL_FACTS_MD.name
            )
        if cpm_runtime_signal_capture_json == DEFAULT_CPM_RUNTIME_SIGNAL_CAPTURE_JSON:
            cpm_runtime_signal_capture_json = (
                cpm_parent / DEFAULT_CPM_RUNTIME_SIGNAL_CAPTURE_JSON.name
            )
        if cpm_runtime_signal_capture_md == DEFAULT_CPM_RUNTIME_SIGNAL_CAPTURE_MD:
            cpm_runtime_signal_capture_md = (
                cpm_parent / DEFAULT_CPM_RUNTIME_SIGNAL_CAPTURE_MD.name
            )
        if cpm_shadow_candidate_evidence_json == DEFAULT_CPM_SHADOW_CANDIDATE_EVIDENCE_JSON:
            cpm_shadow_candidate_evidence_json = (
                cpm_parent / DEFAULT_CPM_SHADOW_CANDIDATE_EVIDENCE_JSON.name
            )
        if cpm_shadow_candidate_evidence_md == DEFAULT_CPM_SHADOW_CANDIDATE_EVIDENCE_MD:
            cpm_shadow_candidate_evidence_md = (
                cpm_parent / DEFAULT_CPM_SHADOW_CANDIDATE_EVIDENCE_MD.name
            )
        if cpm_dry_run_submit_rehearsal_json == DEFAULT_CPM_DRY_RUN_SUBMIT_REHEARSAL_JSON:
            cpm_dry_run_submit_rehearsal_json = (
                cpm_parent / DEFAULT_CPM_DRY_RUN_SUBMIT_REHEARSAL_JSON.name
            )
        if cpm_dry_run_submit_rehearsal_md == DEFAULT_CPM_DRY_RUN_SUBMIT_REHEARSAL_MD:
            cpm_dry_run_submit_rehearsal_md = (
                cpm_parent / DEFAULT_CPM_DRY_RUN_SUBMIT_REHEARSAL_MD.name
            )
        if (
            strategy_fresh_signal_action_time_boundary_json
            == DEFAULT_STRATEGY_FRESH_SIGNAL_ACTION_TIME_BOUNDARY_JSON
        ):
            strategy_fresh_signal_action_time_boundary_json = (
                cpm_parent
                / DEFAULT_STRATEGY_FRESH_SIGNAL_ACTION_TIME_BOUNDARY_JSON.name
            )
        if (
            strategy_fresh_signal_action_time_boundary_md
            == DEFAULT_STRATEGY_FRESH_SIGNAL_ACTION_TIME_BOUNDARY_MD
        ):
            strategy_fresh_signal_action_time_boundary_md = (
                cpm_parent
                / DEFAULT_STRATEGY_FRESH_SIGNAL_ACTION_TIME_BOUNDARY_MD.name
            )
        if replay_live_parity_audit_json == DEFAULT_REPLAY_LIVE_PARITY_AUDIT_JSON:
            replay_live_parity_audit_json = (
                cpm_parent / DEFAULT_REPLAY_LIVE_PARITY_AUDIT_JSON.name
            )
        if replay_live_parity_audit_md == DEFAULT_REPLAY_LIVE_PARITY_AUDIT_MD:
            replay_live_parity_audit_md = (
                cpm_parent / DEFAULT_REPLAY_LIVE_PARITY_AUDIT_MD.name
            )
        if (
            mi_trial_admission_decision_json
            == DEFAULT_MI_TRIAL_ADMISSION_DECISION_JSON
        ):
            mi_trial_admission_decision_json = (
                cpm_parent / DEFAULT_MI_TRIAL_ADMISSION_DECISION_JSON.name
            )
        if mi_trial_admission_decision_md == DEFAULT_MI_TRIAL_ADMISSION_DECISION_MD:
            mi_trial_admission_decision_md = (
                cpm_parent / DEFAULT_MI_TRIAL_ADMISSION_DECISION_MD.name
            )
        if daily_live_enablement_table_json == DEFAULT_DAILY_LIVE_ENABLEMENT_TABLE_JSON:
            daily_live_enablement_table_json = (
                cpm_parent / DEFAULT_DAILY_LIVE_ENABLEMENT_TABLE_JSON.name
            )
        if daily_live_enablement_table_md == DEFAULT_DAILY_LIVE_ENABLEMENT_TABLE_MD:
            daily_live_enablement_table_md = (
                cpm_parent / DEFAULT_DAILY_LIVE_ENABLEMENT_TABLE_MD.name
            )
        if single_lane_task_packet_json == DEFAULT_SINGLE_LANE_TASK_PACKET_JSON:
            single_lane_task_packet_json = (
                cpm_parent / DEFAULT_SINGLE_LANE_TASK_PACKET_JSON.name
            )
        if single_lane_task_packet_md == DEFAULT_SINGLE_LANE_TASK_PACKET_MD:
            single_lane_task_packet_md = (
                cpm_parent / DEFAULT_SINGLE_LANE_TASK_PACKET_MD.name
            )
        if (
            strategy_live_candidate_pool_json
            == DEFAULT_STRATEGY_LIVE_CANDIDATE_POOL_JSON
        ):
            strategy_live_candidate_pool_json = (
                cpm_parent / DEFAULT_STRATEGY_LIVE_CANDIDATE_POOL_JSON.name
            )
        if strategy_live_candidate_pool_md == DEFAULT_STRATEGY_LIVE_CANDIDATE_POOL_MD:
            strategy_live_candidate_pool_md = (
                cpm_parent / DEFAULT_STRATEGY_LIVE_CANDIDATE_POOL_MD.name
            )
        if (
            four_candidate_runtime_activation_closure_json
            == DEFAULT_FOUR_CANDIDATE_RUNTIME_ACTIVATION_CLOSURE_JSON
        ):
            four_candidate_runtime_activation_closure_json = (
                cpm_parent
                / DEFAULT_FOUR_CANDIDATE_RUNTIME_ACTIVATION_CLOSURE_JSON.name
            )
        if (
            four_candidate_runtime_activation_closure_md
            == DEFAULT_FOUR_CANDIDATE_RUNTIME_ACTIVATION_CLOSURE_MD
        ):
            four_candidate_runtime_activation_closure_md = (
                cpm_parent / DEFAULT_FOUR_CANDIDATE_RUNTIME_ACTIVATION_CLOSURE_MD.name
            )
        if (
            strategygroup_trial_grade_signal_gate_audit_json
            == DEFAULT_STRATEGYGROUP_TRIAL_GRADE_SIGNAL_GATE_AUDIT_JSON
        ):
            strategygroup_trial_grade_signal_gate_audit_json = (
                cpm_parent
                / DEFAULT_STRATEGYGROUP_TRIAL_GRADE_SIGNAL_GATE_AUDIT_JSON.name
            )
        if (
            strategygroup_trial_grade_signal_gate_audit_md
            == DEFAULT_STRATEGYGROUP_TRIAL_GRADE_SIGNAL_GATE_AUDIT_MD
        ):
            strategygroup_trial_grade_signal_gate_audit_md = (
                cpm_parent
                / DEFAULT_STRATEGYGROUP_TRIAL_GRADE_SIGNAL_GATE_AUDIT_MD.name
            )
        binance_usdm_public_facts_json = (
            cpm_parent / DEFAULT_BINANCE_USDM_PUBLIC_FACTS_JSON.name
        )
        binance_usdm_public_facts_md = (
            cpm_parent / DEFAULT_BINANCE_USDM_PUBLIC_FACTS_MD.name
        )
        mpg_runtime_activation_evidence_json = (
            cpm_parent / DEFAULT_MPG_RUNTIME_ACTIVATION_EVIDENCE_JSON.name
        )
        sor_runtime_activation_evidence_json = (
            cpm_parent / DEFAULT_SOR_RUNTIME_ACTIVATION_EVIDENCE_JSON.name
        )
        sor_session_detector_facts_json = (
            cpm_parent / DEFAULT_SOR_SESSION_DETECTOR_FACTS_JSON.name
        )
    else:
        binance_usdm_public_facts_json = DEFAULT_BINANCE_USDM_PUBLIC_FACTS_JSON
        binance_usdm_public_facts_md = DEFAULT_BINANCE_USDM_PUBLIC_FACTS_MD
        mpg_runtime_activation_evidence_json = (
            DEFAULT_MPG_RUNTIME_ACTIVATION_EVIDENCE_JSON
        )
        sor_runtime_activation_evidence_json = (
            DEFAULT_SOR_RUNTIME_ACTIVATION_EVIDENCE_JSON
        )
        sor_session_detector_facts_json = DEFAULT_SOR_SESSION_DETECTOR_FACTS_JSON
    runner = command_runner or _run_command
    steps: list[dict[str, Any]] = []

    daily_command = _daily_check_command(
        mode=daily_check_mode,
        output_json=daily_check_json,
        output_owner_progress=daily_owner_progress,
    )
    steps.append(_run_step("daily_check", daily_command, daily_check_json, runner))

    dry_run_audit_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/runtime_dry_run_audit_chain.py"),
        "--output-dir",
        str(dry_run_audit_dir),
        "--output-json",
        str(dry_run_audit_json),
    ]
    steps.append(
        _run_step(
            "runtime_dry_run_audit_chain",
            dry_run_audit_command,
            dry_run_audit_json,
            runner,
        )
    )

    live_cutover_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/runtime_live_cutover_readiness.py"),
        "--output-json",
        str(live_cutover_json),
        "--output-owner-progress",
        str(live_cutover_md),
    ]
    steps.append(
        _run_step(
            "live_cutover_readiness",
            live_cutover_command,
            live_cutover_json,
            runner,
        )
    )

    strategygroup_portfolio_board_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_portfolio_board.py"),
        "--capture-gap-audit-json",
        str(strategy_capture_gap_audit_json),
        "--review-deep-dive-json",
        str(strategygroup_review_only_deep_dive_wave_json),
        "--owner-policy-package-json",
        str(strategygroup_owner_policy_package_json),
        "--quality-closure-wave-json",
        str(strategygroup_quality_closure_wave_json),
        "--output-json",
        str(strategygroup_portfolio_board_json),
        "--output-md",
        str(strategygroup_portfolio_board_md),
        "--output-trial-pool-md",
        str(strategygroup_trial_candidate_pool_md),
    ]
    steps.append(
        _run_step(
            "strategygroup_portfolio_board",
            strategygroup_portfolio_board_command,
            strategygroup_portfolio_board_json,
            runner,
        )
    )

    strategygroup_research_intake_review_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_research_intake_review.py"),
        "--output-json",
        str(strategygroup_research_intake_review_json),
        "--output-owner-progress",
        str(strategygroup_research_intake_review_md),
    ]
    steps.append(
        _run_step(
            "strategygroup_research_intake_review",
            strategygroup_research_intake_review_command,
            strategygroup_research_intake_review_json,
            runner,
        )
    )

    strategygroup_capital_trial_envelope_projection_command = [
        sys.executable,
        str(
            REPO_ROOT
            / "scripts/build_strategygroup_capital_trial_envelope_projection.py"
        ),
        "--portfolio-board-json",
        str(strategygroup_portfolio_board_json),
        "--research-intake-review-json",
        str(strategygroup_research_intake_review_json),
        "--output-json",
        str(strategygroup_capital_trial_envelope_projection_json),
        "--output-owner-progress",
        str(strategygroup_capital_trial_envelope_projection_md),
        "--output-trial-envelope-json",
        str(strategygroup_capital_trial_envelope_json),
        "--output-trial-envelope-md",
        str(strategygroup_capital_trial_envelope_md),
    ]
    steps.append(
        _run_step(
            "strategygroup_capital_trial_envelope_projection",
            strategygroup_capital_trial_envelope_projection_command,
            strategygroup_capital_trial_envelope_projection_json,
            runner,
        )
    )

    brf2_owner_trial_policy_scope_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_brf2_owner_trial_policy_scope.py"),
        "--output-json",
        str(brf2_owner_trial_policy_scope_json),
        "--output-owner-progress",
        str(brf2_owner_trial_policy_scope_md),
    ]
    steps.append(
        _run_step(
            "brf2_owner_trial_policy_scope",
            brf2_owner_trial_policy_scope_command,
            brf2_owner_trial_policy_scope_json,
            runner,
        )
    )

    strategygroup_trial_asset_admission_proposal_command = [
        sys.executable,
        str(
            REPO_ROOT
            / "scripts/build_strategygroup_trial_asset_admission_proposal.py"
        ),
        "--capital-trial-envelope-projection-json",
        str(strategygroup_capital_trial_envelope_projection_json),
        "--trial-envelope-json",
        str(strategygroup_capital_trial_envelope_json),
        "--brf2-owner-trial-policy-scope-json",
        str(brf2_owner_trial_policy_scope_json),
        "--output-json",
        str(strategygroup_trial_asset_admission_proposal_json),
        "--output-owner-progress",
        str(strategygroup_trial_asset_admission_proposal_md),
    ]
    steps.append(
        _run_step(
            "strategygroup_trial_asset_admission_proposal",
            strategygroup_trial_asset_admission_proposal_command,
            strategygroup_trial_asset_admission_proposal_json,
            runner,
        )
    )

    brf2_required_facts_mapping_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_brf2_required_facts_mapping.py"),
        "--trial-asset-admission-proposal-json",
        str(strategygroup_trial_asset_admission_proposal_json),
        "--brf2-owner-trial-policy-scope-json",
        str(brf2_owner_trial_policy_scope_json),
        "--output-json",
        str(brf2_required_facts_mapping_json),
        "--output-owner-progress",
        str(brf2_required_facts_mapping_md),
    ]
    steps.append(
        _run_step(
            "brf2_required_facts_mapping",
            brf2_required_facts_mapping_command,
            brf2_required_facts_mapping_json,
            runner,
        )
    )

    brf2_runtime_signal_facts_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_brf2_runtime_signal_facts.py"),
        "--strategy-source",
        signal_coverage_source,
        "--output-json",
        str(brf2_runtime_signal_facts_json),
        "--output-owner-progress",
        str(brf2_runtime_signal_facts_md),
    ]
    steps.append(
        _run_step(
            "brf2_runtime_signal_facts",
            brf2_runtime_signal_facts_command,
            brf2_runtime_signal_facts_json,
            runner,
        )
    )

    brf2_runtime_signal_capture_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_brf2_runtime_signal_capture.py"),
        "--required-facts-mapping-json",
        str(brf2_required_facts_mapping_json),
        "--owner-policy-json",
        str(brf2_owner_trial_policy_scope_json),
        "--fact-input-json",
        str(brf2_runtime_signal_facts_json),
        "--output-json",
        str(brf2_runtime_signal_capture_json),
        "--output-owner-progress",
        str(brf2_runtime_signal_capture_md),
    ]
    steps.append(
        _run_step(
            "brf2_runtime_signal_capture",
            brf2_runtime_signal_capture_command,
            brf2_runtime_signal_capture_json,
            runner,
        )
    )

    brf2_shadow_candidate_evidence_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_brf2_shadow_candidate_evidence.py"),
        "--runtime-signal-capture-json",
        str(brf2_runtime_signal_capture_json),
        "--output-json",
        str(brf2_shadow_candidate_evidence_json),
        "--output-owner-progress",
        str(brf2_shadow_candidate_evidence_md),
    ]
    steps.append(
        _run_step(
            "brf2_shadow_candidate_evidence",
            brf2_shadow_candidate_evidence_command,
            brf2_shadow_candidate_evidence_json,
            runner,
        )
    )

    cpm_identity_routing_decision_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_cpm_identity_routing_decision.py"),
        "--output-json",
        str(cpm_identity_routing_decision_json),
        "--output-owner-progress",
        str(cpm_identity_routing_decision_md),
    ]
    steps.append(
        _run_step(
            "cpm_identity_routing_decision",
            cpm_identity_routing_decision_command,
            cpm_identity_routing_decision_json,
            runner,
        )
    )

    cpm_owner_trial_policy_scope_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_cpm_owner_trial_policy_scope.py"),
        "--identity-json",
        str(cpm_identity_routing_decision_json),
        "--output-json",
        str(cpm_owner_trial_policy_scope_json),
        "--output-owner-progress",
        str(cpm_owner_trial_policy_scope_md),
    ]
    steps.append(
        _run_step(
            "cpm_owner_trial_policy_scope",
            cpm_owner_trial_policy_scope_command,
            cpm_owner_trial_policy_scope_json,
            runner,
        )
    )

    cpm_required_facts_mapping_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_cpm_required_facts_mapping.py"),
        "--owner-policy-json",
        str(cpm_owner_trial_policy_scope_json),
        "--output-json",
        str(cpm_required_facts_mapping_json),
        "--output-owner-progress",
        str(cpm_required_facts_mapping_md),
    ]
    steps.append(
        _run_step(
            "cpm_required_facts_mapping",
            cpm_required_facts_mapping_command,
            cpm_required_facts_mapping_json,
            runner,
        )
    )

    binance_usdm_public_facts_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/fetch_binance_usdm_public_facts.py"),
        "--fallback-json",
        str(binance_usdm_public_facts_json),
        "--output-json",
        str(binance_usdm_public_facts_json),
        "--output-owner-progress",
        str(binance_usdm_public_facts_md),
    ]
    if binance_public_facts_ssh_host:
        binance_usdm_public_facts_command.extend(
            ["--ssh-host", binance_public_facts_ssh_host]
        )
    steps.append(
        _run_step(
            "binance_usdm_public_facts",
            binance_usdm_public_facts_command,
            binance_usdm_public_facts_json,
            runner,
        )
    )

    cpm_runtime_signal_facts_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_cpm_runtime_signal_facts.py"),
        "--public-facts-json",
        str(binance_usdm_public_facts_json),
        "--fallback-json",
        str(cpm_runtime_signal_facts_json),
        "--output-json",
        str(cpm_runtime_signal_facts_json),
        "--output-owner-progress",
        str(cpm_runtime_signal_facts_md),
    ]
    steps.append(
        _run_step(
            "cpm_runtime_signal_facts",
            cpm_runtime_signal_facts_command,
            cpm_runtime_signal_facts_json,
            runner,
        )
    )

    cpm_runtime_signal_capture_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_cpm_runtime_signal_capture.py"),
        "--required-facts-mapping-json",
        str(cpm_required_facts_mapping_json),
        "--fact-input-json",
        str(cpm_runtime_signal_facts_json),
        "--output-json",
        str(cpm_runtime_signal_capture_json),
        "--output-owner-progress",
        str(cpm_runtime_signal_capture_md),
    ]
    steps.append(
        _run_step(
            "cpm_runtime_signal_capture",
            cpm_runtime_signal_capture_command,
            cpm_runtime_signal_capture_json,
            runner,
        )
    )

    cpm_shadow_candidate_evidence_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_cpm_shadow_candidate_evidence.py"),
        "--runtime-signal-capture-json",
        str(cpm_runtime_signal_capture_json),
        "--output-json",
        str(cpm_shadow_candidate_evidence_json),
        "--output-owner-progress",
        str(cpm_shadow_candidate_evidence_md),
    ]
    steps.append(
        _run_step(
            "cpm_shadow_candidate_evidence",
            cpm_shadow_candidate_evidence_command,
            cpm_shadow_candidate_evidence_json,
            runner,
        )
    )

    cpm_dry_run_submit_rehearsal_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_cpm_dry_run_submit_rehearsal.py"),
        "--required-facts-mapping-json",
        str(cpm_required_facts_mapping_json),
        "--runtime-signal-capture-json",
        str(cpm_runtime_signal_capture_json),
        "--shadow-candidate-evidence-json",
        str(cpm_shadow_candidate_evidence_json),
        "--synthetic-fresh-signal-fixture-json",
        str(
            REPO_ROOT
            / "docs/current/strategy-group-handoffs/CPM-RO-001/replay/cpm-long-synthetic-fresh-signal-fixture.json"
        ),
        "--output-json",
        str(cpm_dry_run_submit_rehearsal_json),
        "--output-owner-progress",
        str(cpm_dry_run_submit_rehearsal_md),
    ]
    steps.append(
        _run_step(
            "cpm_dry_run_submit_rehearsal",
            cpm_dry_run_submit_rehearsal_command,
            cpm_dry_run_submit_rehearsal_json,
            runner,
        )
    )

    four_candidate_runtime_activation_evidence_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_four_candidate_runtime_activation_evidence.py"),
        "--public-facts-json",
        str(binance_usdm_public_facts_json),
        "--replay-json",
        str(four_candidate_recent_live_submit_replay_json),
        "--cpm-capture-json",
        str(cpm_runtime_signal_capture_json),
        "--output-dir",
        str(four_candidate_runtime_activation_closure_json.parent),
    ]
    steps.append(
        _run_step(
            "four_candidate_runtime_activation_evidence",
            four_candidate_runtime_activation_evidence_command,
            mpg_runtime_activation_evidence_json,
            runner,
        )
    )

    sor_session_scope_detector_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_sor_session_scope_detector.py"),
        "--public-facts-json",
        str(binance_usdm_public_facts_json),
        "--output-dir",
        str(four_candidate_runtime_activation_closure_json.parent),
    ]
    if binance_public_facts_ssh_host:
        sor_session_scope_detector_command.extend(
            ["--ssh-host", binance_public_facts_ssh_host]
        )
    steps.append(
        _run_step(
            "sor_session_scope_detector",
            sor_session_scope_detector_command,
            sor_session_detector_facts_json,
            runner,
        )
    )

    mpg_high_beta_scope_readiness_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_mpg_high_beta_scope_readiness.py"),
        "--public-facts-json",
        str(binance_usdm_public_facts_json),
        "--replay-json",
        str(four_candidate_recent_live_submit_replay_json),
        "--output-dir",
        str(four_candidate_runtime_activation_closure_json.parent),
    ]
    steps.append(
        _run_step(
            "mpg_high_beta_scope_readiness",
            mpg_high_beta_scope_readiness_command,
            DEFAULT_MPG_ACTION_TIME_FACTS_READINESS_JSON,
            runner,
        )
    )

    strategy_fresh_signal_action_time_boundary_command = [
        sys.executable,
        str(
            REPO_ROOT
            / "scripts/build_strategy_fresh_signal_action_time_boundary.py"
        ),
        "--cpm-capture-json",
        str(cpm_runtime_signal_capture_json),
        "--cpm-facts-json",
        str(cpm_runtime_signal_facts_json),
        "--cpm-rehearsal-json",
        str(cpm_dry_run_submit_rehearsal_json),
        "--mpg-readiness-json",
        str(DEFAULT_MPG_ACTION_TIME_FACTS_READINESS_JSON),
        "--mpg-evidence-json",
        str(mpg_runtime_activation_evidence_json),
        "--sor-evidence-json",
        str(sor_runtime_activation_evidence_json),
        "--sor-detector-json",
        str(sor_session_detector_facts_json),
        "--output-json",
        str(strategy_fresh_signal_action_time_boundary_json),
        "--output-owner-progress",
        str(strategy_fresh_signal_action_time_boundary_md),
    ]
    steps.append(
        _run_step(
            "strategy_fresh_signal_action_time_boundary",
            strategy_fresh_signal_action_time_boundary_command,
            strategy_fresh_signal_action_time_boundary_json,
            runner,
        )
    )

    replay_live_parity_audit_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_replay_live_parity_audit.py"),
        "--replay-json",
        str(four_candidate_recent_live_submit_replay_json),
        "--cpm-facts-json",
        str(cpm_runtime_signal_facts_json),
        "--mpg-watcher-json",
        str(DEFAULT_MPG_EXPANDED_WATCHER_FACTS_JSON),
        "--sor-evidence-json",
        str(sor_runtime_activation_evidence_json),
        "--sor-detector-json",
        str(sor_session_detector_facts_json),
        "--output-json",
        str(replay_live_parity_audit_json),
        "--output-owner-progress",
        str(replay_live_parity_audit_md),
    ]
    steps.append(
        _run_step(
            "replay_live_parity_audit",
            replay_live_parity_audit_command,
            replay_live_parity_audit_json,
            runner,
        )
    )

    mi_trial_admission_decision_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_mi_trial_admission_decision.py"),
        "--replay-json",
        str(four_candidate_recent_live_submit_replay_json),
        "--public-facts-json",
        str(binance_usdm_public_facts_json),
        "--output-json",
        str(mi_trial_admission_decision_json),
        "--output-owner-progress",
        str(mi_trial_admission_decision_md),
    ]
    steps.append(
        _run_step(
            "mi_trial_admission_decision",
            mi_trial_admission_decision_command,
            mi_trial_admission_decision_json,
            runner,
        )
    )

    four_candidate_runtime_activation_closure_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_four_candidate_runtime_activation_closure.py"),
        "--replay-json",
        str(four_candidate_recent_live_submit_replay_json),
        "--cpm-required-facts-json",
        str(cpm_required_facts_mapping_json),
        "--cpm-capture-json",
        str(cpm_runtime_signal_capture_json),
        "--cpm-rehearsal-json",
        str(cpm_dry_run_submit_rehearsal_json),
        "--mpg-runtime-artifact-json",
        str(mpg_runtime_activation_evidence_json),
        "--sor-runtime-artifact-json",
        str(sor_runtime_activation_evidence_json),
        "--output-json",
        str(four_candidate_runtime_activation_closure_json),
        "--output-owner-progress",
        str(four_candidate_runtime_activation_closure_md),
    ]
    steps.append(
        _run_step(
            "four_candidate_runtime_activation_closure",
            four_candidate_runtime_activation_closure_command,
            four_candidate_runtime_activation_closure_json,
            runner,
        )
    )

    goal_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/run_strategygroup_runtime_goal_progress_audit.py"),
        "--owner-progress",
        "--strategygroup-portfolio-board-json",
        str(strategygroup_portfolio_board_json),
        "--strategygroup-capital-trial-envelope-projection-json",
        str(strategygroup_capital_trial_envelope_projection_json),
        "--output-json",
        str(goal_progress_json),
        "--output-owner-progress",
        str(goal_progress_md),
    ]
    steps.append(_run_step("goal_progress", goal_command, goal_progress_json, runner))

    completion_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/runtime_first_bounded_live_order_completion_audit.py"),
        "--owner-progress",
        "--dry-run-audit-json",
        str(dry_run_audit_json),
        "--output-json",
        str(completion_audit_json),
        "--output-owner-progress",
        str(completion_audit_md),
    ]
    steps.append(
        _run_step("completion_audit", completion_command, completion_audit_json, runner)
    )

    replay_lab_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/run_strategygroup_runtime_replay_lab.py"),
        "--output-json",
        str(replay_lab_json),
        "--output-owner-progress",
        str(replay_lab_md),
    ]
    steps.append(_run_step("replay_lab", replay_lab_command, replay_lab_json, runner))

    signal_coverage_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/run_strategygroup_signal_coverage_diagnostic.py"),
        "--source",
        signal_coverage_source,
        "--output-json",
        str(signal_coverage_json),
        "--output-owner-progress",
        str(signal_coverage_md),
    ]
    steps.append(
        _run_step(
            "signal_coverage",
            signal_coverage_command,
            signal_coverage_json,
            runner,
        )
    )

    signal_coverage_expansion_review_command = [
        sys.executable,
        str(
            REPO_ROOT
            / "scripts/build_strategygroup_signal_coverage_expansion_review.py"
        ),
        "--signal-coverage-json",
        str(signal_coverage_json),
        "--output-json",
        str(signal_coverage_expansion_review_json),
        "--output-owner-progress",
        str(signal_coverage_expansion_review_md),
    ]
    steps.append(
        _run_step(
            "signal_coverage_expansion_review",
            signal_coverage_expansion_review_command,
            signal_coverage_expansion_review_json,
            runner,
        )
    )

    l2_readiness_review_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_l2_readiness_review.py"),
        "--expansion-review-json",
        str(signal_coverage_expansion_review_json),
        "--output-json",
        str(l2_readiness_review_json),
        "--output-owner-progress",
        str(l2_readiness_review_md),
    ]
    steps.append(
        _run_step(
            "l2_readiness_review",
            l2_readiness_review_command,
            l2_readiness_review_json,
            runner,
        )
    )

    l2_intake_dry_run_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/run_strategygroup_l2_intake_dry_run.py"),
        "--l2-readiness-json",
        str(l2_readiness_review_json),
        "--output-json",
        str(l2_intake_dry_run_json),
        "--output-owner-progress",
        str(l2_intake_dry_run_md),
    ]
    steps.append(
        _run_step(
            "l2_intake_dry_run",
            l2_intake_dry_run_command,
            l2_intake_dry_run_json,
            runner,
        )
    )

    l2_tier_policy_review_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/run_strategygroup_l2_tier_policy_review.py"),
        "--l2-intake-dry-run-json",
        str(l2_intake_dry_run_json),
        "--output-json",
        str(l2_tier_policy_review_json),
        "--output-owner-progress",
        str(l2_tier_policy_review_md),
    ]
    steps.append(
        _run_step(
            "l2_tier_policy_review",
            l2_tier_policy_review_command,
            l2_tier_policy_review_json,
            runner,
        )
    )

    post_revision_replay_review_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_post_revision_replay_review.py"),
        "--output-json",
        str(post_revision_replay_review_json),
        "--output-owner-progress",
        str(post_revision_replay_review_md),
    ]
    steps.append(
        _run_step(
            "post_revision_replay_review",
            post_revision_replay_review_command,
            post_revision_replay_review_json,
            runner,
        )
    )

    opportunity_review_work_loop_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_opportunity_review_work_loop.py"),
        "--expansion-review-json",
        str(signal_coverage_expansion_review_json),
        "--l2-readiness-json",
        str(l2_readiness_review_json),
        "--l2-intake-json",
        str(l2_intake_dry_run_json),
        "--replay-lab-json",
        str(replay_lab_json),
        "--post-revision-review-json",
        str(post_revision_replay_review_json),
        "--output-json",
        str(opportunity_review_work_loop_json),
        "--output-owner-progress",
        str(opportunity_review_work_loop_md),
    ]
    steps.append(
        _run_step(
            "opportunity_review_work_loop",
            opportunity_review_work_loop_command,
            opportunity_review_work_loop_json,
            runner,
        )
    )

    btpc_l2_shadow_fact_quality_review_command = [
        sys.executable,
        str(
            REPO_ROOT
            / "scripts/build_strategygroup_btpc_l2_shadow_fact_quality_review.py"
        ),
        "--opportunity-review-work-loop-json",
        str(opportunity_review_work_loop_json),
        "--l2-readiness-json",
        str(l2_readiness_review_json),
        "--replay-lab-json",
        str(replay_lab_json),
        "--output-json",
        str(btpc_l2_shadow_fact_quality_review_json),
        "--output-owner-progress",
        str(btpc_l2_shadow_fact_quality_review_md),
    ]
    steps.append(
        _run_step(
            "btpc_l2_shadow_fact_quality_review",
            btpc_l2_shadow_fact_quality_review_command,
            btpc_l2_shadow_fact_quality_review_json,
            runner,
        )
    )

    btpc_local_fact_proxy_review_command = [
        sys.executable,
        str(
            REPO_ROOT
            / "scripts/build_strategygroup_btpc_local_fact_proxy_review.py"
        ),
        "--btpc-fact-quality-json",
        str(btpc_l2_shadow_fact_quality_review_json),
        "--output-json",
        str(btpc_local_fact_proxy_review_json),
        "--output-owner-progress",
        str(btpc_local_fact_proxy_review_md),
    ]
    steps.append(
        _run_step(
            "btpc_local_fact_proxy_review",
            btpc_local_fact_proxy_review_command,
            btpc_local_fact_proxy_review_json,
            runner,
        )
    )

    btpc_proxy_replay_quality_review_command = [
        sys.executable,
        str(
            REPO_ROOT
            / "scripts/build_strategygroup_btpc_proxy_replay_quality_review.py"
        ),
        "--btpc-local-fact-proxy-json",
        str(btpc_local_fact_proxy_review_json),
        "--output-json",
        str(btpc_proxy_replay_quality_review_json),
        "--output-owner-progress",
        str(btpc_proxy_replay_quality_review_md),
    ]
    steps.append(
        _run_step(
            "btpc_proxy_replay_quality_review",
            btpc_proxy_replay_quality_review_command,
            btpc_proxy_replay_quality_review_json,
            runner,
        )
    )

    opportunity_review_work_loop_final_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_opportunity_review_work_loop.py"),
        "--expansion-review-json",
        str(signal_coverage_expansion_review_json),
        "--l2-readiness-json",
        str(l2_readiness_review_json),
        "--l2-intake-json",
        str(l2_intake_dry_run_json),
        "--replay-lab-json",
        str(replay_lab_json),
        "--post-revision-review-json",
        str(post_revision_replay_review_json),
        "--btpc-proxy-replay-quality-json",
        str(btpc_proxy_replay_quality_review_json),
        "--output-json",
        str(opportunity_review_work_loop_json),
        "--output-owner-progress",
        str(opportunity_review_work_loop_md),
    ]
    steps.append(
        _run_step(
            "opportunity_review_work_loop_final",
            opportunity_review_work_loop_final_command,
            opportunity_review_work_loop_json,
            runner,
        )
    )

    btpc_l2_keep_revise_fact_source_review_command = [
        sys.executable,
        str(
            REPO_ROOT
            / "scripts/build_strategygroup_btpc_l2_keep_revise_fact_source_review.py"
        ),
        "--opportunity-review-work-loop-json",
        str(opportunity_review_work_loop_json),
        "--btpc-proxy-replay-quality-json",
        str(btpc_proxy_replay_quality_review_json),
        "--output-json",
        str(btpc_l2_keep_revise_fact_source_review_json),
        "--output-owner-progress",
        str(btpc_l2_keep_revise_fact_source_review_md),
    ]
    steps.append(
        _run_step(
            "btpc_l2_keep_revise_fact_source_review",
            btpc_l2_keep_revise_fact_source_review_command,
            btpc_l2_keep_revise_fact_source_review_json,
            runner,
        )
    )

    btpc_live_derivatives_fact_source_mapping_command = [
        sys.executable,
        str(
            REPO_ROOT
            / "scripts/build_strategygroup_btpc_live_derivatives_fact_source_mapping.py"
        ),
        "--btpc-l2-review-json",
        str(btpc_l2_keep_revise_fact_source_review_json),
        "--output-json",
        str(btpc_live_derivatives_fact_source_mapping_json),
        "--output-owner-progress",
        str(btpc_live_derivatives_fact_source_mapping_md),
    ]
    steps.append(
        _run_step(
            "btpc_live_derivatives_fact_source_mapping",
            btpc_live_derivatives_fact_source_mapping_command,
            btpc_live_derivatives_fact_source_mapping_json,
            runner,
        )
    )

    btpc_classifier_rule_review_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_btpc_classifier_rule_review.py"),
        "--btpc-l2-review-json",
        str(btpc_l2_keep_revise_fact_source_review_json),
        "--btpc-proxy-replay-quality-json",
        str(btpc_proxy_replay_quality_review_json),
        "--btpc-live-source-mapping-json",
        str(btpc_live_derivatives_fact_source_mapping_json),
        "--output-json",
        str(btpc_classifier_rule_review_json),
        "--output-owner-progress",
        str(btpc_classifier_rule_review_md),
    ]
    steps.append(
        _run_step(
            "btpc_classifier_rule_review",
            btpc_classifier_rule_review_command,
            btpc_classifier_rule_review_json,
            runner,
        )
    )

    strategy_asset_state_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_strategy_asset_state.py"),
        "--opportunity-review-work-loop-json",
        str(opportunity_review_work_loop_json),
        "--signal-coverage-json",
        str(signal_coverage_json),
        "--post-revision-replay-review-json",
        str(post_revision_replay_review_json),
        "--capture-gap-audit-json",
        str(strategy_capture_gap_audit_json),
        "--research-intake-review-json",
        str(strategygroup_research_intake_review_json),
        "--output-json",
        str(strategy_asset_state_json),
        "--output-owner-progress",
        str(strategy_asset_state_md),
    ]
    steps.append(
        _run_step(
            "strategy_asset_state",
            strategy_asset_state_command,
            strategy_asset_state_json,
            runner,
        )
    )

    strategygroup_quality_wave_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_quality_wave.py"),
        "--strategy-asset-state-json",
        str(strategy_asset_state_json),
        "--output-json",
        str(strategygroup_quality_wave_json),
        "--output-md",
        str(strategygroup_quality_wave_md),
    ]
    steps.append(
        _run_step(
            "strategygroup_quality_wave",
            strategygroup_quality_wave_command,
            strategygroup_quality_wave_json,
            runner,
        )
    )

    strategygroup_handoff_boundary_closure_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_handoff_boundary_closure.py"),
        "--quality-wave-json",
        str(strategygroup_quality_wave_json),
        "--output-json",
        str(strategygroup_handoff_boundary_closure_json),
        "--output-owner-progress",
        str(strategygroup_handoff_boundary_closure_md),
    ]
    steps.append(
        _run_step(
            "strategygroup_handoff_boundary_closure",
            strategygroup_handoff_boundary_closure_command,
            strategygroup_handoff_boundary_closure_json,
            runner,
        )
    )

    strategygroup_btpc_fact_classifier_guard_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_btpc_fact_classifier_guard.py"),
        "--btpc-l2-review-json",
        str(btpc_l2_keep_revise_fact_source_review_json),
        "--btpc-live-source-mapping-json",
        str(btpc_live_derivatives_fact_source_mapping_json),
        "--btpc-classifier-rule-review-json",
        str(btpc_classifier_rule_review_json),
        "--output-json",
        str(strategygroup_btpc_fact_classifier_guard_json),
        "--output-owner-progress",
        str(strategygroup_btpc_fact_classifier_guard_md),
    ]
    steps.append(
        _run_step(
            "strategygroup_btpc_fact_classifier_guard",
            strategygroup_btpc_fact_classifier_guard_command,
            strategygroup_btpc_fact_classifier_guard_json,
            runner,
        )
    )

    strategygroup_lifecycle_rehearsal_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_lifecycle_rehearsal.py"),
        "--output-json",
        str(strategygroup_lifecycle_rehearsal_json),
        "--output-owner-progress",
        str(strategygroup_lifecycle_rehearsal_md),
    ]
    steps.append(
        _run_step(
            "strategygroup_lifecycle_rehearsal",
            strategygroup_lifecycle_rehearsal_command,
            strategygroup_lifecycle_rehearsal_json,
            runner,
        )
    )

    strategygroup_pre_live_rehearsal_readiness_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_pre_live_rehearsal_readiness.py"),
        "--quality-wave-json",
        str(strategygroup_quality_wave_json),
        "--handoff-boundary-json",
        str(strategygroup_handoff_boundary_closure_json),
        "--btpc-guard-json",
        str(strategygroup_btpc_fact_classifier_guard_json),
        "--lifecycle-rehearsal-json",
        str(strategygroup_lifecycle_rehearsal_json),
        "--output-json",
        str(strategygroup_pre_live_rehearsal_readiness_json),
        "--output-owner-progress",
        str(strategygroup_pre_live_rehearsal_readiness_md),
    ]
    steps.append(
        _run_step(
            "strategygroup_pre_live_rehearsal_readiness",
            strategygroup_pre_live_rehearsal_readiness_command,
            strategygroup_pre_live_rehearsal_readiness_json,
            runner,
        )
    )

    strategygroup_runtime_safety_state_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_runtime_safety_state.py"),
        "--pre-live-readiness-json",
        str(strategygroup_pre_live_rehearsal_readiness_json),
        "--daily-check-json",
        str(daily_check_json),
        "--live-cutover-json",
        str(live_cutover_json),
        "--goal-progress-json",
        str(goal_progress_json),
        "--completion-audit-json",
        str(completion_audit_json),
        "--brf2-shadow-candidate-evidence-json",
        str(brf2_shadow_candidate_evidence_json),
        "--output-json",
        str(strategygroup_runtime_safety_state_json),
        "--output-owner-progress",
        str(strategygroup_runtime_safety_state_md),
    ]
    steps.append(
        _run_step(
            "strategygroup_runtime_safety_state",
            strategygroup_runtime_safety_state_command,
            strategygroup_runtime_safety_state_json,
            runner,
        )
    )

    strategygroup_trial_grade_signal_gate_audit_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_trial_grade_signal_gate_audit.py"),
        "--live-preview-json",
        str(REPO_ROOT / "output/runtime-monitor/latest-live-market-strategy-preview.json"),
        "--local-preview-json",
        str(REPO_ROOT / "output/runtime-monitor/latest-local-sqlite-strategy-preview.json"),
        "--brf2-policy-json",
        str(brf2_owner_trial_policy_scope_json),
        "--brf2-capture-json",
        str(brf2_runtime_signal_capture_json),
        "--three-strategy-portfolio-json",
        str(three_strategy_live_trial_portfolio_json),
        "--output-json",
        str(strategygroup_trial_grade_signal_gate_audit_json),
        "--output-owner-progress",
        str(strategygroup_trial_grade_signal_gate_audit_md),
    ]
    steps.append(
        _run_step(
            "strategygroup_trial_grade_signal_gate_audit",
            strategygroup_trial_grade_signal_gate_audit_command,
            strategygroup_trial_grade_signal_gate_audit_json,
            runner,
        )
    )

    three_strategy_live_trial_portfolio_command = [
        sys.executable,
        str(
            REPO_ROOT
            / "scripts/build_strategygroup_three_strategy_live_trial_portfolio.py"
        ),
        "--registry-json",
        str(
            REPO_ROOT
            / "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json"
        ),
        "--tier-policy-json",
        str(
            REPO_ROOT
            / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
        ),
        "--capital-trial-envelope-projection-json",
        str(strategygroup_capital_trial_envelope_projection_json),
        "--trial-asset-admission-proposal-json",
        str(strategygroup_trial_asset_admission_proposal_json),
        "--brf2-owner-trial-policy-scope-json",
        str(brf2_owner_trial_policy_scope_json),
        "--brf2-required-facts-mapping-json",
        str(brf2_required_facts_mapping_json),
        "--brf2-runtime-signal-capture-json",
        str(brf2_runtime_signal_capture_json),
        "--trial-grade-signal-gate-audit-json",
        str(strategygroup_trial_grade_signal_gate_audit_json),
        "--signal-coverage-json",
        str(signal_coverage_json),
        "--output-json",
        str(three_strategy_live_trial_portfolio_json),
        "--output-owner-progress",
        str(three_strategy_live_trial_portfolio_md),
    ]
    steps.append(
        _run_step(
            "three_strategy_live_trial_portfolio",
            three_strategy_live_trial_portfolio_command,
            three_strategy_live_trial_portfolio_json,
            runner,
        )
    )

    strategygroup_tradeability_decision_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_tradeability_decision.py"),
        "--capital-trial-envelope-projection-json",
        str(strategygroup_capital_trial_envelope_projection_json),
        "--registry-json",
        str(
            REPO_ROOT
            / "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json"
        ),
        "--tier-policy-json",
        str(
            REPO_ROOT
            / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
        ),
        "--signal-coverage-json",
        str(signal_coverage_json),
        "--runtime-safety-state-json",
        str(strategygroup_runtime_safety_state_json),
        "--trial-asset-admission-proposal-json",
        str(strategygroup_trial_asset_admission_proposal_json),
        "--brf2-owner-trial-policy-scope-json",
        str(brf2_owner_trial_policy_scope_json),
        "--cpm-identity-routing-decision-json",
        str(cpm_identity_routing_decision_json),
        "--cpm-owner-trial-policy-scope-json",
        str(cpm_owner_trial_policy_scope_json),
        "--cpm-required-facts-mapping-json",
        str(cpm_required_facts_mapping_json),
        "--cpm-runtime-signal-capture-json",
        str(cpm_runtime_signal_capture_json),
        "--cpm-shadow-candidate-evidence-json",
        str(cpm_shadow_candidate_evidence_json),
        "--cpm-dry-run-submit-rehearsal-json",
        str(cpm_dry_run_submit_rehearsal_json),
        "--three-strategy-live-trial-portfolio-json",
        str(three_strategy_live_trial_portfolio_json),
        "--brf2-runtime-signal-capture-json",
        str(brf2_runtime_signal_capture_json),
        "--brf2-shadow-candidate-evidence-json",
        str(brf2_shadow_candidate_evidence_json),
        "--trial-grade-signal-gate-audit-json",
        str(strategygroup_trial_grade_signal_gate_audit_json),
        "--replay-live-parity-audit-json",
        str(replay_live_parity_audit_json),
        "--mi-trial-admission-decision-json",
        str(mi_trial_admission_decision_json),
        "--strategy-fresh-signal-action-time-boundary-json",
        str(strategy_fresh_signal_action_time_boundary_json),
        "--output-json",
        str(strategygroup_tradeability_decision_json),
        "--output-owner-progress",
        str(strategygroup_tradeability_decision_md),
    ]
    steps.append(
        _run_step(
            "strategygroup_tradeability_decision",
            strategygroup_tradeability_decision_command,
            strategygroup_tradeability_decision_json,
            runner,
        )
    )

    daily_live_enablement_table_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_daily_live_enablement_table.py"),
        "--tradeability-json",
        str(strategygroup_tradeability_decision_json),
        "--replay-live-parity-json",
        str(replay_live_parity_audit_json),
        "--action-time-boundary-json",
        str(strategy_fresh_signal_action_time_boundary_json),
        "--mi-trial-admission-json",
        str(mi_trial_admission_decision_json),
        "--runtime-safety-json",
        str(strategygroup_runtime_safety_state_json),
        "--output-json",
        str(daily_live_enablement_table_json),
        "--output-owner-progress",
        str(daily_live_enablement_table_md),
    ]
    steps.append(
        _run_step(
            "daily_live_enablement_table",
            daily_live_enablement_table_command,
            daily_live_enablement_table_json,
            runner,
        )
    )

    validate_daily_live_enablement_table_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/validate_daily_live_enablement_table.py"),
        str(daily_live_enablement_table_json),
    ]
    steps.append(
        _run_step(
            "validate_daily_live_enablement_table",
            validate_daily_live_enablement_table_command,
            daily_live_enablement_table_json,
            runner,
        )
    )

    single_lane_task_packet_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_single_lane_task_packet.py"),
        "--daily-table-json",
        str(daily_live_enablement_table_json),
        "--output-json",
        str(single_lane_task_packet_json),
        "--output-owner-progress",
        str(single_lane_task_packet_md),
    ]
    steps.append(
        _run_step(
            "single_lane_task_packet",
            single_lane_task_packet_command,
            single_lane_task_packet_json,
            runner,
        )
    )

    validate_single_lane_task_packet_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/validate_single_lane_task_packet.py"),
        str(single_lane_task_packet_json),
    ]
    steps.append(
        _run_step(
            "validate_single_lane_task_packet",
            validate_single_lane_task_packet_command,
            single_lane_task_packet_json,
            runner,
        )
    )

    strategy_live_candidate_pool_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategy_live_candidate_pool.py"),
        "--daily-table-json",
        str(daily_live_enablement_table_json),
        "--tradeability-json",
        str(strategygroup_tradeability_decision_json),
        "--replay-live-parity-json",
        str(replay_live_parity_audit_json),
        "--action-time-boundary-json",
        str(strategy_fresh_signal_action_time_boundary_json),
        "--single-lane-task-packet-json",
        str(single_lane_task_packet_json),
        "--runtime-active-monitor-json",
        str(runtime_active_monitor_json),
        "--output-json",
        str(strategy_live_candidate_pool_json),
        "--output-owner-progress",
        str(strategy_live_candidate_pool_md),
    ]
    steps.append(
        _run_step(
            "strategy_live_candidate_pool",
            strategy_live_candidate_pool_command,
            strategy_live_candidate_pool_json,
            runner,
        )
    )

    validate_strategy_live_candidate_pool_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/validate_strategy_live_candidate_pool.py"),
        str(strategy_live_candidate_pool_json),
    ]
    steps.append(
        _run_step(
            "validate_strategy_live_candidate_pool",
            validate_strategy_live_candidate_pool_command,
            strategy_live_candidate_pool_json,
            runner,
        )
    )

    server_backed_daily_live_enablement_table_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_daily_live_enablement_table.py"),
        "--tradeability-json",
        str(strategygroup_tradeability_decision_json),
        "--replay-live-parity-json",
        str(replay_live_parity_audit_json),
        "--action-time-boundary-json",
        str(strategy_fresh_signal_action_time_boundary_json),
        "--mi-trial-admission-json",
        str(mi_trial_admission_decision_json),
        "--runtime-safety-json",
        str(strategygroup_runtime_safety_state_json),
        "--candidate-pool-json",
        str(strategy_live_candidate_pool_json),
        "--output-json",
        str(daily_live_enablement_table_json),
        "--output-owner-progress",
        str(daily_live_enablement_table_md),
    ]
    steps.append(
        _run_step(
            "daily_live_enablement_table",
            server_backed_daily_live_enablement_table_command,
            daily_live_enablement_table_json,
            runner,
        )
    )

    steps.append(
        _run_step(
            "validate_daily_live_enablement_table",
            validate_daily_live_enablement_table_command,
            daily_live_enablement_table_json,
            runner,
        )
    )

    steps.append(
        _run_step(
            "single_lane_task_packet",
            single_lane_task_packet_command,
            single_lane_task_packet_json,
            runner,
        )
    )

    steps.append(
        _run_step(
            "validate_single_lane_task_packet",
            validate_single_lane_task_packet_command,
            single_lane_task_packet_json,
            runner,
        )
    )

    artifacts = {
        step["name"]: step.get("artifact") if isinstance(step.get("artifact"), dict) else {}
        for step in steps
    }
    artifact_parent = four_candidate_runtime_activation_closure_json.parent
    artifacts["four_candidate_scope_review_decision"] = _read_json_if_exists(
        artifact_parent / DEFAULT_FOUR_CANDIDATE_SCOPE_REVIEW_DECISION_JSON.name
    )
    artifacts["cpm_fresh_signal_live_path_readiness"] = _read_json_if_exists(
        artifact_parent / DEFAULT_CPM_FRESH_SIGNAL_LIVE_PATH_READINESS_JSON.name
    )
    status = _sequence_status(steps=steps, artifacts=artifacts)
    interaction = _sequence_interaction(steps)
    execution_blockers = [
        f"{step['name']}:returncode:{step['returncode']}"
        for step in steps
        if int(step.get("returncode") or 0) not in (0,)
        and not _step_returncode_is_allowed_monitor_refresh(step, artifacts)
        and not _step_returncode_is_allowed_deployment_issue(step, artifacts)
        and not (
            step["name"] == "completion_audit"
            and _status(artifacts["completion_audit"]) == "needs_non_market_repair"
        )
    ]
    completion_non_market_gaps = list(
        artifacts["completion_audit"].get("non_market_gaps") or []
    )
    non_market_gaps = list(completion_non_market_gaps)
    expansion_review_resolved = _expansion_review_resolved(
        artifacts.get("l2_readiness_review", {}),
        artifacts.get("l2_tier_policy_review", {}),
        artifacts.get("opportunity_review_work_loop", {}),
    )
    signal_coverage_gap = _expansion_review_non_market_gap(
        artifacts.get("signal_coverage_expansion_review", {}),
        artifacts.get("l2_readiness_review", {}),
        artifacts.get("l2_intake_dry_run", {}),
        artifacts.get("l2_tier_policy_review", {}),
        artifacts.get("opportunity_review_work_loop", {}),
    )
    if signal_coverage_gap is None and not expansion_review_resolved:
        signal_coverage_gap = _signal_coverage_non_market_gap(
            artifacts.get("signal_coverage", {}),
        )
    if signal_coverage_gap:
        non_market_gaps.append(signal_coverage_gap)
    brf2_fact_input_gap = _brf2_fact_input_non_market_gap(
        artifacts.get("brf2_runtime_signal_facts", {}),
        artifacts.get("brf2_runtime_signal_capture", {}),
    )
    if brf2_fact_input_gap:
        non_market_gaps.append(brf2_fact_input_gap)
    owner_intervention_required = _sequence_owner_intervention_required(
        artifacts=artifacts,
        execution_blockers=execution_blockers,
        engineering_gaps=non_market_gaps,
    )

    monitor_projection = _sequence_monitor_projection(
        status=status,
        artifacts=artifacts,
        owner_intervention_required=owner_intervention_required,
    )
    monitor_status = monitor_projection.monitor_status
    runtime_status = monitor_projection.runtime_status
    owner_status = monitor_projection.owner_status
    monitor_refresh_reasons = monitor_projection.monitor_refresh_reasons
    owner_runtime_state = monitor_projection.owner_runtime_state
    monitor_refresh_needed = bool(owner_runtime_state["monitor_refresh_needed"])
    owner_runtime_issues = owner_runtime_issues_projection(
        blockers=execution_blockers,
        non_market_gaps=non_market_gaps,
        include_counts=True,
    )
    research_intake_summary = _sequence_research_intake_summary(
        artifacts.get("strategygroup_research_intake_review", {})
    )
    capital_trial_summary = _sequence_capital_trial_summary(
        artifacts.get("strategygroup_capital_trial_envelope_projection", {})
    )
    trial_admission_summary = _sequence_trial_admission_summary(
        artifacts.get("strategygroup_trial_asset_admission_proposal", {})
    )
    brf2_policy_summary = _sequence_brf2_owner_trial_policy_summary(
        artifacts.get("brf2_owner_trial_policy_scope", {})
    )
    brf2_required_facts_summary = _sequence_brf2_required_facts_mapping_summary(
        artifacts.get("brf2_required_facts_mapping", {})
    )
    brf2_runtime_signal_facts_summary = _sequence_brf2_runtime_signal_facts_summary(
        artifacts.get("brf2_runtime_signal_facts", {})
    )
    brf2_runtime_signal_capture_summary = _sequence_brf2_runtime_signal_capture_summary(
        artifacts.get("brf2_runtime_signal_capture", {})
    )
    brf2_shadow_candidate_evidence_summary = (
        _sequence_brf2_shadow_candidate_evidence_summary(
            artifacts.get("brf2_shadow_candidate_evidence", {})
        )
    )
    cpm_identity_routing_decision_summary = (
        _sequence_cpm_identity_routing_decision_summary(
            artifacts.get("cpm_identity_routing_decision", {})
        )
    )
    cpm_owner_trial_policy_summary = _sequence_cpm_owner_trial_policy_summary(
        artifacts.get("cpm_owner_trial_policy_scope", {})
    )
    cpm_required_facts_summary = _sequence_cpm_required_facts_mapping_summary(
        artifacts.get("cpm_required_facts_mapping", {})
    )
    cpm_runtime_signal_facts_summary = _sequence_cpm_runtime_signal_facts_summary(
        artifacts.get("cpm_runtime_signal_facts", {})
    )
    cpm_runtime_signal_capture_summary = _sequence_cpm_runtime_signal_capture_summary(
        artifacts.get("cpm_runtime_signal_capture", {})
    )
    cpm_shadow_candidate_evidence_summary = (
        _sequence_cpm_shadow_candidate_evidence_summary(
            artifacts.get("cpm_shadow_candidate_evidence", {})
        )
    )
    cpm_dry_run_submit_rehearsal_summary = (
        _sequence_cpm_dry_run_submit_rehearsal_summary(
            artifacts.get("cpm_dry_run_submit_rehearsal", {})
        )
    )
    four_candidate_runtime_activation_closure_summary = (
        _sequence_four_candidate_runtime_activation_closure_summary(
            artifacts.get("four_candidate_runtime_activation_closure", {})
        )
    )
    four_candidate_scope_review_decision_summary = (
        _sequence_four_candidate_scope_review_decision_summary(
            artifacts.get("four_candidate_scope_review_decision", {})
        )
    )
    cpm_fresh_signal_live_path_readiness_summary = (
        _sequence_cpm_fresh_signal_live_path_readiness_summary(
            artifacts.get("cpm_fresh_signal_live_path_readiness", {})
        )
    )
    strategy_fresh_signal_action_time_boundary_summary = (
        _sequence_strategy_fresh_signal_action_time_boundary_summary(
            artifacts.get("strategy_fresh_signal_action_time_boundary", {})
        )
    )
    replay_live_parity_audit_summary = _sequence_replay_live_parity_audit_summary(
        artifacts.get("replay_live_parity_audit", {})
    )
    mi_trial_admission_decision_summary = (
        _sequence_mi_trial_admission_decision_summary(
            artifacts.get("mi_trial_admission_decision", {})
        )
    )
    sor_session_detector_facts_summary = _sequence_sor_session_detector_facts_summary(
        artifacts.get("sor_session_scope_detector", {})
    )
    three_strategy_portfolio_summary = _sequence_three_strategy_portfolio_summary(
        artifacts.get("three_strategy_live_trial_portfolio", {})
    )
    trial_grade_signal_gate_audit_summary = (
        _sequence_trial_grade_signal_gate_audit_summary(
            artifacts.get("strategygroup_trial_grade_signal_gate_audit", {})
        )
    )
    signal_observation_grade_summary = _sequence_signal_observation_grade_summary(
        signal_coverage_artifact=artifacts.get("signal_coverage", {}),
        expansion_review_artifact=artifacts.get("signal_coverage_expansion_review", {}),
        strategy_asset_state_artifact=artifacts.get("strategy_asset_state", {}),
        capital_trial_summary=capital_trial_summary,
    )
    tradeability_summary = _sequence_tradeability_decision_summary(
        artifacts.get("strategygroup_tradeability_decision", {})
    )
    armed_trade_candidate_summary = _sequence_armed_trade_candidate_summary(
        three_strategy_portfolio_summary=three_strategy_portfolio_summary,
        tradeability_summary=tradeability_summary,
    )

    return {
        "schema": "brc.strategygroup_runtime_local_monitor_sequence.v1",
        "scope": "strategygroup_runtime_local_monitor_sequence",
        "status": status,
        "runtime_status": runtime_status,
        "monitor_status": monitor_status,
        "owner_status": owner_status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "daily_check_mode": daily_check_mode,
        "owner_runtime_state": owner_runtime_state,
        "owner_runtime_issues": owner_runtime_issues,
        "owner_summary": {
            "state": monitor_owner_state_label_for(
                status,
                local_labels=OWNER_PROGRESS_STATE_LABELS,
                default_label="需要修复",
            ),
            "non_authority_checkpoint": monitor_owner_action_label_for(
                status,
                local_labels=OWNER_PROGRESS_ACTION_LABELS,
                default_label="修复本地监控或非市场证据缺口",
            ),
            "checkpoint_source": "local_monitor_status_projection",
            "owner_intervention_required": owner_intervention_required,
            "risk_level": interaction["level"],
            "signal_observation_grade": signal_observation_grade_summary,
            "strategy_research_intake": research_intake_summary,
            "strategy_experiment_candidate": capital_trial_summary,
            "trial_asset_admission": trial_admission_summary,
            "brf2_owner_trial_policy": brf2_policy_summary,
            "brf2_runtime_signal_facts": brf2_runtime_signal_facts_summary,
            "brf2_runtime_signal_capture": brf2_runtime_signal_capture_summary,
            "brf2_shadow_candidate_evidence": (
                brf2_shadow_candidate_evidence_summary
            ),
            "cpm_identity_routing_decision": cpm_identity_routing_decision_summary,
            "cpm_owner_trial_policy": cpm_owner_trial_policy_summary,
            "cpm_required_facts_mapping": cpm_required_facts_summary,
            "cpm_runtime_signal_facts": cpm_runtime_signal_facts_summary,
            "cpm_runtime_signal_capture": cpm_runtime_signal_capture_summary,
            "cpm_shadow_candidate_evidence": (
                cpm_shadow_candidate_evidence_summary
            ),
            "cpm_dry_run_submit_rehearsal": cpm_dry_run_submit_rehearsal_summary,
            "four_candidate_runtime_activation_closure": (
                four_candidate_runtime_activation_closure_summary
            ),
            "four_candidate_scope_review_decision": (
                four_candidate_scope_review_decision_summary
            ),
            "cpm_fresh_signal_live_path_readiness": (
                cpm_fresh_signal_live_path_readiness_summary
            ),
            "strategy_fresh_signal_action_time_boundary": (
                strategy_fresh_signal_action_time_boundary_summary
            ),
            "replay_live_parity_audit": replay_live_parity_audit_summary,
            "mi_trial_admission_decision": mi_trial_admission_decision_summary,
            "sor_session_detector_facts": sor_session_detector_facts_summary,
            "three_strategy_live_trial_portfolio": three_strategy_portfolio_summary,
            "armed_trade_candidates": armed_trade_candidate_summary,
            "tradeability_decision": tradeability_summary,
            "trial_grade_signal_gate_audit": (
                trial_grade_signal_gate_audit_summary
            ),
        },
        "interaction": interaction,
        "notification": monitor_notification_projection(
            monitor_refresh_needed=monitor_refresh_needed,
            owner_notify=owner_intervention_required,
            owner_intervention_required=owner_intervention_required,
            monitor_refresh_reasons=monitor_refresh_reasons,
            include_monitor_refresh_fields=True,
        ),
        "signal_observation_grade": signal_observation_grade_summary,
        "strategy_research_intake": research_intake_summary,
        "strategy_experiment_candidate": capital_trial_summary,
        "strategy_trial_asset_admission": trial_admission_summary,
        "brf2_owner_trial_policy": brf2_policy_summary,
        "brf2_required_facts_mapping": brf2_required_facts_summary,
        "brf2_runtime_signal_facts": brf2_runtime_signal_facts_summary,
        "brf2_runtime_signal_capture": brf2_runtime_signal_capture_summary,
        "brf2_shadow_candidate_evidence": brf2_shadow_candidate_evidence_summary,
        "cpm_identity_routing_decision": cpm_identity_routing_decision_summary,
        "cpm_owner_trial_policy": cpm_owner_trial_policy_summary,
        "cpm_required_facts_mapping": cpm_required_facts_summary,
        "cpm_runtime_signal_facts": cpm_runtime_signal_facts_summary,
        "cpm_runtime_signal_capture": cpm_runtime_signal_capture_summary,
        "cpm_shadow_candidate_evidence": cpm_shadow_candidate_evidence_summary,
        "cpm_dry_run_submit_rehearsal": cpm_dry_run_submit_rehearsal_summary,
        "four_candidate_runtime_activation_closure": (
            four_candidate_runtime_activation_closure_summary
        ),
        "four_candidate_scope_review_decision": (
            four_candidate_scope_review_decision_summary
        ),
        "cpm_fresh_signal_live_path_readiness": (
            cpm_fresh_signal_live_path_readiness_summary
        ),
        "strategy_fresh_signal_action_time_boundary": (
            strategy_fresh_signal_action_time_boundary_summary
        ),
        "replay_live_parity_audit": replay_live_parity_audit_summary,
        "mi_trial_admission_decision": mi_trial_admission_decision_summary,
        "sor_session_detector_facts": sor_session_detector_facts_summary,
        "three_strategy_live_trial_portfolio": three_strategy_portfolio_summary,
        "armed_trade_candidates": armed_trade_candidate_summary,
        "tradeability_decision": tradeability_summary,
        "strategy_trial_grade_signal_gate_audit": (
            trial_grade_signal_gate_audit_summary
        ),
        "steps": [
            {
                "name": step["name"],
                "returncode": step["returncode"],
                "status": _status(step.get("artifact")),
                "output_json": step["output_json"],
                "interaction": _interaction(step.get("artifact")),
            }
            for step in steps
        ],
        "source_paths": {
            "daily_check_json": str(daily_check_json),
            "dry_run_audit_json": str(dry_run_audit_json),
            "live_cutover_json": str(live_cutover_json),
            "goal_progress_json": str(goal_progress_json),
            "completion_audit_json": str(completion_audit_json),
            "replay_lab_json": str(replay_lab_json),
            "signal_coverage_json": str(signal_coverage_json),
            "signal_coverage_expansion_review_json": str(
                signal_coverage_expansion_review_json
            ),
            "l2_readiness_review_json": str(l2_readiness_review_json),
            "l2_intake_dry_run_json": str(l2_intake_dry_run_json),
            "l2_tier_policy_review_json": str(l2_tier_policy_review_json),
            "post_revision_replay_review_json": str(
                post_revision_replay_review_json
            ),
            "opportunity_review_work_loop_json": str(opportunity_review_work_loop_json),
            "btpc_l2_shadow_fact_quality_review_json": str(
                btpc_l2_shadow_fact_quality_review_json
            ),
            "btpc_local_fact_proxy_review_json": str(btpc_local_fact_proxy_review_json),
            "btpc_proxy_replay_quality_review_json": str(
                btpc_proxy_replay_quality_review_json
            ),
            "btpc_l2_keep_revise_fact_source_review_json": str(
                btpc_l2_keep_revise_fact_source_review_json
            ),
            "btpc_live_derivatives_fact_source_mapping_json": str(
                btpc_live_derivatives_fact_source_mapping_json
            ),
            "btpc_classifier_rule_review_json": str(btpc_classifier_rule_review_json),
            "strategy_asset_state_json": str(
                strategy_asset_state_json
            ),
            "strategygroup_quality_wave_json": str(strategygroup_quality_wave_json),
            "strategygroup_handoff_boundary_closure_json": str(
                strategygroup_handoff_boundary_closure_json
            ),
            "strategygroup_btpc_fact_classifier_guard_json": str(
                strategygroup_btpc_fact_classifier_guard_json
            ),
            "strategygroup_lifecycle_rehearsal_json": str(
                strategygroup_lifecycle_rehearsal_json
            ),
            "strategygroup_pre_live_rehearsal_readiness_json": str(
                strategygroup_pre_live_rehearsal_readiness_json
            ),
            "strategygroup_runtime_safety_state_json": str(
                strategygroup_runtime_safety_state_json
            ),
            "daily_live_enablement_table_json": str(daily_live_enablement_table_json),
            "single_lane_task_packet_json": str(single_lane_task_packet_json),
            "strategy_live_candidate_pool_json": str(strategy_live_candidate_pool_json),
            "strategygroup_portfolio_board_json": str(strategygroup_portfolio_board_json),
            "strategygroup_review_only_deep_dive_wave_json": str(
                strategygroup_review_only_deep_dive_wave_json
            ),
            "strategygroup_owner_policy_package_json": str(
                strategygroup_owner_policy_package_json
            ),
            "strategygroup_quality_closure_wave_json": str(
                strategygroup_quality_closure_wave_json
            ),
            "strategygroup_capital_trial_envelope_projection_json": str(
                strategygroup_capital_trial_envelope_projection_json
            ),
            "strategygroup_capital_trial_envelope_json": str(
                strategygroup_capital_trial_envelope_json
            ),
            "strategygroup_research_intake_review_json": str(
                strategygroup_research_intake_review_json
            ),
            "strategygroup_trial_asset_admission_proposal_json": str(
                strategygroup_trial_asset_admission_proposal_json
            ),
            "brf2_required_facts_mapping_json": str(brf2_required_facts_mapping_json),
            "brf2_runtime_signal_facts_json": str(brf2_runtime_signal_facts_json),
            "brf2_runtime_signal_capture_json": str(
                brf2_runtime_signal_capture_json
            ),
            "brf2_shadow_candidate_evidence_json": str(
                brf2_shadow_candidate_evidence_json
            ),
            "cpm_identity_routing_decision_json": str(
                cpm_identity_routing_decision_json
            ),
            "cpm_owner_trial_policy_scope_json": str(
                cpm_owner_trial_policy_scope_json
            ),
            "cpm_required_facts_mapping_json": str(cpm_required_facts_mapping_json),
            "cpm_runtime_signal_facts_json": str(cpm_runtime_signal_facts_json),
            "cpm_runtime_signal_capture_json": str(cpm_runtime_signal_capture_json),
            "cpm_shadow_candidate_evidence_json": str(
                cpm_shadow_candidate_evidence_json
            ),
            "cpm_dry_run_submit_rehearsal_json": str(
                cpm_dry_run_submit_rehearsal_json
            ),
            "strategygroup_trial_grade_signal_gate_audit_json": str(
                strategygroup_trial_grade_signal_gate_audit_json
            ),
            "strategygroup_tradeability_decision_json": str(
                strategygroup_tradeability_decision_json
            ),
        },
    }


def _daily_check_command(
    *,
    mode: str,
    output_json: Path,
    output_owner_progress: Path,
) -> list[str]:
    if mode not in {"cache", "auto-cache", "artifact"}:
        raise ValueError(f"unsupported daily_check_mode: {mode}")
    if mode == "cache":
        mode_args = ["--from-cache", "--require-fresh-cache"]
    elif mode == "artifact":
        mode_args = ["--report-json-path", str(output_json)]
    else:
        mode_args = [
            "--auto-cache",
            "--snapshot-host",
            _default_snapshot_host_for_repo(),
        ]
    return [
        sys.executable,
        str(REPO_ROOT / "scripts/run_strategygroup_runtime_daily_check.py"),
        *mode_args,
        "--json",
        "--output-json",
        str(output_json),
        "--output-owner-progress",
        str(output_owner_progress),
    ]


def _run_step(
    name: str,
    command: list[str],
    output_json: Path,
    runner: CommandRunner,
) -> dict[str, Any]:
    completed = runner(command)
    artifact = _read_json_if_exists(output_json)
    return {
        "name": name,
        "command": _display_command(command),
        "returncode": int(completed.returncode),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "output_json": str(output_json),
        "artifact": artifact,
    }


def _default_snapshot_host_for_repo() -> str:
    repo_path = str(REPO_ROOT)
    return "local" if repo_path.startswith("/home/ubuntu/brc-deploy/") else "tokyo"


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _sequence_artifacts(
    *,
    artifacts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    return artifacts or {}


def _sequence_status(
    *,
    steps: list[dict[str, Any]],
    artifacts: dict[str, dict[str, Any]] | None = None,
) -> str:
    artifacts = _sequence_artifacts(artifacts=artifacts)
    if artifact_monitor_status(artifacts["daily_check"]) == "deployment_issue" or (
        artifact_monitor_status(artifacts["goal_progress"]) == "deployment_issue"
    ):
        return DEPLOYMENT_ISSUE_STATUS
    failed_steps = [
        step
        for step in steps
        if int(step.get("returncode") or 0) != 0
        and not _step_returncode_is_allowed_monitor_refresh(step, artifacts)
        and not _step_returncode_is_allowed_deployment_issue(step, artifacts)
        and not (
            step["name"] == "completion_audit"
            and _status(artifacts["completion_audit"]) == "needs_non_market_repair"
        )
    ]
    if failed_steps:
        return "needs_non_market_repair"
    if _binance_usdm_public_facts_refresh_needed(
        artifacts.get("binance_usdm_public_facts", {})
    ):
        return "temporarily_unavailable_monitor_refresh_needed"
    completion_status = _status(artifacts["completion_audit"])
    if completion_status == "needs_non_market_repair":
        return "needs_non_market_repair"
    if _brf2_fact_input_non_market_gap(
        artifacts.get("brf2_runtime_signal_facts", {}),
        artifacts.get("brf2_runtime_signal_capture", {}),
    ):
        return "needs_non_market_repair"
    if _sequence_has_processing_signal(artifacts=artifacts):
        return "processing"
    refresh_status = monitor_refresh_sequence_status(
        [artifacts["daily_check"], artifacts["goal_progress"]]
    )
    if refresh_status:
        return refresh_status

    if completion_status in {"complete", "completed"}:
        return "complete"
    l2_readiness_status = _status(artifacts.get("l2_readiness_review"))
    l2_dry_run_status = _status(artifacts.get("l2_intake_dry_run"))
    l2_tier_status = _status(artifacts.get("l2_tier_policy_review"))
    l2_tier_review_clears_expansion = l2_tier_status in {
        "l2_tier_policy_review_applied",
    } or l2_readiness_status == "l2_readiness_review_already_enabled"
    expansion_review_clears_expansion = (
        l2_tier_review_clears_expansion
        or _opportunity_review_work_loop_clears_expansion(
            artifacts.get("opportunity_review_work_loop", {}),
            l2_readiness_status=l2_readiness_status,
            l2_dry_run_status=l2_dry_run_status,
            l2_tier_status=l2_tier_status,
        )
    )
    signal_coverage_status = _status(artifacts.get("signal_coverage"))
    if signal_coverage_status == "mainline_runtime_signal_ready":
        return "processing"
    if signal_coverage_status in {
        "blocked_forbidden_effect",
        "broader_preview_invalid_needs_review",
    } or (
        signal_coverage_status == "mainline_no_signal_broader_would_enter"
        and not expansion_review_clears_expansion
    ):
        return "needs_non_market_repair"
    expansion_review_status = _status(artifacts.get("signal_coverage_expansion_review"))
    if expansion_review_status in {
        "blocked_forbidden_effect",
    } or (
        expansion_review_status == "review_needed_broader_observe_only_would_enter"
        and not expansion_review_clears_expansion
    ):
        return "needs_non_market_repair"
    if l2_readiness_status in {
        "blocked_forbidden_effect",
    } or (
        l2_readiness_status == "l2_readiness_review_has_conditional_candidate"
        and not l2_tier_review_clears_expansion
    ):
        return "needs_non_market_repair"
    if l2_dry_run_status in {
        "blocked_forbidden_effect",
        "l2_intake_dry_run_failed",
    } or (
        l2_dry_run_status == "l2_intake_dry_run_passed"
        and not l2_tier_review_clears_expansion
    ):
        return "needs_non_market_repair"
    if l2_tier_status in {
        "blocked_forbidden_effect",
        "l2_tier_policy_review_failed",
        "l2_tier_policy_review_recommended",
    }:
        return "needs_non_market_repair"
    if (
        artifact_declared_runtime_status(artifacts["daily_check"])
        == "waiting_for_market"
        and artifact_declared_runtime_status(artifacts["goal_progress"])
        == "waiting_for_market"
        and completion_status == "not_complete_waiting_for_market"
    ):
        return "waiting_for_market"
    if artifact_declared_runtime_status(artifacts["daily_check"]) == "processing" or (
        artifact_declared_runtime_status(artifacts["goal_progress"]) == "processing"
    ):
        return "processing"
    return "needs_non_market_repair"


def _sequence_has_processing_signal(
    *,
    artifacts: dict[str, dict[str, Any]] | None = None,
) -> bool:
    artifacts = _sequence_artifacts(artifacts=artifacts)
    if artifact_declared_runtime_status(artifacts.get("daily_check", {})) == "processing":
        return True
    if artifact_declared_runtime_status(artifacts.get("goal_progress", {})) == "processing":
        return True
    if _status(artifacts.get("completion_audit")) == "not_complete_runtime_processing":
        return True
    if _status(artifacts.get("signal_coverage")) == "mainline_runtime_signal_ready":
        return True
    return False


def _step_returncode_is_allowed_monitor_refresh(
    step: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
) -> bool:
    step_name = str(step.get("name") or "")
    if (
        step_name == "binance_usdm_public_facts"
        and int(step.get("returncode") or 0) != 0
    ):
        return _binance_usdm_public_facts_refresh_needed(
            artifacts.get(step_name, {})
        )
    if (
        step_name == "four_candidate_runtime_activation_evidence"
        and int(step.get("returncode") or 0) != 0
    ):
        return _runtime_activation_evidence_refresh_needed(
            artifacts.get(step_name, {})
        )
    return monitor_step_returncode_is_refresh(
        step_name=step_name,
        returncode=int(step.get("returncode") or 0),
        artifact=artifacts.get(step_name, {}),
    )


def _step_returncode_is_allowed_deployment_issue(
    step: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
) -> bool:
    step_name = str(step.get("name") or "")
    return monitor_step_returncode_is_deployment_issue(
        step_name=step_name,
        returncode=int(step.get("returncode") or 0),
        artifact=artifacts.get(step_name, {}),
    )


def _binance_usdm_public_facts_refresh_needed(artifact: dict[str, Any]) -> bool:
    if not isinstance(artifact, dict):
        return False
    if _status(artifact) == "binance_usdm_public_facts_unavailable":
        return True
    checks = _as_dict(artifact.get("checks"))
    if "public_facts_ready" in checks and checks.get("public_facts_ready") is not True:
        return True
    summary = _as_dict(artifact.get("summary"))
    if summary.get("symbol_count") and summary.get("ready_symbol_count") != summary.get(
        "symbol_count"
    ):
        return True
    return False


def _runtime_activation_evidence_refresh_needed(artifact: dict[str, Any]) -> bool:
    if not isinstance(artifact, dict):
        return False
    if _status(artifact) == "runtime_activation_evidence_public_facts_unavailable":
        return True
    checks = _as_dict(artifact.get("checks"))
    return checks.get("public_facts_artifact_fresh") is False


def _signal_coverage_non_market_gap(artifact: dict[str, Any]) -> dict[str, Any] | None:
    status = _status(artifact)
    if status == "mainline_no_signal_broader_would_enter":
        return {
            "source": "signal_coverage",
            "requirement": "mainline runtime coverage should not miss broad observe-only opportunities silently",
            "missing_or_false": [
                "mainline_no_signal_but_broader_would_enter_observed"
            ],
        }
    if status == "broader_preview_invalid_needs_review":
        return {
            "source": "signal_coverage",
            "requirement": "broader preview signals must satisfy the signal contract",
            "missing_or_false": ["broader_preview_invalid_signal"],
        }
    if status == "blocked_forbidden_effect":
        return {
            "source": "signal_coverage",
            "requirement": "signal coverage diagnostic must stay non-executing",
            "missing_or_false": ["signal_coverage_forbidden_effect"],
        }
    return None


def _brf2_fact_input_non_market_gap(
    facts_artifact: dict[str, Any],
    capture_artifact: dict[str, Any],
) -> dict[str, Any] | None:
    facts_missing = (
        _status(facts_artifact) == "brf2_runtime_signal_facts_missing_watcher_input"
        or facts_artifact.get("fact_input_present") is False
    )
    capture_preview = _as_dict(capture_artifact.get("signal_detector_preview"))
    capture_missing = (
        str(capture_preview.get("current_signal_state") or "") == "fact_input_missing"
        or str(capture_preview.get("first_blocker_class") or "")
        == "brf2_watcher_fact_input_missing"
    )
    if not facts_missing and not capture_missing:
        return None
    return {
        "class": "missing_fact",
        "source": "brf2_runtime_signal_facts",
        "strategy_group_id": "BRF2-001",
        "gap": "brf2_watcher_fact_input_missing",
        "owner": "engineering",
        "next_engineering_checkpoint": "attach_brf2_watcher_fact_input_producer",
        "requirement": "BRF2 armed observation must have watcher fact input before it can be classified as market wait",
        "missing_or_false": [
            "brf2_runtime_signal_fact_input_present",
            "brf2_runtime_signal_watcher_tick_present",
        ],
    }


def _expansion_review_resolved(
    l2_artifact: dict[str, Any],
    l2_tier_policy_artifact: dict[str, Any],
    opportunity_review_work_loop_artifact: dict[str, Any] | None = None,
) -> bool:
    return _status(l2_artifact) == "l2_readiness_review_already_enabled" or _status(
        l2_tier_policy_artifact
    ) == "l2_tier_policy_review_applied" or _opportunity_review_work_loop_clears_expansion(
        opportunity_review_work_loop_artifact or {},
        l2_readiness_status=_status(l2_artifact),
        l2_dry_run_status="",
        l2_tier_status=_status(l2_tier_policy_artifact),
    )


def _opportunity_review_work_loop_clears_expansion(
    artifact: dict[str, Any],
    *,
    l2_readiness_status: str,
    l2_dry_run_status: str,
    l2_tier_status: str,
) -> bool:
    if _status(artifact) != "review_work_loop_ready":
        return False
    if l2_tier_status in {
        "blocked_forbidden_effect",
        "l2_tier_policy_review_failed",
        "l2_tier_policy_review_recommended",
    }:
        return False
    if l2_dry_run_status in {
        "blocked_forbidden_effect",
        "l2_intake_dry_run_failed",
        "l2_intake_dry_run_passed",
    }:
        return False
    if l2_readiness_status in {
        "blocked_forbidden_effect",
        "l2_readiness_review_has_conditional_candidate",
    }:
        return False
    return True


def _expansion_review_non_market_gap(
    artifact: dict[str, Any],
    l2_artifact: dict[str, Any] | None = None,
    l2_dry_run_artifact: dict[str, Any] | None = None,
    l2_tier_policy_artifact: dict[str, Any] | None = None,
    opportunity_review_work_loop_artifact: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    l2_artifact = l2_artifact or {}
    l2_dry_run_artifact = l2_dry_run_artifact or {}
    l2_tier_policy_artifact = l2_tier_policy_artifact or {}
    opportunity_review_work_loop_artifact = opportunity_review_work_loop_artifact or {}
    if _status(l2_artifact) == "l2_readiness_review_already_enabled":
        return None
    l2_tier_status = _status(l2_tier_policy_artifact)
    if l2_tier_status == "l2_tier_policy_review_applied":
        return None
    if l2_tier_status == "l2_tier_policy_review_recommended":
        groups = review_outcome_string_list(
            l2_tier_policy_artifact,
            "groups_ready_to_apply_l2",
        )
        return {
            "source": "l2_tier_policy_review",
            "requirement": "conditional L2 tier policy review recommends a local policy update before the broader opportunity is considered covered",
            "missing_or_false": [
                "conditional_l2_tier_policy_update_needed",
                f"groups:{','.join(groups) if groups else 'none'}",
            ],
        }
    if l2_tier_status in {
        "blocked_forbidden_effect",
        "l2_tier_policy_review_failed",
    }:
        return {
            "source": "l2_tier_policy_review",
            "requirement": "conditional L2 tier policy review must pass without dangerous effects",
            "missing_or_false": [f"l2_tier_policy_review_status:{l2_tier_status}"],
    }
    l2_dry_run_status = _status(l2_dry_run_artifact)
    if l2_dry_run_status == "l2_intake_dry_run_passed":
        groups = review_outcome_string_list(
            l2_dry_run_artifact,
            "groups_ready_for_l2_policy_review",
        )
        return {
            "source": "l2_intake_dry_run",
            "requirement": "conditional L2 candidate dry-run passed and needs tier-policy review before any L2 policy change",
            "missing_or_false": [
                "conditional_l2_tier_policy_review_ready",
                f"groups:{','.join(groups) if groups else 'none'}",
            ],
        }
    if l2_dry_run_status in {
        "blocked_forbidden_effect",
        "l2_intake_dry_run_failed",
    }:
        return {
            "source": "l2_intake_dry_run",
            "requirement": "conditional L2 intake dry-run must pass without dangerous effects",
            "missing_or_false": [f"l2_intake_dry_run_status:{l2_dry_run_status}"],
    }
    l2_status = _status(l2_artifact)
    if l2_status == "l2_readiness_review_has_conditional_candidate":
        groups = review_outcome_string_list(
            l2_artifact,
            "handoff_intake_recommended_groups",
        )
        default_next_step = review_outcome_default_next_step(l2_artifact)
        needs_dry_run = default_next_step == "run_conditional_l2_dry_run_without_tier_change"
        return {
            "source": "l2_readiness_review",
            "requirement": (
                "conditional L2 candidates should run non-executing dry-run before any tier policy change"
                if needs_dry_run
                else "conditional L2 candidates should enter handoff intake and dry-run before any tier policy change"
            ),
            "missing_or_false": [
                (
                    "conditional_l2_dry_run_needed"
                    if needs_dry_run
                    else "conditional_l2_handoff_intake_needed"
                ),
                f"groups:{','.join(groups) if groups else 'none'}",
            ],
        }
    if l2_status == "blocked_forbidden_effect":
        return {
            "source": "l2_readiness_review",
            "requirement": "L2 readiness review must stay non-executing",
            "missing_or_false": ["l2_readiness_review_forbidden_effect"],
        }
    if _opportunity_review_work_loop_clears_expansion(
        opportunity_review_work_loop_artifact,
        l2_readiness_status=l2_status,
        l2_dry_run_status=l2_dry_run_status,
        l2_tier_status=l2_tier_status,
    ):
        return None
    status = _status(artifact)
    if status == "review_needed_broader_observe_only_would_enter":
        counts = artifact.get("counts") if isinstance(artifact.get("counts"), dict) else {}
        return {
            "source": "signal_coverage_expansion_review",
            "requirement": "broader observe-only opportunities should be reviewed for observation-scope expansion",
            "missing_or_false": [
                "observation_scope_expansion_review_needed",
                f"review_row_count:{_int(counts.get('review_row_count'))}",
            ],
        }
    if status == "blocked_forbidden_effect":
        return {
            "source": "signal_coverage_expansion_review",
            "requirement": "signal coverage expansion review must stay non-executing",
            "missing_or_false": ["signal_coverage_expansion_review_forbidden_effect"],
        }
    return None


def _sequence_interaction(steps: list[dict[str, Any]]) -> dict[str, Any]:
    remote_count = 0
    mutates_remote = False
    approaches_real_order = False
    calls_finalgate = False
    calls_operation_layer = False
    calls_exchange_write = False
    places_order = False
    for step in steps:
        interaction = _interaction(step.get("artifact"))
        remote_count += _int(interaction.get("remote_interaction_count"))
        mutates_remote = mutates_remote or interaction.get("mutates_remote_files") is True
        approaches_real_order = (
            approaches_real_order or interaction.get("approaches_real_order") is True
        )
        calls_finalgate = calls_finalgate or interaction.get("calls_finalgate") is True
        calls_operation_layer = (
            calls_operation_layer or interaction.get("calls_operation_layer") is True
        )
        calls_exchange_write = (
            calls_exchange_write or interaction.get("calls_exchange_write") is True
        )
        places_order = places_order or interaction.get("places_order") is True
    return {
        "level": "L1_local_monitor_sequence_with_auto_cache"
        if remote_count
        else "L0_local_monitor_sequence",
        "remote_interaction_count": remote_count,
        "mutates_remote_files": mutates_remote,
        "approaches_real_order": approaches_real_order,
        "calls_finalgate": calls_finalgate,
        "calls_operation_layer": calls_operation_layer,
        "calls_exchange_write": calls_exchange_write,
        "places_order": places_order,
    }


def _sequence_monitor_status(
    *,
    status: str,
    artifacts: dict[str, dict[str, Any]] | None = None,
) -> str:
    return _sequence_monitor_projection(
        status=status,
        artifacts=artifacts,
        owner_intervention_required=False,
    ).monitor_status


def _sequence_runtime_status(
    *,
    status: str,
    artifacts: dict[str, dict[str, Any]] | None = None,
) -> str:
    return _sequence_monitor_projection(
        status=status,
        artifacts=artifacts,
        owner_intervention_required=False,
    ).runtime_status


def _sequence_monitor_projection(
    *,
    status: str,
    artifacts: dict[str, dict[str, Any]] | None = None,
    owner_intervention_required: bool,
):
    artifacts = _sequence_artifacts(artifacts=artifacts)
    source_artifacts = [
        artifacts.get("daily_check", {}),
        artifacts.get("goal_progress", {}),
    ]
    runtime_status = first_artifact_declared_runtime_status(source_artifacts) or None
    return monitor_status_projection(
        status=status,
        artifacts=source_artifacts,
        runtime_status=runtime_status,
        owner_intervention_required=owner_intervention_required,
        waiting_for_market=runtime_status == "waiting_for_market"
        if runtime_status
        else None,
        default_runtime_status="temporarily_unavailable",
        default_monitor_status="unknown",
    )


def _sequence_owner_intervention_required(
    *,
    artifacts: dict[str, dict[str, Any]] | None = None,
    execution_blockers: list[str],
    engineering_gaps: list[dict[str, Any]],
) -> bool:
    artifacts = _sequence_artifacts(artifacts=artifacts)
    return owner_intervention_required_from_sources(
        artifacts=artifacts.values(),
        execution_blockers=execution_blockers,
        engineering_gaps=engineering_gaps,
    )


def _sequence_monitor_refresh_reasons(
    artifacts: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    artifacts = _sequence_artifacts(artifacts=artifacts)
    return combined_artifact_monitor_refresh_reasons(
        [artifacts.get("daily_check", {}), artifacts.get("goal_progress", {})]
    )


def _sequence_research_intake_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    summary = (
        artifact.get("summary") if isinstance(artifact.get("summary"), dict) else {}
    )
    rows = (
        artifact.get("candidate_rows")
        if isinstance(artifact.get("candidate_rows"), list)
        else []
    )
    strategy_group_ids = [
        str(row.get("strategy_group_id"))
        for row in rows
        if isinstance(row, dict) and row.get("strategy_group_id")
    ]
    return {
        "status": _status(artifact) or "missing",
        "active": _status(artifact) == "research_intake_review_ready",
        "candidate_count": _int(summary.get("candidate_count")),
        "paper_observation_admission_candidate_count": _int(
            summary.get("paper_observation_admission_candidate_count")
        ),
        "role_only_intake_candidate_count": _int(
            summary.get("role_only_intake_candidate_count")
        ),
        "strategy_group_ids": strategy_group_ids,
        "live_permission_change": False,
    }


@dataclass(frozen=True)
class _CapitalTrialSummaryProjection:
    status: str
    projection_status: str
    projection_schema: str
    active: bool
    selected_strategy_group_id: str
    selected_short_strategy_group_id: str
    selected_candidate_status: str
    strategy_asset_current_decision: str
    reason: str
    promotion_scope: str
    promotion_target: str
    next_checkpoint: str
    side_scope: list[str]
    short_experiment_candidate_count: int
    trial_envelope_generated: bool
    state_source: str = "capital_trial_envelope_projection"
    projection_role: str = "trial_envelope_compatibility_projection"
    primary_judgment_source: bool = False
    strategygroup_lifecycle_owner: bool = False
    tradeability_decision_source: bool = False
    runtime_truth_source: bool = False
    live_permission_change: bool = False

    @classmethod
    def from_artifact(
        cls, artifact: dict[str, Any]
    ) -> "_CapitalTrialSummaryProjection":
        status = _status(artifact) or "missing"
        summary = _as_dict(artifact.get("capital_trial_summary"))
        selected = _as_dict(artifact.get("selected_non_mpg_trial_candidate"))
        metadata = _as_dict(artifact.get("projection_metadata"))
        return cls(
            status=status,
            projection_status=str(
                artifact.get("projection_status") or "missing"
            ),
            projection_schema=str(artifact.get("projection_schema") or ""),
            active=artifact.get("projection_status")
            == "trial_envelope_projection_ready",
            selected_strategy_group_id=str(
                summary.get("selected_non_mpg_strategy_group_id") or ""
            ),
            selected_short_strategy_group_id=str(
                summary.get("selected_short_strategy_group_id") or ""
            ),
            selected_candidate_status=str(
                summary.get("selected_candidate_status") or "missing"
            ),
            strategy_asset_current_decision=str(
                selected.get("strategy_asset_current_decision") or "pending"
            ),
            reason=str(selected.get("reason") or ""),
            promotion_scope=str(
                selected.get("promotion_scope") or "not_applicable"
            ),
            promotion_target=str(
                selected.get("promotion_target") or "not_applicable"
            ),
            next_checkpoint=str(selected.get("next_checkpoint") or ""),
            side_scope=[
                str(item) for item in selected.get("side_scope") or [] if str(item)
            ],
            short_experiment_candidate_count=_coalesce_int(
                summary.get("short_experiment_candidate_count")
            ),
            trial_envelope_generated=summary.get("trial_envelope_generated") is True,
            strategygroup_lifecycle_owner=(
                metadata.get("strategygroup_lifecycle_owner") is True
            ),
            tradeability_decision_source=(
                metadata.get("tradeability_decision_source") is True
            ),
            runtime_truth_source=metadata.get("runtime_truth_source") is True,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "projection_status": self.projection_status,
            "projection_schema": self.projection_schema,
            "active": self.active,
            "selected_strategy_group_id": self.selected_strategy_group_id,
            "selected_short_strategy_group_id": self.selected_short_strategy_group_id,
            "selected_candidate_status": self.selected_candidate_status,
            "strategy_asset_current_decision": self.strategy_asset_current_decision,
            "reason": self.reason,
            "promotion_scope": self.promotion_scope,
            "promotion_target": self.promotion_target,
            "next_checkpoint": self.next_checkpoint,
            "side_scope": self.side_scope,
            "short_experiment_candidate_count": (
                self.short_experiment_candidate_count
            ),
            "trial_envelope_generated": self.trial_envelope_generated,
            "state_source": self.state_source,
            "projection_role": self.projection_role,
            "primary_judgment_source": self.primary_judgment_source,
            "strategygroup_lifecycle_owner": self.strategygroup_lifecycle_owner,
            "tradeability_decision_source": self.tradeability_decision_source,
            "runtime_truth_source": self.runtime_truth_source,
            "live_permission_change": self.live_permission_change,
        }


def _sequence_capital_trial_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    return _CapitalTrialSummaryProjection.from_artifact(artifact).as_dict()


def _sequence_trial_admission_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    proposal = _as_dict(artifact.get("proposal"))
    checkpoint = _as_dict(artifact.get("owner_policy_checkpoint"))
    return {
        "status": _status(artifact) or "missing",
        "active": _status(artifact) == "trial_asset_admission_proposal_ready",
        "strategy_group_id": str(proposal.get("strategy_group_id") or ""),
        "current_stage": str(proposal.get("current_stage") or ""),
        "proposed_stage": str(proposal.get("proposed_stage") or ""),
        "owner_policy_required": checkpoint.get("owner_policy_required") is True,
        "owner_policy_fields": [
            str(item) for item in checkpoint.get("owner_policy_fields") or []
        ],
        "admission_checkpoint": str(
            proposal.get("non_authority_checkpoint") or ""
        ),
        "after_next_state": str(proposal.get("after_next_state") or ""),
    }


def _sequence_brf2_owner_trial_policy_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    policy = _as_dict(artifact.get("policy"))
    return {
        "status": _status(artifact) or "missing",
        "active": _status(artifact) == "brf2_owner_trial_policy_scope_recorded",
        "strategy_group_id": str(policy.get("strategy_group_id") or ""),
        "trial_identity": str(policy.get("trial_identity") or ""),
        "owner_policy_recorded": artifact.get("brf2_policy_scope_recorded") is True,
        "owner_policy_scope_missing": artifact.get("owner_policy_scope_missing")
        is not False,
        "brf2_stage_after_policy": str(
            artifact.get("brf2_stage_after_policy") or ""
        ),
        "brf2_new_first_blocker": str(
            artifact.get("brf2_new_first_blocker") or ""
        ),
        "policy_checkpoint": str(artifact.get("brf2_policy_checkpoint") or ""),
        "capital_scope": _as_dict(policy.get("capital_scope")),
        "max_notional": _as_dict(policy.get("max_notional")),
        "side_scope": [str(item) for item in policy.get("side_scope") or []],
        "symbol_scope": str(policy.get("symbol_scope") or ""),
        "leverage_scenario": str(policy.get("leverage_scenario") or ""),
        "attempt_cap": _int(policy.get("attempt_cap")),
        "loss_unit": _as_dict(policy.get("loss_unit")),
    }


def _sequence_brf2_required_facts_mapping_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    fresh_signal_rule = _as_dict(artifact.get("fresh_signal_rule"))
    required_fact_specs = _dict_rows(artifact.get("required_fact_observation_specs"))
    disable_fact_specs = _dict_rows(artifact.get("disable_fact_observation_specs"))
    return {
        "status": _status(artifact) or "missing",
        "active": _status(artifact) == "brf2_required_facts_mapping_ready",
        "ready": artifact.get("required_facts_mapping_ready") is True,
        "strategy_group_id": str(artifact.get("strategy_group_id") or ""),
        "fresh_signal_rule_id": str(fresh_signal_rule.get("signal_id") or ""),
        "required_fact_count": _int(
            _as_dict(artifact.get("checks")).get("required_fact_count")
            or len(required_fact_specs)
            or len(_dict_rows(artifact.get("required_facts")))
        ),
        "disable_fact_count": _int(
            _as_dict(artifact.get("checks")).get("disable_fact_count")
            or len(disable_fact_specs)
            or len(_dict_rows(artifact.get("disable_facts")))
        ),
        "after_next_state": str(artifact.get("after_next_state") or ""),
        "first_blocker_after_mapping": str(
            artifact.get("first_blocker_after_mapping") or ""
        ),
        "mapping_checkpoint": str(artifact.get("mapping_checkpoint") or ""),
    }


@dataclass(frozen=True)
class _BRF2RuntimeSignalFactsProjection:
    status: str
    active: bool
    strategy_group_id: str
    fact_input_present: bool
    watcher_tick_present: bool
    source_status: str
    source_path: str
    first_blocker_class: str
    first_blocker_owner: str
    fact_input_checkpoint: str
    projection_role: str = "requiredfacts_input_health_projection"
    state_source: str = "brf2_runtime_signal_facts"
    primary_judgment_source: bool = False
    tradeability_decision_source: bool = False
    runtime_truth_source: bool = False
    live_requiredfacts_authority: bool = False

    @classmethod
    def from_artifact(
        cls, artifact: dict[str, Any]
    ) -> "_BRF2RuntimeSignalFactsProjection":
        status = _status(artifact) or "missing"
        first_blocker = _as_dict(artifact.get("first_blocker"))
        return cls(
            status=status,
            active=status
            in {
                "brf2_runtime_signal_facts_ready",
                "brf2_runtime_signal_facts_missing_watcher_input",
            },
            strategy_group_id=str(artifact.get("strategy_group_id") or ""),
            fact_input_present=artifact.get("fact_input_present") is True,
            watcher_tick_present=artifact.get("watcher_tick_present") is True,
            source_status=str(artifact.get("source_status") or "missing"),
            source_path=str(artifact.get("source_path") or ""),
            first_blocker_class=str(first_blocker.get("class") or "missing"),
            first_blocker_owner=str(first_blocker.get("owner") or "unknown"),
            fact_input_checkpoint=str(
                artifact.get("fact_input_checkpoint")
                or first_blocker.get("repair_checkpoint")
                or ""
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "active": self.active,
            "strategy_group_id": self.strategy_group_id,
            "fact_input_present": self.fact_input_present,
            "watcher_tick_present": self.watcher_tick_present,
            "source_status": self.source_status,
            "source_path": self.source_path,
            "first_blocker_class": self.first_blocker_class,
            "first_blocker_owner": self.first_blocker_owner,
            "fact_input_checkpoint": self.fact_input_checkpoint,
            "projection_role": self.projection_role,
            "state_source": self.state_source,
            "primary_judgment_source": self.primary_judgment_source,
            "tradeability_decision_source": self.tradeability_decision_source,
            "runtime_truth_source": self.runtime_truth_source,
            "live_requiredfacts_authority": self.live_requiredfacts_authority,
        }


def _sequence_brf2_runtime_signal_facts_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    return _BRF2RuntimeSignalFactsProjection.from_artifact(artifact).as_dict()


@dataclass(frozen=True)
class _BRF2RuntimeSignalCaptureProjection:
    status: str
    active: bool
    ready: bool
    strategy_group_id: str
    signal_id: str
    fact_input_present: bool
    watcher_tick_present: bool
    fact_input_status: str
    current_signal_state: str
    fresh_signal_present: bool
    first_blocker_class: str
    first_blocker_owner: str
    signal_capture_checkpoint: str
    missing_required_fact_count: int
    active_disable_fact_count: int
    blocked_fact_count: int
    shadow_candidate_shape_ready: bool
    projection_role: str = "runtime_readiness_signal_capture_projection"
    state_source: str = "brf2_runtime_signal_capture"
    primary_judgment_source: bool = False
    tradeability_decision_source: bool = False
    runtime_truth_source: bool = False
    live_submit_readiness_source: str = "runtime_safety_state"
    execution_attempt_required_for_lifecycle_entry: bool = True

    @classmethod
    def from_artifact(
        cls, artifact: dict[str, Any]
    ) -> "_BRF2RuntimeSignalCaptureProjection":
        status = _status(artifact) or "missing"
        preview = _as_dict(artifact.get("signal_detector_preview"))
        no_action = _as_dict(artifact.get("no_action_attribution"))
        candidate = _as_dict(artifact.get("shadow_candidate_shape"))
        watcher_scope = _as_dict(artifact.get("watcher_scope"))
        return cls(
            status=status,
            active=status == "brf2_runtime_signal_capture_ready",
            ready=status == "brf2_runtime_signal_capture_ready",
            strategy_group_id=str(artifact.get("strategy_group_id") or ""),
            signal_id=str(watcher_scope.get("signal_id") or ""),
            fact_input_present=(
                artifact.get("fact_input_present") is True
                or preview.get("fact_input_present") is True
            ),
            watcher_tick_present=(
                artifact.get("watcher_tick_present") is True
                or preview.get("watcher_tick_present") is True
            ),
            fact_input_status=str(
                artifact.get("fact_input_status")
                or preview.get("fact_input_status")
                or "missing"
            ),
            current_signal_state=str(
                preview.get("current_signal_state") or "unknown"
            ),
            fresh_signal_present=preview.get("fresh_signal_present") is True,
            first_blocker_class=str(
                preview.get("first_blocker_class") or "missing"
            ),
            first_blocker_owner=str(
                preview.get("first_blocker_owner") or "unknown"
            ),
            signal_capture_checkpoint=str(
                preview.get("signal_capture_checkpoint") or ""
            ),
            missing_required_fact_count=_int(
                len(preview.get("missing_required_fact_keys") or [])
            ),
            active_disable_fact_count=_int(
                len(preview.get("active_disable_fact_keys") or [])
            ),
            blocked_fact_count=_int(no_action.get("blocked_fact_count")),
            shadow_candidate_shape_ready=(
                candidate.get("shadow_candidate_ready") is True
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "active": self.active,
            "ready": self.ready,
            "strategy_group_id": self.strategy_group_id,
            "signal_id": self.signal_id,
            "fact_input_present": self.fact_input_present,
            "watcher_tick_present": self.watcher_tick_present,
            "fact_input_status": self.fact_input_status,
            "current_signal_state": self.current_signal_state,
            "fresh_signal_present": self.fresh_signal_present,
            "first_blocker_class": self.first_blocker_class,
            "first_blocker_owner": self.first_blocker_owner,
            "signal_capture_checkpoint": self.signal_capture_checkpoint,
            "missing_required_fact_count": self.missing_required_fact_count,
            "active_disable_fact_count": self.active_disable_fact_count,
            "blocked_fact_count": self.blocked_fact_count,
            "shadow_candidate_shape_ready": self.shadow_candidate_shape_ready,
            "projection_role": self.projection_role,
            "state_source": self.state_source,
            "primary_judgment_source": self.primary_judgment_source,
            "tradeability_decision_source": self.tradeability_decision_source,
            "runtime_truth_source": self.runtime_truth_source,
            "live_submit_readiness_source": self.live_submit_readiness_source,
            "execution_attempt_required_for_lifecycle_entry": (
                self.execution_attempt_required_for_lifecycle_entry
            ),
        }


def _sequence_brf2_runtime_signal_capture_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    return _BRF2RuntimeSignalCaptureProjection.from_artifact(artifact).as_dict()


@dataclass(frozen=True)
class _BRF2ShadowCandidateEvidenceProjection:
    status: str
    active: bool
    strategy_group_id: str
    shadow_candidate_evidence_ready: bool
    shadow_candidate_evidence_id: str
    signal_state: str
    first_blocker_class: str
    first_blocker_owner: str
    next_runtime_step: str
    projection_role: str = "shadow_candidate_evidence_provenance"
    state_source: str = "brf2_shadow_candidate_evidence"
    primary_judgment_source: bool = False
    non_executing_evidence: bool = True

    @classmethod
    def from_artifact(
        cls, artifact: dict[str, Any]
    ) -> "_BRF2ShadowCandidateEvidenceProjection":
        status = _status(artifact) or "missing"
        first_blocker = _as_dict(artifact.get("first_blocker"))
        candidate = _as_dict(artifact.get("shadow_candidate_evidence"))
        return cls(
            status=status,
            active=status
            in {
                "brf2_shadow_candidate_evidence_ready",
                "brf2_shadow_candidate_evidence_waiting_for_fresh_signal",
            },
            strategy_group_id=str(artifact.get("strategy_group_id") or ""),
            shadow_candidate_evidence_ready=(
                artifact.get("shadow_candidate_evidence_ready") is True
            ),
            shadow_candidate_evidence_id=str(
                candidate.get("shadow_candidate_evidence_id") or ""
            ),
            signal_state=str(candidate.get("signal_state") or "unknown"),
            first_blocker_class=str(first_blocker.get("class") or "missing"),
            first_blocker_owner=str(first_blocker.get("owner") or "unknown"),
            next_runtime_step=str(artifact.get("next_runtime_step") or ""),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "active": self.active,
            "strategy_group_id": self.strategy_group_id,
            "shadow_candidate_evidence_ready": self.shadow_candidate_evidence_ready,
            "shadow_candidate_evidence_id": self.shadow_candidate_evidence_id,
            "signal_state": self.signal_state,
            "first_blocker_class": self.first_blocker_class,
            "first_blocker_owner": self.first_blocker_owner,
            "next_runtime_step": self.next_runtime_step,
            "projection_role": self.projection_role,
            "state_source": self.state_source,
            "primary_judgment_source": self.primary_judgment_source,
            "non_executing_evidence": self.non_executing_evidence,
        }


def _sequence_brf2_shadow_candidate_evidence_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    return _BRF2ShadowCandidateEvidenceProjection.from_artifact(artifact).as_dict()


def _sequence_cpm_identity_routing_decision_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": _status(artifact) or "missing",
        "active": _status(artifact) == "cpm_identity_routing_decision_ready",
        "strategy_group_id": str(artifact.get("strategy_group_id") or ""),
        "path_id": str(artifact.get("path_id") or ""),
        "identity_decision": str(artifact.get("identity_decision") or ""),
        "standalone_trial_asset": (
            artifact.get("identity_decision") == "standalone_trial_asset"
        ),
        "cpm_long_vs_mpg_long_distinct": (
            artifact.get("cpm_long_vs_mpg_long_distinct") is True
        ),
        "projection_role": "identity_routing_decision_projection",
        "state_source": "cpm_identity_routing_decision",
        "primary_judgment_source": False,
        "tradeability_decision_source": False,
        "runtime_truth_source": False,
    }


def _sequence_cpm_owner_trial_policy_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    policy = _as_dict(artifact.get("policy"))
    capital_scope = _as_dict(policy.get("capital_scope"))
    return {
        "status": _status(artifact) or "missing",
        "active": _status(artifact) == "cpm_owner_trial_policy_scope_recorded",
        "strategy_group_id": str(policy.get("strategy_group_id") or ""),
        "owner_policy_recorded": artifact.get("owner_policy_recorded") is True,
        "cpm_policy_scope_recorded": artifact.get("cpm_policy_scope_recorded") is True,
        "owner_policy_scope_missing": artifact.get("owner_policy_scope_missing")
        is not False,
        "capital_scope_source": str(capital_scope.get("amount_source") or ""),
        "capital_scope_type": str(capital_scope.get("type") or ""),
        "side_scope": [str(item) for item in policy.get("side_scope") or []],
        "symbol_scope": str(policy.get("symbol_scope") or ""),
        "leverage_scenario": str(policy.get("leverage_scenario") or ""),
        "attempt_cap": _int(policy.get("attempt_cap")),
        "cpm_stage_after_policy": str(artifact.get("cpm_stage_after_policy") or ""),
        "cpm_new_first_blocker": str(artifact.get("cpm_new_first_blocker") or ""),
        "projection_role": "owner_trial_policy_scope_projection",
        "state_source": "cpm_owner_trial_policy_scope",
        "primary_judgment_source": False,
        "tradeability_decision_source": False,
        "runtime_truth_source": False,
    }


def _sequence_cpm_required_facts_mapping_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    fresh_signal_rule = _as_dict(artifact.get("fresh_signal_rule"))
    required_fact_specs = _dict_rows(artifact.get("required_fact_observation_specs"))
    disable_fact_specs = _dict_rows(artifact.get("disable_fact_observation_specs"))
    return {
        "status": _status(artifact) or "missing",
        "active": _status(artifact) == "cpm_required_facts_mapping_ready",
        "ready": artifact.get("required_facts_mapping_ready") is True,
        "strategy_group_id": str(artifact.get("strategy_group_id") or ""),
        "path_id": str(artifact.get("path_id") or ""),
        "fresh_signal_rule_id": str(fresh_signal_rule.get("signal_id") or ""),
        "required_fact_count": _int(
            _as_dict(artifact.get("checks")).get("required_fact_count")
            or len(required_fact_specs)
        ),
        "disable_fact_count": _int(
            _as_dict(artifact.get("checks")).get("disable_fact_count")
            or len(disable_fact_specs)
        ),
        "live_required_facts_authority": artifact.get(
            "live_required_facts_authority"
        )
        is True,
        "action_time_refresh_required": artifact.get("action_time_refresh_required")
        is True,
        "after_next_state": str(artifact.get("after_next_state") or ""),
        "first_blocker_after_mapping": str(
            artifact.get("first_blocker_after_mapping") or ""
        ),
        "projection_role": "requiredfacts_mapping_projection",
        "state_source": "cpm_required_facts_mapping",
        "primary_judgment_source": False,
        "tradeability_decision_source": False,
        "runtime_truth_source": False,
    }


def _sequence_cpm_runtime_signal_facts_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    first_blocker = _as_dict(artifact.get("first_blocker"))
    return {
        "status": _status(artifact) or "missing",
        "active": _status(artifact) == "cpm_runtime_signal_facts_ready",
        "strategy_group_id": str(artifact.get("strategy_group_id") or ""),
        "path_id": str(artifact.get("path_id") or ""),
        "fact_input_present": artifact.get("fact_input_present") is True,
        "watcher_tick_present": artifact.get("watcher_tick_present") is True,
        "fact_authority": str(artifact.get("fact_authority") or ""),
        "live_required_facts_authority": _as_dict(
            artifact.get("fact_authority_boundary")
        ).get("live_required_facts_authority")
        is True,
        "action_time_refresh_required": _as_dict(
            artifact.get("fact_authority_boundary")
        ).get("action_time_refresh_required")
        is True,
        "first_blocker_class": str(first_blocker.get("class") or "missing"),
        "first_blocker_owner": str(first_blocker.get("owner") or "unknown"),
        "projection_role": "requiredfacts_input_health_projection",
        "state_source": "cpm_runtime_signal_facts",
        "primary_judgment_source": False,
        "tradeability_decision_source": False,
        "runtime_truth_source": False,
    }


def _sequence_cpm_runtime_signal_capture_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    status = _status(artifact) or "missing"
    preview = _as_dict(artifact.get("signal_detector_preview"))
    candidate = _as_dict(artifact.get("shadow_candidate_shape"))
    watcher_scope = _as_dict(artifact.get("watcher_scope"))
    return {
        "status": status,
        "active": status == "cpm_runtime_signal_capture_ready",
        "ready": status == "cpm_runtime_signal_capture_ready",
        "strategy_group_id": str(artifact.get("strategy_group_id") or ""),
        "path_id": str(artifact.get("path_id") or ""),
        "signal_id": str(watcher_scope.get("signal_id") or ""),
        "fact_input_present": (
            artifact.get("fact_input_present") is True
            or preview.get("fact_input_present") is True
        ),
        "watcher_tick_present": (
            artifact.get("watcher_tick_present") is True
            or preview.get("watcher_tick_present") is True
        ),
        "fact_input_status": str(artifact.get("fact_input_status") or "missing"),
        "current_signal_state": str(preview.get("current_signal_state") or "unknown"),
        "fresh_signal_present": preview.get("fresh_signal_present") is True,
        "first_blocker_class": str(preview.get("first_blocker_class") or "missing"),
        "first_blocker_owner": str(preview.get("first_blocker_owner") or "unknown"),
        "signal_capture_checkpoint": str(
            preview.get("signal_capture_checkpoint") or ""
        ),
        "missing_required_fact_count": _int(
            len(preview.get("missing_required_fact_keys") or [])
        ),
        "active_disable_fact_count": _int(
            len(preview.get("active_disable_fact_keys") or [])
        ),
        "action_time_pending_fact_count": _int(
            len(preview.get("action_time_pending_fact_keys") or [])
        ),
        "shadow_candidate_shape_ready": (
            candidate.get("shadow_candidate_ready") is True
        ),
        "projection_role": "runtime_readiness_signal_capture_projection",
        "state_source": "cpm_runtime_signal_capture",
        "primary_judgment_source": False,
        "tradeability_decision_source": False,
        "runtime_truth_source": False,
        "live_submit_readiness_source": "runtime_safety_state",
        "execution_attempt_required_for_lifecycle_entry": True,
    }


def _sequence_cpm_shadow_candidate_evidence_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    status = _status(artifact) or "missing"
    first_blocker = _as_dict(artifact.get("first_blocker"))
    candidate = _as_dict(artifact.get("shadow_candidate_evidence"))
    return {
        "status": status,
        "active": status
        in {
            "cpm_shadow_candidate_evidence_ready",
            "cpm_shadow_candidate_evidence_waiting_for_fresh_signal",
        },
        "strategy_group_id": str(artifact.get("strategy_group_id") or ""),
        "shadow_candidate_evidence_ready": (
            artifact.get("shadow_candidate_evidence_ready") is True
        ),
        "shadow_candidate_evidence_id": str(
            candidate.get("shadow_candidate_evidence_id") or ""
        ),
        "signal_state": str(candidate.get("signal_state") or "unknown"),
        "first_blocker_class": str(first_blocker.get("class") or "missing"),
        "first_blocker_owner": str(first_blocker.get("owner") or "unknown"),
        "next_runtime_step": str(artifact.get("next_runtime_step") or ""),
        "projection_role": "shadow_candidate_evidence_provenance",
        "state_source": "cpm_shadow_candidate_evidence",
        "primary_judgment_source": False,
        "non_executing_evidence": True,
    }


def _sequence_cpm_dry_run_submit_rehearsal_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    checks = _as_dict(artifact.get("checks"))
    synthetic = _as_dict(artifact.get("synthetic_fresh_signal_rehearsal"))
    status = _status(artifact) or "missing"
    return {
        "status": status,
        "active": status
        in {
            "cpm_dry_run_submit_rehearsal_passed",
            "cpm_dry_run_submit_rehearsal_shape_ready",
        },
        "strategy_group_id": str(artifact.get("strategy_group_id") or ""),
        "path_id": str(artifact.get("path_id") or ""),
        "dry_run_submit_rehearsal": str(
            artifact.get("dry_run_submit_rehearsal") or ""
        ),
        "armed_observation_ready": checks.get("armed_observation_ready") is True
        or artifact.get("armed_observation_ready") is True,
        "submit_rehearsal_shape_ready": (
            checks.get("submit_rehearsal_shape_ready") is True
            or artifact.get("submit_rehearsal_shape_ready") is True
        ),
        "fresh_signal_submit_rehearsal_passed": (
            checks.get("fresh_signal_submit_rehearsal_passed") is True
            or artifact.get("fresh_signal_submit_rehearsal_passed") is True
        ),
        "candidate_authorization_evidence_ready": checks.get(
            "candidate_authorization_evidence_ready"
        )
        is True,
        "finalgate_dry_run_passed": checks.get("finalgate_dry_run_passed") is True,
        "operation_layer_paper_passed": checks.get("operation_layer_paper_passed")
        is True,
        "execution_attempt_rehearsal_ready": checks.get(
            "execution_attempt_rehearsal_ready"
        )
        is True,
        "synthetic_fresh_signal_fixture_ready": checks.get(
            "synthetic_fresh_signal_fixture_ready"
        )
        is True
        or synthetic.get("fixture_ready") is True,
        "synthetic_fresh_signal_present": checks.get(
            "synthetic_fresh_signal_present"
        )
        is True
        or synthetic.get("fresh_signal_present") is True,
        "synthetic_dangerous_authority_fields_fail_closed": checks.get(
            "synthetic_dangerous_authority_fields_fail_closed"
        )
        is True
        or synthetic.get("dangerous_authority_fields_fail_closed") is True,
        "synthetic_shadow_candidate_evidence_ready": checks.get(
            "synthetic_shadow_candidate_evidence_ready"
        )
        is True
        or synthetic.get("shadow_candidate_evidence_ready") is True,
        "synthetic_candidate_authorization_evidence_shape_ready": checks.get(
            "synthetic_candidate_authorization_evidence_shape_ready"
        )
        is True
        or synthetic.get("candidate_authorization_evidence_shape_ready") is True,
        "synthetic_action_time_required_facts_declared": checks.get(
            "synthetic_action_time_required_facts_declared"
        )
        is True
        or synthetic.get("action_time_required_facts_declared") is True,
        "synthetic_finalgate_dry_run_passed": checks.get(
            "synthetic_finalgate_dry_run_passed"
        )
        is True
        or synthetic.get("finalgate_dry_run_passed") is True,
        "synthetic_operation_layer_paper_passed": checks.get(
            "synthetic_operation_layer_paper_passed"
        )
        is True
        or synthetic.get("operation_layer_paper_passed") is True,
        "synthetic_execution_attempt_rehearsal_ready": checks.get(
            "synthetic_execution_attempt_rehearsal_ready"
        )
        is True
        or synthetic.get("execution_attempt_rehearsal_ready") is True,
        "synthetic_fresh_signal_submit_rehearsal_passed": synthetic.get(
            "fresh_signal_submit_rehearsal_passed"
        )
        is True,
        "exchange_write": checks.get("exchange_write") is True,
        "order_created": checks.get("order_created") is True,
        "projection_role": "non_executing_submit_rehearsal_projection",
        "state_source": "cpm_dry_run_submit_rehearsal",
        "primary_judgment_source": False,
        "tradeability_decision_source": False,
        "runtime_truth_source": False,
    }


def _sequence_four_candidate_runtime_activation_closure_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    status = _status(artifact) or "missing"
    summary = _as_dict(artifact.get("summary"))
    source = _as_dict(artifact.get("source_replay"))
    return {
        "status": status,
        "active": status
        in {
            "four_candidate_runtime_activation_contract_ready",
            "four_candidate_runtime_activation_closure_ready",
        },
        "p0_contract_declared": summary.get("p0_contract_declared") is True,
        "p1_contract_declared": summary.get("p1_contract_declared") is True,
        "p0_runtime_artifacts_ready": (
            summary.get("p0_runtime_artifacts_ready") is True
        ),
        "p1_runtime_artifacts_ready": (
            summary.get("p1_runtime_artifacts_ready") is True
        ),
        "p0_tasks_closed": summary.get("p0_tasks_closed") is True,
        "p1_tasks_closed": summary.get("p1_tasks_closed") is True,
        "contract_declared_count": int(summary.get("contract_declared_count") or 0),
        "runtime_artifact_ready_count": int(
            summary.get("runtime_artifact_ready_count") or 0
        ),
        "scope_review_closed_count": int(summary.get("scope_review_closed_count") or 0),
        "watcher_scope_contract_ready_count": int(
            summary.get("watcher_scope_contract_ready_count") or 0
        ),
        "required_facts_contract_ready_count": int(
            summary.get("required_facts_contract_ready_count") or 0
        ),
        "candidate_evidence_shape_ready_count": int(
            summary.get("candidate_evidence_shape_ready_count") or 0
        ),
        "fresh_signal_rehearsal_ready_count": int(
            summary.get("fresh_signal_rehearsal_ready_count") or 0
        ),
        "action_time_boundary_ready_count": int(
            summary.get("action_time_boundary_ready_count") or 0
        ),
        "live_submit_allowed_count": int(
            summary.get("live_submit_allowed_count") or 0
        ),
        "formal_replay_review_opened_count": int(
            summary.get("formal_replay_review_opened_count") or 0
        ),
        "next_checkpoint": str(summary.get("next_checkpoint") or ""),
        "venue_basis": str(source.get("venue_basis") or ""),
        "execution_venue_match": source.get("execution_venue_match") is True,
        "projection_role": "expanded_readonly_watcher_scope_contract_projection",
        "state_source": "four_candidate_runtime_activation_closure",
        "primary_judgment_source": False,
        "tradeability_decision_source": False,
        "runtime_truth_source": False,
    }


def _sequence_four_candidate_scope_review_decision_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    status = _status(artifact) or "missing"
    summary = _as_dict(artifact.get("summary"))
    return {
        "status": status,
        "active": status == "four_candidate_scope_review_decision_ready",
        "decision_count": int(summary.get("decision_count") or 0),
        "readonly_watcher_scope_expansion_count": int(
            summary.get("readonly_watcher_scope_expansion_count") or 0
        ),
        "primary_live_submit_scope_changed_count": int(
            summary.get("primary_live_submit_scope_changed_count") or 0
        ),
        "deferred_replay_symbol_count": len(
            summary.get("deferred_replay_symbols") or []
        ),
        "projection_role": "scope_review_decision_projection",
        "state_source": "four_candidate_scope_review_decision",
        "primary_judgment_source": False,
        "tradeability_decision_source": False,
        "runtime_truth_source": False,
    }


def _sequence_cpm_fresh_signal_live_path_readiness_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    status = _status(artifact) or "missing"
    return {
        "status": status,
        "active": status == "cpm_fresh_signal_live_path_readiness_ready",
        "public_fact_path_ready": artifact.get("public_fact_path_ready") is True,
        "fresh_signal_present": artifact.get("fresh_signal_present") is True,
        "private_action_time_facts_ready": (
            artifact.get("private_action_time_facts_ready") is True
        ),
        "finalgate_called": artifact.get("finalgate_called") is True,
        "operation_layer_called": artifact.get("operation_layer_called") is True,
        "live_submit_allowed": artifact.get("live_submit_allowed") is True,
        "next_blocker": str(artifact.get("next_blocker") or ""),
        "projection_role": "cpm_fresh_signal_live_path_readiness_projection",
        "state_source": "cpm_fresh_signal_live_path_readiness",
        "primary_judgment_source": False,
        "tradeability_decision_source": False,
        "runtime_truth_source": False,
    }


def _sequence_strategy_fresh_signal_action_time_boundary_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    status = _status(artifact) or "missing"
    summary = _as_dict(artifact.get("summary"))
    checks = _as_dict(artifact.get("checks"))
    return {
        "status": status,
        "active": status == "strategy_fresh_signal_action_time_boundary_ready",
        "fresh_signal_present_count": int(
            summary.get("fresh_signal_present_count") or 0
        ),
        "would_enter_finalgate_if_private_facts_ready_count": int(
            summary.get("would_enter_finalgate_if_private_facts_ready_count") or 0
        ),
        "live_submit_allowed_count": int(summary.get("live_submit_allowed_count") or 0),
        "finalgate_called": checks.get("calls_finalgate") is True,
        "operation_layer_called": checks.get("calls_operation_layer") is True,
        "exchange_write_called": checks.get("calls_exchange_write") is True,
        "order_created": checks.get("order_created") is True,
        "projection_role": "fresh_signal_action_time_boundary_projection",
        "state_source": "strategy_fresh_signal_action_time_boundary",
        "primary_judgment_source": False,
        "tradeability_decision_source": False,
        "runtime_truth_source": False,
    }


def _sequence_replay_live_parity_audit_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    status = _status(artifact) or "missing"
    summary = _as_dict(artifact.get("summary"))
    per_symbol = [
        _replay_live_parity_symbol_row(row)
        for row in _dict_rows(artifact.get("per_symbol_mismatch_table"))
    ]
    cpm_symbol_rows = [
        row for row in per_symbol if row.get("strategy_group_id") == "CPM-RO-001"
    ]
    first_cpm_row = cpm_symbol_rows[0] if cpm_symbol_rows else {}
    return {
        "status": status,
        "active": status == "replay_live_parity_audit_ready",
        "replay_signal_count": int(summary.get("replay_signal_count") or 0),
        "live_detector_reproduced_count": int(
            summary.get("live_detector_reproduced_count") or 0
        ),
        "mismatch_count": int(summary.get("mismatch_count") or 0),
        "mismatch_reason_policy": str(summary.get("mismatch_reason_policy") or ""),
        "per_symbol_blocker_matrix": per_symbol,
        "cpm_per_symbol_blocker_matrix": cpm_symbol_rows,
        "cpm_first_blocker_class": str(first_cpm_row.get("blocker_class") or ""),
        "cpm_first_failed_facts": list(first_cpm_row.get("failed_facts") or []),
        "cpm_first_next_action": str(first_cpm_row.get("next_action") or ""),
        "projection_role": "replay_live_parity_projection",
        "state_source": "replay_live_parity_audit",
    }


def _replay_live_parity_symbol_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_group_id": str(row.get("strategy_group_id") or ""),
        "symbol": str(row.get("symbol") or ""),
        "detector_attached": row.get("detector_attached") is True,
        "watcher_tick_present": row.get("watcher_tick_present") is True,
        "computed": row.get("computed") is True,
        "failed_facts": [str(item) for item in row.get("failed_facts") or []],
        "blocker_class": str(row.get("blocker_class") or ""),
        "next_action": str(row.get("next_action") or ""),
        "mismatch_count": int(row.get("mismatch_count") or 0),
    }


def _sequence_mi_trial_admission_decision_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    status = _status(artifact) or "missing"
    tradeability = _as_dict(artifact.get("tradeability"))
    return {
        "status": status,
        "active": status == "mi_trial_admission_decision_ready",
        "trial_admission_decision": str(
            artifact.get("trial_admission_decision") or ""
        ),
        "promotion_scope": str(artifact.get("promotion_scope") or ""),
        "can_trade_now": tradeability.get("can_trade_now") is True,
        "first_blocker": str(tradeability.get("first_blocker") or ""),
        "blocker_owner": str(tradeability.get("blocker_owner") or ""),
        "projection_role": "mi_trial_admission_decision_projection",
        "state_source": "mi_trial_admission_decision",
    }


def _sequence_sor_session_detector_facts_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    status = _status(artifact) or "missing"
    summary = _as_dict(artifact.get("summary"))
    return {
        "status": status,
        "active": status == "sor_session_detector_facts_ready",
        "fresh_session_signal_count": int(
            summary.get("fresh_session_signal_count") or 0
        ),
        "first_blocker": str(summary.get("first_blocker") or ""),
        "projection_role": "sor_session_detector_projection",
        "state_source": "sor_session_detector_facts",
    }


@dataclass(frozen=True)
class _ThreeStrategyPortfolioSummaryProjection:
    status: str
    ready: bool
    objective_met: bool
    seat_count: int
    selected_strategy_groups: list[str]
    market_wait_count: int
    owner_policy_gap_count: int
    engineering_gap_count: int
    strategy_review_gap_count: int
    next_bottlenecks: dict[str, Any]
    stage_5_status: str
    controlled_live_standby_count: int
    hard_safety_gates_relaxed: bool
    readiness_stage_evidence: dict[str, Any]
    projection_role: str = "trial_envelope_projection"
    state_source: str = "three_strategy_live_trial_portfolio"
    primary_judgment_source: bool = False
    tradeability_decision_source: bool = False
    runtime_truth_source: bool = False

    @classmethod
    def from_artifact(
        cls, artifact: dict[str, Any]
    ) -> "_ThreeStrategyPortfolioSummaryProjection":
        status = _status(artifact) or "missing"
        seats = _as_dict(artifact.get("seat_readiness"))
        selected = [
            str(item) for item in artifact.get("selected_strategy_groups") or []
        ]
        blocker_rows = [
            _as_dict(_as_dict(seats.get(strategy_id)).get("first_blocker"))
            for strategy_id in selected
        ]
        stage_5 = _as_dict(artifact.get("stage_5_live_opportunity_standby"))
        readiness_stage_evidence = _portfolio_readiness_stage_evidence(
            selected=selected,
            seats=seats,
            stage_5=stage_5,
        )
        return cls(
            status=status,
            ready=status == "three_strategy_live_trial_portfolio_ready",
            objective_met=artifact.get("objective_met") is True,
            seat_count=_int(artifact.get("seat_count")),
            selected_strategy_groups=selected,
            market_wait_count=sum(
                blocker.get("blocker_owner") == "market" for blocker in blocker_rows
            ),
            owner_policy_gap_count=sum(
                blocker.get("blocker_owner") == "owner" for blocker in blocker_rows
            ),
            engineering_gap_count=sum(
                blocker.get("blocker_owner") == "engineering"
                for blocker in blocker_rows
            ),
            strategy_review_gap_count=sum(
                blocker.get("blocker_owner") == "strategy_review"
                for blocker in blocker_rows
            ),
            next_bottlenecks=_as_dict(artifact.get("next_engineering_bottleneck")),
            stage_5_status=str(stage_5.get("status") or "missing"),
            controlled_live_standby_count=_int(stage_5.get("standby_count")),
            hard_safety_gates_relaxed=(
                stage_5.get("hard_safety_gates_relaxed") is True
            ),
            readiness_stage_evidence=readiness_stage_evidence,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ready": self.ready,
            "objective_met": self.objective_met,
            "seat_count": self.seat_count,
            "selected_strategy_groups": self.selected_strategy_groups,
            "market_wait_count": self.market_wait_count,
            "owner_policy_gap_count": self.owner_policy_gap_count,
            "engineering_gap_count": self.engineering_gap_count,
            "strategy_review_gap_count": self.strategy_review_gap_count,
            "next_bottlenecks": self.next_bottlenecks,
            "stage_5_status": self.stage_5_status,
            "controlled_live_standby_count": self.controlled_live_standby_count,
            "hard_safety_gates_relaxed": self.hard_safety_gates_relaxed,
            "readiness_stage_evidence": self.readiness_stage_evidence,
            "projection_role": self.projection_role,
            "state_source": self.state_source,
            "primary_judgment_source": self.primary_judgment_source,
            "tradeability_decision_source": self.tradeability_decision_source,
            "runtime_truth_source": self.runtime_truth_source,
        }


def _sequence_three_strategy_portfolio_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    return _ThreeStrategyPortfolioSummaryProjection.from_artifact(artifact).as_dict()


def _sequence_armed_trade_candidate_summary(
    *,
    three_strategy_portfolio_summary: dict[str, Any],
    tradeability_summary: dict[str, Any],
) -> dict[str, Any]:
    legacy = [
        str(item)
        for item in three_strategy_portfolio_summary.get("selected_strategy_groups")
        or []
    ]
    armed_candidates = list(legacy)
    cpm = _as_dict(tradeability_summary.get("cpm_armed_observation"))
    if (
        cpm.get("strategy_group_id") == "CPM-RO-001"
        and cpm.get("stage") == "armed_observation"
        and "CPM-RO-001" not in armed_candidates
    ):
        armed_candidates.append("CPM-RO-001")
    return {
        "status": "armed_trade_candidates_ready" if armed_candidates else "missing",
        "candidate_count": len(armed_candidates),
        "strategy_group_ids": armed_candidates,
        "legacy_three_strategy_portfolio": legacy,
        "legacy_three_strategy_portfolio_count": len(legacy),
        "cpm_armed_observation_lane_present": "CPM-RO-001" in armed_candidates,
        "projection_role": "owner_candidate_summary_projection",
        "state_source": "tradeability_decision_plus_legacy_three_strategy_portfolio",
        "primary_judgment_source": False,
        "tradeability_decision_source": False,
        "runtime_truth_source": False,
    }


def _portfolio_readiness_stage_evidence(
    *,
    selected: list[str],
    seats: dict[str, Any],
    stage_5: dict[str, Any],
) -> dict[str, Any]:
    stage_rows = [
        _as_dict(
            _as_dict(_as_dict(seats.get(strategy_id)).get("runtime_readiness")).get(
                "readiness_stage_evidence"
            )
        )
        for strategy_id in selected
    ]
    known = [row for row in stage_rows if row]
    stage_ready = stage_5.get("ready") is True
    return {
        "source": "three_strategy_live_trial_portfolio.summary_projection",
        "trial_eligible": (
            bool(selected)
            and len(known) == len(selected)
            and all(row.get("trial_eligible") is True for row in known)
        ),
        "tiny_live_ready": (
            bool(selected)
            and len(known) == len(selected)
            and all(row.get("tiny_live_ready") is True for row in known)
        ),
        "pre_live_rehearsal_ready": False,
        "live_submit_ready": False,
        "ready_for_finalgate_checkpoint": False,
        "fresh_signal_state": "none" if stage_ready else "blocked",
        "live_submit_ready_false_reason": (
            "no_fresh_signal" if stage_ready else "portfolio_readiness_projection"
        ),
        "can_create_execution_attempt": False,
        "scoped_strategy_group_ids": selected,
        "trial_eligible_source": "Strategy Asset State / Owner policy",
        "tiny_live_ready_source": "Tradeability Decision / Runtime Safety State",
        "pre_live_rehearsal_ready_source": "Runtime Safety rehearsal",
        "live_submit_ready_source": "Runtime Safety action-time chain",
    }


@dataclass(frozen=True)
class _TradeabilityDecisionProjection:
    status: str
    active: bool
    row_count: int
    decision_rows_count: int
    row_count_matches_decision_rows: bool
    runtime_trade_allowed_rows: int
    controlled_live_standby_count: int
    stage_5_waiting_live_opportunity_ready_count: int
    top_strategy_group_id: str
    top_decision: str
    top_first_blocker_class: str
    top_tradeability_checkpoint: str
    top_blocker_owner: str
    top_after_next_state: str
    owner_intervention_required: bool
    july_bullish_rebound_trade_path_closure: dict[str, Any]
    cpm_armed_observation: dict[str, Any]

    _TOP_NEXT_ACTION_FIELD = "top_next_" + "action"

    @classmethod
    def from_artifact(
        cls, artifact: dict[str, Any]
    ) -> "_TradeabilityDecisionProjection":
        status = _status(artifact) or "missing"
        summary = (
            artifact.get("summary")
            if isinstance(artifact.get("summary"), dict)
            else {}
        )
        top_strategy_group_id = str(summary.get("top_strategy_group_id") or "")
        top_row = {}
        decision_rows = _dict_rows(artifact.get("decision_rows"))
        for row in decision_rows:
            if str(row.get("strategy_group_id") or "") == top_strategy_group_id:
                top_row = row
                break
        cpm_row = {}
        for row in decision_rows:
            if str(row.get("strategy_group_id") or "") == "CPM-RO-001":
                cpm_row = row
                break
        row_count = _int(summary.get("row_count"))
        july_closure = _as_dict(
            artifact.get("july_bullish_rebound_trade_path_closure")
        )
        july_summary = _as_dict(july_closure.get("summary"))
        july_checks = _as_dict(july_closure.get("checks"))
        cpm_long_path = {}
        for path in _dict_rows(july_closure.get("paths")):
            if str(path.get("path_id") or "") == "CPM-LONG":
                cpm_long_path = path
                break
        return cls(
            status=status,
            active=status == "tradeability_decision_ready",
            row_count=row_count,
            decision_rows_count=len(decision_rows),
            row_count_matches_decision_rows=row_count == len(decision_rows),
            runtime_trade_allowed_rows=_int(summary.get("tradable_now_count")),
            controlled_live_standby_count=_int(
                summary.get("controlled_live_standby_count")
            ),
            stage_5_waiting_live_opportunity_ready_count=_int(
                summary.get("stage_5_waiting_live_opportunity_ready_count")
            ),
            top_strategy_group_id=top_strategy_group_id,
            top_decision=str(summary.get("top_decision") or "missing"),
            top_first_blocker_class=str(
                summary.get("top_first_blocker_class") or "missing"
            ),
            top_tradeability_checkpoint=str(
                summary.get(cls._TOP_NEXT_ACTION_FIELD) or "missing"
            ),
            top_blocker_owner=str(top_row.get("blocker_owner") or "unknown"),
            top_after_next_state=str(top_row.get("after_next_state") or "unknown"),
            owner_intervention_required=_as_dict(artifact.get("owner_runtime_state")).get(
                "owner_intervention_required"
            )
            is True,
            july_bullish_rebound_trade_path_closure={
                "status": str(july_closure.get("status") or "missing"),
                "hypothesis_id": str(july_closure.get("hypothesis_id") or ""),
                "machine_consumption_surface": str(
                    july_closure.get("machine_consumption_surface") or ""
                ),
                "machine_consumed_path_count": _int(
                    july_summary.get("machine_consumed_path_count")
                ),
                "long_side_path_count": _int(
                    july_summary.get("long_side_path_count")
                ),
                "short_side_guard_path_count": _int(
                    july_summary.get("short_side_guard_path_count")
                ),
                "rbr_exit_decision_count": _int(
                    july_summary.get("rbr_exit_decision_count")
                ),
                "required_path_ids_present": (
                    july_checks.get("required_path_ids_present") is True
                ),
                "cpm_mapping_gap_removed_from_first_blockers": (
                    july_checks.get("cpm_mapping_gap_removed_from_first_blockers")
                    is True
                ),
                "rbr_observe_only_has_exit_decision": (
                    july_checks.get("rbr_observe_only_has_exit_decision") is True
                ),
                "capital_scope_uses_action_time_exchange_available_balance": (
                    july_checks.get(
                        "capital_scope_uses_action_time_exchange_available_balance"
                    )
                    is True
                ),
            },
            cpm_armed_observation={
                "strategy_group_id": str(cpm_row.get("strategy_group_id") or ""),
                "stage": str(cpm_row.get("stage") or ""),
                "decision": str(cpm_row.get("decision") or ""),
                "first_blocker_class": str(
                    cpm_row.get("first_blocker_class") or ""
                ),
                "blocker_owner": str(cpm_row.get("blocker_owner") or ""),
                "required_facts_status": str(
                    cpm_row.get("required_facts_status") or ""
                ),
                "path_id": str(cpm_long_path.get("path_id") or ""),
                "path_required_facts_mapping_status": str(
                    cpm_long_path.get("required_facts_mapping_status") or ""
                ),
                "path_first_blocker": str(cpm_long_path.get("first_blocker") or ""),
                "path_blocker_owner": str(cpm_long_path.get("blocker_owner") or ""),
                "path_can_trade_now": cpm_long_path.get("can_trade_now") is True,
                "capital_scope_source": str(
                    cpm_long_path.get("capital_scope_source") or ""
                ),
            },
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "projection_role": "tradeability_decision_projection",
            "status": self.status,
            "active": self.active,
            "row_count": self.row_count,
            "decision_rows_count": self.decision_rows_count,
            "row_count_matches_decision_rows": self.row_count_matches_decision_rows,
            "decision_result_counts": {
                "runtime_trade_allowed_rows": self.runtime_trade_allowed_rows,
            },
            "controlled_live_standby_count": self.controlled_live_standby_count,
            "stage_5_waiting_live_opportunity_ready_count": (
                self.stage_5_waiting_live_opportunity_ready_count
            ),
            "top_strategy_group_id": self.top_strategy_group_id,
            "top_decision": self.top_decision,
            "top_first_blocker_class": self.top_first_blocker_class,
            "top_tradeability_checkpoint": self.top_tradeability_checkpoint,
            "top_blocker_owner": self.top_blocker_owner,
            "top_after_next_state": self.top_after_next_state,
            "owner_intervention_required": self.owner_intervention_required,
            "july_bullish_rebound_trade_path_closure": (
                self.july_bullish_rebound_trade_path_closure
            ),
            "cpm_armed_observation": self.cpm_armed_observation,
        }


def _sequence_tradeability_decision_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    return _TradeabilityDecisionProjection.from_artifact(artifact).as_dict()


def _sequence_trial_grade_signal_gate_audit_summary(
    artifact: dict[str, Any],
) -> dict[str, Any]:
    summary = _as_dict(artifact.get("summary"))
    rows = _as_dict(artifact.get("strategy_group_rows"))

    def would_enter(strategy_group_id: str) -> bool:
        return (
            _as_dict(
                _as_dict(rows.get(strategy_group_id)).get(
                    "tomorrow_same_structure_assessment"
                )
            ).get("would_enter_controlled_live_trial")
            is True
        )

    return {
        "status": _status(artifact) or "missing",
        "active": _status(artifact) == "trial_grade_signal_gate_audit_ready",
        "ready": _status(artifact) == "trial_grade_signal_gate_audit_ready",
        "strategy_group_count": _int(summary.get("strategy_group_count")),
        "trial_grade_observation_count_30d": _int(
            summary.get("trial_grade_observation_count_30d")
        ),
        "action_time_submit_count_30d": _int(
            summary.get("action_time_trial_submit_count_30d")
        ),
        "hard_safety_gates_relaxed": summary.get("hard_safety_gates_relaxed")
        is True,
        "brf2_would_enter_controlled_live_trial_if_same_structure": would_enter("BRF2-001"),
        "mpg_would_enter_controlled_live_trial_if_same_structure": would_enter("MPG-001"),
        "sor_would_enter_controlled_live_trial_if_same_structure": would_enter("SOR-001"),
    }


def _sequence_signal_observation_grade_summary(
    *,
    signal_coverage_artifact: dict[str, Any],
    expansion_review_artifact: dict[str, Any],
    strategy_asset_state_artifact: dict[str, Any],
    capital_trial_summary: dict[str, Any],
) -> dict[str, Any]:
    signal_observation = _as_dict(signal_coverage_artifact.get("broader_observation"))
    signal_checks = _as_dict(signal_coverage_artifact.get("checks"))
    expansion_observation = _as_dict(expansion_review_artifact.get("observation_layer"))
    ledger_observation = _as_dict(strategy_asset_state_artifact.get("observation_layer"))

    would_enter_rows = _dict_rows(signal_observation.get("would_enter_signals"))
    no_action_rows = _dict_rows(
        signal_observation.get("high_priority_no_action_signals")
    )
    latest = (
        _as_dict(expansion_observation.get("latest_observe_only_would_enter"))
        or _as_dict(ledger_observation.get("latest_observe_only_would_enter"))
        or (would_enter_rows[0] if would_enter_rows else {})
    )
    no_action_queue = _dict_rows(
        strategy_asset_state_artifact.get("no_action_attribution_queue")
    ) or _dict_rows(expansion_review_artifact.get("no_action_attribution_queue"))
    role_reviews = _dict_rows(strategy_asset_state_artifact.get("role_review_rows")) or _dict_rows(
        expansion_review_artifact.get("role_review_rows")
    )
    broader_would_enter_count = _coalesce_int(
        expansion_observation.get("broader_would_enter_count"),
        ledger_observation.get("broader_would_enter_count"),
        signal_checks.get("broader_current_signal_count")
        if would_enter_rows
        else None,
        len(would_enter_rows),
    )
    high_priority_no_action_count = _coalesce_int(
        expansion_observation.get("high_priority_no_action_count"),
        ledger_observation.get("high_priority_no_action_count"),
        signal_checks.get("broader_high_priority_no_action_signal_count"),
        len(no_action_rows),
    )
    state = (
        "observation_active"
        if broader_would_enter_count or high_priority_no_action_count
        else "quiet"
    )
    return {
        "main_chain_state": "waiting_for_executable_fresh_signal",
        "grade_code": "signal-observation-grade-review",
        "state": state,
        "broader_would_enter_count": broader_would_enter_count,
        "broader_actionable_would_enter_count": _coalesce_int(
            expansion_observation.get("broader_actionable_would_enter_count"),
            ledger_observation.get("broader_actionable_would_enter_count"),
            signal_checks.get("broader_actionable_would_enter_signal_count"),
            0,
        ),
        "high_priority_no_action_count": high_priority_no_action_count,
        "latest_observe_only_would_enter": {
            "strategy_group_id": str(latest.get("strategy_group_id") or ""),
            "symbol": str(latest.get("symbol") or ""),
            "side": str(latest.get("side") or ""),
            "confidence": str(latest.get("confidence") or ""),
            "not_live_signal": True,
        }
        if latest
        else {},
        "selected_short_intake_candidate": capital_trial_summary.get(
            "selected_short_strategy_group_id"
        )
        or "",
        "selected_short_intake_candidate_promotion_scope": capital_trial_summary.get(
            "promotion_scope"
        )
        or "not_applicable",
        "no_action_attribution_count": len(no_action_queue),
        "no_action_attribution_strategy_group_ids": [
            str(row.get("strategy_group_id") or "") for row in no_action_queue
        ],
        "role_review_count": len(role_reviews),
        "role_review_pairs": [
            {
                "source_observation_strategy_group_id": str(
                    row.get("source_observation_strategy_group_id") or ""
                ),
                "linked_intake_strategy_group_id": str(
                    row.get("linked_intake_strategy_group_id") or ""
                ),
                "next_checkpoint": str(row.get("next_checkpoint") or ""),
            }
            for row in role_reviews
        ],
    }


def _owner_progress_text(report: dict[str, Any]) -> str:
    owner = report["owner_summary"]
    interaction = report["interaction"]
    issues = artifact_owner_runtime_issues(report)
    signal_observation_grade = report.get("signal_observation_grade") or {}
    latest_observation = (
        signal_observation_grade.get("latest_observe_only_would_enter")
        if isinstance(
            signal_observation_grade.get("latest_observe_only_would_enter"), dict
        )
        else {}
    )
    research_intake = report.get("strategy_research_intake") or {}
    experiment_candidate = report.get("strategy_experiment_candidate") or {}
    trial_admission = report.get("strategy_trial_asset_admission") or {}
    brf2_policy = report.get("brf2_owner_trial_policy") or {}
    brf2_required_facts_mapping = report.get("brf2_required_facts_mapping") or {}
    brf2_runtime_signal_facts = report.get("brf2_runtime_signal_facts") or {}
    brf2_runtime_signal_capture = report.get("brf2_runtime_signal_capture") or {}
    brf2_shadow_candidate_evidence = (
        report.get("brf2_shadow_candidate_evidence") or {}
    )
    cpm_identity = report.get("cpm_identity_routing_decision") or {}
    cpm_policy = report.get("cpm_owner_trial_policy") or {}
    cpm_required_facts_mapping = report.get("cpm_required_facts_mapping") or {}
    cpm_runtime_signal_facts = report.get("cpm_runtime_signal_facts") or {}
    cpm_runtime_signal_capture = report.get("cpm_runtime_signal_capture") or {}
    cpm_shadow_candidate_evidence = report.get("cpm_shadow_candidate_evidence") or {}
    cpm_dry_run_submit_rehearsal = report.get("cpm_dry_run_submit_rehearsal") or {}
    four_candidate_runtime_activation_closure = (
        report.get("four_candidate_runtime_activation_closure") or {}
    )
    four_candidate_scope_review_decision = (
        report.get("four_candidate_scope_review_decision") or {}
    )
    cpm_fresh_signal_live_path_readiness = (
        report.get("cpm_fresh_signal_live_path_readiness") or {}
    )
    strategy_fresh_signal_action_time_boundary = (
        report.get("strategy_fresh_signal_action_time_boundary") or {}
    )
    replay_live_parity_audit = report.get("replay_live_parity_audit") or {}
    mi_trial_admission_decision = report.get("mi_trial_admission_decision") or {}
    sor_session_detector_facts = report.get("sor_session_detector_facts") or {}
    three_strategy_portfolio = (
        report.get("three_strategy_live_trial_portfolio") or {}
    )
    tradeability = report.get("tradeability_decision") or {}
    cpm_tradeability = _as_dict(tradeability.get("cpm_armed_observation"))
    legacy_three_strategy_groups = [
        str(item) for item in three_strategy_portfolio.get("selected_strategy_groups") or []
    ]
    armed_trade_candidates = list(legacy_three_strategy_groups)
    if (
        cpm_tradeability.get("strategy_group_id") == "CPM-RO-001"
        and cpm_tradeability.get("stage") == "armed_observation"
        and "CPM-RO-001" not in armed_trade_candidates
    ):
        armed_trade_candidates.append("CPM-RO-001")
    trial_grade_audit = (
        report.get("strategy_trial_grade_signal_gate_audit") or {}
    )
    lines = [
        "## StrategyGroup Runtime Local Monitor Sequence",
        "",
        f"- 报告时间: {report['generated_at_utc']}",
        f"- 当前阶段: {owner['state']}",
        f"- 当前检查点: {owner['non_authority_checkpoint']}",
        f"- 风险等级: {owner['risk_level']}",
        f"- Owner 介入: {_yes_no(bool(owner['owner_intervention_required']))}",
        f"- 交互等级: {interaction['level']}",
        f"- 远端交互次数: {interaction['remote_interaction_count']}",
        f"- 服务器修改: {_yes_no(bool(interaction['mutates_remote_files']))}",
        f"- 接近真实订单: {_yes_no(bool(interaction['approaches_real_order']))}",
        f"- Signal Observation grade: `{signal_observation_grade.get('grade_code', 'unknown')}` / `{signal_observation_grade.get('state', 'unknown')}`",
        f"- Signal Observation would-enter / no-action: `{signal_observation_grade.get('broader_would_enter_count', 0)}` / `{signal_observation_grade.get('high_priority_no_action_count', 0)}`",
        "- 昨晚观察信号: `{}` / `{}` / `{}`".format(
            latest_observation.get("strategy_group_id") or "none",
            latest_observation.get("symbol") or "-",
            latest_observation.get("side") or "-",
        ),
        f"- No-action 归因队列: `{signal_observation_grade.get('no_action_attribution_count', 0)}`",
        f"- RBR/RBR2 role review: `{signal_observation_grade.get('role_review_count', 0)}`",
        f"- 策略 intake 状态: `{research_intake.get('status', 'missing')}`",
        f"- 策略 intake 候选: `{', '.join(research_intake.get('strategy_group_ids') or []) or 'none'}`",
        f"- 受控实盘候选状态: `{experiment_candidate.get('status', 'missing')}`",
        f"- 受控实盘候选策略组: `{experiment_candidate.get('selected_strategy_group_id') or 'none'}`",
        f"- 做空试验候选策略组: `{experiment_candidate.get('selected_short_strategy_group_id') or 'none'}`",
        f"- 晋级范围: `{experiment_candidate.get('promotion_scope') or 'not_applicable'}`",
        f"- 准入提案状态: `{trial_admission.get('status', 'missing')}`",
        f"- 准入提案策略组: `{trial_admission.get('strategy_group_id') or 'none'}`",
        f"- 准入提案下一状态: `{trial_admission.get('after_next_state') or 'none'}`",
        f"- Owner policy required: `{_yes_no(trial_admission.get('owner_policy_required') is True)}`",
        f"- BRF2 Owner policy recorded: `{_yes_no(brf2_policy.get('owner_policy_recorded') is True)}`",
        f"- BRF2 next blocker: `{brf2_policy.get('brf2_new_first_blocker', 'missing')}`",
        f"- BRF2 RequiredFacts mapping: `{brf2_required_facts_mapping.get('status', 'missing')}`",
        f"- BRF2 fresh signal rule: `{brf2_required_facts_mapping.get('fresh_signal_rule_id') or 'none'}`",
        f"- BRF2 after mapping state: `{brf2_required_facts_mapping.get('after_next_state') or 'none'}`",
        f"- BRF2 runtime signal facts: `{brf2_runtime_signal_facts.get('status', 'missing')}`",
        f"- BRF2 fact input / watcher tick: `{_yes_no(brf2_runtime_signal_facts.get('fact_input_present') is True)}` / `{_yes_no(brf2_runtime_signal_facts.get('watcher_tick_present') is True)}`",
        f"- BRF2 runtime signal capture: `{brf2_runtime_signal_capture.get('status', 'missing')}`",
        f"- BRF2 signal state: `{brf2_runtime_signal_capture.get('current_signal_state', 'unknown')}`",
        f"- BRF2 signal first blocker: `{brf2_runtime_signal_capture.get('first_blocker_class', 'missing')}` / `{brf2_runtime_signal_capture.get('first_blocker_owner', 'unknown')}`",
        f"- BRF2 shadow candidate shape ready: `{_yes_no(brf2_runtime_signal_capture.get('shadow_candidate_shape_ready') is True)}`",
        f"- BRF2 shadow candidate evidence: `{brf2_shadow_candidate_evidence.get('status', 'missing')}`",
        f"- BRF2 shadow evidence ready: `{_yes_no(brf2_shadow_candidate_evidence.get('shadow_candidate_evidence_ready') is True)}`",
        f"- BRF2 shadow evidence first blocker: `{brf2_shadow_candidate_evidence.get('first_blocker_class', 'missing')}` / `{brf2_shadow_candidate_evidence.get('first_blocker_owner', 'unknown')}`",
        f"- CPM identity decision: `{cpm_identity.get('identity_decision') or 'missing'}`",
        f"- CPM standalone trial asset: `{_yes_no(cpm_identity.get('standalone_trial_asset') is True)}`",
        f"- CPM Owner policy recorded: `{_yes_no(cpm_policy.get('owner_policy_recorded') is True)}`",
        f"- CPM capital source: `{cpm_policy.get('capital_scope_source') or 'missing'}`",
        f"- CPM RequiredFacts mapping: `{cpm_required_facts_mapping.get('status', 'missing')}`",
        f"- CPM fresh signal rule: `{cpm_required_facts_mapping.get('fresh_signal_rule_id') or 'none'}`",
        f"- CPM runtime signal facts: `{cpm_runtime_signal_facts.get('status', 'missing')}`",
        f"- CPM fact input / watcher tick: `{_yes_no(cpm_runtime_signal_facts.get('fact_input_present') is True)}` / `{_yes_no(cpm_runtime_signal_facts.get('watcher_tick_present') is True)}`",
        f"- CPM runtime signal capture: `{cpm_runtime_signal_capture.get('status', 'missing')}`",
        f"- CPM signal state: `{cpm_runtime_signal_capture.get('current_signal_state', 'unknown')}`",
        f"- CPM signal first blocker: `{cpm_runtime_signal_capture.get('first_blocker_class', 'missing')}` / `{cpm_runtime_signal_capture.get('first_blocker_owner', 'unknown')}`",
        f"- CPM shadow candidate evidence: `{cpm_shadow_candidate_evidence.get('status', 'missing')}`",
        f"- CPM shadow evidence first blocker: `{cpm_shadow_candidate_evidence.get('first_blocker_class', 'missing')}` / `{cpm_shadow_candidate_evidence.get('first_blocker_owner', 'unknown')}`",
        f"- CPM dry-run submit rehearsal: `{cpm_dry_run_submit_rehearsal.get('dry_run_submit_rehearsal') or 'missing'}`",
        f"- CPM armed observation ready: `{_yes_no(cpm_dry_run_submit_rehearsal.get('armed_observation_ready') is True)}`",
        f"- CPM submit rehearsal shape ready: `{_yes_no(cpm_dry_run_submit_rehearsal.get('submit_rehearsal_shape_ready') is True)}`",
        f"- CPM fresh-signal submit rehearsal passed: `{_yes_no(cpm_dry_run_submit_rehearsal.get('fresh_signal_submit_rehearsal_passed') is True)}`",
        f"- CPM rehearsal FinalGate/Operation Layer paper: `{_yes_no(cpm_dry_run_submit_rehearsal.get('finalgate_dry_run_passed') is True)}` / `{_yes_no(cpm_dry_run_submit_rehearsal.get('operation_layer_paper_passed') is True)}`",
        f"- CPM synthetic fresh-signal rehearsal passed: `{_yes_no(cpm_dry_run_submit_rehearsal.get('synthetic_fresh_signal_submit_rehearsal_passed') is True)}`",
        f"- CPM synthetic candidate/action-time shape: `{_yes_no(cpm_dry_run_submit_rehearsal.get('synthetic_candidate_authorization_evidence_shape_ready') is True)}` / `{_yes_no(cpm_dry_run_submit_rehearsal.get('synthetic_action_time_required_facts_declared') is True)}`",
        f"- CPM synthetic FinalGate/Operation Layer paper: `{_yes_no(cpm_dry_run_submit_rehearsal.get('synthetic_finalgate_dry_run_passed') is True)}` / `{_yes_no(cpm_dry_run_submit_rehearsal.get('synthetic_operation_layer_paper_passed') is True)}`",
        f"- CPM synthetic authority fail-closed: `{_yes_no(cpm_dry_run_submit_rehearsal.get('synthetic_dangerous_authority_fields_fail_closed') is True)}`",
        f"- Four-candidate activation contract: `{four_candidate_runtime_activation_closure.get('status', 'missing')}`",
        f"- P0/P1 contract declared: `{_yes_no(four_candidate_runtime_activation_closure.get('p0_contract_declared') is True)}` / `{_yes_no(four_candidate_runtime_activation_closure.get('p1_contract_declared') is True)}`",
        f"- P0/P1 runtime artifacts ready: `{_yes_no(four_candidate_runtime_activation_closure.get('p0_runtime_artifacts_ready') is True)}` / `{_yes_no(four_candidate_runtime_activation_closure.get('p1_runtime_artifacts_ready') is True)}`",
        f"- Contract/runtime/scope/watcher/facts/candidate/rehearsal/boundary ready: `{four_candidate_runtime_activation_closure.get('contract_declared_count', 0)}` / `{four_candidate_runtime_activation_closure.get('runtime_artifact_ready_count', 0)}` / `{four_candidate_runtime_activation_closure.get('scope_review_closed_count', 0)}` / `{four_candidate_runtime_activation_closure.get('watcher_scope_contract_ready_count', 0)}` / `{four_candidate_runtime_activation_closure.get('required_facts_contract_ready_count', 0)}` / `{four_candidate_runtime_activation_closure.get('candidate_evidence_shape_ready_count', 0)}` / `{four_candidate_runtime_activation_closure.get('fresh_signal_rehearsal_ready_count', 0)}` / `{four_candidate_runtime_activation_closure.get('action_time_boundary_ready_count', 0)}`",
        f"- MI formal replay review opened: `{four_candidate_runtime_activation_closure.get('formal_replay_review_opened_count', 0)}`",
        f"- Scope review decision: `{four_candidate_scope_review_decision.get('status', 'missing')}` / readonly expansions `{four_candidate_scope_review_decision.get('readonly_watcher_scope_expansion_count', 0)}` / live-scope changes `{four_candidate_scope_review_decision.get('primary_live_submit_scope_changed_count', 0)}`",
        f"- CPM fresh-path public facts / fresh signal / next blocker: `{_yes_no(cpm_fresh_signal_live_path_readiness.get('public_fact_path_ready') is True)}` / `{_yes_no(cpm_fresh_signal_live_path_readiness.get('fresh_signal_present') is True)}` / `{cpm_fresh_signal_live_path_readiness.get('next_blocker') or 'missing'}`",
        f"- Fresh-signal action-time boundary: `{strategy_fresh_signal_action_time_boundary.get('status', 'missing')}` / fresh `{strategy_fresh_signal_action_time_boundary.get('fresh_signal_present_count', 0)}` / finalgate-if-private-facts `{strategy_fresh_signal_action_time_boundary.get('would_enter_finalgate_if_private_facts_ready_count', 0)}` / live-submit `{strategy_fresh_signal_action_time_boundary.get('live_submit_allowed_count', 0)}`",
        f"- Replay-live parity: `{replay_live_parity_audit.get('status', 'missing')}` / replay `{replay_live_parity_audit.get('replay_signal_count', 0)}` / reproduced `{replay_live_parity_audit.get('live_detector_reproduced_count', 0)}` / mismatch `{replay_live_parity_audit.get('mismatch_count', 0)}`",
        "- CPM replay-live first blocker: `{}` / failed `{}` / next `{}`".format(
            replay_live_parity_audit.get("cpm_first_blocker_class") or "missing",
            ", ".join(replay_live_parity_audit.get("cpm_first_failed_facts") or [])
            or "none",
            replay_live_parity_audit.get("cpm_first_next_action") or "missing",
        ),
        f"- MI trial admission: `{mi_trial_admission_decision.get('trial_admission_decision') or 'missing'}` / scope `{mi_trial_admission_decision.get('promotion_scope') or 'missing'}` / blocker `{mi_trial_admission_decision.get('first_blocker') or 'missing'}`",
        f"- SOR session detector: `{sor_session_detector_facts.get('status', 'missing')}` / fresh `{sor_session_detector_facts.get('fresh_session_signal_count', 0)}` / blocker `{sor_session_detector_facts.get('first_blocker') or 'missing'}`",
        f"- Activation venue basis/match: `{four_candidate_runtime_activation_closure.get('venue_basis') or 'missing'}` / `{_yes_no(four_candidate_runtime_activation_closure.get('execution_venue_match') is True)}`",
        f"- Activation next checkpoint: `{four_candidate_runtime_activation_closure.get('next_checkpoint') or 'missing'}`",
        f"- Armed trade candidates: `{', '.join(armed_trade_candidates) or 'none'}`",
        f"- Armed trade candidate count: `{len(armed_trade_candidates)}`",
        f"- Legacy three-strategy portfolio: `{', '.join(legacy_three_strategy_groups) or 'none'}`",
        f"- Legacy three-strategy portfolio status/count: `{three_strategy_portfolio.get('status', 'missing')}` / `{three_strategy_portfolio.get('seat_count', 0)}`",
        f"- 第五阶段状态: `{three_strategy_portfolio.get('stage_5_status', 'missing')}`",
        f"- 受控实盘 standby 席位: `{three_strategy_portfolio.get('controlled_live_standby_count', 0)}` / `{three_strategy_portfolio.get('seat_count', 0)}`",
        f"- 组合第一阻断统计 market/owner/engineering: `{three_strategy_portfolio.get('market_wait_count', 0)}` / `{three_strategy_portfolio.get('owner_policy_gap_count', 0)}` / `{three_strategy_portfolio.get('engineering_gap_count', 0)}`",
        f"- Tradeability Decision 状态: `{tradeability.get('status', 'missing')}`",
        f"- Tradeability Decision Top: `{tradeability.get('top_strategy_group_id') or 'none'}` / `{tradeability.get('top_decision', 'missing')}`",
        f"- 第一阻断: `{tradeability.get('top_first_blocker_class', 'missing')}` / `{tradeability.get('top_blocker_owner', 'unknown')}`",
        f"- 下一检查点: `{tradeability.get('top_tradeability_checkpoint', 'missing')}`",
        f"- CPM Tradeability row: `{cpm_tradeability.get('stage') or 'missing'}` / `{cpm_tradeability.get('decision') or 'missing'}`",
        f"- CPM Tradeability blocker: `{cpm_tradeability.get('first_blocker_class') or 'missing'}` / `{cpm_tradeability.get('blocker_owner') or 'unknown'}`",
        f"- CPM-LONG path readiness: `{cpm_tradeability.get('path_required_facts_mapping_status') or 'missing'}` / `{_yes_no(cpm_tradeability.get('path_can_trade_now') is True)}`",
        f"- Tradeability trial-grade standby: `{tradeability.get('controlled_live_standby_count', 0)}`",
        f"- Trial-grade signal audit: `{trial_grade_audit.get('status', 'missing')}`",
        f"- Trial-grade 30d observation / action-time submit: `{trial_grade_audit.get('trial_grade_observation_count_30d', 0)}` / `{trial_grade_audit.get('action_time_submit_count_30d', 0)}`",
        f"- Trial-grade hard gates relaxed: `{_yes_no(trial_grade_audit.get('hard_safety_gates_relaxed') is True)}`",
        f"- 当前可交易数量: `{_as_dict(tradeability.get('decision_result_counts')).get('runtime_trade_allowed_rows', 0)}`",
        "",
        "## Steps",
        "",
        "| Step | Status | Returncode |",
        "| --- | --- | ---: |",
    ]
    for step in report["steps"]:
        lines.append(
            f"| {step['name']} | {step.get('status') or 'unknown'} | {step['returncode']} |"
        )
    lines.extend([
        "",
        "## Owner Runtime Issues",
        "",
        f"- Blockers: {_list_or_none(issues.get('blockers') or [])}",
        f"- Non-market gaps: {_list_or_none(issues.get('non_market_gaps') or [])}",
    ])
    return "\n".join(lines)


def _print_human_report(report: dict[str, Any]) -> None:
    print(f"status={report['status']}")
    print(f"owner_state={report['owner_summary']['state']}")
    print(
        "non_authority_checkpoint="
        f"{report['owner_summary']['non_authority_checkpoint']}"
    )
    print(f"interaction={report['interaction']['level']}")
    print(f"remote_interaction_count={report['interaction']['remote_interaction_count']}")
    issues = artifact_owner_runtime_issues(report)
    blockers = [str(item) for item in issues.get("blockers") or []]
    if blockers:
        print("blockers=" + ",".join(blockers))


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _status(artifact: Any) -> str:
    return str(artifact.get("status") or "") if isinstance(artifact, dict) else ""


def _interaction(artifact: Any) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        return {}
    interaction = artifact.get("interaction")
    return interaction if isinstance(interaction, dict) else {}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def _coalesce_int(*values: Any) -> int:
    for value in values:
        if value is not None:
            return _int(value)
    return 0


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _display_command(command: list[str]) -> str:
    return " ".join(command).replace(str(REPO_ROOT) + "/", "")


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


def _list_or_none(values: list[Any]) -> str:
    if not values:
        return "none"
    rendered = []
    for value in values:
        if isinstance(value, (dict, list)):
            rendered.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
        else:
            rendered.append(str(value))
    return ", ".join(rendered)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local StrategyGroup runtime monitor artifacts sequentially."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument("--owner-progress", action="store_true")
    parser.add_argument(
        "--daily-check-mode",
        choices=["cache", "auto-cache", "artifact"],
        default="cache",
        help=(
            "cache is local-only; auto-cache may perform one L1 readonly refresh; "
            "artifact reads the supplied daily-check JSON without probing Tokyo."
        ),
    )
    parser.add_argument("--daily-check-json", default=str(DEFAULT_DAILY_CHECK_JSON))
    parser.add_argument("--daily-owner-progress", default=str(DEFAULT_DAILY_OWNER_PROGRESS))
    parser.add_argument("--live-cutover-json", default=str(DEFAULT_LIVE_CUTOVER_JSON))
    parser.add_argument("--live-cutover-md", default=str(DEFAULT_LIVE_CUTOVER_MD))
    parser.add_argument("--goal-progress-json", default=str(DEFAULT_GOAL_PROGRESS_JSON))
    parser.add_argument("--goal-progress-md", default=str(DEFAULT_GOAL_PROGRESS_MD))
    parser.add_argument("--completion-audit-json", default=str(DEFAULT_COMPLETION_AUDIT_JSON))
    parser.add_argument("--completion-audit-md", default=str(DEFAULT_COMPLETION_AUDIT_MD))
    parser.add_argument("--dry-run-audit-json", default=str(DEFAULT_DRY_RUN_AUDIT_JSON))
    parser.add_argument("--dry-run-audit-dir", default=str(DEFAULT_DRY_RUN_AUDIT_DIR))
    parser.add_argument("--replay-lab-json", default=str(DEFAULT_REPLAY_LAB_JSON))
    parser.add_argument("--replay-lab-md", default=str(DEFAULT_REPLAY_LAB_MD))
    parser.add_argument("--signal-coverage-json", default=str(DEFAULT_SIGNAL_COVERAGE_JSON))
    parser.add_argument("--signal-coverage-md", default=str(DEFAULT_SIGNAL_COVERAGE_MD))
    parser.add_argument(
        "--signal-coverage-expansion-review-json",
        default=str(DEFAULT_SIGNAL_COVERAGE_EXPANSION_REVIEW_JSON),
    )
    parser.add_argument(
        "--signal-coverage-expansion-review-md",
        default=str(DEFAULT_SIGNAL_COVERAGE_EXPANSION_REVIEW_MD),
    )
    parser.add_argument(
        "--l2-readiness-review-json",
        default=str(DEFAULT_L2_READINESS_REVIEW_JSON),
    )
    parser.add_argument(
        "--l2-readiness-review-md",
        default=str(DEFAULT_L2_READINESS_REVIEW_MD),
    )
    parser.add_argument(
        "--l2-intake-dry-run-json",
        default=str(DEFAULT_L2_INTAKE_DRY_RUN_JSON),
    )
    parser.add_argument(
        "--l2-intake-dry-run-md",
        default=str(DEFAULT_L2_INTAKE_DRY_RUN_MD),
    )
    parser.add_argument(
        "--l2-tier-policy-review-json",
        default=str(DEFAULT_L2_TIER_POLICY_REVIEW_JSON),
    )
    parser.add_argument(
        "--l2-tier-policy-review-md",
        default=str(DEFAULT_L2_TIER_POLICY_REVIEW_MD),
    )
    parser.add_argument(
        "--post-revision-replay-review-json",
        default=str(DEFAULT_POST_REVISION_REPLAY_REVIEW_JSON),
    )
    parser.add_argument(
        "--post-revision-replay-review-md",
        default=str(DEFAULT_POST_REVISION_REPLAY_REVIEW_MD),
    )
    parser.add_argument(
        "--opportunity-review-work-loop-json",
        default=str(DEFAULT_OPPORTUNITY_REVIEW_WORK_LOOP_JSON),
    )
    parser.add_argument(
        "--opportunity-review-work-loop-md",
        default=str(DEFAULT_OPPORTUNITY_REVIEW_WORK_LOOP_MD),
    )
    parser.add_argument(
        "--btpc-l2-shadow-fact-quality-review-json",
        default=str(DEFAULT_BTPC_L2_SHADOW_FACT_QUALITY_REVIEW_JSON),
    )
    parser.add_argument(
        "--btpc-l2-shadow-fact-quality-review-md",
        default=str(DEFAULT_BTPC_L2_SHADOW_FACT_QUALITY_REVIEW_MD),
    )
    parser.add_argument(
        "--btpc-local-fact-proxy-review-json",
        default=str(DEFAULT_BTPC_LOCAL_FACT_PROXY_REVIEW_JSON),
    )
    parser.add_argument(
        "--btpc-local-fact-proxy-review-md",
        default=str(DEFAULT_BTPC_LOCAL_FACT_PROXY_REVIEW_MD),
    )
    parser.add_argument(
        "--btpc-proxy-replay-quality-review-json",
        default=str(DEFAULT_BTPC_PROXY_REPLAY_QUALITY_REVIEW_JSON),
    )
    parser.add_argument(
        "--btpc-proxy-replay-quality-review-md",
        default=str(DEFAULT_BTPC_PROXY_REPLAY_QUALITY_REVIEW_MD),
    )
    parser.add_argument(
        "--btpc-l2-keep-revise-fact-source-review-json",
        default=str(DEFAULT_BTPC_L2_KEEP_REVISE_FACT_SOURCE_REVIEW_JSON),
    )
    parser.add_argument(
        "--btpc-l2-keep-revise-fact-source-review-md",
        default=str(DEFAULT_BTPC_L2_KEEP_REVISE_FACT_SOURCE_REVIEW_MD),
    )
    parser.add_argument(
        "--btpc-live-derivatives-fact-source-mapping-json",
        default=str(DEFAULT_BTPC_LIVE_DERIVATIVES_FACT_SOURCE_MAPPING_JSON),
    )
    parser.add_argument(
        "--btpc-live-derivatives-fact-source-mapping-md",
        default=str(DEFAULT_BTPC_LIVE_DERIVATIVES_FACT_SOURCE_MAPPING_MD),
    )
    parser.add_argument(
        "--btpc-classifier-rule-review-json",
        default=str(DEFAULT_BTPC_CLASSIFIER_RULE_REVIEW_JSON),
    )
    parser.add_argument(
        "--btpc-classifier-rule-review-md",
        default=str(DEFAULT_BTPC_CLASSIFIER_RULE_REVIEW_MD),
    )
    parser.add_argument(
        "--strategy-asset-state-json",
        default=str(DEFAULT_STRATEGY_ASSET_STATE_JSON),
    )
    parser.add_argument(
        "--strategy-asset-state-md",
        default=str(DEFAULT_STRATEGY_ASSET_STATE_MD),
    )
    parser.add_argument(
        "--strategygroup-quality-wave-json",
        default=str(DEFAULT_STRATEGYGROUP_QUALITY_WAVE_JSON),
    )
    parser.add_argument(
        "--strategygroup-quality-wave-md",
        default=str(DEFAULT_STRATEGYGROUP_QUALITY_WAVE_MD),
    )
    parser.add_argument(
        "--strategygroup-handoff-boundary-closure-json",
        default=str(DEFAULT_STRATEGYGROUP_HANDOFF_BOUNDARY_CLOSURE_JSON),
    )
    parser.add_argument(
        "--strategygroup-handoff-boundary-closure-md",
        default=str(DEFAULT_STRATEGYGROUP_HANDOFF_BOUNDARY_CLOSURE_MD),
    )
    parser.add_argument(
        "--strategygroup-btpc-fact-classifier-guard-json",
        default=str(DEFAULT_STRATEGYGROUP_BTPC_FACT_CLASSIFIER_GUARD_JSON),
    )
    parser.add_argument(
        "--strategygroup-btpc-fact-classifier-guard-md",
        default=str(DEFAULT_STRATEGYGROUP_BTPC_FACT_CLASSIFIER_GUARD_MD),
    )
    parser.add_argument(
        "--strategygroup-lifecycle-rehearsal-json",
        default=str(DEFAULT_STRATEGYGROUP_LIFECYCLE_REHEARSAL_JSON),
    )
    parser.add_argument(
        "--strategygroup-lifecycle-rehearsal-md",
        default=str(DEFAULT_STRATEGYGROUP_LIFECYCLE_REHEARSAL_MD),
    )
    parser.add_argument(
        "--strategygroup-pre-live-rehearsal-readiness-json",
        default=str(DEFAULT_STRATEGYGROUP_PRE_LIVE_REHEARSAL_READINESS_JSON),
    )
    parser.add_argument(
        "--strategygroup-pre-live-rehearsal-readiness-md",
        default=str(DEFAULT_STRATEGYGROUP_PRE_LIVE_REHEARSAL_READINESS_MD),
    )
    parser.add_argument(
        "--strategygroup-runtime-safety-state-json",
        default=str(DEFAULT_STRATEGYGROUP_RUNTIME_SAFETY_STATE_JSON),
    )
    parser.add_argument(
        "--strategygroup-runtime-safety-state-md",
        default=str(DEFAULT_STRATEGYGROUP_RUNTIME_SAFETY_STATE_MD),
    )
    parser.add_argument(
        "--strategygroup-portfolio-board-json",
        default=str(DEFAULT_STRATEGYGROUP_PORTFOLIO_BOARD_JSON),
    )
    parser.add_argument(
        "--strategygroup-portfolio-board-md",
        default=str(DEFAULT_STRATEGYGROUP_PORTFOLIO_BOARD_MD),
    )
    parser.add_argument(
        "--strategygroup-review-only-deep-dive-wave-json",
        default=str(DEFAULT_STRATEGYGROUP_REVIEW_ONLY_DEEP_DIVE_WAVE_JSON),
    )
    parser.add_argument(
        "--strategygroup-owner-policy-package-json",
        dest="strategygroup_owner_policy_package_json",
        default=str(DEFAULT_STRATEGYGROUP_OWNER_POLICY_PACKAGE_JSON),
    )
    parser.add_argument(
        "--strategygroup-quality-closure-wave-json",
        default=str(DEFAULT_STRATEGYGROUP_QUALITY_CLOSURE_WAVE_JSON),
    )
    parser.add_argument(
        "--strategygroup-trial-candidate-pool-md",
        default=str(DEFAULT_STRATEGYGROUP_TRIAL_CANDIDATE_POOL_MD),
    )
    parser.add_argument(
        "--strategy-capture-gap-audit-json",
        default=str(DEFAULT_STRATEGY_CAPTURE_GAP_AUDIT_JSON),
    )
    parser.add_argument(
        "--strategygroup-capital-trial-envelope-projection-json",
        default=str(DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_ENVELOPE_PROJECTION_JSON),
    )
    parser.add_argument(
        "--strategygroup-capital-trial-envelope-projection-md",
        default=str(DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_ENVELOPE_PROJECTION_MD),
    )
    parser.add_argument(
        "--strategygroup-capital-trial-envelope-json",
        default=str(DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_ENVELOPE_JSON),
    )
    parser.add_argument(
        "--strategygroup-capital-trial-envelope-md",
        default=str(DEFAULT_STRATEGYGROUP_CAPITAL_TRIAL_ENVELOPE_MD),
    )
    parser.add_argument(
        "--strategygroup-research-intake-review-json",
        default=str(DEFAULT_STRATEGYGROUP_RESEARCH_INTAKE_REVIEW_JSON),
    )
    parser.add_argument(
        "--strategygroup-research-intake-review-md",
        default=str(DEFAULT_STRATEGYGROUP_RESEARCH_INTAKE_REVIEW_MD),
    )
    parser.add_argument(
        "--strategygroup-trial-asset-admission-proposal-json",
        default=str(DEFAULT_STRATEGYGROUP_TRIAL_ASSET_ADMISSION_PROPOSAL_JSON),
    )
    parser.add_argument(
        "--strategygroup-trial-asset-admission-proposal-md",
        default=str(DEFAULT_STRATEGYGROUP_TRIAL_ASSET_ADMISSION_PROPOSAL_MD),
    )
    parser.add_argument(
        "--brf2-owner-trial-policy-scope-json",
        default=str(DEFAULT_BRF2_OWNER_TRIAL_POLICY_SCOPE_JSON),
    )
    parser.add_argument(
        "--brf2-owner-trial-policy-scope-md",
        default=str(DEFAULT_BRF2_OWNER_TRIAL_POLICY_SCOPE_MD),
    )
    parser.add_argument(
        "--brf2-required-facts-mapping-json",
        default=str(DEFAULT_BRF2_REQUIRED_FACTS_MAPPING_JSON),
    )
    parser.add_argument(
        "--brf2-required-facts-mapping-md",
        default=str(DEFAULT_BRF2_REQUIRED_FACTS_MAPPING_MD),
    )
    parser.add_argument(
        "--brf2-runtime-signal-facts-json",
        default=str(DEFAULT_BRF2_RUNTIME_SIGNAL_FACTS_JSON),
    )
    parser.add_argument(
        "--brf2-runtime-signal-facts-md",
        default=str(DEFAULT_BRF2_RUNTIME_SIGNAL_FACTS_MD),
    )
    parser.add_argument(
        "--brf2-runtime-signal-capture-json",
        default=str(DEFAULT_BRF2_RUNTIME_SIGNAL_CAPTURE_JSON),
    )
    parser.add_argument(
        "--brf2-runtime-signal-capture-md",
        default=str(DEFAULT_BRF2_RUNTIME_SIGNAL_CAPTURE_MD),
    )
    parser.add_argument(
        "--brf2-shadow-candidate-evidence-json",
        default=str(DEFAULT_BRF2_SHADOW_CANDIDATE_EVIDENCE_JSON),
    )
    parser.add_argument(
        "--brf2-shadow-candidate-evidence-md",
        default=str(DEFAULT_BRF2_SHADOW_CANDIDATE_EVIDENCE_MD),
    )
    parser.add_argument(
        "--cpm-identity-routing-decision-json",
        default=str(DEFAULT_CPM_IDENTITY_ROUTING_DECISION_JSON),
    )
    parser.add_argument(
        "--cpm-identity-routing-decision-md",
        default=str(DEFAULT_CPM_IDENTITY_ROUTING_DECISION_MD),
    )
    parser.add_argument(
        "--cpm-owner-trial-policy-scope-json",
        default=str(DEFAULT_CPM_OWNER_TRIAL_POLICY_SCOPE_JSON),
    )
    parser.add_argument(
        "--cpm-owner-trial-policy-scope-md",
        default=str(DEFAULT_CPM_OWNER_TRIAL_POLICY_SCOPE_MD),
    )
    parser.add_argument(
        "--cpm-required-facts-mapping-json",
        default=str(DEFAULT_CPM_REQUIRED_FACTS_MAPPING_JSON),
    )
    parser.add_argument(
        "--cpm-required-facts-mapping-md",
        default=str(DEFAULT_CPM_REQUIRED_FACTS_MAPPING_MD),
    )
    parser.add_argument(
        "--cpm-runtime-signal-facts-json",
        default=str(DEFAULT_CPM_RUNTIME_SIGNAL_FACTS_JSON),
    )
    parser.add_argument(
        "--cpm-runtime-signal-facts-md",
        default=str(DEFAULT_CPM_RUNTIME_SIGNAL_FACTS_MD),
    )
    parser.add_argument(
        "--cpm-runtime-signal-capture-json",
        default=str(DEFAULT_CPM_RUNTIME_SIGNAL_CAPTURE_JSON),
    )
    parser.add_argument(
        "--cpm-runtime-signal-capture-md",
        default=str(DEFAULT_CPM_RUNTIME_SIGNAL_CAPTURE_MD),
    )
    parser.add_argument(
        "--cpm-shadow-candidate-evidence-json",
        default=str(DEFAULT_CPM_SHADOW_CANDIDATE_EVIDENCE_JSON),
    )
    parser.add_argument(
        "--cpm-shadow-candidate-evidence-md",
        default=str(DEFAULT_CPM_SHADOW_CANDIDATE_EVIDENCE_MD),
    )
    parser.add_argument(
        "--cpm-dry-run-submit-rehearsal-json",
        default=str(DEFAULT_CPM_DRY_RUN_SUBMIT_REHEARSAL_JSON),
    )
    parser.add_argument(
        "--cpm-dry-run-submit-rehearsal-md",
        default=str(DEFAULT_CPM_DRY_RUN_SUBMIT_REHEARSAL_MD),
    )
    parser.add_argument(
        "--four-candidate-recent-live-submit-replay-json",
        default=str(DEFAULT_FOUR_CANDIDATE_RECENT_LIVE_SUBMIT_REPLAY_JSON),
    )
    parser.add_argument(
        "--four-candidate-runtime-activation-closure-json",
        default=str(DEFAULT_FOUR_CANDIDATE_RUNTIME_ACTIVATION_CLOSURE_JSON),
    )
    parser.add_argument(
        "--four-candidate-runtime-activation-closure-md",
        default=str(DEFAULT_FOUR_CANDIDATE_RUNTIME_ACTIVATION_CLOSURE_MD),
    )
    parser.add_argument(
        "--strategygroup-trial-grade-signal-gate-audit-json",
        default=str(DEFAULT_STRATEGYGROUP_TRIAL_GRADE_SIGNAL_GATE_AUDIT_JSON),
    )
    parser.add_argument(
        "--strategygroup-trial-grade-signal-gate-audit-md",
        default=str(DEFAULT_STRATEGYGROUP_TRIAL_GRADE_SIGNAL_GATE_AUDIT_MD),
    )
    parser.add_argument(
        "--three-strategy-live-trial-portfolio-json",
        default=str(DEFAULT_THREE_STRATEGY_LIVE_TRIAL_PORTFOLIO_JSON),
    )
    parser.add_argument(
        "--three-strategy-live-trial-portfolio-md",
        default=str(DEFAULT_THREE_STRATEGY_LIVE_TRIAL_PORTFOLIO_MD),
    )
    parser.add_argument(
        "--strategygroup-tradeability-decision-json",
        dest="strategygroup_tradeability_decision_json",
        default=str(DEFAULT_STRATEGYGROUP_TRADEABILITY_DECISION_JSON),
    )
    parser.add_argument(
        "--strategygroup-tradeability-decision-md",
        dest="strategygroup_tradeability_decision_md",
        default=str(DEFAULT_STRATEGYGROUP_TRADEABILITY_DECISION_MD),
    )
    parser.add_argument(
        "--daily-live-enablement-table-json",
        default=str(DEFAULT_DAILY_LIVE_ENABLEMENT_TABLE_JSON),
    )
    parser.add_argument(
        "--daily-live-enablement-table-md",
        default=str(DEFAULT_DAILY_LIVE_ENABLEMENT_TABLE_MD),
    )
    parser.add_argument(
        "--single-lane-task-packet-json",
        default=str(DEFAULT_SINGLE_LANE_TASK_PACKET_JSON),
    )
    parser.add_argument(
        "--single-lane-task-packet-md",
        default=str(DEFAULT_SINGLE_LANE_TASK_PACKET_MD),
    )
    parser.add_argument(
        "--strategy-live-candidate-pool-json",
        default=str(DEFAULT_STRATEGY_LIVE_CANDIDATE_POOL_JSON),
    )
    parser.add_argument(
        "--strategy-live-candidate-pool-md",
        default=str(DEFAULT_STRATEGY_LIVE_CANDIDATE_POOL_MD),
    )
    parser.add_argument(
        "--runtime-active-monitor-json",
        default=str(DEFAULT_RUNTIME_ACTIVE_MONITOR_JSON),
    )
    parser.add_argument(
        "--binance-public-facts-ssh-host",
        default="",
        help=(
            "Optional SSH host for read-only Binance USD-M public facts fetch "
            "when local public endpoints are unavailable."
        ),
    )
    parser.add_argument(
        "--signal-coverage-source",
        choices=["sample", "local_sqlite_read_only", "live_market"],
        default="local_sqlite_read_only",
        help="Read-only broader strategy source for local signal coverage diagnostics.",
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
