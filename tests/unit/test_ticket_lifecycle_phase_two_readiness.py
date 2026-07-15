from __future__ import annotations

from sqlalchemy import text

from scripts.verify_ticket_lifecycle_phase_two_readiness import (
    evaluate_phase_two_readiness,
    readiness_exit_code,
)
from tests.unit.test_capital_safety_scope_freeze_gate import _insert_scope_freeze
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)
from tests.unit.test_ticket_bound_exchange_command_worker import (
    _create_ready_protected_submit,
    _prepare_real_submit,
)
from src.application.readmodels.lifecycle_mutation_enablement_proof import (
    ActionTimeCertificationReferenceV2,
    LaneSourceWatermarkV1,
    LifecycleMutationEnablementProof,
)


def _install_v2_capability_proof(conn) -> None:
    action_time = ActionTimeCertificationReferenceV2(
        stage="post_canary",
        target_runtime_head="a" * 40,
        certification_input_digest="sha256:" + "b" * 64,
        release_activation_outcome_id="activation-1",
        release_activation_source_watermark="release:1",
        lane_source_watermarks=(LaneSourceWatermarkV1(lane_scope_key="scope-1", lane_identity_key="lane-1", source_watermark="watermark-1", process_outcome_id="process-1"),),
        fact_snapshot_ids=("fact-1",),
        fact_set_digest="sha256:" + "c" * 64,
        fact_min_valid_until_ms=NOW_MS + 60_000,
        deploy_nonce="nonce-1",
    )
    proof = LifecycleMutationEnablementProof(
        target_runtime_head="a" * 40,
        lane_identity_digest="sha256:" + "d" * 64,
        action_time_certification_ref=action_time.certification_ref(),
        action_time_certification_payload=action_time,
        certification_projection_digest="sha256:" + "e" * 64,
    )
    conn.execute(
        text(
            "UPDATE brc_runtime_capabilities_current SET proof_schema=:schema, "
            "proof_payload=:payload, certification_ref=:ref WHERE capability_id="
            "'ticket_lifecycle_durable_mutation'"
        ),
        {
            "schema": proof.proof_schema,
            "payload": __import__("json").dumps(proof.canonical_payload()),
            "ref": proof.lifecycle_certification_ref(),
        },
    )


