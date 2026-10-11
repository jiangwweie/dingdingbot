"""Freeze the engineering workload before running the resident soak."""

from decimal import Decimal
from itertools import pairwise

import pytest

from src.trading_kernel.domain.generic_selection_core import compute_generic_selection
from tests.trading_kernel.support.generic_selection import HOUR
from tests.trading_kernel.support.generic_selection_soak import (
    SOAK_CUTOFF,
    SOAK_GROUPS,
    SoakResourceFacts,
    SoakWorkload,
    percentile95,
    vacuum_time_union_ms,
)

CUTOFF = SOAK_CUTOFF


def test_soak_workload_freezes_nonempty_churn_and_real_predecessors() -> None:
    workload = SoakWorkload()
    expected = {
        "MPG-001": (24, 19, 19, 21),
        "MI-001": (24, 19, 19, 15),
        "CPM-RO-001": (6, 11, 11, 6),
        "BRF2-001": (6, 19, 19, 6),
    }
    for group in SOAK_GROUPS:
        prior = None
        additions = removals = changes = periods = 0
        cadence = workload.spec(group).cadence_hours
        for hour in range(-12, 25):
            if hour % cadence:
                continue
            snapshot = compute_generic_selection(workload.selection_input(
                group, cutoff_ms=CUTOFF+hour*HOUR, predecessor=prior,
            ))
            assert len(snapshot.members) == 24 and snapshot.ready_count == 24
            assert snapshot.selected_members
            if hour > 0:
                periods += 1
                additions += len(set(snapshot.selected_members)-set(prior.selected_members))
                removals += len(set(prior.selected_members)-set(snapshot.selected_members))
                changes += snapshot.selected_members != prior.selected_members
            prior = snapshot
        assert (periods, additions, removals, changes) == expected[group]
    assert len(workload.semantic_digest) == 71
    assert workload.semantic_digest == SoakWorkload().semantic_digest


def test_soak_overlapping_source_windows_are_the_same_closed_market_path() -> None:
    workload = SoakWorkload()
    for group in SOAK_GROUPS:
        first = workload.selection_input(group, cutoff_ms=CUTOFF)
        step = workload.spec(group).cadence_hours
        next_input = workload.selection_input(group, cutoff_ms=CUTOFF+step*HOUR)
        for left, right in zip(first.member_windows, next_input.member_windows, strict=True):
            assert left.candles[step:] == right.candles[:-step]
        assert all(c.close_time_ms <= CUTOFF for w in first.member_windows for c in w.candles)


def test_soak_metrics_do_not_hide_overlap_or_small_sample_latency() -> None:
    assert percentile95((1, 2, 100)) == 100
    assert percentile95(()) is None
    assert vacuum_time_union_ms(((0, 10), (5, 20), (30, 40)), start_ms=8, end_ms=35) == 17
    with pytest.raises(ValueError, match="interval"):
        vacuum_time_union_ms(((20, 10),), start_ms=0, end_ms=30)


def test_soak_tape_covers_full_four_hour_warming_without_future_bars() -> None:
    workload = SoakWorkload()
    for member in workload.spec("CPM-RO-001").candidate_ids:
        for close in (CUTOFF, CUTOFF+24*HOUR):
            path = workload.candles(member, close_ms=close, count=100)
            assert len(path)==100 and path[-1].close_time_ms==close
            assert all(right.open_time_ms==left.close_time_ms for left,right in pairwise(path))
            assert all(c.low<=min(c.open,c.close)<=max(c.open,c.close)<=c.high for c in path)


def test_soak_resource_claim_requires_actual_cgroup_limits() -> None:
    facts = SoakResourceFacts.from_cgroup(cpu_max="100000 100000", memory_max="1073741824")
    assert facts.cpu_cores == Decimal(1) and facts.memory_limit_bytes == 1024**3
    for cpu, memory in (("max 100000", "1073741824"), ("100000 100000", "max"),
                        ("200000 100000", "1073741824"), ("100000 100000", "2147483648")):
        with pytest.raises(ValueError, match="resource"):
            SoakResourceFacts.from_cgroup(cpu_max=cpu, memory_max=memory)
