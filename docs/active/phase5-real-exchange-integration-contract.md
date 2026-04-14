# Phase 5: 实盘集成 - 契约表 (v1.3)

**创建日期**: 2026-03-30
**修订日期**: 2026-03-30
**状态**: ✅ 审查通过，待开发
**修订版本**: v1.3 (用户确认后修订)
**审查状态**: ✅ 已通过 (所有问题已修复)

---

## 修订记录

| 版本 | 日期 | 修订内容 | 修订人 |
|------|------|----------|--------|
| v1.0 | 2026-03-30 | 初稿 | - |
| v1.1 | 2026-03-30 | 修复 H-001/H-002/H-003 高优先级问题 | - |
| v1.2 | 2026-03-30 | 修复 Gemini 指出的 4 个关键问题 | - |
| v1.3 | 2026-03-30 | 添加 DCA + 资金安全限制设计 | - |

### v1.3 新增内容

| 功能 | 说明 | 状态 |
|------|------|------|
| **DCA 分批建仓** | 2-5 批次入场，支持价格/跌幅触发 | ✅ 新增 |
| **资金安全限制** | 单笔/每日/单次仓位限制 | ✅ 新增 |
| **飞书告警** | 异常事件通知推送 | ✅ 新增 |
| **香港服务器切换** | 预留多区域部署能力 | ✅ 新增 |

---

## 17. 资金安全限制设计（v1.3 新增）

### 17.1 配置参数

```yaml
# config/core.yaml

capital_protection:
  enabled: true  # 是否启用资金保护

  # 单笔交易限制
  single_trade:
    max_loss_percent: 2.0    # 单笔最大损失 2% of balance
    max_position_percent: 20 # 单次最大仓位 20% of balance

  # 每日限制
  daily:
    max_loss_percent: 5.0    # 每日最大回撤 5% of balance
    max_trade_count: 50      # 每日最大交易次数

  # 账户限制
  account:
    min_balance: 100         # 最低余额保留 (USDT)
    max_leverage: 10         # 最大杠杆倍数
```

### 17.2 检查逻辑

```python
class CapitalProtectionManager:
    """
    资金保护管理器

    职责:
    1. 下单前检查资金限制
    2. 追踪每日交易统计
    3. 触发限制时阻止下单并告警
    """

    def __init__(
        self,
        config: CapitalProtectionConfig,
        account_service: AccountService,
        notifier: Notifier,
    ):
        self._config = config
        self._account = account_service
        self._notifier = notifier

        # 每日统计
        self._daily_stats = DailyTradeStats()

    async def pre_order_check(
        self,
        symbol: str,
        order_type: OrderType,
        amount: Decimal,
        price: Decimal,
    ) -> OrderCheckResult:
        """
        下单前检查

        检查项:
        1. 单笔损失是否超限
        2. 仓位占比是否超限
        3. 每日亏损是否超限
        4. 每日交易次数是否超限
        5. 账户余额是否充足
        """
        balance = await self._account.get_balance()

        # 检查 1: 单笔最大损失
        max_loss = balance * (self._config.single_trade.max_loss_percent / 100)
        estimated_loss = self._calculate_max_loss(amount, price)
        if estimated_loss > max_loss:
            await self._notifier.send_alert(
                "单笔交易损失超限",
                f"预计损失 {estimated_loss} > 限制 {max_loss}"
            )
            return OrderCheckResult(
                allowed=False,
                reason="SINGLE_TRADE_LOSS_LIMIT"
            )

        # 检查 2: 单次最大仓位
        max_position = balance * (self._config.single_trade.max_position_percent / 100)
        position_value = amount * price
        if position_value > max_position:
            await self._notifier.send_alert(
                "单次仓位超限",
                f"仓位价值 {position_value} > 限制 {max_position}"
            )
            return OrderCheckResult(
                allowed=False,
                reason="POSITION_LIMIT"
            )

        # 检查 3: 每日最大亏损
        if self._daily_stats.realized_pnl < -max_loss:
            await self._notifier.send_alert(
                "每日亏损超限",
                f"已亏损 {self._daily_stats.realized_pnl} < 限制 {-max_loss}"
            )
            return OrderCheckResult(
                allowed=False,
                reason="DAILY_LOSS_LIMIT"
            )

        # 检查 4: 每日交易次数
        if self._daily_stats.trade_count >= self._config.daily.max_trade_count:
            return OrderCheckResult(
                allowed=False,
                reason="DAILY_TRADE_COUNT_LIMIT"
            )

        # 检查 5: 最低余额
        if balance <= self._config.account.min_balance:
            await self._notifier.send_alert(
                "账户余额不足",
                f"余额 {balance} < 最低要求 {self._config.account.min_balance}"
            )
            return OrderCheckResult(
                allowed=False,
                reason="INSUFFICIENT_BALANCE"
            )

        return OrderCheckResult(allowed=True)

    def _calculate_max_loss(self, amount: Decimal, price: Decimal) -> Decimal:
        """计算最大可能损失（假设止损打满）"""
        # 简化计算：假设止损 1R
        return amount * price * Decimal('0.01')  # 1% 损失
```

