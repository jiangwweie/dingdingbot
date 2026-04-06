# test_config_import_export_e2e.py 测试设计文档

**创建日期**: 2026-04-06  
**优先级**: P1  
**状态**: 设计中

---

## 1. 测试文件路径

```
tests/e2e/test_config_import_export_e2e.py
```

---

## 2. 测试目标

验证配置导入导出功能的端到端流程，包括：
- 配置导出 API 返回有效 YAML
- 配置导入预览正确识别变更和冲突
- 配置导入确认正确应用变更
- 预览 Token 有效期验证
- 回滚功能验证
- 边界条件和异常情况处理

---

## 3. 测试用例清单 (8 个)

### 3.1 导出流程测试

```python
class TestExportFlow:
    """测试配置导出功能"""
    
    def test_export_returns_valid_yaml(self, client_with_config):
        """验证导出接口返回有效的 YAML 格式"""
        # 执行导出
        response = client.post("/api/v1/config/export", json={
            "include_risk": True,
            "include_system": True,
            "include_strategies": True,
            "include_symbols": True,
            "include_notifications": True,
        }, headers={"X-User-Role": "admin"})
        
        # 验证响应状态码
        assert response.status_code == 200
        
        # 验证 Content-Type
        data = response.json()
        assert "yaml_content" in data
        
        # 验证 YAML 可解析
        import yaml
        parsed = yaml.safe_load(data["yaml_content"])
        assert isinstance(parsed, dict)
        
        # 验证包含所有配置段
        assert "risk" in parsed
        assert "system" in parsed
        assert "strategies" in parsed
        assert "symbols" in parsed
        assert "notifications" in parsed
        
    def test_export_filename_format(self, client_with_config):
        """验证导出文件名格式正确"""
        response = client.post("/api/v1/config/export", json={
            "include_risk": True,
        }, headers={"X-User-Role": "admin"})
        
        data = response.json()
        filename = data["filename"]
        
        # 验证格式：config_backup_YYYYMMDD_HHMMSS.yaml
        assert filename.startswith("config_backup_")
        assert filename.endswith(".yaml")
        # 验证包含时间戳
        import re
        assert re.match(r'config_backup_\d{8}_\d{6}\.yaml', filename)
```

### 3.2 导入预览测试

```python
class TestImportPreview:
    """测试配置导入预览功能"""
    
    def test_preview_shows_changes_summary(self, client, temp_config_yaml):
        """验证预览显示变更摘要"""
        response = client.post("/api/v1/config/import/preview", json={
            "yaml_content": temp_config_yaml,
            "filename": "test_config.yaml",
        }, headers={"X-User-Role": "admin"})
        
        assert response.status_code == 200
        data = response.json()
        
        # 验证预览有效
        assert data["valid"] is True
        assert "preview_token" in data
        assert data["preview_token"] is not None
        
        # 验证变更摘要
        summary = data["summary"]
        assert "strategies" in summary
        assert "symbols" in summary
        assert "risk" in summary
        
        # 验证新增/修改/删除数量
        assert "added" in summary["strategies"]
        assert "modified" in summary["strategies"]
        assert "deleted" in summary["strategies"]
        
    def test_preview_detects_conflicts(self, client, duplicate_strategy_yaml):
        """验证预览检测命名冲突"""
        response = client.post("/api/v1/config/import/preview", json={
            "yaml_content": duplicate_strategy_yaml,
            "filename": "conflict_config.yaml",
        }, headers={"X-User-Role": "admin"})
        
        data = response.json()
        
        # 验证检测到冲突
        assert "conflicts" in data
        assert len(data["conflicts"]) > 0
        assert any("Duplicate" in c for c in data["conflicts"])
        
    def test_preview_detects_restart_required(self, client, sample_config_yaml):
        """验证预览识别需要重启的配置"""
        response = client.post("/api/v1/config/import/preview", json={
            "yaml_content": sample_config_yaml,
            "filename": "system_change.yaml",
        }, headers={"X-User-Role": "admin"})
        
        data = response.json()
        
        # system.core_symbols 变更需要重启
        assert data["requires_restart"] is True
        assert "restart_required_sections" in data
        assert "system" in data["restart_required_sections"]
```

### 3.3 导入确认测试

