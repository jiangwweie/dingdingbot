# 回测数据本地化方案设计

**文档版本**: v1.0  
**创建日期**: 2026-04-02  
**作者**: AI Builder  
**状态**: 待评审  

---

## 一、背景与目标

### 1.1 当前问题

现有回测程序通过 `ExchangeGateway.fetch_historical_ohlcv()` 实时请求币安 API：

```
Backtester → ExchangeGateway → CCXT REST API → 币安
```

**痛点**:
| 问题 | 影响 |
|------|------|
| API 频率限制 | 连续回测受限 |
| 网络延迟 | 每次回测需等待 |
| 数据久远度 | 无法回测太久远历史 |
| 重复请求 | 相同数据反复下载 |

### 1.2 已完成准备

- ✅ 本地 SQLite 数据库：`data/backtests/market_data.db` (56MB)
- ✅ BTC 历史数据：285,877 条 (2020-2026，覆盖 15m/1h/4h/1d)
- ✅ KlineORM 模型：`src/infrastructure/v3_orm.py`
- ✅ 索引优化：`(symbol, timeframe, timestamp)` 复合索引

### 1.3 设计目标

1. **性能提升**: 回测数据读取速度提升 10-50 倍
2. **透明切换**: 用户无感知，自动使用本地数据
3. **自动补充**: 本地缺失时自动请求交易所并缓存
4. **MTF 支持**: 多时间周期数据对齐

---

## 二、架构设计

### 2.1 推荐方案：自动降级模式

```
┌─────────────────────────────────────────────────────────────┐
│              数据流：本地优先 + 自动补充                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Backtester.run_backtest()                                   │
│         │                                                    │
│         ▼                                                    │
│  HistoricalDataRepository.get_klines()                       │
│         │                                                    │
│         ├──── 有数据 ─────► 返回本地 SQLite                 │
│         │                    • 一次性查询                    │
│         │                    • 数据完整性检查                │
│         │                                                    │
│         └──── 无数据 ─────► ExchangeGateway.fetch()         │
│                              • 请求交易所                    │
│                              • 保存到本地                    │
│                              • 返回结果                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

| 组件 | 职责 | 位置 |
|------|------|------|
| `HistoricalDataRepository` | 数据仓库：统一数据源访问 | 新建 |
| `Backtester` | 回测引擎：调用数据仓库 | 修改 |
| `ExchangeGateway` | 交易所网关：补充缺失数据 | 保持 |

### 2.3 数据流时序图

```
用户请求回测
     │
     ▼
Backtester.run_backtest()
     │
     ▼
HistoricalDataRepository.get_klines(
    symbol="BTC/USDT:USDT",
    timeframe="15m",
    start_time=...,
    end_time=...
)
     │
     ├─┬─ 查询本地 DB ─────────────────────────┐
     │ │                                       │
     │ ▼                                       │
     │ SELECT * FROM klines                    │
     │ WHERE symbol=? AND timeframe=?          │
     │ AND timestamp BETWEEN ? AND ?           │
     │                                         │
     │ ▼                                       │
     │ 有数据？───是───► 返回 List[KlineData] ──┤
     │ │                                       │
     │ 否                                      │
     │ │                                       │
     │ ▼                                       │
     ├─► ExchangeGateway.fetch() ──────────────┤
     │     │                                   │
     │     ▼                                   │
     │     CCXT REST API                       │
     │     │                                   │
     │     ▼                                   │
     │     保存到本地 (INSERT OR IGNORE)       │
     │     │                                   │
     │     ▼                                   │
     └────►返回 List[KlineData]────────────────┘
          │
          ▼
     回测引擎继续执行
```

---

## 三、接口设计

### 3.1 HistoricalDataRepository

```python
# src/infrastructure/data_repository.py

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import select
from src.infrastructure.v3_orm import KlineORM
from src.domain.models import KlineData


