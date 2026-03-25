import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from src.interfaces.api import app

def run():
    payload = {
        "symbol":"BTC/USDT:USDT",
        "timeframe":"1h",
        "start_time":1773573060000,
        "end_time":1774350660000,
        "strategies":[{
            "id":"1774350722661-pqn43lyj1",
            "name":"新策略 1",
            "trigger":{
                "id":"1774350722661-xtopzi51d",
                "type":"pinbar",
                "enabled":True,
                "params":{
                    "min_wick_ratio":0.6,
                    "max_body_ratio":0.3,
                    "body_position_tolerance":0.1
                }
            },
            "filters":[{
                "id":"1774350726379-9vm40zs2e",
                "type":"volatility_filter",
                "enabled":True,
                "params":{
                    "min_atr_ratio":0.5,
                    "max_atr_ratio":3,
                    "atr_period":14
                }
            }],
            "filter_logic":"AND"
        }],
        "risk_overrides":{
            "max_loss_percent":0.02,
            "max_leverage":10,
            "default_leverage":5
        }
    }

    # Using 'with' triggers the FastAPI lifespan startup/shutdown events
    with TestClient(app) as client:
        print("Sending POST request to /api/backtest...")
        response = client.post("/api/backtest", json=payload)
        print("STATUS:", response.status_code)
        try:
            print("JSON:", response.json())
        except:
            print("TEXT:", response.text)

if __name__ == "__main__":
    run()
