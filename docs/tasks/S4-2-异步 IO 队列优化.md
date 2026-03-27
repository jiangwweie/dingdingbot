# S4-2: 异步 I/O 队列优化

**任务负责人**: Claude (窗口 2)
**预估工时**: 4-6 小时
**优先级**: 中
**依赖**: 无（但 S4-3 依赖此任务完成）

---

## 目标

优化 `signal_pipeline.py` 的异步 I/O 队列，提升高并发场景下的稳定性和性能：
1. 队列参数配置化
2. 添加背压监控和告警
3. 实现异常恢复策略
4. 编写集成测试验证

---

## 交付物

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/application/signal_pipeline.py` | 修改 | 队列参数配置化、背压监控 |
| `src/application/config_manager.py` | 修改 | 新增队列配置项 |
| `tests/integration/test_async_queue.py` | 新建 | 集成测试 |

---

## 实现步骤

### 步骤 1: 队列参数配置化

**现状分析**:
当前 `signal_pipeline.py` 中的队列参数是硬编码的：
```python
async def _flush_attempts_worker(self, batch_size: int = 10, flush_interval: float = 5.0)
```

**目标**:
从配置中读取这些参数，支持动态调整。

**实现**:

1. 在 `config/core.yaml` 中添加配置：
```yaml
signal_pipeline:
  cooldown_seconds: 14400
  queue:
    batch_size: 10          # 批量落盘大小
    flush_interval: 5.0     # 最大等待时间 (秒)
    max_queue_size: 1000    # 队列最大容量
```

2. 在 `src/application/config_manager.py` 中新增模型：
```python
class SignalQueueConfig(BaseModel):
    batch_size: int = Field(default=10, ge=1, description="批量落盘大小")
    flush_interval: float = Field(default=5.0, ge=0.1, description="最大等待时间 (秒)")
    max_queue_size: int = Field(default=1000, ge=100, description="队列最大容量")

class SignalPipelineConfig(BaseModel):
    cooldown_seconds: int = Field(default=14400, ge=60, description="Signal deduplication cooldown in seconds")
    queue: SignalQueueConfig = Field(default_factory=SignalQueueConfig)
```

3. 在 `SignalPipeline.__init__` 中读取配置：
```python
self._queue_batch_size = config_manager.core_config.signal_pipeline.queue.batch_size
self._queue_flush_interval = config_manager.core_config.signal_pipeline.queue.flush_interval
self._queue_max_size = config_manager.core_config.signal_pipeline.queue.max_queue_size
```

4. 修改 `_flush_attempts_worker` 调用：
```python
self._flush_task = asyncio.create_task(
    self._flush_attempts_worker(
        batch_size=self._queue_batch_size,
        flush_interval=self._queue_flush_interval,
    )
)
```

**验收标准**:
- [ ] 配置可从 `core.yaml` 读取
- [ ] 参数正确传递到队列 worker

---

### 步骤 2: 添加背压监控

**目标**:
当队列堆积时发出告警，便于运维发现性能瓶颈。

**实现**:

在 `_flush_attempts_worker` 中添加监控：

```python
async def _flush_attempts_worker(self, batch_size: int = 10, flush_interval: float = 5.0) -> None:
    buffer: List[tuple] = []
    last_flush = time.time()
    consecutive_drops = 0  # Track consecutive drop events

    while True:
        try:
            # Check queue size for backpressure monitoring
            queue_size = self._attempts_queue.qsize()

            # Alert if queue is approaching max capacity
            if queue_size > self._queue_max_size * 0.8:
                logger.warning(
                    f"BACKPRESSURE ALERT: Queue size ({queue_size}) approaching "
                    f"max capacity ({self._queue_max_size})"
                )

            # Wait for item or timeout
            try:
                item = await asyncio.wait_for(self._attempts_queue.get(), timeout=1.0)
                buffer.append(item)
            except asyncio.TimeoutError:
                pass

            # Flush if batch is full or interval exceeded
            now = time.time()
            if len(buffer) >= batch_size or (buffer and now - last_flush >= flush_interval):
                await self._flush_buffer(buffer)
                buffer = []
                last_flush = now

        except asyncio.CancelledError:
            if buffer:
                await self._flush_buffer(buffer)
            raise
        except Exception as e:
            logger.error(f"Flush worker error: {e}")
            consecutive_drops += 1

            # Alert on consecutive errors
            if consecutive_drops >= 3:
                logger.error(
                    f"CRITICAL: {consecutive_drops} consecutive flush worker errors, "
                    f"potential database connectivity issue"
                )
            buffer = []
