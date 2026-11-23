"""Recovery refuses identity drift, new exposure and unrelated incidents."""
import pytest

from scripts.trading_kernel.tokyo_postfill_maintenance import (
    ACCOUNT,
    SCHEMA,
    SOURCE,
    TICKET,
    validate_source,
)


def basis():
    return dict(commit=SOURCE,schema=SCHEMA,account=ACCOUNT,policy=3,entry=False,tickets=[TICKET],unknown=False,other_incidents=False)


@pytest.mark.parametrize('field,value', [('commit','foreign'),('schema','0025_directional_sor'),('account','other'),('policy',4),('entry',True),('tickets',[]),('tickets',[TICKET,'other']),('unknown',True),('other_incidents',True)])
def test_recovery_refuses_source_drift(field,value):
    row=basis();row[field]=value
    with pytest.raises(ValueError):
        validate_source(row)


def test_exact_stopped_source_is_eligible_for_proof_collection():
    validate_source(basis())