### 17.3 每日统计重置

```python
class DailyTradeStats:
    """每日交易统计"""

    trade_count: int = 0
    realized_pnl: Decimal = Decimal('0')
    last_reset_date: date = date.today()

    def reset_if_new_day(self):
        """如果是新的一天，重置统计"""
        today = date.today()
        if today != self.last_reset_date:
            self.trade_count = 0
            self.realized_pnl = Decimal('0')
            self.last_reset_date = today
```

---

## 18. DCA 分批建仓设计（v1.3 扩展）

### 18.1 完整 DCA 流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    DCA 分批建仓流程                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 策略生成 Signal                                               │
│         │                                                        │
│         ▼                                                        │
│  2. OrderManager 创建 DCA 订单链                                  │
│         │                                                        │
│         ▼                                                        │
│  3. 执行第 1 批 (50% 仓位，市价单)                                    │
│         │                                                        │
│         ▼                                                        │
│  4. 监听成交 → 更新 DCA 状态                                       │
│         │                                                        │
│         ▼                                                        │
│  5. 检查第 2 批条件 (跌幅 2%)                                       │
│         │                                                        │
│         ▼                                                        │
│  6. 条件触发 → 执行第 2 批 (30% 仓位，限价单)                         │
│         │                                                        │
│         ▼                                                        │
│  7. 检查第 3 批条件 (跌幅 4%)                                       │
│         │                                                        │
│         ▼                                                        │
│  8. 条件触发 → 执行第 3 批 (20% 仓位，限价单)                         │
│         │                                                        │
│         ▼                                                        │
│  9. 全部完成 → 生成 TP/SL 订单                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 18.2 DCA 配置示例

```yaml
# config/strategies/dca_martingale.yaml

strategy:
  id: "dca_martingale_v1"
  name: "马丁格尔 DCA"
  type: "DCA"

  # 批次配置
  entry_batches: 3
  entry_ratios: [0.5, 0.3, 0.2]  # 50% / 30% / 20%

  # 触发条件
  trigger_type: "percentage_drop"

  # 各批次触发条件
  batch_triggers:
    - batch_index: 1
      order_type: "MARKET"  # 市价单立即入场
      ratio: 0.5

    - batch_index: 2
      order_type: "LIMIT"
      trigger_drop_percent: -2.0  # 相对首批下跌 2% 触发
      ratio: 0.3

    - batch_index: 3
      order_type: "LIMIT"
      trigger_drop_percent: -4.0  # 相对首批下跌 4% 触发
      ratio: 0.2

  # 成本计算
  cost_basis_mode: "average"  # 平均成本

  # 止盈配置
  take_profit:
    tp_levels: 2
    tp_ratios: [0.6, 0.4]
    tp_targets: [1.5, 2.0]  # 1.5R / 2.0R

  # 止损配置
  stop_loss:
    initial_stop_loss_rr: -1.0  # 1R 止损
    trailing_stop: true
    trailing_percent: 2.0
```

---

## 19. 飞书告警集成（v1.3 新增）

### 19.1 告警事件类型

| 事件类型 | 级别 | 说明 | 示例 |
|----------|------|------|------|
| `ORDER_FILLED` | INFO | 订单成交通知 | TP1 成交，盈利 50 USDT |
| `ORDER_FAILED` | WARNING | 订单失败 | 保证金不足，下单被拒 |
| `DAILY_LOSS_LIMIT` | ERROR | 每日亏损超限 | 已亏损 150 USDT > 限制 100 USDT |
| `CONNECTION_LOST` | ERROR | WebSocket 断连 | 超过 5 次重连失败 |
| `RECONCILIATION_MISMATCH` | ERROR | 对账差异 | 仓位数量不一致 |
| `CAPITAL_PROTECTION_TRIGGERED` | WARNING | 资金保护触发 | 单笔损失超限被拦截 |

### 19.2 告警消息格式

