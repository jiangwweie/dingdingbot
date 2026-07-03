from __future__ import annotations

from fastapi.testclient import TestClient

from src.application.brc_admission_service import AdmissionRuleViolation
from src.domain.brc_admission import (
    AdmissionDecision,
    AdmissionDecisionValue,
    AdmissionExecutionMode,
    AdmissionEvidence,
    AdmissionRequest,
    AdmissionTrialBinding,
    AdmissionTrialBindingStatus,
    OwnerMarketRegimeInput,
    StrategyFamily,
    StrategyFamilyStatus,
    StrategyFamilyVersion,
    TrialEnv,
    TrialStage,
)
from src.interfaces.operator_auth import require_operator_session


def _now() -> int:
    return 1770000000000


class _FakeAdmissionService:
    def __init__(self) -> None:
        self.family = StrategyFamily(
            strategy_family_id="sf-test",
            family_key="ema60",
            name="EMA60",
            status=StrategyFamilyStatus.INTAKE,
            created_at_ms=_now(),
            updated_at_ms=_now(),
        )
        self.version = StrategyFamilyVersion(
            strategy_family_version_id="sfv-test",
            strategy_family_id="sf-test",
            version=1,
            playbook_id="PB-004-BRC-CONTROLLED-TESTNET",
            playbook_catalog_snapshot_json={"id": "PB-004-BRC-CONTROLLED-TESTNET"},
            created_at_ms=_now(),
        )
        self.evidence = AdmissionEvidence(
            admission_evidence_id="evidence-test",
            strategy_family_version_id="sfv-test",
            payload_json={},
            mandatory_complete=False,
            created_at_ms=_now(),
        )
        self.regime = OwnerMarketRegimeInput(
            owner_market_regime_input_id="regime-test",
            current_regime="range",
            created_at_ms=_now(),
        )
        self.request = AdmissionRequest(
            admission_request_id="admission-req-test",
            strategy_family_version_id="sfv-test",
            admission_evidence_id="evidence-test",
            owner_market_regime_input_id="regime-test",
            trial_env=TrialEnv.TESTNET,
            trial_stage=TrialStage.FUNDED_VALIDATION,
            requested_risk_profile="micro",
            account_facts_snapshot_ref="acct-facts-1",
            account_facts_snapshot_json={"source": "exchange_testnet"},
            created_at_ms=_now(),
        )
        self.decision = AdmissionDecision(
            admission_decision_id="decision-test",
            admission_request_id="admission-req-test",
            decision=AdmissionDecisionValue.ADMIT_WITH_CONSTRAINTS,
            trial_env=TrialEnv.TESTNET,
            trial_stage=TrialStage.FUNDED_VALIDATION,
            strategy_family_version_id="sfv-test",
            playbook_id="PB-004-BRC-CONTROLLED-TESTNET",
            owner_market_regime_input_id="regime-test",
            admission_evidence_id="evidence-test",
            admission_rule_config_id="rules-v1",
            trial_constraint_snapshot_id="constraint-test",
            execution_mode=AdmissionExecutionMode.AUTO_WITHIN_BUDGET,
            constraints_snapshot_json={
                "status": "pending_risk_capital_resolution",
                "constraints_json": {
                    "source": "unavailable",
                    "trial_env": "testnet",
                    "trial_stage": "funded_validation",
                    "max_attempts": None,
                    "allowed_symbols": ["ETH/USDT:USDT"],
                },
            },
            created_at_ms=_now(),
        )
        self.binding = AdmissionTrialBinding(
            binding_id="binding-test",
            admission_decision_id="decision-test",
            owner_risk_acceptance_id="risk-acceptance-test",
            trial_constraint_snapshot_id="constraint-test",
            strategy_family_version_id="sfv-test",
            playbook_id="PB-004-BRC-CONTROLLED-TESTNET",
            playbook_catalog_snapshot_json={"id": "PB-004-BRC-CONTROLLED-TESTNET"},
            trial_env=TrialEnv.TESTNET,
            trial_stage=TrialStage.FUNDED_VALIDATION,
            execution_mode=AdmissionExecutionMode.AUTO_WITHIN_BUDGET,
            binding_status=AdmissionTrialBindingStatus.BINDING_RESERVED,
            created_by_operation_id="op-test",
            created_by_preflight_id="pre-test",
            created_at_ms=_now(),
            updated_at_ms=_now(),
        )

    async def list_strategy_families(self, *, limit: int = 100):
        return [self.family]

    async def create_strategy_family(self, **kwargs):
        return self.family

    async def get_strategy_family(self, strategy_family_id: str):
        return self.family

    async def create_strategy_family_version(self, **kwargs):
        return self.version

    async def sync_strategy_family_version_scope(self, strategy_family_version_id: str, **kwargs):
        self.version = self.version.model_copy(
            update={
                "supported_symbols": list(kwargs.get("supported_symbols") or []),
                "supported_timeframes": list(kwargs.get("supported_timeframes") or []),
            }
        )
        return self.version

    async def create_admission_evidence(self, **kwargs):
        return self.evidence

    async def create_owner_regime_input(self, **kwargs):
        return self.regime

    async def create_admission_request(self, **kwargs):
        return self.request

    async def get_admission_request(self, admission_request_id: str):
        return self.request

    async def evaluate(self, admission_request_id: str):
        return self.decision

    async def list_admission_decisions(self, *, limit: int = 100):
        return [self.decision]

    async def get_admission_decision(self, admission_decision_id: str):
        return self.decision

    async def create_owner_risk_acceptance(self, payload):
        raise AdmissionRuleViolation("owner risk acceptance requires installable trial constraints")

    async def list_admission_trial_bindings(self, *, limit: int = 100):
        return [self.binding]

    async def get_admission_trial_binding(self, binding_id: str):
        return self.binding


