"""
Configuration Manager - Load configuration from SQLite database.
Handles API key validation from environment variables.
Supports hot-reload with atomic pointer swap and observer pattern.
"""
import asyncio
import os
from typing import List, Dict, Any, Optional, Callable, Awaitable, Set, Tuple
from decimal import Decimal
from datetime import datetime, timezone
import yaml

from pydantic import BaseModel, Field

from src.domain.exceptions import FatalStartupError
from src.infrastructure.logger import logger, register_secret, mask_secret
from src.domain.models import RiskConfig, StrategyDefinition, TriggerConfig, FilterConfig
from src.infrastructure.config_repository import ConfigRepository


# ============================================================
# Pydantic Config Models (for in-memory representation)
# ============================================================

class SystemConfig(BaseModel):
    """System configuration (read-only after startup)"""
    history_bars: int = Field(default=100, ge=50, le=1000, description="K 线预热数量")
    queue_batch_size: int = Field(default=10, ge=1, le=100, description="队列批大小")
    queue_flush_interval: float = Field(default=5.0, ge=1.0, le=60.0, description="队列刷新间隔 (秒)")

    # S3-1: Add MTF EMA period config
    mtf_ema_period: int = Field(
        default=60,
        description="Default EMA period for MTF trend calculation",
        ge=5,
        le=200
    )

    # Signal pipeline config
    cooldown_seconds: int = Field(default=14400, ge=60, description="Signal deduplication cooldown in seconds")


class ExchangeConfig(BaseModel):
    """Exchange configuration (from environment variables)"""
    name: str = Field(default="binance", description="Exchange name (ccxt id)")
    api_key: str = Field(..., description="API Key from environment variable")
    api_secret: str = Field(..., description="API Secret from environment variable")
    # 仅支持实盘，禁用测试网


class AssetPollingConfig(BaseModel):
    interval_seconds: int = Field(default=60, ge=10, description="Asset polling interval")


