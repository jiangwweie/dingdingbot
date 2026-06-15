from __future__ import annotations

from scripts.bootstrap_strategygroup_runtime_pilot import (
    RuntimePilotBootstrapConfig,
    _runtime_rows_from_payload,
    _runtime_symbol,
    build_packet,
)


class _FakeClient:
    def __init__(self, active=None):
        self.calls: list[dict] = []
        self.active = active or []

    def request_json(self, method, path, *, query=None, body=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": dict(query or {}),
                "body": body,
            }
        )
        if path == "/api/trading-console/strategy-runtimes":
            return {"http_status": 200, "body": self.active}
        if (
            method == "GET"
            and "/strategy-families/" in path
            and not path.endswith("/versions")
        ):
            return {"http_status": 404, "body": {"detail": "not found"}, "error": True}
        if method == "GET" and "/strategy-family-versions/" in path:
            return {"http_status": 404, "body": {"detail": "not found"}, "error": True}
        if method == "POST" and path == "/api/brc/strategy-families":
            return {
                "http_status": 200,
                "body": {"strategy_family_id": body["strategy_family_id"]},
            }
        if method == "POST" and path.endswith("/versions"):
            return {
                "http_status": 200,
                "body": {
                    "strategy_family_version_id": body["strategy_family_version_id"]
                },
            }
        if path.endswith("/admissions/evidence-packets"):
            return {"http_status": 200, "body": {"evidence_packet_id": "evidence-1"}}
        if path.endswith("/admissions/owner-regime-inputs"):
            return {
                "http_status": 200,
                "body": {"owner_market_regime_input_id": "regime-1"},
            }
        if path.endswith("/admissions/requests"):
            return {"http_status": 200, "body": {"admission_request_id": "req-1"}}
        if path.endswith("/admissions/requests/req-1/evaluate"):
            return {
                "http_status": 200,
                "body": {
                    "admission_decision_id": "decision-1",
                    "trial_constraint_snapshot_id": "constraint-1",
                    "decision": "admit_with_constraints",
                },
            }
        if path.endswith("/admissions/risk-acceptances"):
            return {
                "http_status": 200,
                "body": {"owner_risk_acceptance_id": "risk-acceptance-1"},
            }
        if path.endswith("/operations/preflight"):
            return {
                "http_status": 200,
                "body": {
                    "operation_id": "operation-1",
                    "preflight_id": "preflight-1",
                    "idempotency_key": "idem-1",
                    "decision": "allow",
                    "risk_summary": {"blockers": []},
                },
            }
        if path.endswith("/operations/operation-1/confirm"):
            return {
                "http_status": 200,
                "body": {
                    "status": "executed",
                    "result_summary": {"binding_id": "binding-1"},
                },
            }
        if path.endswith("/strategy-runtime-profile-proposals"):
            return {
                "http_status": 200,
                "body": {
                    "status": "ready_for_owner_codex_confirmation",
                    "proposal_id": "proposal-1",
                    "strategy_family_id": "TEQ-001",
                    "strategy_family_version_id": "TEQ-001-v0",
                    "symbol": "INTC/USDT:USDT",
                    "side": "long",
                    "boundary": {"allowed_symbols": ["INTC/USDT:USDT"]},
                    "metadata": {},
                },
            }
        if path.endswith("/strategy-runtime-promotion-confirmations"):
            return {
                "http_status": 200,
                "body": {"confirmation": {"confirmation_id": "confirmation-1"}},
            }
        if path.endswith("/runtime-drafts"):
            return {
                "http_status": 200,
                "body": {"runtime": {"runtime_instance_id": "runtime-teq-1"}},
            }
        if path.endswith("/strategy-runtimes/runtime-teq-1/lifecycle"):
            return {
                "http_status": 200,
                "body": {
                    "runtime": {
                        "runtime_instance_id": "runtime-teq-1",
                        "status": "active",
                    }
                },
            }
        return {"http_status": 200, "body": {"status": "ok"}}


def _group(
    strategy_group_id: str,
    *,
    rank: int,
    default_mode: str = "armed_observation",
    side: str = "long",
    symbols: list[str] | None = None,
) -> dict:
    symbols = symbols or ["INTCUSDT", "MSTRUSDT"]
    return {
        "strategy_group_id": strategy_group_id,
        "name": f"{strategy_group_id} Pilot",
        "intake_status": (
            "observe_only_intake_ready"
            if default_mode == "observe_only"
            else "armed_observation_intake_ready"
        ),
        "supported_symbols": symbols,
        "supported_sides": [side],
        "signal_ready_rule": {"side": side},
        "risk_defaults": {
            "max_notional_per_action_usdt": "8",
            "max_leverage": "1",
        },
        "picker": {"rank": rank, "default_mode": default_mode},
    }


def _intake() -> dict:
    return {
        "status": "ready_for_main_control_intake",
        "strategy_picker": [
            _group("MPG-001", rank=1, symbols=["COINUSDT", "INTCUSDT"]),
            _group("TEQ-001", rank=2),
            _group("FBS-001", rank=3),
            _group("SOR-001", rank=4, side="short", symbols=["XAGUSDT", "XAUUSDT"]),
            _group("PMR-001", rank=5, default_mode="observe_only", side="short"),
        ],
    }


