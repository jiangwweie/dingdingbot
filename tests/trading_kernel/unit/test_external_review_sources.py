from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.fee_valuation import (
    FeeValuationEvidence,
    NativeFee,
    value_native_fee,
)
from src.trading_kernel.domain.review import ReviewFill


def values():
    return {'exchange_trade_id':'manual-trade', 'exchange_order_id':'manual-order',
        'role':'exit', 'quantity':Decimal(16406), 'price':Decimal('.0678'),
        'fee':value_native_fee(native_fee=NativeFee(asset='USDT', amount=Decimal('.2')), valuation_evidence=FeeValuationEvidence(method="native_usdt",rate_usdt_per_asset=Decimal(1),price_pair=None,observed_at_ms=None,valued_at_ms=2000)),
        'realized_pnl_quote':Decimal(1), 'occurred_at_ms':2000}


def test_verified_external_fill_has_evidence_without_fabricated_command():
    fill = ReviewFill(**values(), command_id=None, external_evidence_id='evidence:app-exit')
    attributed = fill.to_attributed_trade_fill()
    assert attributed.command_id is None
    assert attributed.external_evidence_id == 'evidence:app-exit'


@pytest.mark.parametrize('command,evidence', [(None,None),('cmd','ev')])
def test_review_source_is_exclusive(command,evidence):
    with pytest.raises(ValidationError):
        ReviewFill(**values(), command_id=command, external_evidence_id=evidence)
