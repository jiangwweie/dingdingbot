from decimal import Decimal as D

import pytest

from src.trading_kernel.domain.exit_configuration import (
    EXIT_EVENTS,
    EventExitParameters,
    ExitConfigurationIntent,
    derive_exit_profile,
)
from src.trading_kernel.domain.exit_policy import registered_exit_profiles


def params(event=EXIT_EVENTS[0], **changes):
    p = {
        "event_spec_id": event,
        "expected_binding_id": "b",
        "expected_binding_revision": 1,
        "reward_multiple": "1",
        "target_fraction": ".05",
        "minimum_lift": True,
        "max_actual_fraction": ".5",
        "ma50_enabled": True,
    }
    p.update(changes)
    return EventExitParameters.model_validate(p)


@pytest.mark.parametrize(
    "updates",
    [
        {"reward_multiple": "0"},
        {"reward_multiple": "1.25"},
        {"reward_multiple": "5.1"},
        {"max_actual_fraction": ".51"},
        {"target_fraction": ".51"},
        {"target_fraction": "0"},
    ],
)
def test_unsupported_parameters_refuse(updates):
    with pytest.raises(ValueError):
        params(**updates)


def test_revision_inherits_every_uneditable_semantic():
    source = next(p for p in registered_exit_profiles() if p.position_side == "long")
    revision = derive_exit_profile(
        source=source, parameters=params(), revision_id="new"
    )
    assert revision.break_even_floor == source.break_even_floor
    assert revision.runner == source.runner
    assert revision.time_stop == source.time_stop
    assert revision.pre_tp1_guards == source.pre_tp1_guards
    assert revision.tp1.quantity_fraction == D(".05")
    assert "execution" not in source.model_dump(mode="json")


def test_sor_cannot_change_fraction_or_gain_minimum_lift():
    source = next(p for p in registered_exit_profiles() if p.position_side == "long")
    p = params(
        EXIT_EVENTS[4], minimum_lift=False, max_actual_fraction="1", ma50_enabled=False
    )
    with pytest.raises(ValueError, match="original quantity"):
        derive_exit_profile(source=source, parameters=p, revision_id="new")
    with pytest.raises(ValueError):
        params(EXIT_EVENTS[4])


def test_bundle_cannot_skip_or_duplicate_an_event():
    with pytest.raises(ValueError, match="six distinct"):
        ExitConfigurationIntent(
            account_id="account", expected_revision=0, events=(params(),) * 6
        )
