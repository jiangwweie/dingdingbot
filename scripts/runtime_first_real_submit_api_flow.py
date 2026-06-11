#!/usr/bin/env python3
"""Guarded API flow for runtime first-real-submit.

The script drives the official Trading Console API surface.  It is intentionally
boring: every state transition is explicit, every response is captured, and the
real exchange submit action is only called when both CLI and env guards are
present.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.interfaces.operator_auth import (
    SESSION_COOKIE,
    _load_auth_config,
    _sign_payload,
)


API_BASE_ENV = "RUNTIME_FIRST_REAL_SUBMIT_API_BASE"
APPROVAL_ENV = "OWNER_APPROVED_RUNTIME_FIRST_REAL_SUBMIT"
DEFAULT_API_BASE = "http://127.0.0.1:18080"
DEFAULT_OUTCOME_KIND = "entry_filled_protection_creation_failed"


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
class FlowConfig:
    api_base: str
    mode: str
    env_file: str | None = None
    order_candidate_id: str | None = None
    authorization_id: str | None = None
    signal_input_path: str | None = None
    runtime_instance_id: str | None = None
    candidate_id: str | None = None
    context_id: str | None = None
    owner_operator_id: str = "owner"
    owner_confirmation_reference: str = "owner-authorized-first-real-submit"
    reason: str = "owner authorized first real runtime submit"
    outcome_kind: str = DEFAULT_OUTCOME_KIND
    next_attempt_symbol: str | None = None
    next_attempt_side: str | None = None
    next_attempt_family: str | None = None
    next_attempt_strategy_family_id: str | None = None
    next_attempt_carrier_id: str | None = None
    skip_next_attempt_gate_check: bool = False
    skip_order_candidate_usage_check: bool = False
    enable_local_registration: bool = True
    arm_exchange_submit_adapter: bool = True
    record_gateway_readiness: bool = True
    preview_disabled_first_real_submit_action: bool = False
    execute_real_submit: bool = False
    record_attempt_consumption: bool = False
    record_post_submit_accounting: bool = True
    adapter_result_store_implemented: bool = True
    real_adapter_boundary_implemented: bool = True


@dataclass
class FlowState:
    ids: dict[str, str] = field(default_factory=dict)
    steps: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_attempt_gate: dict[str, Any] | None = None

    def remember(self, key: str, value: Any) -> None:
        if value is None:
            return
        text = str(value).strip()
        if text:
            self.ids[key] = text

    def merge_ids(self, values: dict[str, Any] | None) -> None:
        for key, value in (values or {}).items():
            self.remember(key, value)

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


class UrlLibApiClient:
    def __init__(self, *, api_base: str) -> None:
        self._api_base = api_base.rstrip("/")
        self._cookie = _session_cookie()

    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self._api_base + path
        if query:
            url += "?" + urllib.parse.urlencode(_query_values(query))
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Content-Type": "application/json",
                "Cookie": self._cookie,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read().decode("utf-8")
                return {
                    "http_status": response.status,
                    "body": json.loads(raw) if raw else None,
                }
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                parsed: Any = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw
            return {
                "http_status": exc.code,
                "body": parsed,
                "error": True,
            }


class FirstRealSubmitApiFlow:
    def __init__(self, *, client: ApiClient, config: FlowConfig) -> None:
        self._client = client
        self._config = config
        self.state = FlowState()

    def run(self) -> dict[str, Any]:
        if self._config.mode == "inspect":
            self._inspect()
        elif self._config.mode == "disabled-smoke":
            if self._config.authorization_id:
                self.state.remember("authorization_id", self._config.authorization_id)
                self._preview_disabled_first_real_submit_action()
            else:
                self.state.add_blockers(["authorization_id_required_for_disabled_smoke"])
        else:
            self._verify_next_attempt_gate_if_available()
            if self.state.blockers:
                return self._report()
            if self._config.signal_input_path:
                self._create_shadow_candidate_from_signal_input()
            if self._config.order_candidate_id:
                self.state.remember("order_candidate_id", self._config.order_candidate_id)
                self._prepare_from_order_candidate()
            elif self._config.authorization_id:
                self.state.remember("authorization_id", self._config.authorization_id)
            else:
                self.state.add_blockers(
                    ["order_candidate_id_or_authorization_id_required"]
                )
            if self._config.mode in {"arm", "execute"}:
                if self._config.mode == "execute":
                    authorization_id = self._required_id("authorization_id")
                    if authorization_id:
                        self._require_final_execute_guard(authorization_id)
                    if self.state.blockers:
                        return self._report()
                self._arm_for_exchange_submit()
            if self._config.mode == "execute":
                self._execute_first_real_submit()
                if self._config.record_post_submit_accounting:
                    self._record_post_submit_accounting()
        return self._report()

    def _inspect(self) -> None:
        self._step("list_strategy_runtimes", "GET", "/api/trading-console/strategy-runtimes")
        self._step("list_order_candidates", "GET", "/api/trading-console/order-candidates")

    def _create_shadow_candidate_from_signal_input(self) -> None:
        if not self._config.runtime_instance_id:
            self.state.add_blockers(["runtime_instance_id_required_for_signal_input"])
            return
        signal_input = self._load_signal_input()
        body = {
            "signal_input": signal_input,
            "allow_shadow_candidate_creation": True,
            "candidate_id": self._config.candidate_id,
            "context_id": self._config.context_id,
            "metadata": {
                "source": "runtime_first_real_submit_api_flow",
                "owner_authorized_first_real_submit": self._config.execute_real_submit,
            },
        }
        result = self._step(
            "create_shadow_candidate_from_signal_input",
            "POST",
            (
                "/api/trading-console/strategy-runtimes/"
                f"{self._config.runtime_instance_id}/strategy-signal-shadow-plans"
            ),
            body=body,
        )
        body = _body(result)
        candidate = (
            body.get("candidate_planning_result", {}).get("candidate")
            if isinstance(body, dict)
            else None
        )
        if isinstance(candidate, dict):
            self.state.remember("order_candidate_id", candidate.get("order_candidate_id"))
            self._config.order_candidate_id = candidate.get("order_candidate_id")

    def _verify_next_attempt_gate_if_available(self) -> None:
        if self._config.skip_next_attempt_gate_check:
            self.state.add_warnings(["next_attempt_gate_check_skipped_by_cli"])
            return

        scope = self._next_attempt_gate_scope()
        symbol = scope.get("symbol")
        if not symbol:
            self.state.add_warnings(["next_attempt_gate_check_skipped_symbol_missing"])
            return

        result = self._step(
            "verify_next_attempt_gate",
            "GET",
            "/api/trading-console/owner-action-flow",
            query={
                "include_exchange": False,
                "symbol": symbol,
                "side": scope.get("side"),
                "family": scope.get("family"),
                "strategy_family_id": scope.get("strategy_family_id"),
                "carrier_id": scope.get("carrier_id"),
            },
            collect_body_blockers=False,
        )
        body = _body(result)
        gate = _extract_next_attempt_gate(body)
        self.state.next_attempt_gate = gate
        if result.get("http_status", 0) >= 300 or result.get("error"):
            return
        if not gate:
            self.state.add_blockers(["next_attempt_gate_missing_from_owner_action_flow"])
            return
        status = str(gate.get("status") or "")
        gate_name = str(gate.get("gate") or "")
        if (
            status != "clear_for_preflight"
            or gate.get("next_attempt_allowed_by_lifecycle") is not True
        ):
            self.state.add_blockers(
                [f"next_attempt_gate_not_clear:{gate_name or status or 'unknown'}"]
            )
            for blocker in gate.get("blockers") or []:
                if isinstance(blocker, dict) and blocker.get("id"):
                    self.state.add_blockers([f"next_attempt_gate:{blocker['id']}"])

    def _next_attempt_gate_scope(self) -> dict[str, Any]:
        scope: dict[str, Any] = {
            "symbol": self._config.next_attempt_symbol,
            "side": self._config.next_attempt_side,
            "family": self._config.next_attempt_family,
            "strategy_family_id": self._config.next_attempt_strategy_family_id,
            "carrier_id": self._config.next_attempt_carrier_id,
        }
        if self._config.signal_input_path:
            try:
                signal_input = self._load_signal_input()
            except (OSError, json.JSONDecodeError):
                return scope
            scope["symbol"] = scope.get("symbol") or signal_input.get("symbol")
            scope["strategy_family_id"] = (
                scope.get("strategy_family_id")
                or signal_input.get("strategy_family_id")
            )
            scope["carrier_id"] = (
                scope.get("carrier_id")
                or signal_input.get("strategy_family_version_id")
            )
        return scope

    def _load_signal_input(self) -> dict[str, Any]:
        with open(self._config.signal_input_path or "", "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("signal_input_json_must_be_object")
        return payload

    def _prepare_from_order_candidate(self) -> None:
        candidate_id = self._required_id("order_candidate_id")
        if not candidate_id:
            return
        self._verify_order_candidate_reusable(candidate_id)
        if self.state.blockers:
            return
        draft = self._step(
            "record_intent_draft",
            "POST",
            f"/api/trading-console/runtime-execution-intent-drafts/order-candidates/{candidate_id}",
            query={
                "owner_reviewed": True,
                "owner_confirmed_for_intent": True,
            },
        )
        draft_body = _body(draft)
        self.state.remember("runtime_execution_intent_draft_id", draft_body.get("draft_id"))

        draft_id = self._required_id("runtime_execution_intent_draft_id")
        if not draft_id:
            return
        intent = self._step(
            "record_execution_intent",
            "POST",
            f"/api/trading-console/runtime-execution-intents/drafts/{draft_id}",
        )
        intent_body = _body(intent)
        self.state.remember("execution_intent_id", intent_body.get("id"))

        self._record_protection_plan()

        intent_id = self._required_id("execution_intent_id")
        if not intent_id:
            return
        authorization = self._step(
            "record_submit_authorization",
            "POST",
            f"/api/trading-console/runtime-execution-submit-authorizations/intents/{intent_id}",
            query={"owner_confirmed_for_submit": True},
        )
        authorization_body = _body(authorization)
        self.state.remember("authorization_id", authorization_body.get("authorization_id"))

        self._record_evidence_preparation(collect_body_blockers=False)

    def _hydrate_authorization_context(self) -> None:
        authorization_id = self._required_id("authorization_id")
        if not authorization_id:
            return
        plan = self._step(
            "hydrate_controlled_submit_plan",
            "GET",
            (
                "/api/trading-console/"
                "runtime-execution-controlled-submit-plans/"
                f"authorizations/{authorization_id}"
            ),
        )
        body = _body(plan)
        self.state.remember("execution_intent_id", body.get("execution_intent_id"))
        self.state.remember(
            "runtime_execution_intent_draft_id",
            body.get("runtime_execution_intent_draft_id"),
        )
        semantic_ids = body.get("semantic_ids")
        if isinstance(semantic_ids, dict):
            self.state.merge_ids(
                {
                    "order_candidate_id": semantic_ids.get("order_candidate_id"),
                    "runtime_instance_id": semantic_ids.get("runtime_instance_id"),
                    "signal_evaluation_id": semantic_ids.get("signal_evaluation_id"),
                }
            )
        self.state.remember("order_candidate_id", body.get("source_id"))

    def _record_protection_plan(self) -> None:
        intent_id = self._required_id("execution_intent_id")
        if not intent_id:
            return
        protection_plan = self._step(
            "record_protection_plan",
            "POST",
            (
                "/api/trading-console/"
                f"runtime-execution-protection-plans/intents/{intent_id}"
            ),
        )
        self.state.remember(
            "protection_plan_id",
            _body(protection_plan).get("protection_plan_id"),
        )

    def _record_evidence_preparation(
        self,
        *,
        collect_body_blockers: bool = True,
    ) -> dict[str, Any]:
        authorization_id = self._required_id("authorization_id")
        if not authorization_id:
            return {}
        preparation = self._step(
            "prepare_machine_evidence",
            "POST",
            (
                "/api/trading-console/"
                "runtime-execution-first-real-submit-evidence-preparations/"
                f"authorizations/{authorization_id}"
            ),
            query={
                "adapter_result_store_implemented": (
                    self._config.adapter_result_store_implemented
                ),
                "real_adapter_boundary_implemented": (
                    self._config.real_adapter_boundary_implemented
                ),
            },
            collect_body_blockers=collect_body_blockers,
        )
        body = _body(preparation)
        self.state.merge_ids(body.get("available_evidence_ids"))
        self.state.merge_ids(body.get("prepared_evidence_ids"))
        if self.state.ids.get("attempt_outcome_policy_id"):
            reservation_id = f"runtime-attempt-reservation-{authorization_id}"
            self.state.remember("reservation_id", reservation_id)
            self.state.remember(
                "attempt_mutation_id",
                f"runtime-attempt-mutation-{reservation_id}",
            )
        return body

    def _verify_order_candidate_reusable(self, candidate_id: str) -> None:
        if self._config.skip_order_candidate_usage_check:
            self.state.add_warnings(["order_candidate_usage_check_skipped_by_cli"])
            return
        result = self._step(
            "verify_order_candidate_usage",
            "GET",
            f"/api/trading-console/order-candidates/{candidate_id}",
            collect_body_blockers=False,
        )
        body = _body(result)
        if result.get("http_status", 0) >= 300 or result.get("error"):
            return
        reusable = body.get("candidate_reusable_for_new_attempt")
        if reusable is None:
            self.state.add_warnings(["order_candidate_usage_check_unavailable"])
            return
        if reusable is not True:
            usage_status = str(body.get("candidate_usage_status") or "unknown")
            reuse_blocker = str(body.get("reuse_blocker") or "candidate_not_reusable")
            self.state.add_blockers(
                [
                    f"order_candidate_not_reusable:{usage_status}",
                    reuse_blocker,
                ]
            )

    def _record_attempt_reservation_and_policy(self) -> None:
        authorization_id = self._required_id("authorization_id")
        if not authorization_id:
            return
        if self.state.ids.get("attempt_outcome_policy_id"):
            self.state.add_warnings(
                [
                    (
                        "existing_attempt_outcome_policy_reused_"
                        "no_new_attempt_mutation"
                    )
                ]
            )
            return
        reservation = self._step(
            "record_attempt_reservation",
            "POST",
            (
                "/api/trading-console/"
                f"runtime-execution-attempt-reservations/authorizations/{authorization_id}"
            ),
        )
        reservation_body = _body(reservation)
        self.state.remember("reservation_id", reservation_body.get("reservation_id"))
        if self.state.blockers:
            return

        reservation_id = self._required_id("reservation_id")
        if not reservation_id:
            return
        mutation = self._step(
            "apply_attempt_mutation",
            "POST",
            (
                "/api/trading-console/"
                f"runtime-execution-attempt-mutations/reservations/{reservation_id}"
            ),
        )
        self.state.remember("attempt_mutation_id", _body(mutation).get("mutation_id"))
        if self.state.blockers:
            return

        policy = self._step(
            "record_attempt_outcome_policy",
            "POST",
            (
                "/api/trading-console/"
                f"runtime-execution-attempt-outcome-policies/reservations/{reservation_id}"
            ),
            query={"outcome_kind": self._config.outcome_kind},
        )
        self.state.remember("attempt_outcome_policy_id", _body(policy).get("policy_id"))
        if self.state.blockers:
            return
        self._record_evidence_preparation(collect_body_blockers=False)

    def _record_order_lifecycle_handoff(self) -> None:
        authorization_id = self._required_id("authorization_id")
        if not authorization_id:
            return
        self._step(
            "record_order_lifecycle_handoff_draft",
            "POST",
            (
                "/api/trading-console/"
                "runtime-execution-order-lifecycle-handoff-drafts/"
                f"authorizations/{authorization_id}"
            ),
        )

    def _arm_for_exchange_submit(self) -> None:
        if not self._config.enable_local_registration:
            self.state.add_blockers(["local_registration_not_enabled_by_cli"])
            return
        authorization_id = self._required_id("authorization_id")
        if not authorization_id:
            return
        self._hydrate_authorization_context()
        if self.state.blockers:
            return
        self._record_protection_plan()
        if self.state.blockers:
            return
        evidence_body = self._record_evidence_preparation(collect_body_blockers=False)
        self.state.add_blockers(_pre_adapter_evidence_blockers(evidence_body))
        if any(blocker.endswith("_http_404") for blocker in self.state.blockers):
            return
        if self.state.blockers:
            return
        if not self._config.record_attempt_consumption:
            if self.state.ids.get("attempt_outcome_policy_id"):
                self.state.add_warnings(
                    [
                        (
                            "existing_attempt_outcome_policy_reused_"
                            "no_new_attempt_mutation"
                        )
                    ]
                )
            else:
                self.state.add_warnings(
                    ["attempt_consumption_not_recorded_in_arm_preview"]
                )
                self.state.add_blockers(
                    ["attempt_consumption_required_before_order_lifecycle_handoff"]
                )
                return

        if self._config.record_attempt_consumption:
            self._record_attempt_reservation_and_policy()
            if self.state.blockers:
                return

        self._record_order_lifecycle_handoff()
        if self.state.blockers:
            return
        self._derive_action_ids(authorization_id)
        local_action = self._step(
            "record_local_registration_action_authorization",
            "POST",
            (
                "/api/trading-console/"
                "runtime-execution-local-registration-action-authorizations/"
                f"authorizations/{authorization_id}"
            ),
            query={
                **self._common_evidence_query(local=True),
                "owner_confirmed_for_local_registration_action": True,
                "owner_operator_id": self._config.owner_operator_id,
                "reason": self._config.reason,
                "owner_confirmation_reference": (
                    self._config.owner_confirmation_reference
                ),
            },
        )
        self.state.remember(
            "local_registration_action_authorization_id",
            _body(local_action).get("action_authorization_id"),
        )
        local_enablement = self._step(
            "preview_local_registration_enablement",
            "GET",
            (
                "/api/trading-console/"
                "runtime-execution-local-registration-enablements/"
                f"authorizations/{authorization_id}"
            ),
            query=self._common_evidence_query(
                local=True,
                include_local_registration_action=True,
            ),
        )
        self.state.remember(
            "local_registration_enablement_decision_id",
            _body(local_enablement).get("decision_id"),
        )
        local_result = self._step(
            "record_local_order_registration_result",
            "POST",
            (
                "/api/trading-console/"
                "runtime-execution-order-lifecycle-adapter-results/"
                f"authorizations/{authorization_id}"
            ),
            query={
                **self._common_evidence_query(
                    local=True,
                    include_local_registration_action=True,
                ),
                "order_lifecycle_adapter_enabled": True,
                "local_order_registration_enabled": True,
            },
        )
        self.state.remember(
            "local_registration_adapter_result_id",
            _body(local_result).get("adapter_result_id"),
        )
        if not self._config.arm_exchange_submit_adapter:
            return
        if self._config.record_gateway_readiness:
            readiness = self._step(
                "record_exchange_gateway_readiness",
                "POST",
                "/api/trading-console/runtime-execution-exchange-gateway-readiness",
                query={
                    "owner_confirmed_gateway_readiness_review": True,
                    "owner_operator_id": self._config.owner_operator_id,
                    "reason": self._config.reason,
                    "owner_confirmation_reference": (
                        self._config.owner_confirmation_reference
                    ),
                },
            )
            self.state.remember(
                "deployment_readiness_evidence_id",
                _body(readiness).get("readiness_id"),
            )

        exchange_action = self._step(
            "record_exchange_submit_action_authorization",
            "POST",
            (
                "/api/trading-console/"
                "runtime-execution-exchange-submit-action-authorizations/"
                f"authorizations/{authorization_id}"
            ),
            query={
                **self._common_evidence_query(exchange=True),
                "owner_confirmed_for_exchange_submit_action": True,
                "owner_operator_id": self._config.owner_operator_id,
                "reason": self._config.reason,
                "owner_confirmation_reference": (
                    self._config.owner_confirmation_reference
                ),
            },
        )
        self.state.remember(
            "exchange_submit_action_authorization_id",
            _body(exchange_action).get("action_authorization_id"),
        )
        exchange_enablement = self._step(
            "preview_exchange_submit_enablement",
            "GET",
            (
                "/api/trading-console/"
                "runtime-execution-exchange-submit-enablements/"
                f"authorizations/{authorization_id}"
            ),
            query=self._common_evidence_query(
                exchange=True,
                include_exchange_action=True,
            ),
        )
        self.state.remember(
            "exchange_submit_enablement_decision_id",
            _body(exchange_enablement).get("decision_id"),
        )
        exchange_adapter = self._step(
            "record_exchange_submit_adapter_result",
            "POST",
            (
                "/api/trading-console/"
                "runtime-execution-exchange-submit-adapter-results/"
                f"authorizations/{authorization_id}"
            ),
            query={
                **self._common_evidence_query(
                    exchange=True,
                    include_exchange_action=True,
                ),
                "exchange_submit_adapter_enabled": True,
            },
        )
        self.state.remember(
            "exchange_submit_adapter_result_id",
            _body(exchange_adapter).get("adapter_result_id"),
        )
        self._preview_enablement_packet()
        if self._config.preview_disabled_first_real_submit_action:
            self._preview_disabled_first_real_submit_action()

    def _preview_disabled_first_real_submit_action(self) -> None:
        authorization_id = self._required_id("authorization_id")
        if not authorization_id:
            return
        result = self._step(
            "preview_disabled_first_real_submit_action",
            "POST",
            (
                "/api/trading-console/"
                "runtime-execution-first-real-submit-actions/"
                f"authorizations/{authorization_id}"
            ),
            query={
                **self._common_evidence_query(
                    exchange=True,
                    include_exchange_action=True,
                ),
                "owner_confirmed_for_first_real_submit_action": False,
            },
        )
        body = _body(result)
        self.state.remember(
            "disabled_first_real_submit_execution_result_id",
            body.get("execution_result_id"),
        )
        status = str(body.get("status") or "")
        if status and status != "exchange_submit_execution_disabled":
            self.state.add_blockers(
                [
                    (
                        "disabled_first_real_submit_action_unexpected_status:"
                        f"{status}"
                    )
                ]
            )
        if result.get("http_status") == 404:
            detail = _optional_detail(body)
            if detail:
                self.state.add_warnings(
                    [
                        (
                            "disabled_first_real_submit_action_prerequisite_missing:"
                            f"{detail}"
                        )
                    ]
                )

    def _execute_first_real_submit(self) -> None:
        authorization_id = self._required_id("authorization_id")
        if not authorization_id:
            return
        self._require_final_execute_guard(authorization_id)
        if self.state.blockers:
            return
        result = self._step(
            "execute_first_real_submit_action",
            "POST",
            (
                "/api/trading-console/"
                "runtime-execution-first-real-submit-actions/"
                f"authorizations/{authorization_id}"
            ),
            query={
                **self._common_evidence_query(
                    exchange=True,
                    include_exchange_action=True,
                ),
                "owner_confirmed_for_first_real_submit_action": True,
            },
        )
        body = _body(result)
        self.state.remember("execution_result_id", body.get("execution_result_id"))
        for key in ("entry_exchange_order_id", "failed_reason"):
            self.state.remember(key, body.get(key))

    def _record_post_submit_accounting(self) -> None:
        authorization_id = self._required_id("authorization_id")
        reservation_id = self._required_id("reservation_id")
        if not authorization_id or not reservation_id:
            return
        review = self._step(
            "record_submit_outcome_review",
            "POST",
            (
                "/api/trading-console/"
                f"runtime-execution-submit-outcome-reviews/authorizations/{authorization_id}"
            ),
        )
        self.state.remember("submit_outcome_review_id", _body(review).get("review_id"))
        accounting = self._step(
            "record_first_real_submit_outcome_accounting",
            "POST",
            (
                "/api/trading-console/"
                "runtime-execution-first-real-submit-outcome-accounting/"
                f"authorizations/{authorization_id}"
            ),
            query={"reservation_id": reservation_id},
        )
        self.state.remember(
            "first_real_submit_outcome_accounting_id",
            _body(accounting).get("accounting_id"),
        )
        settlement = self._step(
            "record_post_submit_budget_settlement",
            "POST",
            (
                "/api/trading-console/"
                "runtime-execution-post-submit-budget-settlements/"
                f"authorizations/{authorization_id}"
            ),
            query={"reservation_id": reservation_id},
        )
        self.state.remember(
            "post_submit_budget_settlement_id",
            _body(settlement).get("settlement_id"),
        )

    def _preview_enablement_packet(self) -> None:
        authorization_id = self._required_id("authorization_id")
        if not authorization_id:
            return
        packet = self._step(
            "preview_first_real_submit_enablement_packet",
            "GET",
            (
                "/api/trading-console/"
                "runtime-execution-first-real-submit-enablement-packets/"
                f"authorizations/{authorization_id}"
            ),
            query={
                **self._common_evidence_query(
                    exchange=True,
                    include_exchange_action=True,
                ),
                "exchange_submit_enablement_decision_id": self.state.ids.get(
                    "exchange_submit_enablement_decision_id"
                ),
                "budget_release_or_consume_rule_confirmed": True,
                "protection_creation_failure_policy_confirmed": True,
                "duplicate_submit_policy_confirmed": True,
                "deployment_readiness_confirmed": True,
                "explicit_owner_real_submit_authorization": True,
                "strategy_family_confirmed": True,
                "implementation_source_confirmed": True,
                "required_facts_confirmed": True,
                "entry_policy_confirmed": True,
                "exit_policy_confirmed": True,
                "protection_policy_confirmed": True,
                "eligible_for_runtime_execution_confirmed": True,
                "right_tail_review_metrics_confirmed": True,
                "runtime_profile_confirmed": True,
                "owner_confirmation_mode_confirmed": True,
                "symbol_side_boundary_confirmed": True,
                "max_loss_budget_confirmed": True,
                "max_notional_boundary_confirmed": True,
                "max_active_positions_boundary_confirmed": True,
                "max_leverage_boundary_confirmed": True,
                "margin_usage_boundary_confirmed": True,
                "liquidation_buffer_boundary_confirmed": True,
                "protection_readiness_source_confirmed": True,
                "stale_fact_behavior_confirmed": True,
                "attempt_consumption_rule_confirmed": True,
                "budget_reservation_rule_confirmed": True,
                "trusted_active_position_source_confirmed": True,
                "trusted_account_fact_source_confirmed": True,
                "short_side_conservative_profile_confirmed": True,
            },
        )
        self.state.remember("first_real_submit_packet_status", _body(packet).get("status"))

    def _derive_action_ids(self, authorization_id: str) -> None:
        self.state.remember(
            "owner_real_submit_authorization_id",
            f"owner-real-submit-authorization-{authorization_id}",
        )
        self.state.remember(
            "order_lifecycle_adapter_enablement_id",
            f"order-lifecycle-adapter-enable-{authorization_id}",
        )
        self.state.remember(
            "local_order_registration_enablement_id",
            f"local-order-registration-enable-{authorization_id}",
        )
        self.state.remember(
            "order_lifecycle_submit_enablement_id",
            f"order-lifecycle-submit-enable-{authorization_id}",
        )
        self.state.remember(
            "exchange_submit_adapter_enablement_id",
            f"exchange-submit-adapter-enable-{authorization_id}",
        )

    def _common_evidence_query(
        self,
        *,
        local: bool = False,
        exchange: bool = False,
        include_local_registration_action: bool = False,
        include_exchange_action: bool = False,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {
            "trusted_submit_fact_snapshot_id": self.state.ids.get(
                "trusted_submit_fact_snapshot_id"
            ),
            "submit_idempotency_policy_id": self.state.ids.get(
                "submit_idempotency_policy_id"
            ),
            "attempt_outcome_policy_id": self.state.ids.get(
                "attempt_outcome_policy_id"
            ),
            "protection_creation_failure_policy_id": self.state.ids.get(
                "protection_creation_failure_policy_id"
            ),
            "owner_real_submit_authorization_id": self.state.ids.get(
                "owner_real_submit_authorization_id"
            ),
            "deployment_readiness_evidence_id": self.state.ids.get(
                "deployment_readiness_evidence_id"
            ),
        }
        if local:
            query.update(
                {
                    "order_lifecycle_adapter_enablement_id": self.state.ids.get(
                        "order_lifecycle_adapter_enablement_id"
                    ),
                    "local_order_registration_enablement_id": self.state.ids.get(
                        "local_order_registration_enablement_id"
                    ),
                }
            )
        if include_local_registration_action:
            query["local_registration_action_authorization_id"] = self.state.ids.get(
                "local_registration_action_authorization_id"
            )
        if exchange:
            query.update(
                {
                    "local_registration_enablement_decision_id": self.state.ids.get(
                        "local_registration_enablement_decision_id"
                    ),
                    "order_lifecycle_submit_enablement_id": self.state.ids.get(
                        "order_lifecycle_submit_enablement_id"
                    ),
                    "exchange_submit_adapter_enablement_id": self.state.ids.get(
                        "exchange_submit_adapter_enablement_id"
                    ),
                }
            )
        if include_exchange_action:
            query["exchange_submit_action_authorization_id"] = self.state.ids.get(
                "exchange_submit_action_authorization_id"
            )
        return query

    def _step(
        self,
        name: str,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        collect_body_blockers: bool = True,
    ) -> dict[str, Any]:
        result = self._client.request_json(method, path, query=query, body=body)
        body_value = _body(result)
        record = {
            "name": name,
            "method": method,
            "path": path,
            "query_keys": sorted(k for k, v in (query or {}).items() if v is not None),
            "http_status": result.get("http_status"),
            "status": body_value.get("status") if isinstance(body_value, dict) else None,
            "detail": _optional_detail(body_value),
            "id_summary": _id_summary(body_value),
            "blockers": body_value.get("blockers", []) if isinstance(body_value, dict) else [],
            "warnings": body_value.get("warnings", []) if isinstance(body_value, dict) else [],
        }
        self.state.steps.append(record)
        if result.get("http_status", 0) >= 300 or result.get("error"):
            self.state.add_blockers([f"{name}_http_{result.get('http_status')}"])
        if isinstance(body_value, dict) and collect_body_blockers:
            self.state.add_blockers(body_value.get("blockers"))
        if isinstance(body_value, dict):
            self.state.add_warnings(body_value.get("warnings"))
        return result

    def _required_id(self, key: str) -> str | None:
        value = self.state.ids.get(key)
        if not value:
            self.state.add_blockers([f"{key}_missing"])
            return None
        return value

    def _require_final_execute_guard(self, authorization_id: str) -> None:
        if not self._config.execute_real_submit:
            self.state.add_blockers(["execute_real_submit_cli_flag_missing"])
            return
        expected = _approval_value(authorization_id)
        actual = os.environ.get(APPROVAL_ENV, "").strip()
        if actual != expected:
            self.state.add_blockers(
                [
                    "owner_runtime_first_real_submit_env_confirmation_missing",
                    f"expected_{APPROVAL_ENV}={expected}",
                ]
            )

    def _report(self) -> dict[str, Any]:
        return {
            "script": "runtime_first_real_submit_api_flow",
            "mode": self._config.mode,
            "api_base": self._config.api_base,
            "ready_for_real_submit_action": (
                self._config.mode == "execute"
                and self._config.execute_real_submit
                and not self.state.blockers
            ),
            "ids": self.state.ids,
            "next_attempt_gate": self.state.next_attempt_gate or {},
            "steps": self.state.steps,
            "blockers": self.state.blockers,
            "warnings": self.state.warnings,
            "safety": {
                "uses_official_trading_console_api": True,
                "owner_authorization_required_for_real_submit": True,
                "real_submit_requires_cli_flag": True,
                "real_submit_requires_env_confirmation": True,
                "env_confirmation_name": APPROVAL_ENV,
                "no_withdrawal_or_transfer": True,
            },
        }


def _body(result: dict[str, Any]) -> dict[str, Any]:
    body = result.get("body")
    return body if isinstance(body, dict) else {}


def _optional_detail(value: dict[str, Any]) -> str | None:
    detail = value.get("detail")
    if detail is None:
        return None
    text = str(detail).strip()
    return text or None


def _id_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    keys = (
        "id",
        "draft_id",
        "authorization_id",
        "reservation_id",
        "mutation_id",
        "policy_id",
        "decision_id",
        "action_authorization_id",
        "adapter_result_id",
        "execution_result_id",
        "readiness_id",
        "settlement_id",
        "review_id",
        "accounting_id",
    )
    return {key: value.get(key) for key in keys if value.get(key)}


def _extract_next_attempt_gate(body: dict[str, Any]) -> dict[str, Any]:
    data = body.get("data")
    if isinstance(data, dict):
        post_action = data.get("post_action_state")
        if isinstance(post_action, dict) and isinstance(
            post_action.get("next_attempt_gate"),
            dict,
        ):
            return post_action["next_attempt_gate"]
    post_action = body.get("post_action_state")
    if isinstance(post_action, dict) and isinstance(post_action.get("next_attempt_gate"), dict):
        return post_action["next_attempt_gate"]
    gate = body.get("next_attempt_gate")
    return gate if isinstance(gate, dict) else {}


def _pre_adapter_evidence_blockers(body: dict[str, Any]) -> list[str]:
    """Block arm on submit facts while tolerating the expected missing adapter result."""
    tolerated_fragments = (
        "runtimeexecutionorderlifecycleadapterresult_not_found",
        "runtime_execution_order_lifecycle_adapter_result_not_found",
    )
    blockers = body.get("blockers") if isinstance(body, dict) else None
    result: list[str] = []
    for blocker in blockers or []:
        text = str(blocker)
        if any(fragment in text for fragment in tolerated_fragments):
            continue
        result.append(text)
    return result


def _query_values(query: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in query.items():
        if value is None:
            continue
        if isinstance(value, bool):
            result[key] = "true" if value else "false"
        else:
            result[key] = str(value)
    return result


def _load_env_file(path: str | None) -> None:
    if not path:
        return
    env_path = Path(path).expanduser()
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and not os.environ.get(key):
            os.environ[key] = value


def _session_cookie() -> str:
    config = _load_auth_config()
    now = int(time.time())
    token = _sign_payload(
        {
            "sub": config.username,
            "iat": now,
            "exp": now + min(config.ttl_seconds, 3600),
            "scope": "brc_operator_console",
        },
        config.session_secret,
    )
    return f"{SESSION_COOKIE}={token}"


def _approval_value(authorization_id: str) -> str:
    return f"{authorization_id}:first-real-submit:real_gateway_action"


def _parse_args(argv: list[str]) -> FlowConfig:
    parser = argparse.ArgumentParser(
        description="Run a guarded runtime first-real-submit API flow.",
    )
    parser.add_argument("--api-base", default=os.environ.get(API_BASE_ENV, DEFAULT_API_BASE))
    parser.add_argument("--env-file", help="Optional env file for operator auth/API config.")
    parser.add_argument(
        "--mode",
        choices=["inspect", "prepare", "arm", "execute", "disabled-smoke"],
        default="inspect",
    )
    parser.add_argument("--order-candidate-id")
    parser.add_argument("--authorization-id")
    parser.add_argument("--signal-input-json", dest="signal_input_path")
    parser.add_argument("--runtime-instance-id")
    parser.add_argument("--candidate-id")
    parser.add_argument("--context-id")
    parser.add_argument("--owner-operator-id", default="owner")
    parser.add_argument(
        "--owner-confirmation-reference",
        default="owner-authorized-first-real-submit",
    )
    parser.add_argument("--reason", default="owner authorized first real runtime submit")
    parser.add_argument("--outcome-kind", default=DEFAULT_OUTCOME_KIND)
    parser.add_argument("--next-attempt-symbol")
    parser.add_argument("--next-attempt-side")
    parser.add_argument("--next-attempt-family")
    parser.add_argument("--next-attempt-strategy-family-id")
    parser.add_argument("--next-attempt-carrier-id")
    parser.add_argument("--skip-next-attempt-gate-check", action="store_true")
    parser.add_argument("--skip-order-candidate-usage-check", action="store_true")
    parser.add_argument("--skip-local-registration", action="store_true")
    parser.add_argument("--skip-exchange-arm", action="store_true")
    parser.add_argument("--skip-gateway-readiness", action="store_true")
    parser.add_argument(
        "--record-attempt-consumption",
        action="store_true",
        help=(
            "Record attempt reservation/mutation during arm. Defaults to true "
            "only for execute mode; disabled previews should not consume attempts."
        ),
    )
    parser.add_argument(
        "--preview-disabled-first-real-submit-action",
        action="store_true",
        help=(
            "After arm evidence is ready, call the official first-real-submit "
            "action wrapper with owner_confirmed=false. This proves the action "
            "surface is reachable while keeping exchange execution disabled."
        ),
    )
    parser.add_argument("--execute-real-submit", action="store_true")
    parser.add_argument("--skip-post-submit-accounting", action="store_true")
    parser.add_argument("--adapter-result-store-implemented", action="store_true", default=True)
    parser.add_argument("--real-adapter-boundary-implemented", action="store_true", default=True)
    args = parser.parse_args(argv)
    return FlowConfig(
        api_base=args.api_base,
        mode=args.mode,
        env_file=args.env_file,
        order_candidate_id=args.order_candidate_id,
        authorization_id=args.authorization_id,
        signal_input_path=args.signal_input_path,
        runtime_instance_id=args.runtime_instance_id,
        candidate_id=args.candidate_id,
        context_id=args.context_id,
        owner_operator_id=args.owner_operator_id,
        owner_confirmation_reference=args.owner_confirmation_reference,
        reason=args.reason,
        outcome_kind=args.outcome_kind,
        next_attempt_symbol=args.next_attempt_symbol,
        next_attempt_side=args.next_attempt_side,
        next_attempt_family=args.next_attempt_family,
        next_attempt_strategy_family_id=args.next_attempt_strategy_family_id,
        next_attempt_carrier_id=args.next_attempt_carrier_id,
        skip_next_attempt_gate_check=args.skip_next_attempt_gate_check,
        skip_order_candidate_usage_check=args.skip_order_candidate_usage_check,
        enable_local_registration=not args.skip_local_registration,
        arm_exchange_submit_adapter=not args.skip_exchange_arm,
        record_gateway_readiness=not args.skip_gateway_readiness,
        preview_disabled_first_real_submit_action=(
            args.preview_disabled_first_real_submit_action
        ),
        execute_real_submit=args.execute_real_submit,
        record_attempt_consumption=(
            args.record_attempt_consumption or args.mode == "execute"
        ),
        record_post_submit_accounting=not args.skip_post_submit_accounting,
        adapter_result_store_implemented=args.adapter_result_store_implemented,
        real_adapter_boundary_implemented=args.real_adapter_boundary_implemented,
    )


def main(argv: list[str] | None = None) -> int:
    config = _parse_args(argv or sys.argv[1:])
    _load_env_file(config.env_file)
    flow = FirstRealSubmitApiFlow(
        client=UrlLibApiClient(api_base=config.api_base),
        config=config,
    )
    report = flow.run()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if not report["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
