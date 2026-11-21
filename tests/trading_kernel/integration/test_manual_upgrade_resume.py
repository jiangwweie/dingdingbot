"""Faults after durable upgrade side effects must resume the exact same candidate."""

import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.trading_kernel import manual_same_schema_upgrade as upgrade
from scripts.trading_kernel.manual_upgrade_journal import UpgradeJournal
from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork
from src.trading_kernel.infrastructure.runtime_authority_seed import (
    RuntimeAuthoritySeedRequest,
    seed_runtime_authority,
)
from tests.trading_kernel.support.postgres import (
    create_empty_database,
    drop_disposable_database,
    run_alembic,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fault", "source_revision", "target_revision"),
    [
        (fault, "0023_management_recovery", "0024_owner_cooperation")
        for fault in (
            "migration",
            "identity",
            "environment",
            "kernel",
            "api",
            "static",
            "starting_services",
            "services",
        )
    ]
    + [
        (fault, "0024_owner_cooperation", "0025_directional_sor")
        for fault in ("migration", "identity", "starting_services")
    ],
)
async def test_real_stopped_upgrade_resumes_after_each_side_effect(
    tmp_path, monkeypatch, fault, source_revision, target_revision
):
    from unittest.mock import AsyncMock

    from src.trading_kernel.infrastructure import manual_account_setup

    name, url = await create_empty_database()
    engine = create_async_engine(url)
    root = tmp_path / "etc/brc/manual-install"
    root.mkdir(parents=True)
    etc = tmp_path / "etc/brc"
    (etc / "trading-kernel.write-fenced").touch()
    (tmp_path / "etc/nginx/snippets").mkdir(parents=True)
    source = {
        "commit": "a" * 40,
        "schema": source_revision,
        "paused": True,
        "tickets": False,
        "commands": False,
        "positions": False,
        "incidents": False,
    }
    receipt = {"commit": "b" * 40, "schema_revision": target_revision}
    links = {}
    for kind, relative in [
        ("kernel", "opt/brc/current"),
        ("api", "opt/brc/owner-console-api/current"),
        ("static", "opt/brc/owner-console/current"),
    ]:
        old = tmp_path / f"old-{kind}"
        target = tmp_path / f"new-{kind}"
        old.mkdir()
        target.mkdir()
        for directory, commit, schema in [
            (old, "a" * 40, source["schema"]),
            (target, "b" * 40, receipt["schema_revision"]),
        ]:
            (directory / ".brc-runtime-commit").write_text(commit)
            (directory / ".brc-schema-revision").write_text(schema)
        link = tmp_path / relative
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(old)
        links[kind] = link
        receipt[kind + "_release"] = str(target)
    environment = etc / "trading-kernel.env"
    environment.write_text(
        "TRADING_KERNEL_RUNTIME_COMMIT="
        + json.dumps("a" * 40)
        + "\nTRADING_KERNEL_SCHEMA_REVISION="
        + json.dumps(source["schema"])
        + "\n"
    )
    (root / "verified-account.json").write_text(
        json.dumps(
            {"account_id": "resume-account", "credential_fingerprint": "local-fake"}
        )
    )
    (root / "exchange-credentials.json").write_text(
        json.dumps(
            {
                "expected_uid": "12345",
                "api_key": "local-placeholder",
                "api_secret": "local-placeholder",
            }
        )
    )
    monkeypatch.setattr(upgrade, "ROOT", root)
    monkeypatch.setattr(
        manual_account_setup,
        "verify_manual_account",
        AsyncMock(
            return_value={"account_ready": True, "credential_fingerprint": "local-fake"}
        ),
    )
    failed = [False]

    def trip(step):
        if fault == step and not failed[0]:
            failed[0] = True
            raise RuntimeError("injected interruption")

    def command(argv, **kwargs):
        if any("bootstrap_schema.py" in str(a) for a in argv):
            run_alembic(url, "upgrade", target_revision)
            trip("migration")
        return b""

    monkeypatch.setattr(upgrade, "run", command)

    async def read_grants(_engine):
        pass

    monkeypatch.setattr(upgrade, "refresh_owner_read_grants", read_grants)
    monkeypatch.setattr(upgrade, "refresh_owner_position_lock_grant", read_grants)
    actual_complete = UpgradeJournal.complete_step

    def complete(self, step):
        if step in {
            "identity",
            "environment",
            "kernel",
            "api",
            "static",
            "starting_services",
            "services",
        }:
            trip(step)
        return actual_complete(self, step)

    monkeypatch.setattr(UpgradeJournal, "complete_step", complete)
    try:
        run_alembic(url, "upgrade", source["schema"])
        async with PostgresKernelUnitOfWork(engine) as u:
            await seed_runtime_authority(
                u,
                RuntimeAuthoritySeedRequest(
                    account_id="resume-account",
                    runtime_commit="a" * 40,
                    schema_revision=source["schema"],
                    seeded_at_ms=1000,
                ),
            )
            if target_revision == "0025_directional_sor":
                from src.trading_kernel.domain.orb_session_selection import (
                    OrbSessionSelectionSpec,
                )

                await u.instrument_selection.install_orb_spec(
                    OrbSessionSelectionSpec(), installed_at_ms=1001
                )
        if target_revision == "0025_directional_sor":
            from src.trading_kernel.application.advance_strategy_universe import (
                UniverseActivationRequest,
                advance_strategy_universe,
            )
            from src.trading_kernel.application.install_strategy_universe import (
                UniverseInstallRequest,
                install_strategy_universe,
            )
            from src.trading_kernel.domain.orb_session_selection import (
                ORB_EVENT_SPEC_IDS,
                ORB_STATIC_MEMBERS,
            )
            from tests.trading_kernel.integration.universe_activation_support import (
                make_warming_ready,
            )
            from tests.trading_kernel.support.exit_configuration import (
                install_approved_exit_configuration,
            )

            await install_approved_exit_configuration(
                engine, account_id="resume-account", now_ms=2000
            )
            for event_id in ORB_EVENT_SPEC_IDS:
                async with PostgresKernelUnitOfWork(engine) as u:
                    prepared = await install_strategy_universe(
                        u,
                        UniverseInstallRequest(
                            event_spec_id=event_id,
                            runtime_profile_id="tiny-live-v1",
                            owner_policy_id="policy-main",
                            exchange_instrument_ids=ORB_STATIC_MEMBERS,
                            installed_at_ms=3000,
                        ),
                    )
                assert prepared.universe is not None
                await make_warming_ready(
                    engine,
                    universe_version_id=prepared.universe.universe_version_id,
                    warm_closed_bar_time_ms=3_600_000,
                    valid_until_ms=7_200_000,
                )
                async with PostgresKernelUnitOfWork(engine) as u:
                    active = await advance_strategy_universe(
                        u,
                        UniverseActivationRequest(
                            universe_version_id=prepared.universe.universe_version_id,
                            attempted_at_ms=3_600_001,
                        ),
                    )
                    assert active.status.value == "activated", active
        with pytest.raises(RuntimeError, match="injected interruption"):
            await upgrade.activate(receipt, source, url, filesystem_root=tmp_path)
        saved = json.loads((root / "upgrade-progress.json").read_text())
        baseline = saved["baseline"]
        assert baseline is not None and failed[0]
        # Use the same official preflight entry before invoking activation again.
        from types import SimpleNamespace

        from scripts.trading_kernel import manual_host_bootstrap as host

        async with engine.connect() as c:
            pair = (
                await c.execute(
                    sa.text(
                        "SELECT (SELECT metadata_value FROM brc_schema_metadata WHERE metadata_key='runtime_commit'),(SELECT version_num FROM alembic_version)"
                    )
                )
            ).one()
        observed = {**source, "commit": pair[0], "schema": pair[1]}
        monkeypatch.setattr(host, "read_database", lambda _: json.dumps(observed))
        real_subprocess_run = host.subprocess.run
        monkeypatch.setattr(
            host.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=3)
        )
        journal = UpgradeJournal(root, receipt, source)
        assert (
            host.require_stopped_upgrade(
                filesystem_root=tmp_path, resume_binding=journal.resume_binding()
            )
            == observed
        )
        monkeypatch.setattr(host.subprocess, "run", real_subprocess_run)
        result = await upgrade.activate(receipt, source, url, filesystem_root=tmp_path)
        assert result["preservation_pass"] and result["commit"] == "b" * 40
        assert (
            json.loads((root / "upgrade-progress.json").read_text())["baseline"]
            == baseline
        )
        assert all(
            link.resolve() == Path(receipt[kind + "_release"])
            for kind, link in links.items()
        )
        assert (
            json.loads(environment.read_text().splitlines()[0].split("=", 1)[1])
            == "b" * 40
        )
        assert UpgradeJournal(root, receipt, source).done("complete")
    finally:
        await engine.dispose()
        await drop_disposable_database(name)


@pytest.mark.asyncio
async def test_preservation_orders_large_diagnostics_by_stable_identity(
    head_template_engine,
):
    async with head_template_engine.begin() as connection:
        await connection.execute(
            sa.text("""
            INSERT INTO brc_failure_diagnostics(diagnostic_id,stage,subject_id,reason_code,basis,occurred_at_ms)
            VALUES ('diag:z','observation','a','reason','{"context":"first"}',1000),
                   ('diag:a','observation','z','reason','{"context":"last"}',1001)
        """)
        )
        columns = [
            "diagnostic_id",
            "stage",
            "subject_id",
            "reason_code",
            "basis",
            "occurred_at_ms",
        ]
        result = await connection.execute(
            sa.text(
                upgrade.preservation_projection_sql("brc_failure_diagnostics", columns)
            )
        )
        rows = [json.loads(row) for row in result.scalars()]
        assert [row["diagnostic_id"] for row in rows] == ["diag:a", "diag:z"]
        assert [row["basis"] for row in rows] == [
            {"context": "last"},
            {"context": "first"},
        ]