```

**验收标准**:
- [ ] 队列大小超过 80% 时输出警告日志
- [ ] 连续错误 3 次时输出严重错误日志

---

### 步骤 3: 异常恢复策略

**目标**:
当队列 worker 异常退出时自动重启。

**实现**:

在 `SignalPipeline` 中添加健康检查和恢复机制：

```python
async def _start_flush_worker_with_recovery(self) -> None:
    """Start flush worker with automatic recovery on failure."""
    restart_count = 0
    max_restarts = 5
    restart_delay = 1.0  # Initial delay, will increase exponentially

    while restart_count < max_restarts:
        try:
            self._ensure_async_primitives()
            if self._attempts_queue is None or self._runner_lock is None:
                logger.debug("Cannot start flush worker: no event loop")
                return

            self._flush_task = asyncio.create_task(
                self._flush_attempts_worker(
                    batch_size=self._queue_batch_size,
                    flush_interval=self._queue_flush_interval,
                )
            )
            logger.info(f"Flush worker started (restart #{restart_count})")

            # Wait for task to complete (should not happen unless error)
            await self._flush_task

        except Exception as e:
            restart_count += 1
            logger.error(
                f"Flush worker crashed (restart {restart_count}/{max_restarts}): {e}"
            )

            if restart_count >= max_restarts:
                logger.error(
                    "CRITICAL: Flush worker exceeded max restarts, "
                    "data persistence may be compromised"
                )
                raise

            # Exponential backoff before restart
            delay = restart_delay * (2 ** (restart_count - 1))
            logger.info(f"Waiting {delay}s before restart...")
            await asyncio.sleep(delay)
```

**验收标准**:
- [ ] Worker 异常退出后自动重启
- [ ] 重启延迟指数退避
- [ ] 超过最大重启次数时抛出严重错误

---

### 步骤 4: 集成测试

**文件**: `tests/integration/test_async_queue.py`

```python
import pytest
import asyncio
import time
from decimal import Decimal
from src.application.signal_pipeline import SignalPipeline
from src.application.config_manager import ConfigManager
from src.domain.risk_calculator import RiskConfig
from src.domain.models import KlineData, AccountSnapshot
from src.infrastructure.signal_repository import SignalRepository

class TestAsyncQueueBackpressure:
    """Test queue backpressure monitoring."""

    @pytest.fixture
    async def pipeline(self):
        """Create a test pipeline."""
        config_manager = ConfigManager()
        config_manager.load_core_config()
        config_manager.load_user_config()
        config_manager.merge_symbols()

        risk_config = RiskConfig(
            max_loss_percent=Decimal("0.01"),
            max_leverage=10,
        )

        repository = SignalRepository(db_path=":memory:")
        await repository.initialize()

        pipeline = SignalPipeline(
            config_manager=config_manager,
            risk_config=risk_config,
            signal_repository=repository,
        )

        yield pipeline

        await repository.close()

    @pytest.mark.asyncio
    async def test_queue_backpressure_alert(self, pipeline, caplog):
        """Test that backpressure alert is triggered when queue is near capacity."""
        # Fill queue to near capacity
        for _ in range(900):  # 90% of default 1000
            await pipeline._attempts_queue.put(("dummy", "BTC", "15m"))

        # Trigger worker
        await pipeline._flush_attempts_worker(batch_size=10, flush_interval=0.1)

        # Check log for backpressure alert
        assert "BACKPRESSURE ALERT" in caplog.text

class TestAsyncQueueRecovery:
    """Test queue worker recovery."""

    @pytest.mark.asyncio
    async def test_worker_recovers_from_error(self):
        """Test that worker restarts after error."""
        # Test implementation
        pass

class TestQueueConfig:
    """Test queue configuration."""

    @pytest.mark.asyncio
    async def test_queue_params_from_config(self):
        """Test that queue parameters are loaded from config."""
        # Test implementation
        pass
```

**验收标准**:
- [ ] 背压测试通过
- [ ] 恢复测试通过
- [ ] 配置测试通过

---

## 验收标准

- [ ] 队列参数可从配置文件读取
- [ ] 背压告警日志正确输出
- [ ] Worker 异常后自动重启
- [ ] 集成测试通过率 100%
- [ ] Git 提交完成

---

## 依赖关系

**S4-3 依赖此任务完成**，因为：
- S4-3 需要修改 `signal_pipeline.py` 集成 EMA 缓存
- 如果 S4-2 未提交，S4-3 会产生代码冲突

**完成后请立即提交**:
```bash
git add -A
git commit -m "feat(S4-2): 异步 I/O 队列优化"
```

然后通知 Claude 可以开始 S4-3。

---

*任务文档创建时间：2026-03-27*
