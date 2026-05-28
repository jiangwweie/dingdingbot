from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.brc_admission_service import (
    AdmissionRuleViolation,
    BrcAdmissionService,
    OwnerRiskAcceptanceInput,
    PendingRiskCapitalAdapter,
)
from src.domain.brc_admission import (
    AdmissionDecisionValue,
    AdmissionExecutionMode,
    AdmissionTrialBindingStatus,
    RiskCapitalAdapterResult,
    TrialConstraintSnapshotStatus,
    TrialEnv,
    TrialStage,
)
from src.infrastructure.pg_brc_admission_repository import PgBrcAdmissionRepository
from src.infrastructure.pg_models import (
    PGBrcAdmissionAuditLogORM,
    PGBrcAdmissionDecisionORM,
    PGBrcAdmissionEvidencePacketORM,
    PGBrcAdmissionRequestORM,
    PGBrcAdmissionRuleConfigORM,
    PGBrcAdmissionTrialBindingORM,
    PGBrcOwnerMarketRegimeInputORM,
    PGBrcOwnerRiskAcceptanceORM,
    PGBrcStrategyFamilyORM,
    PGBrcStrategyFamilyVersionORM,
    PGBrcTrialTradeIntentORM,
    PGBrcTrialConstraintSnapshotORM,
)


ADMISSION_TABLES = [
    PGBrcStrategyFamilyORM.__table__,
    PGBrcStrategyFamilyVersionORM.__table__,
    PGBrcAdmissionRuleConfigORM.__table__,
    PGBrcAdmissionEvidencePacketORM.__table__,
    PGBrcOwnerMarketRegimeInputORM.__table__,
    PGBrcAdmissionRequestORM.__table__,
    PGBrcTrialConstraintSnapshotORM.__table__,
    PGBrcAdmissionDecisionORM.__table__,
    PGBrcOwnerRiskAcceptanceORM.__table__,
    PGBrcAdmissionAuditLogORM.__table__,
    PGBrcAdmissionTrialBindingORM.__table__,
    PGBrcTrialTradeIntentORM.__table__,
]


