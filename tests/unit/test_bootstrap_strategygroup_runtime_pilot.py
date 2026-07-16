from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text

from scripts import bootstrap_strategygroup_runtime_pilot as bootstrap
from scripts.bootstrap_strategygroup_runtime_pilot import (
    PG_SOURCE_REF,
    RuntimePilotBootstrapConfig,
    _bootstrap_config,
    _runtime_symbol,
    build_artifact,
)
from tests.support.runtime_control_state_schema import seed_runtime_control_state

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
)
SEED_PATH = REPO_ROOT / "scripts/seed_runtime_control_state_foundation.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _seed_runtime_control_state_db(tmp_path: Path) -> str:
    migration = _load_module(MIGRATION_PATH, "migration_086_bootstrap_runtime")
    seed = _load_module(SEED_PATH, "seed_runtime_control_state_bootstrap_runtime")
    database_url = f"sqlite:///{tmp_path / 'runtime-control-state.db'}"
    engine = create_engine(database_url)
    with engine.begin() as conn:
        old_op = migration.op
        migration.op = Operations(MigrationContext.configure(conn))
        try:
            migration.upgrade()
        finally:
            migration.op = old_op
        seed_runtime_control_state(conn)
    engine.dispose()
    return database_url


def _mutate_runtime_control_state_db(database_url: str, statement: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text(statement))
    engine.dispose()


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
                    "admission_result": "admit_with_constraints",
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
                    "preflight_result": "allow",
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


