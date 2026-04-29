# 日志系统架构规范

> **创建日期**: 2026-03-29
> **版本**: 1.0
> **状态**: 设计中

---

## 一、日志系统架构

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         盯盘狗日志系统架构                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      Logger 核心层                                │   │
│  │  ┌─────────────────────────────────────────────────────────────┐ │   │
│  │  │  setup_logger(name, level)                                  │ │   │
│  │  │  ├── 创建命名 Logger                                         │ │   │
│  │  │  ├── 注册 StreamHandler (控制台输出)                         │ │   │
│  │  │  └── 注册 FileHandler (文件持久化)                           │ │   │
│  │  └─────────────────────────────────────────────────────────────┘ │   │
│  │                              │                                     │   │
│  │                              ▼                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐ │   │
│  │  │                 SecretMaskingFormatter                      │ │   │
│  │  │  - 自动脱敏 API Key、Webhook URL 等敏感数据                   │ │   │
│  │  │  - 统一日志格式：[timestamp] [level] [module] message       │ │   │
│  │  └─────────────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      Handler 输出层                               │   │
│  │  ┌─────────────────────┐         ┌─────────────────────────────┐ │   │
│  │  │ StreamHandler       │         │ TimedRotatingFileHandler    │ │   │
│  │  │ - stdout 输出        │         │ - 按天轮转日志文件           │ │   │
│  │  │ - 实时调试           │         │ - 自动压缩归档               │ │   │
│  │  │ - 级别：INFO         │         │ - 级别：DEBUG               │ │   │
│  │  └─────────────────────┘         └─────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      文件存储层                                   │   │
│  │                                                                  │   │
│  │  logs/                                                           │   │
│  │  ├── dingdingbot.log          # 当前日志（软链接到最新）         │   │
│  │  ├── dingdingbot-2026-03-29.log  # 按天命名                      │   │
│  │  ├── dingpingbot-2026-03-28.log.gz  # 压缩归档                   │   │
│  │  └── ...                                                         │   │
│  │                                                                  │   │
│  │  轮转策略：                                                       │   │
│  │  - 每天 00:00 自动轮转                                             │   │
│  │  - 保留最近 30 天                                                   │   │
│  │  - 7 天前的日志自动压缩为 .gz                                     │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 日志文件命名规范

| 文件类型 | 命名格式 | 示例 | 说明 |
|----------|----------|------|------|
| 当前日志 | `dingdingbot.log` | `dingdingbot.log` | 始终指向最新日志 |
| 历史日志 | `dingdingbot-YYYY-MM-DD.log` | `dingdingbot-2026-03-29.log` | 按天命名 |
| 归档日志 | `dingdingbot-YYYY-MM-DD.log.gz` | `dingdingbot-2026-03-22.log.gz` | 7 天前压缩 |

### 1.3 日志目录结构

```
project-root/
├── logs/                           # 日志根目录（自动创建）
│   ├── dingdingbot.log             # 当前日志
│   ├── dingdingbot-2026-03-29.log  # 今天
│   ├── dingdingbot-2026-03-28.log  # 昨天
│   ├── ...
│   ├── dingdingbot-2026-03-22.log.gz  # 7 天前，已压缩
│   └── ...
└── config/
    └── logging.yaml                # 日志配置（可选）
```

---

## 二、日志级别使用规范

### 2.1 级别定义

| 级别 | 名称 | 使用场景 | 示例 |
|------|------|----------|------|
| `DEBUG` | 调试 | 详细调试信息，生产环境通常关闭 | "处理 K 线数据：BTC/USDT:USDT:15m" |
| `INFO` | 信息 | 正常业务流程记录 | "信号已发送：BTC/USDT:USDT:LONG" |
| `WARNING` | 警告 | 异常但可继续运行 | "WebSocket 连接断开，正在重连" |
| `ERROR` | 错误 | 操作失败但系统可恢复 | "发送通知失败：网络超时" |
| `CRITICAL` | 严重 | 系统无法继续运行 | "交易所 API 认证失败，系统退出" |

### 2.2 各模块日志级别指南

#### 2.2.1 系统启动/关闭