```python
class TestImportConfirm:
    """测试配置导入确认功能"""
    
    def test_confirm_applies_changes(self, client, temp_config_yaml):
        """验证确认导入后配置正确应用"""
        # 步骤 1: 预览
        preview_response = client.post("/api/v1/config/import/preview", json={
            "yaml_content": temp_config_yaml,
            "filename": "test_apply.yaml",
        }, headers={"X-User-Role": "admin"})
        preview_token = preview_response.json()["preview_token"]
        
        # 步骤 2: 确认导入
        confirm_response = client.post("/api/v1/config/import/confirm", json={
            "preview_token": preview_token,
        }, headers={"X-User-Role": "admin"})
        
        assert confirm_response.status_code == 200
        data = confirm_response.json()
        assert data["status"] == "success"
        
        # 步骤 3: 验证配置已应用
        risk_response = client.get("/api/v1/config/risk")
        risk_data = risk_response.json()
        assert risk_data["max_loss_percent"] == "0.02"  # YAML 中的值
        
    def test_confirm_creates_snapshot(self, client, temp_config_yaml):
        """验证确认导入时自动创建快照"""
        # 预览
        preview_response = client.post("/api/v1/config/import/preview", json={
            "yaml_content": temp_config_yaml,
            "filename": "snapshot_test.yaml",
        }, headers={"X-User-Role": "admin"})
        preview_token = preview_response.json()["preview_token"]
        
        # 确认导入
        confirm_response = client.post("/api/v1/config/import/confirm", json={
            "preview_token": preview_token,
        }, headers={"X-User-Role": "admin"})
        
        # 验证创建快照
        data = confirm_response.json()
        assert "snapshot_id" in data
        assert data["snapshot_id"] is not None
        
        # 验证快照存在
        snapshot_id = data["snapshot_id"]
        snapshot_response = client.get(f"/api/v1/config/snapshots/{snapshot_id}")
        assert snapshot_response.status_code == 200
        
    def test_confirm_cleans_preview_cache(self, client, temp_config_yaml):
        """验证确认导入后清理预览缓存"""
        from src.interfaces.api_v1_config import _import_preview_cache
        
        # 预览
        preview_response = client.post("/api/v1/config/import/preview", json={
            "yaml_content": temp_config_yaml,
            "filename": "cleanup_test.yaml",
        }, headers={"X-User-Role": "admin"})
        preview_token = preview_response.json()["preview_token"]
        
        # 验证 token 在缓存中
        assert preview_token in _import_preview_cache
        
        # 确认导入
        client.post("/api/v1/config/import/confirm", json={
            "preview_token": preview_token,
        }, headers={"X-User-Role": "admin"})
        
        # 验证 token 已从缓存清除
        assert preview_token not in _import_preview_cache
```

### 3.4 冲突检测测试

```python
class TestConflictDetection:
    """测试配置导入冲突检测"""
    
    def test_import_with_conflicts_shows_warning(self, client, duplicate_strategy_yaml):
        """验证导入冲突配置时显示警告"""
        response = client.post("/api/v1/config/import/preview", json={
            "yaml_content": duplicate_strategy_yaml,
            "filename": "conflict_test.yaml",
        }, headers={"X-User-Role": "admin"})
        
        data = response.json()
        
        # 验证冲突列表
        assert data["valid"] is True  # YAML 本身有效
        assert "conflicts" in data
        assert len(data["conflicts"]) > 0
        
        # 验证冲突详情
        for conflict in data["conflicts"]:
            assert "entity_type" in conflict
            assert "entity_id" in conflict
            assert "message" in conflict
```

### 3.5 回滚验证测试

```python
class TestRollback:
    """测试配置回滚功能"""
    
    def test_rollback_after_import(self, client):
        """验证导入后执行回滚恢复到导入前状态"""
        # 步骤 1: 记录导入前配置
        before_response = client.get("/api/v1/config/risk")
        before_data = before_response.json()
        original_max_loss = before_data["max_loss_percent"]
        
        # 步骤 2: 导入新配置
        new_yaml = """
risk:
  max_loss_percent: 0.03
  max_leverage: 30
"""
        preview_response = client.post("/api/v1/config/import/preview", json={
            "yaml_content": new_yaml,
            "filename": "rollback_test.yaml",
        }, headers={"X-User-Role": "admin"})
        preview_token = preview_response.json()["preview_token"]
        
        confirm_response = client.post("/api/v1/config/import/confirm", json={
            "preview_token": preview_token,
        }, headers={"X-User-Role": "admin"})
        snapshot_id = confirm_response.json()["snapshot_id"]
        
        # 步骤 3: 验证配置已变更
        after_response = client.get("/api/v1/config/risk")
        after_data = after_response.json()
        assert after_data["max_loss_percent"] == "0.03"
        
        # 步骤 4: 执行回滚
        rollback_response = client.post(
            f"/api/v1/config/snapshots/{snapshot_id}/activate",
            headers={"X-User-Role": "admin"}
        )
        assert rollback_response.status_code == 200
        
        # 步骤 5: 验证配置已恢复
        restored_response = client.get("/api/v1/config/risk")
        restored_data = restored_response.json()
        assert restored_data["max_loss_percent"] == original_max_loss
```

