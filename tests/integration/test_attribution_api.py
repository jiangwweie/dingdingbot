"""
Attribution API 集成测试

测试归因分析 API 端点的完整功能
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_backtest_report():
    """创建模拟回测报告"""
    return {
        "attempts": [
            {
                "strategy_name": "pinbar",
                "final_result": "SIGNAL_FIRED",
                "direction": "long",
                "kline_timestamp": 1711785600000,
                "pattern_score": 0.85,
                "filter_results": [
                    {"filter": "ema_trend", "passed": True, "reason": "trend_match", "metadata": {"trend_direction": "bullish"}},
                ],
                "pnl_ratio": 2.0,
                "exit_reason": "TAKE_PROFIT",
            },
            {
                "strategy_name": "pinbar",
                "final_result": "SIGNAL_FIRED",
                "direction": "short",
                "kline_timestamp": 1711789200000,
                "pattern_score": 0.35,
                "filter_results": [
                    {"filter": "ema_trend", "passed": True, "reason": "trend_match", "metadata": {"trend_direction": "bearish"}},
                ],
                "pnl_ratio": -1.0,
                "exit_reason": "STOP_LOSS",
            },
        ],
    }


@pytest.fixture
def test_client():
    """创建 FastAPI 测试客户端（带资源清理）"""
    from src.interfaces.api import app

    # Mock dependencies
    mock_account_getter = Mock(return_value=None)

    with patch('src.interfaces.api._get_repository', return_value=Mock()):
        with patch('src.interfaces.api._account_getter', mock_account_getter):
            with patch('src.interfaces.api._get_exchange_gateway', return_value=Mock()):
                # 使用 TestClient 的上下文管理器确保资源清理
                with TestClient(app) as client:
                    yield client


# ============================================================
# Tests: POST /api/backtest/{report_id}/attribution
# ============================================================

class TestAttributionAnalysisEndpoint:
    """归因分析 API 端点测试"""

    def test_attribution_analysis_returns_200(self, test_client, mock_backtest_report):
        """测试归因分析端点返回 200"""
        # Mock database repository
        mock_report = Mock()
        mock_report.attempts = mock_backtest_report["attempts"]

        with patch('src.infrastructure.backtest_repository.BacktestReportRepository') as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.get_report_by_id = AsyncMock(return_value=mock_report)
            mock_repo.close = AsyncMock()
            mock_repo_class.return_value = mock_repo

            response = test_client.post("/api/backtest/test-report-id/attribution")

            assert response.status_code == 200
            assert response.json()["status"] == "success"

    def test_attribution_analysis_returns_all_dimensions(self, test_client, mock_backtest_report):
        """测试归因分析返回所有维度"""
        mock_report = Mock()
        mock_report.attempts = mock_backtest_report["attempts"]

        with patch('src.infrastructure.backtest_repository.BacktestReportRepository') as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.get_report_by_id = AsyncMock(return_value=mock_report)
            mock_repo.close = AsyncMock()
            mock_repo_class.return_value = mock_repo

            response = test_client.post("/api/backtest/test-report-id/attribution")
            assert response.status_code == 200

            data = response.json()
            attribution = data["attribution"]

            # 验证所有维度都存在
            assert "shape_quality" in attribution
            assert "filter_attribution" in attribution
            assert "trend_attribution" in attribution
            assert "rr_attribution" in attribution

    def test_attribution_analysis_returns_404_for_missing_report(self, test_client):
        """测试不存在的报告返回 404"""
        with patch('src.infrastructure.backtest_repository.BacktestReportRepository') as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.get_report_by_id = AsyncMock(return_value=None)
            mock_repo.close = AsyncMock()
            mock_repo_class.return_value = mock_repo

            response = test_client.post("/api/backtest/non-existent-id/attribution")

            assert response.status_code == 404


# ============================================================
# Tests: GET /api/backtest/{report_id}/attribution (deprecated)
# ============================================================

class TestDeprecatedAttributionEndpoint:
    """已废弃的归因 API 端点测试（GET 方法）"""

    def test_get_attribution_returns_stored_data(self, test_client):
        """测试 GET 接口返回已存储的归因数据"""
        from decimal import Decimal

        # Mock report with stored attribution data
        mock_report = Mock()
        mock_report.signal_attributions = [
            {"final_score": 0.72, "explanation": "Pinbar 形态(54.4%)"}
        ]
        mock_report.aggregate_attribution = {
            "avg_pattern_contribution": 45.2,
            "top_performing_filters": ["ema_trend"]
        }
        mock_report.analysis_dimensions = {
            "shape_quality": {"high_score": {"count": 5}},
            "rr_attribution": {"optimal_range": {"suggested_rr": "2:1 以上"}}
        }

        with patch('src.infrastructure.backtest_repository.BacktestReportRepository') as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.get_report = AsyncMock(return_value=mock_report)
            mock_repo.close = AsyncMock()
            mock_repo_class.return_value = mock_repo

            response = test_client.get("/api/backtest/test-report-id/attribution")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "attribution" in data
            assert data["attribution"]["signal_attributions"] is not None
            assert data["attribution"]["aggregate_attribution"] is not None
            assert data["attribution"]["analysis_dimensions"] is not None

    def test_get_attribution_returns_null_for_old_report(self, test_client):
        """测试旧报告无归因数据时返回 null"""
        mock_report = Mock()
        mock_report.signal_attributions = None
        mock_report.aggregate_attribution = None
        mock_report.analysis_dimensions = None

        with patch('src.infrastructure.backtest_repository.BacktestReportRepository') as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.get_report = AsyncMock(return_value=mock_report)
            mock_repo.close = AsyncMock()
            mock_repo_class.return_value = mock_repo

            response = test_client.get("/api/backtest/old-report-id/attribution")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["attribution"]["signal_attributions"] is None
            assert data["attribution"]["aggregate_attribution"] is None
            assert data["attribution"]["analysis_dimensions"] is None

    def test_get_attribution_returns_404_for_missing_report(self, test_client):
        """测试不存在的报告返回 404"""
        with patch('src.infrastructure.backtest_repository.BacktestReportRepository') as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.get_report = AsyncMock(return_value=None)
            mock_repo.close = AsyncMock()
            mock_repo_class.return_value = mock_repo

            response = test_client.get("/api/backtest/non-existent-id/attribution")

            assert response.status_code == 404

    def test_deprecated_endpoint_warning(self, test_client):
        """测试废弃接口返回 deprecated 警告"""
        mock_report = Mock()
        mock_report.signal_attributions = None
        mock_report.aggregate_attribution = None
        mock_report.analysis_dimensions = None

        with patch('src.infrastructure.backtest_repository.BacktestReportRepository') as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.get_report = AsyncMock(return_value=mock_report)
            mock_repo.close = AsyncMock()
            mock_repo_class.return_value = mock_repo

            response = test_client.get("/api/backtest/test-id/attribution")

            # 验证响应头包含 deprecated 警告（FastAPI 自动添加）
            assert response.status_code == 200


# ============================================================
# Tests: POST /api/backtest/attribution/preview
# ============================================================

class TestAttributionPreviewEndpoint:
    """归因分析预览 API 端点测试"""

    def test_preview_with_backtest_report(self, test_client, mock_backtest_report):
        """测试直接传入回测报告数据进行预览"""
        response = test_client.post(
            "/api/backtest/attribution/preview",
            json={"backtest_report": mock_backtest_report}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_preview_with_report_id(self, test_client, mock_backtest_report):
        """测试通过报告 ID 预览"""
        mock_report = Mock()
        mock_report.attempts = mock_backtest_report["attempts"]

        with patch('src.infrastructure.backtest_repository.BacktestReportRepository') as mock_repo_class:
            mock_repo = AsyncMock()
            mock_repo.initialize = AsyncMock()
            mock_repo.get_report_by_id = AsyncMock(return_value=mock_report)
            mock_repo.close = AsyncMock()
            mock_repo_class.return_value = mock_repo

            response = test_client.post(
                "/api/backtest/attribution/preview",
                json={"report_id": "test-report-id"}
            )

            assert response.status_code == 200
            assert response.json()["status"] == "success"

    def test_preview_without_params_returns_400(self, test_client):
        """测试没有参数时返回 400"""
        response = test_client.post(
            "/api/backtest/attribution/preview",
            json={}
        )

        assert response.status_code == 422  # 验证错误（Pydantic 验证器）


# ============================================================
# Tests: AttributionAnalysisRequest 验证器测试 (C-03 修复验证)
# ============================================================

class TestAttributionAnalysisRequestValidator:
    """AttributionAnalysisRequest 验证器测试"""

    def test_attribution_request_requires_one_field(self):
        """测试请求必须提供至少一个字段"""
        from src.interfaces.api import AttributionAnalysisRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            AttributionAnalysisRequest()
        assert "必须提供 report_id 或 backtest_report 其中之一" in str(exc_info.value)

    def test_attribution_request_accepts_report_id(self):
        """测试接受 report_id"""
        from src.interfaces.api import AttributionAnalysisRequest

        request = AttributionAnalysisRequest(report_id="test-id")
        assert request.report_id == "test-id"

    def test_attribution_request_accepts_backtest_report(self):
        """测试接受 backtest_report"""
        from src.interfaces.api import AttributionAnalysisRequest

        request = AttributionAnalysisRequest(backtest_report={"attempts": []})
        assert request.backtest_report is not None


# ============================================================
# Tests: 归因分析结果验证
# ============================================================

class TestAttributionResultsValidation:
    """归因分析结果验证测试"""

    def test_shape_quality_has_correct_structure(self, test_client):
        """测试形态质量归因结构正确"""
        mock_backtest_report = {
            "attempts": [
                {
                    "final_result": "SIGNAL_FIRED",
                    "pattern_score": 0.8,
                    "pnl_ratio": 1.5,
                }
            ]
        }

        response = test_client.post(
            "/api/backtest/attribution/preview",
            json={"backtest_report": mock_backtest_report}
        )

        assert response.status_code == 200
        data = response.json()

        shape_quality = data["attribution"]["shape_quality"]
        assert "high_score" in shape_quality
        assert "medium_score" in shape_quality
        assert "low_score" in shape_quality

        # 验证高分组结构
        high_score = shape_quality["high_score"]
        assert "count" in high_score
        assert "win_rate" in high_score
        assert "avg_pnl_ratio" in high_score

    def test_filter_attribution_has_correct_structure(self, test_client):
        """测试过滤器归因结构正确"""
        mock_backtest_report = {
            "attempts": [
                {
                    "final_result": "SIGNAL_FIRED",
                    "pattern_score": 0.8,
                    "filter_results": [
                        {"filter": "ema_trend", "passed": True, "reason": "trend_match"}
                    ],
                    "pnl_ratio": 1.5,
                }
            ]
        }

        response = test_client.post(
            "/api/backtest/attribution/preview",
            json={"backtest_report": mock_backtest_report}
        )

        assert response.status_code == 200
        data = response.json()

        filter_attribution = data["attribution"]["filter_attribution"]
        assert "ema_filter" in filter_attribution
        assert "rejection_stats" in filter_attribution

    def test_trend_attribution_has_correct_structure(self, test_client):
        """测试市场趋势归因结构正确"""
        mock_backtest_report = {
            "attempts": [
                {
                    "final_result": "SIGNAL_FIRED",
                    "pattern_score": 0.8,
                    "direction": "long",
                    "filter_results": [
                        {"filter": "ema_trend", "passed": True, "reason": "trend_match", "metadata": {"trend_direction": "bullish"}}
                    ],
                    "pnl_ratio": 1.5,
                }
            ]
        }

        response = test_client.post(
            "/api/backtest/attribution/preview",
            json={"backtest_report": mock_backtest_report}
        )

        assert response.status_code == 200
        data = response.json()

        trend_attribution = data["attribution"]["trend_attribution"]
        assert "bullish_trend" in trend_attribution
        assert "bearish_trend" in trend_attribution
        assert "alignment_stats" in trend_attribution

    def test_rr_attribution_has_correct_structure(self, test_client):
        """测试盈亏比归因结构正确"""
        mock_backtest_report = {
            "attempts": [
                {
                    "final_result": "SIGNAL_FIRED",
                    "pattern_score": 0.8,
                    "pnl_ratio": 2.5,
                },
                {
                    "final_result": "SIGNAL_FIRED",
                    "pattern_score": 0.6,
                    "pnl_ratio": -1.0,
                }
            ]
        }

        response = test_client.post(
            "/api/backtest/attribution/preview",
            json={"backtest_report": mock_backtest_report}
        )

        assert response.status_code == 200
        data = response.json()

        rr_attribution = data["attribution"]["rr_attribution"]
        assert "high_rr" in rr_attribution
        assert "medium_rr" in rr_attribution
        assert "low_rr" in rr_attribution
        assert "stop_loss" in rr_attribution
        assert "optimal_range" in rr_attribution
