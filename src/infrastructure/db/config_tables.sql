-- ============================================================
-- 盯盘狗 🐶 配置管理系统数据库表结构
-- ============================================================
-- 创建时间：2026-04-04
-- 最后更新：2026-04-11
-- 数据库：SQLite 3
-- 用途：配置管理系统 - 9 张核心配置表
-- ============================================================

-- ============================================================
-- 1. strategies - 策略配置表
-- ============================================================
-- 存储用户定义的策略配置，包括触发器、过滤器、作用域
-- ============================================================
CREATE TABLE IF NOT EXISTS strategies (
    id TEXT PRIMARY KEY,                              -- 策略 ID, UUID 格式
    name TEXT NOT NULL,                               -- 策略名称
    description TEXT,                                  -- 策略描述
    is_active BOOLEAN DEFAULT TRUE,                    -- 是否启用
    trigger_config TEXT NOT NULL,                      -- JSON: 触发器配置
    filter_configs TEXT NOT NULL,                      -- JSON: 过滤器链配置
    filter_logic TEXT DEFAULT 'AND',                   -- 过滤器组合逻辑：'AND' | 'OR'
    symbols TEXT NOT NULL,                             -- JSON: 作用币种列表
    timeframes TEXT NOT NULL,                          -- JSON: 作用周期列表
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,    -- 创建时间
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,    -- 最后更新时间
    version INTEGER DEFAULT 1                          -- 版本号 (用于乐观锁)
);

-- 索引：查询活跃策略
CREATE INDEX IF NOT EXISTS idx_strategies_active ON strategies(is_active);
-- 索引：按更新时间排序
CREATE INDEX IF NOT EXISTS idx_strategies_updated ON strategies(updated_at);


-- ============================================================
-- 2. risk_configs - 风控配置表
-- ============================================================
-- 存储全局风控参数，单例模式 (id='global')
-- ============================================================
CREATE TABLE IF NOT EXISTS risk_configs (
    id TEXT PRIMARY KEY DEFAULT 'global',              -- 固定为'global'
    max_loss_percent DECIMAL(5,4) NOT NULL,            -- 最大损失百分比 (默认 0.01 = 1%)
    max_leverage INTEGER NOT NULL,                     -- 最大杠杆倍数 (默认 10)
    max_total_exposure DECIMAL(5,4),                   -- 最大总敞口 (默认 0.8 = 80%)
    daily_max_trades INTEGER,                          -- 每日最大交易次数
    daily_max_loss DECIMAL(20,8),                      -- 每日最大损失金额
    max_position_hold_time INTEGER,                    -- 最大持仓时间 (分钟)
    cooldown_minutes INTEGER DEFAULT 240,              -- 信号冷却时间 (默认 240 分钟=4 小时)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,    -- 创建时间
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,    -- 最后更新时间
    version INTEGER DEFAULT 1                          -- 版本号 (用于乐观锁)
);


-- ============================================================
-- 3. system_configs - 系统配置表
-- ============================================================
-- 存储系统级配置参数，单例模式 (id='global')
-- ============================================================
CREATE TABLE IF NOT EXISTS system_configs (
    id TEXT PRIMARY KEY DEFAULT 'global',              -- 固定为'global'
    core_symbols TEXT NOT NULL,                        -- JSON: 核心币种列表
    ema_period INTEGER DEFAULT 60,                     -- EMA 周期 (默认 60)
    mtf_ema_period INTEGER DEFAULT 60,                 -- MTF-EMA 周期 (默认 60)
    mtf_mapping TEXT NOT NULL,                         -- JSON: MTF 映射关系
    signal_cooldown_seconds INTEGER DEFAULT 14400,     -- 信号冷却时间 (默认 14400 秒=4 小时)
    queue_batch_size INTEGER DEFAULT 10,               -- 队列批处理大小
    queue_flush_interval DECIMAL(4,2) DEFAULT 5.0,     -- 队列刷新间隔 (秒)
    queue_max_size INTEGER DEFAULT 1000,               -- 队列最大容量
    warmup_history_bars INTEGER DEFAULT 100,           -- 预热历史 K 线数量
    atr_filter_enabled BOOLEAN DEFAULT TRUE,           -- ATR 过滤器开关
    atr_period INTEGER DEFAULT 14,                     -- ATR 周期
    atr_min_ratio DECIMAL(4,2) DEFAULT 0.5,            -- ATR 最小比率
    timeframes TEXT NOT NULL DEFAULT '["15m","1h"]',   -- JSON: 监控时间周期列表
    asset_polling_enabled BOOLEAN DEFAULT TRUE,        -- 资产轮询开关
    asset_polling_interval INTEGER DEFAULT 60,         -- 资产轮询间隔 (秒)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,    -- 创建时间
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP     -- 最后更新时间
);