```python
logger.info("========== 系统启动 ==========")
logger.info("加载核心配置...")
logger.info("初始化交易所网关...")
logger.info("启动 WebSocket 数据流...")
logger.info("========== 系统就绪 ==========")

# 关闭时
logger.info("========== 系统关闭 ==========")
logger.info("关闭交易所连接...")
logger.info("刷新待发送信号队列...")
logger.info("========== 系统已关闭 ==========")
```

#### 2.2.2 信号处理管道

```python
# INFO 级别 - 正常流程
logger.info(f"[Signal] 检测到形态：{symbol}:{timeframe} {direction} Pinbar")
logger.info(f"[Signal] 信号已持久化：id={signal_id}")
logger.info(f"[Signal] 通知已发送：{channel}")

# WARNING 级别 - 过滤/跳过
logger.warning(f"[Filter] 信号被过滤：{symbol}:{timeframe} - {filter_name}: {reason}")
logger.warning(f"[Cooldown] 信号在冷却期：{symbol}:{timeframe}")

# ERROR 级别 - 失败
logger.error(f"[Persist] 信号保存失败：{symbol}:{timeframe} - {error}")
logger.error(f"[Notify] 通知发送失败：{channel} - {error}")
```

#### 2.2.3 过滤器执行

```python
# 每个过滤器通过/拒绝都要记录
logger.debug(f"[Filter] {filter_type} 检查通过：{symbol}:{timeframe}")
logger.warning(f"[Filter] {filter_type} 拒绝：{symbol}:{timeframe} - {reason}")
```

#### 2.2.4 WebSocket/交易所

```python
logger.info(f"[WS] 连接到 {exchange}...")
logger.info(f"[WS] 已订阅：{symbols}")
logger.warning(f"[WS] 连接断开，{seconds}s 后重连...")
logger.error(f"[WS] 重连失败：{error}")
```

#### 2.2.5 配置管理

```python
logger.info("[Config] 配置热重载中...")
logger.info(f"[Config] 配置已更新：{changes}")
logger.error(f"[Config] 配置加载失败：{error}")
```

---

## 三、信号过滤日志详细设计

### 3.1 过滤事件结构

当信号被过滤器拒绝时，记录以下信息：

```json
{
  "event_type": "signal_filtered",
  "timestamp": "2026-03-29T10:30:00",
  "signal": {
    "symbol": "BTC/USDT:USDT",
    "timeframe": "15m",
    "pattern": "pinbar",
    "direction": "long",
    "entry_price": "67500.00"
  },
  "filter": {
    "type": "atr",
    "name": "ATR 波幅过滤",
    "reason": "K 线波幅过小",
    "details": {
      "candle_range": "0.0012",
      "atr_value": "0.015",
      "ratio": "0.08",
      "threshold": "0.2"
    }
  },
  "decision": "rejected"
}
```

### 3.2 数据库表设计

```sql
-- 信号过滤日志表
CREATE TABLE IF NOT EXISTS signal_filter_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,  -- 关联 signals 表，可为空（被过滤的信号不会入库）
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    pattern_type TEXT NOT NULL,
    direction TEXT NOT NULL,
    filter_type TEXT NOT NULL,
    filter_name TEXT NOT NULL,
    reject_reason TEXT NOT NULL,
    filter_details JSON,  -- 过滤器内部状态 JSON
    candle_range_pct REAL,
    atr_value REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_filter_logs_symbol_timeframe ON signal_filter_logs(symbol, timeframe);
CREATE INDEX idx_filter_logs_created_at ON signal_filter_logs(created_at);
CREATE INDEX idx_filter_logs_filter_type ON signal_filter_logs(filter_type);
```

### 3.3 代码实现位置

| 文件 | 方法 | 修改内容 |
|------|------|----------|
| `src/domain/filter_factory.py` | `AtrFilterDynamic.check()` | 添加拒绝原因详情 |
| `src/domain/filter_factory.py` | `EmaTrendFilter.check()` | 添加拒绝原因详情 |
| `src/domain/filter_factory.py` | `MtfFilter.check()` | 添加拒绝原因详情 |
| `src/application/signal_pipeline.py` | `process_kline()` | 记录过滤事件到数据库 |
| `src/infrastructure/signal_repository.py` | `add_filter_log()` | 新增方法 |

