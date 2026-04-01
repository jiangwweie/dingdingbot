# 部署报告 - MTF EMA 热重载修复 (方案 A)

**部署时间**: 2026-04-01 10:47 (UTC+8)
**版本**: v2 (commit: d94431c)
**部署类型**: Bug 修复 (MTF EMA 预热边界场景)

---

## 变更摘要

本次部署修复了配置热重载时新添加符号的 MTF EMA 未预热问题：

| 问题 | 修复前 | 修复后 |
|------|--------|--------|
| 启动时 MTF EMA 预热 | ✅ 正常 | ✅ 正常 |
| 热重载后新符号 MTF EMA | ❌ 未预热 | ✅ 自动预热 |
| `higher_tf_data_unavailable` 错误 | 可能发生 | 完全消除 |

---

## 问题背景

### 现象
虽然初始启动时 MTF EMA 预热正常，但在配置热重载（hot-reload）场景下，新添加的符号其 MTF EMA 指标未被预热，可能导致 `higher_tf_data_unavailable` 错误。

### 根因
`_build_and_warmup_runner` 方法在启动时预热所有符号的 MTF EMA，但 `on_config_updated` 方法在热重载时仅调用 `_build_and_warmup_runner`，如果 `_kline_history` 已存在（非首次启动），新符号的高周期 K 线可能已被缓存，但其 MTF EMA 未被初始化。

### 修复方案
采用**方案 A**（防御性修复）：
- 在 `on_config_updated` 方法中新增调用 `_warmup_mtf_ema_for_new_symbols()`
- 该方法遍历 `_kline_history`，查找未初始化的 MTF EMA 指标并预热
- 仅处理 1h/4h/1d 高周期，跳过已初始化的指标

---

## 部署步骤执行

### 阶段 1: 拉取最新代码

```bash
cd /usr/local/monitorDog
git fetch origin
git checkout v2
git pull origin v2
```

**结果**: ✅ 成功
```
d94431c - fix: 添加热重载时 MTF EMA 预热修复 (方案 A)
9518e17 - docs: 添加方案 C 部署报告
```

### 阶段 2: 备份数据库

```bash
mkdir -p data/backups
cp data/signals-prod.db data/backups/signals-prod.20260401-024624.db
```

**结果**: ✅ 成功

### 阶段 3: 重启 Docker 容器

```bash
docker compose down
docker compose up -d
sleep 10
```

**结果**: ✅ 成功

### 阶段 4: 健康检查

**容器状态**:
```
NAME                   IMAGE                 STATUS
monitor-dog-backend    monitordog-backend    Up (health: starting)
monitor-dog-frontend   monitordog-frontend   Up (health: starting)
```

**API 健康检查**:
```bash
curl -f http://45.76.111.81:8000/api/health
```
```json
{"status":"ok","timestamp":"2026-04-01T02:47:24Z"}
```

**前端访问**:
```bash
curl -f http://45.76.111.81/
```
**结果**: ✅ 返回 HTML 页面

**Backend 日志** (关键行):
```
[2026-04-01 10:47:10] MTF EMA warmup: checked 16 keys, warmed 1188 data points across 12 indicators
[2026-04-01 10:47:10] MTF EMA warmup complete: 1188 data points across 12 indicators ready
[2026-04-01 10:47:10] SYSTEM READY - Monitoring started
```

**结果**: ✅ 通过

---

## 代码变更

### 修改文件
`src/application/signal_pipeline.py`

### 新增方法
`_warmup_mtf_ema_for_new_symbols()` (第 383-433 行)
- 遍历 `_kline_history` 查找未初始化的 MTF EMA
- 仅处理 1h/4h/1d 高周期
- 跳过已初始化的指标
- 用历史 K 线数据预热（排除当前运行中的 K 线）

### 修改方法
`on_config_updated()` (第 279-302 行)
- 新增 Step 3: 调用 `_warmup_mtf_ema_for_new_symbols()`

### 新增测试
`tests/unit/test_mtf_ema_hot_reload.py`
- 7 个单元测试覆盖热重载场景
- 全部通过 ✅

---

## 验证清单

- [x] 容器状态正常 (`docker compose ps` 显示 Up)
- [x] API 健康检查通过 (`/api/health` 返回 200)
- [x] 前端页面可访问 (`http://45.76.111.81/`)
- [x] MTF EMA warmup 日志正常 (16 keys, 1188 data points, 12 indicators)
- [x] 数据库备份完成
- [x] 单元测试通过 (7/7)
- [x] 现有测试未被破坏 (10/10 test_mtf_ema_warmup.py)

---

## 预期效果

修复后，系统在以下场景均能正确处理 MTF EMA 预热：

| 场景 | 行为 |
|------|------|
| 首次启动 | 启动时预热所有符号的 MTF EMA |
| 配置热重载（新符号）| 自动预热新符号的 MTF EMA |
| 配置热重载（已有符号）| 跳过已初始化的 MTF EMA |
| 数据不足 | EMA 初始化为 `is_ready=False`，待数据足够后自动就绪 |

**MTF 过滤器行为**:
- 不再返回 `higher_tf_data_unavailable` 错误（除非真的没有高周期数据）
- 正确返回 `mtf_bullish` 或 `mtf_bearish` 状态

---

## 回滚方案

如需回滚到部署前版本：

```bash
cd /usr/local/monitorDog
git reset --hard 9518e17
docker compose restart
```

数据库备份位置：
```
data/backups/signals-prod.20260401-024624.db
```

---

## 相关文件

- **诊断报告**: `docs/diagnostic-reports/2026-04-01-MTF-EMA 预热缺失问题修复报告.md`
- **修复提交**: `d94431c`
- **测试文件**: `tests/unit/test_mtf_ema_hot_reload.py`

---

## 部署人员

**运维工程师**: DevOps Agent
**后端开发**: Backend Dev Agent
**测试专家**: QA Agent
**审查人员**: Code Reviewer Agent
**协调员**: Team Coordinator

---

**部署状态**: ✅ 完成
