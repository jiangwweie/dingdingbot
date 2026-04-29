"""
Tests for Profile Switch confirm gate.

Covers:
- Unconfirmed switch → 409
- Confirmed switch → 200
- Non-existent profile → 404 (unchanged)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.interfaces.api import app


@pytest.fixture
def client():
    return TestClient(app)


def _mock_profile(name: str = "test_profile", is_active: bool = False):
    p = MagicMock()
    p.name = name
    p.is_active = is_active
    p.to_dict.return_value = {"name": name, "is_active": is_active}
    return p


def _mock_diff(total_changes: int = 0):
    d = MagicMock()
    d.total_changes = total_changes
    d.from_profile = "default"
    d.to_profile = "test_profile"
    d.to_dict.return_value = {
        "from_profile": "default",
        "to_profile": "test_profile",
        "total_changes": total_changes,
        "diff": {},
    }
    return d


class TestProfileSwitchConfirm:
    """Profile switch requires explicit confirm=true."""

    def test_switch_without_confirm_returns_409(self, client):
        """confirm 缺省或为 false 时拒绝切换，返回 409"""
        resp = client.post("/api/config/profiles/test_profile/activate")
        assert resp.status_code == 409
        assert "confirm" in resp.json()["message"].lower()

        resp = client.post("/api/config/profiles/test_profile/activate?confirm=false")
        assert resp.status_code == 409

    @patch("src.interfaces.api._get_config_manager")
    @patch("src.interfaces.api._get_config_entry_repo")
    @patch("src.application.config_profile_service.ConfigProfileService")
    @patch("src.infrastructure.config_profile_repository.ConfigProfileRepository")
    def test_switch_with_confirm_succeeds(
        self, mock_repo_cls, mock_service_cls, mock_entry_repo_fn, mock_cm_fn, client
    ):
        """confirm=true 时正常执行切换"""
        service = AsyncMock()
        service.get_profile = AsyncMock(return_value=_mock_profile("test_profile"))
        service.switch_profile = AsyncMock(return_value=_mock_diff(2))
        mock_service_cls.return_value = service

        mock_repo = AsyncMock()
        mock_repo.initialize = AsyncMock()
        mock_repo_cls.return_value = mock_repo

        resp = client.post("/api/config/profiles/test_profile/activate?confirm=true")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        service.switch_profile.assert_called_once_with("test_profile")

    @patch("src.interfaces.api._get_config_manager")
    @patch("src.interfaces.api._get_config_entry_repo")
    @patch("src.application.config_profile_service.ConfigProfileService")
    @patch("src.infrastructure.config_profile_repository.ConfigProfileRepository")
    def test_switch_nonexistent_profile_returns_404(
        self, mock_repo_cls, mock_service_cls, mock_entry_repo_fn, mock_cm_fn, client
    ):
        """profile 不存在时仍返回 404（confirm=true 也一样）"""
        service = AsyncMock()
        service.get_profile = AsyncMock(return_value=None)
        mock_service_cls.return_value = service

        mock_repo = AsyncMock()
        mock_repo.initialize = AsyncMock()
        mock_repo_cls.return_value = mock_repo

        resp = client.post("/api/config/profiles/ghost/activate?confirm=true")
        assert resp.status_code == 404
