"""
Configuration Import/Export Functionality Tests

Tests for configuration import/export features:
- POST /api/v1/config/export - Export YAML
- POST /api/v1/config/import/preview - Preview import
- POST /api/v1/config/import/confirm - Confirm import
- Preview token expiry validation
- Auto-snapshot creation on import

Coverage target: >= 80%
"""
import json
import os
import pytest
import tempfile
import yaml
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any

from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.infrastructure.repositories.config_repositories import (
    StrategyConfigRepository,
    RiskConfigRepository,
    SystemConfigRepository,
    SymbolConfigRepository,
    NotificationConfigRepository,
    ConfigHistoryRepository,
    ConfigSnapshotRepositoryExtended,
    ConfigDatabaseManager,
)
from src.interfaces.api_v1_config import (
    router,
    set_config_dependencies,
    _import_preview_cache,
)


# ============================================================
# Test Fixtures
# ============================================================

@pytest.fixture
def temp_db_path():
    """Create a temporary database file for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.remove(path)
    for suffix in ["-wal", "-shm"]:
        wal_path = path + suffix
        if os.path.exists(wal_path):
            os.remove(wal_path)


@pytest.fixture
async def db_manager(temp_db_path):
    """Create and initialize ConfigDatabaseManager."""
    manager = ConfigDatabaseManager(temp_db_path)
    await manager.initialize()
    yield manager
    await manager.close()


@pytest.fixture
def app():
    """Create FastAPI app with config router."""
    app = FastAPI(title="Config Import/Export Test")
    # Router already has prefix built-in: /api/v1/config
    app.include_router(router, tags=["config"])
    return app


@pytest.fixture
def client(app, db_manager):
    """Create TestClient with injected dependencies."""
    set_config_dependencies(
        strategy_repo=db_manager.strategy_repo,
        risk_repo=db_manager.risk_repo,
        system_repo=db_manager.system_repo,
        symbol_repo=db_manager.symbol_repo,
        notification_repo=db_manager.notification_repo,
        history_repo=db_manager.history_repo,
        snapshot_repo=db_manager.snapshot_repo,
    )

    # Clear preview cache before each test
    _import_preview_cache.clear()

    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_config_yaml():
    """Sample valid configuration YAML for testing."""
    return """
risk:
  max_loss_percent: 0.02
  max_leverage: 20
  max_total_exposure: 0.9
  cooldown_minutes: 300

system:
  core_symbols:
    - BTC/USDT:USDT
    - ETH/USDT:USDT
    - SOL/USDT:USDT
  ema_period: 50
  mtf_ema_period: 50
  mtf_mapping:
    "15m": "1h"
    "1h": "4h"
  signal_cooldown_seconds: 7200

strategies:
  - name: Pinbar + EMA Strategy
    description: Pinbar pattern with EMA trend filter
    trigger:
      type: pinbar
      enabled: true
      params:
        min_wick_ratio: 0.6
        max_body_ratio: 0.3
    filters:
      - type: ema
        enabled: true
        params:
          period: 60
      - type: mtf
        enabled: true
        params: {}
    filter_logic: AND
    symbols:
      - BTC/USDT:USDT
      - ETH/USDT:USDT
    timeframes:
      - 15m
      - 1h

symbols:
  - symbol: BTC/USDT:USDT
    is_core: true
    price_precision: 2
  - symbol: ETH/USDT:USDT
    is_core: true
    price_precision: 2
  - symbol: SOL/USDT:USDT
    is_core: false
    price_precision: 3

notifications:
  - channel_type: feishu
    webhook_url: https://open.feishu.cn/open-apis/bot/v2/hook/test123
    is_active: true
    notify_on_signal: true
    notify_on_order: true
