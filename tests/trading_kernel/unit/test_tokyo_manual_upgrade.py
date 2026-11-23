import pytest

from scripts.trading_kernel.tokyo_manual_upgrade import validate_binding


def basis():
    return {'machine_id':'1c3442ab300e405e945a469ed8a12593','account_id':'owner-subaccount-runtime-v0','database':'brc_trading_kernel','system_identifier':'7710109570187497514','uid':'1244153647'}


@pytest.mark.parametrize('field', list(basis()))
def test_tokyo_upgrade_refuses_any_foreign_identity(field):
    row=basis();row[field]='foreign'
    with pytest.raises(ValueError):
        validate_binding(row)


def test_tokyo_upgrade_accepts_only_the_retained_manual_database():
    validate_binding(basis())
