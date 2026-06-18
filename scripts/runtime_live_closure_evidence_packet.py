#!/usr/bin/env python3
"""Build first bounded live-order closure evidence packets from official reports.

This is a local packet assembler. It reads JSON reports that already exist and
maps their evidence ids into the first-live-closure contract. It does not call
Tokyo, FinalGate, Operation Layer, exchange write paths, or OrderLifecycle.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sys
import time
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_live_closure_evidence_verifier as verifier  # noqa: E402
from scripts import runtime_live_cutover_readiness as live_cutover  # noqa: E402


DEFAULT_OUTPUT_DIR = Path("output/strategygroup-runtime-pilot/live-closure-evidence")
DEFAULT_OUTPUT_JSON = DEFAULT_OUTPUT_DIR / "runtime-live-closure-evidence.json"

EVIDENCE_ALIASES: dict[str, tuple[str, ...]] = {
    "live_watcher_signal_packet_id": (
        "live_watcher_signal_packet_id",
        "watcher_signal_packet_id",
        "signal_packet_id",
        "signal_evaluation_id",
        "evaluation_id",
    ),
    "required_facts_readiness_packet_id": (
        "required_facts_readiness_packet_id",
        "strategy_group_live_facts_readiness_packet_id",
        "live_facts_readiness_packet_id",
        "readiness_packet_id",
    ),
    "candidate_id": (
        "candidate_id",
        "order_candidate_id",
        "shadow_candidate_id",
    ),
    "runtime_grant_id": (
        "runtime_grant_id",
        "runtime_grant_authorization_id",
        "runtime_grant",
    ),
    "fresh_submit_authorization_id": (
        "fresh_submit_authorization_id",
        "post_submit_authorization_id",
        "preflight_authorization_id",
        "authorization_id",
    ),
    "action_time_finalgate_packet_id": (
        "action_time_finalgate_packet_id",
        "action_time_final_gate_packet_id",
        "final_gate_packet_id",
        "final_gate_preview_id",
        "preflight_packet_id",
        "controlled_submit_preflight_id",
    ),
    "operation_layer_submit_authorization_id": (
        "operation_layer_submit_authorization_id",
        "exchange_submit_action_authorization_id",
        "owner_real_submit_authorization_id",
    ),
    "exchange_submit_execution_result_id": (
        "exchange_submit_execution_result_id",
        "durable_exchange_submit_execution_result_id",
    ),
    "exchange_native_hard_stop_order_id": (
        "exchange_native_hard_stop_order_id",
        "hard_stop_order_id",
        "stop_loss_order_id",
        "protective_stop_order_id",
    ),
    "runtime_post_submit_finalize_packet_id": (
        "runtime_post_submit_finalize_packet_id",
        "post_submit_finalize_packet_id",
        "finalize_packet_id",
    ),
    "post_submit_reconciliation_evidence_id": (
        "post_submit_reconciliation_evidence_id",
        "reconciliation_evidence_id",
        "reconciliation_report_id",
    ),
    "post_submit_budget_settlement_id": (
        "post_submit_budget_settlement_id",
        "budget_settlement_id",
        "settlement_id",
    ),
    "submit_outcome_review_id": (
        "submit_outcome_review_id",
        "review_id",
    ),
}
EXCHANGE_RESULT_EVIDENCE_KEY = "exchange_submit_execution_result_id"
LIVE_SIGNAL_CHAIN_KEY = "live_watcher_signal_packet_id"
PRE_SUBMIT_AUTHORIZATION_CHAIN_KEY = "fresh_submit_authorization_id"
PROTECTION_EVIDENCE_KEY = "exchange_native_hard_stop_order_id"
LIVE_SIGNAL_CHAIN_EVIDENCE_KEYS = (
    "required_facts_readiness_packet_id",
    "candidate_id",
)
PRE_SUBMIT_AUTHORIZATION_CHAIN_EVIDENCE_KEYS = (
    "candidate_id",
    "runtime_grant_id",
    "action_time_finalgate_packet_id",
    "operation_layer_submit_authorization_id",
)
POST_SUBMIT_CLOSE_LOOP_EVIDENCE_KEYS = (
    "runtime_post_submit_finalize_packet_id",
    "post_submit_reconciliation_evidence_id",
    "post_submit_budget_settlement_id",
    "submit_outcome_review_id",
)
LIVE_EXCHANGE_CALLED_KEYS = (
    "live_exchange_called",
    "exchange_write_called",
    "exchange_called",
)
REAL_ORDER_PLACED_KEYS = (
    "real_order_placed",
    "places_order",
    "exchange_order_submitted",
)
RUNTIME_BOUNDARY_FIELDS = (
    "strategy_group_id",
    "runtime_profile_id",
    "subaccount_id",
    "symbol",
    "side",
    "notional",
    "leverage",
)
RUNTIME_BOUNDARY_ALIASES: dict[str, tuple[str, ...]] = {
    "strategy_group_id": (
        "strategy_group_id",
        "strategyGroupId",
        "strategy_group",
        "strategy_id",
    ),
    "runtime_profile_id": (
        "runtime_profile_id",
        "live_profile_id",
        "profile_id",
        "runtime_profile",
    ),
    "subaccount_id": (
        "allocated_subaccount_id",
        "subaccount_id",
        "sub_account_id",
    ),
    "symbol": (
        "symbol",
        "market_symbol",
        "instrument",
    ),
    "side": (
        "side",
        "direction",
    ),
    "notional": (
        "notional",
        "order_notional",
        "notional_usdt",
        "max_notional",
    ),
    "leverage": (
        "leverage",
        "leverage_x",
    ),
}
RUNTIME_BOUNDARY_REJECT_REASONS = {
    "strategy_group_id": "strategy_group_boundary_mismatch",
    "runtime_profile_id": "runtime_profile_boundary_mismatch",
    "subaccount_id": "subaccount_boundary_mismatch",
    "symbol": "symbol_boundary_mismatch",
    "side": "side_boundary_mismatch",
    "notional": "notional_boundary_mismatch",
    "leverage": "leverage_boundary_mismatch",
}


def build_live_closure_evidence_packet(
    source_packets: list[dict[str, Any]],
    *,
    source_kind: str = "local_rehearsal_evidence",
    official_live_source: bool = False,
    evidence_overrides: dict[str, Any] | None = None,
    generated_at_ms: int | None = None,
) -> dict[str, Any]:
    contract = live_cutover.build_live_closure_cutover_contract()
    required_keys = [str(item) for item in contract.get("required_evidence_keys") or []]
    evidence = _extract_evidence(source_packets=source_packets, required_keys=required_keys)
    evidence.update(
        {
            str(key): value
            for key, value in (evidence_overrides or {}).items()
            if _present(value)
        }
    )
    present_keys = [key for key in required_keys if _present(evidence.get(key))]
    missing_keys = [key for key in required_keys if not _present(evidence.get(key))]
    live_signal_chain_proof = _live_signal_chain_proof(
        source_packets=source_packets,
        evidence=evidence,
    )
    pre_submit_authorization_chain_proof = _pre_submit_authorization_chain_proof(
        source_packets=source_packets,
        evidence=evidence,
    )
    live_submit_proof = _live_submit_proof(
        source_packets=source_packets,
        evidence=evidence,
    )
    post_submit_close_loop_proof = _post_submit_close_loop_proof(
        source_packets=source_packets,
        evidence=evidence,
    )
    exchange_native_protection_proof = _exchange_native_protection_proof(
        source_packets=source_packets,
        evidence=evidence,
    )
    runtime_boundary_proof = _runtime_boundary_proof(
        source_packets=source_packets,
        evidence=evidence,
    )
    reject_reasons = _derive_reject_reasons(
        source_packets=source_packets,
        source_kind=source_kind,
        official_live_source=official_live_source,
        evidence=evidence,
        live_signal_chain_proof=live_signal_chain_proof,
        pre_submit_authorization_chain_proof=(
            pre_submit_authorization_chain_proof
        ),
        live_submit_proof=live_submit_proof,
        exchange_native_protection_proof=exchange_native_protection_proof,
        post_submit_close_loop_proof=post_submit_close_loop_proof,
        runtime_boundary_proof=runtime_boundary_proof,
    )
    return {
        "scope": "runtime_live_closure_evidence_packet",
        "status": "live_closure_evidence_packet_built",
        "generated_at_ms": generated_at_ms or int(time.time() * 1000),
        "source_kind": source_kind,
        "official_live_closure_evidence": official_live_source,
        "contract_scope": contract.get("scope"),
        "contract_status": contract.get("status"),
        "required_evidence_keys": required_keys,
        "present_evidence_keys": present_keys,
        "missing_evidence_keys": missing_keys,
        "live_signal_chain_proof": live_signal_chain_proof,
        "pre_submit_authorization_chain_proof": (
            pre_submit_authorization_chain_proof
        ),
        "live_submit_proof": live_submit_proof,
        "exchange_native_protection_proof": exchange_native_protection_proof,
        "post_submit_close_loop_proof": post_submit_close_loop_proof,
        "runtime_boundary_proof": runtime_boundary_proof,
        "reject_reasons": reject_reasons,
        "evidence": evidence,
        "input_count": len(source_packets),
        "input_summaries": [_input_summary(packet) for packet in source_packets],
        "safety_invariants": {
            "calls_tokyo_api": False,
            "calls_live_finalgate": False,
            "calls_live_operation_layer": False,
            "exchange_write_called": False,
            "order_lifecycle_called": False,
            "withdrawal_or_transfer_created": False,
            "modifies_secret_or_credentials": False,
            "modifies_live_profile": False,
            "modifies_order_sizing_defaults": False,
        },
    }


def _extract_evidence(
    *,
    source_packets: list[dict[str, Any]],
    required_keys: list[str],
) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for key in required_keys:
        value = _first_present_value(source_packets, EVIDENCE_ALIASES.get(key, (key,)))
        if _present(value):
            evidence[key] = value
    return evidence


def _first_present_value(source_packets: list[dict[str, Any]], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        for packet in source_packets:
            value = _find_key(packet, alias)
            if _present(value):
                return value
    return None


def _find_key(value: Any, target_key: str) -> Any:
    if isinstance(value, dict):
        if target_key in value:
            return value[target_key]
        for child in value.values():
            found = _find_key(child, target_key)
            if _present(found):
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_key(child, target_key)
            if _present(found):
                return found
    return None


def _derive_reject_reasons(
    *,
    source_packets: list[dict[str, Any]],
    source_kind: str,
    official_live_source: bool,
    evidence: dict[str, Any],
    live_signal_chain_proof: dict[str, Any],
    pre_submit_authorization_chain_proof: dict[str, Any],
    live_submit_proof: dict[str, Any],
    exchange_native_protection_proof: dict[str, Any],
    post_submit_close_loop_proof: dict[str, Any],
    runtime_boundary_proof: dict[str, Any],
) -> list[str]:
    reasons: set[str] = set()
    source_kind_value = str(source_kind)
    if not official_live_source:
        reasons.add("local_rehearsal_evidence")
    if "replay" in source_kind_value:
        reasons.add("replay_signal")
    if "synthetic" in source_kind_value or "mock" in source_kind_value:
        reasons.add("synthetic_signal")

    status_text = " ".join(_status_like_values(source_packets)).lower()
    if any(token in status_text for token in ("dry_run", "rehearsal", "sample")):
        reasons.add("dry_run_or_rehearsal_evidence")
    if any(token in status_text for token in ("controlled_", "in_memory_simulation")):
        reasons.add("controlled_in_memory_execution")

    live_signal_chain_missing = set(
        str(item)
        for item in live_signal_chain_proof.get("missing_source_match_keys") or []
    )
    if live_signal_chain_missing:
        if "required_facts_readiness_packet_id" in live_signal_chain_missing:
            reasons.add("required_facts_signal_source_missing")
        if "candidate_id" in live_signal_chain_missing:
            reasons.add("candidate_signal_source_missing")

    authorization_chain_missing = set(
        str(item)
        for item in pre_submit_authorization_chain_proof.get(
            "missing_source_match_keys"
        )
        or []
    )
    if authorization_chain_missing:
        if authorization_chain_missing & {"candidate_id", "runtime_grant_id"}:
            reasons.add("candidate_authorization_chain_source_missing")
        if "action_time_finalgate_packet_id" in authorization_chain_missing:
            reasons.add("finalgate_authorization_chain_source_missing")
        if "operation_layer_submit_authorization_id" in authorization_chain_missing:
            reasons.add("operation_layer_authorization_chain_source_missing")

    exchange_result_present = _present(evidence.get("exchange_submit_execution_result_id"))
    if exchange_result_present:
        if not live_submit_proof["live_exchange_called"]:
            reasons.add("live_exchange_not_called")
        if not live_submit_proof["real_order_placed"]:
            reasons.add("real_order_not_placed")
        if False in _bool_values(source_packets, "executes_real_submit"):
            reasons.add("real_order_not_placed")
        if False in _bool_values(source_packets, "live_submit_allowed"):
            reasons.add("real_order_not_placed")
        if True in _bool_values(source_packets, "controlled_fake_gateway_called"):
            reasons.add("controlled_in_memory_execution")
        if True in _bool_values(source_packets, "controlled_order_lifecycle_submit_called"):
            reasons.add("controlled_in_memory_execution")
        if True in _bool_values(source_packets, "controlled_in_memory_execution_result_recorded"):
            reasons.add("controlled_in_memory_execution")
        if (
            _present(evidence.get(PROTECTION_EVIDENCE_KEY))
            and not exchange_native_protection_proof.get("result_source_matched")
        ):
            reasons.add("exchange_native_protection_result_source_missing")
        close_loop_missing = set(
            str(item)
            for item in post_submit_close_loop_proof.get(
                "missing_source_match_keys"
            )
            or []
        )
        if close_loop_missing:
            if "runtime_post_submit_finalize_packet_id" in close_loop_missing:
                reasons.add("post_submit_finalize_result_source_missing")
            if close_loop_missing - {"runtime_post_submit_finalize_packet_id"}:
                reasons.add("post_submit_close_loop_result_source_missing")
    for field in runtime_boundary_proof.get("conflict_fields") or []:
        reason = RUNTIME_BOUNDARY_REJECT_REASONS.get(str(field))
        if reason:
            reasons.add(reason)
    return sorted(reasons)


def _live_signal_chain_proof(
    *,
    source_packets: list[dict[str, Any]],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    live_watcher_signal_packet_id = _evidence_id(evidence.get(LIVE_SIGNAL_CHAIN_KEY))
    present_keys: list[str] = []
    matched_keys: list[str] = []
    missing_source_match_keys: list[str] = []
    for key in LIVE_SIGNAL_CHAIN_EVIDENCE_KEYS:
        evidence_id = _evidence_id(evidence.get(key))
        if not evidence_id:
            continue
        present_keys.append(key)
        key_source_packets = _source_packets_for_evidence_id(
            source_packets,
            aliases=EVIDENCE_ALIASES[key],
            evidence_id=evidence_id,
        )
        signal_bound = bool(live_watcher_signal_packet_id) and any(
            _packet_has_evidence_id(
                packet,
                aliases=EVIDENCE_ALIASES[LIVE_SIGNAL_CHAIN_KEY],
                evidence_id=live_watcher_signal_packet_id,
            )
            for packet in key_source_packets
        )
        if signal_bound:
            matched_keys.append(key)
        else:
            missing_source_match_keys.append(key)
    proof: dict[str, Any] = {
        "present_evidence_keys": present_keys,
        "matched_evidence_keys": matched_keys,
        "missing_source_match_keys": missing_source_match_keys,
    }
    if live_watcher_signal_packet_id:
        proof["live_watcher_signal_packet_id"] = live_watcher_signal_packet_id
    return proof


def _pre_submit_authorization_chain_proof(
    *,
    source_packets: list[dict[str, Any]],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    fresh_submit_authorization_id = _evidence_id(
        evidence.get(PRE_SUBMIT_AUTHORIZATION_CHAIN_KEY)
    )
    present_keys: list[str] = []
    matched_keys: list[str] = []
    missing_source_match_keys: list[str] = []
    for key in PRE_SUBMIT_AUTHORIZATION_CHAIN_EVIDENCE_KEYS:
        evidence_id = _evidence_id(evidence.get(key))
        if not evidence_id:
            continue
        present_keys.append(key)
        key_source_packets = _source_packets_for_evidence_id(
            source_packets,
            aliases=EVIDENCE_ALIASES[key],
            evidence_id=evidence_id,
        )
        authorization_bound = bool(fresh_submit_authorization_id) and any(
            _packet_has_evidence_id(
                packet,
                aliases=EVIDENCE_ALIASES[PRE_SUBMIT_AUTHORIZATION_CHAIN_KEY],
                evidence_id=fresh_submit_authorization_id,
            )
            for packet in key_source_packets
        )
        if authorization_bound:
            matched_keys.append(key)
        else:
            missing_source_match_keys.append(key)
    proof: dict[str, Any] = {
        "present_evidence_keys": present_keys,
        "matched_evidence_keys": matched_keys,
        "missing_source_match_keys": missing_source_match_keys,
    }
    if fresh_submit_authorization_id:
        proof["fresh_submit_authorization_id"] = fresh_submit_authorization_id
    return proof


def _live_submit_proof(
    *,
    source_packets: list[dict[str, Any]],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    exchange_submit_execution_result_id = _evidence_id(
        evidence.get(EXCHANGE_RESULT_EVIDENCE_KEY)
    )
    exchange_result_present = exchange_submit_execution_result_id is not None
    result_source_packets = _source_packets_for_evidence_id(
        source_packets,
        aliases=EVIDENCE_ALIASES[EXCHANGE_RESULT_EVIDENCE_KEY],
        evidence_id=exchange_submit_execution_result_id,
    )
    proof: dict[str, Any] = {
        "exchange_result_present": exchange_result_present,
        "result_source_matched": bool(result_source_packets),
        "result_source_count": len(result_source_packets),
        "live_exchange_called": _any_true(
            result_source_packets,
            LIVE_EXCHANGE_CALLED_KEYS,
        ),
        "real_order_placed": _any_true(
            result_source_packets,
            REAL_ORDER_PLACED_KEYS,
        ),
    }
    if exchange_submit_execution_result_id:
        proof["exchange_submit_execution_result_id"] = (
            exchange_submit_execution_result_id
        )
    return proof


def _exchange_native_protection_proof(
    *,
    source_packets: list[dict[str, Any]],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    exchange_submit_execution_result_id = _evidence_id(
        evidence.get(EXCHANGE_RESULT_EVIDENCE_KEY)
    )
    exchange_native_hard_stop_order_id = _evidence_id(
        evidence.get(PROTECTION_EVIDENCE_KEY)
    )
    protection_source_packets = _source_packets_for_evidence_id(
        source_packets,
        aliases=EVIDENCE_ALIASES[PROTECTION_EVIDENCE_KEY],
        evidence_id=exchange_native_hard_stop_order_id,
    )
    result_source_matched = bool(exchange_submit_execution_result_id) and any(
        _packet_has_evidence_id(
            packet,
            aliases=EVIDENCE_ALIASES[EXCHANGE_RESULT_EVIDENCE_KEY],
            evidence_id=exchange_submit_execution_result_id,
        )
        for packet in protection_source_packets
    )
    proof: dict[str, Any] = {
        "hard_stop_present": exchange_native_hard_stop_order_id is not None,
        "result_source_matched": result_source_matched,
        "result_source_count": len(protection_source_packets),
    }
    if exchange_submit_execution_result_id:
        proof["exchange_submit_execution_result_id"] = (
            exchange_submit_execution_result_id
        )
    if exchange_native_hard_stop_order_id:
        proof["exchange_native_hard_stop_order_id"] = (
            exchange_native_hard_stop_order_id
        )
    return proof


def _post_submit_close_loop_proof(
    *,
    source_packets: list[dict[str, Any]],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    exchange_submit_execution_result_id = _evidence_id(
        evidence.get(EXCHANGE_RESULT_EVIDENCE_KEY)
    )
    present_keys: list[str] = []
    matched_keys: list[str] = []
    missing_source_match_keys: list[str] = []
    for key in POST_SUBMIT_CLOSE_LOOP_EVIDENCE_KEYS:
        evidence_id = _evidence_id(evidence.get(key))
        if not evidence_id:
            continue
        present_keys.append(key)
        key_source_packets = _source_packets_for_evidence_id(
            source_packets,
            aliases=EVIDENCE_ALIASES[key],
            evidence_id=evidence_id,
        )
        result_bound = bool(exchange_submit_execution_result_id) and any(
            _packet_has_evidence_id(
                packet,
                aliases=EVIDENCE_ALIASES[EXCHANGE_RESULT_EVIDENCE_KEY],
                evidence_id=exchange_submit_execution_result_id,
            )
            for packet in key_source_packets
        )
        if result_bound:
            matched_keys.append(key)
        else:
            missing_source_match_keys.append(key)
    proof: dict[str, Any] = {
        "present_evidence_keys": present_keys,
        "matched_evidence_keys": matched_keys,
        "missing_source_match_keys": missing_source_match_keys,
    }
    if exchange_submit_execution_result_id:
        proof["exchange_submit_execution_result_id"] = (
            exchange_submit_execution_result_id
        )
    return proof


def _runtime_boundary_proof(
    *,
    source_packets: list[dict[str, Any]],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    boundary_source_packets = _runtime_boundary_source_packets(
        source_packets=source_packets,
        evidence=evidence,
    )
    values: dict[str, list[str]] = {}
    for field in RUNTIME_BOUNDARY_FIELDS:
        field_values: list[str] = []
        for packet in boundary_source_packets:
            for alias in RUNTIME_BOUNDARY_ALIASES[field]:
                for value in _collect_values_for_keys(packet, {alias}):
                    normalized = _normalize_boundary_value(field, value)
                    if normalized and normalized not in field_values:
                        field_values.append(normalized)
        values[field] = field_values
    observed_fields = [field for field, field_values in values.items() if field_values]
    missing_fields = [
        field for field, field_values in values.items() if not field_values
    ]
    conflict_fields = [
        field for field, field_values in values.items() if len(field_values) > 1
    ]
    return {
        "source_packet_count": len(boundary_source_packets),
        "observed_fields": observed_fields,
        "missing_fields": missing_fields,
        "conflict_fields": conflict_fields,
        "values": values,
    }


def _runtime_boundary_source_packets(
    *,
    source_packets: list[dict[str, Any]],
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    matched_ids: set[int] = set()
    for key, aliases in EVIDENCE_ALIASES.items():
        evidence_id = _evidence_id(evidence.get(key))
        if not evidence_id:
            continue
        for packet in _source_packets_for_evidence_id(
            source_packets,
            aliases=aliases,
            evidence_id=evidence_id,
        ):
            packet_id = id(packet)
            if packet_id in matched_ids:
                continue
            matched.append(packet)
            matched_ids.add(packet_id)
    return matched


def _source_packets_for_evidence_id(
    source_packets: list[dict[str, Any]],
    *,
    aliases: tuple[str, ...],
    evidence_id: str | None,
) -> list[dict[str, Any]]:
    if not evidence_id:
        return []
    matched: list[dict[str, Any]] = []
    for packet in source_packets:
        if _packet_has_evidence_id(
            packet,
            aliases=aliases,
            evidence_id=evidence_id,
        ):
            matched.append(packet)
    return matched


def _packet_has_evidence_id(
    packet: dict[str, Any],
    *,
    aliases: tuple[str, ...],
    evidence_id: str | None,
) -> bool:
    if not evidence_id:
        return False
    return any(
        _evidence_id(_find_key(packet, alias)) == evidence_id
        for alias in aliases
    )


def _status_like_values(source_packets: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for packet in source_packets:
        values.extend(_collect_values_for_keys(packet, {"scope", "status", "source_kind", "execution_mode"}))
    return [str(item) for item in values if str(item)]


def _bool_values(source_packets: list[dict[str, Any]], target_key: str) -> list[bool]:
    return [
        item
        for packet in source_packets
        for item in _collect_values_for_keys(packet, {target_key})
        if isinstance(item, bool)
    ]


def _any_true(source_packets: list[dict[str, Any]], target_keys: tuple[str, ...]) -> bool:
    return any(
        item is True
        for packet in source_packets
        for item in _collect_values_for_keys(packet, set(target_keys))
        if isinstance(item, bool)
    )


def _collect_values_for_keys(value: Any, keys: set[str]) -> list[Any]:
    values: list[Any] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in keys:
                values.append(child)
            values.extend(_collect_values_for_keys(child, keys))
    elif isinstance(value, list):
        for child in value:
            values.extend(_collect_values_for_keys(child, keys))
    return values


def _normalize_boundary_value(field: str, value: Any) -> str | None:
    text = _string_or_none(value)
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    if field in {"strategy_group_id", "symbol"}:
        return text.upper()
    if field == "side":
        return text.lower()
    if field in {"notional", "leverage"}:
        try:
            number = Decimal(text)
        except (InvalidOperation, ValueError):
            return text
        return format(number.normalize(), "f")
    return text


def _input_summary(packet: dict[str, Any]) -> dict[str, str | None]:
    return {
        "scope": _string_or_none(packet.get("scope")),
        "status": _string_or_none(packet.get("status")),
        "source_kind": _string_or_none(packet.get("source_kind")),
    }


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _evidence_id(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, dict):
        for field in ("id", "evidence_id", "packet_id", "ref_id", "reference_id"):
            nested = value.get(field)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parse_evidence_overrides(items: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not key.strip():
            raise ValueError(f"Invalid --evidence-id value: {item!r}")
        overrides[key.strip()] = value.strip()
    return overrides


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build first bounded live-order closure evidence packet."
    )
    parser.add_argument("--input-json", action="append", default=[])
    parser.add_argument("--evidence-id", action="append", default=[])
    parser.add_argument("--source-kind", default="local_rehearsal_evidence")
    parser.add_argument("--official-live-source", action="store_true")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--verify-output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    source_packets = [
        _read_json(Path(item).expanduser()) for item in args.input_json
    ]
    source_kind = (
        "official_live_closure_evidence"
        if args.official_live_source
        else args.source_kind
    )
    packet = build_live_closure_evidence_packet(
        source_packets,
        source_kind=source_kind,
        official_live_source=args.official_live_source,
        evidence_overrides=_parse_evidence_overrides(args.evidence_id),
    )
    _write_json(Path(args.output_json).expanduser(), packet)
    if args.verify_output_json:
        verification = verifier.build_live_closure_evidence_verification(packet)
        _write_json(Path(args.verify_output_json).expanduser(), verification)
    print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