def test_brc_admission_api_routes_are_registered_without_trading_surface():
    from src.interfaces.api import app

    routes = {
        getattr(route, "path", "")
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/brc")
    }

    assert "/api/brc/strategy-families" in routes
    assert (
        "/api/brc/strategy-family-versions/{strategy_family_version_id}/scope-sync"
        in routes
    )
    assert "/api/brc/admissions/requests/{admission_request_id}/evaluate" in routes
    assert "/api/brc/admissions/risk-acceptances" in routes
    assert "/api/brc/admissions/trial-bindings" in routes
    assert "/api/brc/admissions/trial-bindings/{binding_id}" in routes
    assert "/api/brc/operations/preflight" in routes
    assert "/api/brc/admissions/create_gated_trial_from_admission" not in routes
    assert "/api/brc/admissions/install_runtime_constraints_from_admission_campaign" not in routes
    assert "/api/brc/admissions/prepare_runtime_carrier_from_admission_campaign" not in routes
    assert "/api/brc/admissions/prepare_runtime_start_from_admission_carrier" not in routes
    assert "/api/brc/admissions/evaluate_trial_trade_intent" not in routes
    assert "/api/brc/admissions/prepare_runtime_handoff_from_admission_campaign" not in routes
    assert "/api/brc/admissions/start_runtime_from_admission_handoff" not in routes
    assert "/api/brc/admissions/prepare_strategy_activation_from_admission_runtime" not in routes
    assert "/api/brc/admissions/activate_strategy_from_admission_runtime" not in routes
    assert "/api/brc/admissions/prepare_signal_loop_from_admission_strategy" not in routes
    assert "/api/brc/admissions/start_signal_loop_from_admission_strategy" not in routes
    assert "/api/brc/admissions/evaluate_signal_from_admission_strategy" not in routes
    assert "/api/brc/trial-trade-intents/orders" not in routes
    assert "/api/brc/execution-intents" not in routes
    assert "/api/brc/orders" not in routes
    assert "/api/brc/trade" not in routes
    assert "/api/brc/withdrawal" not in routes
    assert "/api/brc/transfer" not in routes


def test_brc_admission_create_and_evaluate_endpoints(monkeypatch):
    from src.interfaces import api as api_module
    from src.interfaces.api import app

    app.dependency_overrides[require_operator_session] = lambda: {"operator": "owner"}
    monkeypatch.setattr(api_module, "_brc_admission_service", _FakeAdmissionService())
    try:
        with TestClient(app) as client:
            families = client.get("/api/brc/strategy-families")
            assert families.status_code == 200
            assert families.json()[0]["strategy_family_id"] == "sf-test"

            scope_sync = client.post(
                "/api/brc/strategy-family-versions/sfv-test/scope-sync",
                json={
                    "supported_symbols": ["ETH/USDT:USDT", "SOL/USDT:USDT"],
                    "supported_timeframes": ["1h"],
                    "reason": "unit candidate universe scope sync",
                },
            )
            assert scope_sync.status_code == 200
            assert scope_sync.json()["supported_symbols"] == [
                "ETH/USDT:USDT",
                "SOL/USDT:USDT",
            ]

            request = client.post(
                "/api/brc/admissions/requests",
                json={
                    "strategy_family_version_id": "sfv-test",
                    "admission_evidence_id": "evidence-test",
                    "owner_market_regime_input_id": "regime-test",
                    "trial_env": "testnet",
                    "trial_stage": "funded_validation",
                    "account_facts_snapshot_ref": "acct-facts-1",
                },
            )
            assert request.status_code == 200
            assert request.json()["strategy_family_version_id"] == "sfv-test"

            decision = client.post("/api/brc/admissions/requests/admission-req-test/evaluate")
            assert decision.status_code == 200
            assert decision.json()["decision"] == "admit_with_constraints"
            assert (
                decision.json()["constraints_snapshot_json"]["status"]
                == "pending_risk_capital_resolution"
            )
            assert (
                decision.json()["constraints_snapshot_json"]["constraints_json"]["source"]
                == "unavailable"
            )

            detail = client.get("/api/brc/admissions/decisions/decision-test")
            assert detail.status_code == 200
            assert detail.json()["constraints_snapshot_json"]["constraints_json"]["allowed_symbols"] == [
                "ETH/USDT:USDT"
            ]

            acceptance = client.post(
                "/api/brc/admissions/risk-acceptances",
                json={
                    "admission_request_id": "admission-req-test",
                    "constraint_snapshot_id": "constraint-test",
                    "admission_decision_id": "decision-test",
                    "confirmation_phrase": "I ACCEPT BOUNDED FUNDED VALIDATION RISK",
                },
            )
            assert acceptance.status_code == 400
            assert "requires installable trial constraints" in acceptance.json()["message"]

            bindings = client.get("/api/brc/admissions/trial-bindings")
            assert bindings.status_code == 200
            assert bindings.json()[0]["binding_status"] == "binding_reserved"

            binding_detail = client.get("/api/brc/admissions/trial-bindings/binding-test")
            assert binding_detail.status_code == 200
            assert binding_detail.json()["campaign_id"] is None
            assert binding_detail.json()["runtime_carrier_id"] is None
    finally:
        app.dependency_overrides.pop(require_operator_session, None)
