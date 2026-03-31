# 部署报告 - 方案 C 回测引擎重构

**部署时间**: 2026-03-31 16:55 (UTC+8)
**版本**: v2 (commit: 3d75754)
**部署类型**: 架构重构 + Bug 修复

---

## 变更摘要

本次部署修复了回测引擎 ATR 过滤器缺失问题：

| 问题 | 修复前 | 修复后 |
|------|--------|--------|
| 回测过滤器 | 仅 EMA + MTF | EMA + MTF + ATR |
| 实盘过滤器 | EMA + MTF + ATR | EMA + MTF + ATR |
| 一致性 | ❌ 不一致 | ✅ 一致 |

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
3d75754 - docs: 添加方案 C 实施报告和更新诊断报告
c469943 - feat: 统一回测引擎使用 DynamicStrategyRunner (方案 C)
6ddc63a - fix: 修复前端部署路径和信号标记文本
```

---

### 阶段 2: 构建前端

```bash
cd /usr/local/monitorDog/web-front
npm ci
npm run build
cp -r dist/* /usr/local/monitorDog/build/dist/
```

**结果**: ✅ 成功 (构建耗时 3.46s)

---

### 阶段 3: 备份数据库

```bash
mkdir -p /usr/local/monitorDog/data/backups
cp /usr/local/monitorDog/data/signals-prod.db \
   /usr/local/monitorDog/data/backups/signals-prod.db.20260331-085450
```

**结果**: ✅ 成功

---

### 阶段 4: 重启 Docker 容器

```bash
docker-compose down
docker-compose up -d
sleep 10
```

**结果**: ✅ 成功

---

### 阶段 5: 健康检查

**容器状态**:
```
monitor-dog-backend   Up
monitor-dog-frontend  Up
```

**API 健康检查**:
```bash
curl -f http://localhost:8000/api/health
```
```json
{"status":"ok","timestamp":"2026-03-31T08:55:49Z"}
```

**Backend 日志** (最新 16 条):
- WebSocket 订阅全部建立 (16 个品种/周期组合)
- 无错误日志

**结果**: ✅ 通过

---

### 阶段 6: 回测功能验证

```bash
curl -X POST http://localhost:8000/api/backtest \
  -H "Content-Type: application/json" \
  -d '{"symbol": "ETH/USDT:USDT", "timeframe": "1h", "limit": 10}'
```

**结果**: ✅ 正常响应，ATR 过滤器已集成

---

## 验证清单

- [x] 容器状态正常 (`docker-compose ps` 显示 Up)
- [x] API 健康检查通过 (`/api/health` 返回 200)
- [x] 前端页面可访问 (`http://45.76.111.81/`)
- [x] 回测 API 正常响应
- [x] 数据库备份完成

---

## 预期效果

修复后，回测信号将通过完整的过滤器链：

| 过滤器 | 状态 |
|--------|------|
| EMA Trend | ✅ 启用 |
| MTF | ✅ 启用 |
| **ATR Volatility** | ✅ **启用 (新增)** |
| Volume Surge | ✅ 支持 |

- ATR 过滤器拒绝波动率 < 0.5% 的信号
- 止损距离过近的信号将被正确过滤
- 回测与实盘结果一致性提升

---

## 回滚方案

如需回滚到部署前版本：

```bash
cd /usr/local/monitorDog
git reset --hard 6ddc63a
docker-compose restart
```

---

## 部署人员

**运维工程师**: DevOps Agent
**审查人员**: Backend Dev + Team Coordinator

---

**部署状态**: ✅ 完成
