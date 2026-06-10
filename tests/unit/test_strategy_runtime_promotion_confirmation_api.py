from __future__ import annotations

import time

from fastapi.testclient import TestClient

from src.domain.experimental_runtime_profile_proposal import (
    build_experimental_runtime_profile_proposal,
)
from src.domain.strategy_runtime import (
    StrategyRuntimeBoundary,
    StrategyRuntimeInstance,
    StrategyRuntimeInstanceStatus,
    StrategyRuntimePolicySnapshot,
)
from src.interfaces.operator_auth import create_password_hash


NOW_MS = 1781000000000


def _configure_auth(monkeypatch):
    import src.interfaces.api  # noqa: F401

    monkeypatch.setenv("BRC_OPERATOR_USERNAME", "owner")
    monkeypatch.setenv("BRC_OPERATOR_PASSWORD_HASH", create_password_hash("pw"))
    monkeypatch.setenv("BRC_OPERATOR_TOTP_SECRET", "JBSWY3DPEHPK3PXP")
    monkeypatch.setenv("BRC_OPERATOR_SESSION_SECRET", "session-secret-for-unit-test")


def _totp() -> str:
    from src.interfaces.operator_auth import _hotp

    return _hotp("JBSWY3DPEHPK3PXP", int(time.time() // 30))


def _login(client: TestClient):
    return client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "pw", "totp_code": _totp()},
    )


class _FakePromotionConfirmationRepo:
    def __init__(self) -> None:
        self.records = []

    async def initialize(self) -> None:
        return None

    async def append(self, record):
        self.records.append(record)
        return record

    async def get(self, confirmation_id):
        for record in self.records:
            if record.confirmation_id == confirmation_id:
                return record
        return None

    async def list(
        self,
        *,
        runtime_instance_id=None,
        strategy_family_id=None,
        strategy_family_version_id=None,
        scope=None,
        limit=50,
    ):
        records = [
            record
            for record in self.records
            if (
                runtime_instance_id is None
                or record.runtime_instance_id == runtime_instance_id
            )
            and (
                strategy_family_id is None
                or record.strategy_family_id == strategy_family_id
            )
            and (
                strategy_family_version_id is None
                or record.strategy_family_version_id == strategy_family_version_id
            )
            and (scope is None or record.scope == scope)
        ]
        return list(reversed(records))[:limit]


class _FakeRuntimeDraftService:
    def __init__(self) -> None:
        self.calls = []
        self.lifecycle_calls = []

    async def create_draft_from_profile_confirmation(
        self,
        trial_binding_id,
        *,
        confirmation,
        carrier_id=None,
        expires_at_ms=None,
        metadata=None,
    ):
        self.calls.append(
            {
                "trial_binding_id": trial_binding_id,
                "confirmation_id": confirmation.confirmation_id,
                "carrier_id": carrier_id,
                "expires_at_ms": expires_at_ms,
                "metadata": metadata or {},
            }
        )
        proposal = confirmation.runtime_profile_proposal_snapshot
        return StrategyRuntimeInstance(
            runtime_instance_id="strategy-runtime-api-profile-1",
            trial_binding_id=trial_binding_id,
            admission_decision_id="decision-api-profile-1",
            strategy_family_id=confirmation.strategy_family_id,
            strategy_family_version_id=confirmation.strategy_family_version_id,
            owner_risk_acceptance_id="risk-api-profile-1",
            carrier_id=carrier_id,
            symbol=proposal.symbol,
            side=proposal.side,
            status=StrategyRuntimeInstanceStatus.DRAFT,
            boundary=StrategyRuntimeBoundary.model_validate(
                proposal.boundary.model_dump(mode="python")
            ),
            policy_snapshot=StrategyRuntimePolicySnapshot(
                source="runtime_profile_promotion_confirmation"
            ),
            execution_enabled=False,
            shadow_mode=True,
            created_at_ms=NOW_MS,
            updated_at_ms=NOW_MS,
            expires_at_ms=expires_at_ms,
            metadata={
                "confirmation_id": confirmation.confirmation_id,
                "creates_execution_intent": False,
                "order_created": False,
                "exchange_called": False,
            },
        )

    async def activate_runtime(self, runtime_instance_id, *, actor="owner"):
        self.lifecycle_calls.append(
            {"action": "activate_shadow", "runtime_instance_id": runtime_instance_id, "actor": actor}
        )
        return self._runtime(runtime_instance_id, StrategyRuntimeInstanceStatus.ACTIVE)

    async def pause_runtime(self, runtime_instance_id, *, actor="owner"):
        self.lifecycle_calls.append(
            {"action": "pause_shadow", "runtime_instance_id": runtime_instance_id, "actor": actor}
        )
        return self._runtime(runtime_instance_id, StrategyRuntimeInstanceStatus.PAUSED)

    async def revoke_runtime(self, runtime_instance_id, *, actor="owner"):
        self.lifecycle_calls.append(
            {"action": "revoke_shadow", "runtime_instance_id": runtime_instance_id, "actor": actor}
        )
        return self._runtime(runtime_instance_id, StrategyRuntimeInstanceStatus.REVOKED)

    def _runtime(self, runtime_instance_id, status):
        return StrategyRuntimeInstance(
            runtime_instance_id=runtime_instance_id,
            trial_binding_id="binding-api-profile-1",
            admission_decision_id="decision-api-profile-1",
            strategy_family_id="CPM-RO-001",
            strategy_family_version_id="CPM-RO-001-v0",
            owner_risk_acceptance_id="risk-api-profile-1",
            carrier_id="carrier-api-profile-1",
            symbol="BNB/USDT:USDT",
            side="long",
            status=status,
            boundary=StrategyRuntimeBoundary(
                max_attempts=3,
                max_active_positions=1,
                max_notional_per_attempt="10.00",
                total_budget="9.00",
                allowed_symbols=["BNB/USDT:USDT"],
                allowed_sides=["long"],
                max_leverage="1",
                max_margin_per_attempt="10.00",
                min_liquidation_stop_buffer="25",
                requires_protection=True,
                requires_review=True,
            ),
            policy_snapshot=StrategyRuntimePolicySnapshot(
                source="runtime_profile_promotion_confirmation"
            ),
            execution_enabled=False,
            shadow_mode=True,
            created_at_ms=NOW_MS,
            updated_at_ms=NOW_MS,
            metadata={
                "creates_signal_evaluation": False,
                "creates_order_candidate": False,
                "creates_execution_intent": False,
                "order_created": False,
                "exchange_called": False,
            },
        )


