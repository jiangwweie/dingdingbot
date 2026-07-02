from scripts.strategygroup_non_executing_projection import (
    L2_NON_EXECUTING_SOURCE_TRUE_KEYS,
    RUNTIME_AUTHORITY_SOURCES,
    authority_boundary_candidate_true_key_effects,
    legacy_authority_mirror_effects_for_artifacts,
    non_executing_safety_invariants,
    recursive_true_key_paths,
    review_outcome_source_validation_errors,
    review_outcome_default_next_step,
    review_outcome_flag,
    review_outcome_state_boundary,
    review_outcome_state_from,
    review_outcome_state_validation_errors,
    review_outcome_string_list,
    review_outcome_value,
    review_only_safety_invariants,
    review_only_forbidden_effects,
    review_only_legacy_authority_mirror_true_keys,
    section_true_key_effects,
    source_forbidden_effects,
)


def test_recursive_true_key_paths_preserves_nested_source_paths() -> None:
    paths = recursive_true_key_paths(
        {
            "rows": [
                {
                    "strategy_group_id": "BTPC-001",
                    "safety": {"order_created": True},
                }
            ],
            "actionable_now": False,
        },
        true_keys=("actionable_now", "order_created"),
    )

    assert paths == ["source[0].rows[0].safety.order_created"]


def test_source_forbidden_effects_preserves_named_source_formats() -> None:
    effects = source_forbidden_effects(
        (
            (
                "source_artifact",
                {
                    "safety_invariants": {
                        "order_created": True,
                        "source_forbidden_effects": ["upstream.order_created"],
                    },
                    "interaction": {
                        "calls_finalgate": True,
                    },
                },
            ),
        ),
        true_keys=("order_created", "calls_finalgate"),
        source_names=("safety_invariants", "interaction"),
        true_effect_source_label=None,
        source_effect_includes_source_name=True,
    )

    assert effects == [
        "source_artifact.interaction.calls_finalgate",
        "source_artifact.safety_invariants.order_created",
        "source_artifact.safety_invariants.upstream.order_created",
    ]


def test_source_forbidden_effects_allows_unprefixed_source_paths() -> None:
    effects = source_forbidden_effects(
        (
            (
                "",
                {
                    "safety_invariants": {
                        "order_created": True,
                        "source_forbidden_effects": ["source.order"],
                    },
                },
            ),
        ),
        true_keys=("order_created",),
    )

    assert effects == ["safety.order_created", "source.order"]


def test_section_true_key_effects_preserves_section_key_paths() -> None:
    effects = section_true_key_effects(
        {
            "decision": {"l4_scope_change_recommended": True},
            "interaction": {"places_order": False},
        },
        (
            ("decision", "l4_scope_change_recommended"),
            ("interaction", "places_order"),
        ),
    )

    assert effects == ["decision.l4_scope_change_recommended"]


def test_authority_boundary_candidate_true_key_effects_preserves_research_intake_paths() -> None:
    effects = authority_boundary_candidate_true_key_effects(
        {
            "authority_boundary": {
                "exchange_write": True,
                "finalgate_input": "true",
            },
            "candidates": [
                {
                    "strategy_id": "CPM-RO-001",
                    "operation_layer_input": True,
                    "real_order_authority": False,
                },
                "not-a-row",
                {
                    "strategy_id": "BRF2-001",
                    "order_created": True,
                },
            ],
        },
        true_keys=(
            "exchange_write",
            "finalgate_input",
            "operation_layer_input",
            "order_created",
            "real_order_authority",
        ),
    )

    assert effects == [
        "authority_boundary.exchange_write=true",
        "candidates[0].operation_layer_input=true",
        "candidates[1].order_created=true",
    ]


def test_l2_non_executing_source_true_keys_cover_lifecycle_side_effects() -> None:
    assert L2_NON_EXECUTING_SOURCE_TRUE_KEYS == (
        "shadow_candidate_created",
        "execution_intent_created",
        "final_gate_called",
        "operation_layer_called",
        "order_created",
        "order_lifecycle_called",
        "exchange_write_called",
        "withdrawal_or_transfer_created",
    )


