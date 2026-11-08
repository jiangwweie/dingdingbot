import pytest

from scripts.trading_kernel.prepare_manual_release import build_preparation
from src.trading_kernel.domain.product_identity import ManualReleaseBinding


def test_preparation_never_authorizes_deployment_without_live_acceptance():
    plan = build_preparation(commit='a' * 40, schema_revision='0017_app_management_observation')
    assert plan['product_id'] == 'brc-app-manual-v1'
    assert plan['deployment_authorized'] is False
    assert plan['server_binding'] == 'missing'
    assert 'real_app_protocol_acceptance' in plan['remaining_gates']


def test_preparation_rejects_other_candidate_even_when_target_matches_itself():
    binding = ManualReleaseBinding(product_id='brc-app-manual-v1', ssh_target='manual-test',
        machine_id='a' * 32, venue_id='binance-usdm', account_id='manual-only',
        exchange_account_uid='12345', database_name='manual-db', database_system_identifier='123456',
        release_commit='b' * 40, schema_revision='0017_app_management_observation')
    with pytest.raises(ValueError, match='candidate'):
        build_preparation(commit='a' * 40, schema_revision='0017_app_management_observation',
            expected=binding, observed=binding)