### 3.6 边界条件测试

```python
class TestBoundaryConditions:
    """测试边界条件和异常情况"""
    
    def test_import_invalid_yaml_returns_400(self, client):
        """验证导入无效 YAML 返回 400"""
        invalid_yaml = """
risk:
  [invalid yaml syntax
  max_loss_percent: 0.01
"""
        response = client.post("/api/v1/config/import/preview", json={
            "yaml_content": invalid_yaml,
            "filename": "invalid.yaml",
        }, headers={"X-User-Role": "admin"})
        
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0
        
    def test_import_yaml_root_not_mapping(self, client):
        """验证 YAML 根节点不是映射时返回错误"""
        yaml_content = """
- item1
- item2
"""
        response = client.post("/api/v1/config/import/preview", json={
            "yaml_content": yaml_content,
            "filename": "list_root.yaml",
        }, headers={"X-User-Role": "admin"})
        
        data = response.json()
        assert data["valid"] is False
        assert any("root" in e.lower() for e in data["errors"])
        
    def test_preview_token_expiry(self, client, temp_config_yaml):
        """验证预览 Token 过期后无法使用"""
        from datetime import datetime, timezone, timedelta
        from src.interfaces.api_v1_config import _import_preview_cache
        
        # 预览
        preview_response = client.post("/api/v1/config/import/preview", json={
            "yaml_content": temp_config_yaml,
            "filename": "expiry_test.yaml",
        }, headers={"X-User-Role": "admin"})
        preview_token = preview_response.json()["preview_token"]
        
        # 手动过期 token
        _import_preview_cache[preview_token]["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(minutes=10)
        )
        
        # 确认导入应该失败
        confirm_response = client.post("/api/v1/config/import/confirm", json={
            "preview_token": preview_token,
        }, headers={"X-User-Role": "admin"})
        
        assert confirm_response.status_code == 400
        data = confirm_response.json()
        assert "expired" in data.get("error", "").lower()
        
    def test_import_nonexistent_token_returns_400(self, client):
        """验证使用不存在的 token 返回 400"""
        response = client.post("/api/v1/config/import/confirm", json={
            "preview_token": "nonexistent-token-12345",
        }, headers={"X-User-Role": "admin"})
        
        assert response.status_code == 400
```

---

## 4. Fixtures 设计

```python
# ============================================================
# Pytest Fixtures
# ============================================================

@pytest.fixture
def temp_config_yaml() -> str:
    """生成临时 YAML 配置字符串"""
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


@pytest.fixture
def duplicate_strategy_yaml() -> str:
    """生成包含重复策略名称的 YAML"""
    return """
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


@pytest.fixture
def client_with_config(temp_config_dir) -> TestClient:
    """创建带配置的测试客户端"""
    from src.interfaces.api_v1_config import app, set_config_dependencies
    from src.infrastructure.repositories.config_repositories import ConfigDatabaseManager
    
    # 初始化数据库
    db_manager = ConfigDatabaseManager(":memory:")
    await db_manager.initialize()
    
    # 注入依赖
    set_config_dependencies(
        strategy_repo=db_manager.strategy_repo,
        risk_repo=db_manager.risk_repo,
        system_repo=db_manager.system_repo,
        symbol_repo=db_manager.symbol_repo,
        notification_repo=db_manager.notification_repo,
        history_repo=db_manager.history_repo,
        snapshot_repo=db_manager.snapshot_repo,
    )
    
    with TestClient(app) as client:
        yield client
    
    await db_manager.close()


@pytest.fixture
async def preview_token(client, temp_config_yaml) -> str:
    """创建有效的预览 token"""
    response = client.post("/api/v1/config/import/preview", json={
        "yaml_content": temp_config_yaml,
        "filename": "test.yaml",
    }, headers={"X-User-Role": "admin"})
    return response.json()["preview_token"]


@pytest.fixture
def temp_config_dir():
    """创建临时配置目录"""
    import tempfile
    from pathlib import Path
    import yaml
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        
        # 创建 core.yaml
        core_config = {
            "core_symbols": ["BTC/USDT:USDT", "ETH/USDT:USDT"],
            "pinbar_defaults": {
                "min_wick_ratio": "0.6",
                "max_body_ratio": "0.3",
            },
            "ema": {"period": 60},
            "mtf_mapping": {"15m": "1h"},
        }
        with open(config_dir / "core.yaml", "w") as f:
            yaml.dump(core_config, f)
        
        # 创建 user.yaml
        user_config = {
            "exchange": {
                "name": "binance",
                "api_key": "test_api_key",
                "api_secret": "test_secret",
                "testnet": True,
            },
            "user_symbols": ["SOL/USDT:USDT"],
            "risk": {
                "max_loss_percent": "0.01",
                "max_leverage": 10,
            },
        }
        with open(config_dir / "user.yaml", "w") as f:
            yaml.dump(user_config, f)
        
        yield config_dir
```