"""


# ============================================================
# Export API Tests
# ============================================================

class TestExportAPI:
    """Tests for POST /api/v1/config/export endpoint."""

    @pytest.mark.asyncio
    async def test_export_all_configs(self, client):
        """Test exporting all configuration types."""
        # Create some data first
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.015", "max_leverage": 15},
            headers={"X-User-Role": "admin"}
        )
        client.put(
            "/api/v1/config/system",
            json={
                "core_symbols": ["BTC/USDT:USDT"],
                "ema_period": 55,
            },
            headers={"X-User-Role": "admin"}
        )

        # Export all
        response = client.post(
            "/api/v1/config/export",
            json={
                "include_risk": True,
                "include_system": True,
                "include_strategies": True,
                "include_symbols": True,
                "include_notifications": True,
            },
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "yaml_content" in data
        assert "filename" in data

        # Verify YAML content
        yaml_data = yaml.safe_load(data["yaml_content"])
        assert "risk" in yaml_data
        assert "system" in yaml_data

    @pytest.mark.asyncio
    async def test_export_selective_configs(self, client):
        """Test exporting only selected configuration types."""
        # Create data
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )
        client.put(
            "/api/v1/config/system",
            json={"core_symbols": ["BTC/USDT:USDT"], "ema_period": 60},
            headers={"X-User-Role": "admin"}
        )

        # Export only risk
        response = client.post(
            "/api/v1/config/export",
            json={
                "include_risk": True,
                "include_system": False,
                "include_strategies": False,
            },
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        yaml_data = yaml.safe_load(data["yaml_content"])

        assert "risk" in yaml_data
        assert "system" not in yaml_data

    @pytest.mark.asyncio
    async def test_export_filename_format(self, client):
        """Test that export filename follows expected format."""
        response = client.post(
            "/api/v1/config/export",
            json={"include_risk": True},
            headers={"X-User-Role": "admin"}
        )

        data = response.json()
        filename = data["filename"]

        # Should match format: config_backup_YYYYMMDD_HHMMSS.yaml
        assert filename.startswith("config_backup_")
        assert filename.endswith(".yaml")

    @pytest.mark.asyncio
    async def test_export_yaml_valid_format(self, client):
        """Test that exported YAML is valid and parseable."""
        # Create data
        client.put(
            "/api/v1/config/risk",
            json={
                "max_loss_percent": "0.02",
                "max_leverage": 20,
                "cooldown_minutes": 180,
            },
            headers={"X-User-Role": "admin"}
        )

        response = client.post(
            "/api/v1/config/export",
            json={"include_risk": True},
            headers={"X-User-Role": "admin"}
        )

        data = response.json()
        yaml_content = data["yaml_content"]

        # Should be parseable
        parsed = yaml.safe_load(yaml_content)
        assert isinstance(parsed, dict)
        assert "risk" in parsed
        assert parsed["risk"]["max_leverage"] == 20

    @pytest.mark.asyncio
    async def test_export_with_strategies(self, client):
        """Test exporting strategies."""
        # Create a strategy
        client.post(
            "/api/v1/config/strategies",
            json={
                "name": "Export Test Strategy",
                "trigger": {"type": "pinbar", "enabled": True, "params": {}},
                "filters": [],
                "filter_logic": "AND",
            },
            headers={"X-User-Role": "admin"}
        )

        response = client.post(
            "/api/v1/config/export",
            json={"include_strategies": True},
            headers={"X-User-Role": "admin"}
        )

        data = response.json()
        yaml_data = yaml.safe_load(data["yaml_content"])

        assert "strategies" in yaml_data
        assert len(yaml_data["strategies"]) >= 1


# ============================================================
# Import Preview API Tests
# ============================================================

class TestImportPreviewAPI:
    """Tests for POST /api/v1/config/import/preview endpoint."""

    @pytest.mark.asyncio
    async def test_preview_valid_yaml(self, client, sample_config_yaml):
        """Test previewing valid YAML configuration."""
        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": sample_config_yaml, "filename": "test_config.yaml"},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert "preview_token" in data
        assert "summary" in data
        assert data["conflicts"] == []

    @pytest.mark.asyncio
    async def test_preview_invalid_yaml_format(self, client):
        """Test previewing invalid YAML format."""
        invalid_yaml = """
