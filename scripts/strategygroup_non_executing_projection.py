"""Shared helpers for non-executing StrategyGroup projections."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


_INTERACTION_FALSE_KEYS = (
    "mutates_remote_files",
    "approaches_real_order",
    "calls_finalgate",
    "calls_operation_layer",
    "calls_exchange_write",
    "places_order",
)

_SAFETY_FALSE_KEYS = (
    "calls_finalgate",
    "calls_operation_layer",
    "calls_exchange_write",
    "places_order",
    "live_profile_changed",
    "order_sizing_changed",
    "withdrawal_or_transfer_created",
)

_LEGACY_AUTHORITY_MIRROR_FALSE_KEYS = (
    "actionable_now",
    "real_order_authority",
)
LEGACY_AUTHORITY_MIRROR_KEYS = _LEGACY_AUTHORITY_MIRROR_FALSE_KEYS

_REVIEW_ONLY_FORBIDDEN_EFFECTS = (
    "registry_authority_changed",
    "tier_policy_changed",
    "live_profile_changed",
    "order_sizing_changed",
    "mpg_member_live_scope_expanded",
    "l4_real_order_scope_expanded",
    "shadow_candidate_created",
    "execution_intent_created",
    "final_gate_called",
    "operation_layer_called",
    "order_created",
    "exchange_write_called",
)
_REVIEW_ONLY_SAFETY_FALSE_KEYS = (
    "server_interaction",
    "server_files_mutated",
    "strategy_parameters_changed",
    "registry_authority_changed",
    "tier_policy_changed",
    "live_profile_changed",
    "mpg_member_live_scope_expanded",
    "l4_real_order_scope_expanded",
    "shadow_candidate_created",
    "final_gate_called",
    "operation_layer_called",
    "order_created",
    "exchange_write_called",
    "preview_or_replay_treated_as_live_signal",
)

SOURCE_SAFETY_TRUE_KEYS = (
    "server_files_mutated",
    "runtime_started",
    "strategy_parameters_changed",
    "tier_policy_changed",
    "shadow_candidate_created",
    "execution_intent_created",
    "final_gate_called",
    "operation_layer_called",
    "order_created",
    "order_lifecycle_called",
    "exchange_write_called",
    "withdrawal_or_transfer_created",
)

EXTENDED_SOURCE_SAFETY_TRUE_KEYS = (
    "server_files_mutated",
    "runtime_started",
    "strategy_parameters_changed",
    "live_profile_changed",
    "order_sizing_defaults_changed",
    "tier_policy_changed",
    "l2_promotion_authorized",
    "l4_real_order_scope_expanded",
    "shadow_candidate_created",
    "execution_intent_created",
    "final_gate_called",
    "operation_layer_called",
    "order_created",
    "order_lifecycle_called",
    "exchange_write_called",
    "withdrawal_or_transfer_created",
)

SOURCE_INTERACTION_TRUE_KEYS = (
    "mutates_remote_files",
    "approaches_real_order",
    "calls_finalgate",
    "calls_operation_layer",
    "calls_exchange_write",
    "places_order",
)

L2_NON_EXECUTING_SOURCE_TRUE_KEYS = (
    "shadow_candidate_created",
    "execution_intent_created",
    "final_gate_called",
    "operation_layer_called",
    "order_created",
    "order_lifecycle_called",
    "exchange_write_called",
    "withdrawal_or_transfer_created",
)

REVIEW_OUTCOME_STATE_FAMILY = "Review Outcome State"
RUNTIME_AUTHORITY_SOURCES = ("Tradeability Decision", "Runtime Safety State")


@dataclass(frozen=True)
class ReviewOutcomeStateBoundary:
    source_role: str
    review_scope: str
    primary_judgment_source_name: str = "strategy_asset_state"
    tradeability_decision_source: bool = False
    runtime_authority_sources: tuple[str, ...] | None = None

    def as_dict(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        state: dict[str, Any] = {
            "state_family": REVIEW_OUTCOME_STATE_FAMILY,
            "source_role": self.source_role,
            "review_scope": self.review_scope,
            "primary_judgment_source": False,
            "primary_judgment_source_name": self.primary_judgment_source_name,
            "tradeability_decision_source": self.tradeability_decision_source,
        }
        if self.runtime_authority_sources is not None:
            state["runtime_authority_sources"] = list(self.runtime_authority_sources)
        if extra:
            state.update(extra)
        return state


def non_executing_interaction(level: str) -> dict[str, bool | int | str]:
    return {
        "level": level,
        "remote_interaction_count": 0,
        **{key: False for key in _INTERACTION_FALSE_KEYS},
    }


def review_outcome_state_boundary(
    *,
    source_role: str,
    review_scope: str,
    runtime_authority_sources: Iterable[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ReviewOutcomeStateBoundary(
        source_role=source_role,
        review_scope=review_scope,
        runtime_authority_sources=(
            tuple(runtime_authority_sources)
            if runtime_authority_sources is not None
            else None
        ),
    ).as_dict(extra=extra)


def review_outcome_state_validation_errors(
    review_outcome: dict[str, Any],
    *,
    expected_source_role: str,
    false_keys: Iterable[str] = (),
    require_runtime_authority_sources: bool = False,
    require_owner_runtime_authority_rule: bool = False,
    error_prefix: str = "review_outcome_state",
) -> list[str]:
    errors: list[str] = []
    if review_outcome.get("state_family") != REVIEW_OUTCOME_STATE_FAMILY:
        errors.append(f"{error_prefix}_family_mismatch")
    if review_outcome.get("source_role") != expected_source_role:
        errors.append(f"{error_prefix}_source_role_mismatch")
    if review_outcome.get("primary_judgment_source") is not False:
        errors.append(f"{error_prefix}_must_not_be_primary")
    if review_outcome.get("tradeability_decision_source") is not False:
        errors.append(f"{error_prefix}_must_not_answer_tradeability")
    if (
        require_owner_runtime_authority_rule
        and review_outcome.get("owner_risk_acceptance_cannot_grant_runtime_authority")
        is not True
    ):
        errors.append("owner_risk_acceptance_rule_missing")
    if require_runtime_authority_sources and review_outcome.get(
        "runtime_authority_sources"
    ) != list(RUNTIME_AUTHORITY_SOURCES):
        errors.append(f"{error_prefix}_runtime_authority_sources_mismatch")
    for key in false_keys:
        if review_outcome.get(key) is not False:
            errors.append(f"{error_prefix}_not_false:{key}")
    return errors


def review_outcome_source_validation_errors(
    artifact: dict[str, Any],
    *,
    source_name: str,
) -> list[str]:
    review_outcome = _as_dict(artifact.get("review_outcome_state"))
    errors: list[str] = []
    if not review_outcome.get("default_next_step"):
        errors.append(f"{source_name}.missing_review_outcome_default_next_step")
    if review_outcome.get("tradeability_decision_source") is not False:
        errors.append(f"{source_name}.review_outcome_must_not_answer_tradeability")
    return errors


def review_outcome_state_from(artifact: dict[str, Any]) -> dict[str, Any]:
    return (
        _as_dict(artifact.get("review_outcome_state"))
        if isinstance(artifact, dict)
        else {}
    )


def review_outcome_default_next_step(artifact: dict[str, Any]) -> str:
    return str(review_outcome_state_from(artifact).get("default_next_step") or "")


def review_outcome_flag(artifact: dict[str, Any], key: str) -> bool:
    return review_outcome_state_from(artifact).get(key) is True


def review_outcome_value(artifact: dict[str, Any], key: str, default: Any = None) -> Any:
    return review_outcome_state_from(artifact).get(key, default)


def review_outcome_string_list(
    artifact: dict[str, Any],
    key: str,
    *,
    unique: bool = False,
    sorted_values: bool = False,
) -> list[str]:
    values = [
        str(item)
        for item in review_outcome_state_from(artifact).get(key) or []
        if str(item)
    ]
    if unique:
        values = list(dict.fromkeys(values))
    if sorted_values:
        values = sorted(values)
    return values


def non_executing_safety_invariants(
    extra_false_keys: Iterable[str] = (),
    *,
    include_authority_mirrors: bool = False,
    include_withdrawal_or_transfer: bool = True,
) -> dict[str, bool]:
    safety = {key: False for key in _SAFETY_FALSE_KEYS}
    if include_authority_mirrors:
        safety.update({key: False for key in _LEGACY_AUTHORITY_MIRROR_FALSE_KEYS})
    if not include_withdrawal_or_transfer:
        safety.pop("withdrawal_or_transfer_created")
    safety.update({key: False for key in extra_false_keys})
    return safety


def legacy_authority_mirror_present_errors(
    mapping: dict[str, Any],
    *,
    label_prefix: str,
    keys: Iterable[str] = LEGACY_AUTHORITY_MIRROR_KEYS,
) -> list[str]:
    return [
        f"{label_prefix}legacy_authority_mirror_present:{key}"
        for key in keys
        if key in mapping
    ]


def legacy_authority_mirror_effects_for_artifacts(
    artifacts: Iterable[tuple[str, dict[str, Any]]],
    *,
    section_names: Iterable[str] = (),
    row_names: Iterable[str] = (),
    row_id_keys: Iterable[str] = (),
    include_root: bool = False,
    root_section_name: str | None = None,
    include_row_name_in_label: bool = True,
    keys: Iterable[str] = LEGACY_AUTHORITY_MIRROR_KEYS,
) -> list[str]:
    effects: list[str] = []
    row_id_key_tuple = tuple(row_id_keys)
    for artifact_name, artifact in artifacts:
        artifact_prefix = f"{artifact_name}." if artifact_name else ""
        if include_root:
            effects.extend(
                legacy_authority_mirror_present_errors(
                    artifact,
                    label_prefix=artifact_prefix,
                    keys=keys,
                )
            )
        if root_section_name:
            effects.extend(
                legacy_authority_mirror_present_errors(
                    artifact,
                    label_prefix=f"{artifact_prefix}{root_section_name}.",
                    keys=keys,
                )
            )
        for section_name in section_names:
            effects.extend(
                legacy_authority_mirror_present_errors(
                    _as_dict(artifact.get(section_name)),
                    label_prefix=f"{artifact_prefix}{section_name}.",
                    keys=keys,
                )
            )
        for row_name in row_names:
            for index, row in enumerate(_dict_rows(artifact.get(row_name))):
                row_id = _row_id(row, row_id_key_tuple, fallback=index)
                row_label = (
                    f"{artifact_prefix}{row_name}.{row_id}."
                    if include_row_name_in_label
                    else f"{artifact_prefix}{row_id}."
                )
                effects.extend(
                    legacy_authority_mirror_present_errors(
                        row,
                        label_prefix=row_label,
                        keys=keys,
                    )
                )
    return effects


def _row_id(
    row: dict[str, Any],
    keys: tuple[str, ...],
    *,
    fallback: int,
) -> str:
    for key in keys:
        value = row.get(key)
        if str(value or "").strip():
            return str(value)
    return str(fallback)


def non_executing_safety_boundary(
    *,
    true_keys: Iterable[str] = (),
    false_keys: Iterable[str] | None = None,
    extra_false_keys: Iterable[str] = (),
    source_forbidden_effects: Iterable[str] = (),
    include_source_forbidden_effects: bool = True,
) -> dict[str, bool | list[str]]:
    default_false_keys = (
        "server_interaction",
        "server_files_mutated",
        "runtime_started",
        "strategy_parameters_changed",
        "live_profile_changed",
        "order_sizing_defaults_changed",
        "tier_policy_changed",
        "l2_promotion_authorized",
        "l4_real_order_scope_expanded",
        "shadow_candidate_created",
        "final_gate_called",
        "operation_layer_called",
        "order_created",
        "order_lifecycle_called",
        "exchange_write_called",
        "withdrawal_or_transfer_created",
    )
    selected_false_keys = tuple(default_false_keys if false_keys is None else false_keys)
    safety: dict[str, bool | list[str]] = {key: True for key in true_keys}
    safety.update(
        {
            key: False
            for key in (*selected_false_keys, *tuple(extra_false_keys))
        }
    )
    if include_source_forbidden_effects:
        safety["source_forbidden_effects"] = list(source_forbidden_effects)
    return safety


def review_only_forbidden_effects() -> tuple[str, ...]:
    return _REVIEW_ONLY_FORBIDDEN_EFFECTS


def review_only_legacy_authority_mirror_true_keys() -> tuple[str, ...]:
    return LEGACY_AUTHORITY_MIRROR_KEYS


def review_only_interaction(
    level: str,
    *,
    mutation_key: str = "server_files_mutated",
) -> dict[str, bool | int | str]:
    return {
        "level": level,
        "remote_interaction_count": 0,
        mutation_key: False,
        "calls_finalgate": False,
        "calls_operation_layer": False,
        "calls_exchange_write": False,
        "places_order": False,
        "approaches_real_order": False,
    }


def review_only_safety_invariants(
    *,
    include_runtime_started: bool = False,
    include_order_sizing_changed: bool = False,
    include_authority_mirrors: bool = False,
) -> dict[str, bool]:
    safety = {
        "local_review_only": True,
        **{key: False for key in _REVIEW_ONLY_SAFETY_FALSE_KEYS},
    }
    if include_authority_mirrors:
        safety.update({key: False for key in LEGACY_AUTHORITY_MIRROR_KEYS})
    if include_runtime_started:
        safety["runtime_started"] = False
    if include_order_sizing_changed:
        safety["order_sizing_changed"] = False
    return safety


def recursive_true_key_paths(
    *artifacts: dict[str, Any],
    true_keys: Iterable[str],
    source_prefix: str = "source",
) -> list[str]:
    keys = set(true_keys)
    found: list[str] = []
    for index, artifact in enumerate(artifacts):
        _walk_true_key_paths(
            artifact,
            prefix=f"{source_prefix}[{index}]",
            keys=keys,
            found=found,
        )
    return list(dict.fromkeys(found))


def source_forbidden_effects(
    artifacts: Iterable[tuple[str, dict[str, Any]]],
    *,
    true_keys: Iterable[str],
    source_names: Iterable[str] = ("safety_invariants",),
    true_effect_source_label: str | None = "safety",
    include_source_forbidden_effects: bool = True,
    source_effect_includes_source_name: bool = False,
) -> list[str]:
    keys = tuple(true_keys)
    effects: list[str] = []
    for artifact_name, artifact in artifacts:
        for source_name in source_names:
            source = _as_dict(artifact.get(source_name))
            if include_source_forbidden_effects:
                for item in source.get("source_forbidden_effects") or []:
                    if not item:
                        continue
                    if source_effect_includes_source_name:
                        effects.append(
                            _effect_path(artifact_name, f"{source_name}.{item}")
                        )
                    else:
                        effects.append(_effect_path(artifact_name, str(item)))
            label = source_name if true_effect_source_label is None else true_effect_source_label
            for key in keys:
                if source.get(key) is True:
                    effects.append(_effect_path(artifact_name, f"{label}.{key}"))
    return sorted(set(effect for effect in effects if effect))


def artifact_source_forbidden_effects(
    artifacts: Iterable[dict[str, Any]],
    *,
    true_keys: Iterable[str],
    include_interaction: bool = False,
) -> list[str]:
    source_artifacts = tuple(
        (f"artifact_{index}", artifact) for index, artifact in enumerate(artifacts)
    )
    effects = source_forbidden_effects(source_artifacts, true_keys=true_keys)
    if include_interaction:
        effects.extend(
            source_forbidden_effects(
                source_artifacts,
                true_keys=SOURCE_INTERACTION_TRUE_KEYS,
                source_names=("interaction",),
                true_effect_source_label="interaction",
                include_source_forbidden_effects=False,
            )
        )
    return sorted(set(effects))


def section_true_key_effects(
    artifact: dict[str, Any],
    section_keys: Iterable[tuple[str, str]],
) -> list[str]:
    effects: list[str] = []
    for section, key in section_keys:
        if _as_dict(artifact.get(section)).get(key) is True:
            effects.append(f"{section}.{key}")
    return sorted(set(effects))


def authority_boundary_candidate_true_key_effects(
    artifact: dict[str, Any],
    *,
    true_keys: Iterable[str],
    authority_section: str = "authority_boundary",
    candidates_section: str = "candidates",
) -> list[str]:
    keys = tuple(true_keys)
    effects: list[str] = []
    authority = _as_dict(artifact.get(authority_section))
    for key in keys:
        if authority.get(key) is True:
            effects.append(f"{authority_section}.{key}=true")
    for index, candidate in enumerate(_dict_rows(artifact.get(candidates_section))):
        for key in keys:
            if candidate.get(key) is True:
                effects.append(f"{candidates_section}[{index}].{key}=true")
    return sorted(effects)


def _walk_true_key_paths(
    value: Any,
    *,
    prefix: str,
    keys: set[str],
    found: list[str],
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            if key in keys and item is True:
                found.append(path)
            _walk_true_key_paths(item, prefix=path, keys=keys, found=found)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_true_key_paths(item, prefix=f"{prefix}[{index}]", keys=keys, found=found)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def _effect_path(artifact_name: str, suffix: str) -> str:
    if artifact_name:
        return f"{artifact_name}.{suffix}"
    return suffix
