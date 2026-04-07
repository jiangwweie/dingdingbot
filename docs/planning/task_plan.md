# 任务计划：P1-1 和 P1-2 配置修复

> **创建时间**: 2026-04-07
> **状态**: 已完成 ✅

---

## 任务概述

### P1-1: Decimal YAML 精度修复
- **文件位置**: `src/interfaces/api_v1_config.py:57-71`
- **问题**: Decimal 被转换为 float 后序列化，精度丢失
- **方案**: 使用字符串表示 Decimal

### P1-2: 缓存 TTL 机制
- **文件位置**: `src/interfaces/api_v1_config.py:1457-1460`
- **问题**: 预览数据永久占用内存，无过期机制
- **方案**: 使用 cachetools.TTLCache

---

## 任务分解

### P1-1 实施步骤
- [x] 读取当前实现代码
- [x] 修改 `_decimal_representer` 使用字符串表示
- [x] 添加 `_decimal_constructor` 用于反序列化
- [x] 更新 `_convert_decimals_to_str` 函数（原 `_convert_decimals_to_float`）
- [x] 编写测试用例验证精度
- [x] 运行测试验证（3 个测试全部通过）

### P1-2 实施步骤
- [x] 确认项目依赖是否有 cachetools (确认：无)
- [x] 添加 cachetools 到 requirements.txt
- [x] 替换 `_import_preview_cache` 为 TTLCache
- [x] 更新使用 TTLCache 的代码（移除手动过期检查）
- [x] 更新 `ImportPreviewResult` 模型（移除 `expires_at` 字段）
- [x] 编写测试用例验证 TTL 机制
- [x] 运行测试验证（4 个测试全部通过）

---

## 测试结果

### P1-1 Decimal 精度测试
```
tests/unit/test_config_import_export.py::TestDecimalYamlPrecision::test_decimal_representer_preserves_precision PASSED
tests/unit/test_config_import_export.py::TestDecimalYamlPrecision::test_decimal_representer_complex_config PASSED
tests/unit/test_config_import_export.py::TestDecimalYamlPrecision::test_export_preserves_decimal_precision PASSED
```

### P1-2 TTL 缓存测试
```
tests/unit/test_config_import_export.py::TestTTLCacheExpiry::test_preview_token_stored_in_ttl_cache PASSED
tests/unit/test_config_import_export.py::TestTTLCacheExpiry::test_ttl_cache_maxsize PASSED
tests/unit/test_config_import_export.py::TestTTLCacheExpiry::test_confirm_import_removes_token_from_cache PASSED
tests/unit/test_config_import_export.py::TestTTLCacheExpiry::test_invalid_token_returns_400 PASSED
```

### 完整测试套件
```
36 passed in 0.96s - 无回归
```

---

## 进度追踪

| 时间 | 任务 | 状态 |
|------|------|------|
| 2026-04-07 | P1-1 实施 | 已完成 ✅ |
| 2026-04-07 | P1-2 实施 | 已完成 ✅ |
| 2026-04-07 | 测试验证 | 已完成 ✅ |
| 2026-04-07 | 代码提交 | 待执行 |

---

## 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `src/interfaces/api_v1_config.py` | P1-1: Decimal representer 改为字符串表示；P1-2: TTLCache 替换 Dict |
| `requirements.txt` | 添加 `cachetools>=5.3.0` 依赖 |
| `tests/unit/test_config_import_export.py` | 新增 7 个测试用例（P1-1: 3 个，P1-2: 4 个） |

---

## 依赖关系

- P1-1 和 P1-2 串行执行（同一文件，避免冲突）
- 两个任务都完成后统一测试提交
