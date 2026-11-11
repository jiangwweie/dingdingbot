import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.operational_evidence import FailureDiagnostic


def test_failure_identity_retains_each_attempt_and_never_contains_credentials():
    common = {'stage':'certification', 'subject_id':'DOGE', 'reason_code':'projected_position_exceeds_venue',
        'basis':{'projected_quantity':'32811','venue_quantity':'16406'}, 'occurred_at_ms':1000}
    first = FailureDiagnostic(**common)
    assert first.identity() == FailureDiagnostic(**common).identity()
    assert first.identity() != first.model_copy(update={'occurred_at_ms':1001}).identity()
    for bad in ({'api_key':'hidden'}, {'nested':{'signature':'hidden'}}, {'safe':'x'*13000}):
        with pytest.raises(ValidationError):
            FailureDiagnostic(**{**common,'basis':bad})
