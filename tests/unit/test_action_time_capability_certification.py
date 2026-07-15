from __future__ import annotations

from copy import deepcopy

import pytest

from src.application.action_time import capability_certification as certification_module
from scripts.seed_runtime_control_state_foundation import build_seed_rows
from src.application.action_time.capability_certification import (
    ActionTimeCapabilityIdentityError,
    build_action_time_capability_identities,
    current_action_time_capability_truth_by_lane,
    current_runtime_head,
)


RUNTIME_HEAD = "a" * 40


def _fact_digest_rows():
    return (
        certification_module.ActionTimeFactDigestRowV1(
            fact_snapshot_id="fact:digest:test",
            strategy_group_id="SOR-001",
            symbol="ETHUSDT",
            side="long",
            runtime_profile_id="owner-runtime-console-v1",
            fact_surface="action_time_private",
            source_kind="live_account",
            source_ref="pytest",
            computed=True,
            satisfied=True,
            freshness_state="fresh",
            failed_facts=[],
            fact_values={"mark_price": "1888.50"},
            blocker_class=None,
            observed_at_ms=1_800_000_000_000,
            valid_until_ms=1_800_000_060_000,
        ),
    )


def _bounded_certification_state() -> dict[str, object]:
    state = _control_state()
    columns = {
        "strategy_groups": ("strategy_group_id", "current_version_id", "status"),
        "strategy_group_versions": (
            "strategy_group_version_id",
            "strategy_group_id",
            "status",
        ),
        "strategy_runtime_instances": (
            "runtime_instance_id",
            "strategy_family_id",
            "strategy_family_version_id",
            "symbol",
            "side",
            "status",
        ),
        "candidate_scope": (
            "candidate_scope_id",
            "strategy_group_id",
            "symbol",
            "asset_class",
            "side",
            "policy_current_id",
            "priority_rank",
            "status",
        ),
        "candidate_scope_event_bindings": (
            "binding_id",
            "candidate_scope_id",
            "event_spec_id",
            "strategy_group_id",
            "symbol",
            "side",
            "status",
        ),
        "runtime_scope_bindings": (
            "runtime_scope_binding_id",
            "candidate_scope_id",
            "strategy_group_id",
            "symbol",
            "side",
            "policy_current_id",
            "runtime_profile_id",
            "selected_strategygroup_scope",
            "symbol_side_scope_closed",
            "notional_leverage_scope_closed",
            "live_submit_allowed",
            "server_runtime_coverage_required",
            "status",
            "conditional_hard_gates",
        ),
        "strategy_side_event_specs": (
            "event_spec_id",
            "strategy_group_id",
            "strategy_group_version_id",
            "event_spec_version",
            "event_id",
            "side",
            "timeframe",
            "execution_eligibility_enabled",
            "declared_signal_grade",
            "declared_required_execution_mode",
            "freshness_window_ms",
            "time_authority",
            "protection_ref_type",
            "status",
        ),
        "owner_policy_current": (
            "policy_current_id",
            "strategy_group_id",
            "symbol",
            "side",
            "runtime_profile_id",
            "enabled_state",
            "pretrade_candidate_allowed",
            "action_time_rehearsal_allowed",
            "live_submit_allowed",
            "planned_stop_risk_fraction",
            "max_initial_margin_utilization",
            "max_leverage",
            "attempt_cap",
            "policy_event_ids",
        ),
        "strategy_event_required_facts": (
            "event_required_fact_id",
            "event_spec_id",
            "required_facts_version_id",
            "fact_key",
            "fact_role",
            "fact_surface",
            "operator",
            "expected_value",
            "disable_on_match",
            "freshness_ms",
            "required_for_promotion",
            "required_for_ticket",
            "required_for_finalgate",
            "missing_blocker_class",
            "failed_blocker_class",
            "value_source",
            "status",
        ),
    }
    bounded = {
        key: [{name: row.get(name) for name in names} for row in state[key]]
        for key, names in columns.items()
    }
    bounded["runtime_process_outcomes"] = [
        {
            "process_outcome_id": "process_outcome:release",
            "process_name": "runtime_release_activation",
            "scope_key": "production:tokyo",
            "process_state": "succeeded",
            "runtime_head": RUNTIME_HEAD,
            "source_watermark": "runtime_release_activation:watermark-a",
            "updated_at_ms": 1_800_000_000_100,
        }
    ]
    bounded["current_runtime_head"] = RUNTIME_HEAD
    return bounded


