from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    ROOT
    / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
HANDOFF_ROOT = ROOT / "docs/current/strategy-group-handoffs"


def _policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def test_runtime_tier_policy_keeps_only_mpg_in_current_l4_lane():
    policy = _policy()
    current = policy["current_strategy_groups"]

    l4_groups = [
        strategy_group_id
        for strategy_group_id, item in current.items()
        if item["tier"] == "L4"
    ]

    assert l4_groups == ["MPG-001"]
    assert current["MPG-001"]["mode"] == "tiny_real_order_eligible"
    assert current["TEQ-001"]["tier"] == "L2"
    assert current["FBS-001"]["tier"] == "L3"
    assert current["SOR-001"]["mode"] == "conditional_armed_observation"
    assert current["PMR-001"]["tier"] == "L1"
    assert current["BTPC-001"]["tier"] == "L2"
    assert current["BTPC-001"]["mode"] == "shadow_candidate"


def test_runtime_tier_policy_does_not_promote_new_groups_to_l4_by_default():
    defaults = _policy()["new_strategy_group_defaults"]

    assert defaults["default_tier"] == "L1"
    assert defaults["default_mode"] == "observe_only"
    assert set(defaults["known_new_groups"]) == {
        "BRF",
        "VCB",
        "LSR",
        "RBR",
    }
    assert all(tier == "L1" for tier in defaults["known_new_groups"].values())
    assert "must not enter L4" in defaults["promotion_rule"]


def test_runtime_tier_policy_is_catalog_aligned_with_current_handoffs():
    policy = _policy()
    expected = set(policy["current_strategy_groups"])
    handoff_ids = {
        json.loads(path.read_text(encoding="utf-8"))["strategy_group_id"]
        for path in HANDOFF_ROOT.glob("*/handoff.json")
    }

    assert handoff_ids == expected


def test_runtime_tier_l4_still_requires_official_chain():
    policy = _policy()
    tiers = policy["tier_definitions"]
    invariants = policy["safety_invariants"]

    assert tiers["L4"]["may_place_real_order"] is True
    assert tiers["L4"]["may_reach_finalgate"] is True
    assert tiers["L4"]["may_reach_operation_layer"] is True
    assert invariants["l4_still_requires_official_runtime_chain"] is True
    assert invariants["no_strategy_group_directly_authorizes_real_submit"] is True
    assert policy["not_execution_authority"] is True
    assert policy["not_finalgate_input"] is True
    assert policy["not_operation_layer_input"] is True
    assert policy["strategygroup_decision_review"][
        "review_rows_are_not_submit_authority"
    ] is True
    assert "real_order_authority" not in policy["strategygroup_decision_review"]
