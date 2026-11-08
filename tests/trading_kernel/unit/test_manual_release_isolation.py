from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.owner_console import deploy_release as owner
from scripts.owner_console.certify_release_candidate import (
    build_owner_api_certification_identity,
)
from scripts.owner_console.certify_static_release_candidate import (
    build_owner_static_certification_identity,
)
from scripts.trading_kernel import deploy_tokyo_release as kernel
from scripts.trading_kernel.certify_release_candidate import (
    build_certification_identity,
)


@pytest.mark.parametrize('target', ['tokyo', 'root@tokyo', 'new-manual'])
@pytest.mark.parametrize('backend_class', [kernel.SshTokyoReleaseBackend, owner.SshOwnerConsoleReleaseBackend])
def test_manual_artifact_cannot_invoke_inherited_remote_deployer(monkeypatch, target, backend_class):
    run = Mock(side_effect=AssertionError('remote process must not start'))
    monkeypatch.setattr(kernel.subprocess, 'run', run)
    backend = backend_class(target=target, repo_root=Path('.'), timeout_seconds=1)
    with pytest.raises(ValueError, match='manual product'):
        backend._ssh_base()
    run.assert_not_called()


@pytest.mark.parametrize('builder', [build_certification_identity, build_owner_api_certification_identity, build_owner_static_certification_identity])
def test_every_surface_certification_binds_manual_product(builder):
    assert builder('a' * 40)['product_id'] == 'brc-app-manual-v1'


@pytest.mark.asyncio
@pytest.mark.parametrize('product_id', [None, 'brc-auto-tokyo-v1', 'brc-app-manual-v1'])
async def test_writer_requires_certified_product_identity(product_id):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.trading_kernel.application.ports import RuntimeCapabilitySnapshot
    from src.trading_kernel.application.runtime_fence import runtime_writer_is_certified
    capability = RuntimeCapabilitySnapshot.model_validate({
        'capability_key': 'exchange_commands', 'enabled': True,
        'certified_commit': 'a' * 40, 'schema_revision': '0017_app_management_observation',
        'certification': {} if product_id is None else {'product_id': product_id},
    }, extra='ignore')
    uow = SimpleNamespace(signals=SimpleNamespace(get_runtime_capability=AsyncMock(return_value=capability)),
        incidents=SimpleNamespace(add=AsyncMock(), resolve=AsyncMock()))
    @asynccontextmanager
    async def factory():
        yield uow
    allowed = await runtime_writer_is_certified(factory, worker_id='test',
        runtime_commit='a' * 40, schema_revision='0017_app_management_observation', observed_at_ms=1000)
    assert allowed is (product_id == 'brc-app-manual-v1')
    assert uow.incidents.add.await_count == (0 if allowed else 1)


@pytest.mark.parametrize('identity', [None, 'brc-auto-tokyo-v1'])
def test_auto_environment_cannot_construct_manual_live_runtime(identity):
    from src.trading_kernel.infrastructure.production_runtime import (
        ProductionRuntimeSettings,
    )
    values = {'TRADING_KERNEL_ENVIRONMENT': 'live', 'TRADING_KERNEL_VENUE_ID': 'binance-usdm',
        'TRADING_KERNEL_ACCOUNT_ID': 'separate-manual', 'TRADING_KERNEL_ACCOUNT_POSITION_MODE': 'independent_sides',
        'TRADING_KERNEL_API_KEY': 'test-only', 'TRADING_KERNEL_API_SECRET': 'test-only',
        'TRADING_KERNEL_TIMEOUT_SECONDS': '5', 'TRADING_KERNEL_EXIT_TAKER_FEE_RATE': '0.0005'}
    if identity is not None:
        values['TRADING_KERNEL_PRODUCT_ID'] = identity
    with pytest.raises(ValueError, match='product'):
        ProductionRuntimeSettings.from_environment(values)


@pytest.mark.parametrize('field,wrong', [
    ('ssh_target', 'other-host'), ('machine_id', 'b' * 32),
    ('account_id', 'other-account'), ('exchange_account_uid', '99999'),
    ('database_name', 'auto-db'), ('database_system_identifier', '999999'),
    ('release_commit', 'b' * 40), ('schema_revision', '0015_generic_owner_recovery_v1'),
])
def test_local_release_binding_requires_every_identity(field, wrong):
    from src.trading_kernel.domain.product_identity import (
        ManualReleaseBinding,
        require_manual_release_identity,
    )
    expected = ManualReleaseBinding(product_id='brc-app-manual-v1', ssh_target='manual-test',
        machine_id='a' * 32, venue_id='binance-usdm', account_id='independent-manual',
        exchange_account_uid='12345', database_name='manual-db', database_system_identifier='123456',
        release_commit='a' * 40, schema_revision='0017_app_management_observation')
    require_manual_release_identity(expected, expected)
    with pytest.raises(ValueError, match='identity mismatch'):
        require_manual_release_identity(expected, expected.model_copy(update={field: wrong}))


@pytest.mark.asyncio
async def test_legacy_cutover_runner_refuses_remote_command_and_archive(monkeypatch):
    from pathlib import PurePosixPath
    from unittest.mock import AsyncMock

    from src.trading_kernel.infrastructure import tokyo_cutover_adapter as old
    runner = old.SshCommandRunner(target='tokyo', timeout_seconds=1)
    start = AsyncMock(side_effect=AssertionError('no process'))
    archive = Mock(side_effect=AssertionError('no archive process'))
    monkeypatch.setattr(old.asyncio, 'create_subprocess_exec', start)
    monkeypatch.setattr(old.subprocess, 'Popen', archive)
    with pytest.raises(ValueError, match='manual product'):
        await runner.run(('sudo', 'systemctl', 'stop', 'brc-trading-kernel-entry-worker.service'))
    with pytest.raises(ValueError, match='manual product'):
        await runner.upload_git_archive(repo_root=Path('.'), commit='a' * 40, destination=PurePosixPath('/opt/brc'))
    start.assert_not_awaited()
    archive.assert_not_called()


def test_required_order_coverage_keeps_regular_and_conditional_namespaces():
    from src.trading_kernel.application.management_intents import (
        accepted_order_identities,
    )
    rows = [
        {'status': 'accepted', 'command_kind': 'take_profit', 'result_payload': {'exchange_order_id': '123'},
         'request_payload': {'order_type': 'limit'}},
        {'status': 'accepted', 'command_kind': 'initial_stop', 'result_payload': {'exchange_order_id': '123'},
         'request_payload': {'order_type': 'stop_market'}},
    ]
    assert accepted_order_identities(rows) == frozenset({('regular', '123'), ('conditional', '123')})
