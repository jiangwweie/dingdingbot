from decimal import Decimal

from src.trading_kernel.application.owner_console.exit_attribution import classify_exit
from src.trading_kernel.application.owner_console.models import PerformanceQuery
from src.trading_kernel.application.owner_console.performance import (
    build_performance_summary,
    sample_from_trade,
)
from src.trading_kernel.application.owner_console.trades import build_trade_item
from tests.trading_kernel.unit.owner_console.factories import trade_item_facts


def sample(ticket, net, reason):
    facts = trade_item_facts()
    metrics = dict(facts.review_metrics)
    metrics["net_pnl_quote"] = net
    item = build_trade_item(facts.model_copy(update={"review_metrics": metrics}))
    return sample_from_trade(
        item.model_copy(update={"ticket_id": ticket, "exit_reason": reason}),
        "version:1",
    )


def test_full_window_totals_partition_exactly_and_do_not_guess_unknown_exits():
    q = PerformanceQuery(from_ms=1, to_ms=100000)
    result = build_performance_summary(
        (
            sample("a", "10", "initial_stop_triggered"),
            sample("b", "3", "owner_flatten_all:auth:1"),
            sample("c", "-2", None),
        ),
        q,
    )
    assert result.sample_count == 3
    assert result.verified_totals.net_pnl.value == Decimal(11)
    assert result.breakdown["strategy"].verified_totals.net_pnl.value == Decimal(10)
    assert result.breakdown["owner"].verified_totals.net_pnl.value == Decimal(3)
    assert result.breakdown["unknown"].verified_totals.net_pnl.value == Decimal(-2)
    assert classify_exit(None) == "unknown"
    assert classify_exit("future_new_reason") == "unknown"
    assert classify_exit("initial_stop_rejected") == "safety"
    assert result.time_basis == "terminal"


def test_snapshot_ignores_pagination_but_changes_for_review_revision():
    q = PerformanceQuery(from_ms=1, to_ms=100000)
    a = sample("a", "10", "initial_stop_triggered")
    assert (
        build_performance_summary((a,), q).snapshot_id
        == build_performance_summary(
            (a,), q.model_copy(update={"limit": 1, "cursor": "ignored"})
        ).snapshot_id
    )
    b = a.model_copy(update={"review_revision": 2})
    assert (
        build_performance_summary((a,), q).snapshot_id
        != build_performance_summary((b,), q).snapshot_id
    )


def test_money_sum_preserves_80_digits_and_unknown_funding_is_not_zero():
    q = PerformanceQuery(from_ms=1, to_ms=100000)
    result = build_performance_summary(
        (
            sample("a", "1000000000000000000000000000000", "initial_stop_triggered"),
            sample("b", "0.01", "initial_stop_triggered"),
            sample("c", "-1000000000000000000000000000000", "initial_stop_triggered"),
        ),
        q,
    )
    assert result.verified_totals.net_pnl.value == Decimal("0.01")


def test_unknown_funding_and_empty_windows_do_not_fabricate_zero_net():
    q=PerformanceQuery(from_ms=1,to_ms=100000)
    known=sample('a','4.5','strategy_exit')
    unknown=known.model_copy(update={'ticket_id':'b','economics':known.economics.model_copy(update={'funding':known.economics.funding.model_copy(update={'value':None,'unavailable_reason':'funding_unavailable'}),'net_pnl':known.economics.net_pnl.model_copy(update={'value':None,'unavailable_reason':'funding_unavailable'}),'net_r':known.economics.net_r.model_copy(update={'value':None,'unavailable_reason':'funding_unavailable'})})})
    result=build_performance_summary((known,unknown),q)
    assert result.verified_totals.net_pnl.value==Decimal('4.5')
    assert result.metric_coverage['net_pnl'].available_count==1
    assert result.metric_coverage['fees'].available_count==2
    assert result.confirmed_count==1
    assert build_performance_summary((unknown,),q).verified_totals.net_pnl.value is None
    assert build_performance_summary((),q).verified_totals.net_pnl.value is None


def test_partition_sum_preserves_actual_income_and_scope_totals():
    q=PerformanceQuery(from_ms=1,to_ms=100000)
    samples=(sample('a','10','strategy_exit'),sample('b','-2','owner_flatten_all:auth:1'),sample('c','1','initial_stop_rejected'),sample('d','-0.5',None))
    all_income=build_performance_summary(samples,q)
    assert sum((part.verified_totals.net_pnl.value for part in all_income.breakdown.values()),Decimal(0))==all_income.verified_totals.net_pnl.value
    owner=build_performance_summary(samples,q.model_copy(update={'exit_scope':'owner'}))
    assert owner.sample_count==1 and owner.verified_totals.net_pnl.value==Decimal(-2)