---

## 5. Mock 策略

```python
# ============================================================
# 测试辅助 Mock
# ============================================================

class MockConfigManager:
    """模拟配置管理器"""
    
    def __init__(self):
        self.current_config = {
            "risk": {
                "max_loss_percent": Decimal("0.01"),
                "max_leverage": 10,
            },
            "system": {
                "core_symbols": ["BTC/USDT:USDT"],
                "ema_period": 60,
            },
        }
    
    def get_config(self):
        return self.current_config
    
    def hot_reload(self, new_config):
        self.current_config.update(new_config)


class MockObserver:
    """模拟配置变更通知器"""
    
    def __init__(self):
        self.notifications = []
    
    def notify_change(self, entity_type, entity_id, new_values):
        self.notifications.append({
            "entity_type": entity_type,
            "entity_id": entity_id,
            "new_values": new_values,
        })
```

---

## 6. 验收标准

### 6.1 功能验收

| 编号 | 验收项 | 预期结果 |
|------|--------|----------|
| F-1 | 导出配置 | 返回有效 YAML，包含所有配置段 |
| F-2 | 导出文件名 | 符合 config_backup_YYYYMMDD_HHMMSS.yaml 格式 |
| F-3 | 导入预览 | 返回 preview_token 和变更摘要 |
| F-4 | 变更摘要 | 显示新增/修改/删除数量 |
| F-5 | 冲突检测 | 正确识别重复命名冲突 |
| F-6 | 重启检测 | 识别需要重启的配置段 |
| F-7 | 导入确认 | 正确应用配置变更 |
| F-8 | 自动快照 | 导入前自动创建快照 |
| F-9 | 回滚功能 | 可恢复到导入前状态 |
| F-10 | 缓存清理 | 确认后清理预览 token |

### 6.2 错误处理验收

| 编号 | 错误场景 | 预期行为 |
|------|----------|----------|
| E-1 | 无效 YAML | 返回 valid=false 和错误列表 |
| E-2 | YAML 根节点非映射 | 返回错误提示 |
| E-3 | 策略非列表格式 | 返回错误提示 |
| E-4 | 不存在的 token | 返回 400 错误 |
| E-5 | Token 过期 | 返回 400 错误，提示已过期 |

### 6.3 历史记验收

| 编号 | 验收项 | 预期结果 |
|------|--------|----------|
| H-1 | 导出记录 | 历史表记录 EXPORT 操作 |
| H-2 | 导入记录 | 历史表记录 IMPORT 操作 |
| H-3 | 记录字段 | 包含 filename/sections/snapshot_id |

---

## 7. 参考文件

- API 实现：`src/interfaces/api_v1_config.py`
- 现有 E2E 参考：`tests/e2e/test_api_config.py`
- 后端单元测试：`tests/unit/test_config_import_export.py`

---

## 8. 测试数据流

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  创建测试配置    │────▶│  导出配置 (POST)  │────▶│  验证 YAML 格式   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  验证回滚恢复    │◀────│  激活快照 (POST)   │◀────│  创建快照       │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                                              ▲
         ▼                                              │
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  清理测试数据    │◀────│  确认导入 (POST)   │◀────│  预览导入 (POST) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```
