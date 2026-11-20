import pytest
import sqlalchemy as sa

from src.trading_kernel.infrastructure.manual_clone_initialization import (
    initialize_tokyo_manual,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION


@pytest.mark.asyncio
async def test_clean_tokyo_initialization_is_empty_paused_and_retains_manual_capability(
    head_template_engine,
):
    async with PostgresKernelUnitOfWork(head_template_engine) as u:
        await initialize_tokyo_manual(
            u,
            RuntimeAuthoritySeedRequest(
                account_id="owner-subaccount-runtime-v0",
                runtime_commit="a" * 40,
                schema_revision=CURRENT_SCHEMA_REVISION,
                seeded_at_ms=1000,
            ),
        )
    async with head_template_engine.connect() as c:
        assert (
            await c.scalar(
                sa.text("SELECT new_entry_submit_enabled FROM brc_owner_policy_current")
            )
            is False
        )
        assert (
            await c.scalar(
                sa.text(
                    "SELECT enabled FROM brc_runtime_capabilities_current WHERE capability_key='exchange_commands'"
                )
            )
            is True
        )
        assert await c.scalar(sa.text("SELECT count(*) FROM brc_trade_tickets")) == 0
        assert (
            await c.scalar(sa.text("SELECT count(*) FROM brc_exchange_commands")) == 0
        )
        assert (
            await c.scalar(
                sa.text(
                    "SELECT count(*) FROM brc_owner_authorizations WHERE authentication_strength='totp_step_up'"
                )
            )
            == 0
        )
        assert (
            await c.scalar(
                sa.text(
                    "SELECT entry_state FROM brc_strategy_entry_controls_current WHERE strategy_group_id='SOR-001'"
                )
            )
            == "paused"
        )
    with pytest.raises(ValueError, match="empty"):
        async with PostgresKernelUnitOfWork(head_template_engine) as u:
            await initialize_tokyo_manual(
                u,
                RuntimeAuthoritySeedRequest(
                    account_id="owner-subaccount-runtime-v0",
                    runtime_commit="a" * 40,
                    schema_revision=CURRENT_SCHEMA_REVISION,
                    seeded_at_ms=2000,
                ),
            )


@pytest.mark.asyncio
async def test_rebuild_spec_and_universe_config_uses_canonical_install_paths(
    head_template_engine,
):
    from scripts.trading_kernel.tokyo_clean_manual import initialize_fresh_database
    from src.trading_kernel.domain.generic_selection_spec import (
        SpecNumericInstallationEvidence,
        generic_selection_spec,
    )

    groups = ["CPM-RO-001", "MPG-001", "MI-001", "BRF2-001"]
    config = {
        "members": {
            generic_selection_spec(g).event_spec_id: [
                "binance-usdm:BTCUSDT:perpetual",
                "binance-usdm:ETHUSDT:perpetual",
            ]
            for g in groups
        },
        "strategy": {
            "CPM-RO-001": "paused",
            "MI-001": "enabled",
            "MPG-001": "enabled",
            "BRF2-001": "enabled",
            "SOR-001": "paused",
            "SOR-1H-001": "enabled",
            "SOR-US-EQ-PERP-001": "paused",
        },
        "direction": "neutral",
        "spec_evidence": {},
    }
    for group in groups:
        spec = generic_selection_spec(group)
        config["spec_evidence"][group] = SpecNumericInstallationEvidence(
            selection_spec_id=spec.selection_spec_id,
            algorithm_semantic_digest=spec.algorithm_semantic_digest,
            checked_cutoffs=463 if spec.cadence_hours == 4 else 1852,
            mismatch_count=0,
            source_archive_count=96,
            reference_commit="f65d72fa92580de4b8c0323f4106d5975b97f4eb",
            common_numeric_authority="PASS",
            sor_golden="PASS",
            spec_cert="PASS",
        ).model_dump(mode="json")
    await initialize_fresh_database(
        head_template_engine.url.render_as_string(hide_password=False),
        {"commit": "a" * 40, "schema_revision": CURRENT_SCHEMA_REVISION},
        config,
    )
    async with head_template_engine.connect() as c:
        assert (
            await c.scalar(
                sa.text(
                    "SELECT count(*) FROM brc_instrument_selection_specs WHERE selection_kind='generic_dynamic_v1'"
                )
            )
            == 4
        )
        assert (
            await c.scalar(
                sa.text(
                    "SELECT entry_state FROM brc_strategy_entry_controls_current WHERE strategy_group_id='CPM-RO-001'"
                )
            )
            == "paused"
        )
        assert (
            await c.scalar(
                sa.text(
                    "SELECT entry_state FROM brc_strategy_entry_controls_current WHERE strategy_group_id='SOR-1H-001'"
                )
            )
            == "enabled"
        )
        assert (
            await c.scalar(
                sa.text(
                    "SELECT count(*) FROM brc_owner_authorizations WHERE authentication_strength='totp_step_up'"
                )
            )
            == 0
        )