def test_builds_post_canary_action_time_v2_reference_from_frozen_inputs():
    state = _bounded_certification_state()
    facts = _fact_digest_rows()
    prepared = certification_module.prepare_action_time_capability_certification(
        state,
        runtime_head=RUNTIME_HEAD,
        fact_digest_rows=facts,
    )

    reference = certification_module.build_action_time_certification_reference_v2(
        prepared=prepared,
        control_state=state,
        fact_digest_rows=facts,
        stage="post_canary",
        deploy_nonce="deploy-nonce-1",
    )

    assert reference.stage == "post_canary"
    assert reference.target_runtime_head == RUNTIME_HEAD
    assert reference.fact_min_valid_until_ms == facts[0].valid_until_ms
    assert reference.certification_ref().startswith("action-time-cert:v2:")
    assert len(reference.lane_source_watermarks) == 22


def test_certification_input_digest_is_typed_stable_and_release_bound() -> None:
    state = _bounded_certification_state()
    prepared = certification_module.prepare_action_time_capability_certification(
        state,
        runtime_head=RUNTIME_HEAD,
        fact_digest_rows=_fact_digest_rows(),
    )
    reordered = deepcopy(state)
    for value in reordered.values():
        if isinstance(value, list):
            value.reverse()
    stable = certification_module.prepare_action_time_capability_certification(
        reordered,
        runtime_head=RUNTIME_HEAD,
        fact_digest_rows=_fact_digest_rows(),
    )

    assert prepared.digest_schema == (
        "brc.action_time_capability_certification_input.v1"
    )
    assert prepared.canonical_encoding == "brc.typed_canonical_json.v1"
    assert prepared.certification_input_digest == stable.certification_input_digest

    changed = deepcopy(state)
    changed["runtime_process_outcomes"][0]["source_watermark"] = (
        "runtime_release_activation:watermark-b"
    )
    changed_prepared = (
        certification_module.prepare_action_time_capability_certification(
            changed,
            runtime_head=RUNTIME_HEAD,
            fact_digest_rows=_fact_digest_rows(),
        )
    )
    assert (
        changed_prepared.certification_input_digest
        != prepared.certification_input_digest
    )


def test_certification_input_digest_rejects_binary_float() -> None:
    state = _bounded_certification_state()
    state["owner_policy_current"][0]["planned_stop_risk_fraction"] = 0.03

    with pytest.raises(ValueError, match="binary_float_forbidden"):
        certification_module.prepare_action_time_capability_certification(
            state,
            runtime_head=RUNTIME_HEAD,
            fact_digest_rows=_fact_digest_rows(),
        )


def test_certification_apply_rejects_prepare_digest_drift_before_write() -> None:
    state = _bounded_certification_state()
    prepared = certification_module.prepare_action_time_capability_certification(
        state,
        runtime_head=RUNTIME_HEAD,
        fact_digest_rows=_fact_digest_rows(),
    )
    changed = deepcopy(state)
    changed["owner_policy_current"][0]["max_leverage"] = 9

    result = certification_module.apply_prepared_action_time_capability_certification(
        None,
        prepared=prepared,
        control_state=changed,
        fact_digest_rows=_fact_digest_rows(),
        runtime_head=RUNTIME_HEAD,
        certification_ref="pytest:digest-drift",
        expected_lane_count=22,
        now_ms=1_800_000_000_200,
    )

    assert result["status"] == "blocked"
    assert result["first_blocker"] == "certification_input_digest_drift"
    assert result["certified_lane_count"] == 0