class HistoricalDataRepository:
    """
    历史数据仓库 - 统一数据源访问
    
    设计原则:
    1. 本地优先 - 优先从 SQLite 读取
    2. 自动补充 - 缺失时自动请求交易所
    3. 幂等写入 - INSERT OR IGNORE 防止重复
    """
    
    def __init__(
        self,
        db_path: str = "data/backtests/market_data.db",
        exchange_gateway: Optional[ExchangeGateway] = None,
    ):
        self._db_path = db_path
        self._gateway = exchange_gateway
        self._engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            echo=False,
        )
    
    async def get_klines(
        self,
        symbol: str,
        timeframe: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
    ) -> List[KlineData]:
        """
        获取 K 线数据（本地优先）
        
        Args:
            symbol: 交易对 (CCXT 格式)
            timeframe: 时间周期
            start_time: 开始时间戳 (毫秒)，可选
            end_time: 结束时间戳 (毫秒)，可选
            limit: 默认获取数量 (当未指定时间范围时)
        
        Returns:
            List[KlineData]
        """
        async with AsyncSession(self._engine) as session:
            # 构建查询
            stmt = select(KlineORM).where(
                KlineORM.symbol == symbol,
                KlineORM.timeframe == timeframe,
            )
            
            # 时间范围过滤
            if start_time:
                stmt = stmt.where(KlineORM.timestamp >= start_time)
            if end_time:
                stmt = stmt.where(KlineORM.timestamp <= end_time)
            
            # 排序 + 限制
            stmt = stmt.order_by(KlineORM.timestamp.asc()).limit(limit)
            
            result = await session.execute(stmt)
            rows = result.scalars().all()
            
            # 本地有数据 → 直接返回
            if rows:
                logger.info(f"从本地加载 {len(rows)} 条 {symbol} {timeframe} 数据")
                return [self._to_kline_data(row) for row in rows]
            
            # 本地无数据 → 请求交易所
            if self._gateway is None:
                logger.warning(f"本地无数据且未配置交易所网关：{symbol} {timeframe}")
                return []
            
            logger.info(f"本地无数据，从交易所获取：{symbol} {timeframe}")
            exchange_klines = await self._gateway.fetch_historical_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                limit=limit,
            )
            
            # 保存到本地
            await self._save_klines(exchange_klines)
            
            return exchange_klines
    
    async def get_klines_aligned(
        self,
        symbol: str,
        main_tf: str,
        higher_tf: str,
        start_time: int,
        end_time: int,
    ) -> Tuple[List[KlineData], Dict[int, KlineData]]:
        """
        获取对齐的多周期数据 (MTF 专用)
        
        Args:
            symbol: 交易对
            main_tf: 主周期 (如 "15m")
            higher_tf: 高周期 (如 "1h")
            start_time: 开始时间戳
            end_time: 结束时间戳
        
        Returns:
            (主周期 K 线列表，{时间戳：高周期 K 线})
        """
        # 并行获取两个周期数据
        main_klines, higher_klines = await asyncio.gather(
            self.get_klines(symbol, main_tf, start_time, end_time),
            self.get_klines(symbol, higher_tf, start_time, end_time),
        )
        
        # 构建高周期映射 {timestamp: KlineData}
        higher_map = {k.timestamp: k for k in higher_klines}
        
        return main_klines, higher_map
    
    async def _save_klines(self, klines: List[KlineData]) -> None:
        """保存 K 线到本地 (幂等)"""
        async with AsyncSession(self._engine) as session:
            records = [
                {
                    "symbol": k.symbol,
                    "timeframe": k.timeframe,
                    "timestamp": k.timestamp,
                    "open": k.open,
                    "high": k.high,
                    "low": k.low,
                    "close": k.close,
                    "volume": k.volume,
                    "is_closed": k.is_closed,
                }
                for k in klines
            ]
            
            await session.execute(
                insert(KlineORM).prefix_with("OR IGNORE").values(records)
            )
            await session.commit()
    
    def _to_kline_data(self, orm: KlineORM) -> KlineData:
        """ORM → Domain 模型转换"""
        return KlineData(
            symbol=orm.symbol,
            timeframe=orm.timeframe,
            timestamp=orm.timestamp,
            open=orm.open,
            high=orm.high,
            low=orm.low,
            close=orm.close,
            volume=orm.volume,
            is_closed=orm.is_closed,
        )
```

### 3.2 Backtester 修改点

```python
# src/application/backtester.py

