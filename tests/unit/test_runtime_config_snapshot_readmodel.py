"""Tests for RuntimeConfigSnapshotReadModel source_of_truth_hints.

Verifies:
1. Provider exists → hints contain runtime_profile + resolved_from_profile
2. Provider missing → hints contain no_provider
3. Provider exception → hints contain provider_error
4. Environment summary present → hints reflect environment source
5. Empty summary → hints contain legacy_fallback
"""
import pytest
from unittest.mock import MagicMock

from src.application.readmodels.runtime_config_snapshot import RuntimeConfigSnapshotReadModel
from src.application.readmodels.console_models import ConfigSnapshotResponse


def _make_provider(summary: dict) -> MagicMock:
    """Create a mock provider whose to_safe_summary() returns the given dict."""
    provider = MagicMock()
    provider.to_safe_summary.return_value = summary
    return provider


class TestNoProvider:
    def test_no_provider_returns_no_provider_hint(self):
        rm = RuntimeConfigSnapshotReadModel()
        resp = rm.build(runtime_config_provider=None)
        assert resp.source_of_truth_hints == ["no_provider"]
        assert resp.profile == "unavailable"
        assert resp.identity.profile == "unavailable"


class TestProviderError:
    def test_provider_raises_returns_provider_error_hint(self):
        provider = MagicMock()
        provider.to_safe_summary.side_effect = RuntimeError("boom")
        rm = RuntimeConfigSnapshotReadModel()
        resp = rm.build(runtime_config_provider=provider)
        assert resp.source_of_truth_hints == ["provider_error"]
        assert resp.profile == "error"

    def test_provider_raises_value_error(self):
        provider = MagicMock()
        provider.to_safe_summary.side_effect = ValueError("bad data")
        rm = RuntimeConfigSnapshotReadModel()
        resp = rm.build(runtime_config_provider=provider)
        assert "provider_error" in resp.source_of_truth_hints


class TestProviderWithFullSummary:
    def test_hints_contain_runtime_profile(self):
        provider = _make_provider({
            "profile_name": "sim1",
            "version": 3,
            "config_hash": "abc123",
            "environment": {
                "exchange_name": "binance",
                "exchange_testnet": True,
                "backend_port": 8000,
            },
            "market": {"symbol": "BTC/USDT:USDT"},
            "strategy": {"pinbar_enabled": True},
            "risk": {"max_loss_pct": "0.01"},
            "execution": {"order_backend": "pg"},
        })
        rm = RuntimeConfigSnapshotReadModel()
        resp = rm.build(runtime_config_provider=provider)

        hints = resp.source_of_truth_hints
        assert "runtime_profile:sim1" in hints
        assert "strategy:resolved_from_profile" in hints
        assert "risk:resolved_from_profile" in hints
        assert "execution:resolved_from_profile" in hints
        assert "market:resolved_from_profile" in hints
        assert "backend:environment" in hints

    def test_profile_name_unknown_no_runtime_profile_hint(self):
        provider = _make_provider({
            "profile_name": "unknown",
            "version": 0,
            "config_hash": "",
            "environment": {},
            "market": {},
            "strategy": {},
            "risk": {},
            "execution": {},
        })
        rm = RuntimeConfigSnapshotReadModel()
        resp = rm.build(runtime_config_provider=provider)

        # "unknown" profile should NOT produce runtime_profile hint
        assert not any(h.startswith("runtime_profile:") for h in resp.source_of_truth_hints)


class TestEnvironmentHints:
    def test_env_with_exchange_name_produces_environment_hint(self):
        provider = _make_provider({
            "profile_name": "prod",
            "version": 1,
            "config_hash": "h1",
            "environment": {
                "exchange_name": "binance",
                "exchange_testnet": False,
            },
            "market": {},
            "strategy": {},
            "risk": {},
            "execution": {},
        })
        rm = RuntimeConfigSnapshotReadModel()
        resp = rm.build(runtime_config_provider=provider)

        assert "backend:environment" in resp.source_of_truth_hints

    def test_env_with_backend_port_produces_environment_hint(self):
        provider = _make_provider({
            "profile_name": "prod",
            "version": 1,
            "config_hash": "h1",
            "environment": {
                "backend_port": 9000,
            },
            "market": {},
            "strategy": {},
            "risk": {},
            "execution": {},
        })
        rm = RuntimeConfigSnapshotReadModel()
        resp = rm.build(runtime_config_provider=provider)

        assert "backend:environment" in resp.source_of_truth_hints

    def test_empty_env_no_environment_hint(self):
        provider = _make_provider({
            "profile_name": "prod",
            "version": 1,
            "config_hash": "h1",
            "environment": {},
            "market": {},
            "strategy": {},
            "risk": {},
            "execution": {},
        })
        rm = RuntimeConfigSnapshotReadModel()
        resp = rm.build(runtime_config_provider=provider)

        assert "backend:environment" not in resp.source_of_truth_hints


class TestLegacyFallback:
    def test_empty_summary_produces_legacy_fallback(self):
        provider = _make_provider({
            "profile_name": "unknown",
            "version": 0,
            "config_hash": "",
            "environment": {},
            "market": {},
            "strategy": {},
            "risk": {},
            "execution": {},
        })
        rm = RuntimeConfigSnapshotReadModel()
        resp = rm.build(runtime_config_provider=provider)

        assert "legacy_fallback" in resp.source_of_truth_hints


class TestPartialSections:
    def test_only_strategy_section(self):
        provider = _make_provider({
            "profile_name": "partial",
            "version": 1,
            "config_hash": "h2",
            "environment": {},
            "market": {},
            "strategy": {"pinbar_enabled": True},
            "risk": {},
            "execution": {},
        })
        rm = RuntimeConfigSnapshotReadModel()
        resp = rm.build(runtime_config_provider=provider)

        hints = resp.source_of_truth_hints
        assert "runtime_profile:partial" in hints
        assert "strategy:resolved_from_profile" in hints
        # Empty sections should NOT produce resolved_from_profile hints
        assert "risk:resolved_from_profile" not in hints
        assert "execution:resolved_from_profile" not in hints

    def test_response_structure_stable(self):
        """Verify response model fields remain stable."""
        provider = _make_provider({
            "profile_name": "test",
            "version": 5,
            "config_hash": "deadbeef",
            "environment": {"exchange_name": "bybit"},
            "market": {"timeframe": "1h"},
            "strategy": {},
            "risk": {"max_loss_pct": "0.02"},
            "execution": {},
        })
        rm = RuntimeConfigSnapshotReadModel()
        resp = rm.build(runtime_config_provider=provider)

        assert isinstance(resp, ConfigSnapshotResponse)
        assert resp.profile == "test"
        assert resp.version == 5
        assert resp.hash == "deadbeef"
        assert resp.identity.profile == "test"
        assert resp.identity.version == 5
        assert resp.identity.hash == "deadbeef"
        assert resp.backend["exchange_name"] == "bybit"
        assert resp.environment["exchange_name"] == "bybit"
