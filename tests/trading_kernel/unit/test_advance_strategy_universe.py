from __future__ import annotations

import importlib
import importlib.util
from types import SimpleNamespace

import pytest
from pydantic import ValidationError


@pytest.mark.parametrize(
    ("changed_field", "expected_reason"),
    (
        ("target_is_warming", "UNIVERSE_NOT_WARMING"),
        ("current_is_complete", "CURRENT_UNIVERSE_IDENTITY_CONFLICT"),
        ("event_is_active", "EVENT_AUTHORITY_CONFLICT"),
        ("members_are_complete", "UNIVERSE_MEMBER_IDENTITY_CONFLICT"),
        ("scopes_are_complete", "WARMING_SCOPE_IDENTITY_CONFLICT"),
        ("certifications_are_complete", "CERTIFICATION_MISSING"),
        ("certifications_are_eligible", "CERTIFICATION_NOT_ELIGIBLE"),
        ("certifications_are_fresh", "CERTIFICATION_STALE"),
        ("warm_readiness_is_complete", "WARM_READINESS_MISSING"),
        ("warm_readiness_is_fresh", "WARM_READINESS_STALE"),
        (
            "comparative_projection_is_complete",
            "COMPARATIVE_PROJECTION_INCOMPLETE",
        ),
    ),
)
def test_activation_readiness_decision_has_stable_fail_closed_precedence(
    changed_field: str,
    expected_reason: str,
) -> None:
    """Catches a persistence adapter inventing or reordering blocker semantics."""

    module = importlib.import_module(
        "src.trading_kernel.application.advance_strategy_universe"
    )
    assert hasattr(module, "UniverseActivationReadiness")
    assert hasattr(module, "activation_readiness_blocker")
    baseline = {
        "target_is_warming": True,
        "current_is_complete": True,
        "event_is_active": True,
        "members_are_complete": True,
        "scopes_are_complete": True,
        "certifications_are_complete": True,
        "certifications_are_eligible": True,
        "certifications_are_fresh": True,
        "warm_readiness_is_complete": True,
        "warm_readiness_is_fresh": True,
        "comparative_projection_is_required": True,
        "comparative_projection_is_complete": True,
    }
    baseline[changed_field] = False
    readiness = module.UniverseActivationReadiness(**baseline)

    assert module.activation_readiness_blocker(readiness) == expected_reason
    with pytest.raises(ValidationError):
        module.UniverseActivationReadiness(**baseline, bypass=True)


@pytest.mark.asyncio
async def test_activation_exposes_one_typed_db_only_application_boundary() -> None:
    """Catches an untyped activation request or a bypass around its repository."""

    module_spec = importlib.util.find_spec(
        "src.trading_kernel.application.advance_strategy_universe"
    )
    assert module_spec is not None
    module = importlib.import_module(
        "src.trading_kernel.application.advance_strategy_universe"
    )
    request = module.UniverseActivationRequest(
        universe_version_id="universe:sor-long:v2",
        attempted_at_ms=1_800_000_020_000,
    )
    expected = module.UniverseActivationResult(
        status=module.UniverseActivationStatus.ACTIVATED,
        reason_code=None,
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        universe_version_id=request.universe_version_id,
        previous_universe_version_id="universe:sor-long:v1",
        activation_generation=2,
        activated_at_ms=request.attempted_at_ms,
    )

    class _Repository:
        async def try_activate(self, actual_request: object) -> object:
            assert actual_request is request
            return expected

    actual = await module.advance_strategy_universe(
        SimpleNamespace(strategy_universes=_Repository()),
        request,
    )

    assert actual == expected
    with pytest.raises(ValidationError):
        module.UniverseActivationRequest(
            universe_version_id=request.universe_version_id,
            attempted_at_ms=0,
        )
    with pytest.raises(ValidationError):
        module.UniverseActivationRequest(
            **request.model_dump(mode="python"),
            allow_uncertified=True,
        )
