"""Risk/Capital resolution for BRC admission constraints.

This adapter resolves admission-time trial constraints only. It does not install
runtime constraints, create campaigns, place orders, or authorize live trading.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from src.domain.brc_admission import (
    AdmissionEvidence,
    AdmissionExecutionMode,
    AdmissionRequest,
    AdmissionRuleConfig,
    OwnerMarketRegimeInput,
    RiskCapitalAdapterResult,
    StrategyFamilyVersion,
    TrialConstraintSnapshotStatus,
    TrialEnv,
    TrialStage,
)


_DEFAULT_TESTNET_MAX_NOTIONAL = Decimal("25")
_DEFAULT_TESTNET_MAX_LOSS_BUDGET = Decimal("5")
_DEFAULT_TESTNET_MAX_LEVERAGE = 1
_DEFAULT_MAX_ATTEMPTS = 1


class BrcAdmissionRiskCapitalAdapter:
    """Minimal Phase 2 resolver for installable admission constraints.

    The adapter can emit conservative installable constraints for testnet
    development validation. Live funded validation requires both healthy account
    facts and explicit risk/capital resolution data; otherwise the result stays
    pending.
    """

    async def resolve_constraints(
        self,
        *,
        request: AdmissionRequest,
        strategy_family_version: StrategyFamilyVersion,
        admission_evidence: AdmissionEvidence,
        owner_regime_input: OwnerMarketRegimeInput,
        rule_config: AdmissionRuleConfig,
    ) -> RiskCapitalAdapterResult:
        account = _account_facts_summary(request.account_facts_snapshot_json)
        execution_mode = _execution_mode(request)
        allowed_symbols = _allowed_symbols(strategy_family_version)
        allowed_timeframes = list(strategy_family_version.supported_timeframes)
        blockers = _account_blockers(account)
        warnings: list[str] = []
        limitations: list[str] = []

        if not allowed_symbols:
            warnings.append("strategy family version does not declare allowed symbols")
            limitations.append("no symbols can be installed until strategy family version is pinned")
        if not allowed_timeframes:
            limitations.append("allowed_timeframes not declared by strategy family version")
        if not admission_evidence.mandatory_complete:
            warnings.append("mandatory evidence incomplete")

        base = {
            "source": "unavailable",
            "risk_profile": request.requested_risk_profile,
            "execution_mode": execution_mode.value,
            "trial_env": request.trial_env.value,
            "trial_stage": request.trial_stage.value,
            "account_facts_snapshot_ref": request.account_facts_snapshot_ref,
            "account_source": account["source"],
            "truth_level": account["truth_level"],
            "reconciliation_status": account["reconciliation_status"],
            "max_loss_budget": None,
            "max_notional": None,
            "max_leverage": None,
            "max_attempts": None,
            "allowed_symbols": allowed_symbols,
            "allowed_timeframes": allowed_timeframes,
            "review_requirements": _review_requirements(request),
            "cooldowns": _cooldowns(rule_config),
            "blockers": list(blockers),
            "warnings": list(warnings),
            "limitations": list(limitations),
        }

        if request.trial_env == TrialEnv.LIVE and request.trial_stage == TrialStage.FUNDED_VALIDATION:
            return self._resolve_live_funded(request=request, base=base, account=account)

        return self._resolve_non_live(
            request=request,
            base=base,
            account=account,
            rule_config=rule_config,
        )

    def _resolve_non_live(
        self,
        *,
        request: AdmissionRequest,
        base: dict[str, Any],
        account: dict[str, Any],
        rule_config: AdmissionRuleConfig,
    ) -> RiskCapitalAdapterResult:
        constraints = dict(base)
        policy = _policy_from_rule_config(rule_config) or {}

        constraints["source"] = "non_live_policy_defaults"
        constraints["max_loss_budget"] = _money_string(
            policy.get("max_loss_budget") or _DEFAULT_TESTNET_MAX_LOSS_BUDGET
        )
        constraints["max_notional"] = _money_string(
            policy.get("max_notional") or _DEFAULT_TESTNET_MAX_NOTIONAL
        )
        constraints["max_leverage"] = int(policy.get("max_leverage") or _DEFAULT_TESTNET_MAX_LEVERAGE)
        constraints["max_attempts"] = int(policy.get("max_attempts") or _DEFAULT_MAX_ATTEMPTS)
        constraints["limitations"].append(
            "non-live policy defaults are for non-live admission only and are not live risk capital"
        )
        if account["source"] == "unavailable":
            constraints["warnings"].append(
                "account facts unavailable; accepted only for non-live development semantics"
            )

        return RiskCapitalAdapterResult(
            status=TrialConstraintSnapshotStatus.INSTALLABLE,
            risk_profile=request.requested_risk_profile,
            risk_policy_version=str(
                policy.get("risk_policy_version")
                or "brc-admission-non-live-defaults-v1"
            ),
            constraints_json=constraints,
            risk_policy_snapshot_json={
                "source": "non_live_policy_defaults",
                "risk_policy_version": str(
                    policy.get("risk_policy_version")
                    or "brc-admission-non-live-defaults-v1"
                ),
                "live_usable": False,
            },
            adapter_result_json={
                "adapter": "BrcAdmissionRiskCapitalAdapter",
                "resolution": "installable_non_live_policy_defaults",
                "sizing_computed": False,
                "live_usable": False,
            },
        )

    def _resolve_live_funded(
        self,
        *,
        request: AdmissionRequest,
        base: dict[str, Any],
        account: dict[str, Any],
    ) -> RiskCapitalAdapterResult:
        constraints = dict(base)
        constraints["source"] = "unavailable"
        if not request.account_facts_snapshot_ref:
            constraints["blockers"].append("account facts snapshot ref unavailable")
        if account["source"] not in {"exchange_live", "mixed"}:
            constraints["blockers"].append("live funded validation requires exchange live account facts")
        if account["truth_level"] not in {"exchange_read", "reconciled"}:
            constraints["blockers"].append("live funded validation requires exchange_read or reconciled truth")

        if constraints["blockers"]:
            return _pending_result(
                request=request,
                constraints=constraints,
                reason="live funded validation account facts are not clean",
            )

        resolution = _risk_capital_resolution(request.account_facts_snapshot_json)
        if resolution is None:
            constraints["limitations"].append(
                "live funded validation requires explicit risk capital resolution"
            )
            return _pending_result(
                request=request,
                constraints=constraints,
                reason="risk capital module has not returned concrete live constraints",
            )

        required = ["max_loss_budget", "max_notional", "max_leverage", "max_attempts"]
        missing = [key for key in required if resolution.get(key) in (None, "")]
        if missing:
            constraints["blockers"].append(
                f"risk capital resolution missing required fields: {', '.join(missing)}"
            )
            return _pending_result(
                request=request,
                constraints=constraints,
                reason="risk capital resolution incomplete",
            )

        constraints["source"] = "risk_capital_adapter"
        constraints["max_loss_budget"] = _money_string(resolution["max_loss_budget"])
        constraints["max_notional"] = _money_string(resolution["max_notional"])
        constraints["max_leverage"] = int(resolution["max_leverage"])
        constraints["max_attempts"] = int(resolution["max_attempts"])
        constraints["warnings"].extend(list(resolution.get("warnings") or []))
        constraints["limitations"].extend(list(resolution.get("limitations") or []))

        return RiskCapitalAdapterResult(
            status=TrialConstraintSnapshotStatus.INSTALLABLE,
            risk_profile=request.requested_risk_profile,
            risk_policy_version=str(resolution.get("risk_policy_version") or "unknown"),
            constraints_json=constraints,
            risk_policy_snapshot_json={
                "source": "risk_capital_adapter",
                "risk_policy_version": str(resolution.get("risk_policy_version") or "unknown"),
                "live_usable": True,
                "account_facts_snapshot_ref": request.account_facts_snapshot_ref,
            },
            adapter_result_json={
                "adapter": "BrcAdmissionRiskCapitalAdapter",
                "resolution": "installable_live_funded",
                "sizing_computed": True,
                "live_usable": True,
            },
        )


def _pending_result(
    *,
    request: AdmissionRequest,
    constraints: dict[str, Any],
    reason: str,
) -> RiskCapitalAdapterResult:
    return RiskCapitalAdapterResult(
        status=TrialConstraintSnapshotStatus.PENDING_RISK_CAPITAL_RESOLUTION,
        risk_profile=request.requested_risk_profile,
        constraints_json=constraints,
        risk_policy_snapshot_json={
            "source": constraints.get("source") or "unavailable",
            "live_usable": False,
        },
        adapter_result_json={
            "adapter": "BrcAdmissionRiskCapitalAdapter",
            "resolution": "pending",
            "reason": reason,
            "sizing_computed": False,
            "live_usable": False,
        },
    )


def _execution_mode(request: AdmissionRequest) -> AdmissionExecutionMode:
    if request.requested_execution_mode is not None:
        return request.requested_execution_mode
    if request.trial_stage == TrialStage.FUNDED_VALIDATION:
        return AdmissionExecutionMode.AUTO_WITHIN_BUDGET
    return AdmissionExecutionMode.OBSERVE_ONLY


def _allowed_symbols(version: StrategyFamilyVersion) -> list[str]:
    return [symbol for symbol in version.supported_symbols if symbol]


def _review_requirements(request: AdmissionRequest) -> dict[str, Any]:
    return {
        "owner_risk_acceptance_required": request.trial_stage == TrialStage.FUNDED_VALIDATION,
        "post_trial_review_required": True,
        "operation_preflight_required": True,
    }


def _cooldowns(rule_config: AdmissionRuleConfig) -> dict[str, Any]:
    details = rule_config.rule_details_json
    if isinstance(details.get("cooldowns"), dict):
        return dict(details["cooldowns"])
    return {"after_trial_minutes": 0, "after_loss_review_required": True}


def _policy_from_rule_config(rule_config: AdmissionRuleConfig) -> Optional[dict[str, Any]]:
    details = rule_config.rule_details_json
    policy = details.get("non_live_policy_defaults")
    return dict(policy) if isinstance(policy, dict) else None


def _risk_capital_resolution(account_facts: dict[str, Any]) -> Optional[dict[str, Any]]:
    for key in ("risk_capital_resolution", "risk_capital_policy", "trial_risk_constraints"):
        value = account_facts.get(key)
        if isinstance(value, dict):
            return dict(value)
    return None


def _account_facts_summary(account_facts: dict[str, Any]) -> dict[str, Any]:
    source = str(account_facts.get("source") or "unavailable").lower()
    truth_level = str(account_facts.get("truth_level") or "unavailable").lower()
    reconciliation = account_facts.get("reconciliation_status")
    reconciliation_status = (
        str(reconciliation.get("status") or "unknown").lower()
        if isinstance(reconciliation, dict)
        else str(account_facts.get("reconciliation_status_value") or "unknown").lower()
    )
    unknown_counts = account_facts.get("unknown_unmanaged_counts")
    return {
        "source": source,
        "truth_level": truth_level,
        "reconciliation_status": reconciliation_status,
        "unknown_unmanaged_counts": dict(unknown_counts) if isinstance(unknown_counts, dict) else {},
    }


def _account_blockers(account: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if account["source"] == "unavailable" or account["truth_level"] == "unavailable":
        blockers.append("account facts unavailable")
    if account["reconciliation_status"] == "mismatch":
        blockers.append("account reconciliation mismatch")
    unknown_counts = account["unknown_unmanaged_counts"]
    if int(unknown_counts.get("orders") or 0) > 0:
        blockers.append("unknown unmanaged exposure detected")
    if int(unknown_counts.get("positions") or 0) > 0:
        blockers.append("unknown unmanaged exposure detected")
    return blockers


def _money_string(value: Any) -> str:
    try:
        decimal_value = Decimal(str(value)).quantize(Decimal("0.00000001")).normalize()
        text = format(decimal_value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid monetary constraint value: {value}") from exc
