"""
Crypto Signal Monitor - Main Entry Point

Orchestrates the complete startup flow:
1. Load configuration
2. Initialize exchange (REST + WebSocket)
3. Warm up historical data
4. Start WebSocket subscriptions
5. Start asset polling
6. Enter event loop

Zero Execution Policy: This system is READ-ONLY. No trading operations.
"""
import asyncio
import json
import os
import sys
import signal as sys_signal
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

if load_dotenv is not None:
    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env")
    load_dotenv(repo_root / ".env.local", override=True)

from src.application.config_manager import ConfigManager, load_all_configs
from src.application.runtime_config import RuntimeConfigProvider, RuntimeConfigResolver
from src.application.account_service import BinanceAccountService
from src.application.capital_protection import CapitalProtectionManager
from src.application.execution_orchestrator import ExecutionOrchestrator
from src.application.order_lifecycle_service import OrderLifecycleService
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.notifier import NotificationService, get_notification_service
from src.infrastructure.core_repository_factory import (
    create_execution_intent_repository,
    create_order_repository,
)
from src.infrastructure.runtime_profile_repository import RuntimeProfileRepository
from src.application.signal_pipeline import SignalPipeline
from src.domain.risk_calculator import RiskConfig
from src.domain.models import KlineData
from src.domain.exceptions import FatalStartupError, DependencyNotReadyError, ConnectionLostError
from src.infrastructure.logger import logger, setup_logger, register_secret
from src.infrastructure.database import close_db, validate_pg_core_configuration


# ============================================================
# Global State
# ============================================================
_shutdown_event: Optional[asyncio.Event] = None  # Created in run_application()
_exchange_gateway: Optional[ExchangeGateway] = None
_notification_service: Optional[NotificationService] = None
_config_entry_repo = None  # Initialized in Phase 9
_order_repo = None
_execution_intent_repo = None
_order_lifecycle_service: Optional[OrderLifecycleService] = None
_capital_protection: Optional[CapitalProtectionManager] = None
_execution_orchestrator: Optional[ExecutionOrchestrator] = None
_execution_recovery_repo = None  # PG 正式版
_runtime_config_provider: Optional[RuntimeConfigProvider] = None


class _CapitalProtectionNotifierAdapter:
    """把 NotificationService 适配为 CapitalProtectionManager 需要的告警接口。"""

    def __init__(self, notification_service: NotificationService):
        self._notification_service = notification_service

    async def send_alert(self, title: str, message: str) -> None:
        await self._notification_service.send_system_alert(title, message)


# ============================================================
# Signal Handlers
# ============================================================
def setup_signal_handlers(loop: asyncio.AbstractEventLoop):
    """Set up graceful shutdown signal handlers"""
    for sig in (sys_signal.SIGINT, sys_signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(graceful_shutdown())
            )
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass


async def graceful_shutdown():
    """
    Perform graceful shutdown.
    Close exchange connections and cleanup resources.
    """
    logger.info("Graceful shutdown initiated...")

    global _shutdown_event, _exchange_gateway, _order_lifecycle_service
    global _execution_intent_repo, _order_repo, _execution_recovery_repo
    global _runtime_config_provider
    _shutdown_event.set()

    if _exchange_gateway:
        await _exchange_gateway.close()
        _exchange_gateway = None

    if _order_lifecycle_service:
        await _order_lifecycle_service.stop()
        _order_lifecycle_service = None

    if _execution_intent_repo:
        await _execution_intent_repo.close()
        _execution_intent_repo = None

    if _order_repo:
        await _order_repo.close()
        _order_repo = None

    # PG 正式恢复表
    if _execution_recovery_repo:
        await _execution_recovery_repo.close()
        _execution_recovery_repo = None

    await close_db()
    _runtime_config_provider = None

    logger.info("Shutdown complete")


# ============================================================
# K-line Callback
# ============================================================
async def on_kline_received(kline: KlineData):
    """
    Callback when a new closed K-line is received.
    Passes the K-line to the signal pipeline for processing.

    Args:
        kline: Closed K-line data
    """
    logger.debug(f"K-line received: {kline.symbol} {kline.timeframe} @ {kline.timestamp}")

    # Get pipeline from global state
    pipeline = get_signal_pipeline()
    if pipeline:
        await pipeline.process_kline(kline)