# ============================================================
# Config Manager
# ============================================================
class ConfigManager:
    """
    Manages configuration loading from SQLite database.
    Supports hot-reload with atomic pointer swap and observer pattern.
    API Key is read from environment variables, not stored in DB.
    """

    def __init__(self, db_path: str = "data/config.db"):
        """
        Initialize ConfigManager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._repo: Optional[ConfigRepository] = None

        # In-memory configuration (atomic pointer swap for hot-reload)
        self._active_strategy: Optional[StrategyDefinition] = None
        self._risk_config: Optional[RiskConfig] = None
        self._system_config: Optional[SystemConfig] = None
        self._symbols: List[str] = []
        self._notifications: List[Dict[str, Any]] = []
        self._exchange_config: Optional[ExchangeConfig] = None
        self._asset_polling_config: AssetPollingConfig = AssetPollingConfig()

        # Hot-reload state
        self._observers: Set[Callable[[], Awaitable[None]]] = set()
        self._update_lock: Optional[asyncio.Lock] = None  # Lazily initialized

    async def initialize(self) -> None:
        """
        Initialize the configuration repository and load all configurations.
        Must be called during application startup.
        """
        self._repo = ConfigRepository(self.db_path)
        await self._repo.initialize()
        await self.load_all_from_db()

    async def load_all_from_db(self) -> None:
        """
        Load all configurations from SQLite database.

        This is the main entry point for loading configuration.
        All config accessors will be populated after this method completes.
        """
        if not self._repo:
            raise FatalStartupError("ConfigRepository not initialized. Call initialize() first.", "F-003")

        # Load active strategy
        active_strategy_data = await self._repo.get_active_strategy()
        if active_strategy_data:
            self._active_strategy = self._convert_db_strategy_to_model(active_strategy_data)
        else:
            # Create default strategy if none exists
            default_strategy = StrategyDefinition(
                id="default",
                name="pinbar",
                trigger=TriggerConfig(type="pinbar", enabled=True, params={}),
                filters=[
                    FilterConfig(type="ema", period=60, enabled=True),
                    FilterConfig(type="mtf", enabled=True)
                ],
                filter_logic="AND",
                is_global=True
            )
            self._active_strategy = default_strategy
            logger.warning("使用默认策略配置（数据库中无激活策略）")

        # Load risk config
        risk_data = await self._repo.get_risk_config()
        if risk_data:
            self._risk_config = RiskConfig(
                max_loss_percent=Decimal(str(risk_data.get('max_loss_percent', 1.0))),
                max_leverage=risk_data.get('max_leverage', 10),
                max_total_exposure=Decimal(str(risk_data.get('max_total_exposure', 0.8)))
            )
        else:
            # Create default risk config if none exists
            self._risk_config = RiskConfig(
                max_loss_percent=Decimal('1.0'),
                max_leverage=10,
                max_total_exposure=Decimal('0.8')
            )
            logger.warning("使用默认风控配置（数据库中无风控配置）")

        # Load system config
        system_data = await self._repo.get_system_config()
        if system_data:
            self._system_config = SystemConfig(
                history_bars=system_data.get('history_bars', 100),
                queue_batch_size=system_data.get('queue_batch_size', 10),
                queue_flush_interval=system_data.get('queue_flush_interval', 5.0),
                mtf_ema_period=60,
                cooldown_seconds=14400
            )
        else:
            # Create default system config if none exists
            self._system_config = SystemConfig(
                history_bars=100,
                queue_batch_size=10,
                queue_flush_interval=5.0,
                mtf_ema_period=60,
                cooldown_seconds=14400
            )
            logger.warning("使用默认系统配置（数据库中无系统配置）")

        # Load symbols (enabled only)
        symbols_data = await self._repo.get_enabled_symbols()
        if symbols_data:
            self._symbols = symbols_data
        else:
            # Default core symbols if none exist
            self._symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
            logger.warning("使用默认币池配置（数据库中无币池配置）")

        # Load notification channels (enabled only)
        notifications_data = await self._repo.get_enabled_notifications()
        if notifications_data:
            self._notifications = notifications_data
        else:
            # Empty notifications if none exist
            self._notifications = []
            logger.warning("未配置通知渠道（数据库中无通知配置）")

        # Load exchange config from environment variables
        self._exchange_config = self._load_exchange_config_from_env()

        logger.info(f"配置加载完成：{len(self._symbols)} 个交易对，{len(self._notifications)} 个通知渠道")

    def _convert_db_strategy_to_model(self, strategy_data: Dict[str, Any]) -> StrategyDefinition:
        """
        Convert database strategy record to StrategyDefinition model.

        Args:
            strategy_data: Dictionary from database query

        Returns:
            StrategyDefinition model instance
        """
        triggers = strategy_data.get('triggers', [])
        filters = strategy_data.get('filters', [])
        apply_to = strategy_data.get('apply_to', [])

        # Parse triggers
        trigger_configs = []
        for t in triggers:
            if isinstance(t, dict):
                trigger_configs.append(TriggerConfig(
                    type=t.get('type', 'pinbar'),
                    enabled=t.get('enabled', True),
                    params=t.get('params', {})
                ))

        # Parse filters
        filter_configs = []
        for f in filters:
            if isinstance(f, dict):
                filter_configs.append(FilterConfig(
                    type=f.get('type', 'ema'),
                    enabled=f.get('enabled', True),
                    params={k: v for k, v in f.items() if k not in ('type', 'enabled')}
                ))

        # Build StrategyDefinition
        return StrategyDefinition(
            id=str(strategy_data.get('id', '')),
            name=strategy_data.get('name', 'unknown'),
            triggers=trigger_configs,
            trigger_logic="OR",
            filters=filter_configs,
            filter_logic="AND",
            is_global=len(apply_to) == 0,
            apply_to=apply_to
        )

    def _load_exchange_config_from_env(self) -> ExchangeConfig:
        """
        Load exchange configuration from environment variables.

        Required environment variables:
        - EXCHANGE_API_KEY: API key for exchange
        - EXCHANGE_API_SECRET: API secret for exchange

        Optional environment variables:
        - EXCHANGE_NAME: Exchange name (default: "binance")

        Returns:
            ExchangeConfig instance

        Raises:
            FatalStartupError: If required environment variables are missing
        """
        api_key = os.getenv('EXCHANGE_API_KEY')
        api_secret = os.getenv('EXCHANGE_API_SECRET')

        if not api_key:
            raise FatalStartupError(
                "环境变量 EXCHANGE_API_KEY 未设置。请在 .env 文件或系统环境变量中配置 API 密钥。",
                "F-003"
            )

        if not api_secret:
            raise FatalStartupError(
                "环境变量 EXCHANGE_API_SECRET 未设置。请在 .env 文件或系统环境变量中配置 API 密钥。",
                "F-003"
            )

        name = os.getenv('EXCHANGE_NAME', 'binance')

        # Register secrets for masking
        register_secret(api_key)
        register_secret(api_secret)

        return ExchangeConfig(
            name=name,
            api_key=api_key,
            api_secret=api_secret
        )

    async def check_api_key_permissions(self, exchange: Any) -> None:
        """
        API Key 读写权限探测已被强行跳过。
        用户需自行保证该 Key 仅拥有只读与合约权限，发生资产意外操作责任自负！

        Args:
            exchange: Initialized CCXT exchange instance
        """
        logger.warning(
            "API Key 读写权限探测已被强行跳过。"
            "用户需自行保证该 Key 仅拥有只读与合约权限，发生资产意外操作责任自负！"
        )
        return

    def print_startup_info(self) -> None:
        """
        Print all effective configuration parameters to console (with secrets masked).
        """
        logger.info("=" * 60)
        logger.info("EFFECTIVE CONFIGURATION (Startup)")
        logger.info("=" * 60)

        # Exchange info (masked)
        if self._exchange_config:
            logger.info(f"Exchange: {self._exchange_config.name}")
            logger.info(f"API Key: {mask_secret(self._exchange_config.api_key)}")
            logger.info("Mode: LIVE (实盘模式，禁用测试网)")

        # Symbols
        logger.info(f"Monitoring {len(self._symbols)} symbols:")
        for symbol in self._symbols[:10]:  # Show first 10
            logger.info(f"  - {symbol}")
        if len(self._symbols) > 10:
            logger.info(f"  ... and {len(self._symbols) - 10} more")

        # Active strategy
        if self._active_strategy:
            status = "ENABLED" if self._active_strategy.trigger and self._active_strategy.trigger.enabled else "DISABLED"
            filter_names = ", ".join([f.type for f in self._active_strategy.filters]) if self._active_strategy.filters else "none"
            logger.info(f"Active Strategy: {self._active_strategy.name} ({status})")
            logger.info(f"  Filters: {filter_names or 'none'}")

        # Risk settings
        if self._risk_config:
            logger.info(f"Risk Settings:")
            logger.info(f"  - Max Loss per Trade: {float(self._risk_config.max_loss_percent) * 100}%")
            logger.info(f"  - Max Leverage: {self._risk_config.max_leverage}x")
            logger.info(f"  - Max Total Exposure: {float(self._risk_config.max_total_exposure) * 100}%")

        # System settings
        if self._system_config:
            logger.info(f"System Settings:")
            logger.info(f"  - History Bars: {self._system_config.history_bars}")
            logger.info(f"  - Queue Batch Size: {self._system_config.queue_batch_size}")
            logger.info(f"  - Queue Flush Interval: {self._system_config.queue_flush_interval}s")
            logger.info(f"  - Signal Cooldown: {self._system_config.cooldown_seconds}s")

        # Notification channels
        logger.info(f"Notification Channels ({len(self._notifications)}):")
        if self._notifications:
            for channel in self._notifications:
                webhook = channel.get('webhook_url', '')
                channel_type = channel.get('channel', 'unknown')
                logger.info(f"  - {channel_type}: {mask_secret(webhook)}")
        else:
            logger.info("  (none configured)")

        logger.info("=" * 60)

    # ============================================================
    # Config Accessor Properties
    # ============================================================

    @property
    def active_strategy(self) -> Optional[StrategyDefinition]:
        """Get the currently active strategy definition."""
        return self._active_strategy

    @property
    def risk_config(self) -> Optional[RiskConfig]:
        """Get the risk management configuration."""
        return self._risk_config

    @property
    def system_config(self) -> Optional[SystemConfig]:
        """Get the system configuration."""
        return self._system_config

    @property
    def symbols(self) -> List[str]:
        """Get the list of enabled trading symbols."""
        return self._symbols

    @property
    def notifications(self) -> List[Dict[str, Any]]:
        """Get the list of enabled notification channels."""
        return self._notifications

    @property
    def exchange_config(self) -> Optional[ExchangeConfig]:
        """Get the exchange configuration (from environment variables)."""
        return self._exchange_config

    @property
    def asset_polling_config(self) -> AssetPollingConfig:
        """Get the asset polling configuration."""
        return self._asset_polling_config

    # ============================================================
    # Hot-Reload & Observer Pattern
    # ============================================================

    def _get_update_lock(self) -> asyncio.Lock:
        """Get or create the update lock for thread-safe config updates."""
        if self._update_lock is None:
            try:
                self._update_lock = asyncio.Lock()
            except RuntimeError:
                # No running event loop
                pass
        return self._update_lock

    def add_observer(self, callback: Callable[[], Awaitable[None]]) -> None:
        """
        Add an observer callback to be invoked when configuration is updated.

        Observers are called asynchronously after atomic config replacement.
        Use case: auto-reconnect exchange WebSocket on config change.

        Args:
            callback: Async function to call with no arguments
        """
        self._observers.add(callback)
        logger.info(f"Observer added. Total observers: {len(self._observers)}")

    def remove_observer(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Remove an observer callback."""
        self._observers.discard(callback)

    async def reload_config(self) -> None:
        """
        Hot-reload configuration from database.

        This method reloads all configurations from the database and
        notifies all observers asynchronously.

        Use this for hot-reloading after configuration changes via API.
        """
        if not self._repo:
            raise FatalStartupError("ConfigRepository not initialized", "F-003")

        async with self._get_update_lock():
            # Reload all configs from DB
            await self.load_all_from_db()

            # Notify observers
            await self._notify_observers()

            logger.info("Configuration reloaded from database")

    async def _notify_observers(self) -> None:
        """Notify all observers of config update (non-blocking)."""
        if not self._observers:
            return

        # Fire all observers concurrently
        results = await asyncio.gather(
            *[self._safe_observer_call(cb) for cb in self._observers],
            return_exceptions=True
        )

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Observer {i} failed: {result}")

    async def _safe_observer_call(self, callback: Callable[[], Awaitable[None]]) -> Any:
        """Safely call an observer, catching any exceptions."""
        try:
            return await callback()
        except Exception as e:
            logger.error(f"Observer callback raised: {e}")
            raise


    # ============================================================
    # Import/Export Methods
    # ============================================================

    def get_full_config(self) -> Dict[str, Any]:
        """
        Get complete configuration as a dictionary.

        Returns:
            Dictionary containing all configuration sections:
            - strategy: Active strategy definition
            - risk: Risk management config
            - system: System config
            - symbols: List of symbol configs
            - notifications: List of notification configs
        """
        from decimal import Decimal

        result = {}

        # Strategy
        if self._active_strategy:
            strat = self._active_strategy
            strat_dict = {
                'name': strat.name,
                'is_active': strat.trigger.enabled if strat.trigger else True,
            }
            if strat.triggers:
                strat_dict['triggers'] = [
                    {'type': t.type, 'params': t.params or {}}
                    for t in strat.triggers
                ]
            if strat.filters:
                strat_dict['filters'] = [
                    {'type': f.type, 'params': f.params or {}}
                    for f in strat.filters
                ]
            if strat.apply_to:
                strat_dict['apply_to'] = strat.apply_to
            result['strategy'] = strat_dict

        # Risk config
        if self._risk_config:
            result['risk'] = {
                'max_loss_percent': float(self._risk_config.max_loss_percent),
                'max_total_exposure': float(self._risk_config.max_total_exposure),
                'max_leverage': self._risk_config.max_leverage,
            }

        # System config
        if self._system_config:
            result['system'] = {
                'history_bars': self._system_config.history_bars,
                'queue_batch_size': self._system_config.queue_batch_size,
                'queue_flush_interval': self._system_config.queue_flush_interval,
            }

        # Symbols
        core_symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
        result['symbols'] = [
            {
                'symbol': symbol,
                'is_core': symbol in core_symbols,
                'is_enabled': True,
            }
            for symbol in self._symbols
        ]

        # Notifications
        result['notifications'] = [
            {
                'channel': channel.get('channel', 'feishu'),
                'webhook_url': channel.get('webhook_url', ''),
                'is_enabled': True,
            }
            for channel in self._notifications
        ]

        return result

    def export_to_yaml(self, include_strategies: bool = True) -> str:
        """
        Export current configuration to YAML format.

        Args:
            include_strategies: Whether to include strategy definitions

        Returns:
            YAML string containing the configuration
        """
        export_data = {
            'exported_at': datetime.now(timezone.utc).isoformat(),
            'version': '1.0',
        }

        # Risk config
        if self._risk_config:
            export_data['risk_config'] = {
                'max_loss_percent': float(self._risk_config.max_loss_percent),
                'max_total_exposure': float(self._risk_config.max_total_exposure),
                'max_leverage': self._risk_config.max_leverage,
            }

        # System config
        if self._system_config:
            export_data['system_config'] = {
                'history_bars': self._system_config.history_bars,
                'queue_batch_size': self._system_config.queue_batch_size,
                'queue_flush_interval': self._system_config.queue_flush_interval,
            }

        # Symbols with their status
        core_symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
        symbols_list = []
        for symbol in self._symbols:
            symbols_list.append({
                'symbol': symbol,
                'is_core': symbol in core_symbols,
                'is_enabled': True,
            })
        export_data['symbols'] = symbols_list

        # Strategies (optional)
        if include_strategies and self._active_strategy:
            strat = self._active_strategy
            strat_dict = {
                'name': strat.name,
                'is_active': strat.trigger.enabled if strat.trigger else True,
            }
            if strat.triggers:
                strat_dict['triggers'] = [
                    {'type': t.type, 'params': t.params or {}}
                    for t in strat.triggers
                ]
            if strat.filters:
                strat_dict['filters'] = [
                    {'type': f.type, 'params': f.params or {}}
                    for f in strat.filters
                ]
            if strat.apply_to:
                strat_dict['apply_to'] = strat.apply_to
            export_data['strategies'] = [strat_dict]

        # Notification channels
        channels = []
        for channel in self._notifications:
            channels.append({
                'type': channel.get('channel', 'feishu'),
                'webhook_url': channel.get('webhook_url', ''),
                'is_enabled': True,
            })
        export_data['notifications'] = channels

        # Custom representer for Decimal
        def decimal_representer(dumper, data):
            return dumper.represent_float(float(data), '')
        
        yaml.add_representer(Decimal, decimal_representer)
        
        return yaml.safe_dump(
            export_data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False
        )

    def import_preview(self, yaml_content: str) -> Dict[str, Any]:
        """
        Preview import changes without applying them.
        """
        result = {
            'valid': True,
            'changes': [],
            'errors': [],
            'warnings': [],
        }

        try:
            import_data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            result['valid'] = False
            result['errors'].append({
                'field': 'yaml',
                'message': f'YAML parse error: {str(e)}',
            })
            return result

        if not isinstance(import_data, dict):
            result['valid'] = False
            result['errors'].append({
                'field': 'yaml',
                'message': 'YAML content must be a dictionary',
            })
            return result

        if 'risk_config' in import_data:
            changes, errors = self._validate_risk_config(import_data['risk_config'])
            result['changes'].extend(changes)
            result['errors'].extend(errors)

        if 'system_config' in import_data:
            changes, errors = self._validate_system_config(import_data['system_config'])
            result['changes'].extend(changes)
            result['errors'].extend(errors)

        if 'symbols' in import_data:
            changes, errors, warnings = self._validate_symbols(import_data['symbols'])
            result['changes'].extend(changes)
            result['errors'].extend(errors)
            result['warnings'].extend(warnings)

        if 'strategies' in import_data:
            changes, errors, warnings = self._validate_strategies(import_data['strategies'])
            result['changes'].extend(changes)
            result['errors'].extend(errors)
            result['warnings'].extend(warnings)

        if 'notifications' in import_data:
            changes, errors = self._validate_notifications(import_data['notifications'])
            result['changes'].extend(changes)
            result['errors'].extend(errors)

        if result['errors']:
            result['valid'] = False

        return result

    def _validate_risk_config(self, risk_data: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
        """Validate risk config changes."""
        changes = []
        errors = []

        if not self._risk_config:
            return changes, errors

        if 'max_loss_percent' in risk_data:
            try:
                value = Decimal(str(risk_data['max_loss_percent']))
                if value <= 0 or value > Decimal('1'):
                    errors.append({'field': 'risk_config.max_loss_percent', 'message': 'Value must be between 0 and 1 (exclusive)'})
                else:
                    changes.append({
                        'category': 'risk', 'action': 'update', 'field': 'max_loss_percent',
                        'old_value': float(self._risk_config.max_loss_percent), 'new_value': float(value),
                    })
            except Exception as e:
                errors.append({'field': 'risk_config.max_loss_percent', 'message': f'Invalid value: {str(e)}'})

        if 'max_leverage' in risk_data:
            try:
                value = int(risk_data['max_leverage'])
                if value < 1 or value > 125:
                    errors.append({'field': 'risk_config.max_leverage', 'message': 'Value must be between 1 and 125'})
                else:
                    changes.append({
                        'category': 'risk', 'action': 'update', 'field': 'max_leverage',
                        'old_value': self._risk_config.max_leverage, 'new_value': value,
                    })
            except Exception as e:
                errors.append({'field': 'risk_config.max_leverage', 'message': f'Invalid value: {str(e)}'})

        if 'max_total_exposure' in risk_data:
            try:
                value = Decimal(str(risk_data['max_total_exposure']))
                if value < 0 or value > Decimal('1'):
                    errors.append({'field': 'risk_config.max_total_exposure', 'message': 'Value must be between 0 and 1'})
                else:
                    changes.append({
                        'category': 'risk', 'action': 'update', 'field': 'max_total_exposure',
                        'old_value': float(self._risk_config.max_total_exposure), 'new_value': float(value),
                    })
            except Exception as e:
                errors.append({'field': 'risk_config.max_total_exposure', 'message': f'Invalid value: {str(e)}'})

        return changes, errors

    def _validate_system_config(self, system_data: Dict[str, Any]) -> Tuple[List[Dict], List[Dict]]:
        """Validate system config changes."""
        changes = []
        errors = []

        if not self._system_config:
            return changes, errors

        current = {
            'history_bars': self._system_config.history_bars,
            'queue_batch_size': self._system_config.queue_batch_size,
            'queue_flush_interval': self._system_config.queue_flush_interval,
        }

        for field in ['history_bars', 'queue_batch_size', 'queue_flush_interval']:
            if field in system_data:
                value = system_data[field]
                valid = True
                if field == 'history_bars' and (not isinstance(value, int) or value < 10):
                    errors.append({'field': f'system_config.{field}', 'message': 'Value must be an integer >= 10'})
                    valid = False
                elif field == 'queue_batch_size' and (not isinstance(value, int) or value < 1):
                    errors.append({'field': f'system_config.{field}', 'message': 'Value must be an integer >= 1'})
                    valid = False
                elif field == 'queue_flush_interval' and (not isinstance(value, (int, float)) or value < 0.1):
                    errors.append({'field': f'system_config.{field}', 'message': 'Value must be a number >= 0.1'})
                    valid = False

                if valid:
                    changes.append({
                        'category': 'system', 'action': 'update', 'field': field,
                        'old_value': current[field], 'new_value': value,
                    })

        return changes, errors

    def _validate_symbols(self, symbols_data: List[Dict]) -> Tuple[List[Dict], List[Dict], List[str]]:
        """Validate symbols changes."""
        changes, errors, warnings = [], [], []

        if not isinstance(symbols_data, list):
            return [{'field': 'symbols', 'message': 'Symbols must be a list'}], [], []

        core_symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
        current_symbols = set(self._symbols) if self._symbols else set()

        for idx, sym_data in enumerate(symbols_data):
            if not isinstance(sym_data, dict):
                errors.append({'field': f'symbols[{idx}]', 'message': 'Each symbol entry must be a dictionary'})
                continue

            symbol = sym_data.get('symbol')
            if not symbol:
                errors.append({'field': f'symbols[{idx}]', 'message': 'Missing required field: symbol'})
                continue

            if '/' not in symbol or ':' not in symbol:
                errors.append({'field': f'symbols[{idx}].symbol', 'message': f'Invalid symbol format: {symbol}'})
                continue

            is_core = sym_data.get('is_core', False)
            is_enabled = sym_data.get('is_enabled', True)

            if symbol in core_symbols and not is_core:
                warnings.append(f'Core symbol {symbol} marked as non-core in import (will be ignored)')

            action = 'update' if symbol in current_symbols else 'create'
            changes.append({
                'category': 'symbol', 'action': action, 'field': symbol,
                'new_value': {'is_core': is_core, 'is_enabled': is_enabled},
            })

        return changes, errors, warnings

    def _validate_strategies(self, strategies_data: List[Dict]) -> Tuple[List[Dict], List[Dict], List[str]]:
        """Validate strategies changes."""
        changes, errors, warnings = [], [], []

        if not isinstance(strategies_data, list):
            return [{'field': 'strategies', 'message': 'Strategies must be a list'}], [], []

        for idx, strat_data in enumerate(strategies_data):
            if not isinstance(strat_data, dict):
                errors.append({'field': f'strategies[{idx}]', 'message': 'Each strategy entry must be a dictionary'})
                continue

            name = strat_data.get('name')
            if not name:
                errors.append({'field': f'strategies[{idx}]', 'message': 'Missing required field: name'})
                continue

            triggers = strat_data.get('triggers', [])
            if not isinstance(triggers, list):
                errors.append({'field': f'strategies[{idx}].triggers', 'message': 'Triggers must be a list'})
            else:
                for t_idx, t in enumerate(triggers):
                    if not isinstance(t, dict) or 'type' not in t:
                        errors.append({'field': f'strategies[{idx}].triggers[{t_idx}]', 'message': 'Invalid trigger'})

            filters = strat_data.get('filters', [])
            if not isinstance(filters, list):
                errors.append({'field': f'strategies[{idx}].filters', 'message': 'Filters must be a list'})
            else:
                for f_idx, f in enumerate(filters):
                    if not isinstance(f, dict) or 'type' not in f:
                        errors.append({'field': f'strategies[{idx}].filters[{f_idx}]', 'message': 'Invalid filter'})

            if 'apply_to' in strat_data:
                warnings.append(f'Strategy {name} scope changes may require restart')

            changes.append({
                'category': 'strategy', 'action': 'update' if self._active_strategy else 'create',
                'field': name, 'new_value': strat_data,
            })

        return changes, errors, warnings

    def _validate_notifications(self, notifications_data: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """Validate notifications changes."""
        changes, errors = [], []

        if not isinstance(notifications_data, list):
            return [{'field': 'notifications', 'message': 'Notifications must be a list'}], []

        for idx, notif_data in enumerate(notifications_data):
            if not isinstance(notif_data, dict):
                errors.append({'field': f'notifications[{idx}]', 'message': 'Must be a dictionary'})
                continue

            channel_type = notif_data.get('type')
            if not channel_type or channel_type not in ('feishu', 'wecom', 'telegram'):
                errors.append({'field': f'notifications[{idx}].type', 'message': 'Invalid channel type'})
                continue

            webhook_url = notif_data.get('webhook_url')
            if not webhook_url:
                errors.append({'field': f'notifications[{idx}].webhook_url', 'message': 'Missing webhook_url'})
                continue

            changes.append({
                'category': 'notification', 'action': 'update' if idx < len(self._notifications) else 'create',
                'field': f'{channel_type}:{webhook_url[:20]}...', 'new_value': notif_data,
            })

        return changes, errors

    async def import_confirm(self, yaml_content: str, create_snapshot: bool = True) -> Dict[str, Any]:
        """
        Confirm and apply import changes.

        Args:
            yaml_content: YAML string to import
            create_snapshot: Whether to create a snapshot before applying changes (not yet implemented)

        Returns:
            Dictionary containing:
            - success: bool - Whether the import was successful
            - message: str - Result message
            - requires_restart: bool - Whether restart is required
            - applied_changes: int - Number of changes applied
        """
        preview = self.import_preview(yaml_content)

        if not preview['valid']:
            return {
                'success': False,
                'message': f'Import validation failed: {len(preview["errors"])} errors',
                'requires_restart': False,
                'applied_changes': 0,
                'errors': preview['errors'],
            }

        try:
            import_data = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            return {'success': False, 'message': f'YAML parse error: {str(e)}', 'requires_restart': False, 'applied_changes': 0}

        applied_changes = 0
        requires_restart = False

        # Apply risk config changes
        if 'risk_config' in import_data and self._repo:
            risk_data = import_data['risk_config']
            if 'max_loss_percent' in risk_data:
                await self._repo.update_risk_config(max_loss_percent=float(risk_data['max_loss_percent']))
                applied_changes += 1
            if 'max_leverage' in risk_data:
                await self._repo.update_risk_config(max_leverage=risk_data['max_leverage'])
                applied_changes += 1
            if 'max_total_exposure' in risk_data:
                await self._repo.update_risk_config(max_total_exposure=float(risk_data['max_total_exposure']))
                applied_changes += 1

        # Apply system config changes (requires restart)
        if 'system_config' in import_data and self._repo:
            system_data = import_data['system_config']
            if 'history_bars' in system_data:
                await self._repo.update_system_config(history_bars=system_data['history_bars'])
                applied_changes += 1
            if 'queue_batch_size' in system_data:
                await self._repo.update_system_config(queue_batch_size=system_data['queue_batch_size'])
                applied_changes += 1
            if 'queue_flush_interval' in system_data:
                await self._repo.update_system_config(queue_flush_interval=system_data['queue_flush_interval'])
                applied_changes += 1
            if any(k in system_data for k in ['history_bars', 'queue_batch_size', 'queue_flush_interval']):
                requires_restart = True
                logger.warning("System config changes detected. Restart required.")

        # Apply symbol changes
        if 'symbols' in import_data and self._repo:
            for sym_data in import_data['symbols']:
                symbol = sym_data.get('symbol')
                is_core = sym_data.get('is_core', False)
                is_enabled = sym_data.get('is_enabled', True)
                if symbol:
                    await self._repo.add_symbol(symbol, 1 if is_core else 0, 1 if is_enabled else 0)
                    applied_changes += 1

        # Apply strategy changes
        if 'strategies' in import_data and self._repo:
            for strat_data in import_data['strategies']:
                await self._update_strategy_from_import(strat_data)
                applied_changes += 1

        # Apply notification changes
        if 'notifications' in import_data and self._repo:
            for notif_data in import_data['notifications']:
                channel_type = notif_data.get('type', 'feishu')
                webhook_url = notif_data.get('webhook_url', '')
                is_enabled = notif_data.get('is_enabled', True)
                await self._repo.add_notification(channel_type, webhook_url, 1 if is_enabled else 0)
                applied_changes += 1

        # Reload config from database to apply changes
        if applied_changes > 0:
            await self.reload_config()

        return {
            'success': True,
            'message': f'Successfully applied {applied_changes} changes' + (' (restart required)' if requires_restart else ''),
            'requires_restart': requires_restart,
            'applied_changes': applied_changes,
        }

    async def _update_strategy_from_import(self, strat_data: Dict[str, Any]) -> None:
        """Update or create a strategy from import data."""
        if not self._repo:
            return

        name = strat_data.get('name', 'unknown')
        is_active = strat_data.get('is_active', True)

        triggers = [{'type': t.get('type', 'pinbar'), 'enabled': t.get('enabled', True), 'params': t.get('params', {})} for t in strat_data.get('triggers', [])]
        filters = [{'type': f.get('type', 'ema'), 'enabled': f.get('enabled', True), **f.get('params', {})} for f in strat_data.get('filters', [])]
        apply_to = strat_data.get('apply_to', [])

        await self._repo.update_strategy(name=name, triggers=triggers, filters=filters, apply_to=apply_to, is_active=is_active)



    async def close(self) -> None:
        """Close the configuration repository connection."""
        if self._repo:
            await self._repo.close()
            logger.info("Configuration repository connection closed")


# ============================================================
# Convenience function
# ============================================================
async def load_all_from_db(db_path: str = "data/config.db") -> ConfigManager:
    """
    Load all configurations from database and return ConfigManager instance.

    Args:
        db_path: Path to SQLite database file

    Returns:
        ConfigManager with all configs loaded
    """
    manager = ConfigManager(db_path)
    await manager.initialize()
    manager.print_startup_info()
    return manager