def _semantic_confirmed() -> dict:
    return {
        "strategy_family_confirmed": True,
        "implementation_source_confirmed": True,
        "required_facts_confirmed": True,
        "entry_policy_confirmed": True,
        "exit_policy_confirmed": True,
        "protection_policy_confirmed": True,
        "eligible_for_runtime_execution_confirmed": True,
        "right_tail_review_metrics_confirmed": True,
    }


def _runtime_confirmed() -> dict:
    return {
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
    }


def test_promotion_confirmation_api_records_gate_snapshot_without_action(monkeypatch):
    _configure_auth(monkeypatch)
    repo = _FakePromotionConfirmationRepo()
    from src.interfaces import api_brc_console

    monkeypatch.setattr(
        api_brc_console,
        "_strategy_runtime_promotion_confirmation_repository",
        lambda: repo,
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.post(
            "/api/brc/strategy-runtime-promotion-confirmations",
            json={
                "confirmation_id": "promotion-confirmation-api-1",
                "runtime_instance_id": "runtime-cpm-api-1",
                "strategy_family_id": "CPM-RO-001",
                "strategy_family_version_id": "CPM-RO-001-v0",
                "semantic_confirmations": _semantic_confirmed(),
                "runtime_confirmations": _runtime_confirmed(),
                "reason": "Owner confirms bounded 30U experimental capital semantics.",
                "evidence_refs": ["owner-note://promotion-confirmation-api-1"],
                "created_at_ms": NOW_MS,
                "metadata": {"source": "api-unit-test"},
            },
        )
        listed = client.get(
            "/api/brc/strategy-runtime-promotion-confirmations"
            "?runtime_instance_id=runtime-cpm-api-1"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["confirmation"]["confirmation_id"] == "promotion-confirmation-api-1"
    assert payload["confirmation"]["recorded_by"] == "owner"
    assert (
        payload["promotion_gate_result"]["status"]
        == "ready_for_controlled_runtime_execution_design"
    )
    assert payload["confirmation"]["not_execution_authority"] is True
    assert payload["confirmation"]["execution_intent_created"] is False
    assert payload["confirmation"]["order_created"] is False
    assert payload["confirmation"]["exchange_called"] is False
    assert payload["confirmation"]["owner_bounded_execution_called"] is False
    assert payload["confirmation"]["order_lifecycle_called"] is False
    assert payload["confirmation"]["runtime_mutation_created"] is False
    assert payload["no_action_guarantee"]["creates_order"] is False
    assert listed.status_code == 200
    assert listed.json()["confirmations"][0]["confirmation_id"] == (
        "promotion-confirmation-api-1"
    )


def test_promotion_confirmation_api_records_profile_proposal_snapshot(monkeypatch):
    _configure_auth(monkeypatch)
    repo = _FakePromotionConfirmationRepo()
    from src.interfaces import api_brc_console

    monkeypatch.setattr(
        api_brc_console,
        "_strategy_runtime_promotion_confirmation_repository",
        lambda: repo,
    )
    from src.interfaces.api import app

    profile_proposal = build_experimental_runtime_profile_proposal(
        strategy_family_id="BRF-001",
        strategy_family_version_id="BRF-001-v0",
        symbol="BNB/USDT:USDT",
        side="short",
    )

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.post(
            "/api/brc/strategy-runtime-promotion-confirmations",
            json={
                "confirmation_id": "promotion-confirmation-api-profile-1",
                "strategy_family_id": "BRF-001",
                "strategy_family_version_id": "BRF-001-v0",
                "semantic_confirmations": _semantic_confirmed(),
                "runtime_confirmations": {
                    **_runtime_confirmed(),
                    "short_side_conservative_profile_confirmed": True,
                },
                "runtime_profile_proposal_snapshot": profile_proposal.model_dump(
                    mode="json"
                ),
                "reason": "Owner confirms BRF conservative 30U proposal snapshot.",
                "evidence_refs": ["runtime-profile-proposal://BRF-001-v0"],
                "created_at_ms": NOW_MS,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    snapshot = payload["confirmation"]["runtime_profile_proposal_snapshot"]
    assert snapshot["strategy_family_id"] == "BRF-001"
    assert snapshot["profile_kind"] == "small_capital_conservative_short"
    assert snapshot["total_loss_budget"] == "6.00"
    assert snapshot["not_execution_authority"] is True
    assert snapshot["order_created"] is False
    assert payload["confirmation"]["metadata"]["runtime_profile_proposal_attached"] is True
    assert payload["confirmation"]["runtime_mutation_created"] is False
    assert payload["no_action_guarantee"]["creates_order"] is False
    assert repo.records[0].runtime_profile_proposal_snapshot is not None


def test_promotion_confirmation_api_creates_shadow_runtime_draft(monkeypatch):
    _configure_auth(monkeypatch)
    repo = _FakePromotionConfirmationRepo()
    runtime_service = _FakeRuntimeDraftService()
    from src.interfaces import api_brc_console

    monkeypatch.setattr(
        api_brc_console,
        "_strategy_runtime_promotion_confirmation_repository",
        lambda: repo,
    )
    from src.interfaces import api as api_module

    monkeypatch.setattr(
        api_module,
        "_strategy_runtime_service",
        runtime_service,
        raising=False,
    )
    from src.interfaces.api import app

    confirmation = api_brc_console.StrategyRuntimePromotionGateConfirmationRecord(
        confirmation_id="promotion-confirmation-api-runtime-draft-1",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        semantic_confirmations=_semantic_confirmed(),
        runtime_confirmations=_runtime_confirmed(),
        runtime_profile_proposal_snapshot=build_experimental_runtime_profile_proposal(
            strategy_family_id="CPM-RO-001",
            strategy_family_version_id="CPM-RO-001-v0",
            symbol="BNB/USDT:USDT",
            side="long",
        ),
        reason="Owner/Codex confirms CPM runtime profile proposal.",
        created_at_ms=NOW_MS,
    )
    repo.records.append(confirmation)

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.post(
            "/api/brc/strategy-runtime-promotion-confirmations/"
            "promotion-confirmation-api-runtime-draft-1/runtime-drafts",
            json={
                "trial_binding_id": "binding-cpm-api-profile-1",
                "carrier_id": "carrier-cpm-api-profile-1",
                "expires_at_ms": NOW_MS + 60000,
                "metadata": {"source": "api-unit-test"},
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["confirmation_id"] == (
        "promotion-confirmation-api-runtime-draft-1"
    )
    assert payload["runtime"]["runtime_instance_id"] == "strategy-runtime-api-profile-1"
    assert payload["runtime"]["execution_enabled"] is False
    assert payload["runtime"]["shadow_mode"] is True
    assert payload["runtime"]["boundary"]["total_budget"] == "9.00"
    assert payload["runtime"]["metadata"]["creates_execution_intent"] is False
    assert payload["runtime"]["metadata"]["order_created"] is False
    assert payload["runtime"]["metadata"]["exchange_called"] is False
    assert payload["no_action_guarantee"]["creates_execution_intent"] is False
    assert payload["no_action_guarantee"]["creates_order"] is False
    assert runtime_service.calls[0]["trial_binding_id"] == "binding-cpm-api-profile-1"
    assert runtime_service.calls[0]["metadata"]["created_by"] == "owner"
    assert runtime_service.calls[0]["metadata"]["non_executing_record"] is True


def test_strategy_runtime_lifecycle_api_keeps_shadow_no_action(monkeypatch):
    _configure_auth(monkeypatch)
    runtime_service = _FakeRuntimeDraftService()
    from src.interfaces import api as api_module

    monkeypatch.setattr(
        api_module,
        "_strategy_runtime_service",
        runtime_service,
        raising=False,
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.post(
            "/api/brc/strategy-runtimes/strategy-runtime-api-profile-1/lifecycle",
            json={"action": "activate_shadow"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "activate_shadow"
    assert payload["runtime"]["status"] == "active"
    assert payload["runtime"]["execution_enabled"] is False
    assert payload["runtime"]["shadow_mode"] is True
    assert payload["runtime"]["metadata"]["creates_signal_evaluation"] is False
    assert payload["runtime"]["metadata"]["creates_order_candidate"] is False
    assert payload["runtime"]["metadata"]["creates_execution_intent"] is False
    assert payload["runtime"]["metadata"]["order_created"] is False
    assert payload["runtime"]["metadata"]["exchange_called"] is False
    assert payload["no_action_guarantee"]["creates_signal_evaluation"] is False
    assert payload["no_action_guarantee"]["creates_order_candidate"] is False
    assert payload["no_action_guarantee"]["creates_execution_intent"] is False
    assert payload["no_action_guarantee"]["creates_order"] is False
    assert payload["no_action_guarantee"]["calls_exchange"] is False
    assert payload["no_action_guarantee"]["mutates_shadow_runtime_status"] is True
    assert runtime_service.lifecycle_calls == [
        {
            "action": "activate_shadow",
            "runtime_instance_id": "strategy-runtime-api-profile-1",
            "actor": "owner",
        }
    ]


def test_promotion_confirmation_api_rejects_execution_metadata(monkeypatch):
    _configure_auth(monkeypatch)
    repo = _FakePromotionConfirmationRepo()
    from src.interfaces import api_brc_console

    monkeypatch.setattr(
        api_brc_console,
        "_strategy_runtime_promotion_confirmation_repository",
        lambda: repo,
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        response = client.post(
            "/api/brc/strategy-runtime-promotion-confirmations",
            json={
                "confirmation_id": "promotion-confirmation-api-forbidden",
                "strategy_family_id": "CPM-RO-001",
                "strategy_family_version_id": "CPM-RO-001-v0",
                "semantic_confirmations": _semantic_confirmed(),
                "runtime_confirmations": _runtime_confirmed(),
                "reason": "Forbidden execution metadata must be rejected.",
                "created_at_ms": NOW_MS,
                "metadata": {"nested": {"exchange_order_id": "forbidden"}},
            },
        )

    assert response.status_code == 400
    assert "forbidden execution field" in response.json()["message"]
    assert repo.records == []


def test_promotion_confirmation_api_returns_503_when_repository_unavailable(
    monkeypatch,
):
    _configure_auth(monkeypatch)
    from src.interfaces import api_brc_console

    def unavailable_repo():
        raise ValueError("PG_DATABASE_URL missing")

    monkeypatch.setattr(
        api_brc_console,
        "_strategy_runtime_promotion_confirmation_repository",
        unavailable_repo,
    )
    from src.interfaces.api import app

    with TestClient(app) as client:
        assert _login(client).status_code == 200
        post_response = client.post(
            "/api/brc/strategy-runtime-promotion-confirmations",
            json={
                "confirmation_id": "promotion-confirmation-api-unavailable",
                "strategy_family_id": "CPM-RO-001",
                "strategy_family_version_id": "CPM-RO-001-v0",
                "semantic_confirmations": _semantic_confirmed(),
                "runtime_confirmations": _runtime_confirmed(),
                "reason": "Repository unavailable should fail closed.",
                "created_at_ms": NOW_MS,
            },
        )
        get_response = client.get(
            "/api/brc/strategy-runtime-promotion-confirmations"
            "?runtime_instance_id=runtime-cpm-api-1"
        )

    assert post_response.status_code == 503
    assert get_response.status_code == 503
    assert "repository unavailable" in post_response.json()["message"]
    assert "repository unavailable" in get_response.json()["message"]