def test_fact_set_digest_changes_when_content_changes_with_same_id() -> None:
    row = certification_module.ActionTimeFactDigestRowV1(
        fact_snapshot_id="fact:digest:stable-id",
        strategy_group_id="SOR-001",
        symbol="ETHUSDT",
        side="long",
        runtime_profile_id="owner-runtime-console-v1",
        fact_surface="action_time_private",
        source_kind="live_account",
        source_ref="pytest",
        computed=True,
        satisfied=True,
        freshness_state="fresh",
        failed_facts=[],
        fact_values={"mark_price": "1888.50"},
        blocker_class=None,
        observed_at_ms=1_800_000_000_000,
        valid_until_ms=1_800_000_060_000,
    )

    before = certification_module.compute_action_time_fact_set_digest((row,))
    changed = row.model_copy(
        update={"fact_values": {"mark_price": "1888.51"}}
    )
    after = certification_module.compute_action_time_fact_set_digest((changed,))

    assert before.fact_snapshot_ids == ("fact:digest:stable-id",)
    assert before.fact_set_digest_schema == "brc.action_time_fact_set_digest.v1"
    assert before.fact_set_digest != after.fact_set_digest


def _control_state() -> dict[str, object]:
    rows = build_seed_rows(now_ms=1_800_000_000_000)
    event_by_candidate = {
        binding["candidate_scope_id"]: next(
            event
            for event in rows["brc_strategy_side_event_specs"]
            if event["event_spec_id"] == binding["event_spec_id"]
        )
        for binding in rows["brc_candidate_scope_event_bindings"]
        if binding["status"] == "active"
    }
    runtime_instances = [
        {
            "runtime_instance_id": "runtime:" + candidate["candidate_scope_id"],
            "strategy_family_id": candidate["strategy_group_id"],
            "strategy_family_version_id": event_by_candidate[
                candidate["candidate_scope_id"]
            ]["strategy_group_version_id"],
            "symbol": candidate["symbol"],
            "side": candidate["side"],
            "status": "active",
        }
        for candidate in rows["brc_strategy_group_candidate_scope"]
        if candidate["status"] == "active"
    ]
    return {
        "strategy_groups": rows["brc_strategy_groups"],
        "strategy_group_versions": rows["brc_strategy_group_versions"],
        "candidate_scope": rows["brc_strategy_group_candidate_scope"],
        "candidate_scope_event_bindings": rows[
            "brc_candidate_scope_event_bindings"
        ],
        "strategy_side_event_specs": rows["brc_strategy_side_event_specs"],
        "strategy_event_required_facts": rows[
            "brc_strategy_event_required_facts"
        ],
        "runtime_scope_bindings": rows["brc_runtime_scope_bindings"],
        "strategy_runtime_instances": runtime_instances,
        "owner_policy_current": rows["brc_owner_policy_current"],
        "runtime_process_outcomes": [],
    }


def _certification(identity, *, runtime_head: str = RUNTIME_HEAD) -> dict[str, object]:
    return {
        "process_outcome_id": f"process:{identity.strategy_group_id}:{identity.symbol}:{identity.side}",
        "process_name": "action_time_capability_certification",
        "scope_key": identity.scope_key,
        "run_id": "certification:test",
        "process_state": "succeeded",
        "business_state": "completed",
        "first_blocker": None,
        "runtime_head": runtime_head,
        "source_watermark": identity.source_watermark,
        "projector_owner": "runtime_process_outcome_projector",
        "updated_at_ms": 1_800_000_000_100,
    }


def test_builds_one_stable_identity_for_each_current_candidate_scope() -> None:
    state = _control_state()

    identities = build_action_time_capability_identities(state)

    assert len(identities) == 22
    assert len({identity.scope_key for identity in identities}) == 22
    assert {identity.strategy_group_id for identity in identities} == {
        "CPM-RO-001",
        "MPG-001",
        "MI-001",
        "SOR-001",
        "BRF2-001",
    }
    assert all(identity.source_watermark.startswith("action_time_capability:") for identity in identities)
    assert all(identity.required_fact_contract_refs for identity in identities)


