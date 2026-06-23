#!/usr/bin/env python3
"""Build or validate the current StrategyGroup tier review packet.

The tier review packet turns registry rows plus current tier policy and the
generated Decision Ledger into one current next-action decision per
StrategyGroup. It is local governance evidence only and never grants live
authority.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-registry-baseline.json"
)
DEFAULT_TIER_POLICY_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/main-control-runtime-tier-policy.json"
)
DEFAULT_DECISION_LEDGER_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-strategygroup-decision-ledger.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-tier-review-current.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT
    / "docs/current/strategy-group-handoffs/strategygroup-tier-review-current.md"
)

EXPECTED_TIERS = {
    "MPG-001": "L4",
    "TEQ-001": "L2",
    "FBS-001": "L3",
    "SOR-001": "L3",
    "PMR-001": "L1",
    "BTPC-001": "L2",
    "VCB-001": "L1",
    "LSR-001": "L1",
    "BRF-001": "L1",
    "RBR-001": "L1",
}
EXPECTED_GROUPS = list(EXPECTED_TIERS)
REQUIRED_ROW_FIELDS = [
    "strategy_group_id",
    "current_tier",
    "registry_trial_eligible",
    "actionable_now",
    "current_decision",
    "promotion_scope",
    "promotion_target",
    "decision_source",
    "recommended_next_action",
    "owner_decision_needed",
    "required_next_evidence",
    "do_not_promote_reason",
    "authority_boundary",
]
SAFETY_INVARIANTS = {
    "real_order_authority": False,
    "calls_finalgate": False,
    "calls_operation_layer": False,
    "calls_exchange_write": False,
    "places_order": False,
    "changes_live_profile": False,
    "changes_order_sizing_defaults": False,
    "withdrawal_or_transfer": False,
}
AUTHORITY_BOUNDARY = (
    "tier_review_support_only; actionable_now=false; real_order_authority=false; "
    "no_exchange_write; no_live_profile_or_sizing_change"
)


def build_tier_review_packet(
    registry: dict[str, Any],
    tier_policy: dict[str, Any],
    decision_ledger: dict[str, Any] | None,
) -> dict[str, Any]:
    ledger_rows, ledger_status = _ledger_rows_and_status(decision_ledger)
    ledger_by_group = {row["strategy_group_id"]: row for row in ledger_rows}
    registry_rows = _dict_rows(registry.get("rows"))
    policy_groups = _as_dict(tier_policy.get("current_strategy_groups"))

    rows = []
    for registry_row in registry_rows:
        group = str(registry_row.get("strategy_group_id") or "")
        policy_row = _as_dict(policy_groups.get(group))
        current_tier = str(policy_row.get("tier") or registry_row.get("default_tier") or "")
        ledger_row = ledger_by_group.get(group)
        rows.append(_build_review_row(registry_row, policy_row, ledger_row, current_tier))

    packet = {
        "schema": "brc.strategygroup_tier_review.v1",
        "status": "tier_review_ready",
        "scope": "strategygroup_tier_review_current",
        "source_authority": {
            "registry_baseline": (
                "docs/current/strategy-group-handoffs/"
                "strategygroup-registry-baseline.json"
            ),
            "tier_policy": (
                "docs/current/strategy-group-handoffs/"
                "main-control-runtime-tier-policy.json"
            ),
            "decision_ledger": (
                "output/runtime-monitor/latest-strategygroup-decision-ledger.json"
            ),
        },
        "ledger_status": ledger_status,
        "actionability_contract": {
            "actionable_now_source": "runtime_state_only",
            "static_tier_review_must_not_set_actionable_now_true": True,
            "strategy_uncertainty_is_not_execution_blocker": True,
            "owner_scoped_risk_acceptance_may_promote_trial_eligibility": True,
            "owner_scoped_risk_acceptance_cannot_set_actionable_now_true": True,
        },
        "safety_invariants": deepcopy(SAFETY_INVARIANTS),
        "required_row_fields": REQUIRED_ROW_FIELDS,
        "rows": rows,
        "decision_counts": _decision_counts(rows),
    }
    return packet


def build_owner_markdown(packet: dict[str, Any]) -> str:
    rows = _dict_rows(packet.get("rows"))
    lines = [
        "---",
        "title: STRATEGYGROUP_TIER_REVIEW_CURRENT",
        "status: CURRENT",
        "authority: docs/current/strategy-group-handoffs/strategygroup-tier-review-current.json",
        "last_verified: 2026-06-20",
        "---",
        "",
        "# StrategyGroup Tier Review Current",
        "",
        "## 目的",
        "",
        "这份 review 把 StrategyGroup 从“策略资产是什么”推进到“下一步怎么走”。它消费 Registry Baseline、Runtime Tier Policy 和 Decision Ledger，给每个策略组一条当前推进判断。",
        "",
        "静态 review 不代表当前可以下单。`actionable_now` 只能由运行时根据新鲜信号、账户、保护、订单和交易所事实判断，因此这里始终为 `false`。",
        "",
        "## 总览",
        "",
        _summary_table(rows),
        "",
        "## Owner 读法",
        "",
        "- `wait_for_live_outcome`: 保持 P0 实盘链路待命，等待真实市场机会和后续结果。",
        "- `keep`: 维持当前层级继续观察，不晋级。",
        "- `revise`: 先修 facts / classifier / replay 证据，再谈层级变化。",
        "- `park`: 暂停主动推进，除非出现新证据。",
        "- `do_not_go_live`: 当前不进入实盘，缺少足够证据或政策基础。",
        "- 策略不确定性不是执行安全 blocker；它只影响 revise、tier、观察或 Owner 风险接受路径。",
        "",
        "## 分组判断",
        "",
    ]
    for row in rows:
        lines.extend(_row_section(row))
    lines.extend(
        [
            "## 权限边界",
            "",
            "本 review 只服务层级治理和策略学习，不授权下单、不修改实盘配置、不修改杠杆/仓位/订单大小默认值、不创建提现或划转动作。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def validate_inputs(
    registry: dict[str, Any],
    tier_policy: dict[str, Any],
    *,
    require_exact_policy_tiers: bool = True,
) -> list[str]:
    errors: list[str] = []
    registry_rows = _dict_rows(registry.get("rows"))
    groups = [str(row.get("strategy_group_id") or "") for row in registry_rows]
    if groups != EXPECTED_GROUPS:
        errors.append(f"registry_group_order_mismatch:{groups}")

    policy_groups = _as_dict(tier_policy.get("current_strategy_groups"))
    for row in registry_rows:
        group = str(row.get("strategy_group_id") or "")
        expected_tier = EXPECTED_TIERS.get(group)
        registry_tier = str(row.get("default_tier") or "")
        if registry_tier != expected_tier:
            errors.append(
                f"registry_tier_mismatch:{group}:expected={expected_tier}:actual={registry_tier}"
            )
        policy_row = _as_dict(policy_groups.get(group))
        if policy_row:
            policy_tier = str(policy_row.get("tier") or "")
            if require_exact_policy_tiers and policy_tier != expected_tier:
                errors.append(
                    f"tier_policy_mismatch:{group}:expected={expected_tier}:actual={policy_tier}"
                )
            if policy_tier and policy_tier != registry_tier:
                errors.append(
                    f"registry_policy_tier_drift:{group}:registry={registry_tier}:policy={policy_tier}"
                )
    return errors


def validate_packet(packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if packet.get("schema") != "brc.strategygroup_tier_review.v1":
        errors.append("schema_mismatch")
    rows = _dict_rows(packet.get("rows"))
    groups = [str(row.get("strategy_group_id") or "") for row in rows]
    if groups != EXPECTED_GROUPS:
        errors.append(f"row_group_order_mismatch:{groups}")
    safety = _as_dict(packet.get("safety_invariants"))
    for key, expected in SAFETY_INVARIANTS.items():
        if safety.get(key) is not expected:
            errors.append(f"safety_invariant_not_false:{key}")
    for row in rows:
        group = str(row.get("strategy_group_id") or "unknown")
        for field in REQUIRED_ROW_FIELDS:
            if field not in row:
                errors.append(f"{group}.missing_field:{field}")
        if row.get("actionable_now") is True:
            errors.append(f"{group}.actionable_now_true")
        if row.get("authority_boundary") != AUTHORITY_BOUNDARY:
            errors.append(f"{group}.authority_boundary_mismatch")
        if row.get("recommended_next_action") not in {
            "keep",
            "revise",
            "promote",
            "promote_review_only",
            "park",
            "kill",
            "do_not_go_live",
            "wait_for_live_outcome",
        }:
            errors.append(f"{group}.unexpected_recommended_next_action")
        if row.get("current_decision") in {"promote", "promote_review_only"}:
            scope = str(row.get("promotion_scope") or "not_applicable")
            if scope == "not_applicable":
                errors.append(f"{group}.missing_promotion_scope")
        row_safety = _as_dict(row.get("safety_invariants"))
        for key in (
            "real_order_authority",
            "calls_finalgate",
            "calls_operation_layer",
            "calls_exchange_write",
            "places_order",
        ):
            if row_safety.get(key) is not False:
                errors.append(f"{group}.row_safety_invariant_not_false:{key}")
    return errors


def load_inputs(
    registry_path: Path,
    tier_policy_path: Path,
    decision_ledger_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    registry = _load_json(registry_path)
    tier_policy = _load_json(tier_policy_path)
    decision_ledger = None
    if decision_ledger_path.exists():
        decision_ledger = _load_json(decision_ledger_path)
    return registry, tier_policy, decision_ledger


def _build_review_row(
    registry_row: dict[str, Any],
    policy_row: dict[str, Any],
    ledger_row: dict[str, Any] | None,
    current_tier: str,
) -> dict[str, Any]:
    group = str(registry_row.get("strategy_group_id") or "")
    if ledger_row:
        return _row_from_ledger(registry_row, ledger_row, current_tier)
    if group == "MPG-001":
        return _base_row(
            registry_row,
            current_tier,
            current_decision="preserve_p0_live_lane_waiting_for_market",
            decision_source="registry_and_p0_runtime_policy",
            recommended_next_action="wait_for_live_outcome",
            owner_decision_needed=False,
            required_next_evidence=(
                "fresh selected signal plus first allocated-subaccount live outcome"
            ),
            do_not_promote_reason=(
                "already_l4_live_trial_lane; no further tier promotion is needed"
            ),
        )

    policy_reason = str(policy_row.get("reason") or "no current Decision Ledger row")
    return _base_row(
        registry_row,
        current_tier,
        current_decision="keep_current_tier_no_promotion_evidence",
        decision_source="registry_and_tier_policy",
        recommended_next_action="keep",
        owner_decision_needed=False,
        required_next_evidence=str(
            registry_row.get("required_next_evidence") or "decision-changing evidence"
        ),
        do_not_promote_reason=(
            "strategy uncertainty is not an execution blocker, but there is no "
            f"current decision evidence for promotion or live scope change; {policy_reason}"
        ),
    )


def _row_from_ledger(
    registry_row: dict[str, Any],
    ledger_row: dict[str, Any],
    current_tier: str,
) -> dict[str, Any]:
    decision = str(ledger_row.get("decision") or "")
    promotion_target = str(ledger_row.get("promotion_target") or "not_applicable")
    promotion_scope = _display_promotion_scope(ledger_row)
    display_decision = _display_decision(decision, promotion_target)
    action = {
        "keep_observing": "keep",
        "revise": "revise",
        "park": "park",
        "kill": "kill",
        "promote": "promote_review_only"
        if promotion_target == "promotion_evidence_review_only"
        else "promote",
        "go_live": "promote",
        "do_not_go_live": "do_not_go_live",
        "block_for_safety": "do_not_go_live",
    }.get(decision, "do_not_go_live")
    if decision == "keep_observing":
        reason = "current ledger supports continued observation, not tier promotion"
    elif decision == "revise":
        reason = "current ledger requires revision before any tier change"
    elif decision == "park":
        reason = "current ledger parks this StrategyGroup until new evidence"
    else:
        reason = "current ledger does not provide live-scope authority"
    return _base_row(
        registry_row,
        current_tier,
        current_decision=display_decision,
        promotion_scope=promotion_scope,
        promotion_target=promotion_target,
        decision_source="decision_ledger",
        recommended_next_action=action,
        owner_decision_needed=action == "promote",
        required_next_evidence=str(
            ledger_row.get("required_next_evidence")
            or registry_row.get("required_next_evidence")
            or "decision-changing evidence"
        ),
        do_not_promote_reason=reason,
        ledger_reason=str(ledger_row.get("reason") or ""),
        next_checkpoint=str(ledger_row.get("next_checkpoint") or ""),
    )


def _base_row(
    registry_row: dict[str, Any],
    current_tier: str,
    *,
    current_decision: str,
    decision_source: str,
    recommended_next_action: str,
    owner_decision_needed: bool,
    required_next_evidence: str,
    do_not_promote_reason: str,
    promotion_scope: str = "not_applicable",
    promotion_target: str = "not_applicable",
    ledger_reason: str = "",
    next_checkpoint: str = "",
) -> dict[str, Any]:
    return {
        "strategy_group_id": str(registry_row.get("strategy_group_id") or ""),
        "owner_label": str(registry_row.get("owner_label") or ""),
        "current_tier": current_tier,
        "registry_trial_eligible": bool(registry_row.get("trial_eligible")),
        "actionable_now": False,
        "current_decision": current_decision,
        "promotion_scope": promotion_scope,
        "promotion_target": promotion_target,
        "decision_source": decision_source,
        "recommended_next_action": recommended_next_action,
        "owner_decision_needed": owner_decision_needed,
        "required_next_evidence": required_next_evidence,
        "do_not_promote_reason": do_not_promote_reason,
        "strategy_uncertainty_is_execution_blocker": False,
        "owner_scoped_risk_acceptance_path": (
            "may support trial eligibility or tier review, but cannot set "
            "runtime actionability to true or bypass runtime safety gates"
        ),
        "authority_boundary": AUTHORITY_BOUNDARY,
        "ledger_reason": ledger_reason,
        "next_checkpoint": next_checkpoint or required_next_evidence,
        "safety_invariants": {
            "real_order_authority": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
    }


def _display_decision(decision: str, promotion_target: str) -> str:
    if decision == "promote" and promotion_target == "promotion_evidence_review_only":
        return "promote_review_only"
    return decision


def _display_promotion_scope(ledger_row: dict[str, Any]) -> str:
    promotion_target = str(ledger_row.get("promotion_target") or "")
    if promotion_target == "promotion_evidence_review_only":
        return "review_only"
    return str(ledger_row.get("promotion_scope") or "not_applicable")


def _ledger_rows_and_status(
    decision_ledger: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], str]:
    if decision_ledger is None:
        return [], "missing_generated_view"
    rows = _dict_rows(decision_ledger.get("ledger_rows"))
    if not rows:
        return [], "present_empty"
    return rows, str(decision_ledger.get("status") or "present")


def _decision_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        action = str(row.get("recommended_next_action") or "unknown")
        counts[action] = counts.get(action, 0) + 1
    return dict(sorted(counts.items()))


def _summary_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| StrategyGroup | 当前层级 | 可试运行 | 当前判断 | 推荐动作 | Owner 需决策 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("current_tier"),
                str(row.get("registry_trial_eligible")).lower(),
                row.get("current_decision"),
                row.get("recommended_next_action"),
                str(row.get("owner_decision_needed")).lower(),
            )
        )
    return "\n".join(lines)


def _row_section(row: dict[str, Any]) -> list[str]:
    return [
        f"### `{row.get('strategy_group_id')}` {row.get('owner_label')}",
        "",
        f"- 当前层级: `{row.get('current_tier')}`",
        f"- 当前判断: `{row.get('current_decision')}`",
        f"- 晋级范围: `{row.get('promotion_scope')}`",
        f"- 晋级目标: `{row.get('promotion_target')}`",
        f"- 推荐动作: `{row.get('recommended_next_action')}`",
        f"- 判断来源: `{row.get('decision_source')}`",
        f"- Owner 需决策: `{str(row.get('owner_decision_needed')).lower()}`",
        f"- 下一证据: {row.get('required_next_evidence')}",
        f"- 暂不晋级原因: {row.get('do_not_promote_reason')}",
        "",
    ]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return payload


def _write_files(packet: dict[str, Any], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(build_owner_markdown(packet), encoding="utf-8")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-json", default=str(DEFAULT_REGISTRY_JSON))
    parser.add_argument("--tier-policy-json", default=str(DEFAULT_TIER_POLICY_JSON))
    parser.add_argument("--decision-ledger-json", default=str(DEFAULT_DECISION_LEDGER_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_OUTPUT_MD))
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate existing output files instead of writing them.",
    )
    args = parser.parse_args(argv)

    registry_path = Path(args.registry_json).expanduser()
    tier_policy_path = Path(args.tier_policy_json).expanduser()
    decision_ledger_path = Path(args.decision_ledger_json).expanduser()
    output_json = Path(args.output_json).expanduser()
    output_md = Path(args.output_md).expanduser()

    registry, tier_policy, decision_ledger = load_inputs(
        registry_path, tier_policy_path, decision_ledger_path
    )
    expected = build_tier_review_packet(registry, tier_policy, decision_ledger)
    errors = validate_inputs(registry, tier_policy)
    errors.extend(validate_packet(expected))

    if args.check:
        if not output_json.exists():
            errors.append(f"missing_json:{output_json}")
        if not output_md.exists():
            errors.append(f"missing_markdown:{output_md}")
        if output_json.exists():
            existing = _load_json(output_json)
            if existing != expected:
                errors.append("json_output_drift")
            errors.extend(validate_packet(existing))
        if output_md.exists():
            markdown = output_md.read_text(encoding="utf-8")
            for group in EXPECTED_GROUPS:
                if group not in markdown:
                    errors.append(f"markdown_missing_group:{group}")
            if "actionable_now" not in markdown:
                errors.append("markdown_missing_actionable_boundary")
    else:
        _write_files(expected, output_json, output_md)

    report = {
        "status": "passed" if not errors else "failed",
        "scope": "strategygroup_tier_review_current",
        "json_path": str(output_json),
        "markdown_path": str(output_md),
        "row_count": len(expected["rows"]),
        "ledger_status": expected["ledger_status"],
        "decision_counts": expected["decision_counts"],
        "errors": errors,
        "safety_invariants": expected["safety_invariants"],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
