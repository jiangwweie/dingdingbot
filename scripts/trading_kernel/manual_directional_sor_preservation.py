"""Prove the bounded authority delta while preserving all existing history."""

from __future__ import annotations

import json
from collections.abc import Callable

from src.trading_kernel.domain.directional_risk import (
    DIRECTIONAL_RULES,
    DIRECTIONAL_SOR_RULE_DIGEST,
    DIRECTIONAL_SOR_RULE_ID,
    RULE_LIMITS,
)
from src.trading_kernel.domain.orb_session_selection import (
    ORB_DIRECTIONAL_EVENTS,
    ORB_DIRECTIONAL_GROUPS,
    ORB_EVENT_SPEC_IDS,
    ORB_STRATEGY_GROUP_ID,
    directional_orb_spec,
)
from src.trading_kernel.domain.risk_budget import BUDGET_CONTRACT
from src.trading_kernel.domain.strategy_registry import (
    build_registry_semantic_hash,
    registered_strategy_contracts,
)

# Only these tables may differ in the stopped identity transaction.
DIRECTIONAL_DELTA_TABLES = frozenset(
    {
        "brc_directional_risk_controls",
        "brc_directional_risk_events",
        "brc_directional_risk_rules",
        "brc_event_exit_profile_binding_current",
        "brc_event_exit_profile_binding_events",
        "brc_event_exit_profile_bindings",
        "brc_event_product_compatibility",
        "brc_event_required_facts",
        "brc_event_specs",
        "brc_instrument_selection_spec_events",
        "brc_instrument_selection_spec_members",
        "brc_instrument_selection_specs",
        "brc_orb_session_selection_specs_v1",
        "brc_owner_authorizations",
        "brc_owner_policy_current",
        "brc_owner_policy_events",
        "brc_runtime_scopes_current",
        "brc_strategy_entry_control_events",
        "brc_strategy_entry_controls_current",
        "brc_strategy_groups",
        "brc_strategy_selection_control_current",
        "brc_strategy_universe_current",
        "brc_strategy_universe_versions",
        "brc_strategy_versions",
    }
)


def _expect(condition: bool, label: str) -> None:
    if not condition:
        raise ValueError(f"directional SOR preservation differs at {label}")


def verify_directional_sor_controls(before: dict, after: dict) -> None:
    old = before["policy"]
    new = after["policy"]
    _expect(len(old) == len(new) == 1, "policy identity")
    policy = old[0]
    current = new[0]
    scope = {
        item["event_spec_id"]: item["runtime_profile_id"]
        for item in policy["scope"]["event_runtime_profiles"]
    }
    for source, target in zip(ORB_EVENT_SPEC_IDS, ORB_DIRECTIONAL_EVENTS, strict=True):
        _expect(
            scope.get(source) == "tiny-live-v1" and target not in scope, "source scope"
        )
        scope[target] = scope.pop(source)
    updated_scope = {
        "event_runtime_profiles": [
            {"event_spec_id": event, "runtime_profile_id": profile}
            for event, profile in sorted(scope.items())
        ]
    }
    _expect(
        policy["new_entry_submit_enabled"] is False
        and current["updated_at_ms"] > policy["updated_at_ms"]
        and current
        == {
            **policy,
            "scope": updated_scope,
            "policy_version": policy["policy_version"] + 1,
            "updated_at_ms": current["updated_at_ms"],
        },
        "paused policy and limits",
    )
    for key in ("controls", "selection"):
        untouched = [
            row
            for row in after[key]
            if row["strategy_group_id"] not in ORB_DIRECTIONAL_GROUPS
        ]
        _expect(untouched == before[key], key)
        inserted = {
            row["strategy_group_id"]: row
            for row in after[key]
            if row["strategy_group_id"] in ORB_DIRECTIONAL_GROUPS
        }
        _expect(set(inserted) == set(ORB_DIRECTIONAL_GROUPS), f"{key} identities")
        for group, row in inserted.items():
            _expect(row["control_version"] == 1, f"{key} version")
            if key == "controls":
                _expect(row["entry_state"] == "paused", group)
            else:
                _expect(
                    row["selection_mode"] == "static_baseline"
                    and row["selection_spec_id"]
                    == directional_orb_spec(group).selection_spec_id
                    and row["pending_selection_mode"] is None
                    and row["selection_epoch_id"] is None,
                    group,
                )


