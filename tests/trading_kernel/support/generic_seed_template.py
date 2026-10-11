"""Cache immutable Generic fixture setup, never a runtime authority source."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import asyncpg
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.trading_kernel.domain.generic_selection_spec import (
    SpecNumericInstallationEvidence,
    generic_selection_spec,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION
from tests.trading_kernel.support.generic_selection import CUTOFF, HOUR
from tests.trading_kernel.support.postgres import (
    HEAD_TEMPLATE_DATABASE,
    SAFE_TEST_DATABASE,
    TEST_POSTGRES_ADMIN_DSN,
    HeadTemplateCloneHarness,
    async_database_url,
    head_template_source_fingerprint,
)

GROUPS = ("CPM-RO-001", "MPG-001", "MI-001", "BRF2-001")


async def seed_generic_database(engine: AsyncEngine, *, excluded_group: str | None = None) -> None:
    """The exact original public installer/seed path, paid once per template."""
    if excluded_group is not None and excluded_group not in GROUPS:
        raise ValueError("unknown excluded Generic family")
    async with PostgresKernelUnitOfWork(engine) as uow:
        await seed_runtime_authority(uow, RuntimeAuthoritySeedRequest(
            account_id="generic-snapshot", runtime_commit="a" * 40,
            schema_revision=CURRENT_SCHEMA_REVISION, seeded_at_ms=CUTOFF-HOUR,
        ))
        for group in GROUPS:
            if group == excluded_group:
                continue
            spec = generic_selection_spec(group)
            await uow.instrument_selection.install_generic_spec(spec, installed_at_ms=CUTOFF-HOUR,
                certification=SpecNumericInstallationEvidence(
                    selection_spec_id=spec.selection_spec_id, algorithm_semantic_digest=spec.algorithm_semantic_digest,
                    checked_cutoffs=463 if spec.cadence_hours==4 else 1852, mismatch_count=0, source_archive_count=96,
                    reference_commit="f65d72fa92580de4b8c0323f4106d5975b97f4eb", common_numeric_authority="PASS",
                    sor_golden="PASS", spec_cert="PASS",
                ))


class GenericSeedTemplateHarness(HeadTemplateCloneHarness):
    """Every test still owns its own database, transactions and disposal."""

    def __init__(self, *, excluded_group: str | None = None) -> None:
        if excluded_group is not None and excluded_group not in GROUPS:
            raise ValueError("unknown excluded Generic family")
        self.excluded_group = excluded_group
        self.template = "brc_kernel_template_generic_" + (
            "all" if excluded_group is None else excluded_group.split("-")[0].lower()
        )

    def fingerprint(self) -> str:
        digest = sha256(head_template_source_fingerprint().encode())
        digest.update(str(self.excluded_group).encode())
        for path in (Path(__file__),Path(__file__).with_name("generic_selection.py")):
            digest.update(path.read_bytes())
        return "sha256:" + digest.hexdigest()

    async def create_clone(self) -> tuple[str, str]:
        admin = await asyncpg.connect(TEST_POSTGRES_ADMIN_DSN)
        try:
            await admin.execute("SELECT pg_advisory_lock(hashtextextended('brc-test-head-template',0))")
            await self._ensure_template(admin)
            actual = await admin.fetchval(
                "SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=$1", self.template,
            )
            expected = self.fingerprint()
            if actual != expected:
                exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname=$1",self.template)
                if exists:
                    await admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=$1 AND pid<>pg_backend_pid()",self.template)
                    await admin.execute(f'DROP DATABASE "{self.template}"')
                await admin.execute(f'CREATE DATABASE "{self.template}" TEMPLATE "{HEAD_TEMPLATE_DATABASE}"')
                base = TEST_POSTGRES_ADMIN_DSN.rsplit("/",1)[0].replace("postgresql://","postgresql+asyncpg://",1)
                engine = create_async_engine(base+"/"+self.template)
                try:
                    await seed_generic_database(engine,excluded_group=self.excluded_group)
                finally:
                    await engine.dispose()
                await admin.execute(f"COMMENT ON DATABASE {self.template} IS '{expected}'")
            name = f"brc_kernel_test_{uuid4().hex[:12]}"
            assert SAFE_TEST_DATABASE.fullmatch(name)
            await admin.execute(f'CREATE DATABASE "{name}" TEMPLATE "{self.template}"')
            return name,async_database_url(name)
        finally:
            await admin.close()
