from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.seed_runtime_control_state_foundation import build_seed_rows
from src.application.action_time.capability_certification import (
    ActionTimeCapabilityIdentityError,
    build_action_time_capability_identities,
    current_action_time_capability_truth_by_lane,
    current_runtime_head,
)


RUNTIME_HEAD = "a" * 40


def _control_state() -> dict[str, object]:
    rows = build_seed_rows(now_ms=1_800_000_000_000)
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
