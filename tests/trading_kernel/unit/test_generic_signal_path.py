from __future__ import annotations

from decimal import Decimal

import pytest

from src.trading_kernel.domain.market import ClosedCandle
from src.trading_kernel.domain.shadow_outcome import (
    ShadowOutcomeSpec,
    evaluate_shadow_outcome,
)

HOUR = 3_600_000


def candle(index: int, high: str, low: str) -> ClosedCandle:
    return ClosedCandle(open_time_ms=index * HOUR, close_time_ms=(index + 1) * HOUR,
        open=Decimal(100), high=Decimal(high), low=Decimal(low), close=Decimal(100), volume=Decimal(1))


def spec(side: str = 'long') -> ShadowOutcomeSpec:
    return ShadowOutcomeSpec(shadow_outcome_id='shadow:signal', signal_event_id='signal:one',
        admission_decision_id=None, source_kind='signal_path', evaluation_kind='generic_signal_path_v1',
        exchange_instrument_id='binance-usdm:BTCUSDT:perpetual', position_side=side, timeframe='1h',
        entry_reference_price=Decimal(100), initial_stop_price=Decimal('95' if side == 'long' else '105'),
        horizon_start_ms=HOUR, horizon_end_ms=4 * HOUR, created_at_ms=HOUR,
        reference_at_ms=HOUR, price_basis='signal_closed_bar', path_spec_digest='sha256:'+'a'*64, source_runtime_commit='a'*40)


@pytest.mark.parametrize('side,first,stop', [('long','high','low'), ('short','low','high')])
def test_generic_signal_path_first_touch_and_full_horizon(side, first, stop):
    bars = (candle(1,'106' if side=='long' else '101','99' if side=='long' else '94'),
            candle(2,'125' if side=='long' else '106','94' if side=='long' else '75'),
            candle(3,'100','100'))
    result = evaluate_shadow_outcome(spec(side), bars)
    assert result.evaluation_kind == 'generic_signal_path_v1'
    assert result.mfe_r == Decimal(5)
    assert result.mae_r == Decimal('1.2')
    assert result.path_levels['1R'].first_touch_at_ms == 2*HOUR
    assert result.path_levels['3R'].first_touch_at_ms == 3*HOUR
    assert result.path_levels['5R'].first_touch_at_ms == 3*HOUR
    assert result.initial_stop_first_touch_at_ms == 3*HOUR
    assert result.path_levels['1R'].order_vs_stop == 'threshold_first'
    assert result.path_levels['3R'].order_vs_stop == 'same_bar_ambiguous'
    assert result.max_favorable_at_ms == 3*HOUR
    assert result.max_adverse_at_ms == 3*HOUR


def test_generic_signal_path_stop_before_later_rally_is_not_tradable_profit():
    bars=(candle(1,'101','94'),candle(2,'125','99'),candle(3,'100','100'))
    result=evaluate_shadow_outcome(spec(),bars)
    assert result.mfe_r == Decimal(5)
    assert result.path_levels['5R'].order_vs_stop == 'stop_first'


def test_generic_signal_path_requires_complete_closed_sequence():
    from src.trading_kernel.domain.shadow_outcome import (
        has_complete_closed_candle_sequence,
    )
    value=spec()
    assert has_complete_closed_candle_sequence(value,(candle(1,'101','99'),candle(2,'102','98'),candle(3,'103','97')))
    assert not has_complete_closed_candle_sequence(value,(candle(1,'101','99'),candle(3,'103','97')))
    from src.trading_kernel.domain.shadow_outcome import ShadowOutcomeUnavailable
    with pytest.raises(ShadowOutcomeUnavailable,match='incomplete_historical_window'):
        evaluate_shadow_outcome(value,(candle(1,'101','99'),candle(3,'103','97')))


def test_five_strategy_signal_builder_freezes_trigger_close_and_stop():
    from src.trading_kernel.application.project_shadow_outcome import (
        pending_generic_signal_path_spec,
    )
    from src.trading_kernel.domain.market import MarketSnapshot
    from src.trading_kernel.domain.signal import (
        SignalFactSnapshot,
        StrategySignal,
        build_signal_fact_digest,
    )
    from src.trading_kernel.domain.strategy_registry import (
        registered_strategy_contracts,
    )
    groups={"CPM-RO-001","MPG-001","MI-001","BRF2-001","SOR-1H-001"}
    for contract in registered_strategy_contracts():
        if contract.strategy_group_id not in groups:
            continue
        stop=Decimal('95' if contract.position_side=='long' else '105')
        definitions=(*contract.required_facts,*contract.disable_facts)
        facts=tuple(SignalFactSnapshot(fact_definition_id=d.fact_definition_id,role=d.role,
            value=str(stop) if d.role=='protection_reference' else '1' if d.role in {'identity_reference','lifecycle_reference'} else d.role!='disable',
            satisfied=d.role!='disable',observed_at_ms=HOUR,valid_until_ms=3*HOUR,
            projection_version=1) for d in definitions)
        signal=StrategySignal(signal_event_id='signal:'+contract.event_id,exposure_episode_id='episode:'+contract.event_id,
            runtime_scope_id='scope:'+contract.event_id,runtime_scope_version=1,strategy_group_id=contract.strategy_group_id,
            strategy_version_id=contract.strategy_version_id,event_spec_id=contract.event_spec_id,
            universe_version_id='universe:test',universe_semantic_digest='sha256:'+'b'*64,
            exchange_instrument_id='binance-usdm:BTCUSDT:perpetual',position_side=contract.position_side,
            fact_digest=build_signal_fact_digest(facts),occurred_at_ms=2*HOUR,observed_at_ms=2*HOUR,
            expires_at_ms=2*HOUR+1,facts=facts)
        snapshot=MarketSnapshot(exchange_instrument_id=signal.exchange_instrument_id,trigger_candle_close_time_ms=2*HOUR,
            candles_1h=(ClosedCandle(open_time_ms=HOUR,close_time_ms=2*HOUR,
                open=Decimal(100),high=Decimal(102),low=Decimal(98),close=Decimal(101),volume=Decimal(1)),))
        result=pending_generic_signal_path_spec(signal=signal,snapshot=snapshot,runtime_commit="a"*40)
        assert result.entry_reference_price==Decimal(101)
        assert result.initial_stop_price==stop
        assert result.horizon_end_ms==26*HOUR
        assert result.path_spec_digest and result.source_kind=='signal_path'
        with pytest.raises(ValueError,match='trigger closed candle'):
            pending_generic_signal_path_spec(signal=signal,snapshot=snapshot.model_copy(update={'candles_1h':()}),runtime_commit='a'*40)


@pytest.mark.parametrize('script',['configure_research_collection.py','read_signal_path.py'])
def test_research_cli_help_works_outside_repo_without_database(script,tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[3]
    result=subprocess.run([sys.executable,str(root/'scripts/trading_kernel'/script),'--help'],
        cwd=tmp_path,capture_output=True,text=True,timeout=10,check=False)
    assert result.returncode==0,result.stderr
    assert '--database-url' in result.stdout