---

## 四、日志轮转与归档策略

### 4.1 轮转配置

```python
from logging.handlers import TimedRotatingFileHandler

# 按天轮转
handler = TimedRotatingFileHandler(
    filename='logs/dingdingbot.log',
    when='D',           # 按天
    interval=1,         # 每 1 天
    backupCount=30,     # 保留 30 个备份
    encoding='utf-8',
    delay=False
)
handler.suffix = "%Y-%m-%d.log"  # 文件名后缀
```

### 4.2 压缩归档策略

```python
import gzip
import os
from datetime import datetime, timedelta

def compress_old_logs(logs_dir: str, days_threshold: int = 7):
    """
    压缩 N 天前的日志文件

    Args:
        logs_dir: 日志目录路径
        days_threshold: 多少天前的日志需要压缩
    """
    cutoff = datetime.now() - timedelta(days=days_threshold)

    for filename in os.listdir(logs_dir):
        if not filename.endswith('.log'):
            continue
        if filename.endswith('.gz'):
            continue

        file_path = os.path.join(logs_dir, filename)
        file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))

        if file_mtime < cutoff:
            # 压缩
            gz_path = f"{file_path}.gz"
            with open(file_path, 'rb') as f_in, gzip.open(gz_path, 'wb') as f_out:
                f_out.writelines(f_in)
            # 删除原文件
            os.remove(file_path)
            logger.info(f"已压缩旧日志：{filename} -> {filename}.gz")
```

### 4.3 清理过期日志

```python
def cleanup_old_logs(logs_dir: str, retention_days: int = 30):
    """
    删除超过保留期的日志

    Args:
        logs_dir: 日志目录路径
        retention_days: 保留天数
    """
    cutoff = datetime.now() - timedelta(days=retention_days)

    for filename in os.listdir(logs_dir):
        if not (filename.endswith('.log') or filename.endswith('.log.gz')):
            continue

        # 从文件名解析日期
        date_str = extract_date_from_filename(filename)
        if not date_str:
            continue

        file_date = datetime.strptime(date_str, "%Y-%m-%d")

        if file_date < cutoff:
            os.remove(os.path.join(logs_dir, filename))
            logger.info(f"已删除过期日志：{filename}")
```

---

## 五、实施计划

### Phase 1: 核心实现（P0）

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 添加 FileHandler 支持 | `src/infrastructure/logger.py` | P0 |
| 实现 TimedRotatingFileHandler | `src/infrastructure/logger.py` | P0 |
| 创建日志目录 | `src/main.py` | P0 |

### Phase 2: 过滤日志（P0）

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 创建 signal_filter_logs 表 | `src/infrastructure/signal_repository.py` | P0 |
| 实现过滤器详细原因返回 | `src/domain/filter_factory.py` | P0 |
| 记录过滤事件到数据库 | `src/application/signal_pipeline.py` | P0 |

### Phase 3: 完善关键路径日志（P1）

| 任务 | 文件 | 优先级 |
|------|------|--------|
| Repository 操作日志 | `src/infrastructure/signal_repository.py` | P1 |
| Risk Calculator 日志 | `src/domain/risk_calculator.py` | P1 |
| Performance Tracker 日志 | `src/application/performance_tracker.py` | P1 |

### Phase 4: 清理与压缩（P2）

| 任务 | 文件 | 优先级 |
|------|------|--------|
| 日志压缩工具 | `src/infrastructure/logger.py` | P2 |
| 过期日志清理 | `src/infrastructure/logger.py` | P2 |
| 启动时执行清理任务 | `src/main.py` | P2 |

---

## 六、验收标准

1. **日志持久化**: 系统运行日志完整写入 `logs/` 目录
2. **按天轮转**: 每天 00:00 自动创建新日志文件
3. **归档策略**: 7 天前日志自动压缩，30 天前自动删除
4. **过滤追踪**: 每个被过滤的信号都有详细原因记录
5. **敏感脱敏**: API Key、Webhook URL 自动脱敏