def test_required_fact_contract_change_invalidates_lineage() -> None:
    state = _control_state()
    before = build_action_time_capability_identities(state)[0]
    changed = deepcopy(state)
    rows = changed["strategy_event_required_facts"]
    assert isinstance(rows, list)
    target = next(row for row in rows if row["event_spec_id"] == before.event_spec_id)
    target["expected_value"] = not bool(target.get("expected_value"))

    after = next(
        identity
        for identity in build_action_time_capability_identities(changed)
        if identity.scope_key == before.scope_key
    )

    assert after.source_watermark != before.source_watermark


def test_owner_policy_value_change_invalidates_lineage() -> None:
    state = _control_state()
    before = build_action_time_capability_identities(state)[0]
    policies = state["owner_policy_current"]
    assert isinstance(policies, list)
    candidates = state["candidate_scope"]
    assert isinstance(candidates, list)
    policy_id = next(
        row["policy_current_id"]
        for row in candidates
        if row["candidate_scope_id"] == before.candidate_scope_id
    )
    policy = next(
        row
        for row in policies
        if row["policy_current_id"] == policy_id
    )
    policy["max_leverage"] = 9

    after = next(
        identity
        for identity in build_action_time_capability_identities(state)
        if identity.scope_key == before.scope_key
    )

    assert after.source_watermark != before.source_watermark


def test_execution_ineligible_event_cannot_form_a_certifiable_identity() -> None:
    state = _control_state()
    events = state["strategy_side_event_specs"]
    assert isinstance(events, list)
    events[0]["execution_eligibility_enabled"] = False

    with pytest.raises(
        ActionTimeCapabilityIdentityError,
        match="event_execution_capability_not_certified",
    ):
        build_action_time_capability_identities(state)


def test_matching_release_and_lineage_are_currently_certified() -> None:
    state = _control_state()
    identities = build_action_time_capability_identities(state)
    state["runtime_process_outcomes"] = [
        _certification(identity) for identity in identities
    ]

    truths = current_action_time_capability_truth_by_lane(
        state,
        current_runtime_head=RUNTIME_HEAD,
    )

    assert len(truths) == 22
    assert all(truth.certified for truth in truths.values())
    assert {truth.first_blocker for truth in truths.values()} == {None}


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (lambda state, identities: None, "certification_missing"),
        (
            lambda state, identities: state.update(
                runtime_process_outcomes=[
                    _certification(identity, runtime_head="b" * 40)
                    for identity in identities
                ]
            ),
            "runtime_head_mismatch",
        ),
        (
            lambda state, identities: state.update(
                runtime_process_outcomes=[
                    {**_certification(identity), "source_watermark": "stale"}
                    for identity in identities
                ]
            ),
            "lineage_mismatch",
        ),
    ],
)
def test_missing_or_stale_certification_fails_closed(mutator, reason: str) -> None:
    state = _control_state()
    identities = build_action_time_capability_identities(state)
    mutator(state, identities)

    truths = current_action_time_capability_truth_by_lane(
        state,
        current_runtime_head=RUNTIME_HEAD,
    )

    assert {truth.certified for truth in truths.values()} == {False}
    assert {truth.first_blocker for truth in truths.values()} == {
        "action_time_boundary_not_reproduced"
    }
    assert {truth.reason for truth in truths.values()} == {reason}


def test_incomplete_lane_identity_is_rejected_instead_of_partially_certified() -> None:
    state = _control_state()
    runtime_rows = state["runtime_scope_bindings"]
    assert isinstance(runtime_rows, list)
    runtime_rows.pop()

    with pytest.raises(
        ActionTimeCapabilityIdentityError,
        match="runtime_scope_binding_missing",
    ):
        build_action_time_capability_identities(state)


def test_current_runtime_head_comes_from_deployment_release_activation_truth() -> None:
    state = _control_state()
    state["server_monitor_runs"] = [
        {"runtime_head": None, "created_at_ms": 1_800_000_000_200}
    ]
    state["runtime_process_outcomes"] = [
        {
            "process_name": "runtime_release_activation",
            "scope_key": "production:tokyo",
            "process_state": "succeeded",
            "runtime_head": RUNTIME_HEAD,
            "updated_at_ms": 1_800_000_000_100,
        }
    ]

    assert current_runtime_head(state) == RUNTIME_HEAD