```python
# 飞书消息模板

def format_order_filled_message(order: Order, pnl: Decimal) -> Dict:
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "✅ 订单成交通知"
                },
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"""
**策略**: {order.strategy_name}
**币种**: {order.symbol}
**方向**: {order.direction.value}
**类型**: {order.order_role.value}
**成交价**: {order.average_exec_price}
**数量**: {order.filled_qty}
**盈亏**: {pnl:+.2f} USDT
**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
                    }
                }
            ]
        }
    }
```

### 19.3 飞书配置

```yaml
# config/core.yaml

notification:
  feishu:
    enabled: true
    webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"

    # 告警级别过滤
    alert_levels:
      - INFO
      - WARNING
      - ERROR

    # 静默时段（可选）
    silent_hours:
      start: "02:00"
      end: "08:00"
```

---

## 20. 多区域部署支持（v1.3 新增）

### 20.1 区域配置

```yaml
# config/region.yaml

region:
  current: "tokyo"  # 当前区域：东京
  fallback: "hongkong"  # 备用区域：香港

  # 东京配置
  tokyo:
    aws_region: "ap-northeast-1"
    endpoint: "api.binance.com"

  # 香港配置
  hongkong:
    aws_region: "ap-east-1"
    endpoint: "api.binance.com"
```

### 20.2 切换脚本

```bash
#!/bin/bash
# switch_region.sh

REGION=$1

if [ "$REGION" == "tokyo" ]; then
    export AWS_REGION="ap-northeast-1"
    export EXCHANGE_ENDPOINT="api.binance.com"
elif [ "$REGION" == "hongkong" ]; then
    export AWS_REGION="ap-east-1"
    export EXCHANGE_ENDPOINT="api.binance.com"
else
    echo "Unknown region: $REGION"
    exit 1
fi

echo "Switched to region: $REGION"

# 重启服务
docker-compose restart
```

---

## 21. 测试用例清单更新（v1.3）

### 21.1 新增单元测试

| ID | 测试场景 | 预期结果 |
|----|----------|----------|
| UT-022 | 单笔损失超限检查 | 下单被拒，发送告警 |
| UT-023 | 每日亏损超限检查 | 下单被拒，发送告警 |
| UT-024 | 仓位占比超限检查 | 下单被拒 |
| UT-025 | DCA 第 1 批执行 | 市价单成交，状态更新 |
| UT-026 | DCA 第 2 批触发 | 跌幅 2% 时限价单挂出 |
| UT-027 | DCA 成本计算 | 平均成本正确 |
| UT-028 | 飞书消息格式化 | 消息格式正确 |

### 21.2 新增集成测试

| ID | 测试场景 | 预期结果 |
|----|----------|----------|
| IT-009 | 完整 DCA 流程 | 3 批次入场→止盈平仓 |
| IT-010 | 资金保护触发 | 超限订单被拦截 |
| IT-011 | 飞书告警推送 | 告警成功发送 |

---

## 22. 交付物清单更新（v1.3）

| 类型 | 文件 | 说明 |
|------|------|------|
| **核心实现** | `src/application/capital_protection.py` | 资金保护管理器 |
| | `src/domain/dca_strategy.py` | DCA 策略 |
| | `src/domain/dca_state.py` | DCA 状态追踪 |
| | `src/infrastructure/notifier_feishu.py` | 飞书通知 |
| **配置** | `config/capital_protection.yaml` | 资金保护配置 |
| | `config/strategies/dca_martingale.yaml` | DCA 策略配置 |
| **测试** | `tests/unit/test_capital_protection.py` | 资金保护测试 |
| | `tests/unit/test_dca_strategy.py` | DCA 测试 |
| | `tests/integration/test_feishu_notification.py` | 飞书通知测试 |
| **部署** | `scripts/switch_region.sh` | 区域切换脚本 |

---

## 23. 下一步行动（v1.3）

### Phase 5 开发任务清单

| 任务 | 预计工时 | 优先级 |
|------|----------|--------|
| 1. ExchangeGateway 订单接口 | 4h | P0 |
| 2. WebSocket 订单推送 | 4h | P0 |
| 3. 并发保护机制 | 4h | P0 |
| 4. 启动对账服务 | 4h | P0 |
| 5. 资金保护管理器 | 3h | P0 |
| 6. DCA 分批建仓 | 6h | P0 |
| 7. 飞书告警集成 | 2h | P1 |
| 8. 区域切换支持 | 2h | P2 |
| 9. 单元测试 | 6h | P0 |
| 10. 集成测试 | 8h | P0 |

**预计总工时**: ~39 小时（约 5 个工作日）

---

*契约表 v1.3 - 待开发*
*2026-03-30*