-- ============================================================
-- 4. symbols - 币池配置表
-- ============================================================
-- 存储所有可选币种及其交易参数
-- ============================================================
CREATE TABLE IF NOT EXISTS symbols (
    symbol TEXT PRIMARY KEY,                           -- 币种符号，如"BTC/USDT:USDT"
    is_active BOOLEAN DEFAULT TRUE,                    -- 是否启用
    is_core BOOLEAN DEFAULT FALSE,                     -- 是否为核心币种 (不可删除)
    min_quantity DECIMAL(20,8),                        -- 最小下单数量
    price_precision INTEGER,                           -- 价格精度 (小数位)
    quantity_precision INTEGER,                        -- 数量精度 (小数位)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,    -- 创建时间
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP     -- 最后更新时间
);


-- ============================================================
-- 5. notifications - 通知配置表
-- ============================================================
-- 存储通知渠道配置，支持多通道
-- ============================================================
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,                               -- 通知配置 ID, UUID 格式
    channel_type TEXT NOT NULL,                        -- 渠道类型：'feishu' | 'wechat' | 'telegram'
    webhook_url TEXT NOT NULL,                         -- Webhook URL
    is_active BOOLEAN DEFAULT TRUE,                    -- 是否启用
    notify_on_signal BOOLEAN DEFAULT TRUE,             -- 信号通知开关
    notify_on_order BOOLEAN DEFAULT TRUE,              -- 订单通知开关
    notify_on_error BOOLEAN DEFAULT TRUE,              -- 错误通知开关
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,    -- 创建时间
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP     -- 最后更新时间
);


-- ============================================================
-- 6. config_snapshots - 配置快照表
-- ============================================================
-- 存储配置快照，支持一键回滚
-- ============================================================
CREATE TABLE IF NOT EXISTS config_snapshots (
    id TEXT PRIMARY KEY,                               -- 快照 ID, UUID 格式
    name TEXT NOT NULL,                                -- 快照名称
    description TEXT,                                  -- 快照描述
    snapshot_data TEXT NOT NULL,                       -- JSON: 完整配置快照数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,    -- 创建时间
    created_by TEXT,                                   -- 创建者 (用户名/系统)
    is_auto BOOLEAN DEFAULT FALSE                      -- 是否自动快照
);

-- 索引：按创建时间倒序查询
CREATE INDEX IF NOT EXISTS idx_snapshots_created ON config_snapshots(created_at DESC);


-- ============================================================
-- 7. config_history - 配置历史表
-- ============================================================
-- 记录所有配置变更历史，支持审计追溯
-- ============================================================
CREATE TABLE IF NOT EXISTS config_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,              -- 自增 ID
    entity_type TEXT NOT NULL,                         -- 实体类型：'strategy' | 'risk_config' | 'system_config' | ...
    entity_id TEXT NOT NULL,                           -- 实体 ID
    action TEXT NOT NULL,                              -- 操作类型：'CREATE' | 'UPDATE' | 'DELETE'
    old_values TEXT,                                   -- JSON: 旧值 (UPDATE 时)
    new_values TEXT,                                   -- JSON: 新值 (UPDATE 时)
    changed_by TEXT,                                   -- 变更者 (用户名/系统)
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,    -- 变更时间
    change_summary TEXT                                -- 变更摘要 (人类可读)
);

-- 索引：按实体查询历史
CREATE INDEX IF NOT EXISTS idx_history_entity ON config_history(entity_type, entity_id);
-- 索引：按时间倒序查询
CREATE INDEX IF NOT EXISTS idx_history_time ON config_history(changed_at DESC);


-- ============================================================
-- 8. exchange_configs - 交易所连接配置表
-- ============================================================
-- 存储交易所连接凭证（单例模式，id='primary'）
-- 设计原则：与 system_configs/risk_configs 一致的单例模式
-- ============================================================
CREATE TABLE IF NOT EXISTS exchange_configs (
    id TEXT PRIMARY KEY DEFAULT 'primary',              -- 固定为'primary'（支持未来多交易所）
    exchange_name TEXT NOT NULL DEFAULT 'binance',       -- CCXT 交易所 ID (binance/bybit/okx)
    api_key TEXT NOT NULL,                               -- API Key
    api_secret TEXT NOT NULL,                            -- API Secret
    testnet BOOLEAN DEFAULT TRUE,                        -- 是否使用测试网
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1                            -- 乐观锁版本号
);

CREATE INDEX IF NOT EXISTS idx_exchange_configs_updated ON exchange_configs(updated_at);


-- ============================================================
-- 9. migration_metadata - 迁移状态追踪表
-- ============================================================
CREATE TABLE IF NOT EXISTS migration_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 初始状态
INSERT OR IGNORE INTO migration_metadata (key, value) VALUES ('yaml_fully_migrated', 'false');
INSERT OR IGNORE INTO migration_metadata (key, value) VALUES ('one_time_import_done', 'false');
INSERT OR IGNORE INTO migration_metadata (key, value) VALUES ('import_version', 'v1');
