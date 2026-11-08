import pytest
import sqlalchemy as sa

from scripts.trading_kernel.certify_readonly import _certify
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION


@pytest.mark.asyncio
async def test_readonly_certification_rejects_wrong_product(head_template_engine):
    engine = head_template_engine
    async with PostgresKernelUnitOfWork(engine) as u:
        await seed_runtime_authority(u, RuntimeAuthoritySeedRequest(account_id='manual-test',
            runtime_commit='a' * 40, schema_revision=CURRENT_SCHEMA_REVISION, seeded_at_ms=1000))
    async with engine.begin() as c:
        await c.execute(sa.text("UPDATE brc_runtime_capabilities_current SET certification=certification || '{\"product_id\":\"brc-auto-tokyo-v1\"}'::jsonb"))
    result = await _certify(engine.url.render_as_string(hide_password=False), require_flat=False, now_ms=2000)
    assert result['product_identity']['status'] == 'fail'
    assert result['status'] != 'pass'
