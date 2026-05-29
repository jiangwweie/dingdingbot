from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.application.mi001_sol_pg_registration_apply import (
    Mi001SolPgRegistrationApplyService,
)
from src.application.mi001_sol_trial_start_checklist import (
    CachedAccountFacts,
    ChecklistStatus,
    KillSwitchFacts,
    Mi001SolTrialStartChecklistGenerator,
    OperationLayerFacts,
    TrialStartChecklistInputs,
    TrialStartChecklistVerdict,
    render_trial_start_checklist_markdown,
)
from src.domain.mi001_sol_pg_registration import build_mi001_sol_pg_registration_dry_run
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
async def seeded_repositories():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        for table in TABLES:
            await conn.run_sync(table.create)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    registry_repo = PgStrategyFamilyRegistryRepository(session_maker=session_maker)
    admission_repo = PgBrcAdmissionRepository(session_maker=session_maker)
    apply_service = Mi001SolPgRegistrationApplyService(
        registry_repository=registry_repo,
        admission_repository=admission_repo,
    )
    await apply_service.apply(build_mi001_sol_pg_registration_dry_run(now_ms=1770000000000))
    try:
        yield registry_repo, admission_repo
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_checklist_blocks_when_cached_account_facts_are_missing(seeded_repositories):
    registry_repo, admission_repo = seeded_repositories
    generator = Mi001SolTrialStartChecklistGenerator(
        registry_repository=registry_repo,
        admission_repository=admission_repo,
    )

    checklist = await generator.generate(TrialStartChecklistInputs(generated_at_ms=1770000000000))

    assert checklist.final_verdict == TrialStartChecklistVerdict.BLOCKED_FRESH_ACCOUNT_FACTS_REQUIRED
    assert checklist.source_inputs["pg_registration_records"] == "available"
    assert checklist.source_inputs["cached_account_facts"] == "missing"
    assert any(row.check == "cached AccountSnapshot exists" and row.blocking for row in checklist.account_facts_checks)
    assert "Owner trial start approved" in checklist.blockers
    assert checklist.capital_readiness.computed_max_notional_candidate is None


@pytest.mark.asyncio
async def test_checklist_marks_unsafe_account_fact_path_blocked(seeded_repositories):
    registry_repo, admission_repo = seeded_repositories
    generator = Mi001SolTrialStartChecklistGenerator(
        registry_repository=registry_repo,
        admission_repository=admission_repo,
    )

    checklist = await generator.generate(
        TrialStartChecklistInputs(
            generated_at_ms=1770000000000,
            account_facts=CachedAccountFacts(
                available=False,
                freshness="missing",
                source="runtime_exchange_gateway_cache_path_not_invoked",
                read_method="unsafe_to_read",
                read_only=False,
                notes="Only visible account snapshot path touches runtime exchange gateway state.",
            ),
            kill_switch_facts=KillSwitchFacts(
                available=True,
                active=True,
                source="fake_pg_gks",
                updated_at_ms=1770000000000,
            ),
        )
    )

    assert checklist.final_verdict == TrialStartChecklistVerdict.BLOCKED_FRESH_ACCOUNT_FACTS_REQUIRED
    assert checklist.source_inputs["cached_account_facts"] == "unsafe_to_read"
    assert any(
        row.status == ChecklistStatus.UNSAFE_TO_READ
        and row.check == "read-only source"
        and row.blocking
        for row in checklist.account_facts_checks
    )
    rendered = render_trial_start_checklist_markdown(checklist)
    assert "active=True means Global Kill Switch blocks all new entries" in rendered
    assert "Only visible account snapshot path touches runtime exchange gateway state." in rendered


@pytest.mark.asyncio
async def test_checklist_computes_capital_when_facts_are_fresh_but_keeps_owner_blocker(
    seeded_repositories,
):
    registry_repo, admission_repo = seeded_repositories
    generator = Mi001SolTrialStartChecklistGenerator(
        registry_repository=registry_repo,
        admission_repository=admission_repo,
    )

    checklist = await generator.generate(
        TrialStartChecklistInputs(
            generated_at_ms=1770000000000,
            account_facts=CachedAccountFacts(
                available=True,
                wallet_equity=Decimal("100"),
                available_margin=Decimal("80"),
                timestamp_ms=1770000000000,
                freshness="fresh",
                source="cached_account_snapshot",
                read_method="cache_only",
                read_only=True,
            ),
            operation_layer_facts=OperationLayerFacts(
                available=True,
                gate_available=True,
                notional_cap_available=True,
                notional_cap=Decimal("300"),
                evidence_logging_available=True,
                no_active_trial_position=True,
                startup_guard_available=True,
                startup_guard_armed=False,
                source="fake_operation_layer_facts",
            ),
            kill_switch_facts=KillSwitchFacts(
                available=True,
                active=True,
                source="fake_pg_gks",
                updated_at_ms=1770000000000,
            ),
        )
    )

    assert checklist.final_verdict == (
        TrialStartChecklistVerdict.BLOCKED_OWNER_TRIAL_START_APPROVAL_REQUIRED
    )
    assert checklist.capital_readiness.current_dedicated_subaccount_equity == Decimal("100")
    assert checklist.capital_readiness.available_margin == Decimal("80")
    assert checklist.capital_readiness.computed_max_notional_candidate == Decimal("300")
    assert checklist.capital_readiness.max_leverage == 5
    assert "Owner trial start approved" in checklist.blockers


def test_checklist_generator_has_no_execution_order_or_exchange_dependencies() -> None:
    source = Path("src/application/mi001_sol_trial_start_checklist.py").read_text()

    assert "exchange_gateway" not in source
    assert "ExecutionIntent" not in source
    assert "OrderRepository" not in source
    assert "place_order" not in source
    assert "cancel_order" not in source
    assert "submit_order" not in source
    assert "set_leverage" not in source
    assert "withdraw(" not in source
    assert "transfer(" not in source
