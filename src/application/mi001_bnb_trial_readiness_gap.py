"""Read-only MI-001 BNB bounded-trial readiness gap model.

This module describes what is missing before a future Owner-confirmed testnet
rehearsal or small live trial could be considered. It is a review artifact
only: it does not create execution intents, grant permissions, place orders, or
start runtime.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BnbTrialReadinessGate(BaseModel):
    gate_id: str
    gate_name: str
    current_status: str
    required_for_testnet_rehearsal: bool
    required_for_small_live_trial: bool
    existing_source_or_code_path: str
    gap: str
    recommended_action: str
    risk_if_skipped: str
    owner_intervention_required: bool


class BnbTrialDesignSummary(BaseModel):
    design_id: str
    status: list[str]
    mode: str
    trigger: str
    allowed_scope: list[str] = Field(default_factory=list)
    risk_controls: list[str] = Field(default_factory=list)
    exit_controls: list[str] = Field(default_factory=list)
    recordkeeping: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    non_permissions: list[str] = Field(default_factory=list)


class BnbExecutionBoundaryItem(BaseModel):
    boundary: str
    code_path: str
    current_assessment: str
    bnb_chain_touches_path: bool
    required_control: str


class BnbOwnerPolicyItem(BaseModel):
    decision_id: str
    question: str
    options: list[str]
    recommended_default: str
    authorization_effect: str


class Mi001BnbTrialReadinessGapResponse(BaseModel):
    generated_from: Literal["mi001_bnb_trial_readiness_gap_v1"] = "mi001_bnb_trial_readiness_gap_v1"
    candidate_id: Literal["MI-001-BNB-LONG"] = "MI-001-BNB-LONG"
    strategy_group_id: Literal["MI-001"] = "MI-001"
    symbol: Literal["BNB/USDT:USDT"] = "BNB/USDT:USDT"
    side: Literal["long"] = "long"
    current_phase: str
    current_status: list[str]
    readiness_status: Literal["not_testnet_ready_not_live_ready"] = "not_testnet_ready_not_live_ready"
    gap_matrix: list[BnbTrialReadinessGate]
    testnet_rehearsal_design: BnbTrialDesignSummary
    small_live_trial_readiness_draft: BnbTrialDesignSummary
    execution_boundary_audit: list[BnbExecutionBoundaryItem]
    owner_policy_checklist: list[BnbOwnerPolicyItem]
    api_console_impact: dict[str, str | bool]
    non_permissions: dict[str, bool] = Field(default_factory=lambda: _non_permissions())
    source_refs: list[str] = Field(default_factory=lambda: _source_refs())
    live_ready: Literal[False] = False


def build_mi001_bnb_trial_readiness_gap() -> Mi001BnbTrialReadinessGapResponse:
    """Return a structured Owner-review map for BNB trial-readiness gaps."""

    return Mi001BnbTrialReadinessGapResponse(
        current_phase="live_observation_case_plus_trial_design_draft",
        current_status=[
            "live_readonly_observation_active_as_evidence",
            "BNB live case #001 has 1h/4h adverse path",
            "12h/24h/72h forward reviews remain pending",
            "bounded trial design exists as design_only",
            "no execution intent, no order, no runtime start",
        ],
        gap_matrix=_gap_matrix(),
        testnet_rehearsal_design=_testnet_design(),
        small_live_trial_readiness_draft=_small_live_design(),
        execution_boundary_audit=_execution_boundary_audit(),
        owner_policy_checklist=_owner_policy_checklist(),
        api_console_impact={
            "endpoint": "/api/brc/readiness/mi001-bnb/trial-gap",
            "console_surface": "/strategy-groups read-only panel",
            "runtime_effect": "none",
            "execution_or_order_effect": "none",
            "display_only": True,
        },
    )


def _gap_matrix() -> list[BnbTrialReadinessGate]:
    rows = [
        (
            "G01",
            "Account facts",
            "partially_available_needs_bnb_refresh",
            True,
            True,
            "src/application/trial_readiness_account_facts.py; reports/.../live_account_facts_readiness_result.md",
            "BNB readiness must refresh account equity and available margin at rehearsal/live decision time.",
            "Run read-only Binance USDT futures account facts refresh immediately before any rehearsal artifact.",
            "Sizing and max-loss assumptions may be stale.",
            True,
        ),
        (
            "G02",
            "BNB Operation Layer cap",
            "missing_bnb_specific_cap",
            True,
            True,
            "src/application/brc_operation_layer.py; reports/.../trial_readiness_transition_apply_result.md",
            "SOL cap exists from prior readiness work, but BNB-specific notional/loss cap is not established.",
            "Create metadata-only BNB Operation Layer cap with max leverage 5x and no expansion rules.",
            "Owner could review a signal without a BNB-specific risk ceiling.",
            True,
        ),
        (
            "G03",
            "Global Kill Switch",
            "state_must_be_rechecked",
            True,
            True,
            "src/application/global_kill_switch.py; src/infrastructure/pg_global_kill_switch_repository.py",
            "Current readiness cannot assume the prior SOL GKS state is still current for BNB.",
            "Read GKS state and require non-blocking state for testnet, fail-closed for live if unclear.",
            "A blocking fail-closed state could be bypassed conceptually.",
            True,
        ),
        (
            "G04",
            "Startup guard",
            "runtime_bound_guard_required",
            True,
            True,
            "src/application/startup_trading_guard.py; src/interfaces/api_console_runtime.py",
            "StartupTradingGuardService is process-local runtime-owned state; offline arm would be fake readiness.",
            "Use an explicit guard-only preflight/control surface before rehearsal; do not start strategy execution.",
            "Runtime could start without an explicit operator startup check.",
            True,
        ),
        (
            "G05",
            "Execution permission",
            "read_only_by_default",
            True,
            True,
            "src/application/execution_permission.py",
            "Current BNB chain is observation/design only and does not request execution permission.",
            "Keep final permission at read_only until a separate Owner-authorized rehearsal task.",
            "Observation could be mistaken for permission escalation.",
            True,
        ),
        (
            "G06",
            "Order path",
            "not_touched_by_observation_chain",
            True,
            True,
            "src/application/order_lifecycle_service.py; src/infrastructure/pg_order_repository.py",
            "Order path exists in the repo but is outside the BNB observation/design chain.",
            "For testnet only, require a separately authorized, isolated order-path rehearsal with testnet config.",
            "A design artifact could accidentally become an order path if not isolated.",
            True,
        ),
        (
            "G07",
            "Risk capital",
            "policy_known_needs_current_value",
            True,
            True,
            "reports/.../mi001_bnb_bounded_trial_design_v0.md",
            "Dedicated account equity is the policy, but current value must be captured before rehearsal/live.",
            "Compute risk capital from fresh read-only account facts; no top-up/transfer/withdrawal.",
            "Trial size could exceed the Owner's intended capital boundary.",
            True,
        ),
        (
            "G08",
            "Leverage and max notional",
            "draft_only",
            True,
            True,
            "reports/.../mi001_bnb_bounded_trial_design_v0.md",
            "Draft says max 5x and min(equity*5, available_margin*5, Operation cap), but BNB cap is missing.",
            "Freeze BNB max leverage 5x and BNB notional cap before any rehearsal artifact.",
            "Rehearsal/live review could overstate allowed notional.",
            True,
        ),
        (
            "G09",
            "Max loss / attempts / position count",
            "draft_only",
            True,
            True,
            "reports/.../mi001_bnb_bounded_trial_design_v0.md",
            "Design draft has max attempts and max simultaneous position, not canonical rehearsal config.",
            "Record max attempts=3 draft, max simultaneous position=1, max loss bounded by dedicated equity.",
            "Repeated manual confirmations could create unintended exposure.",
            True,
        ),
        (
            "G10",
            "Exit / stop model",
            "draft_only_needs_rehearsal_artifact",
            True,
            True,
            "reports/.../mi001_bnb_bounded_trial_design_v0.md",
            "Time/manual/Operation Layer/invalidation stops are drafted, not proven operationally.",
            "Define testnet stop procedure and manual Owner stop evidence before any order-path rehearsal.",
            "A position could be opened without an audited exit/stop process.",
            True,
        ),
        (
            "G11",
            "No-chase / wait-for-confirmation",
            "required_by_case_001_path",
            True,
            True,
            "reports/.../mi001_bnb_live_case_001.md",
            "1h/4h adverse path requires no-chase and confirmation gate before any rehearsal consideration.",
            "Keep BNB case in review until later forward windows or a new confirmation case is reviewed.",
            "Owner could chase a local exhaustion event.",
            True,
        ),
        (
            "G12",
            "Active position / open orders",
            "not_checked_for_bnb_current_task",
            True,
            True,
            "src/infrastructure/pg_position_repository.py; src/infrastructure/pg_order_repository.py",
            "BNB-specific active position/open order state must be checked immediately before rehearsal/live.",
            "Read PG/runtime order and position state; block if BNB position/order exists or unknown.",
            "Duplicate or conflicting exposure could be created.",
            True,
        ),
        (
            "G13",
            "Reconciliation",
            "required_not_proven_for_bnb",
            True,
            True,
            "src/application/reconciliation.py; src/application/startup_reconciliation_service.py",
            "BNB rehearsal/live requires account/order/position reconciliation evidence, but current chain is observation only.",
            "Run read-only reconciliation precheck in the rehearsal task; block on mismatch.",
            "Local state could diverge from exchange state.",
            True,
        ),
        (
            "G14",
            "Evidence / audit logging",
            "observation_logging_ready_trial_audit_needed",
            True,
            True,
            "brc_strategy_group_observations; brc_strategy_group_forward_reviews; src/application/brc_operation_layer.py",
            "Observation and forward review are persisted; rehearsal/live audit artifact is not yet defined.",
            "Require Operation Layer preflight/audit records for any rehearsal handoff.",
            "Owner decisions and boundary checks may be hard to reconstruct.",
            True,
        ),
        (
            "G15",
            "Observation case queue",
            "available_for_would_enter_review",
            False,
            False,
            "src/application/strategy_group_observation_case_queue.py",
            "Queue is an Owner review surface only, not a rehearsal permission source.",
            "Continue using it for signal review and forward-window status.",
            "Case visibility could be mistaken for actionability.",
            False,
        ),
        (
            "G16",
            "Forward review",
            "1h_4h_completed_12h_24h_72h_pending",
            True,
            True,
            "reports/.../bnb_live_case_forward_review_continuation.md",
            "Later windows remain pending and the early path is adverse.",
            "Wait for due windows or require a new confirmation case before rehearsal design escalation.",
            "Trial design could ignore adverse path risk.",
            True,
        ),
        (
            "G17",
            "Owner confirmation",
            "design_review_only_no_authorization",
            True,
            True,
            "reports/.../mi001_bnb_owner_policy_checklist.md",
            "No Owner testnet rehearsal or small-live final approval exists for BNB.",
            "Use explicit Owner decision checklist and separate final authorization record.",
            "Review artifacts could be misread as start approval.",
            True,
        ),
        (
            "G18",
            "Testnet rehearsal",
            "design_only_not_started",
            True,
            False,
            "docs/ops/plc-phase5e-controlled-multi-symbol-testnet-runtime-rehearsal.md; scripts/start_brc_local_testnet.sh",
            "Repo has historical testnet surfaces, but no BNB-specific Owner-confirmed rehearsal artifact.",
            "Prepare a BNB-specific testnet rehearsal plan with isolated testnet config and no live authorization.",
            "Testing order path could touch wrong environment or symbol.",
            True,
        ),
        (
            "G19",
            "Small live trial",
            "draft_only_not_authorized",
            False,
            True,
            "reports/.../mi001_bnb_small_live_trial_readiness_draft.md",
            "Small-live requires separate final Owner approval after testnet/manual rehearsal prerequisites.",
            "Do not proceed until all gates pass and Owner grants final live-trial approval.",
            "Real funds could be used without final decision and audit trail.",
            True,
        ),
    ]
    return [
        BnbTrialReadinessGate(
            gate_id=gate_id,
            gate_name=gate_name,
            current_status=current_status,
            required_for_testnet_rehearsal=required_for_testnet,
            required_for_small_live_trial=required_for_live,
            existing_source_or_code_path=source,
            gap=gap,
            recommended_action=action,
            risk_if_skipped=risk,
            owner_intervention_required=owner_required,
        )
        for (
            gate_id,
            gate_name,
            current_status,
            required_for_testnet,
            required_for_live,
            source,
            gap,
            action,
            risk,
            owner_required,
        ) in rows
    ]


def _testnet_design() -> BnbTrialDesignSummary:
    return BnbTrialDesignSummary(
        design_id="MI-001-BNB-owner-confirmed-testnet-rehearsal-v0",
        status=["design_only", "not_started", "not_live_authorized", "not_execution_ready"],
        mode="Owner confirms each entry; would_enter enters Owner review, not order",
        trigger="BNB live observation would_enter plus explicit Owner review decision",
        allowed_scope=[
            "Binance USDT futures testnet only if separately authorized",
            "BNB/USDT:USDT long only",
            "order path may be tested only in testnet controlled rehearsal",
        ],
        risk_controls=[
            "max_leverage=5x",
            "max_attempts draft=3",
            "max_simultaneous_position=1",
            "no add-to-loser",
            "no auto top-up / transfer / withdrawal",
            "no symbol/side/leverage expansion",
        ],
        exit_controls=[
            "time stop",
            "manual stop",
            "Operation Layer stop",
            "invalidation stop",
        ],
        recordkeeping=[
            "testnet order id",
            "fill/reject",
            "position state",
            "PnL",
            "Owner review note",
            "Operation Layer audit refs",
        ],
        blockers=[
            "BNB-specific Operation Layer cap missing",
            "fresh account facts and BNB active position/order facts required",
            "startup guard/GKS/reconciliation prechecks required",
            "explicit Owner testnet rehearsal authorization missing",
        ],
        non_permissions=_non_permission_list(),
    )


def _small_live_design() -> BnbTrialDesignSummary:
    return BnbTrialDesignSummary(
        design_id="MI-001-BNB-small-live-trial-readiness-draft-v0",
        status=["draft_only", "not_authorized", "not_started", "requires_owner_final_approval"],
        mode="Owner manually confirms each entry after all gates pass",
        trigger="separate final Owner approval after observation review and rehearsal prerequisites",
        allowed_scope=[
            "Binance USDT futures current dedicated account only",
            "BNB/USDT:USDT long only",
            "max leverage 5x",
            "no automatic entry",
        ],
        risk_controls=[
            "trial_risk_capital=current dedicated account equity",
            "max_total_loss=current dedicated account equity",
            "max_notional=min(equity*5, available_margin*5, BNB Operation Layer cap)",
            "no add-to-loser",
            "no auto top-up / transfer / withdrawal",
        ],
        exit_controls=[
            "time stop",
            "manual stop",
            "Operation Layer stop",
            "kill-switch rollback",
            "invalidation stop",
        ],
        recordkeeping=[
            "Owner final approval record",
            "fresh account facts",
            "preflight audit",
            "entry/exit evidence",
            "post-trial review artifact",
        ],
        blockers=[
            "not authorized",
            "BNB-specific cap and final preflight missing",
            "forward review still pending",
            "testnet/manual rehearsal not completed",
        ],
        non_permissions=_non_permission_list(),
    )


def _execution_boundary_audit() -> list[BnbExecutionBoundaryItem]:
    return [
        BnbExecutionBoundaryItem(
            boundary="ExecutionIntent path exists",
            code_path="src/infrastructure/pg_execution_intent_repository.py; src/domain/execution_intent.py",
            current_assessment="available in repo but not touched by MI/CPM observation, case queue, or this BNB readiness gap API",
            bnb_chain_touches_path=False,
            required_control="Any future use requires separate Owner authorization and permission resolver pass.",
        ),
        BnbExecutionBoundaryItem(
            boundary="Order creation/cancel path exists",
            code_path="src/application/order_lifecycle_service.py; src/infrastructure/pg_order_repository.py; src/infrastructure/exchange_gateway.py",
            current_assessment="order path exists for runtime/testnet infrastructure, but the BNB chain reads observation evidence only",
            bnb_chain_touches_path=False,
            required_control="Keep observation/case queue/design endpoints free of order repository and gateway dependencies.",
        ),
        BnbExecutionBoundaryItem(
            boundary="Execution permission resolver",
            code_path="src/application/execution_permission.py",
            current_assessment="resolver defaults to read_only unless contributors explicitly allow more; this API grants nothing",
            bnb_chain_touches_path=False,
            required_control="Future rehearsal must prove final permission separately and remain testnet-scoped.",
        ),
        BnbExecutionBoundaryItem(
            boundary="Runtime control surface",
            code_path="src/interfaces/api_console_runtime.py",
            current_assessment="contains runtime control and startup guard endpoints; current BNB readiness API does not call them",
            bnb_chain_touches_path=False,
            required_control="Startup guard/GKS checks must be read/preflight only until a separate rehearsal task.",
        ),
        BnbExecutionBoundaryItem(
            boundary="Observation and case queue",
            code_path="src/application/strategy_group_live_readonly_observation.py; src/application/strategy_group_observation_case_queue.py",
            current_assessment="read-only evidence and Owner review models with explicit non-permission flags",
            bnb_chain_touches_path=True,
            required_control="Never convert signal or case queue item directly into execution intent.",
        ),
    ]


def _owner_policy_checklist() -> list[BnbOwnerPolicyItem]:
    return [
        BnbOwnerPolicyItem(
            decision_id="D01",
            question="Continue observation only?",
            options=["continue_observation_only", "prepare_testnet_rehearsal", "pause_bnb_case"],
            recommended_default="continue_observation_only",
            authorization_effect="No execution or order permission.",
        ),
        BnbOwnerPolicyItem(
            decision_id="D02",
            question="Wait for 12h/24h/72h forward review before any rehearsal prep?",
            options=["wait_all_windows", "wait_12h_24h", "allow_design_only_parallel_work"],
            recommended_default="wait_all_windows",
            authorization_effect="Review timing only; not trial authorization.",
        ),
        BnbOwnerPolicyItem(
            decision_id="D03",
            question="Accept early adverse-path risk as a blocker requiring no-chase and wait-for-confirmation?",
            options=["accept_as_required_gate", "reject_case", "continue_observation"],
            recommended_default="accept_as_required_gate",
            authorization_effect="Adds design constraint only.",
        ),
        BnbOwnerPolicyItem(
            decision_id="D04",
            question="Prepare Owner-confirmed testnet rehearsal artifact?",
            options=["prepare_testnet_artifact", "defer", "observation_only"],
            recommended_default="defer",
            authorization_effect="Artifact design only unless a separate testnet apply/start task is authorized.",
        ),
        BnbOwnerPolicyItem(
            decision_id="D05",
            question="Accept dedicated-account equity as max risk capital model for any future small live trial?",
            options=["accept_model", "require_smaller_cap", "do_not_live_trial"],
            recommended_default="require_smaller_cap",
            authorization_effect="Policy preference only; not live authorization.",
        ),
    ]


def _non_permissions() -> dict[str, bool]:
    return {
        "no_trial_start": True,
        "no_testnet_rehearsal_start": True,
        "no_small_live_authorization": True,
        "no_execution_intent": True,
        "no_order_permission": True,
        "no_execution_permission": True,
        "no_runtime_start": True,
        "no_leverage_change": True,
        "no_transfer_or_withdrawal": True,
    }


def _non_permission_list() -> list[str]:
    return [key for key, value in _non_permissions().items() if value]


def _source_refs() -> list[str]:
    return [
        "reports/directional-opportunity-broad-smoke-20260529/mi001_bnb_live_case_001.md",
        "reports/directional-opportunity-broad-smoke-20260529/mi001_bnb_bounded_trial_design_v0.md",
        "reports/directional-opportunity-broad-smoke-20260529/bnb_live_case_forward_review_continuation.md",
        "reports/directional-opportunity-broad-smoke-20260529/observation_case_queue_v1_result.md",
        "src/application/execution_permission.py",
        "src/application/brc_operation_layer.py",
        "src/interfaces/api_console_runtime.py",
    ]
