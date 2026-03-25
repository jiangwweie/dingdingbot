# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Cryptocurrency Signal Monitoring System** - A Python backend service that monitors crypto markets via WebSocket, detects Pinbar candlestick patterns with EMA60 trend filtering and multi-timeframe (MTF) validation, and sends risk calculations to notification channels (Feishu/WeCom).

**Core Principle: Zero Execution Policy** - The system is read-only and must never integrate any trading execution interfaces.

## Quick Start

```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run tests
pytest tests/unit/ -v

# Run the application
python src/main.py
```

## Tech Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI + asyncio
- **Exchange Integration**: CCXT (async_support) + CCXT.Pro (WebSocket)
- **Data Validation**: Pydantic v2
- **Precision**: `decimal.Decimal` for all financial calculations (never `float`)
- **Testing**: pytest + pytest-asyncio

## Architecture (Clean Architecture)

```
src/
├── domain/                     # Core business logic, NO external I/O dependencies
│   ├── models.py               # Pydantic models (KlineData, SignalResult, etc.)
│   ├── exceptions.py           # Unified exception classes with error codes
│   ├── indicators.py           # EMA streaming calculation (EMACalculator)
│   ├── strategy_engine.py      # Pinbar detection + EMA filtering + MTF validation
│   └── risk_calculator.py      # Position sizing with Decimal precision
│
├── application/                # Application services
│   ├── config_manager.py       # Load/merge core.yaml + user.yaml, API key permission check
│   └── signal_pipeline.py      # K-line → Strategy → Risk → Notification
│
├── infrastructure/             # All I/O operations
│   ├── exchange_gateway.py     # CCXT REST warmup + WebSocket subscription + asset polling
│   ├── notifier.py             # Feishu/WeCom webhook push
│   └── logger.py               # Unified logging with secret masking
│
├── interfaces/                 # REST API endpoints (future expansion)
│   └── api.py
│
└── main.py                     # Entry point: config → permission check → warmup → WS → polling

config/
├── core.yaml                   # System config (core symbols: BTC, ETH, SOL, BNB)
└── user.yaml                   # User config (custom symbols, API keys, switches)

tests/
└── unit/
    ├── test_config_manager.py
    ├── test_exchange_gateway.py
    ├── test_notifier.py
    ├── test_indicators.py
    ├── test_strategy_engine.py
    └── test_risk_calculator.py
```

## Key Constraints (Code Review Red Lines)

### Domain Layer Purity
The `domain/` directory must NEVER import: `ccxt`, `aiohttp`, `requests`, `fastapi`, `yaml`, or any other I/O framework. This is a hard red line for code review.

### Decimal Everywhere
All monetary values, ratios, and calculations in the domain layer must use `decimal.Decimal`. Any `float` usage for financial calculations will be rejected.

### API Key Security
- API keys must have read-only permissions only
- System must refuse to start (`FatalStartupError F-001/F-002`) if `trade` or `withdraw` permissions are detected
- All secrets (api_key, api_secret, webhook_url) must be masked via `mask_secret()` before logging

### Configuration
- Static config loading at startup (no hot-reload of logic)
- `core_symbols` (BTC, ETH, SOL, BNB) cannot be removed or overridden by user config
- All effective parameters must be printed to console at startup (desensitized)

## Error Code System

| Code | Level | Meaning |
|------|-------|---------|
| `F-001` | FATAL | API Key has trade permission |
| `F-002` | FATAL | API Key has withdraw permission |
| `F-003` | FATAL | Missing required config field |
| `F-004` | FATAL | Exchange initialization failed |
| `C-001` | CRITICAL | WebSocket reconnection limit exceeded |
| `C-002` | CRITICAL | REST asset polling consecutive failures |
| `W-001` | WARNING | K-line data quality issue (high < low, etc.) |
| `W-002` | WARNING | Data delay exceeds threshold |

## Core Models

### domain/models.py

```python
# Enums
Direction: LONG | SHORT
TrendDirection: BULLISH | BEARISH
MtfStatus: CONFIRMED | REJECTED | DISABLED | UNAVAILABLE

# Input Data Models
KlineData: symbol, timeframe, timestamp, open/high/low/close/volume (Decimal), is_closed
AccountSnapshot: total_balance, available_balance, unrealized_pnl, positions, timestamp
PositionInfo: symbol, side, size, entry_price, unrealized_pnl, leverage

# Output Model
SignalResult: symbol, timeframe, direction, entry_price, suggested_stop_loss,
              suggested_position_size, current_leverage, ema_trend, mtf_status, risk_reward_info
```