def test_plan_skips_existing_group_and_observe_only_by_default():
    artifact = build_artifact(
        config=RuntimePilotBootstrapConfig(
            execute=False,
            max_symbols_per_group=1,
            max_total_new_runtimes=4,
        ),
        intake_artifact=_intake(),
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

    assert artifact["status"] == "planned_runtime_bootstrap"
    assert [item["strategy_group_id"] for item in artifact["targets"]] == [
        "TEQ-001",
        "FBS-001",
        "SOR-001",
    ]
    assert artifact["targets"][0]["symbol"] == "INTC/USDT:USDT"
    assert artifact["targets"][2]["symbol"] == "XAG/USDT:USDT"
    assert artifact["targets"][2]["side"] == "short"
    skipped = {item["strategy_group_id"]: item for item in artifact["skipped"]}
    assert skipped["MPG-001"]["reason"] == "strategy_group_already_has_active_runtime"
    assert skipped["PMR-001"]["reason"].startswith("mode_not_bootstrappable")
    assert artifact["safety_invariants"]["plan_only"] is True
    assert artifact["safety_invariants"]["creates_runtime_records"] is False
    assert artifact["safety_invariants"]["creates_order"] is False


def test_candidate_pool_side_overrides_legacy_handoff_side():
    candidate_pool = {
        "status": "strategy_live_candidate_pool_ready",
        "candidate_universe": {"SOR-001": ["ETHUSDT"]},
        "symbol_readiness_rows": [
            {
                "strategy_group_id": "SOR-001",
                "symbol": "ETHUSDT",
                "side": "long",
            }
        ],
        "candidate_rows": [
            {
                "strategy_group_id": "SOR-001",
                "side": "long",
                "daily_rank": 1,
            }
        ],
    }

    artifact = build_artifact(
        config=RuntimePilotBootstrapConfig(
            execute=False,
            strategy_group_ids=("SOR-001",),
            max_symbols_per_group=1,
            max_total_new_runtimes=1,
            candidate_universe_source="candidate-pool.json",
        ),
        intake_artifact=_intake(),
        live_facts_readiness={
            "readiness": [
                {
                    "strategy_group_id": "SOR-001",
                    "observe_ready": True,
                    "readiness_status": "candidate_universe_runtime_scope_ready",
                    "exchange_rules": {"ready_symbols": ["ETHUSDT"]},
                }
            ]
        },
        active_runtimes=[],
        candidate_pool=candidate_pool,
    )

    assert artifact["status"] == "planned_runtime_bootstrap"
    assert len(artifact["targets"]) == 1
    assert artifact["targets"][0]["strategy_group_id"] == "SOR-001"
    assert artifact["targets"][0]["exchange_symbol"] == "ETHUSDT"
    assert artifact["targets"][0]["side"] == "long"


def test_candidate_pool_lane_universe_bootstraps_missing_side_even_when_group_active():
    candidate_pool = {
        "status": "strategy_live_candidate_pool_ready",
        "candidate_universe": {"MPG-001": ["OPUSDT"]},
        "candidate_lane_universe": {"MPG-001": ["OPUSDT:long", "OPUSDT:short"]},
        "candidate_rows": [
            {"strategy_group_id": "MPG-001", "daily_rank": 1, "side": "long"},
        ],
        "symbol_readiness_rows": [
            {"strategy_group_id": "MPG-001", "symbol": "OPUSDT", "side": "long"},
            {"strategy_group_id": "MPG-001", "symbol": "OPUSDT", "side": "short"},
        ],
    }

    artifact = build_artifact(
        config=RuntimePilotBootstrapConfig(
            execute=False,
            strategy_group_ids=("MPG-001",),
            max_symbols_per_group=4,
            max_total_new_runtimes=4,
            candidate_universe_source="candidate-pool.json",
        ),
        intake_artifact=_intake(),
        live_facts_readiness={
            "readiness": [
                {
                    "strategy_group_id": "MPG-001",
                    "observe_ready": True,
                    "readiness_status": "candidate_universe_runtime_scope_ready",
                    "exchange_rules": {"ready_symbols": ["OPUSDT"]},
                }
            ]
        },
        active_runtimes=[
            {
                "runtime_instance_id": "runtime-mpg-op-long",
                "strategy_family_id": "MPG-001",
                "strategy_family_version_id": "MPG-001-v0",
                "symbol": "OP/USDT:USDT",
                "side": "long",
                "status": "active",
            }
        ],
        candidate_pool=candidate_pool,
    )

    assert [
        (item["strategy_group_id"], item["exchange_symbol"], item["side"])
        for item in artifact["targets"]
    ] == [("MPG-001", "OPUSDT", "short")]
    skipped = {
        (item["strategy_group_id"], item["exchange_symbol"], item["side"]): item
        for item in artifact["skipped"]
    }
    assert skipped[("MPG-001", "OPUSDT", "long")]["reason"] == (
        "runtime_already_active_for_group_symbol_side"
    )


def test_plan_can_renew_exhausted_runtime_attempts_under_standing_authorization():
    artifact = build_artifact(
        config=RuntimePilotBootstrapConfig(
            execute=False,
            strategy_group_ids=("TEQ-001",),
            renew_exhausted_runtimes=True,
            max_symbols_per_group=1,
            max_total_new_runtimes=1,
        ),
        intake_artifact={"strategy_picker": [_group("TEQ-001", rank=1)]},
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
        active_runtimes=[
            {
                "runtime_instance_id": "runtime-teq-exhausted",
                "strategy_family_id": "TEQ-001",
                "strategy_family_version_id": "TEQ-001-v0",
                "symbol": "INTC/USDT:USDT",
                "side": "long",
                "status": "active",
                "attempts_remaining": 0,
            }
        ],
    )

    assert artifact["status"] == "planned_runtime_bootstrap"
    assert len(artifact["targets"]) == 1
    target = artifact["targets"][0]
    assert target["strategy_group_id"] == "TEQ-001"
    assert target["reason"] == (
        "runtime_attempts_exhausted_renewal_ready_for_runtime_bootstrap"
    )
    assert target["renewal_of_runtime_instance_id"] == "runtime-teq-exhausted"
    assert artifact["safety_invariants"]["creates_candidate"] is False
    assert artifact["safety_invariants"]["creates_execution_intent"] is False
    assert artifact["safety_invariants"]["creates_order"] is False


def test_bootstrap_config_uses_lane_specific_policy_risk_defaults():
    config = _bootstrap_config(
        config=RuntimePilotBootstrapConfig(),
        group={
            "strategy_group_id": "MPG-001",
            "name": "MPG",
            "supported_symbols": ["OPUSDT"],
            "risk_defaults": {
                "max_notional_per_action_usdt": "8",
                "max_leverage": "1",
            },
            "risk_defaults_by_lane": {
                "OPUSDT:long": {
                    "max_notional_per_action_usdt": "13",
                    "max_leverage": "3",
                }
            },
        },
        symbol="OPUSDT",
        side="long",
    )

    assert str(config.max_notional) == "13"
    assert config.max_leverage == 3


def test_plan_can_use_candidate_pool_universe_instead_of_legacy_picker_scope():
    candidate_pool = {
        "status": "strategy_live_candidate_pool_ready",
        "candidate_universe": {
            "CPM-RO-001": ["ETHUSDT", "SOLUSDT"],
            "MPG-001": ["OPUSDT"],
            "SOR-001": ["ETHUSDT"],
            "BRF2-001": [
                "BTCUSDT",
                "brf2_research_supported_symbols_only",
            ],
        },
        "candidate_rows": [
            {"strategy_group_id": "MPG-001", "daily_rank": 1, "side": "long"},
            {"strategy_group_id": "CPM-RO-001", "daily_rank": 2, "side": "long"},
            {"strategy_group_id": "SOR-001", "daily_rank": 3, "side": "long"},
            {"strategy_group_id": "BRF2-001", "daily_rank": 4, "side": "short"},
        ],
        "symbol_readiness_rows": [
            {"strategy_group_id": "CPM-RO-001", "symbol": "ETHUSDT", "side": "long"},
            {"strategy_group_id": "CPM-RO-001", "symbol": "SOLUSDT", "side": "long"},
            {"strategy_group_id": "MPG-001", "symbol": "OPUSDT", "side": "long"},
            {"strategy_group_id": "SOR-001", "symbol": "ETHUSDT", "side": "long"},
            {"strategy_group_id": "BRF2-001", "symbol": "BTCUSDT", "side": "short"},
        ],
    }

    artifact = build_artifact(
        config=RuntimePilotBootstrapConfig(
            execute=False,
            include_observe_only=True,
            max_symbols_per_group=4,
            max_total_new_runtimes=10,
            candidate_universe_source="candidate-pool.json",
        ),
        intake_artifact=_intake(),
        live_facts_readiness={
            "readiness": [
                {
                    "strategy_group_id": strategy_group_id,
                    "observe_ready": True,
                    "readiness_status": "candidate_universe_runtime_scope_ready",
                    "exchange_rules": {"ready_symbols": symbols},
                }
                for strategy_group_id, symbols in {
                    "CPM-RO-001": ["ETHUSDT", "SOLUSDT"],
                    "MPG-001": ["OPUSDT"],
                    "SOR-001": ["ETHUSDT"],
                    "BRF2-001": ["BTCUSDT"],
                }.items()
            ]
        },
        active_runtimes=[],
        candidate_pool=candidate_pool,
    )

    target_keys = [
        (item["strategy_group_id"], item["exchange_symbol"], item["side"])
        for item in artifact["targets"]
    ]
    assert target_keys == [
        ("MPG-001", "OPUSDT", "long"),
        ("CPM-RO-001", "ETHUSDT", "long"),
        ("CPM-RO-001", "SOLUSDT", "long"),
        ("SOR-001", "ETHUSDT", "long"),
        ("BRF2-001", "BTCUSDT", "short"),
    ]
    assert not any("RESEARCH" in item["exchange_symbol"] for item in artifact["targets"])
    assert artifact["runtime_scope"]["candidate_universe_source"] == "candidate-pool.json"
    assert artifact["runtime_scope"]["candidate_universe_symbol_count"] == 5
    assert artifact["safety_invariants"]["creates_candidate"] is False
    assert artifact["safety_invariants"]["creates_execution_intent"] is False
    assert artifact["safety_invariants"]["creates_order"] is False


def test_execute_creates_shadow_runtime_without_submit_paths():
    client = _FakeClient()
    artifact = build_artifact(
        config=RuntimePilotBootstrapConfig(
            api_base="http://unit",
            execute=True,
            strategy_group_ids=("TEQ-001",),
            account_facts_source="static",
        ),
        intake_artifact={"strategy_picker": [_group("TEQ-001", rank=1)]},
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

    assert artifact["status"] == "executed_runtime_bootstrap"
    assert artifact["runtime_scope"]["new_runtime_instance_ids"] == ["runtime-teq-1"]
    assert artifact["safety_invariants"]["mutates_pg_only_for_runtime_admission"] is True
    assert artifact["safety_invariants"]["creates_candidate"] is False
    assert artifact["safety_invariants"]["creates_execution_intent"] is False
    assert artifact["safety_invariants"]["creates_order"] is False
    paths = [call["path"] for call in client.calls]
    assert not any("first-real-submit-actions" in path for path in paths)
    assert not any("exchange-submit" in path for path in paths)
    assert not any("order-candidates" in path for path in paths)
    assert all(
        "decision" not in step
        for execution in artifact["executions"]
        for step in execution["report"]["steps"]
    )


def test_execute_blocks_when_active_inventory_is_unavailable():
    artifact = build_artifact(
        config=RuntimePilotBootstrapConfig(execute=True),
        intake_artifact=_intake(),
        live_facts_readiness=_readiness(),
        active_runtimes=[],
        active_inventory_blockers=["active_runtime_inventory_unavailable:URLError"],
    )

    assert artifact["status"] == "blocked_active_runtime_inventory_unavailable"
    assert artifact["executions"] == []
    assert "active_runtime_inventory_unavailable:URLError" in artifact["blockers"]


def test_cli_requires_pg_runtime_control_state(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)

    result = bootstrap.main([])

    assert result == 2
    assert "PG_DATABASE_URL is required for PG-only runtime bootstrap" in (
        capsys.readouterr().err
    )


def test_cli_execute_requires_database_url(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)

    result = bootstrap.main(
        [
            "--execute",
        ]
    )

    assert result == 2
    assert "PG_DATABASE_URL is required for PG-only runtime bootstrap" in (
        capsys.readouterr().err
    )


def test_cli_rejects_removed_local_diagnostic_flag(tmp_path, capsys):
    database_url = _seed_runtime_control_state_db(tmp_path)
    removed_flag = "--allow-" + "local-file-diagnostic"

    with pytest.raises(SystemExit) as exc:
        bootstrap.main(
            [
                "--database-url",
                database_url,
                "--allow-non-postgres-for-test",
                removed_flag,
                "--execute",
            ]
        )

    assert exc.value.code == 2
    assert f"unrecognized arguments: {removed_flag}" in capsys.readouterr().err


def test_cli_execute_rejects_non_postgres_test_dsn_override(tmp_path, capsys):
    database_url = _seed_runtime_control_state_db(tmp_path)

    result = bootstrap.main(
        [
            "--database-url",
            database_url,
            "--allow-non-postgres-for-test",
            "--execute",
        ]
    )

    assert result == 2
    assert "must not be combined with --execute" in capsys.readouterr().err


def test_cli_rejects_removed_candidate_universe_file_flag(tmp_path, capsys):
    database_url = _seed_runtime_control_state_db(tmp_path)
    removed_flag = "--candidate-" + "universe-json"

    with pytest.raises(SystemExit) as exc:
        bootstrap.main(
            [
                "--database-url",
                database_url,
                "--allow-non-postgres-for-test",
                removed_flag,
                str(tmp_path / "must-not-be-read.json"),
            ]
        )

    assert exc.value.code == 2
    assert f"unrecognized arguments: {removed_flag}" in capsys.readouterr().err


def test_cli_pg_bootstrap_requires_active_runtime_scope_binding(tmp_path, capsys):
    database_url = _seed_runtime_control_state_db(tmp_path)
    _mutate_runtime_control_state_db(
        database_url,
        """
        DELETE FROM brc_runtime_scope_bindings
        WHERE candidate_scope_id = 'candidate_scope:MPG-001:OPUSDT:long:MPG-LONG'
        """,
    )

    result = bootstrap.main(
        [
            "--database-url",
            database_url,
            "--allow-non-postgres-for-test",
        ]
    )

    assert result == 2
    assert "has no active runtime scope binding" in capsys.readouterr().err


def test_cli_pg_bootstrap_requires_policy_notional_leverage_scope(tmp_path, capsys):
    database_url = _seed_runtime_control_state_db(tmp_path)
    _mutate_runtime_control_state_db(
        database_url,
        """
        UPDATE brc_owner_policy_current
        SET max_notional = NULL
        WHERE policy_current_id =
          'policy_current:candidate_scope:MPG-001:OPUSDT:long:MPG-LONG'
        """,
    )

    result = bootstrap.main(
        [
            "--database-url",
            database_url,
            "--allow-non-postgres-for-test",
        ]
    )

    assert result == 2
    assert "missing max_notional or leverage scope" in capsys.readouterr().err


def test_cli_pg_backed_bootstrap_reads_seeded_runtime_control_state(
    tmp_path,
    capsys,
    monkeypatch,
):
    database_url = _seed_runtime_control_state_db(tmp_path)
    monkeypatch.setattr(bootstrap, "UrlLibApiClient", lambda api_base: object())
    monkeypatch.setattr(bootstrap, "_list_active_runtimes", lambda client: ([], []))

    result = bootstrap.main(
        [
            "--database-url",
            database_url,
            "--allow-non-postgres-for-test",
            "--max-symbols-per-group",
            "4",
            "--max-total-new-runtimes",
            "30",
            "--include-observe-only",
        ]
    )

    assert result == 0
    artifact = json.loads(capsys.readouterr().out)
    assert artifact["status"] == "planned_runtime_bootstrap"
    assert artifact["runtime_scope"]["candidate_universe_source"] == PG_SOURCE_REF
    assert artifact["runtime_scope"]["candidate_universe_symbol_count"] == 18
    assert artifact["runtime_scope"]["candidate_universe_lane_count"] == 22
    target_scope = {
        (row["strategy_group_id"], row["exchange_symbol"], row["side"])
        for row in artifact["targets"]
    }
    assert ("CPM-RO-001", "ETHUSDT", "short") not in target_scope
    assert ("MPG-001", "OPUSDT", "short") not in target_scope
    assert ("BRF2-001", "BTCUSDT", "long") not in target_scope
    assert ("SOR-001", "ETHUSDT", "long") in target_scope
    assert ("SOR-001", "ETHUSDT", "short") in target_scope
    assert artifact["safety_invariants"]["creates_candidate"] is False
    assert artifact["safety_invariants"]["creates_execution_intent"] is False
    assert artifact["safety_invariants"]["creates_order"] is False