def _insert_real_lifecycle(
    conn,
    *,
    suffix: str,
    status: str,
    protection_complete: bool,
    reconciled_with_exchange: bool | None = None,
    first_blocker: str | None = None,
) -> None:
    attempt_id = f"attempt-{suffix}"
    ticket_id = f"ticket-{suffix}"
    protection_id = f"protection-{suffix}"
    conn.execute(
        text(
            """
            INSERT INTO brc_ticket_bound_protected_submit_attempts (
                protected_submit_attempt_id, ticket_id, finalgate_pass_id,
                operation_layer_handoff_id, operation_submit_command_id,
                runtime_safety_snapshot_id, action_time_lane_input_id,
                strategy_group_id, symbol, side, runtime_profile_id, submit_mode,
                status, submit_allowed, blockers, warnings, trusted_fact_refs,
                submit_request, submit_result, identity_evidence,
                official_operation_layer_submit_called, exchange_write_called,
                order_created, order_lifecycle_called,
                withdrawal_or_transfer_created, live_profile_changed,
                order_sizing_changed, authority_boundary, created_at_ms,
                updated_at_ms, signal_grade, required_execution_mode,
                execution_eligible, authority_source_ref
            ) VALUES (
                :attempt_id, :ticket_id, :finalgate_pass_id, :handoff_id,
                :command_id, :safety_id, :lane_id, 'SOR-001', 'AVAXUSDT',
                'long', 'runtime-profile-1', 'real_gateway_action', 'submitted',
                true, '[]', '[]', '{}', '{}', '{}', '{}', true, true, true,
                true, false, false, false, 'ticket_bound_submit', :now_ms,
                :now_ms, 'trial_grade_signal', 'trial_live', true, 'unit:test'
            )
            """
        ),
        {
            "attempt_id": attempt_id,
            "ticket_id": ticket_id,
            "finalgate_pass_id": f"finalgate-{suffix}",
            "handoff_id": f"handoff-{suffix}",
            "command_id": f"command-{suffix}",
            "safety_id": f"safety-{suffix}",
            "lane_id": f"lane-{suffix}",
            "now_ms": NOW_MS,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO brc_ticket_bound_exit_protection_sets (
                exit_protection_set_id, ticket_id, protected_submit_attempt_id,
                entry_local_order_id, entry_exchange_order_id, strategy_group_id,
                symbol, side, entry_filled_qty, entry_avg_price, status,
                sl_order_id, tp1_order_id, runner_qty, protection_complete,
                reconciled_with_exchange, first_blocker, blockers, warnings,
                authority_boundary, created_at_ms, updated_at_ms
            ) VALUES (
                :protection_id, :ticket_id, :attempt_id, :entry_local_id,
                :entry_exchange_id, 'SOR-001', 'AVAXUSDT', 'long', 65, 6.65,
                :protection_status, :sl_id, :tp1_id, 33, :protection_complete,
                :reconciled_with_exchange, :first_blocker, :blockers, '[]',
                'ticket_bound_exit_protection', :now_ms, :now_ms
            )
            """
        ),
        {
            "protection_id": protection_id,
            "ticket_id": ticket_id,
            "attempt_id": attempt_id,
            "entry_local_id": f"entry-local-{suffix}",
            "entry_exchange_id": f"entry-exchange-{suffix}",
            "protection_status": "reconciled" if protection_complete else "failed",
            "sl_id": f"sl-{suffix}" if protection_complete else None,
            "tp1_id": f"tp1-{suffix}" if protection_complete else None,
            "protection_complete": protection_complete,
            "reconciled_with_exchange": (
                protection_complete
                if reconciled_with_exchange is None
                else reconciled_with_exchange
            ),
            "first_blocker": first_blocker,
            "blockers": "[]" if first_blocker is None else f'["{first_blocker}"]',
            "now_ms": NOW_MS,
        },
    )
    conn.execute(
        text(
            """
            INSERT INTO brc_ticket_bound_order_lifecycle_runs (
                lifecycle_run_id, ticket_id, protected_submit_attempt_id,
                strategy_group_id, symbol, side, runtime_profile_id, status,
                entry_local_order_id, entry_exchange_order_id,
                entry_fill_confirmed, entry_filled_qty, entry_avg_price,
                exit_protection_set_id, first_blocker, blockers, warnings,
                authority_boundary, created_at_ms, updated_at_ms
            ) VALUES (
                :lifecycle_id, :ticket_id, :attempt_id, 'SOR-001', 'AVAXUSDT',
                'long', 'runtime-profile-1', :status, :entry_local_id,
                :entry_exchange_id, true, 65, 6.65, :protection_id,
                :first_blocker, :blockers, '[]', 'ticket_bound_lifecycle',
                :now_ms, :now_ms
            )
            """
        ),
        {
            "lifecycle_id": f"lifecycle-{suffix}",
            "ticket_id": ticket_id,
            "attempt_id": attempt_id,
            "status": status,
            "entry_local_id": f"entry-local-{suffix}",
            "entry_exchange_id": f"entry-exchange-{suffix}",
            "protection_id": protection_id,
            "first_blocker": first_blocker,
            "blockers": "[]" if first_blocker is None else f'["{first_blocker}"]',
            "now_ms": NOW_MS,
        },
    )


def test_phase_two_accepts_protected_lifecycle_with_disabled_capability_and_safe_mode(
    pg_control_connection,
):
    pg_control_connection.execute(
        text(
            "UPDATE brc_runtime_capabilities_current "
            "SET status = 'disabled', certification_ref = 'unit:phase-one' "
            "WHERE capability_id = 'ticket_lifecycle_durable_mutation'"
        )
    )
    pg_control_connection.execute(
        text(
            "INSERT INTO brc_exchange_account_modes_current ("
            "account_mode_current_id, account_id, exchange_id, runtime_profile_id, "
            "position_mode, dual_side_position, position_mode_safe, status, "
            "fact_snapshot_id, source_kind, source_ref, observed_at_ms, "
            "valid_until_ms, updated_at_ms) VALUES ("
            "'mode-current-1', 'account-1', 'binance_usdm', 'profile-1', "
            "'one_way', 0, 1, 'current', 'fact-1', 'signed_get', "
            "'unit:/positionSide/dual', :now_ms, :valid_until_ms, :now_ms)"
        ),
        {"now_ms": NOW_MS, "valid_until_ms": NOW_MS + 60_000},
    )
    _insert_real_lifecycle(
        pg_control_connection,
        suffix="phase-two-protected",
        status="position_protected",
        protection_complete=True,
    )

    payload = evaluate_phase_two_readiness(
        pg_control_connection,
        now_ms=NOW_MS + 1_000,
    )

    assert payload["status"] == "phase_two_ready"
    assert payload["blockers"] == []
    assert payload["counts"] == {
        "safe_account_mode_count": 1,
        "critical_exchange_commands": 0,
        "active_domain_holds": 0,
        "active_real_lifecycles": 1,
        "protected_active_real_lifecycles": 1,
        "unsafe_active_real_lifecycles": 0,
        "unprotected_real_attempts": 0,
    }


def test_phase_two_rejects_enabled_capability_or_missing_account_truth(
    pg_control_connection,
):
    payload = evaluate_phase_two_readiness(
        pg_control_connection,
        now_ms=NOW_MS + 1_000,
    )

    assert payload["status"] == "blocked"
    assert "phase_two_capability_already_enabled" in payload["blockers"]
    assert "phase_two_safe_account_mode_count:0" in payload["blockers"]


def test_phase_two_blocks_prepared_exchange_command(pg_control_connection):
    _install_v2_capability_proof(pg_control_connection)
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)

    payload = evaluate_phase_two_readiness(
        pg_control_connection,
        now_ms=NOW_MS + 1_000,
        deploy_quiescence=True,
    )

    assert payload["status"] == "blocked"
    assert "phase_two_critical_exchange_commands:3" in payload["blockers"]


def test_phase_two_ignores_closed_historical_hard_stop_without_active_freeze(
    pg_control_connection,
):
    _install_v2_capability_proof(pg_control_connection)
    ids = _create_ready_protected_submit(pg_control_connection)
    _prepare_real_submit(pg_control_connection, ids)
    pg_control_connection.execute(
        text(
            "UPDATE brc_ticket_bound_exchange_commands "
            "SET command_state = 'hard_stopped'"
        )
    )

    payload = evaluate_phase_two_readiness(
        pg_control_connection,
        now_ms=NOW_MS + 1_000,
        deploy_quiescence=True,
    )

    assert payload["status"] == "phase_two_ready"
    assert payload["counts"]["critical_exchange_commands"] == 0


def test_deploy_quiescence_ignores_expired_account_mode_but_not_live_risk(
    pg_control_connection,
):
    payload = evaluate_phase_two_readiness(
        pg_control_connection,
        now_ms=NOW_MS + 1_000,
        deploy_quiescence=True,
    )

    assert payload["status"] == "phase_two_ready"
    assert payload["mode"] == "deploy_quiescence"
    assert payload["blockers"] == []
    assert readiness_exit_code(payload) == 0
    assert payload["counts"]["safe_account_mode_count"] == 0
    assert payload["exchange_read_called"] is False
    assert payload["exchange_write_called"] is False
    assert payload["runtime_state_mutated"] is False


def test_pre_switch_mode_still_rejects_active_lifecycle_risk(pg_control_connection):
    pg_control_connection.execute(
        text(
            "INSERT INTO brc_exchange_account_modes_current ("
            "account_mode_current_id, account_id, exchange_id, runtime_profile_id, "
            "position_mode, dual_side_position, position_mode_safe, status, "
            "fact_snapshot_id, source_kind, source_ref, observed_at_ms, "
            "valid_until_ms, updated_at_ms) VALUES ("
            "'mode-current-risk', 'account-1', 'binance_usdm', 'profile-1', "
            "'one_way', 0, 1, 'current', 'fact-risk', 'signed_get', "
            "'unit:/positionSide/dual', :now_ms, :valid_until_ms, :now_ms)"
        ),
        {"now_ms": NOW_MS, "valid_until_ms": NOW_MS + 60_000},
    )
    _insert_scope_freeze(
        pg_control_connection,
        first_blocker="position_closed_protection_live",
    )

    payload = evaluate_phase_two_readiness(
        pg_control_connection,
        now_ms=NOW_MS + 1_000,
        deploy_quiescence=True,
    )

    assert payload["status"] == "blocked"
    assert readiness_exit_code(payload) == 2
    assert payload["first_blocker"] == "phase_two_active_domain_holds:1"
    assert payload["counts"]["active_domain_holds"] == 1


def test_deploy_quiescence_accepts_protection_complete_position(pg_control_connection):
    _insert_real_lifecycle(
        pg_control_connection,
        suffix="position-protected",
        status="position_protected",
        protection_complete=True,
    )

    payload = evaluate_phase_two_readiness(
        pg_control_connection,
        now_ms=NOW_MS + 1_000,
        deploy_quiescence=True,
    )

    assert payload["status"] == "phase_two_ready"
    assert payload["blockers"] == []
    assert payload["counts"]["active_real_lifecycles"] == 1
    assert payload["counts"]["protected_active_real_lifecycles"] == 1
    assert payload["counts"]["unsafe_active_real_lifecycles"] == 0


def test_deploy_quiescence_accepts_protection_complete_runner(pg_control_connection):
    _insert_real_lifecycle(
        pg_control_connection,
        suffix="runner-protected",
        status="runner_protected",
        protection_complete=True,
    )

    payload = evaluate_phase_two_readiness(
        pg_control_connection,
        now_ms=NOW_MS + 1_000,
        deploy_quiescence=True,
    )

    assert payload["status"] == "phase_two_ready"
    assert payload["counts"]["protected_active_real_lifecycles"] == 1
    assert payload["counts"]["unsafe_active_real_lifecycles"] == 0


def test_deploy_quiescence_rejects_active_lifecycle_with_incomplete_protection(
    pg_control_connection,
):
    _insert_real_lifecycle(
        pg_control_connection,
        suffix="unprotected",
        status="entry_filled",
        protection_complete=False,
        first_blocker="exit_protection_incomplete",
    )

    payload = evaluate_phase_two_readiness(
        pg_control_connection,
        now_ms=NOW_MS + 1_000,
        deploy_quiescence=True,
    )

    assert payload["status"] == "blocked"
    assert "phase_two_unsafe_active_real_lifecycles:1" in payload["blockers"]
    assert payload["counts"]["protected_active_real_lifecycles"] == 0
    assert payload["counts"]["unsafe_active_real_lifecycles"] == 1


def test_deploy_quiescence_rejects_unreconciled_protection(pg_control_connection):
    _insert_real_lifecycle(
        pg_control_connection,
        suffix="unreconciled",
        status="position_protected",
        protection_complete=True,
        reconciled_with_exchange=False,
    )

    payload = evaluate_phase_two_readiness(
        pg_control_connection,
        now_ms=NOW_MS + 1_000,
        deploy_quiescence=True,
    )

    assert payload["status"] == "blocked"
    assert "phase_two_unsafe_active_real_lifecycles:1" in payload["blockers"]
