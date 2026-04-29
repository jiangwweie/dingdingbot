# Phase 5 开发准备清单

**创建日期**: 2026-03-30
**状态**: ✅ 准备就绪

---

## ✅ 已完成准备

### 1. 技术文档

| 文档 | 状态 | 说明 |
|------|------|------|
| Phase 5 契约表 v1.3 | ✅ 完成 | 包含 DCA + 资金保护 + 飞书告警 |
| 环境兼容性分析 | ✅ 完成 | 三环境物理隔离策略 |
| 审查报告 v1.3 | ✅ 完成 | 所有问题已修复 |

### 2. 用户确认事项

| 事项 | 决策 |
|------|------|
| 测试网 API 密钥 | ✅ 已准备好 |
| DCA 分批建仓 | ✅ Phase 5 实现 |
| 资金安全限制 | ✅ Phase 5 实现 |
| 告警渠道 | ✅ 飞书 |
| 服务器位置 | ✅ 东京 AWS（预留香港切换） |

### 3. 核心设计

| 模块 | 状态 |
|------|------|
| ExchangeGateway 扩展 | ✅ 设计完成 |
| WebSocket 去重逻辑 | ✅ 基于 filled_qty 推进 |
| 并发保护机制 | ✅ 双层锁（Asyncio + DB 行锁） |
| 内存锁清理 | ✅ 平仓后自动清理 |
| 资金保护管理器 | ✅ 单笔/每日/仓位限制 |
| DCA 分批建仓 | ✅ 2-5 批次，支持价格/跌幅触发 |
| 飞书告警集成 | ✅ 多事件类型支持 |
| 区域切换 | ✅ 东京↔香港脚本 |

---

## 📋 开发任务清单

| 编号 | 任务 | 预计工时 | 优先级 |
|------|------|----------|--------|
| T-001 | ExchangeGateway 订单接口 | 4h | P0 |
| T-002 | WebSocket 订单推送监听 | 4h | P0 |
| T-003 | 并发保护机制实现 | 4h | P0 |
| T-004 | 启动对账服务 | 4h | P0 |
| T-005 | 资金保护管理器 | 3h | P0 |
| T-006 | DCA 分批建仓实现 | 6h | P0 |
| T-007 | 飞书告警集成 | 2h | P1 |
| T-008 | 区域切换支持 | 2h | P2 |
| T-009 | 单元测试编写 | 6h | P0 |
| T-010 | 集成测试编写 | 8h | P0 |

**预计总工时**: ~39 小时（约 5 个工作日）

---

## 🔧 开发前检查清单

### 环境准备

- [ ] 确认 Binance 测试网 API 密钥可用
- [ ] 确认东京 AWS 服务器可访问
- [ ] 准备飞书 Webhook URL
- [ ] 配置环境变量（.env 文件）

### 依赖安装

```bash
# 确认 CCXT 版本
pip install ccxt>=4.2.24

# 确认其他依赖
pip install -r requirements.txt
```

### 配置准备

```yaml
# .env

# 交易所配置
EXCHANGE_NAME=binance
EXCHANGE_TESTNET=true
EXCHANGE_API_KEY=<你的测试网 API 密钥>
EXCHANGE_API_SECRET=<你的测试网 API 密钥>

# 数据库配置
DATABASE_URL=sqlite+aiosqlite:///./data/v3_dev.db  # 开发

# 飞书配置
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx

# 资金保护配置
CAPITAL_PROTECTION_ENABLED=true
SINGLE_TRADE_MAX_LOSS_PERCENT=2.0
DAILY_MAX_LOSS_PERCENT=5.0
```

---

## 🚀 启动命令

```bash
# 1. 创建任务清单
# (使用 TaskCreate)

# 2. 启动开发
/coordinator Phase 5 实盘集成开发

# 3. 运行测试
pytest tests/unit/test_capital_protection.py -v
pytest tests/unit/test_dca_strategy.py -v
pytest tests/integration/ -v
```

---

## 📊 预期交付时间

| 里程碑 | 日期 | 交付内容 |
|--------|------|----------|
| Week 1 | T+5 天 | 核心功能完成（T-001 ~ T-006） |
| Week 2 | T+2 天 | 测试完成（T-009 ~ T-010） |

---

*准备清单 v1.0*
*2026-03-30*