def test_non_executing_safety_invariants_default_excludes_legacy_authority_mirrors() -> None:
    safety = non_executing_safety_invariants()

    assert "actionable_now" not in safety
    assert "real_order_authority" not in safety
    assert safety["calls_finalgate"] is False
    assert safety["calls_operation_layer"] is False
    assert safety["calls_exchange_write"] is False


def test_non_executing_safety_invariants_can_retain_legacy_authority_mirrors() -> None:
    safety = non_executing_safety_invariants(include_authority_mirrors=True)

    assert safety["actionable_now"] is False
    assert safety["real_order_authority"] is False


def test_review_only_safety_invariants_default_excludes_legacy_authority_mirrors() -> None:
    safety = review_only_safety_invariants()

    assert "actionable_now" not in safety
    assert "real_order_authority" not in safety
    assert safety["local_review_only"] is True
    assert safety["final_gate_called"] is False
    assert safety["operation_layer_called"] is False


def test_review_only_safety_invariants_can_retain_legacy_authority_mirrors() -> None:
    safety = review_only_safety_invariants(include_authority_mirrors=True)

    assert safety["actionable_now"] is False
    assert safety["real_order_authority"] is False


def test_review_only_forbidden_effects_split_legacy_authority_mirrors() -> None:
    assert "actionable_now" not in review_only_forbidden_effects()
    assert "real_order_authority" not in review_only_forbidden_effects()
    assert review_only_legacy_authority_mirror_true_keys() == (
        "actionable_now",
        "real_order_authority",
    )


def test_legacy_authority_mirror_effects_for_artifacts_preserves_source_labels() -> None:
    effects = legacy_authority_mirror_effects_for_artifacts(
        (
            (
                "btpc_local_fact_proxy",
                {
                    "safety_invariants": {"actionable_now": False},
                    "proxy_rows": [
                        {
                            "required_fact": "open_interest",
                            "real_order_authority": False,
                        }
                    ],
                },
            ),
        ),
        section_names=("safety_invariants",),
        row_names=("proxy_rows",),
        row_id_keys=("required_fact",),
    )

    assert effects == [
        "btpc_local_fact_proxy.safety_invariants.legacy_authority_mirror_present:actionable_now",
        "btpc_local_fact_proxy.proxy_rows.open_interest.legacy_authority_mirror_present:real_order_authority",
    ]


def test_legacy_authority_mirror_effects_for_artifacts_can_omit_row_collection_label() -> None:
    effects = legacy_authority_mirror_effects_for_artifacts(
        (
            (
                "btpc_replay_corpus",
                {
                    "replay_samples": [
                        {
                            "fixture_case": "bear_pullback_would_enter",
                            "real_order_authority": False,
                        }
                    ],
                },
            ),
        ),
        row_names=("replay_samples",),
        row_id_keys=("fixture_case",),
        include_row_name_in_label=False,
    )

    assert effects == [
        "btpc_replay_corpus.bear_pullback_would_enter.legacy_authority_mirror_present:real_order_authority"
    ]


def test_legacy_authority_mirror_effects_for_artifacts_preserves_named_root_label() -> None:
    effects = legacy_authority_mirror_effects_for_artifacts(
        (
            (
                "source_l2_readiness",
                {
                    "actionable_now": False,
                    "checks": {"real_order_authority": False},
                    "readiness_rows": [
                        {
                            "strategy_group_id": "BTPC-001",
                            "actionable_now": False,
                        }
                    ],
                },
            ),
        ),
        root_section_name="root",
        section_names=("checks",),
        row_names=("readiness_rows",),
        row_id_keys=("strategy_group_id", "symbol"),
    )

    assert effects == [
        "source_l2_readiness.root.legacy_authority_mirror_present:actionable_now",
        "source_l2_readiness.checks.legacy_authority_mirror_present:real_order_authority",
        "source_l2_readiness.readiness_rows.BTPC-001.legacy_authority_mirror_present:actionable_now",
    ]


def test_legacy_authority_mirror_effects_for_artifacts_allows_empty_artifact_label() -> None:
    effects = legacy_authority_mirror_effects_for_artifacts(
        (
            (
                "",
                {
                    "safety_invariants": {"real_order_authority": False},
                    "action_rows": [
                        {
                            "action": "review_rule",
                            "actionable_now": False,
                        }
                    ],
                },
            ),
        ),
        section_names=("safety_invariants",),
        row_names=("action_rows",),
        row_id_keys=("action",),
    )

    assert effects == [
        "safety_invariants.legacy_authority_mirror_present:real_order_authority",
        "action_rows.review_rule.legacy_authority_mirror_present:actionable_now",
    ]