@pytest_asyncio.fixture()
async def admission_service():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        for table in ADMISSION_TABLES:
            await conn.run_sync(table.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    service = BrcAdmissionService(
        repository=PgBrcAdmissionRepository(session_maker=session_maker)
    )
    try:
        yield service
    finally:
        await engine.dispose()


async def _seed_request(
    service: BrcAdmissionService,
    *,
    trial_env: TrialEnv = TrialEnv.TESTNET,
    trial_stage: TrialStage = TrialStage.FUNDED_VALIDATION,
    mandatory_complete: bool = False,
    account_facts_snapshot_ref: str | None = "acct-facts-1",
    account_facts_snapshot_json: dict | None = None,
    requested_execution_mode: AdmissionExecutionMode | None = None,
):
    family = await service.create_strategy_family(
        family_key="ema60-branches",
        name="EMA60 Branches",
    )
    version = await service.create_strategy_family_version(
        strategy_family_id=family.strategy_family_id,
        version=1,
        hypothesis="Mean reversion branch hypothesis",
        supported_symbols=["ETH/USDT:USDT"],
        supported_timeframes=["1h"],
        playbook_id="PB-004-BRC-CONTROLLED-TESTNET",
        playbook_catalog_snapshot_json={"id": "PB-004-BRC-CONTROLLED-TESTNET"},
    )
    evidence = await service.create_evidence_packet(
        strategy_family_version_id=version.strategy_family_version_id,
        payload_json={"backtest": "available"},
        mandatory_complete=mandatory_complete,
    )
    regime = await service.create_owner_regime_input(
        current_regime="range",
        confidence="medium",
    )
    request = await service.create_admission_request(
        strategy_family_version_id=version.strategy_family_version_id,
        evidence_packet_id=evidence.evidence_packet_id,
        owner_market_regime_input_id=regime.owner_market_regime_input_id,
        trial_env=trial_env,
        trial_stage=trial_stage,
        requested_execution_mode=requested_execution_mode,
        requested_risk_profile="micro",
        account_facts_snapshot_ref=account_facts_snapshot_ref,
        account_facts_snapshot_json=account_facts_snapshot_json
        if account_facts_snapshot_json is not None
        else {
            "source": "exchange_testnet",
            "truth_level": "exchange_read",
            "reconciliation_status": {"status": "clean"},
            "unknown_unmanaged_counts": {"orders": 0, "positions": 0},
        },
    )
    return family, version, evidence, regime, request


def test_migration_creates_brc_admission_tables():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-05-27-018_create_brc_admission_gate_phase1.py"
    )
    spec = importlib.util.spec_from_file_location("brc_admission_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _run() -> set[str]:
        async with engine.begin() as conn:
            def upgrade(sync_conn):
                old_op = migration.op
                migration.op = Operations(MigrationContext.configure(sync_conn))
                try:
                    migration.upgrade()
                    return set(inspect(sync_conn).get_table_names())
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    import asyncio

    tables = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert {
        "brc_strategy_families",
        "brc_strategy_family_versions",
        "brc_admission_rule_configs",
        "brc_admission_requests",
        "brc_owner_market_regime_inputs",
        "brc_admission_evidence_packets",
        "brc_admission_decisions",
        "brc_trial_constraint_snapshots",
        "brc_owner_risk_acceptances",
        "brc_admission_audit_log",
    }.issubset(tables)


def test_migration_creates_brc_admission_trial_binding_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-05-27-019_create_brc_admission_trial_bindings.py"
    )
    spec = importlib.util.spec_from_file_location("brc_admission_binding_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _run() -> set[str]:
        async with engine.begin() as conn:
            def upgrade(sync_conn):
                old_op = migration.op
                migration.op = Operations(MigrationContext.configure(sync_conn))
                try:
                    migration.upgrade()
                    return set(inspect(sync_conn).get_table_names())
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    import asyncio

    tables = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "brc_admission_trial_bindings" in tables


def test_migration_creates_brc_trial_trade_intent_table():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations/versions/2026-05-27-021_create_brc_trial_trade_intents.py"
    )
    spec = importlib.util.spec_from_file_location("brc_trial_trade_intent_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _run() -> set[str]:
        async with engine.begin() as conn:
            def upgrade(sync_conn):
                old_op = migration.op
                migration.op = Operations(MigrationContext.configure(sync_conn))
                try:
                    migration.upgrade()
                    return set(inspect(sync_conn).get_table_names())
                finally:
                    migration.op = old_op

            return await conn.run_sync(upgrade)

    import asyncio

    tables = asyncio.run(_run())
    asyncio.run(engine.dispose())

    assert "brc_trial_trade_intents" in tables


@pytest.mark.asyncio
async def test_repository_create_get_list_and_version_pinning(admission_service):
    family, version, evidence, regime, request = await _seed_request(admission_service)

    listed = await admission_service.list_strategy_families()
    loaded_request = await admission_service.get_admission_request(request.admission_request_id)

    assert listed[0].strategy_family_id == family.strategy_family_id
    assert version.playbook_id == "PB-004-BRC-CONTROLLED-TESTNET"
    assert evidence.strategy_family_version_id == version.strategy_family_version_id
    assert regime.current_regime == "range"
    assert loaded_request.strategy_family_version_id == version.strategy_family_version_id
    assert loaded_request.evidence_packet_id == evidence.evidence_packet_id
    assert loaded_request.owner_market_regime_input_id == regime.owner_market_regime_input_id


@pytest.mark.asyncio
async def test_admission_trial_binding_repository_and_service_reservation(admission_service):
    _, _, _, _, request = await _seed_request(
        admission_service,
        trial_env=TrialEnv.TESTNET,
        trial_stage=TrialStage.FUNDED_VALIDATION,
        mandatory_complete=True,
    )
    decision = await admission_service.evaluate(request.admission_request_id)
    acceptance = await admission_service.create_owner_risk_acceptance(
        OwnerRiskAcceptanceInput(
            admission_request_id=request.admission_request_id,
            admission_decision_id=decision.admission_decision_id,
            constraint_snapshot_id=decision.trial_constraint_snapshot_id,
            owner_rationale="I accept the installable gated trial constraints.",
            confirmation_phrase="I ACCEPT BOUNDED FUNDED VALIDATION RISK",
        )
    )

    binding = await admission_service.reserve_gated_trial_binding(
        {
            "admission_decision_id": decision.admission_decision_id,
            "owner_risk_acceptance_id": acceptance.owner_risk_acceptance_id,
        },
        operation_id="op-unit",
        preflight_id="pre-unit",
    )
    loaded = await admission_service.get_admission_trial_binding(binding.binding_id)
    listed = await admission_service.list_admission_trial_bindings()
    by_decision = await admission_service._repo.list_admission_trial_bindings_by_decision(
        decision.admission_decision_id
    )
    by_operation = await admission_service._repo.list_admission_trial_bindings_by_operation(
        "op-unit"
    )

    assert loaded.binding_status == AdmissionTrialBindingStatus.BINDING_RESERVED
    assert loaded.campaign_id is None
    assert loaded.runtime_carrier_id is None
    assert listed[0].binding_id == binding.binding_id
    assert by_decision[0].binding_id == binding.binding_id
    assert by_operation[0].binding_id == binding.binding_id

    with pytest.raises(AdmissionRuleViolation, match="active admission trial binding"):
        await admission_service.reserve_gated_trial_binding(
            {
                "admission_decision_id": decision.admission_decision_id,
                "owner_risk_acceptance_id": acceptance.owner_risk_acceptance_id,
            },
            operation_id="op-unit-2",
            preflight_id="pre-unit-2",
        )


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_pending_adapter_remains_safe():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        for table in ADMISSION_TABLES:
            await conn.run_sync(table.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    service = BrcAdmissionService(
        repository=PgBrcAdmissionRepository(session_maker=session_maker),
        risk_capital_adapter=PendingRiskCapitalAdapter(),
    )
    try:
        _, version, _, _, request = await _seed_request(
            service,
            trial_env=TrialEnv.TESTNET,
            trial_stage=TrialStage.FUNDED_VALIDATION,
            mandatory_complete=False,
        )
        decision = await service.evaluate(request.admission_request_id)
    finally:
        await engine.dispose()

    assert decision.decision == AdmissionDecisionValue.ADMIT_WITH_CONSTRAINTS
    assert decision.execution_mode == AdmissionExecutionMode.AUTO_WITHIN_BUDGET
    assert decision.strategy_family_version_id == version.strategy_family_version_id
    assert decision.constraints_snapshot_json["status"] == "pending_risk_capital_resolution"
    assert any("risk capital constraints pending" in item for item in decision.warnings_json)


@pytest.mark.asyncio
async def test_testnet_development_validation_returns_installable_constraints(admission_service):
    _, version, _, _, request = await _seed_request(
        admission_service,
        trial_env=TrialEnv.TESTNET,
        trial_stage=TrialStage.DEVELOPMENT_VALIDATION,
        mandatory_complete=False,
        account_facts_snapshot_ref=None,
        account_facts_snapshot_json={},
    )

    decision = await admission_service.evaluate(request.admission_request_id)

    assert decision.decision == AdmissionDecisionValue.ADMIT_WITH_CONSTRAINTS
    assert decision.execution_mode == AdmissionExecutionMode.OBSERVE_ONLY
    assert decision.strategy_family_version_id == version.strategy_family_version_id
    assert decision.trial_constraint_snapshot_id
    assert decision.constraints_snapshot_json["status"] == "installable"
    constraints = decision.constraints_snapshot_json["constraints_json"]
    assert constraints["source"] == "fallback_policy"
    assert constraints["trial_env"] == "testnet"
    assert constraints["trial_stage"] == "development_validation"
    assert constraints["allowed_symbols"] == ["ETH/USDT:USDT"]
    assert constraints["max_leverage"] == 1
    assert any("mandatory evidence incomplete" in item for item in decision.warnings_json)
    assert decision.risk_disclosure_json["sizing_computed_by_admission"] is False


@pytest.mark.asyncio
async def test_live_funded_validation_blocks_when_account_facts_unavailable(admission_service):
    _, _, _, _, request = await _seed_request(
        admission_service,
        trial_env=TrialEnv.LIVE,
        trial_stage=TrialStage.FUNDED_VALIDATION,
        account_facts_snapshot_ref=None,
        account_facts_snapshot_json={"source": "unavailable", "truth_level": "unavailable"},
    )

    decision = await admission_service.evaluate(request.admission_request_id)

    assert decision.decision == AdmissionDecisionValue.REJECT
    assert decision.execution_mode == AdmissionExecutionMode.NO_ENTRY
    assert "account facts unavailable" in decision.blockers_json


@pytest.mark.asyncio
async def test_live_funded_validation_risk_capital_unavailable_stays_pending(admission_service):
    _, _, _, _, request = await _seed_request(
        admission_service,
        trial_env=TrialEnv.LIVE,
        trial_stage=TrialStage.FUNDED_VALIDATION,
        mandatory_complete=True,
        account_facts_snapshot_ref="acct-live-1",
        account_facts_snapshot_json={
            "source": "exchange_live",
            "truth_level": "reconciled",
            "reconciliation_status": {"status": "clean"},
            "unknown_unmanaged_counts": {"orders": 0, "positions": 0},
        },
    )

    decision = await admission_service.evaluate(request.admission_request_id)

    assert decision.decision == AdmissionDecisionValue.ADMIT_WITH_CONSTRAINTS
    assert decision.constraints_snapshot_json["status"] == "pending_risk_capital_resolution"
    assert "risk capital constraints pending resolution" in decision.warnings_json
    assert decision.constraints_snapshot_json["constraints_json"]["source"] == "unavailable"


@pytest.mark.asyncio
async def test_live_funded_validation_installable_requires_clean_account_and_resolution(admission_service):
    _, _, _, _, request = await _seed_request(
        admission_service,
        trial_env=TrialEnv.LIVE,
        trial_stage=TrialStage.FUNDED_VALIDATION,
        mandatory_complete=True,
        account_facts_snapshot_ref="acct-live-2",
        account_facts_snapshot_json={
            "source": "exchange_live",
            "truth_level": "reconciled",
            "reconciliation_status": {"status": "clean"},
            "unknown_unmanaged_counts": {"orders": 0, "positions": 0},
            "risk_capital_resolution": {
                "risk_policy_version": "live-risk-v1",
                "max_loss_budget": "10",
                "max_notional": "100",
                "max_leverage": 1,
                "max_attempts": 1,
            },
        },
    )

    decision = await admission_service.evaluate(request.admission_request_id)

    assert decision.decision == AdmissionDecisionValue.ADMIT_WITH_CONSTRAINTS
    assert decision.constraints_snapshot_json["status"] == "installable"
    constraints = decision.constraints_snapshot_json["constraints_json"]
    assert constraints["source"] == "risk_capital_adapter"
    assert constraints["account_facts_snapshot_ref"] == "acct-live-2"
    assert constraints["max_loss_budget"] == "10"
    assert constraints["max_notional"] == "100"


class _InstallableRiskCapitalAdapter:
    async def resolve_constraints(self, **kwargs):
        request = kwargs["request"]
        return RiskCapitalAdapterResult(
            status=TrialConstraintSnapshotStatus.INSTALLABLE,
            risk_profile=request.requested_risk_profile,
            risk_policy_version="risk-policy-v1",
            constraints_json={"max_attempts": 1, "max_notional_source": "risk_capital"},
            risk_policy_snapshot_json={"version": "risk-policy-v1"},
            adapter_result_json={"sizing_computed": True},
        )


@pytest.mark.asyncio
async def test_owner_risk_acceptance_requires_installable_constraints(admission_service):
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        for table in ADMISSION_TABLES:
            await conn.run_sync(table.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    service = BrcAdmissionService(
        repository=PgBrcAdmissionRepository(session_maker=session_maker),
        risk_capital_adapter=PendingRiskCapitalAdapter(),
    )
    try:
        _, _, _, _, request = await _seed_request(service)
        decision = await service.evaluate(request.admission_request_id)

        with pytest.raises(AdmissionRuleViolation, match="installable"):
            await service.create_owner_risk_acceptance(
                OwnerRiskAcceptanceInput(
                    admission_request_id=request.admission_request_id,
                    admission_decision_id=decision.admission_decision_id,
                    constraint_snapshot_id=decision.trial_constraint_snapshot_id,
                    owner_rationale="I accept the bounded funded validation risk.",
                    confirmation_phrase="I ACCEPT BOUNDED FUNDED VALIDATION RISK",
                )
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_owner_risk_acceptance_persists_for_installable_constraints():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        for table in ADMISSION_TABLES:
            await conn.run_sync(table.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    service = BrcAdmissionService(
        repository=PgBrcAdmissionRepository(session_maker=session_maker),
        risk_capital_adapter=_InstallableRiskCapitalAdapter(),
    )
    try:
        _, _, _, _, request = await _seed_request(
            service,
            trial_env=TrialEnv.TESTNET,
            trial_stage=TrialStage.FUNDED_VALIDATION,
            mandatory_complete=True,
        )
        decision = await service.evaluate(request.admission_request_id)
        acceptance = await service.create_owner_risk_acceptance(
            OwnerRiskAcceptanceInput(
                admission_request_id=request.admission_request_id,
                admission_decision_id=decision.admission_decision_id,
                constraint_snapshot_id=decision.trial_constraint_snapshot_id,
                owner_rationale="I accept the installable constraints.",
                confirmation_phrase="I ACCEPT BOUNDED FUNDED VALIDATION RISK",
            )
        )
    finally:
        await engine.dispose()

    assert acceptance.constraint_snapshot_id == decision.trial_constraint_snapshot_id
    assert acceptance.risk_policy_snapshot_json == {"version": "risk-policy-v1"}
    assert acceptance.account_facts_snapshot_ref == "acct-facts-1"


def test_admission_service_does_not_import_yaml_or_trading_clients():
    source = Path("src/application/brc_admission_service.py").read_text()
    assert "import yaml" not in source
    assert "ccxt" not in source
    assert "create_order" not in source
    assert "_DEFAULT_TESTNET_MAX_NOTIONAL" not in source
    assert "_DEFAULT_TESTNET_MAX_LOSS_BUDGET" not in source


def test_risk_capital_adapter_owns_resolution_contract():
    source = Path("src/application/brc_admission_risk_capital.py").read_text()
    assert "class BrcAdmissionRiskCapitalAdapter" in source
    assert "max_notional" in source
    assert "max_loss_budget" in source
    assert "create_order" not in source