# ============================================================
# Pipeline Factory
# ============================================================
_signal_pipeline: Optional[SignalPipeline] = None


def get_signal_pipeline() -> Optional[SignalPipeline]:
    """Get global SignalPipeline instance"""
    return _signal_pipeline


# ============================================================
# Main Application
# ============================================================
async def run_application():
    """
    Main application entry point.
    Orchestrates the complete startup and runtime flow.
    """
    global _exchange_gateway, _notification_service, _shutdown_event, _config_entry_repo
    global _order_repo, _execution_intent_repo, _order_lifecycle_service
    global _capital_protection, _execution_orchestrator
    global _runtime_config_provider

    # Create shutdown event in the current event loop
    _shutdown_event = asyncio.Event()

    logger.info("=" * 60)
    logger.info("Crypto Signal Monitor - Starting")
    logger.info("=" * 60)

    # Get current event loop for signal handlers
    loop = asyncio.get_event_loop()
    setup_signal_handlers(loop)

    try:
        # =============================================
        # Preflight: Validate PG core backend configuration
        # =============================================
        try:
            validate_pg_core_configuration()
        except ValueError as e:
            raise FatalStartupError(str(e), "F-003")

        # =============================================
        # Phase 1: Load Configuration
        # =============================================
        logger.info("Phase 1: Loading configuration...")
        config_manager = load_all_configs()
        await config_manager.initialize_from_db()
        logger.info("Configuration loaded successfully")

        # R7.1: Explicit marker - ConfigManager initialization complete
        logger.info("[启动顺序] Phase 1 完成：ConfigManager 已初始化")

        # =============================================
        # Phase 1.1: Resolve Runtime Config Snapshot
        # =============================================
        logger.info("Phase 1.1: Resolving runtime config snapshot...")
        runtime_profile_name = os.environ.get("RUNTIME_PROFILE", "sim1_eth_runtime")
        runtime_profile_repo = RuntimeProfileRepository()
        try:
            await runtime_profile_repo.initialize()
            runtime_resolver = RuntimeConfigResolver(runtime_profile_repo)
            resolved_runtime_config = await runtime_resolver.resolve(runtime_profile_name)
            _runtime_config_provider = RuntimeConfigProvider(resolved_runtime_config)
            logger.info(
                "Runtime config resolved: "
                f"profile={resolved_runtime_config.profile_name}, "
                f"version={resolved_runtime_config.version}, "
                f"hash={resolved_runtime_config.config_hash}"
            )
            logger.info(
                "Runtime config safe summary: "
                + json.dumps(
                    _runtime_config_provider.to_safe_summary(),
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            )
            logger.info(
                "Runtime config resolved in partial-cutover mode: market scope is "
                "runtime-driven; strategy/risk/execution still use existing paths"
            )
        except ValueError as e:
            raise FatalStartupError(f"Runtime config resolution failed: {e}", "F-003")
        finally:
            await runtime_profile_repo.close()

        # =============================================
        # Phase 1.5: Initialize Signal Database
        # =============================================
        logger.info("Phase 1.5: Initializing signal database...")
        from src.infrastructure.signal_repository import SignalRepository
        signal_repository = SignalRepository()
        await signal_repository.initialize()
        logger.info("Signal database initialized")

        # =============================================
        # Phase 2: Get Configuration Snapshots (Dependency Injection)
        # =============================================
        logger.info("Phase 2: Getting configuration snapshots...")
        # R7.1: Defensive check - ensure ConfigManager is ready
        config_manager.assert_initialized()
        core_config = config_manager.get_core_config()
        user_config = await config_manager.get_user_config()
        logger.info("Configuration snapshots ready for dependency injection")

        # =============================================
        # Phase 3: Initialize Notification Service
        # =============================================
        logger.info("Phase 3: Setting up notification channels...")
        _notification_service = get_notification_service()
        if _runtime_config_provider is not None:
            env = _runtime_config_provider.resolved_config.environment
            _notification_service.setup_channels(
                [
                    {
                        "type": "feishu",
                        "webhook_url": env.feishu_webhook_url.get_secret_value(),
                    }
                ]
            )
        else:
            _notification_service.setup_channels(
                [{"type": ch.type, "webhook_url": ch.webhook_url} for ch in user_config.notification.channels]
            )
        logger.info(f"Notification channels ready: {len(_notification_service._channels)}")

        # =============================================
        # Phase 4: Initialize Exchange Gateway
        # =============================================
        logger.info("Phase 4: Initializing exchange gateway...")
        if _runtime_config_provider is not None:
            env = _runtime_config_provider.resolved_config.environment
            _exchange_gateway = ExchangeGateway(
                exchange_name=env.exchange_name,
                api_key=env.exchange_api_key.get_secret_value(),
                api_secret=env.exchange_api_secret.get_secret_value(),
                testnet=env.exchange_testnet,
            )
        else:
            exchange_cfg = user_config.exchange
            _exchange_gateway = ExchangeGateway(
                exchange_name=exchange_cfg.name,
                api_key=exchange_cfg.api_key,
                api_secret=exchange_cfg.api_secret,
                testnet=exchange_cfg.testnet,
            )

        await _exchange_gateway.initialize()
        logger.info("Exchange gateway initialized")

        # =============================================
        # Phase 4.2: Initialize Core Execution Runtime
        # =============================================
        logger.info("Phase 4.2: Initializing core execution runtime...")
        _order_repo = create_order_repository()
        await _order_repo.initialize()
        if hasattr(_order_repo, "set_exchange_gateway"):
            _order_repo.set_exchange_gateway(_exchange_gateway)

        _execution_intent_repo = create_execution_intent_repository()
        if _execution_intent_repo is not None:
            await _execution_intent_repo.initialize()

        _order_lifecycle_service = OrderLifecycleService(repository=_order_repo)
        await _order_lifecycle_service.start()

        # PG 正式恢复表：初始化（仅当 PG 可用时）
        _execution_recovery_repo = None
        try:
            from src.infrastructure.database import get_pg_session_maker
            from src.infrastructure.pg_execution_recovery_repository import PgExecutionRecoveryRepository

            session_maker = get_pg_session_maker()
            if session_maker:
                _execution_recovery_repo = PgExecutionRecoveryRepository(session_maker=session_maker)
                await _execution_recovery_repo.initialize()
                logger.info("PG execution recovery repository initialized")
        except Exception as e:
            logger.warning(
                f"PG execution recovery repository 初始化失败（不影响主进程）: {e}",
                exc_info=True
            )
            # 继续启动（降级到无 PG 模式）
            _execution_recovery_repo = None

        account_service = BinanceAccountService(_exchange_gateway)
        capital_notifier = _CapitalProtectionNotifierAdapter(_notification_service)
        capital_protection_config = config_manager.build_capital_protection_config()
        if _runtime_config_provider is not None:
            runtime_risk = _runtime_config_provider.resolved_config.risk
            startup_snapshot = _exchange_gateway.get_account_snapshot()
            if startup_snapshot is None:
                startup_snapshot = await _exchange_gateway.fetch_account_balance()
            startup_equity = startup_snapshot.total_balance if startup_snapshot else None
            capital_protection_config = runtime_risk.to_capital_protection_config(
                account_equity=startup_equity,
                base=capital_protection_config,
            )
            logger.info(
                "CapitalProtection driven by runtime risk: "
                f"profile={_runtime_config_provider.resolved_config.profile_name}, "
                f"hash={_runtime_config_provider.config_hash}, "
                f"single_trade_max_loss_percent={capital_protection_config.single_trade['max_loss_percent']}, "
                f"daily_max_loss_percent={capital_protection_config.daily['max_loss_percent']}, "
                f"daily_max_loss_amount={capital_protection_config.daily.get('max_loss_amount')}, "
                f"max_leverage={capital_protection_config.account['max_leverage']}"
            )
        _capital_protection = CapitalProtectionManager(
            config=capital_protection_config,
            account_service=account_service,
            notifier=capital_notifier,
            gateway=_exchange_gateway,
        )

        # P0-6：为 ExecutionOrchestrator 创建告警适配函数
        async def _orchestrator_notifier_adapter(title: str, message: str) -> None:
            """复用现有 notification service 发送飞书告警"""
            await _notification_service.send_system_alert(title, message)

        _execution_orchestrator = ExecutionOrchestrator(
            capital_protection=_capital_protection,
            order_lifecycle=_order_lifecycle_service,
            gateway=_exchange_gateway,
            intent_repository=_execution_intent_repo,
            notifier=_orchestrator_notifier_adapter,  # P0-6: 注入告警回调
            execution_recovery_repository=_execution_recovery_repo,  # PG 正式版
        )
        _exchange_gateway.set_global_order_callback(_order_lifecycle_service.update_order_from_exchange)
        logger.info("Core execution runtime ready")

        # =============================================
        # Phase 4.3: Run Startup Reconciliation
        # =============================================
        logger.info("Phase 4.3: Running startup reconciliation...")
        try:
            from src.application.startup_reconciliation_service import StartupReconciliationService

            reconciliation_service = StartupReconciliationService(
                gateway=_exchange_gateway,
                repository=_order_repo,
                lifecycle=_order_lifecycle_service,
                orchestrator=_execution_orchestrator,
                execution_recovery_repository=_execution_recovery_repo,
            )

            reconciliation_summary = await reconciliation_service.run_startup_reconciliation()

            logger.info("=" * 70)
            logger.info("启动对账完成")
            logger.info(f"候选订单: {reconciliation_summary['total_candidates']} 个")
            logger.info(f"对账成功: {reconciliation_summary['success_count']} 个")
            logger.info(f"对账失败: {reconciliation_summary['failure_count']} 个")
            logger.info(f"清除待恢复标记: {reconciliation_summary['recovery_cleared_count']} 个")
            logger.info(f"PG recovery: 已解决: {reconciliation_summary['pg_recovery_resolved_count']} 个")
            logger.info(f"PG recovery: 重试中: {reconciliation_summary['pg_recovery_retrying_count']} 个")
            logger.info(f"PG recovery: 已失败: {reconciliation_summary['pg_recovery_failed_count']} 个")
            logger.info(f"执行耗时: {reconciliation_summary['duration_ms']} ms")
            logger.info("=" * 70)

        except Exception as e:
            logger.error(f"启动对账失败（不影响主进程启动）: {e}", exc_info=True)
            # 继续启动（可用性优先）

        # =============================================
        # Phase 4.4: Rebuild Circuit Breakers from PG Recovery Tasks
        # =============================================
        logger.info("Phase 4.4: Rebuilding circuit breakers from PG recovery tasks...")
        try:
            breaker_count = await _execution_orchestrator.rebuild_circuit_breakers_from_recovery_tasks()
            logger.info(f"Circuit breaker 重建完成: {breaker_count} 个 symbol 被熔断")
        except Exception as e:
            logger.error(f"Circuit breaker 重建失败（不影响主进程启动）: {e}", exc_info=True)
            # 继续启动（可用性优先）

        # =============================================
        # Phase 4.5: Check API Key Permissions
        # =============================================
        logger.info("Phase 4.5: Checking API key permissions...")
        await _exchange_gateway.check_api_key_permissions()
        permission_summary = _exchange_gateway.get_permission_check_summary()
        logger.info(
            "Phase 4.5 permission summary: verified=%s, status=%s, exchange=%s, testnet=%s",
            permission_summary["verified"],
            permission_summary["status"],
            permission_summary["exchange"],
            permission_summary["testnet"],
        )
        if permission_summary["reason"]:
            logger.warning(
                "Phase 4.5 permission check reason: %s",
                permission_summary["reason"],
            )

        # =============================================
        # Phase 5: Create Signal Pipeline (Dependency Injection)
        # =============================================
        logger.info("Phase 5: Creating signal pipeline...")
        # 配置重构后：SignalPipeline 需要 config_manager 作为第一个参数
        runtime_strategy_definitions = None
        runtime_allowed_directions = None
        runtime_mtf_ema_period = None
        runtime_execution_strategy = None
        runtime_risk_locked = False

        if _runtime_config_provider is not None:
            runtime_config = _runtime_config_provider.resolved_config
            runtime_risk = runtime_config.risk
            runtime_strategy = runtime_config.strategy
            runtime_execution = runtime_config.execution
            runtime_market = runtime_config.market
            risk_config = runtime_risk.to_risk_config()
            runtime_strategy_definitions = [
                runtime_strategy.to_strategy_definition(
                    primary_symbol=runtime_market.primary_symbol,
                    primary_timeframe=runtime_market.primary_timeframe,
                )
            ]
            runtime_allowed_directions = runtime_strategy.allowed_directions
            runtime_mtf_ema_period = runtime_strategy.get_mtf_ema_period()
            runtime_execution_strategy = runtime_execution.to_order_strategy(
                strategy_id=f"{runtime_config.profile_name}_execution"
            )
            runtime_risk_locked = True
            logger.info(
                "SignalPipeline risk config driven by runtime profile: "
                f"profile={runtime_config.profile_name}, "
                f"hash={_runtime_config_provider.config_hash}, "
                f"max_loss_percent={risk_config.max_loss_percent}, "
                f"max_leverage={risk_config.max_leverage}, "
                f"max_total_exposure={risk_config.max_total_exposure}, "
                f"daily_max_trades={risk_config.daily_max_trades}"
            )
            logger.info(
                "SignalPipeline strategy driven by runtime profile: "
                f"profile={runtime_config.profile_name}, "
                f"allowed_directions={[direction.value for direction in runtime_allowed_directions]}, "
                f"trigger={runtime_strategy.trigger.type}, "
                f"filters={[filter_config.type for filter_config in runtime_strategy.filters]}, "
                f"mtf_ema_period={runtime_mtf_ema_period}"
            )
            logger.info(
                "SignalPipeline execution strategy driven by runtime profile: "
                f"profile={runtime_config.profile_name}, "
                f"tp_levels={runtime_execution_strategy.tp_levels}, "
                f"tp_ratios={runtime_execution_strategy.tp_ratios}, "
                f"tp_targets={runtime_execution_strategy.tp_targets}, "
                f"initial_stop_loss_rr={runtime_execution_strategy.initial_stop_loss_rr}, "
                f"trailing_stop_enabled={runtime_execution_strategy.trailing_stop_enabled}, "
                f"oco_enabled={runtime_execution_strategy.oco_enabled}"
            )
        else:
            risk_config = RiskConfig(
                max_loss_percent=user_config.risk.max_loss_percent,
                max_leverage=user_config.risk.max_leverage,
            )
            logger.warning(
                "Runtime config provider missing; falling back to ConfigManager "
                f"risk config: max_loss_percent={risk_config.max_loss_percent}, "
                f"max_leverage={risk_config.max_leverage}, "
                f"max_total_exposure={risk_config.max_total_exposure}"
            )
        global _signal_pipeline
        _signal_pipeline = SignalPipeline(
            config_manager=config_manager,
            risk_config=risk_config,
            notification_service=_notification_service,
            signal_repository=signal_repository,
            signal_executor=_execution_orchestrator.execute_signal if _execution_orchestrator else None,
            cooldown_seconds=core_config.signal_pipeline.cooldown_seconds,
            runtime_strategy_definitions=runtime_strategy_definitions,
            runtime_allowed_directions=runtime_allowed_directions,
            runtime_mtf_ema_period=runtime_mtf_ema_period,
            runtime_execution_strategy=runtime_execution_strategy,
            runtime_risk_locked=runtime_risk_locked,
        )
        logger.info("Signal pipeline ready")

        # =============================================
        # Phase 6: REST API Warmup
        # =============================================
        logger.info("Phase 6: Warming up historical data...")
        if _runtime_config_provider is not None:
            runtime_market = _runtime_config_provider.resolved_config.market
            warmup_bars = runtime_market.warmup_history_bars
            symbols = runtime_market.symbols
            timeframes = runtime_market.timeframes
            logger.info(
                "Market scope driven by runtime config: "
                f"profile={_runtime_config_provider.resolved_config.profile_name}, "
                f"hash={_runtime_config_provider.config_hash}, "
                f"symbols={symbols}, timeframes={timeframes}, warmup_bars={warmup_bars}"
            )
        else:
            warmup_bars = core_config.warmup.history_bars
            symbols = core_config.core_symbols
            timeframes = user_config.timeframes
            logger.warning(
                "Runtime config provider missing; falling back to ConfigManager "
                f"market scope: symbols={symbols}, timeframes={timeframes}, "
                f"warmup_bars={warmup_bars}"
            )

        warmup_tasks = []
        for symbol in symbols:
            for timeframe in timeframes:
                task = asyncio.create_task(
                    _exchange_gateway.fetch_historical_ohlcv(symbol, timeframe, warmup_bars)
                )
                warmup_tasks.append(task)

        results = await asyncio.gather(*warmup_tasks, return_exceptions=True)
        success_count = sum(1 for r in results if isinstance(r, list))
        logger.info(f"Warmup complete: {success_count}/{len(warmup_tasks)} symbol/timeframe pairs loaded")

        # Feed warmup data to pipeline for EMA initialization
        # The new pipeline auto-warms up its runner, but we still need to store K-lines
        pipeline = get_signal_pipeline()
        for result in results:
            if isinstance(result, list):
                for kline in result:
                    # Store in pipeline history for MTF and runner warmup
                    pipeline._store_kline(kline)

        # Rebuild runner with warmup data to restore EMA and other stateful indicators
        pipeline._runner = pipeline._build_and_warmup_runner()
        logger.info("Historical data fed to pipeline for EMA warmup")

        # =============================================
        # Phase 7: Start Asset Polling
        # =============================================
        logger.info("Phase 7: Starting asset polling...")
        if _runtime_config_provider is not None:
            polling_interval = _runtime_config_provider.resolved_config.market.asset_polling_interval
            logger.info(f"Asset polling interval driven by runtime config: {polling_interval}s")
        else:
            polling_interval = user_config.asset_polling.interval_seconds
            logger.warning(f"Asset polling interval fallback from ConfigManager: {polling_interval}s")
        await _exchange_gateway.start_asset_polling(polling_interval)

        # Periodically update pipeline with latest snapshot
        async def update_snapshot_loop():
            while not _shutdown_event.is_set():
                snapshot = _exchange_gateway.get_account_snapshot()
                if snapshot and get_signal_pipeline():
                    get_signal_pipeline().update_account_snapshot(snapshot)
                await asyncio.sleep(polling_interval)

        asyncio.create_task(update_snapshot_loop())
        logger.info("Asset polling started")

        # =============================================
        # Phase 8: Start WebSocket Subscriptions
        # =============================================
        logger.info("Phase 8: Starting WebSocket subscriptions...")

        # Create WebSocket task
        ws_task = asyncio.create_task(
            _exchange_gateway.subscribe_ohlcv(
                symbols=symbols,
                timeframes=timeframes,
                callback=on_kline_received,
                history_bars=warmup_bars,
            )
        )

        logger.info("=" * 60)
        logger.info("SYSTEM READY - Monitoring started")
        logger.info("=" * 60)

        # =============================================
        # Phase 9: Start REST API Server (embedded)
        # =============================================
        import uvicorn
        from src.interfaces.api import app as api_app, set_dependencies, set_v3_dependencies

        api_port = int(os.environ.get("BACKEND_PORT", 8000))
        logger.info(f"Phase 9: Starting REST API server on port {api_port}...")

        # Set API dependencies (shared with main process)
        from src.application.signal_tracker import SignalStatusTracker
        from src.application.config_snapshot_service import ConfigSnapshotService
        from src.infrastructure.config_snapshot_repository import ConfigSnapshotRepository
        from src.infrastructure.config_entry_repository import ConfigEntryRepository

        _status_tracker = SignalStatusTracker(repository=signal_repository)

        # Initialize ConfigSnapshotService with repository
        snapshot_repo = ConfigSnapshotRepository(db_path="data/config_snapshots.db")
        await snapshot_repo.initialize()
        _snapshot_service = ConfigSnapshotService(repository=snapshot_repo)
        config_manager.set_snapshot_service(_snapshot_service)

        # Initialize ConfigEntryRepository for strategy params API
        _config_entry_repo = ConfigEntryRepository()
        await _config_entry_repo.initialize()

        # Inject into ConfigManager (required for backtest config KV storage)
        config_manager.set_config_entry_repository(_config_entry_repo)

        logger.info("ConfigEntryRepository initialized")

        # Initialize config repositories (unified dependency injection)
        from src.infrastructure.repositories.config_repositories import (
            StrategyConfigRepository,
            RiskConfigRepository,
            SystemConfigRepository,
            SymbolConfigRepository,
            NotificationConfigRepository,
            ConfigHistoryRepository,
            ConfigSnapshotRepositoryExtended,
        )

        _api_strategy_repo = StrategyConfigRepository()
        await _api_strategy_repo.initialize()
        logger.info("StrategyConfigRepository initialized")

        _api_risk_repo = RiskConfigRepository()
        await _api_risk_repo.initialize()
        logger.info("RiskConfigRepository initialized")

        _api_system_repo = SystemConfigRepository()
        await _api_system_repo.initialize()
        logger.info("SystemConfigRepository initialized")

        _api_symbol_repo = SymbolConfigRepository()
        await _api_symbol_repo.initialize()
        logger.info("SymbolConfigRepository initialized")

        _api_notification_repo = NotificationConfigRepository()
        await _api_notification_repo.initialize()
        logger.info("NotificationConfigRepository initialized")

        _api_history_repo = ConfigHistoryRepository()
        await _api_history_repo.initialize()
        logger.info("ConfigHistoryRepository initialized")

        _api_snapshot_repo_extended = ConfigSnapshotRepositoryExtended()
        await _api_snapshot_repo_extended.initialize()
        logger.info("ConfigSnapshotRepository initialized")

        set_dependencies(
            repository=signal_repository,
            account_getter=_exchange_gateway.get_account_snapshot,
            config_manager=config_manager,
            exchange_gateway=_exchange_gateway,
            signal_tracker=_status_tracker,
            snapshot_service=_snapshot_service,
            config_entry_repo=_config_entry_repo,
            order_repo=_order_repo,
            execution_intent_repo=_execution_intent_repo,
            order_lifecycle_service=_order_lifecycle_service,
            # Config repositories (unified with api_v1_config.py)
            strategy_repo=_api_strategy_repo,
            risk_repo=_api_risk_repo,
            system_repo=_api_system_repo,
            symbol_repo=_api_symbol_repo,
            notification_repo=_api_notification_repo,
            history_repo=_api_history_repo,
            snapshot_repo=_api_snapshot_repo_extended,
        )
        set_v3_dependencies(
            capital_protection=_capital_protection,
            account_service=account_service,
            execution_orchestrator=_execution_orchestrator,
        )
        logger.info("API dependencies initialized")

        # Start uvicorn server as a background task
        api_config = uvicorn.Config(
            api_app,
            host="0.0.0.0",
            port=api_port,
            log_level="warning",
            lifespan="off",
        )
        api_server = uvicorn.Server(api_config)
        api_task = asyncio.create_task(api_server.serve())

        # Wait a moment for API server to initialize
        await asyncio.sleep(2)
        logger.info(f"REST API server ready at http://localhost:{api_port}")

        # =============================================
        # Event Loop - Wait for shutdown
        # =============================================
        await _shutdown_event.wait()

        # Cancel WebSocket task
        ws_task.cancel()
        try:
            await ws_task
        except asyncio.CancelledError:
            pass

    except FatalStartupError as e:
        logger.error(f"Fatal startup error: {e}")
        if _notification_service:
            await _notification_service.send_system_alert(
                e.error_code, str(e)
            )
        sys.exit(1)

    except ConnectionLostError as e:
        logger.error(f"Connection lost: {e}")
        if _notification_service:
            await _notification_service.send_system_alert(
                e.error_code, str(e)
            )
        # Enter degraded mode - keep running but no signals
        logger.warning("Entering degraded mode...")
        await _shutdown_event.wait()

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        if _notification_service:
            await _notification_service.send_system_alert(
                "E-001", f"Unexpected error: {e}", e
            )
        sys.exit(1)

    finally:
        # Cleanup
        if _exchange_gateway:
            await _exchange_gateway.close()
            _exchange_gateway = None

        # Close ConfigEntryRepository
        if _config_entry_repo:
            await _config_entry_repo.close()
            logger.info("ConfigEntryRepository closed")
            _config_entry_repo = None

        # Close config repositories (unified dependency injection)
        if '_api_strategy_repo' in locals():
            await _api_strategy_repo.close()
            await _api_risk_repo.close()
            await _api_system_repo.close()
            await _api_symbol_repo.close()
            await _api_notification_repo.close()
            await _api_history_repo.close()
            await _api_snapshot_repo_extended.close()
            logger.info("Config repositories closed")

        # Stop API server task
        if 'api_task' in locals():
            logger.info("Stopping API server...")
            api_task.cancel()
            try:
                await api_task
            except asyncio.CancelledError:
                pass
            logger.info("API server shutdown complete")

        await close_db()
        logger.info("Database engines closed")

        _capital_protection = None
        _execution_orchestrator = None
        _runtime_config_provider = None

        logger.info("Application shutdown complete")


# ============================================================
# Entry Point
# ============================================================
def main():
    """
    Main entry point.
    Sets up event loop and runs the application.
    """
    try:
        # Create event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Run application
        loop.run_until_complete(run_application())

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Failed to start: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
