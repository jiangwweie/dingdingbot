#!/usr/bin/env python3
"""Build a strategy RequiredFacts readiness projection from local semantics.

The projection is an operator-facing view over the current strategy semantics
catalog and optional read-only fact-source reports.  It never calls the API,
PG, exchange, OrderLifecycle, submit endpoints, or strategy evaluators.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.domain.strategy_semantics import (
    StrategyCandidateMode,
    StrategyImplementationBinding,
    StrategySemanticsCatalog,
    initial_strategy_semantics_catalog,
)


TRUSTED_FACT_SOURCES = {
    "account_facts": "trusted_account_facts",
    "runtime_boundary": "trusted_runtime_boundary",
    "position_projection": "trusted_position_projection",
}

TRUSTED_MARKET_FACT_KEYS = {
    "funding_rate",
    "open_interest",
    "crowding_proxy",
}

FORBIDDEN_TRUE_KEYS = {
    "api_called_by_builder",
    "attempt_counter_mutated",
    "exchange_called_by_builder",
    "exchange_order_submitted",
    "exchange_write_called",
    "execution_intent_created",
    "local_order_created",
    "order_created",
    "order_lifecycle_called",
    "pg_called_by_builder",
    "runtime_budget_mutated",
    "runtime_state_mutated",
    "submit_endpoint_called_by_builder",
    "withdrawal_or_transfer_created",
}


def _read_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    text = Path(path).expanduser().read_text(encoding="utf-8")
    start = text.find("{")
    if start < 0:
        raise ValueError(f"{path} does not contain a JSON object")
    payload = json.loads(text[start:])
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _truthy_keys(value: Any, keys: set[str], prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            if key in keys and bool(item):
                found.append(name)
            found.extend(_truthy_keys(item, keys, name))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_truthy_keys(item, keys, f"{prefix}[{index}]"))
    return sorted(set(found))


def _source_artifact(fact_sources: dict[str, Any], source_key: str) -> dict[str, Any]:
    value = fact_sources.get(source_key)
    return value if isinstance(value, dict) else {}


def _source_status(source: dict[str, Any]) -> str:
    return str(source.get("status") or "missing")


def _source_available(source: dict[str, Any]) -> bool:
    return _source_status(source) in {"available", "fresh", "present", "ready"}


def _source_stale(source: dict[str, Any]) -> bool:
    freshness = str(source.get("freshness") or source.get("freshness_status") or "")
    status = _source_status(source)
    return status in {"stale", "expired"} or freshness in {"stale", "expired"}


def _source_read_only(source: dict[str, Any]) -> bool:
    return bool(source.get("read_only_guarantee", False))


def _fact_source_key(fact_key: str) -> str:
    if fact_key in TRUSTED_FACT_SOURCES:
        return TRUSTED_FACT_SOURCES[fact_key]
    if fact_key in TRUSTED_MARKET_FACT_KEYS:
        return "trusted_market_facts"
    return "strategy_market_structure_facts"


def _fact_coverage(
    *,
    binding: StrategyImplementationBinding,
    fact_sources: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    coverage: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []
    for requirement in binding.required_facts:
        source_key = _fact_source_key(requirement.fact_key)
        source = _source_artifact(fact_sources, source_key)
        status = _source_status(source)
        available = _source_available(source)
        stale = _source_stale(source)
        read_only_required = source_key.startswith("trusted_")
        read_only = _source_read_only(source)

        if not available:
            blockers.append(f"{requirement.fact_key}_source_missing")
        if stale:
            blockers.append(f"{requirement.fact_key}_source_stale")
        if read_only_required and source and not read_only:
            blockers.append(f"{requirement.fact_key}_source_not_read_only")
        if requirement.missing_behavior.value == "OBSERVE_ONLY":
            warnings.append(f"{requirement.fact_key}_missing_downgrades_to_observe_only")

        coverage.append(
            {
                "fact_key": requirement.fact_key,
                "required": requirement.required,
                "source_key": source_key,
                "source_status": status,
                "freshness": source.get("freshness") or source.get("freshness_status"),
                "read_only_required": read_only_required,
                "read_only_guarantee": read_only if source else None,
                "missing_behavior": requirement.missing_behavior.value,
                "stale_behavior": requirement.stale_behavior.value,
                "max_age_ms": requirement.max_age_ms,
            }
        )
    return coverage, sorted(set(blockers)), sorted(set(warnings))


def _binding_artifact(
    *,
    binding: StrategyImplementationBinding,
    fact_sources: dict[str, Any],
) -> dict[str, Any]:
    coverage, blockers, warnings = _fact_coverage(
        binding=binding,
        fact_sources=fact_sources,
    )
    if binding.candidate_mode == StrategyCandidateMode.REGIME_CLASSIFIER_ONLY:
        status = "observe_only_reference_semantics"
    elif binding.candidate_mode == StrategyCandidateMode.DATA_BACKLOG_ONLY:
        status = "data_backlog_only"
    elif blockers:
        status = "blocked_required_facts"
    else:
        status = "ready_for_non_executing_strategy_runtime_planning"

    required_trusted_sources = sorted(
        {
            item["source_key"]
            for item in coverage
            if str(item["source_key"]).startswith("trusted_")
        }
    )
    return {
        "status": status,
        "semantic_snapshot": binding.semantic_snapshot(),
        "source_ref": binding.source_ref,
        "supported_sides": list(binding.supported_sides),
        "required_facts": coverage,
        "optional_facts": [
            {
                "fact_key": fact.fact_key,
                "required": fact.required,
                "source_key": _fact_source_key(fact.fact_key),
                "missing_behavior": fact.missing_behavior.value,
                "stale_behavior": fact.stale_behavior.value,
                "max_age_ms": fact.max_age_ms,
            }
            for fact in binding.optional_facts
        ],
        "required_trusted_sources": required_trusted_sources,
        "blockers": blockers,
        "warnings": warnings,
        "runtime_policy": {
            "candidate_mode": binding.candidate_mode.value,
            "runtime_confirmation_mode": binding.runtime_confirmation_mode.value,
            "reference_implementation": binding.reference_implementation,
            "proven_alpha": binding.proven_alpha,
            "owner_confirm_each_entry_required": (
                binding.owner_confirm_each_entry_required
            ),
        },
    }


def _requested_bindings(
    catalog: StrategySemanticsCatalog,
    strategies: list[str],
) -> tuple[list[StrategyImplementationBinding], list[dict[str, Any]]]:
    if not strategies:
        return list(catalog.bindings), []

    found: list[StrategyImplementationBinding] = []
    missing: list[dict[str, Any]] = []
    for strategy in strategies:
        if ":" in strategy:
            family_id, version_id = strategy.split(":", 1)
        else:
            family_id = strategy
            version_id = f"{strategy}-v0"
        try:
            found.append(
                catalog.get_binding(
                    strategy_family_id=family_id,
                    strategy_family_version_id=version_id,
                )
            )
        except KeyError:
            missing.append(
                {
                    "strategy_family_id": family_id,
                    "strategy_family_version_id": version_id,
                    "status": "blocked_strategy_semantics_missing",
                    "blockers": ["strategy_semantics_binding_missing"],
                }
            )
    return found, missing


def _overall_status(
    *,
    strategy_artifacts: list[dict[str, Any]],
    missing_strategy_artifacts: list[dict[str, Any]],
    forbidden_effects: list[str],
) -> str:
    if forbidden_effects:
        return "blocked_forbidden_effect"
    if missing_strategy_artifacts:
        return "blocked_strategy_semantics_missing"
    statuses = {artifact["status"] for artifact in strategy_artifacts}
    if "blocked_required_facts" in statuses:
        return "blocked_strategy_required_facts"
    if statuses <= {"observe_only_reference_semantics", "data_backlog_only"}:
        return "observe_only_reference_semantics"
    return "ready_for_non_executing_strategy_runtime_planning"


def build_strategy_required_facts_readiness_artifact(
    *,
    fact_sources: dict[str, Any] | None = None,
    strategies: list[str] | None = None,
    generated_at_ms: int | None = None,
    catalog: StrategySemanticsCatalog | None = None,
) -> dict[str, Any]:
    fact_sources = fact_sources or {}
    catalog = catalog or initial_strategy_semantics_catalog()
    selected, missing = _requested_bindings(catalog, strategies or [])
    strategy_artifacts = [
        _binding_artifact(binding=binding, fact_sources=fact_sources)
        for binding in selected
    ]
    forbidden_effects = _truthy_keys(fact_sources, FORBIDDEN_TRUE_KEYS)
    status = _overall_status(
        strategy_artifacts=strategy_artifacts,
        missing_strategy_artifacts=missing,
        forbidden_effects=forbidden_effects,
    )
    blockers = sorted(
        {
            *[
                blocker
                for artifact in strategy_artifacts
                for blocker in artifact.get("blockers", [])
            ],
            *[
                blocker
                for artifact in missing
                for blocker in artifact.get("blockers", [])
            ],
            *(
                ["forbidden_side_effect_reported"]
                if forbidden_effects
                else []
            ),
        }
    )
    return {
        "scope": "runtime_strategy_required_facts_readiness_artifact",
        "status": status,
        "generated_at_ms": generated_at_ms
        if generated_at_ms is not None
        else int(time.time() * 1000),
        "strategy_count": len(strategy_artifacts),
        "strategies": strategy_artifacts,
        "missing_strategy_semantics": missing,
        "fact_source_contract": {
            "trusted_account_facts": "read-only account and reconciliation facts",
            "trusted_runtime_boundary": "runtime grant, budget, leverage, attempt gate",
            "trusted_position_projection": "trusted local active-position projection",
            "trusted_market_facts": "funding, open interest, crowding proxy",
            "strategy_market_structure_facts": "closed candles and price-structure evidence",
        },
        "operator_policy": {
            "required_facts_readiness_projection_only": True,
            "does_not_evaluate_strategy": True,
            "does_not_create_shadow_candidate": True,
            "does_not_create_execution_intent": True,
            "does_not_create_order": True,
            "requires_required_facts_before_candidate_planning": True,
            "requires_trusted_account_facts": True,
            "requires_trusted_position_projection": True,
            "requires_runtime_boundary_facts": True,
            "legacy_authorization_replay_allowed": False,
            "executable_submit_allowed_by_evidence": False,
        },
        "blockers": blockers,
        "safety_invariants": {
            "required_facts_readiness_projection_only": True,
            "reads_local_semantics_only": True,
            "reads_optional_json_reports_only": True,
            "api_called_by_builder": False,
            "pg_called_by_builder": False,
            "exchange_called_by_builder": False,
            "exchange_write_called_by_builder": False,
            "order_lifecycle_called_by_builder": False,
            "submit_endpoint_called_by_builder": False,
            "strategy_evaluator_called_by_builder": False,
            "runtime_state_mutated_by_builder": False,
            "withdrawal_or_transfer_created_by_builder": False,
            "no_forbidden_live_side_effects": not forbidden_effects,
            "forbidden_effects": forbidden_effects,
        },
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a P1-B strategy RequiredFacts readiness artifact.",
    )
    parser.add_argument(
        "--strategy",
        action="append",
        default=[],
        help="Strategy as FAMILY:VERSION. May be repeated. Defaults to catalog.",
    )
    parser.add_argument("--fact-sources-json")
    parser.add_argument("--generated-at-ms", type=int)
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    artifact = build_strategy_required_facts_readiness_artifact(
        fact_sources=_read_json(args.fact_sources_json),
        strategies=list(args.strategy),
        generated_at_ms=args.generated_at_ms,
    )
    if args.output_json:
        _write_json(args.output_json, artifact)
    print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if artifact["status"] in {
        "ready_for_non_executing_strategy_runtime_planning",
        "blocked_strategy_required_facts",
        "blocked_strategy_semantics_missing",
        "observe_only_reference_semantics",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