risk:
  max_loss_percent: invalid
  [not valid yaml
"""
        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": invalid_yaml},
            headers={"X-User-Role": "admin"}
        )

        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    @pytest.mark.asyncio
    async def test_preview_detects_duplicate_strategy_names(self, client):
        """Test that preview detects duplicate strategy names."""
        yaml_content = """
strategies:
  - name: Duplicate Strategy
    trigger:
      type: pinbar
      enabled: true
      params: {}
    filters: []
    filter_logic: AND
  - name: Duplicate Strategy
    trigger:
      type: engulfing
      enabled: true
      params: {}
    filters: []
    filter_logic: AND
"""
        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content},
            headers={"X-User-Role": "admin"}
        )

        data = response.json()
        assert "conflicts" in data
        assert any("Duplicate" in c for c in data["conflicts"])

    @pytest.mark.asyncio
    async def test_preview_detects_restart_required(self, client, sample_config_yaml):
        """Test that preview detects when restart is required."""
        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": sample_config_yaml, "filename": "test.yaml"},
            headers={"X-User-Role": "admin"}
        )

        data = response.json()
        # Import includes system config changes
        assert data["requires_restart"] is True

    @pytest.mark.asyncio
    async def test_preview_summary_counts(self, client, sample_config_yaml):
        """Test that preview summary includes correct counts."""
        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": sample_config_yaml, "filename": "test.yaml"},
            headers={"X-User-Role": "admin"}
        )

        data = response.json()
        summary = data["summary"]

        assert "strategies" in summary
        assert "symbols" in summary
        assert "risk" in summary

        # Sample config has 1 strategy, 3 symbols
        assert summary["strategies"]["added"] >= 1
        assert summary["symbols"]["added"] >= 1

    @pytest.mark.asyncio
    async def test_preview_token_stored(self, client):
        """Test that preview token is stored in cache."""
        yaml_content = "risk:\n  max_loss_percent: 0.01"

        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content, "filename": "test.yaml"},
            headers={"X-User-Role": "admin"}
        )

        preview_token = response.json()["preview_token"]
        assert preview_token in _import_preview_cache

    @pytest.mark.asyncio
    async def test_preview_yaml_root_not_mapping(self, client):
        """Test preview rejects YAML where root is not a mapping."""
        yaml_content = """
- item1
- item2
"""
        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content},
            headers={"X-User-Role": "admin"}
        )

        data = response.json()
        assert data["valid"] is False
        assert any("root" in e.lower() for e in data["errors"])

    @pytest.mark.asyncio
    async def test_preview_strategies_not_list(self, client):
        """Test preview rejects strategies that is not a list."""
        yaml_content = """
strategies:
  name: Not a list
"""
        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content},
            headers={"X-User-Role": "admin"}
        )

        data = response.json()
        assert data["valid"] is False
        assert any("strategies" in e.lower() for e in data["errors"])


# ============================================================
# Import Confirm API Tests
# ============================================================

class TestImportConfirmAPI:
    """Tests for POST /api/v1/config/import/confirm endpoint."""

    @pytest.mark.asyncio
    async def test_confirm_import_with_valid_preview(self, client, sample_config_yaml):
        """Test confirming import with valid preview token."""
        # Preview first
        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": sample_config_yaml, "filename": "test.yaml"},
            headers={"X-User-Role": "admin"}
        )
        preview_token = preview_response.json()["preview_token"]

        # Confirm
        response = client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "snapshot_id" in data

    @pytest.mark.asyncio
    async def test_confirm_import_invalid_token(self, client):
        """Test confirming import with invalid token fails."""
        response = client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": "nonexistent-token-12345"},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_confirm_import_expired_token(self, client):
        """Test confirming import with expired token fails."""
        yaml_content = "risk:\n  max_loss_percent: 0.01"

        # Preview
        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content, "filename": "test.yaml"},
            headers={"X-User-Role": "admin"}
        )
        preview_token = preview_response.json()["preview_token"]

        # Manually expire the token
        _import_preview_cache[preview_token]["expires_at"] = datetime.now(timezone.utc) - timedelta(minutes=10)

        # Confirm should fail
        response = client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_confirm_import_risk_config_applied(self, client):
        """Test that confirming import applies risk config."""
        yaml_content = """
risk:
  max_loss_percent: 0.025
  max_leverage: 25
  cooldown_minutes: 120
"""
        # Preview and confirm
        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content, "filename": "risk_only.yaml"},
            headers={"X-User-Role": "admin"}
        )
        preview_token = preview_response.json()["preview_token"]

        client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )

        # Verify risk config was applied
        get_response = client.get("/api/v1/config/risk")
        data = get_response.json()
        assert data["max_loss_percent"] == "0.025"
        assert data["max_leverage"] == 25

    @pytest.mark.asyncio
    async def test_confirm_import_system_config_applied(self, client):
        """Test that confirming import applies system config."""
        yaml_content = """
system:
  core_symbols:
    - BTC/USDT:USDT
    - ETH/USDT:USDT
  ema_period: 45
  mtf_ema_period: 45
"""
        # Preview and confirm
        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content, "filename": "system_only.yaml"},
            headers={"X-User-Role": "admin"}
        )
        preview_token = preview_response.json()["preview_token"]

        client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )

        # Verify system config was applied
        get_response = client.get("/api/v1/config/system")
        data = get_response.json()
        assert data["ema_period"] == 45

    @pytest.mark.asyncio
    async def test_confirm_import_creates_snapshot(self, client):
        """Test that confirming import creates a pre-import snapshot."""
        yaml_content = """
risk:
  max_loss_percent: 0.01
  max_leverage: 10
"""
        # Preview and confirm
        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content, "filename": "snapshot_test.yaml"},
            headers={"X-User-Role": "admin"}
        )
        preview_token = preview_response.json()["preview_token"]

        response = client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )

        data = response.json()
        assert "snapshot_id" in data
        assert data["snapshot_id"] is not None

    @pytest.mark.asyncio
    async def test_confirm_import_preview_cache_cleaned(self, client):
        """Test that preview cache is cleaned after confirm."""
        yaml_content = "risk:\n  max_loss_percent: 0.01"

        # Preview
        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content, "filename": "cleanup_test.yaml"},
            headers={"X-User-Role": "admin"}
        )
        preview_token = preview_response.json()["preview_token"]
        assert preview_token in _import_preview_cache

        # Confirm
        client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )

        # Token should be removed from cache
        assert preview_token not in _import_preview_cache


# ============================================================
# Integration Tests
# ============================================================

class TestImportExportIntegration:
    """Integration tests for complete import/export workflow."""

    @pytest.mark.asyncio
    async def test_full_export_import_cycle(self, client):
        """Test complete export -> modify -> import cycle."""
        # 1. Create initial config
        client.put(
            "/api/v1/config/risk",
            json={"max_loss_percent": "0.01", "max_leverage": 10},
            headers={"X-User-Role": "admin"}
        )

        # 2. Export
        export_response = client.post(
            "/api/v1/config/export",
            json={"include_risk": True},
            headers={"X-User-Role": "admin"}
        )
        yaml_content = export_response.json()["yaml_content"]

        # 3. Modify exported YAML
        modified_yaml = yaml_content.replace("0.01", "0.03")

        # 4. Preview import
        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": modified_yaml, "filename": "modified.yaml"},
            headers={"X-User-Role": "admin"}
        )
        preview_token = preview_response.json()["preview_token"]

        # 5. Confirm import
        client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )

        # 6. Verify config was updated
        get_response = client.get("/api/v1/config/risk")
        data = get_response.json()
        assert data["max_loss_percent"] == "0.03"

    @pytest.mark.asyncio
    async def test_import_multiple_strategies(self, client):
        """Test importing multiple strategies at once."""
        yaml_content = """
strategies:
  - name: Strategy One
    trigger:
      type: pinbar
      enabled: true
      params: {}
    filters: []
    filter_logic: AND
  - name: Strategy Two
    trigger:
      type: engulfing
      enabled: true
      params: {}
    filters: []
    filter_logic: AND
  - name: Strategy Three
    trigger:
      type: doji
      enabled: true
      params: {}
    filters: []
    filter_logic: AND
"""
        # Preview and confirm
        preview_response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content, "filename": "multi_strategy.yaml"},
            headers={"X-User-Role": "admin"}
        )
        preview_token = preview_response.json()["preview_token"]

        client.post(
            "/api/v1/config/import/confirm",
            json={"preview_token": preview_token},
            headers={"X-User-Role": "admin"}
        )

        # Verify strategies were created
        strategies_response = client.get("/api/v1/config/strategies")
        data = strategies_response.json()
        # API returns a list directly, not a dict with 'items'
        if isinstance(data, list):
            assert len(data) >= 3
        else:
            assert len(data.get("items", [])) >= 3


# ============================================================
# Edge Cases
# ============================================================

class TestImportExportEdgeCases:
    """Edge cases for import/export functionality."""

    @pytest.mark.asyncio
    async def test_export_empty_config(self, client):
        """Test exporting when no config exists."""
        response = client.post(
            "/api/v1/config/export",
            json={"include_risk": True, "include_system": True},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        # Should still return valid YAML
        yaml_data = yaml.safe_load(data["yaml_content"])
        assert isinstance(yaml_data, dict)

    @pytest.mark.asyncio
    async def test_preview_unicode_content(self, client):
        """Test previewing YAML with unicode content."""
        yaml_content = """
strategies:
  - name: 测试策略
    description: テスト戦略
    trigger:
      type: pinbar
      enabled: true
      params: {}
    filters: []
    filter_logic: AND
"""
        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content, "filename": "unicode.yaml"},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_preview_large_yaml(self, client):
        """Test previewing large YAML file."""
        # Generate YAML with many strategies
        strategies = []
        for i in range(50):
            strategies.append(f"""
  - name: Strategy {i}
    trigger:
      type: pinbar
      enabled: true
      params: {{}}
    filters: []
    filter_logic: AND
""")

        yaml_content = "strategies:\n" + "\n".join(strategies)

        response = client.post(
            "/api/v1/config/import/preview",
            json={"yaml_content": yaml_content, "filename": "large.yaml"},
            headers={"X-User-Role": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["summary"]["strategies"]["added"] == 50


# ============================================================
# Main entry point
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src/interfaces/api_v1_config"])
