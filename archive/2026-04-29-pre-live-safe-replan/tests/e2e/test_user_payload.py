import pytest
import tempfile
from pathlib import Path
import yaml
from fastapi.testclient import TestClient

from src.application.config_manager import ConfigManager
from src.interfaces.api import app, set_dependencies
from tests.e2e.test_phasek_dynamic_rules import MockExchangeGateway, mock_repository

@pytest.fixture
def temp_config_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        core_config = {
            "core_symbols": ["BTC/USDT:USDT"],
            "pinbar_defaults": {"min_wick_ratio": "0.6", "max_body_ratio": "0.3", "body_position_tolerance": "0.1"},
            "ema": {"period": 60},
            "mtf_mapping": {"15m": "1h", "1h": "4h", "4h": "1d"},
            "warmup": {"history_bars": 100},
            "signal_pipeline": {"cooldown_seconds": 14400},
        }
        with open(config_dir / "core.yaml", "w") as f: yaml.dump(core_config, f)
        
        user_config = {
            "exchange": {"name": "binance", "api_key": "test_api_key", "api_secret": "test_secret", "testnet": True},
            "user_symbols": [],
            "timeframes": ["15m", "1h"],
            "active_strategies": [],
            "risk": {"max_loss_percent": "0.01", "max_leverage": 10},
            "asset_polling": {"interval_seconds": 60},
            "notification": {"channels": [{"type": "feishu", "webhook_url": "https://test.com"}]},
        }
        with open(config_dir / "user.yaml", "w") as f: yaml.dump(user_config, f)
        yield config_dir

@pytest.fixture
def test_client(temp_config_dir, mock_repository):
    manager = ConfigManager(temp_config_dir)
    manager.load_core_config()
    manager.load_user_config()
    manager.merge_symbols()

    gateway = MockExchangeGateway()
    
    from src.domain.models import AccountSnapshot
    from decimal import Decimal
    def mock_account_getter():
        return AccountSnapshot(
            total_balance=Decimal("10000"),
            available_balance=Decimal("10000"),
            unrealized_pnl=Decimal("0"),
            positions=[],
            timestamp=1700000000000,
        )

    set_dependencies(
        repository=mock_repository,
        account_getter=mock_account_getter,
        config_manager=manager,
        exchange_gateway=gateway,
    )

    with TestClient(app) as client:
        yield client

def test_user_exact_payload(test_client):
    payload = {"symbol":"BTC/USDT:USDT","timeframe":"1h","start_time":1773573060000,"end_time":1774350660000,"strategies":[{"id":"1774350722661-pqn43lyj1","name":"新策略 1","trigger":{"id":"1774350722661-xtopzi51d","type":"pinbar","enabled":True,"params":{"min_wick_ratio":0.6,"max_body_ratio":0.3,"body_position_tolerance":0.1}},"filters":[{"id":"1774350726379-9vm40zs2e","type":"volatility_filter","enabled":True,"params":{"min_atr_ratio":0.5,"max_atr_ratio":3,"atr_period":14}}],"filter_logic":"AND"}],"risk_overrides":{"max_loss_percent":0.02,"max_leverage":10,"default_leverage":5}}
    
    response = test_client.post("/api/backtest", json=payload)
    assert response.status_code == 200, f"Error: {response.text}"
    print("\nSUCCESS! Response:", response.json())
