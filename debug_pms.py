import asyncio, tempfile, yaml, json, traceback
from pathlib import Path
from decimal import Decimal

from src.interfaces.api import app, set_dependencies
from src.application.config_manager import ConfigManager
from src.infrastructure.signal_repository import SignalRepository
from src.domain.models import AccountSnapshot
from fastapi.testclient import TestClient

with tempfile.TemporaryDirectory() as tmpdir:
    config_dir = Path(tmpdir)
    db_path = str(config_dir / 'test.db')

    core_config = {
        'core_symbols': ['ETH/USDT:USDT'],
        'pinbar_defaults': {'min_wick_ratio': '0.6', 'max_body_ratio': '0.3', 'body_position_tolerance': '0.1'},
        'ema': {'period': 60},
        'mtf_mapping': {'15m': '1h', '1h': '4h', '4h': '1d'},
        'warmup': {'history_bars': 100},
        'signal_pipeline': {'cooldown_seconds': 14400},
    }
    with open(config_dir / 'core.yaml', 'w') as f:
        yaml.dump(core_config, f)
    user_config = {
        'exchange': {'name': 'binance', 'api_key': 'test_key', 'api_secret': 'test_secret', 'testnet': True},
        'user_symbols': [],
        'timeframes': ['1h'],
        'strategy': {'trend_filter_enabled': True, 'mtf_validation_enabled': True},
        'risk': {'max_loss_percent': '0.01', 'max_leverage': 10},
        'notification': {'channels': [{'type': 'feishu', 'webhook_url': 'https://open.feishu.cn/open-apis/bot/v2/hook/test123'}]},
    }
    with open(config_dir / 'user.yaml', 'w') as f:
        yaml.dump(user_config, f)

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS strategies (id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS risk_configs (id TEXT PRIMARY KEY DEFAULT 'global', max_loss_percent DECIMAL(5,4) NOT NULL DEFAULT 0.01, max_leverage INTEGER NOT NULL DEFAULT 10);
        CREATE TABLE IF NOT EXISTS system_configs (id TEXT PRIMARY KEY DEFAULT 'global', core_symbols TEXT NOT NULL DEFAULT '["ETH/USDT:USDT"]', timeframes TEXT NOT NULL DEFAULT '["1h"]');
        CREATE TABLE IF NOT EXISTS symbols (symbol TEXT PRIMARY KEY, is_active BOOLEAN DEFAULT TRUE);
        CREATE TABLE IF NOT EXISTS notifications (id TEXT PRIMARY KEY, channel_type TEXT NOT NULL, webhook_url TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS config_snapshots (id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS exchange_configs (id TEXT PRIMARY KEY DEFAULT 'primary', exchange_name TEXT NOT NULL DEFAULT 'binance', api_key TEXT NOT NULL, api_secret TEXT NOT NULL, testnet BOOLEAN DEFAULT TRUE);
        CREATE TABLE IF NOT EXISTS config_history (id INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, action TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL, direction TEXT NOT NULL, entry_price TEXT NOT NULL, stop_loss TEXT NOT NULL, position_size TEXT NOT NULL, leverage INTEGER NOT NULL, tags_json TEXT NOT NULL DEFAULT '[]', risk_info TEXT NOT NULL, status TEXT DEFAULT 'PENDING');
    ''')
    conn.commit()
    conn.close()

    async def setup():
        mgr = ConfigManager(config_dir=str(config_dir), db_path=db_path)
        await mgr.initialize_from_db()
        await mgr.import_from_yaml(str(config_dir / 'core.yaml'), changed_by='test')
        await mgr.import_from_yaml(str(config_dir / 'user.yaml'), changed_by='test')
        repo = SignalRepository(db_path=db_path, connection=mgr._db)
        await repo.initialize()
        return mgr, repo
    mgr, repo = asyncio.run(setup())

    class MockGW:
        def set_global_order_callback(self, cb): pass
        async def fetch_historical_ohlcv(self, symbol, timeframe, limit=100):
            from src.domain.models import KlineData
            base = Decimal('3000') if 'ETH' in symbol else Decimal('100')
            klines = []
            for i in range(limit):
                ts = 1700000000000 + (i * 3600 * 1000)
                price = base + Decimal(str(i)) * Decimal('10')
                klines.append(KlineData(symbol=symbol, timeframe=timeframe, timestamp=ts,
                    open=price, high=price*Decimal('1.02'), low=price*Decimal('0.98'),
                    close=price*Decimal('1.01'), volume=Decimal('1000'), is_closed=True))
            return klines
    mock_gw = MockGW()
    set_dependencies(repository=repo, account_getter=lambda: AccountSnapshot(total_balance=Decimal('10000'), available_balance=Decimal('10000'), unrealized_pnl=Decimal('0'), positions=[], timestamp=1700000000000), config_manager=mgr, exchange_gateway=mock_gw)

    payload = {
        'symbol': 'ETH/USDT:USDT',
        'timeframe': '1h',
        'limit': 50,
        'mode': 'v3_pms',
        'initial_balance': '10000',
        'slippage_rate': '0.001',
        'fee_rate': '0.0004',
        'strategies': [
            {
                'id': 'test-strategy-01',
                'name': '01',
                'triggers': [{'type': 'pinbar', 'params': {'min_wick_ratio': 0.5, 'max_body_ratio': 0.35, 'body_position_tolerance': 0.2}}],
                'filters': [
                    {'type': 'ema_trend', 'params': {'period': 60}},
                    {'type': 'atr', 'params': {'period': 14, 'min_atr_ratio': 0.5}},
                    {'type': 'mtf', 'params': {}},
                ],
                'filter_logic': 'AND',
                'apply_to': ['ETH/USDT:USDT:1h'],
            }
        ],
    }

    print('Sending PMS backtest request...')
    try:
        with TestClient(app) as client:
            resp = client.post('/api/backtest/orders', json=payload, timeout=60)
            print('PMS Status:', resp.status_code)
            data = resp.json()
            if 'error' in data:
                print('ERROR:', data['error'])
            else:
                r = data.get('report', {})
                print('Total trades:', r.get('total_trades'))
                print('Positions:', len(r.get('positions', [])))
    except Exception as e:
        print('EXCEPTION:', type(e).__name__, str(e))
        traceback.print_exc()
