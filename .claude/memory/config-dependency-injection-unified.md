---
name: 配置依赖注入统一修复（方案 C）
description: 2026-04-12 /api/v1/config/* 全线 503 修复，统一两条依赖注入链路
type: project
---

**问题**：`lifespan="off"` 导致 7 个配置 Repository 未初始化，`/api/v1/config/*` 全线返回 503。

**修复方案**（方案 C - 统一链路）：
- `main.py` Phase 9 新增 7 个 Repository 初始化 + `set_dependencies()` 传参
- `api.py` `set_dependencies()` 扩容接收 7 个参数，写入 `api_config_globals` 模块
- 新增 `api_config_globals.py` 打破 `api.py` ↔ `api_v1_config.py` 循环导入
- `api_v1_config.py` 删除 `set_config_dependencies()` + 改为从 `api_config_globals` import
- 清理 `lifespan()` 中 40+ 行死代码

**验收**：12 个 `/api/v1/config/*` GET 端点 11/12 返回 200。

**独立问题**（非本次修复引入）：
1. `/api/v1/config/effective` → 500（`ConfigManager.get_system_config()` 不存在）
2. `test_config_repository.py` 3 个测试失败（`AssetPollingConfig` NameError）
3. `exchange_configs` 表 API Key/Secret 为空时需手动写入数据库