def test_review_outcome_state_boundary_builds_non_authority_state() -> None:
    state = review_outcome_state_boundary(
        source_role="btpc_fact_classifier_guard_provenance",
        review_scope="fact_classifier_guard",
        runtime_authority_sources=RUNTIME_AUTHORITY_SOURCES,
        extra={
            "default_next_step": "continue_btpc_l2_shadow_observation",
            "owner_risk_acceptance_cannot_grant_runtime_authority": True,
            "l4_scope_change_recommended": False,
        },
    )

    assert state["state_family"] == "Review Outcome State"
    assert state["primary_judgment_source"] is False
    assert state["primary_judgment_source_name"] == "strategy_asset_state"
    assert state["tradeability_decision_source"] is False
    assert state["runtime_authority_sources"] == [
        "Tradeability Decision",
        "Runtime Safety State",
    ]
    assert review_outcome_state_validation_errors(
        state,
        expected_source_role="btpc_fact_classifier_guard_provenance",
        false_keys=("l4_scope_change_recommended",),
        require_runtime_authority_sources=True,
        require_owner_runtime_authority_rule=True,
    ) == []


def test_review_outcome_state_validation_rejects_authority_misuse() -> None:
    state = review_outcome_state_boundary(
        source_role="handoff_boundary_closure_lifecycle_evidence",
        review_scope="handoff_boundary_closure",
        extra={"promote_or_live_authority_created": True},
    )
    state["primary_judgment_source"] = True
    state["tradeability_decision_source"] = True

    errors = review_outcome_state_validation_errors(
        state,
        expected_source_role="handoff_boundary_closure_lifecycle_evidence",
        false_keys=("promote_or_live_authority_created",),
    )

    assert "review_outcome_state_must_not_be_primary" in errors
    assert "review_outcome_state_must_not_answer_tradeability" in errors
    assert "review_outcome_state_not_false:promote_or_live_authority_created" in errors


def test_review_outcome_source_validation_rejects_missing_step_and_tradeability_source() -> None:
    errors = review_outcome_source_validation_errors(
        {
            "review_outcome_state": {
                "tradeability_decision_source": True,
            }
        },
        source_name="btpc_l2_keep_revise_fact_source_review",
    )

    assert errors == [
        "btpc_l2_keep_revise_fact_source_review."
        "missing_review_outcome_default_next_step",
        "btpc_l2_keep_revise_fact_source_review."
        "review_outcome_must_not_answer_tradeability",
    ]


def test_review_outcome_read_helpers_preserve_boundary_semantics() -> None:
    artifact = {
        "review_outcome_state": {
            "default_next_step": "run_conditional_l2_dry_run_without_tier_change",
            "post_revision_replay_review_passed": True,
            "groups_ready_for_l2_policy_review": [
                "BTPC-001",
                "",
                "MPG-001",
                "BTPC-001",
            ],
        }
    }

    assert review_outcome_state_from(artifact)["default_next_step"] == (
        "run_conditional_l2_dry_run_without_tier_change"
    )
    assert review_outcome_default_next_step(artifact) == (
        "run_conditional_l2_dry_run_without_tier_change"
    )
    assert review_outcome_flag(artifact, "post_revision_replay_review_passed") is True
    assert review_outcome_flag(artifact, "proxy_replay_satisfies_live_required_facts") is False
    assert review_outcome_value(artifact, "default_next_step") == (
        "run_conditional_l2_dry_run_without_tier_change"
    )
    assert review_outcome_value(artifact, "missing_key", "fallback") == "fallback"
    assert review_outcome_string_list(
        artifact,
        "groups_ready_for_l2_policy_review",
    ) == ["BTPC-001", "MPG-001", "BTPC-001"]
    assert review_outcome_string_list(
        artifact,
        "groups_ready_for_l2_policy_review",
        unique=True,
        sorted_values=True,
    ) == ["BTPC-001", "MPG-001"]
    assert review_outcome_default_next_step({}) == ""
    assert review_outcome_string_list({}, "groups_ready_for_l2_policy_review") == []
