#!/usr/bin/env python3
"""
Test signal 291 with copied database
"""
import asyncio
import sys
sys.path.insert(0, '/Users/jiangwei/Documents/v2')

from src.infrastructure.signal_repository import SignalRepository

async def test():
    repo = SignalRepository('data/signals.db')
    await repo.initialize()
    signal = await repo.get_signal_by_id('291')
    if signal:
        print('Signal 291:')
        print(f"  kline_timestamp: {signal.get('kline_timestamp')}")
        print(f"  symbol: {signal.get('symbol')}")
        print(f"  timeframe: {signal.get('timeframe')}")
        print(f"  direction: {signal.get('direction')}")
        print(f"  entry_price: {signal.get('entry_price')}")
    else:
        print('Signal 291 not found')
    await repo.close()

if __name__ == '__main__':
    asyncio.run(test())