def verify_directional_sor_preservation(
    before: dict, after: dict, *, account_id: str, commit: str
) -> None:
    verify_directional_sor_controls(before, after)
    ignore = {
        "directional_delta",
        "preserved_table_rows",
        "policy",
        "controls",
        "selection",
        "active_universe_manifest_digest",
        "active_current_count",
    }
    _expect(
        {k: v for k, v in before.items() if k not in ignore}
        == {k: v for k, v in after.items() if k not in ignore},
        "preserved evidence",
    )
    _expect(
        {
            k: v
            for k, v in before["preserved_table_rows"].items()
            if k not in DIRECTIONAL_DELTA_TABLES
        }
        == {
            k: v
            for k, v in after["preserved_table_rows"].items()
            if k not in DIRECTIONAL_DELTA_TABLES
        },
        "unchanged table digests",
    )
    old, new = before["directional_delta"], after["directional_delta"]
    _expect(set(old) == set(new) == DIRECTIONAL_DELTA_TABLES, "delta inventory")
    timestamp = after["policy"][0]["updated_at_ms"]
    policy_version = after["policy"][0]["policy_version"]
    specs = {
        directional_orb_spec(group).selection_spec_id
        for group in ORB_DIRECTIONAL_GROUPS
    }
    target_events = set(ORB_DIRECTIONAL_EVENTS)
    auth_ids = {f"owner-authorization:seed:{group}" for group in ORB_DIRECTIONAL_GROUPS}
    retired_universes = {
        row["universe_version_id"]
        for row in old["brc_strategy_universe_current"]
        if row["event_spec_id"] in ORB_EVENT_SPEC_IDS
    }
    _expect(
        after["active_current_count"]
        == before["active_current_count"] - len(retired_universes),
        "retired universe count",
    )

    def compare(
        table: str,
        *,
        map_source: Callable[[dict], dict | None] = lambda row: row,
        introduced: Callable[[dict], bool] = lambda row: False,
        added: int = 0,
    ) -> None:
        expected = [
            value for row in old[table] if (value := map_source(row)) is not None
        ]
        untouched = [row for row in new[table] if not introduced(row)]
        _expect(
            sorted(map(_canonical, expected)) == sorted(map(_canonical, untouched)),
            table,
        )
        _expect(len(new[table]) - len(untouched) == added, f"{table} addition count")

    by_event: Callable[[dict], bool] = lambda row: row["event_spec_id"] in target_events
    by_group: Callable[[dict], bool] = lambda row: (
        row["strategy_group_id"] in ORB_DIRECTIONAL_GROUPS
    )
    by_spec: Callable[[dict], bool] = lambda row: row["selection_spec_id"] in specs
    contracts = registered_strategy_contracts(include_sor_split=True)
    new_contracts = tuple(
        contract for contract in contracts if contract.event_spec_id in target_events
    )
    registry_hash = build_registry_semantic_hash(contracts)
    registered_versions = {contract.strategy_version_id for contract in contracts}

    compare(
        "brc_strategy_groups",
        introduced=by_group,
        added=2,
        map_source=lambda row: (
            {**row, "status": "disabled", "updated_at_ms": timestamp}
            if row["strategy_group_id"] == ORB_STRATEGY_GROUP_ID
            else row
        ),
    )
    compare(
        "brc_strategy_versions",
        introduced=by_group,
        added=2,
        map_source=lambda row: (
            {
                **row,
                "semantics": {
                    **row["semantics"],
                    "registry_semantic_hash": registry_hash,
                },
            }
            if row["strategy_version_id"] in registered_versions
            else row
        ),
    )
    for table in (
        "brc_event_specs",
        "brc_event_exit_profile_bindings",
        "brc_event_exit_profile_binding_current",
        "brc_event_exit_profile_binding_events",
        "brc_event_product_compatibility",
    ):
        compare(table, introduced=by_event, added=2)
    compare(
        "brc_event_required_facts",
        introduced=by_event,
        added=sum(
            len(contract.required_facts) + len(contract.disable_facts)
            for contract in new_contracts
        ),
    )
    for table, count in (
        ("brc_instrument_selection_specs", 2),
        ("brc_orb_session_selection_specs_v1", 2),
        ("brc_instrument_selection_spec_events", 2),
        ("brc_instrument_selection_spec_members", 48),
    ):
        compare(table, introduced=by_spec, added=count)
    for table in (
        "brc_strategy_selection_control_current",
        "brc_strategy_entry_controls_current",
        "brc_strategy_entry_control_events",
    ):
        compare(table, introduced=by_group, added=2)
    compare(
        "brc_owner_authorizations",
        introduced=lambda row: row["authorization_id"] in auth_ids,
        added=2,
    )
    compare("brc_owner_policy_current", map_source=lambda row: {
        **row, "scope": after["policy"][0]["scope"],
        "updated_at_ms": timestamp, "policy_version": policy_version,
    })
    compare(
        "brc_owner_policy_events",
        introduced=lambda row: (
            row["policy_version"] == policy_version
            and row["operation"] == "orb_directional_policy_scope_prepared"
            and row["payload"]["scope"] == after["policy"][0]["scope"]
            and row["payload"]["new_entry_submit_enabled"] is False
        ),
        added=1,
    )
    compare(
        "brc_strategy_universe_current",
        map_source=lambda row: (
            None if row["universe_version_id"] in retired_universes else row
        ),
    )
    compare(
        "brc_strategy_universe_versions",
        map_source=lambda row: (
            {
                **row,
                "lifecycle_state": "retired",
                "retired_at_ms": timestamp,
            }
            if row["universe_version_id"] in retired_universes
            else row
        ),
    )
    compare(
        "brc_runtime_scopes_current",
        map_source=lambda row: (
            {
                **row,
                "lifecycle_state": "retired",
                "entry_enabled": False,
                "observation_enabled": False,
                "scope_version": row["scope_version"] + 1,
                "observation_generation": row["observation_generation"] + 1,
                "next_observation_due_at_ms": None,
                "lease_owner": None,
                "lease_expires_at_ms": None,
                "updated_at_ms": timestamp,
            }
            if row["universe_version_id"] in retired_universes
            else row
        ),
    )
    compare(
        "brc_directional_risk_rules",
        introduced=lambda row: (
            row
            == {
                "rule_id": DIRECTIONAL_SOR_RULE_ID,
                "rule_digest": DIRECTIONAL_SOR_RULE_DIGEST,
                "limits": {k: list(v) for k, v in RULE_LIMITS.items()},
                "event_spec_ids": sorted(DIRECTIONAL_RULES[DIRECTIONAL_SOR_RULE_ID][1]),
                "budget_contract": BUDGET_CONTRACT,
            }
        ),
        added=1,
    )
    compare(
        "brc_directional_risk_controls",
        map_source=lambda row: (
            {
                **row,
                "rule_id": DIRECTIONAL_SOR_RULE_ID,
                "rule_digest": DIRECTIONAL_SOR_RULE_DIGEST,
                "version": row["version"] + 1,
            }
            if row["venue_id"] == "binance-usdm" and row["account_id"] == account_id
            else row
        ),
    )
    compare(
        "brc_directional_risk_events",
        introduced=lambda row: (
            row["event_id"] == f"directional-rule:{account_id}:v3"
            and row["event_kind"] == "scope_migrated"
            and row["payload"]["runtime_commit"] == commit
        ),
        added=1,
    )


def _canonical(row: dict) -> str:
    return json.dumps(row, sort_keys=True, default=str, separators=(",", ":"))