## Strategy Logic

### Pinbar Detection (color-agnostic)
- Wick ratio >= `min_wick_ratio` (default 0.6)
- Body ratio <= `max_body_ratio` (default 0.3)
- Body position within `body_position_tolerance` (default 0.1)
- Bullish: long lower wick, body at top
- Bearish: long upper wick, body at bottom

### Filter Combinations
```
signal_valid = (
    pinbar_detected
    and (not trend_filter_enabled or trend_direction_match)
    and (not mtf_validation_enabled or mtf_status == CONFIRMED)
)
```

### Position Sizing Formula
```
Position_Size = (Balance × Loss_Percent) / Stop_Loss_Distance
```
Where:
- `Loss_Percent = max_loss_percent` from config (e.g., 0.01 = 1%)
- `Stop_Loss_Distance = |Entry_Price - Stop_Loss| / Entry_Price`

## Module Interfaces

### ConfigManager (application/config_manager.py)
```python
manager = ConfigManager(config_dir)
manager.load_core_config()  # → CoreConfig
manager.load_user_config()  # → UserConfig (registers secrets for masking)
manager.merge_symbols()     # → List[str] (core ∪ user, deduplicated)
manager.check_api_key_permissions(exchange)  # Raises FatalStartupError on trade/withdraw
manager.print_startup_info()  # Print all effective params (masked)
```

### ExchangeGateway (infrastructure/exchange_gateway.py)
```python
gateway = ExchangeGateway(exchange_name, api_key, api_secret, testnet=True)
await gateway.initialize()  # Raises FatalStartupError F-004 on failure
await gateway.fetch_historical_ohlcv(symbol, timeframe, limit=100)  # → List[KlineData]
await gateway.subscribe_ohlcv(symbols, timeframes, callback)  # WebSocket, emits on is_closed=True
await gateway.start_asset_polling(interval_seconds=60)  # Background task
gateway.get_account_snapshot()  # → AccountSnapshot | None
await gateway.close()
```

### NotificationService (infrastructure/notifier.py)
```python
service = NotificationService()
service.setup_channels(channels_config)  # From user.yaml
await service.send_signal(signal)  # SignalResult → Markdown → webhook
await service.send_system_alert(error_code, error_message, exc_info)
```

### StrategyEngine (domain/strategy_engine.py)
```python
engine = StrategyEngine(config)
direction = engine.process_signal(kline, higher_timeframe_prices)  # → Direction | None
ema_trend = engine.get_ema_trend(kline, symbol, timeframe)  # → TrendDirection | None
higher_tf = engine.get_higher_timeframe(timeframe)  # → str | None
```

### RiskCalculator (domain/risk_calculator.py)
```python
calculator = RiskCalculator(config)
stop_loss = calculator.calculate_stop_loss(kline, direction)  # → Decimal
position_size, leverage = calculator.calculate_position_size(account, entry, stop, direction)
signal = calculator.calculate_signal_result(kline, account, direction, ema_trend, mtf_status)
```

## Development Notes

- **WebSocket**: Implements auto-reconnect with exponential backoff (1s initial, 60s max)
- **K-line closure**: Only trigger strategy calculation on `is_closed=True` K-lines (detected by timestamp change)
- **MTF mapping**: 15m→1h, 1h→4h, 4h→1d, 1d→1w
- **Notification format**: Pure text Markdown (no images)
- **Secret masking**: `mask_secret(value, visible_chars=4)` keeps first 4 and last 4 characters

## Testing

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_config_manager.py -v

# Run specific test
pytest tests/unit/test_config_manager.py::TestConfigManager::test_load_core_config -v
```

Test files:
- `test_config_manager.py`: Config loading, merging, permission checks, secret masking
- `test_exchange_gateway.py`: OHLCV parsing, historical fetch, asset polling, reconnection logic
- `test_notifier.py`: Message formatting, webhook sending, channel setup
- `test_indicators.py`: EMA calculation, warmup, reset, bulk update
- `test_strategy_engine.py`: Pinbar detection, trend filter, MTF validation
- `test_risk_calculator.py`: Position sizing, stop-loss, Decimal precision

## Files to Reference

- `docs/系统架构与开发并行指南.md` - Full architecture and parallel development guide
- `docs/需求文档.md` - Complete business requirements
- `docs/开发建议提纲.md` - Technical recommendations
- `README.md` - User-facing documentation
