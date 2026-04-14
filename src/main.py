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
import sys
import signal as sys_signal
from typing import Optional

from src.application.config_manager import ConfigManager, load_all_configs
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.notifier import NotificationService, get_notification_service
from src.application.signal_pipeline import SignalPipeline
from src.domain.risk_calculator import RiskConfig
from src.domain.models import KlineData
from src.domain.exceptions import FatalStartupError, DependencyNotReadyError, ConnectionLostError
from src.infrastructure.logger import logger, setup_logger, register_secret


# ============================================================
# Global State
# ============================================================
_shutdown_event: Optional[asyncio.Event] = None  # Created in run_application()
_exchange_gateway: Optional[ExchangeGateway] = None
_notification_service: Optional[NotificationService] = None
_config_entry_repo = None  # Initialized in Phase 9


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

    global _shutdown_event
    _shutdown_event.set()

    if _exchange_gateway:
        await _exchange_gateway.close()

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
        # Phase 1: Load Configuration
        # =============================================
        logger.info("Phase 1: Loading configuration...")
        config_manager = load_all_configs()
        await config_manager.initialize_from_db()
        logger.info("Configuration loaded successfully")

        # R7.1: Explicit marker - ConfigManager initialization complete
        logger.info("[启动顺序] Phase 1 完成：ConfigManager 已初始化")

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
        # 配置重构后：直接使用 core_config.core_symbols 获取交易标的列表
        merged_symbols = core_config.core_symbols
        logger.info("Configuration snapshots ready for dependency injection")

        # =============================================
        # Phase 3: Initialize Notification Service
        # =============================================
        logger.info("Phase 3: Setting up notification channels...")
        _notification_service = get_notification_service()
        _notification_service.setup_channels(
            [{"type": ch.type, "webhook_url": ch.webhook_url}
             for ch in user_config.notification.channels]
        )
        logger.info(f"Notification channels ready: {len(_notification_service._channels)}")

        # =============================================
        # Phase 4: Initialize Exchange Gateway
        # =============================================
        logger.info("Phase 4: Initializing exchange gateway...")
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
        # Phase 4.5: Check API Key Permissions
        # =============================================
        logger.info("Phase 4.5: Checking API key permissions...")
        # 配置重构后：权限检查功能已移除，暂跳过此检查
        # TODO: 在 ExchangeGateway 中集成权限检查
        logger.info("API key permission check skipped (feature removed in config refactor)")

        # =============================================
        # Phase 5: Create Signal Pipeline (Dependency Injection)
        # =============================================
        logger.info("Phase 5: Creating signal pipeline...")
        # 配置重构后：SignalPipeline 需要 config_manager 作为第一个参数
        risk_config = RiskConfig(
            max_loss_percent=user_config.risk.max_loss_percent,
            max_leverage=user_config.risk.max_leverage,
        )
        global _signal_pipeline
        _signal_pipeline = SignalPipeline(
            config_manager=config_manager,
            risk_config=risk_config,
            notification_service=_notification_service,
            signal_repository=signal_repository,
            cooldown_seconds=core_config.signal_pipeline.cooldown_seconds,
        )
        logger.info("Signal pipeline ready")

        # =============================================
        # Phase 6: REST API Warmup
        # =============================================
        logger.info("Phase 6: Warming up historical data...")
        warmup_bars = core_config.warmup.history_bars
        symbols = merged_symbols
        timeframes = user_config.timeframes

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
        polling_interval = user_config.asset_polling.interval_seconds
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
        import os
        import uvicorn
        from src.interfaces.api import app as api_app, set_dependencies

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
            # Config repositories (unified with api_v1_config.py)
            strategy_repo=_api_strategy_repo,
            risk_repo=_api_risk_repo,
            system_repo=_api_system_repo,
            symbol_repo=_api_symbol_repo,
            notification_repo=_api_notification_repo,
            history_repo=_api_history_repo,
            snapshot_repo=_api_snapshot_repo_extended,
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

        # Close ConfigEntryRepository
        if _config_entry_repo:
            await _config_entry_repo.close()
            logger.info("ConfigEntryRepository closed")

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
