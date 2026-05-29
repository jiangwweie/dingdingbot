from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.mi001_sol_pg_registration_apply import (
    Mi001SolPgRegistrationApplyService,
)
from src.domain.brc_admission import (
    AdmissionExecutionMode,
    AdmissionTrialBindingStatus,
    TrialConstraintSnapshotStatus,
)
from src.domain.mi001_sol_pg_registration import (
    MI001_CANDIDATE_ID,
    MI001_FAMILY_ID,
    MI001_PLAYBOOK_ID,
    MI001_SIDE,
    MI001_SYMBOL,
    build_mi001_sol_pg_registration_dry_run,
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
    PGBrcStrategyFamilyPlaybookORM,
    PGBrcStrategyFamilyRegistryORM,
    PGBrcStrategyFamilyVersionORM,
    PGBrcTrialConstraintSnapshotORM,
    PGBrcTrialTradeIntentORM,
)
from src.infrastructure.pg_strategy_family_registry_repository import (
    PgStrategyFamilyRegistryRepository,
)


TABLES = [
    PGBrcStrategyFamilyRegistryORM.__table__,
    PGBrcStrategyFamilyPlaybookORM.__table__,
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
async def repositories():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        for table in TABLES:
            await conn.run_sync(table.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield (
            PgStrategyFamilyRegistryRepository(session_maker=session_maker),
            PgBrcAdmissionRepository(session_maker=session_maker),
            session_maker,
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_apply_service_persists_mi001_records_to_injected_repositories(repositories):
    registry_repo, admission_repo, session_maker = repositories
    payload = build_mi001_sol_pg_registration_dry_run(now_ms=1770000000000)
    service = Mi001SolPgRegistrationApplyService(
        registry_repository=registry_repo,
        admission_repository=admission_repo,
    )

    result = await service.apply(payload)

    assert result.source_of_truth_status["trial_constraints"] == (
        "repository_applied_policy_rules_only"
    )
    assert result.safety_assertions["fresh_account_facts_read"] is False
    assert result.safety_assertions["concrete_capital_amount_written"] is False
    assert result.safety_assertions["trial_started"] is False
    assert result.safety_assertions["execution_intent_created"] is False
    assert result.safety_assertions["order_created"] is False

    family = await registry_repo.get_family_metadata_version(MI001_FAMILY_ID, "MI-001-smoke-v0")
    playbook = await registry_repo.get_playbook_metadata(MI001_PLAYBOOK_ID)
    admission_family = await admission_repo.get_strategy_family(MI001_FAMILY_ID)
    version = await admission_repo.get_strategy_family_version(
        f"{MI001_CANDIDATE_ID}-admission-v1"
    )
    evidence = await admission_repo.get_evidence_packet(
        f"{MI001_CANDIDATE_ID}-broad-smoke-evidence-v1"
    )
    request = await admission_repo.get_admission_request(
        f"{MI001_CANDIDATE_ID}-admission-request-v1"
    )
    constraint = await admission_repo.get_trial_constraint_snapshot(
        f"{MI001_CANDIDATE_ID}-trial-constraints-v1"
    )
    decision = await admission_repo.get_admission_decision(
        f"{MI001_CANDIDATE_ID}-admission-decision-v1"
    )
    acceptance = await admission_repo.get_owner_risk_acceptance(
        f"{MI001_CANDIDATE_ID}-owner-risk-acceptance-v1"
    )
    binding = await admission_repo.get_admission_trial_binding(
        f"{MI001_CANDIDATE_ID}-planned-binding-v1"
    )

    assert family is not None and family.family_id == MI001_FAMILY_ID
    assert playbook is not None and playbook.playbook_id == MI001_PLAYBOOK_ID
    assert admission_family is not None
    assert version is not None and version.required_execution_capabilities == []
    assert evidence is not None
    assert evidence.payload_json["broad_smoke_summary"]["signal_count"] == 8135
    assert request is not None
    assert request.requested_execution_mode == AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY
    assert request.account_facts_snapshot_json["risk_capital_policy"][
        "concrete_amounts_resolved"
    ] is False
    assert constraint is not None
    assert constraint.status == TrialConstraintSnapshotStatus.PENDING_RISK_CAPITAL_RESOLUTION
    assert constraint.constraints_json["allowed_symbol"] == MI001_SYMBOL
    assert constraint.constraints_json["allowed_side"] == MI001_SIDE
    assert constraint.constraints_json["max_leverage"] == 5
    assert "max_loss_budget" not in constraint.constraints_json
    assert "max_notional" not in constraint.constraints_json
    assert decision is not None
    assert decision.execution_mode == AdmissionExecutionMode.OWNER_CONFIRM_EACH_ENTRY
    assert decision.risk_intent_json["owner_approved_trial_start"] is False
    assert acceptance is not None
    assert acceptance.risk_disclosure_snapshot_json["owner_has_not_approved_trial_start"] is True
    assert binding is not None
    assert binding.binding_status == AdmissionTrialBindingStatus.PLANNED
    assert binding.campaign_id is None
    assert binding.runtime_carrier_id is None

    async with session_maker() as session:
        count = await session.scalar(select(func.count()).select_from(PGBrcTrialTradeIntentORM))
    assert count == 0


@pytest.mark.asyncio
async def test_apply_service_is_idempotent_for_deterministic_payload(repositories):
    registry_repo, admission_repo, _ = repositories
    payload = build_mi001_sol_pg_registration_dry_run(now_ms=1770000000000)
    service = Mi001SolPgRegistrationApplyService(
        registry_repository=registry_repo,
        admission_repository=admission_repo,
    )

    first = await service.apply(payload)
    second = await service.apply(payload)

    first_statuses = {record.apply_status for record in first.applied_records}
    second_statuses_by_type = {
        record.record_type: record.apply_status for record in second.applied_records
    }

    assert {"created", "upserted"}.issubset(first_statuses)
    assert second_statuses_by_type["strategy_family_registry"] == "upserted"
    assert second_statuses_by_type["playbook_metadata"] == "upserted"
    assert second_statuses_by_type["admission_request"] == "already_exists"
    assert second_statuses_by_type["trial_constraint_snapshot"] == "already_exists"
    assert second_statuses_by_type["planned_trial_binding"] == "already_exists"


def test_apply_service_has_no_execution_order_or_exchange_dependencies() -> None:
    source = Path("src/application/mi001_sol_pg_registration_apply.py").read_text()

    assert "exchange_gateway" not in source
    assert "ExecutionIntent" not in source
    assert "OrderRepository" not in source
    assert "place_order" not in source
    assert "cancel_order" not in source
    assert "submit_order" not in source
    assert "set_leverage" not in source
    assert "withdraw(" not in source
    assert "transfer(" not in source
