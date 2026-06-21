#!/usr/bin/env python3
"""Run local StrategyGroup runtime monitor artifacts in a strict sequence.

This helper is for goal-mode and manual status review. It prevents false
completion-audit gaps caused by running goal-progress and completion-audit
commands in parallel. The default mode is cache-only and does not contact Tokyo.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable
from datetime import datetime, timezone


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DAILY_CHECK_JSON = REPO_ROOT / "output/runtime-monitor/latest-daily-check.json"
DEFAULT_DAILY_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-owner-progress.md"
)
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
DEFAULT_OPPORTUNITY_DECISION_LOOP_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-opportunity-decision-loop.json"
)
DEFAULT_OPPORTUNITY_DECISION_LOOP_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-opportunity-decision-loop.md"
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
DEFAULT_BTPC_L2_KEEP_REVISE_FACT_SOURCE_DECISION_JSON = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-l2-keep-revise-fact-source-decision.json"
)
DEFAULT_BTPC_L2_KEEP_REVISE_FACT_SOURCE_DECISION_MD = (
    REPO_ROOT
    / "output/runtime-monitor/latest-btpc-l2-keep-revise-fact-source-decision.md"
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
DEFAULT_STRATEGYGROUP_DECISION_LEDGER_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-decision-ledger.json"
)
DEFAULT_STRATEGYGROUP_DECISION_LEDGER_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-decision-ledger.md"
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
DEFAULT_STRATEGYGROUP_LIVE_SUBMIT_READINESS_BRIDGE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-live-submit-readiness-bridge.json"
)
DEFAULT_STRATEGYGROUP_LIVE_SUBMIT_READINESS_BRIDGE_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-live-submit-readiness-bridge.md"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-local-monitor-sequence.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-local-monitor-sequence.md"
)
MONITOR_REFRESH_STATUS = "waiting_for_market_monitor_refresh_needed"
DEPLOYMENT_ISSUE_STATUS = "temporarily_unavailable_deployment_issue"


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
        opportunity_decision_loop_json=Path(args.opportunity_decision_loop_json),
        opportunity_decision_loop_md=Path(args.opportunity_decision_loop_md),
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
        btpc_l2_keep_revise_fact_source_decision_json=Path(
            args.btpc_l2_keep_revise_fact_source_decision_json
        ),
        btpc_l2_keep_revise_fact_source_decision_md=Path(
            args.btpc_l2_keep_revise_fact_source_decision_md
        ),
        btpc_live_derivatives_fact_source_mapping_json=Path(
            args.btpc_live_derivatives_fact_source_mapping_json
        ),
        btpc_live_derivatives_fact_source_mapping_md=Path(
            args.btpc_live_derivatives_fact_source_mapping_md
        ),
        btpc_classifier_rule_review_json=Path(args.btpc_classifier_rule_review_json),
        btpc_classifier_rule_review_md=Path(args.btpc_classifier_rule_review_md),
        strategygroup_decision_ledger_json=Path(
            args.strategygroup_decision_ledger_json
        ),
        strategygroup_decision_ledger_md=Path(args.strategygroup_decision_ledger_md),
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
        strategygroup_live_submit_readiness_bridge_json=Path(
            args.strategygroup_live_submit_readiness_bridge_json
        ),
        strategygroup_live_submit_readiness_bridge_md=Path(
            args.strategygroup_live_submit_readiness_bridge_md
        ),
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
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
    if checks.get("blockers") or checks.get("execution_blockers"):
        return False
    if checks.get("engineering_gaps") or checks.get("non_market_gaps"):
        return False
    if checks.get("owner_decision_required") is True:
        return False
    if report.get("monitor_status") == "deployment_issue":
        return False
    status = str(report.get("status") or "")
    runtime_status = str(report.get("runtime_status") or "")
    return status in {"waiting_for_market", "processing", "complete"} or (
        status == MONITOR_REFRESH_STATUS
        and runtime_status == "waiting_for_market"
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
    signal_coverage_source: str = "local_sqlite_fallback",
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
    opportunity_decision_loop_json: Path = DEFAULT_OPPORTUNITY_DECISION_LOOP_JSON,
    opportunity_decision_loop_md: Path = DEFAULT_OPPORTUNITY_DECISION_LOOP_MD,
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
    btpc_l2_keep_revise_fact_source_decision_json: Path = (
        DEFAULT_BTPC_L2_KEEP_REVISE_FACT_SOURCE_DECISION_JSON
    ),
    btpc_l2_keep_revise_fact_source_decision_md: Path = (
        DEFAULT_BTPC_L2_KEEP_REVISE_FACT_SOURCE_DECISION_MD
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
    strategygroup_decision_ledger_json: Path = (
        DEFAULT_STRATEGYGROUP_DECISION_LEDGER_JSON
    ),
    strategygroup_decision_ledger_md: Path = DEFAULT_STRATEGYGROUP_DECISION_LEDGER_MD,
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
    strategygroup_live_submit_readiness_bridge_json: Path = (
        DEFAULT_STRATEGYGROUP_LIVE_SUBMIT_READINESS_BRIDGE_JSON
    ),
    strategygroup_live_submit_readiness_bridge_md: Path = (
        DEFAULT_STRATEGYGROUP_LIVE_SUBMIT_READINESS_BRIDGE_MD
    ),
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
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

    goal_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/run_strategygroup_runtime_goal_progress_audit.py"),
        "--owner-progress",
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

    opportunity_decision_loop_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_opportunity_decision_loop.py"),
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
        str(opportunity_decision_loop_json),
        "--output-owner-progress",
        str(opportunity_decision_loop_md),
    ]
    steps.append(
        _run_step(
            "opportunity_decision_loop",
            opportunity_decision_loop_command,
            opportunity_decision_loop_json,
            runner,
        )
    )

    btpc_l2_shadow_fact_quality_review_command = [
        sys.executable,
        str(
            REPO_ROOT
            / "scripts/build_strategygroup_btpc_l2_shadow_fact_quality_review.py"
        ),
        "--opportunity-decision-loop-json",
        str(opportunity_decision_loop_json),
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

    opportunity_decision_loop_final_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_opportunity_decision_loop.py"),
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
        str(opportunity_decision_loop_json),
        "--output-owner-progress",
        str(opportunity_decision_loop_md),
    ]
    steps.append(
        _run_step(
            "opportunity_decision_loop_final",
            opportunity_decision_loop_final_command,
            opportunity_decision_loop_json,
            runner,
        )
    )

    btpc_l2_keep_revise_fact_source_decision_command = [
        sys.executable,
        str(
            REPO_ROOT
            / "scripts/build_strategygroup_btpc_l2_keep_revise_fact_source_decision.py"
        ),
        "--opportunity-decision-loop-json",
        str(opportunity_decision_loop_json),
        "--btpc-proxy-replay-quality-json",
        str(btpc_proxy_replay_quality_review_json),
        "--output-json",
        str(btpc_l2_keep_revise_fact_source_decision_json),
        "--output-owner-progress",
        str(btpc_l2_keep_revise_fact_source_decision_md),
    ]
    steps.append(
        _run_step(
            "btpc_l2_keep_revise_fact_source_decision",
            btpc_l2_keep_revise_fact_source_decision_command,
            btpc_l2_keep_revise_fact_source_decision_json,
            runner,
        )
    )

    btpc_live_derivatives_fact_source_mapping_command = [
        sys.executable,
        str(
            REPO_ROOT
            / "scripts/build_strategygroup_btpc_live_derivatives_fact_source_mapping.py"
        ),
        "--btpc-l2-decision-json",
        str(btpc_l2_keep_revise_fact_source_decision_json),
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
        "--btpc-l2-decision-json",
        str(btpc_l2_keep_revise_fact_source_decision_json),
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

    strategygroup_decision_ledger_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_decision_ledger.py"),
        "--opportunity-decision-loop-json",
        str(opportunity_decision_loop_json),
        "--signal-coverage-json",
        str(signal_coverage_json),
        "--output-json",
        str(strategygroup_decision_ledger_json),
        "--output-owner-progress",
        str(strategygroup_decision_ledger_md),
    ]
    steps.append(
        _run_step(
            "strategygroup_decision_ledger",
            strategygroup_decision_ledger_command,
            strategygroup_decision_ledger_json,
            runner,
        )
    )

    strategygroup_quality_wave_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_quality_wave.py"),
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
        "--btpc-l2-decision-json",
        str(btpc_l2_keep_revise_fact_source_decision_json),
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

    strategygroup_live_submit_readiness_bridge_command = [
        sys.executable,
        str(REPO_ROOT / "scripts/build_strategygroup_live_submit_readiness_bridge.py"),
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
        "--output-json",
        str(strategygroup_live_submit_readiness_bridge_json),
        "--output-owner-progress",
        str(strategygroup_live_submit_readiness_bridge_md),
    ]
    steps.append(
        _run_step(
            "strategygroup_live_submit_readiness_bridge",
            strategygroup_live_submit_readiness_bridge_command,
            strategygroup_live_submit_readiness_bridge_json,
            runner,
        )
    )

    packets = {
        step["name"]: step.get("packet") if isinstance(step.get("packet"), dict) else {}
        for step in steps
    }
    status = _sequence_status(steps=steps, packets=packets)
    interaction = _sequence_interaction(steps)
    execution_blockers = [
        f"{step['name']}:returncode:{step['returncode']}"
        for step in steps
        if int(step.get("returncode") or 0) not in (0,)
        and not _step_returncode_is_monitor_refresh(step, packets)
        and not _step_returncode_is_deployment_issue(step, packets)
        and not (
            step["name"] == "completion_audit"
            and _status(packets["completion_audit"]) == "needs_non_market_repair"
        )
    ]
    completion_non_market_gaps = list(
        packets["completion_audit"].get("non_market_gaps") or []
    )
    non_market_gaps = list(completion_non_market_gaps)
    expansion_review_resolved = _expansion_review_resolved(
        packets.get("l2_readiness_review", {}),
        packets.get("l2_tier_policy_review", {}),
        packets.get("opportunity_decision_loop", {}),
    )
    signal_coverage_gap = _expansion_review_non_market_gap(
        packets.get("signal_coverage_expansion_review", {}),
        packets.get("l2_readiness_review", {}),
        packets.get("l2_intake_dry_run", {}),
        packets.get("l2_tier_policy_review", {}),
        packets.get("opportunity_decision_loop", {}),
    )
    if signal_coverage_gap is None and not expansion_review_resolved:
        signal_coverage_gap = _signal_coverage_non_market_gap(
            packets.get("signal_coverage", {}),
        )
    if signal_coverage_gap:
        non_market_gaps.append(signal_coverage_gap)
    owner_decision_required = _sequence_owner_decision_required(
        packets=packets,
        execution_blockers=execution_blockers,
        engineering_gaps=non_market_gaps,
    )

    monitor_status = _sequence_monitor_status(status=status, packets=packets)
    runtime_status = _sequence_runtime_status(status=status, packets=packets)
    owner_status = _sequence_owner_status(
        status=status,
        runtime_status=runtime_status,
        monitor_status=monitor_status,
        owner_decision_required=owner_decision_required,
    )
    monitor_refresh_needed = monitor_status in {"needs_refresh", "deployment_issue"}
    monitor_refresh_reasons = _sequence_monitor_refresh_reasons(packets)

    return {
        "schema": "brc.strategygroup_runtime_local_monitor_sequence.v1",
        "scope": "strategygroup_runtime_local_monitor_sequence",
        "status": status,
        "runtime_status": runtime_status,
        "monitor_status": monitor_status,
        "owner_status": owner_status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "daily_check_mode": daily_check_mode,
        "owner_summary": {
            "state": _owner_state(status),
            "current_action": _owner_action(status),
            "owner_intervention_required": owner_decision_required,
            "risk_level": interaction["level"],
        },
        "interaction": interaction,
        "checks": {
            "blockers": execution_blockers,
            "execution_blockers": execution_blockers,
            "non_market_gaps": non_market_gaps,
            "engineering_gaps": non_market_gaps,
            "runtime_status": runtime_status,
            "monitor_status": monitor_status,
            "owner_status": owner_status,
            "monitor_refresh_needed": monitor_refresh_needed,
            "monitor_refresh_reasons": monitor_refresh_reasons,
            "monitor_refresh_gaps": monitor_refresh_reasons,
            "refresh_required": monitor_refresh_needed,
            "automation_notify": monitor_refresh_needed,
            "owner_notify": owner_decision_required,
            "owner_decision_required": owner_decision_required,
            "waiting_for_market": runtime_status == "waiting_for_market",
            "goal_complete": status == "complete",
        },
        "steps": [
            {
                "name": step["name"],
                "returncode": step["returncode"],
                "status": _status(step.get("packet")),
                "output_json": step["output_json"],
                "interaction": _interaction(step.get("packet")),
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
            "opportunity_decision_loop_json": str(opportunity_decision_loop_json),
            "btpc_l2_shadow_fact_quality_review_json": str(
                btpc_l2_shadow_fact_quality_review_json
            ),
            "btpc_local_fact_proxy_review_json": str(btpc_local_fact_proxy_review_json),
            "btpc_proxy_replay_quality_review_json": str(
                btpc_proxy_replay_quality_review_json
            ),
            "btpc_l2_keep_revise_fact_source_decision_json": str(
                btpc_l2_keep_revise_fact_source_decision_json
            ),
            "btpc_live_derivatives_fact_source_mapping_json": str(
                btpc_live_derivatives_fact_source_mapping_json
            ),
            "btpc_classifier_rule_review_json": str(btpc_classifier_rule_review_json),
            "strategygroup_decision_ledger_json": str(
                strategygroup_decision_ledger_json
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
            "strategygroup_live_submit_readiness_bridge_json": str(
                strategygroup_live_submit_readiness_bridge_json
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
    packet = _read_json_if_exists(output_json)
    return {
        "name": name,
        "command": _display_command(command),
        "returncode": int(completed.returncode),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "output_json": str(output_json),
        "packet": packet,
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


def _sequence_status(
    *,
    steps: list[dict[str, Any]],
    packets: dict[str, dict[str, Any]],
) -> str:
    if _packet_monitor_status(packets["daily_check"]) == "deployment_issue" or (
        _packet_monitor_status(packets["goal_progress"]) == "deployment_issue"
    ):
        return DEPLOYMENT_ISSUE_STATUS
    failed_steps = [
        step
        for step in steps
        if int(step.get("returncode") or 0) != 0
        and not _step_returncode_is_monitor_refresh(step, packets)
        and not _step_returncode_is_deployment_issue(step, packets)
        and not (
            step["name"] == "completion_audit"
            and _status(packets["completion_audit"]) == "needs_non_market_repair"
        )
    ]
    if failed_steps:
        return "needs_non_market_repair"
    completion_status = _status(packets["completion_audit"])
    if completion_status == "needs_non_market_repair":
        return "needs_non_market_repair"
    if _sequence_has_processing_signal(packets=packets):
        return "processing"
    if _packet_monitor_refresh_needed(packets["daily_check"]) or _packet_monitor_refresh_needed(
        packets["goal_progress"]
    ):
        if (
            _packet_runtime_status(packets["daily_check"]) == "waiting_for_market"
            or _packet_runtime_status(packets["goal_progress"]) == "waiting_for_market"
        ):
            return MONITOR_REFRESH_STATUS
        return "temporarily_unavailable_monitor_refresh_needed"

    if completion_status in {"complete", "completed"}:
        return "complete"
    l2_readiness_status = _status(packets.get("l2_readiness_review"))
    l2_dry_run_status = _status(packets.get("l2_intake_dry_run"))
    l2_tier_status = _status(packets.get("l2_tier_policy_review"))
    l2_tier_review_clears_expansion = l2_tier_status in {
        "l2_tier_policy_review_applied",
    } or l2_readiness_status == "l2_readiness_review_already_enabled"
    expansion_review_clears_expansion = (
        l2_tier_review_clears_expansion
        or _opportunity_decision_loop_clears_expansion(
            packets.get("opportunity_decision_loop", {}),
            l2_readiness_status=l2_readiness_status,
            l2_dry_run_status=l2_dry_run_status,
            l2_tier_status=l2_tier_status,
        )
    )
    signal_coverage_status = _status(packets.get("signal_coverage"))
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
    expansion_review_status = _status(packets.get("signal_coverage_expansion_review"))
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
        _status(packets["daily_check"]) == "waiting_for_market"
        and _status(packets["goal_progress"]) == "waiting_for_market"
        and completion_status == "not_complete_waiting_for_market"
    ):
        return "waiting_for_market"
    if _status(packets["daily_check"]) == "processing" or _status(
        packets["goal_progress"]
    ) == "processing":
        return "processing"
    return "needs_non_market_repair"


def _sequence_has_processing_signal(*, packets: dict[str, dict[str, Any]]) -> bool:
    if _packet_runtime_status(packets.get("daily_check", {})) == "processing":
        return True
    if _packet_runtime_status(packets.get("goal_progress", {})) == "processing":
        return True
    if _status(packets.get("completion_audit")) == "not_complete_runtime_processing":
        return True
    if _status(packets.get("signal_coverage")) == "mainline_runtime_signal_ready":
        return True
    if _status(packets.get("daily_check")) == "processing":
        return True
    if _status(packets.get("goal_progress")) == "processing":
        return True
    return False


def _step_returncode_is_monitor_refresh(
    step: dict[str, Any],
    packets: dict[str, dict[str, Any]],
) -> bool:
    return (
        step["name"] in {"daily_check", "goal_progress"}
        and int(step.get("returncode") or 0) != 0
        and _packet_monitor_refresh_needed(packets[step["name"]])
        and not (packets[step["name"]].get("checks") or {}).get("blockers")
    )


def _step_returncode_is_deployment_issue(
    step: dict[str, Any],
    packets: dict[str, dict[str, Any]],
) -> bool:
    if step["name"] not in {"daily_check", "goal_progress"}:
        return False
    if int(step.get("returncode") or 0) == 0:
        return False
    packet = packets.get(step["name"], {})
    return _packet_monitor_status(packet) == "deployment_issue" or _status(
        packet
    ) == DEPLOYMENT_ISSUE_STATUS


def _signal_coverage_non_market_gap(packet: dict[str, Any]) -> dict[str, Any] | None:
    status = _status(packet)
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


def _expansion_review_resolved(
    l2_packet: dict[str, Any],
    l2_tier_policy_packet: dict[str, Any],
    opportunity_decision_loop_packet: dict[str, Any] | None = None,
) -> bool:
    return _status(l2_packet) == "l2_readiness_review_already_enabled" or _status(
        l2_tier_policy_packet
    ) == "l2_tier_policy_review_applied" or _opportunity_decision_loop_clears_expansion(
        opportunity_decision_loop_packet or {},
        l2_readiness_status=_status(l2_packet),
        l2_dry_run_status="",
        l2_tier_status=_status(l2_tier_policy_packet),
    )


def _opportunity_decision_loop_clears_expansion(
    packet: dict[str, Any],
    *,
    l2_readiness_status: str,
    l2_dry_run_status: str,
    l2_tier_status: str,
) -> bool:
    if _status(packet) != "decision_loop_ready":
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
    packet: dict[str, Any],
    l2_packet: dict[str, Any] | None = None,
    l2_dry_run_packet: dict[str, Any] | None = None,
    l2_tier_policy_packet: dict[str, Any] | None = None,
    opportunity_decision_loop_packet: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    l2_packet = l2_packet or {}
    l2_dry_run_packet = l2_dry_run_packet or {}
    l2_tier_policy_packet = l2_tier_policy_packet or {}
    opportunity_decision_loop_packet = opportunity_decision_loop_packet or {}
    if _status(l2_packet) == "l2_readiness_review_already_enabled":
        return None
    l2_tier_status = _status(l2_tier_policy_packet)
    if l2_tier_status == "l2_tier_policy_review_applied":
        return None
    if l2_tier_status == "l2_tier_policy_review_recommended":
        decision = (
            l2_tier_policy_packet.get("decision")
            if isinstance(l2_tier_policy_packet.get("decision"), dict)
            else {}
        )
        groups = [
            str(item)
            for item in decision.get("groups_ready_to_apply_l2") or []
        ]
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
    l2_dry_run_status = _status(l2_dry_run_packet)
    if l2_dry_run_status == "l2_intake_dry_run_passed":
        decision = (
            l2_dry_run_packet.get("decision")
            if isinstance(l2_dry_run_packet.get("decision"), dict)
            else {}
        )
        groups = [
            str(item)
            for item in decision.get("groups_ready_for_l2_policy_review") or []
        ]
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
    l2_status = _status(l2_packet)
    if l2_status == "l2_readiness_review_has_conditional_candidate":
        decision = (
            l2_packet.get("decision") if isinstance(l2_packet.get("decision"), dict) else {}
        )
        groups = [
            str(item)
            for item in decision.get("handoff_intake_recommended_groups") or []
        ]
        default_next_step = str(decision.get("default_next_step") or "")
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
    if _opportunity_decision_loop_clears_expansion(
        opportunity_decision_loop_packet,
        l2_readiness_status=l2_status,
        l2_dry_run_status=l2_dry_run_status,
        l2_tier_status=l2_tier_status,
    ):
        return None
    status = _status(packet)
    if status == "review_needed_broader_observe_only_would_enter":
        counts = packet.get("counts") if isinstance(packet.get("counts"), dict) else {}
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
        interaction = _interaction(step.get("packet"))
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
    packets: dict[str, dict[str, Any]],
) -> str:
    if status == DEPLOYMENT_ISSUE_STATUS:
        return "deployment_issue"
    for name in ("daily_check", "goal_progress"):
        packet_status = _packet_monitor_status(packets.get(name, {}))
        if packet_status in {"deployment_issue", "needs_refresh"}:
            return packet_status
    if status in {"needs_refresh", "temporarily_unavailable_monitor_refresh_needed"}:
        return "needs_refresh"
    return "fresh"


def _sequence_runtime_status(
    *,
    status: str,
    packets: dict[str, dict[str, Any]],
) -> str:
    for name in ("daily_check", "goal_progress"):
        runtime_status = _packet_runtime_status(packets.get(name, {}))
        if runtime_status:
            return runtime_status
    if status in {"waiting_for_market", MONITOR_REFRESH_STATUS}:
        return "waiting_for_market"
    if status == "processing":
        return "processing"
    if status == "complete":
        return "completed"
    return "temporarily_unavailable"


def _sequence_owner_status(
    *,
    status: str,
    runtime_status: str,
    monitor_status: str,
    owner_decision_required: bool,
) -> str:
    if owner_decision_required:
        return "needs_intervention"
    if runtime_status == "waiting_for_market":
        return "waiting_for_opportunity"
    if runtime_status == "processing":
        return "processing"
    if runtime_status == "completed":
        return "completed"
    if monitor_status == "deployment_issue":
        return "temporarily_unavailable"
    return "temporarily_unavailable"


def _sequence_owner_decision_required(
    *,
    packets: dict[str, dict[str, Any]],
    execution_blockers: list[str],
    engineering_gaps: list[dict[str, Any]],
) -> bool:
    for packet in packets.values():
        if isinstance(packet, dict) and packet.get("owner_decision_required") is True:
            return True
        owner_summary = packet.get("owner_summary") if isinstance(packet, dict) else {}
        if isinstance(owner_summary, dict) and owner_summary.get(
            "owner_intervention_required"
        ) is True:
            return True
        checks = packet.get("checks") if isinstance(packet, dict) else {}
        if isinstance(checks, dict) and (
            checks.get("owner_decision_required") is True
            or checks.get("owner_intervention_required") is True
        ):
            return True
    owner_tokens = (
        "owner_policy",
        "owner_decision",
        "owner_intervention",
        "capital_adjustment",
        "pause_decision",
        "risk_acceptance",
    )
    for item in [*execution_blockers, *[str(gap) for gap in engineering_gaps]]:
        lowered = item.lower()
        if any(token in lowered for token in owner_tokens):
            return True
    return False


def _sequence_monitor_refresh_reasons(
    packets: dict[str, dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    for name in ("daily_check", "goal_progress"):
        checks = packets.get(name, {}).get("checks")
        if not isinstance(checks, dict):
            continue
        reasons.extend(str(item) for item in checks.get("monitor_refresh_reasons") or [])
    return list(dict.fromkeys(reasons))


def _packet_monitor_refresh_needed(packet: dict[str, Any]) -> bool:
    checks = packet.get("checks") if isinstance(packet, dict) else {}
    if not isinstance(checks, dict):
        checks = {}
    return (
        checks.get("monitor_refresh_needed") is True
        or _packet_monitor_status(packet) in {"needs_refresh", "deployment_issue"}
        or _status(packet)
        in {
            "needs_refresh",
            MONITOR_REFRESH_STATUS,
            DEPLOYMENT_ISSUE_STATUS,
            "temporarily_unavailable_monitor_refresh_needed",
        }
    )


def _packet_monitor_status(packet: dict[str, Any]) -> str:
    if not isinstance(packet, dict):
        return ""
    explicit = str(packet.get("monitor_status") or "")
    if explicit:
        return explicit
    checks = packet.get("checks") if isinstance(packet.get("checks"), dict) else {}
    if checks.get("deployment_issue") is True:
        return "deployment_issue"
    if checks.get("monitor_refresh_needed") is True:
        return "needs_refresh"
    if _status(packet) in {"needs_refresh", MONITOR_REFRESH_STATUS}:
        return "needs_refresh"
    if _status(packet) == DEPLOYMENT_ISSUE_STATUS:
        return "deployment_issue"
    return "fresh"


def _packet_runtime_status(packet: dict[str, Any]) -> str:
    if not isinstance(packet, dict):
        return ""
    explicit = str(packet.get("runtime_status") or "")
    if explicit:
        return explicit
    checks = packet.get("checks") if isinstance(packet.get("checks"), dict) else {}
    if checks.get("waiting_for_market") is True:
        return "waiting_for_market"
    status = _status(packet)
    if status in {"waiting_for_market", MONITOR_REFRESH_STATUS}:
        return "waiting_for_market"
    if status == "processing":
        return "processing"
    if status in {"complete", "completed"}:
        return "completed"
    if status in {DEPLOYMENT_ISSUE_STATUS, "blocked", "degraded"}:
        return "temporarily_unavailable"
    return ""


def _owner_state(status: str) -> str:
    if status in {"waiting_for_market", MONITOR_REFRESH_STATUS}:
        return "等待机会"
    if status == "processing":
        return "处理中"
    if status == "complete":
        return "已完成"
    if status == DEPLOYMENT_ISSUE_STATUS:
        return "暂不可用"
    if status == "needs_refresh":
        return "监控状态需刷新"
    return "需要修复"


def _owner_action(status: str) -> str:
    if status == "waiting_for_market":
        return "继续等待市场机会"
    if status == MONITOR_REFRESH_STATUS:
        return "刷新本地 runtime monitor 缓存"
    if status == "processing":
        return "等待系统完成当前链路"
    if status == "complete":
        return "归档第一笔边界内真实订单闭环"
    if status == DEPLOYMENT_ISSUE_STATUS:
        return "刷新或修复 runtime monitor 权威状态"
    if status == "needs_refresh":
        return "刷新本地 runtime monitor 缓存"
    return "修复本地监控或非市场证据缺口"


def _owner_progress_text(report: dict[str, Any]) -> str:
    owner = report["owner_summary"]
    interaction = report["interaction"]
    checks = report["checks"]
    lines = [
        "## StrategyGroup Runtime Local Monitor Sequence",
        "",
        f"- 报告时间: {report['generated_at_utc']}",
        f"- 当前阶段: {owner['state']}",
        f"- 当前动作: {owner['current_action']}",
        f"- 风险等级: {owner['risk_level']}",
        f"- Owner 介入: {_yes_no(bool(owner['owner_intervention_required']))}",
        f"- 交互等级: {interaction['level']}",
        f"- 远端交互次数: {interaction['remote_interaction_count']}",
        f"- 服务器修改: {_yes_no(bool(interaction['mutates_remote_files']))}",
        f"- 接近真实订单: {_yes_no(bool(interaction['approaches_real_order']))}",
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
        "## Checks",
        "",
        f"- Blockers: {_list_or_none(checks['blockers'])}",
        f"- Non-market gaps: {_list_or_none(checks['non_market_gaps'])}",
    ])
    return "\n".join(lines)


def _print_human_report(report: dict[str, Any]) -> None:
    print(f"status={report['status']}")
    print(f"owner_state={report['owner_summary']['state']}")
    print(f"current_action={report['owner_summary']['current_action']}")
    print(f"interaction={report['interaction']['level']}")
    print(f"remote_interaction_count={report['interaction']['remote_interaction_count']}")
    blockers = [str(item) for item in report["checks"]["blockers"]]
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


def _status(packet: Any) -> str:
    return str(packet.get("status") or "") if isinstance(packet, dict) else ""


def _interaction(packet: Any) -> dict[str, Any]:
    if not isinstance(packet, dict):
        return {}
    interaction = packet.get("interaction")
    return interaction if isinstance(interaction, dict) else {}


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
        "--opportunity-decision-loop-json",
        default=str(DEFAULT_OPPORTUNITY_DECISION_LOOP_JSON),
    )
    parser.add_argument(
        "--opportunity-decision-loop-md",
        default=str(DEFAULT_OPPORTUNITY_DECISION_LOOP_MD),
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
        "--btpc-l2-keep-revise-fact-source-decision-json",
        default=str(DEFAULT_BTPC_L2_KEEP_REVISE_FACT_SOURCE_DECISION_JSON),
    )
    parser.add_argument(
        "--btpc-l2-keep-revise-fact-source-decision-md",
        default=str(DEFAULT_BTPC_L2_KEEP_REVISE_FACT_SOURCE_DECISION_MD),
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
        "--strategygroup-decision-ledger-json",
        default=str(DEFAULT_STRATEGYGROUP_DECISION_LEDGER_JSON),
    )
    parser.add_argument(
        "--strategygroup-decision-ledger-md",
        default=str(DEFAULT_STRATEGYGROUP_DECISION_LEDGER_MD),
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
        "--strategygroup-live-submit-readiness-bridge-json",
        default=str(DEFAULT_STRATEGYGROUP_LIVE_SUBMIT_READINESS_BRIDGE_JSON),
    )
    parser.add_argument(
        "--strategygroup-live-submit-readiness-bridge-md",
        default=str(DEFAULT_STRATEGYGROUP_LIVE_SUBMIT_READINESS_BRIDGE_MD),
    )
    parser.add_argument(
        "--signal-coverage-source",
        choices=["sample", "local_sqlite_fallback", "live_market"],
        default="local_sqlite_fallback",
        help="Read-only broader strategy source for local signal coverage diagnostics.",
    )
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
