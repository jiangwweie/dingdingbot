#!/bin/bash
python3 -m pytest tests/unit/test_matching_engine.py tests/unit/test_backtest_repository.py tests/unit/test_backtester_verification.py -v --tb=short