def _readiness() -> dict:
    rows = []
    for group in _intake()["strategy_picker"]:
        rows.append(
            {
                "strategy_group_id": group["strategy_group_id"],
                "readiness_status": "observe_ready_armed_candidate_blocked",
                "observe_ready": True,
                "armed_candidate_prepare_ready": False,
                "exchange_rules": {
                    "ready_symbols": list(group["supported_symbols"]),
                    "blocked_symbols": [],
                },
                "blockers": ["budget:missing"],
            }
        )
    return {"readiness": rows}


def test_runtime_symbol_normalizes_binance_usdt_to_runtime_symbol():
    assert _runtime_symbol("INTCUSDT") == "INTC/USDT:USDT"
    assert _runtime_symbol("XAUUSDT") == "XAU/USDT:USDT"
    assert _runtime_symbol("COIN/USDT:USDT") == "COIN/USDT:USDT"


def test_runtime_rows_from_payload_accepts_watcher_status_packet_shape():
    rows = _runtime_rows_from_payload(
        {
            "active_runtime_count": 2,
            "runtime_signal_summaries": [
                {
                    "runtime_instance_id": "runtime-mpg-1",
                    "strategy_family_id": "MPG-001",
                    "symbol": "COIN/USDT:USDT",
                    "side": "long",
                }
            ],
        }
    )

    assert rows == [
        {
            "runtime_instance_id": "runtime-mpg-1",
            "strategy_family_id": "MPG-001",
            "symbol": "COIN/USDT:USDT",
            "side": "long",
        }
    ]


def test_plan_skips_existing_group_and_observe_only_by_default():
    packet = build_packet(
        config=RuntimePilotBootstrapConfig(
            execute=False,
            max_symbols_per_group=1,
            max_total_new_runtimes=4,
        ),
        intake_packet=_intake(),
        live_facts_readiness=_readiness(),
        active_runtimes=[
            {
                "runtime_instance_id": "runtime-mpg-coin",
                "strategy_family_id": "MPG-001",
                "strategy_family_version_id": "MPG-001-v0",
                "symbol": "COIN/USDT:USDT",
                "side": "long",
                "status": "active",
            }
        ],
    )

    assert packet["status"] == "planned_runtime_bootstrap"
    assert [item["strategy_group_id"] for item in packet["targets"]] == [
        "TEQ-001",
        "FBS-001",
        "SOR-001",
    ]
    assert packet["targets"][0]["symbol"] == "INTC/USDT:USDT"
    assert packet["targets"][2]["symbol"] == "XAG/USDT:USDT"
    assert packet["targets"][2]["side"] == "short"
    skipped = {item["strategy_group_id"]: item for item in packet["skipped"]}
    assert skipped["MPG-001"]["reason"] == "strategy_group_already_has_active_runtime"
    assert skipped["PMR-001"]["reason"].startswith("mode_not_bootstrappable")
    assert packet["safety_invariants"]["plan_only"] is True
    assert packet["safety_invariants"]["creates_runtime_records"] is False
    assert packet["safety_invariants"]["creates_order"] is False


def test_execute_creates_shadow_runtime_without_submit_paths():
    client = _FakeClient()
    packet = build_packet(
        config=RuntimePilotBootstrapConfig(
            api_base="http://unit",
            execute=True,
            strategy_group_ids=("TEQ-001",),
            account_facts_source="static",
        ),
        intake_packet={"strategy_picker": [_group("TEQ-001", rank=1)]},
        live_facts_readiness={
            "readiness": [
                {
                    "strategy_group_id": "TEQ-001",
                    "observe_ready": True,
                    "readiness_status": "observe_ready_armed_candidate_blocked",
                    "exchange_rules": {"ready_symbols": ["INTCUSDT"]},
                }
            ]
        },
        active_runtimes=[],
        client=client,
    )

    assert packet["status"] == "executed_runtime_bootstrap"
    assert packet["runtime_scope"]["new_runtime_instance_ids"] == ["runtime-teq-1"]
    assert packet["safety_invariants"]["mutates_pg_only_for_runtime_admission"] is True
    assert packet["safety_invariants"]["creates_candidate"] is False
    assert packet["safety_invariants"]["creates_execution_intent"] is False
    assert packet["safety_invariants"]["creates_order"] is False
    paths = [call["path"] for call in client.calls]
    assert not any("first-real-submit-actions" in path for path in paths)
    assert not any("exchange-submit" in path for path in paths)
    assert not any("order-candidates" in path for path in paths)


def test_execute_blocks_when_active_inventory_is_unavailable():
    packet = build_packet(
        config=RuntimePilotBootstrapConfig(execute=True),
        intake_packet=_intake(),
        live_facts_readiness=_readiness(),
        active_runtimes=[],
        active_inventory_blockers=["active_runtime_inventory_unavailable:URLError"],
    )

    assert packet["status"] == "blocked_active_runtime_inventory_unavailable"
    assert packet["executions"] == []
    assert "active_runtime_inventory_unavailable:URLError" in packet["blockers"]