class Backtester:
    def __init__(
        self,
        data_repository: HistoricalDataRepository,  # 新增
        # exchange_gateway: ExchangeGateway,  # 保留用于回测执行
    ):
        self._repository = data_repository
    
    async def _fetch_klines(self, request: BacktestRequest) -> List[KlineData]:
        """修改为使用数据仓库"""
        return await self._repository.get_klines(
            symbol=request.symbol,
            timeframe=request.timeframe,
            start_time=request.start_time,
            end_time=request.end_time,
            limit=request.limit,
        )
```

---

## 四、数据完整性保障

### 4.1 缺口检测

```python
async def validate_data_integrity(
    self,
    symbol: str,
    timeframe: str,
    start_time: int,
    end_time: int,
) -> DataQualityReport:
    """
    验证数据完整性
    
    Returns:
        DataQualityReport(
            expected_bars=2000,
            actual_bars=1998,
            gaps=[(gap1_start, gap1_end), ...],
            completeness=0.999,
        )
    """
    tf_minutes = self._parse_timeframe(timeframe)
    expected_ms = tf_minutes * 60 * 1000
    
    klines = await self.get_klines(symbol, timeframe, start_time, end_time)
    
    gaps = []
    for i in range(1, len(klines)):
        diff = klines[i].timestamp - klines[i-1].timestamp
        if diff > expected_ms * 1.5:  # 允许 50% 容差
            gaps.append((klines[i-1].timestamp, klines[i].timestamp))
    
    return DataQualityReport(
        expected_bars=int((end_time - start_time) / expected_ms),
        actual_bars=len(klines),
        gaps=gaps,
        completeness=len(klines) / max(1, int((end_time - start_time) / expected_ms)),
    )
```

### 4.2 处理策略

| 完整性 | 动作 |
|--------|------|
| ≥ 99% | ✅ 继续回测，记录警告 |
| 90-99% | ⚠️ 继续回测，明确告知用户 |
| < 90% | ❌ 拒绝回测，建议补充数据 |

---

## 五、实施计划

### Phase 7-1: 数据持久化层

| 任务 | 工时 | 交付物 |
|------|------|--------|
| 创建 `HistoricalDataRepository` | 2h | `src/infrastructure/data_repository.py` |
| 修改 `Backtester._fetch_klines()` | 1h | 使用新数据仓库 |
| 单元测试 | 2h | `tests/unit/test_data_repository.py` |

### Phase 7-2: 数据补充机制

| 任务 | 工时 | 交付物 |
|------|------|--------|
| 集成 `ExchangeGateway` | 2h | 自动补充逻辑 |
| 数据完整性验证 | 2h | `validate_data_integrity()` |
| 集成测试 | 2h | `tests/integration/test_backtest_data.py` |

### Phase 7-3: 性能基准测试

| 任务 | 工时 | 交付物 |
|------|------|--------|
| 本地 vs 交易所对比 | 1h | 性能报告 |
| MTF 数据对齐验证 | 2h | 测试用例 |

---

## 六、预期效果

### 6.1 性能提升

| 场景 | 当前 | 预期 | 提升 |
|------|------|------|------|
| 单次回测 (15m, 1 个月) | ~5s (网络) | ~0.1s (本地) | 50x |
| 参数扫描 (100 次) | ~500s | ~10s | 50x |
| Optuna 调参 (100 trial) | ~2 小时 | ~2 分钟 | 60x |

### 6.2 用户体验

- ✅ 无需手动管理数据
- ✅ 首次回测自动缓存
- ✅ 后续回测即时响应
- ✅ 支持离线回测

---

## 七、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 数据库锁竞争 | 低 | 中 | WAL 模式 + 单进程写入 |
| 数据断档 | 中 | 高 | 缺口检测 + 自动补充 |
| 内存溢出 | 低 | 中 | 分批加载 + 限制查询范围 |
| 数据不一致 | 低 | 高 | 唯一约束 + 幂等写入 |

---

## 八、验收标准

- [ ] `HistoricalDataRepository` 单元测试覆盖率 ≥ 90%
- [ ] 本地数据读取速度 < 100ms (1000 条 K 线)
- [ ] 自动补充逻辑正确工作
- [ ] MTF 数据对齐验证通过
- [ ] 性能基准测试报告完成

---

*文档创建时间：2026-04-02*
