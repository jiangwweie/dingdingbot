from __future__ import annotations

import json

from scripts.refresh_strategygroup_runtime_product_state_packets import refresh_packets


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def test_refresh_packets_writes_readmodel_packets_without_side_effects(tmp_path):
    calls = []
    payloads = {
        "/api/trading-console/strategy-group-live-facts-readiness": {
            "freshness_status": "fresh",
            "blockers": [],
            "warnings": [
                {"code": "strategy_group_candidate_prerequisites_pending"}
            ],
            "data": {
                "status": (
                    "strategy_group_observe_ready_candidate_prerequisites_pending"
                ),
                "blockers": [],
                "candidate_prepare_blockers": ["MPG-001:budget:missing"],
            },
        },
        "/api/trading-console/strategygroup-runtime-pilot-status": {
            "freshness_status": "warning",
            "blockers": [],
            "warnings": [{"code": "strategygroup_runtime_pilot_waiting_for_market"}],
            "data": {
                "status": "waiting_for_market",
                "watcher_scope_alignment": {"status": "expanded_scope"},
            },
        },
    }

    def opener(request, timeout):
        calls.append((request.full_url, timeout, request.headers.get("Cookie")))
        path = request.full_url.replace("http://unit", "")
        return _FakeResponse(payloads[path])

    packet = refresh_packets(
        api_base="http://unit",
        output_dir=tmp_path,
        label="unit",
        timeout_seconds=7,
        cookie="session=test",
        opener=opener,
        generated_at_ms=1,
    )

    assert packet["status"] == "refreshed"
    assert [item["status"] for item in packet["packets"]] == [
        "strategy_group_observe_ready_candidate_prerequisites_pending",
        "waiting_for_market",
    ]
    assert (tmp_path / "strategy-group-live-facts-readiness.json").exists()
    assert (tmp_path / "strategygroup-runtime-pilot-status.json").exists()
    assert all(call[1] == 7 for call in calls)
    assert all(call[2] == "session=test" for call in calls)
    assert packet["safety_invariants"] == {
        "readmodel_refresh_only": True,
        "exchange_write_called": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "execution_intent_created": False,
        "runtime_budget_mutated": False,
        "withdrawal_or_transfer_created": False,
        "places_order": False,
        "mutates_pg": False,
    }
