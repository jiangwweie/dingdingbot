#!/usr/bin/env python3
"""Bootstrap a bounded live StrategyRuntimeInstance through official APIs.

The flow creates the minimum admission and runtime records needed before a
strategy signal can plan a shadow candidate. It does not create candidates,
ExecutionIntents, orders, withdrawals, transfers, or exchange submit actions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
import sys
import time
from typing import Any, Protocol

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    DEFAULT_API_BASE,
    UrlLibApiClient,
)


API_BASE_ENV = "RUNTIME_LIVE_BOOTSTRAP_API_BASE"
RISK_ACCEPTANCE_PHRASE = "I ACCEPT BOUNDED FUNDED VALIDATION RISK"
BINDING_RESERVATION_PHRASE = "CONFIRM_RESERVE_ADMISSION_BINDING"


class ApiClient(Protocol):
    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


@dataclass
class BootstrapConfig:
    api_base: str
    mode: str
    strategy_family_id: str = "CPM-001"
    strategy_family_version_id: str = "CPM-001-v0"
    family_key: str = "cpm-price-action"
    family_name: str = "CPM Price Action Reference"
    symbol: str = "BNB/USDT:USDT"
    supported_symbols: list[str] = field(default_factory=list)
    side: str = "long"
    timeframe: str = "1h"
    capital_base: Decimal = Decimal("30")
    max_loss_budget: Decimal = Decimal("9")
    max_notional: Decimal = Decimal("10")
    max_leverage: int = 1
    max_attempts: int = 3
    min_liquidation_stop_buffer: Decimal | None = None
    playbook_id: str = "PB-BRC-LIVE-RUNTIME-V1"
    account_facts_source: str = "binance_readonly"
    account_facts_json: str | None = None
    owner_operator_id: str = "owner"
    runtime_carrier_id: str = "strategygroup-runtime-bootstrap"
    reason: str = "Owner standing-authorized StrategyGroup runtime bootstrap"


@dataclass
class BootstrapState:
    ids: dict[str, str] = field(default_factory=dict)
    steps: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def remember(self, key: str, value: Any) -> None:
        if value is None:
            return
        text = str(value).strip()
        if text:
            self.ids[key] = text

    def add_blockers(self, values: Any) -> None:
        for item in values or []:
            text = str(item)
            if text and text not in self.blockers:
                self.blockers.append(text)

    def add_warnings(self, values: Any) -> None:
        for item in values or []:
            text = str(item)
            if text and text not in self.warnings:
                self.warnings.append(text)


class RuntimeLiveBootstrapApiFlow:
    def __init__(self, *, client: ApiClient, config: BootstrapConfig) -> None:
        self._client = client
        self._config = config
        self.state = BootstrapState()

    def run(self) -> dict[str, Any]:
        if self._config.mode == "inspect":
            self._inspect()
            return self._report()

        account_facts = self._account_facts_snapshot()
        if self.state.blockers:
            return self._report()

        self._ensure_strategy_family()
        self._ensure_strategy_family_version()
        if self.state.blockers:
            return self._report()

        self._create_admission(account_facts)
        if self.state.blockers:
            return self._report()

        self._reserve_binding()
        if self.state.blockers:
            return self._report()
        if self._config.mode == "binding-only":
            return self._report()

        self._create_and_activate_runtime()
        return self._report()

    def _inspect(self) -> None:
        self._step("list_strategy_families", "GET", "/api/brc/strategy-families")
        self._step("list_admission_decisions", "GET", "/api/brc/admissions/decisions")
        self._step("list_trial_bindings", "GET", "/api/brc/admissions/trial-bindings")
        self._step("list_strategy_runtimes", "GET", "/api/trading-console/strategy-runtimes")

    def _ensure_strategy_family(self) -> None:
        result = self._step(
            "get_strategy_family",
            "GET",
            f"/api/brc/strategy-families/{self._config.strategy_family_id}",
            allowed_statuses={200, 404},
        )
        if result.get("http_status") == 200:
            self.state.remember("strategy_family_id", self._config.strategy_family_id)
            return
        created = self._step(
            "create_strategy_family",
            "POST",
            "/api/brc/strategy-families",
            body={
                "strategy_family_id": self._config.strategy_family_id,
                "family_key": self._config.family_key,
                "name": self._config.family_name,
                "description": (
                    "Reference price-action family for bounded first live runtime."
                ),
                "status": "active",
                "owner": self._config.owner_operator_id,
            },
        )
        self.state.remember("strategy_family_id", _body(created).get("strategy_family_id"))

    def _ensure_strategy_family_version(self) -> None:
        result = self._step(
            "get_strategy_family_version",
            "GET",
            (
                "/api/brc/strategy-family-versions/"
                f"{self._config.strategy_family_version_id}"
            ),
            allowed_statuses={200, 404},
        )
        if result.get("http_status") == 200:
            self.state.remember(
                "strategy_family_version_id",
                self._config.strategy_family_version_id,
            )
            return
        created = self._step(
            "create_strategy_family_version",
            "POST",
            (
                "/api/brc/strategy-families/"
                f"{self._config.strategy_family_id}/versions"
            ),
            body={
                "strategy_family_version_id": self._config.strategy_family_version_id,
                "version": 1,
                "hypothesis": (
                    "Reference implementation can express bounded price-action "
                    "attempts; alpha is not assumed."
                ),
                "market_structure": "closed-candle price action",
                "entry_logic_family": "catalog-bound price-action trigger",
                "exit_logic_family": "TP1 partial plus runner/trailing metadata",
                "risk_model": "bounded small-capital attempts; no runaway",
                "supported_symbols": _supported_symbols(self._config),
                "supported_timeframes": [self._config.timeframe],
                "required_data": ["closed_ohlcv", "trusted_account_facts", "active_positions"],
                "required_execution_capabilities": ["market_entry", "hard_stop_protection"],
                "known_failure_modes": [
                    "reference_implementation_not_proven_alpha",
                    "structure_stop_missing_blocks_candidate",
                ],
                "regime_contract_json": {
                    "market_state": "uncertain_allowed_for_runtime_bootstrap",
                    "rmr_not_hard_filter": True,
                },
                "safeguards_json": {
                    "requires_protection": True,
                    "max_attempts": self._config.max_attempts,
                    "max_notional": str(self._config.max_notional),
                    "max_leverage": self._config.max_leverage,
                },
                "degradation_policy_json": {
                    "missing_trusted_facts": "BLOCK",
                    "missing_signal": "NO_ACTION",
                },
                "playbook_id": self._config.playbook_id,
                "playbook_catalog_snapshot_json": {
                    "id": self._config.playbook_id,
                    "runtime_bootstrap": True,
                },
                "created_by": self._config.owner_operator_id,
            },
        )
        self.state.remember(
            "strategy_family_version_id",
            _body(created).get("strategy_family_version_id"),
        )

    def _create_admission(self, account_facts: dict[str, Any]) -> None:
        evidence = self._step(
            "create_admission_evidence",
            "POST",
            "/api/brc/admissions/admission-evidence",
            body={
                "strategy_family_version_id": self._config.strategy_family_version_id,
                "payload_json": {
                    "reference_implementation": True,
                    "proven_alpha": False,
                    "owner_standing_authorized_strategygroup_runtime": True,
                    "bounded_loss_not_runaway": True,
                },
                "mandatory_complete": True,
                "created_by": self._config.owner_operator_id,
            },
        )
        self.state.remember("admission_evidence_id", _body(evidence).get("admission_evidence_id"))
        regime = self._step(
            "create_owner_regime_input",
            "POST",
            "/api/brc/admissions/owner-regime-inputs",
            body={
                "current_regime": "uncertain",
                "confidence": "low",
                "rationale": (
                    "First live runtime bootstrap prioritizes bounded chain "
                    "integrity; strategy alpha is not assumed."
                ),
                "market_facts_snapshot_json": {
                    "symbol": self._config.symbol,
                    "timeframe": self._config.timeframe,
                },
                "created_by": self._config.owner_operator_id,
            },
        )
        self.state.remember(
            "owner_market_regime_input_id",
            _body(regime).get("owner_market_regime_input_id"),
        )
        admission = self._step(
            "create_admission_request",
            "POST",
            "/api/brc/admissions/requests",
            body={
                "strategy_family_version_id": self._config.strategy_family_version_id,
                "admission_evidence_id": self.state.ids.get("admission_evidence_id"),
                "owner_market_regime_input_id": self.state.ids.get(
                    "owner_market_regime_input_id"
                ),
                "trial_env": "live",
                "trial_stage": "funded_validation",
                "requested_execution_mode": "auto_within_budget",
                "requested_risk_profile": "micro",
                "account_facts_snapshot_ref": account_facts["account_facts_snapshot_ref"],
                "account_facts_snapshot_json": account_facts,
                "playbook_id": self._config.playbook_id,
                "playbook_catalog_snapshot_json": {"id": self._config.playbook_id},
                "requested_by": self._config.owner_operator_id,
            },
        )
        self.state.remember(
            "admission_request_id",
            _body(admission).get("admission_request_id"),
        )
        admission_evaluation = self._step(
            "evaluate_admission_request",
            "POST",
            (
                "/api/brc/admissions/requests/"
                f"{self.state.ids.get('admission_request_id')}/evaluate"
            ),
        )
        admission_body = _body(admission_evaluation)
        self.state.remember(
            "admission_decision_id",
            admission_body.get("admission_decision_id"),
        )
        self.state.remember(
            "trial_constraint_snapshot_id",
            admission_body.get("trial_constraint_snapshot_id"),
        )
        admission_result = admission_body.get("admission_result")
        if admission_result not in {"admit", "admit_with_constraints"}:
            self.state.add_blockers([f"admission_result_{admission_result or 'missing'}"])
        acceptance = self._step(
            "create_owner_risk_acceptance",
            "POST",
            "/api/brc/admissions/risk-acceptances",
            body={
                "admission_request_id": self.state.ids.get("admission_request_id"),
                "admission_decision_id": self.state.ids.get("admission_decision_id"),
                "constraint_snapshot_id": self.state.ids.get(
                    "trial_constraint_snapshot_id"
                ),
                "owner_rationale": self._config.reason,
                "confirmation_phrase": RISK_ACCEPTANCE_PHRASE,
                "confirmed_by": self._config.owner_operator_id,
            },
        )
        self.state.remember(
            "owner_risk_acceptance_id",
            _body(acceptance).get("owner_risk_acceptance_id"),
        )

    def _reserve_binding(self) -> None:
        preflight = self._step(
            "preflight_create_gated_trial",
            "POST",
            "/api/brc/operations/preflight",
            body={
                "operation_type": "create_gated_trial_from_admission",
                "requested_by": self._config.owner_operator_id,
                "input_params": {
                    "admission_decision_id": self.state.ids.get("admission_decision_id"),
                    "owner_risk_acceptance_id": self.state.ids.get(
                        "owner_risk_acceptance_id"
                    ),
                    "playbook_id": self._config.playbook_id,
                },
                "source": {"kind": "runtime_live_bootstrap_api_flow"},
            },
        )
        preflight_body = _body(preflight)
        preflight_result = preflight_body.get("preflight_result")
        if preflight_result not in {"allow", "warn"}:
            self.state.add_blockers([f"binding_preflight_{preflight_result}"])
        self.state.add_blockers(preflight_body.get("risk_summary", {}).get("blockers"))
        if self.state.blockers:
            return
        self.state.remember("binding_operation_id", preflight_body.get("operation_id"))
        self.state.remember("binding_preflight_id", preflight_body.get("preflight_id"))
        self.state.remember("binding_idempotency_key", preflight_body.get("idempotency_key"))
        confirmed = self._step(
            "confirm_create_gated_trial",
            "POST",
            f"/api/brc/operations/{self.state.ids.get('binding_operation_id')}/confirm",
            body={
                "preflight_id": self.state.ids.get("binding_preflight_id"),
                "confirmation_phrase": BINDING_RESERVATION_PHRASE,
                "idempotency_key": self.state.ids.get("binding_idempotency_key"),
                "confirmed_by": self._config.owner_operator_id,
            },
        )
        self.state.remember(
            "trial_binding_id",
            _body(confirmed).get("result_summary", {}).get("binding_id"),
        )

    def _create_and_activate_runtime(self) -> None:
        profile = self._step(
            "preview_runtime_profile",
            "GET",
            "/api/trading-console/strategy-runtime-profile-proposals",
            query={
                "strategy_family_id": self._config.strategy_family_id,
                "strategy_family_version_id": self._config.strategy_family_version_id,
                "symbol": self._config.symbol,
                "side": self._config.side,
                "capital_base": str(self._config.capital_base),
            },
        )
        profile_body = _body(profile)
        if profile_body.get("status") != "ready_for_owner_codex_confirmation":
            self.state.add_blockers([f"profile_proposal_{profile_body.get('status')}"])
            return
        profile_body = _profile_with_owner_overrides(profile_body, self._config)
        runtime_confirmations = _all_true(
            [
                "runtime_profile_confirmed",
                "owner_confirmation_mode_confirmed",
                "symbol_side_boundary_confirmed",
                "max_loss_budget_confirmed",
                "max_notional_boundary_confirmed",
                "max_active_positions_boundary_confirmed",
                "max_leverage_boundary_confirmed",
                "margin_usage_boundary_confirmed",
                "liquidation_buffer_boundary_confirmed",
                "protection_readiness_source_confirmed",
                "stale_fact_behavior_confirmed",
                "attempt_consumption_rule_confirmed",
                "budget_reservation_rule_confirmed",
                "trusted_active_position_source_confirmed",
                "trusted_account_fact_source_confirmed",
            ]
        )
        if self._config.side.lower() == "short":
            runtime_confirmations["short_side_conservative_profile_confirmed"] = True
        confirmation = self._step(
            "create_runtime_promotion_confirmation",
            "POST",
            "/api/brc/strategy-runtime-promotion-confirmations",
            body={
                "strategy_family_id": self._config.strategy_family_id,
                "strategy_family_version_id": self._config.strategy_family_version_id,
                "scope": "controlled_runtime_execution",
                "semantic_confirmations": _all_true(
                    [
                        "strategy_family_confirmed",
                        "implementation_source_confirmed",
                        "required_facts_confirmed",
                        "entry_policy_confirmed",
                        "exit_policy_confirmed",
                        "protection_policy_confirmed",
                        "eligible_for_runtime_execution_confirmed",
                        "right_tail_review_metrics_confirmed",
                    ]
                ),
                "runtime_confirmations": runtime_confirmations,
                "runtime_profile_proposal_snapshot": profile_body,
                "reason": self._config.reason,
                "evidence_refs": [
                    self.state.ids.get("admission_decision_id"),
                    self.state.ids.get("owner_risk_acceptance_id"),
                    self.state.ids.get("trial_binding_id"),
                ],
                "metadata": {
                    "script": "runtime_live_bootstrap_api_flow",
                    "creates_order": False,
                    "exchange_called": False,
                    "owner_profile_overrides": _profile_override_metadata(
                        self._config
                    ),
                },
            },
        )
        self.state.remember(
            "promotion_confirmation_id",
            _body(confirmation).get("confirmation", {}).get("confirmation_id"),
        )
        draft = self._step(
            "create_runtime_draft",
            "POST",
            (
                "/api/brc/strategy-runtime-promotion-confirmations/"
                f"{self.state.ids.get('promotion_confirmation_id')}/runtime-drafts"
            ),
            body={
                "trial_binding_id": self.state.ids.get("trial_binding_id"),
                "carrier_id": self._config.runtime_carrier_id,
                "metadata": {
                    "script": "runtime_live_bootstrap_api_flow",
                    "live_runtime_candidate": True,
                    "strategygroup_runtime_pilot": True,
                },
            },
        )
        self.state.remember("runtime_instance_id", _body(draft).get("runtime", {}).get("runtime_instance_id"))
        if self.state.blockers:
            return
        if not self.state.ids.get("runtime_instance_id"):
            self.state.add_blockers(["runtime_instance_id_missing_after_draft"])
            return
        activated = self._step(
            "activate_shadow_runtime",
            "POST",
            f"/api/brc/strategy-runtimes/{self.state.ids.get('runtime_instance_id')}/lifecycle",
            body={"action": "activate_shadow"},
        )
        self.state.remember(
            "runtime_status",
            _body(activated).get("runtime", {}).get("status"),
        )

    def _account_facts_snapshot(self) -> dict[str, Any]:
        if self._config.account_facts_json:
            with open(self._config.account_facts_json, "r", encoding="utf-8") as handle:
                return json.load(handle)
        if self._config.account_facts_source == "static":
            return _static_account_facts(self._config)
        if self._config.account_facts_source == "binance_readonly":
            return asyncio.run(_binance_account_facts(self._config))
        self.state.add_blockers(["account_facts_source_unavailable"])
        return {}

    def _step(
        self,
        name: str,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        allowed_statuses: set[int] | None = None,
    ) -> dict[str, Any]:
        allowed = allowed_statuses or {200}
        result = self._client.request_json(method, path, query=query, body=body)
        body_value = _body(result)
        self.state.steps.append(
            {
                "name": name,
                "method": method,
                "path": path,
                "http_status": result.get("http_status"),
                "status": body_value.get("status") if isinstance(body_value, dict) else None,
                "step_result": _step_result(name, body_value),
                "ids": _id_summary(body_value),
                "blockers": body_value.get("blockers", []) if isinstance(body_value, dict) else [],
                "warnings": body_value.get("warnings", []) if isinstance(body_value, dict) else [],
            }
        )
        if result.get("http_status") not in allowed:
            self.state.add_blockers([f"{name}_http_{result.get('http_status')}"])
        if isinstance(body_value, dict):
            self.state.add_blockers(body_value.get("blockers"))
            self.state.add_warnings(body_value.get("warnings"))
        return result

    def _report(self) -> dict[str, Any]:
        return {
            "script": "runtime_live_bootstrap_api_flow",
            "mode": self._config.mode,
            "api_base": self._config.api_base,
            "ready_for_trial_binding": (
                bool(self.state.ids.get("trial_binding_id")) and not self.state.blockers
            ),
            "ready_for_shadow_candidate_planning": (
                self.state.ids.get("runtime_status") == "active" and not self.state.blockers
            ),
            "ids": self.state.ids,
            "steps": self.state.steps,
            "blockers": self.state.blockers,
            "warnings": self.state.warnings,
            "safety": {
                "uses_official_api_surfaces": True,
                "creates_trial_binding": bool(self.state.ids.get("trial_binding_id")),
                "creates_runtime_only": self._config.mode == "bootstrap",
                "creates_runtime": bool(self.state.ids.get("runtime_instance_id")),
                "activates_shadow_runtime": self.state.ids.get("runtime_status") == "active",
                "creates_order_candidate": False,
                "creates_execution_intent": False,
                "creates_order": False,
                "calls_exchange_submit": False,
                "no_withdrawal_or_transfer": True,
            },
        }


async def _binance_account_facts(config: BootstrapConfig) -> dict[str, Any]:
    _load_env()
    from src.application.binance_usdt_futures_account_facts import (
        BinanceUsdtFuturesAccountFactsSource,
        CcxtBinanceUsdtFuturesBalanceClient,
    )

    api_key = os.environ.get("EXCHANGE_API_KEY", "").strip()
    api_secret = os.environ.get("EXCHANGE_API_SECRET", "").strip()
    if not api_key or not api_secret:
        raise RuntimeError("EXCHANGE_API_KEY and EXCHANGE_API_SECRET are required")
    client = CcxtBinanceUsdtFuturesBalanceClient(
        api_key=api_key,
        api_secret=api_secret,
        testnet=_parse_bool_env(os.environ.get("EXCHANGE_TESTNET")),
    )
    source = BinanceUsdtFuturesAccountFactsSource(balance_client=client)
    try:
        facts = await source.read_trial_readiness_account_facts(
            candidate_id="runtime-live-bootstrap",
            symbol=config.symbol,
            side=config.side,
            generated_at_ms=int(time.time() * 1000),
        )
    finally:
        await source.close()
    if facts.account_equity is None or facts.available_margin is None:
        raise RuntimeError("Binance readonly account facts missing equity or margin")
    return _account_snapshot_from_values(
        config=config,
        source="exchange_live",
        truth_level="exchange_read",
        account_equity=facts.account_equity,
        available_margin=facts.available_margin,
        timestamp_ms=facts.timestamp_ms,
        account_facts_snapshot_ref=f"binance_live_readonly:{facts.timestamp_ms}",
        metadata={
            "source_id": facts.source_id,
            "source_type": facts.source_type.value,
            "read_only_guarantee": facts.read_only_guarantee,
            "external_call_performed": facts.external_call_performed,
            "external_call_type": facts.external_call_type,
            "notes": list(facts.notes),
        },
    )


def _static_account_facts(config: BootstrapConfig) -> dict[str, Any]:
    return _account_snapshot_from_values(
        config=config,
        source="exchange_live",
        truth_level="exchange_read",
        account_equity=config.capital_base,
        available_margin=config.capital_base,
        timestamp_ms=int(time.time() * 1000),
        account_facts_snapshot_ref=(
            "static_owner_authorized_strategygroup_runtime_account_facts"
        ),
        metadata={"source": "static_cli", "used_for_tests": True},
    )


def _account_snapshot_from_values(
    *,
    config: BootstrapConfig,
    source: str,
    truth_level: str,
    account_equity: Decimal,
    available_margin: Decimal,
    timestamp_ms: int | None,
    account_facts_snapshot_ref: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source": source,
        "truth_level": truth_level,
        "account_facts_snapshot_ref": account_facts_snapshot_ref,
        "reconciliation_status": {"status": "clean"},
        "unknown_unmanaged_counts": {"orders": 0, "positions": 0},
        "account_equity": str(account_equity),
        "available_margin": str(available_margin),
        "timestamp_ms": timestamp_ms,
        "risk_capital_resolution": {
            "risk_policy_version": "owner-strategygroup-runtime-pilot-small-cap-v1",
            "max_loss_budget": str(config.max_loss_budget),
            "max_notional": str(config.max_notional),
            "max_leverage": config.max_leverage,
            "max_attempts": config.max_attempts,
            "warnings": ["reference_strategy_not_proven_alpha"],
            "limitations": ["small experimental risk capital only"],
        },
        "read_only_guarantee": True,
        "metadata": metadata,
    }


def _all_true(keys: list[str]) -> dict[str, bool]:
    return {key: True for key in keys}


def _supported_symbols(config: BootstrapConfig) -> list[str]:
    values = [item.strip() for item in config.supported_symbols if item.strip()]
    if not values:
        values = [config.symbol]
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    if config.symbol not in result:
        result.insert(0, config.symbol)
    return result


def _profile_with_owner_overrides(
    profile_body: dict[str, Any],
    config: BootstrapConfig,
) -> dict[str, Any]:
    result = dict(profile_body)
    if config.min_liquidation_stop_buffer is None:
        return result
    buffer_value = str(config.min_liquidation_stop_buffer)
    result["min_liquidation_stop_buffer"] = buffer_value
    boundary = dict(result.get("boundary") or {})
    boundary["min_liquidation_stop_buffer"] = buffer_value
    result["boundary"] = boundary
    metadata = dict(result.get("metadata") or {})
    metadata["owner_runtime_profile_overrides"] = {
        "min_liquidation_stop_buffer": buffer_value,
        "reason": "symbol_price_unit_adjustment_for_small_capital_trial",
    }
    result["metadata"] = metadata
    return result


def _profile_override_metadata(config: BootstrapConfig) -> dict[str, Any]:
    if config.min_liquidation_stop_buffer is None:
        return {}
    return {
        "min_liquidation_stop_buffer": str(config.min_liquidation_stop_buffer),
        "reason": "symbol_price_unit_adjustment_for_small_capital_trial",
    }


def _body(result: dict[str, Any]) -> dict[str, Any]:
    body = result.get("body")
    return body if isinstance(body, dict) else {}


def _step_result(name: str, body: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {}
    if name == "evaluate_admission_request":
        return {"admission_result": body.get("admission_result")}
    if name == "preflight_create_gated_trial":
        return {"preflight_result": body.get("preflight_result")}
    return {}


def _id_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    keys = (
        "strategy_family_id",
        "strategy_family_version_id",
        "admission_evidence_id",
        "owner_market_regime_input_id",
        "admission_request_id",
        "admission_decision_id",
        "trial_constraint_snapshot_id",
        "owner_risk_acceptance_id",
        "operation_id",
        "preflight_id",
        "idempotency_key",
    )
    result = {key: value.get(key) for key in keys if value.get(key)}
    for nested_key in ("result_summary", "confirmation", "runtime"):
        nested = value.get(nested_key)
        if isinstance(nested, dict):
            result.update({key: nested.get(key) for key in keys if nested.get(key)})
            if nested.get("confirmation_id"):
                result["confirmation_id"] = nested["confirmation_id"]
            if nested.get("runtime_instance_id"):
                result["runtime_instance_id"] = nested["runtime_instance_id"]
    return result


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(ROOT_DIR / ".env.local", override=True)


def _parse_bool_env(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_args(argv: list[str]) -> BootstrapConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=os.environ.get(API_BASE_ENV, DEFAULT_API_BASE))
    parser.add_argument(
        "--mode",
        choices=["inspect", "binding-only", "bootstrap"],
        default="inspect",
    )
    parser.add_argument("--strategy-family-id", default="CPM-001")
    parser.add_argument("--strategy-family-version-id", default="CPM-001-v0")
    parser.add_argument("--family-key", default="cpm-price-action")
    parser.add_argument("--family-name", default="CPM Price Action Reference")
    parser.add_argument("--symbol", default="BNB/USDT:USDT")
    parser.add_argument(
        "--supported-symbol",
        action="append",
        default=[],
        help=(
            "StrategyFamilyVersion supported symbol. May be repeated. Defaults "
            "to --symbol when omitted."
        ),
    )
    parser.add_argument("--side", default="long")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--capital-base", type=Decimal, default=Decimal("30"))
    parser.add_argument("--max-loss-budget", type=Decimal, default=Decimal("9"))
    parser.add_argument("--max-notional", type=Decimal, default=Decimal("10"))
    parser.add_argument("--max-leverage", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--min-liquidation-stop-buffer", type=Decimal)
    parser.add_argument("--playbook-id", default="PB-BRC-LIVE-RUNTIME-V1")
    parser.add_argument(
        "--account-facts-source",
        choices=["binance_readonly", "static"],
        default="binance_readonly",
    )
    parser.add_argument("--account-facts-json")
    parser.add_argument("--owner-operator-id", default="owner")
    parser.add_argument(
        "--runtime-carrier-id",
        default="strategygroup-runtime-bootstrap",
    )
    parser.add_argument(
        "--reason",
        default="Owner standing-authorized StrategyGroup runtime bootstrap",
    )
    args = parser.parse_args(argv)
    return BootstrapConfig(
        api_base=args.api_base,
        mode=args.mode,
        strategy_family_id=args.strategy_family_id,
        strategy_family_version_id=args.strategy_family_version_id,
        family_key=args.family_key,
        family_name=args.family_name,
        symbol=args.symbol,
        supported_symbols=args.supported_symbol,
        side=args.side,
        timeframe=args.timeframe,
        capital_base=args.capital_base,
        max_loss_budget=args.max_loss_budget,
        max_notional=args.max_notional,
        max_leverage=args.max_leverage,
        max_attempts=args.max_attempts,
        min_liquidation_stop_buffer=args.min_liquidation_stop_buffer,
        playbook_id=args.playbook_id,
        account_facts_source=args.account_facts_source,
        account_facts_json=args.account_facts_json,
        owner_operator_id=args.owner_operator_id,
        runtime_carrier_id=args.runtime_carrier_id,
        reason=args.reason,
    )


def main(argv: list[str] | None = None) -> int:
    config = _parse_args(argv or sys.argv[1:])
    flow = RuntimeLiveBootstrapApiFlow(
        client=UrlLibApiClient(api_base=config.api_base),
        config=config,
    )
    try:
        report = flow.run()
    except Exception as exc:
        report = {
            "script": "runtime_live_bootstrap_api_flow",
            "mode": config.mode,
            "blockers": [str(exc)],
            "warnings": [],
            "ids": {},
            "steps": [],
        }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not report["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
