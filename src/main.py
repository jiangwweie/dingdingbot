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

from src.application.config_manager import ConfigManager, load_all_from_db
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.notifier import NotificationService, get_notification_service
from src.application.signal_pipeline import SignalPipeline
from src.domain.risk_calculator import RiskConfig
from src.domain.models import KlineData
from src.domain.exceptions import FatalStartupError, ConnectionLostError
from src.infrastructure.logger import logger, setup_logger, register_secret


# ============================================================
# Global State
# ============================================================
_shutdown_event: Optional[asyncio.Event] = None  # Created in run_application()
_exchange_gateway: Optional[ExchangeGateway] = None
_notification_service: Optional[NotificationService] = None


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


def create_signal_pipeline(config_manager: ConfigManager, signal_repository=None) -> SignalPipeline:
    """
    Create SignalPipeline from configuration.

    Args:
        config_manager: Loaded ConfigManager instance
        signal_repository: Optional SignalRepository instance for persistence

    Returns:
        Configured SignalPipeline instance
    """
    global _signal_pipeline

    # Get risk config from config_manager
    risk_config = config_manager.risk_config

    # Create pipeline with new dynamic config
    _signal_pipeline = SignalPipeline(
        config_manager=config_manager,
        risk_config=risk_config,
        notification_service=get_notification_service(),
        signal_repository=signal_repository,
        cooldown_seconds=config_manager.system_config.cooldown_seconds,
    )

    return _signal_pipeline


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
    global _exchange_gateway, _notification_service, _shutdown_event

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
        config_manager = await load_all_from_db()
        logger.info("Configuration loaded successfully")

        # =============================================
        # Phase 1.5: Initialize Signal Database
        # =============================================
        logger.info("Phase 1.5: Initializing signal database...")
        from src.infrastructure.signal_repository import SignalRepository
        signal_repository = SignalRepository()
        await signal_repository.initialize()
        logger.info("Signal database initialized")

        # =============================================
        # Phase 2: Initialize Notification Service
        # =============================================
        logger.info("Phase 2: Setting up notification channels...")
        _notification_service = get_notification_service()
        _notification_service.setup_channels(
            [{"type": ch.get('channel', 'feishu'), "webhook_url": ch.get('webhook_url', '')}
             for ch in config_manager.notifications]
        )
        logger.info(f"Notification channels ready: {len(_notification_service._channels)}")

        # =============================================
        # Phase 3: Initialize Exchange Gateway
        # =============================================
        logger.info("Phase 3: Initializing exchange gateway...")
        exchange_cfg = config_manager.exchange_config

        _exchange_gateway = ExchangeGateway(
            exchange_name=exchange_cfg.name,
            api_key=exchange_cfg.api_key,
            api_secret=exchange_cfg.api_secret,
            testnet=exchange_cfg.testnet,
        )

        await _exchange_gateway.initialize()
        logger.info("Exchange gateway initialized")

        # =============================================
        # Phase 3.5: Check API Key Permissions
        # =============================================
        logger.info("Phase 3.5: Checking API key permissions...")
        await config_manager.check_api_key_permissions(_exchange_gateway.rest_exchange)
        logger.info("API key permission check passed")

        # =============================================
        # Phase 4: Create Signal Pipeline
        # =============================================
        logger.info("Phase 4: Creating signal pipeline...")
        create_signal_pipeline(config_manager, signal_repository=signal_repository)
        logger.info("Signal pipeline ready")

        # =============================================
        # Phase 5: REST API Warmup
        # =============================================
        logger.info("Phase 5: Warming up historical data...")
        warmup_bars = config_manager.system_config.history_bars
        symbols = config_manager.symbols
        timeframes = ["15m", "1h", "4h", "1d"]  # Default timeframes or from config

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
        # Phase 6: Start Asset Polling
        # =============================================
        logger.info("Phase 6: Starting asset polling...")
        polling_interval = config_manager.asset_polling_config.interval_seconds
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
        # Phase 7: Start WebSocket Subscriptions
        # =============================================
        logger.info("Phase 7: Starting WebSocket subscriptions...")

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
        # Phase 7.5: Start REST API Server (embedded)
        # =============================================
        import os
        import uvicorn
        from src.interfaces.api import app as api_app, set_dependencies

        api_port = int(os.environ.get("BACKEND_PORT", 8000))
        logger.info(f"Phase 7.5: Starting REST API server on port {api_port}...")

        # Set API dependencies (shared with main process)
        from src.application.signal_tracker import SignalStatusTracker
        _status_tracker = SignalStatusTracker(repository=signal_repository)

        set_dependencies(
            repository=signal_repository,
            account_getter=_exchange_gateway.get_account_snapshot,
            config_manager=config_manager,
            exchange_gateway=_exchange_gateway,
            signal_tracker=_status_tracker,
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
