"""
Unit tests for configuration snapshot API endpoints.

Tests for:
- GET /api/v1/config/snapshots - List snapshots
- POST /api/v1/config/snapshots - Create snapshot
- GET /api/v1/config/snapshots/{id} - Get snapshot detail
- POST /api/v1/config/snapshots/{id}/activate - Activate snapshot
- DELETE /api/v1/config/snapshots/{id} - Delete snapshot
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any, Tuple
from decimal import Decimal

from src.interfaces.api_v1_config import extract_config_types, SnapshotListItem


class TestExtractConfigTypes:
    """测试 extract_config_types 辅助函数"""

    def test_extract_all_config_types(self):
        """测试提取所有配置类型"""
        config_data = {
            "risk": {"max_loss_percent": 0.01},
            "system": {"ema_period": 20},
            "strategies": [{"id": "1", "name": "test"}],
            "symbols": ["BTC/USDT"],
            "notifications": [{"id": "1", "channel": "feishu"}]
        }

        result = extract_config_types(config_data)

        assert result == ["risk", "system", "strategies", "symbols", "notifications"]

    def test_extract_partial_config_types(self):
        """测试提取部分配置类型"""
        config_data = {
            "risk": {"max_loss_percent": 0.01},
            "symbols": ["BTC/USDT"]
        }

        result = extract_config_types(config_data)

        assert result == ["risk", "symbols"]

    def test_extract_empty_config_types(self):
        """测试空配置数据"""
        config_data = {}

        result = extract_config_types(config_data)

        assert result == []

    def test_extract_none_config_data(self):
        """测试 None 配置数据"""
        result = extract_config_types(None)

        assert result == []

    def test_extract_with_unknown_keys(self):
        """测试包含未知键的配置数据"""
        config_data = {
            "risk": {"max_loss_percent": 0.01},
            "unknown_key": "value"
        }

        result = extract_config_types(config_data)

        assert result == ["risk"]


class TestGetSnapshotsEndpoint:
    """测试 GET /api/v1/config/snapshots 端点"""

    @pytest.fixture
    def mock_snapshot_repo(self):
        """创建 mock snapshot repository"""
        repo = MagicMock()
        repo.get_list = AsyncMock()
        return repo

    @pytest.fixture
    def sample_snapshots(self) -> Tuple[List[Dict[str, Any]], int]:
        """创建示例快照数据"""
        snapshots = [
            {
                "id": "uuid-1",
                "name": "Test Snapshot 1",
                "description": "Test description 1",
                "config_data": {
                    "risk": {"max_loss_percent": 0.01},
                    "system": {"ema_period": 20}
                },
                "created_at": "2026-04-07T10:00:00Z",
                "created_by": "admin",
            },
            {
                "id": "uuid-2",
                "name": "Test Snapshot 2",
                "description": "Test description 2",
                "config_data": {
                    "strategies": [{"id": "1", "name": "test"}],
                    "symbols": ["BTC/USDT"]
                },
                "created_at": "2026-04-07T11:00:00Z",
                "created_by": "admin",
            }
        ]
        return snapshots, 2

    @pytest.mark.asyncio
    async def test_get_snapshots_returns_list(self, mock_snapshot_repo, sample_snapshots):
        """验证快照列表查询返回正确数据"""
        # Arrange
        mock_snapshot_repo.get_list.return_value = sample_snapshots

        # 使用 patch 注入 mock repository
        from src.interfaces import api_v1_config
        with patch.object(api_v1_config, '_snapshot_repo', mock_snapshot_repo):
            # Act
            response = await api_v1_config.get_snapshots(limit=10, offset=0)

            # Assert
            assert len(response) == 2
            assert response[0].id == "uuid-1"
            assert response[0].name == "Test Snapshot 1"
            assert response[0].config_types == ["risk", "system"]
            assert response[1].id == "uuid-2"
            assert response[1].config_types == ["strategies", "symbols"]

    @pytest.mark.asyncio
    async def test_get_snapshots_pagination(self, mock_snapshot_repo):
        """验证分页参数正确传递给 repository"""
        # Arrange
        mock_snapshot_repo.get_list.return_value = ([], 0)

        from src.interfaces import api_v1_config
        with patch.object(api_v1_config, '_snapshot_repo', mock_snapshot_repo):
            # Act
            await api_v1_config.get_snapshots(limit=20, offset=10)

            # Assert
            mock_snapshot_repo.get_list.assert_called_once_with(limit=20, offset=10)

    @pytest.mark.asyncio
    async def test_get_snapshots_empty_list(self, mock_snapshot_repo):
        """验证空列表返回"""
        # Arrange
        mock_snapshot_repo.get_list.return_value = ([], 0)

        from src.interfaces import api_v1_config
        with patch.object(api_v1_config, '_snapshot_repo', mock_snapshot_repo):
            # Act
            response = await api_v1_config.get_snapshots(limit=50, offset=0)

            # Assert
            assert isinstance(response, list)
            assert len(response) == 0

    @pytest.mark.asyncio
    async def test_get_snapshots_missing_description(self, mock_snapshot_repo):
        """验证缺少 description 字段的快照正确处理"""
        # Arrange
        snapshots = [
            {
                "id": "uuid-1",
                "name": "Test Snapshot",
                "config_data": {"risk": {"max_loss_percent": 0.01}},
                "created_at": "2026-04-07T10:00:00Z",
                "created_by": "admin",
            }
        ]
        mock_snapshot_repo.get_list.return_value = (snapshots, 1)

        from src.interfaces import api_v1_config
        with patch.object(api_v1_config, '_snapshot_repo', mock_snapshot_repo):
            # Act
            response = await api_v1_config.get_snapshots(limit=10, offset=0)

            # Assert
            assert len(response) == 1
            assert response[0].description is None

    @pytest.mark.asyncio
    async def test_get_snapshots_missing_created_by(self, mock_snapshot_repo):
        """验证缺少 created_by 字段的快照使用默认值"""
        # Arrange
        snapshots = [
            {
                "id": "uuid-1",
                "name": "Test Snapshot",
                "config_data": {},
                "created_at": "2026-04-07T10:00:00Z",
            }
        ]
        mock_snapshot_repo.get_list.return_value = (snapshots, 1)

        from src.interfaces import api_v1_config
        with patch.object(api_v1_config, '_snapshot_repo', mock_snapshot_repo):
            # Act
            response = await api_v1_config.get_snapshots(limit=10, offset=0)

            # Assert
            assert len(response) == 1
            assert response[0].created_by == "unknown"

    @pytest.mark.asyncio
    async def test_get_snapshots_repository_not_initialized(self):
        """验证 repository 未初始化时抛出 503 错误"""
        from src.interfaces import api_v1_config
        from fastapi import HTTPException

        with patch.object(api_v1_config, '_snapshot_repo', None):
            with pytest.raises(HTTPException) as exc_info:
                await api_v1_config.get_snapshots(limit=10, offset=0)

            assert exc_info.value.status_code == 503
            assert "Snapshot repository not initialized" in str(exc_info.value.detail)


class TestSnapshotListItemModel:
    """测试 SnapshotListItem 数据模型"""

    def test_snapshot_list_item_creation(self):
        """验证 SnapshotListItem 模型创建"""
        item = SnapshotListItem(
            id="uuid-1",
            name="Test Snapshot",
            description="Test description",
            created_at="2026-04-07T10:00:00Z",
            created_by="admin",
            config_types=["risk", "system"]
        )

        assert item.id == "uuid-1"
        assert item.name == "Test Snapshot"
        assert item.description == "Test description"
        assert item.created_at == "2026-04-07T10:00:00Z"
        assert item.created_by == "admin"
        assert item.config_types == ["risk", "system"]

    def test_snapshot_list_item_optional_description(self):
        """验证 SnapshotListItem 可选 description 字段"""
        item = SnapshotListItem(
            id="uuid-1",
            name="Test Snapshot",
            created_at="2026-04-07T10:00:00Z",
            created_by="admin",
            config_types=["risk"]
        )

        assert item.description is None

    def test_snapshot_list_item_json_serialization(self):
        """验证 SnapshotListItem JSON 序列化"""
        item = SnapshotListItem(
            id="uuid-1",
            name="Test Snapshot",
            description="Test",
            created_at="2026-04-07T10:00:00Z",
            created_by="admin",
            config_types=["risk", "system"]
        )

        data = item.model_dump()

        assert data["id"] == "uuid-1"
        assert data["name"] == "Test Snapshot"
        assert data["description"] == "Test"
        assert data["config_types"] == ["risk", "system"]
