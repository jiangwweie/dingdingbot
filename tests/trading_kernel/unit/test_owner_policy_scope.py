from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.owner_policy import OwnerPolicyScope


def test_policy_scope_maps_crypto_and_tradfi_events_to_exact_profiles() -> None:
    scope = OwnerPolicyScope.model_validate(
        {
            "event_runtime_profiles": [
                {
                    "event_spec_id": "event_spec:SOR-001:SOR-LONG:v4",
                    "runtime_profile_id": "tiny-live-v1",
                },
                {
                    "event_spec_id": (
                        "event_spec:SOR-US-EQ-PERP-001:SOR-US-LONG-15M:v1"
                    ),
                    "runtime_profile_id": "tradfi-equity-usdm-v1",
                },
            ]
        }
    )

    assert scope.runtime_profile_for(
        "event_spec:SOR-001:SOR-LONG:v4"
    ) == "tiny-live-v1"
    assert scope.authorizes(
        event_spec_id="event_spec:SOR-US-EQ-PERP-001:SOR-US-LONG-15M:v1",
        runtime_profile_id="tradfi-equity-usdm-v1",
    )
    assert not scope.authorizes(
        event_spec_id="event_spec:SOR-US-EQ-PERP-001:SOR-US-LONG-15M:v1",
        runtime_profile_id="tiny-live-v1",
    )


@pytest.mark.parametrize(
    "entries",
    (
        [
            {
                "event_spec_id": "event_spec:z",
                "runtime_profile_id": "profile-main",
            },
            {
                "event_spec_id": "event_spec:a",
                "runtime_profile_id": "profile-main",
            },
        ],
        [
            {
                "event_spec_id": "event_spec:a",
                "runtime_profile_id": "profile-main",
            },
            {
                "event_spec_id": "event_spec:a",
                "runtime_profile_id": "profile-other",
            },
        ],
    ),
)
def test_policy_scope_rejects_order_drift_and_duplicate_event_authority(
    entries: list[dict[str, str]],
) -> None:
    with pytest.raises(ValidationError):
        OwnerPolicyScope.model_validate({"event_runtime_profiles": entries})
