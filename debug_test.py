import asyncio
import sys
import os

# Ensure the src module is in path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from src.interfaces.api import app
from src.application.config_manager import ConfigManager
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.signal_repository import SignalRepository
from src.interfaces.api import set_dependencies
from decimal import Decimal
from src.domain.models import AccountSnapshot

class MockExchange:
    def __init__(self):
        self.call_count = 0
    async def fetch_historical_ohlcv(self, *args, **kwargs):
        self.call_count += 1
        return []

def run():
    # Setup mock dependencies
    cm = ConfigManager("not_exist")
    # minimal setup
    
    # Just test the bare endpoint
    client = TestClient(app)
    payload = {
        "symbol": "BTC/USDT:USDT",
        "timeframe": "15m",
        "limit": 50,
    }
    response = client.post("/api/backtest", json=payload)
    print("STATUS:", response.status_code)
    print("JSON:", response.json())

if __name__ == "__main__":
    run()
