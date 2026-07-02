-- ============================================================
-- Migration 004: Create order_audit_logs table
-- Date: 2026-04-06
-- Description: 订单审计日志表 - 记录订单全生命周期事件
-- ============================================================
-- 与 ORD-1 状态机对齐：
-- - 事件类型与 OrderStatus 枚举值一致
-- - triggered_by 来源：USER / SYSTEM / EXCHANGE
-- - 支持异步队列写入
-- ============================================================

-- 审计日志表
CREATE TABLE IF NOT EXISTS order_audit_logs (
    id              TEXT PRIMARY KEY,                     -- 审计日志 ID, UUID 格式
    order_id        TEXT NOT NULL,                        -- 订单 ID (外键)
    signal_id       TEXT,                                 -- 关联信号 ID (可选，用于追踪订单链)
    old_status      TEXT,                                 -- 旧状态 (可为 NULL，首次创建时无旧状态)
    new_status      TEXT NOT NULL,                        -- 新状态
    event_type      TEXT NOT NULL,                        -- 事件类型 (见下方枚举)
    triggered_by    TEXT NOT NULL,                        -- 触发来源：USER | SYSTEM | EXCHANGE
    metadata        TEXT,                                 -- JSON 格式元数据
    created_at      INTEGER NOT NULL,                     -- 毫秒时间戳

    -- 外键约束
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
);

-- 索引优化
CREATE INDEX IF NOT EXISTS idx_order_audit_logs_order_id ON order_audit_logs(order_id);
CREATE INDEX IF NOT EXISTS idx_order_audit_logs_signal_id ON order_audit_logs(signal_id);
CREATE INDEX IF NOT EXISTS idx_order_audit_logs_created_at ON order_audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_audit_logs_event_type ON order_audit_logs(event_type);

-- ============================================================
-- 附录：事件类型枚举 (与 ORD-1 状态机对齐)
-- ============================================================
-- ORDER_CREATED        | NULL              | CREATED
-- ORDER_SUBMITTED      | CREATED           | SUBMITTED
-- ORDER_CONFIRMED      | SUBMITTED         | OPEN
-- ORDER_PARTIAL_FILLED | OPEN              | PARTIALLY_FILLED
-- ORDER_FILLED         | OPEN/PARTIALLY    | FILLED
-- ORDER_CANCELED       | *                 | CANCELED
-- ORDER_REJECTED       | SUBMITTED/OPEN    | REJECTED
-- ORDER_EXPIRED        | OPEN              | EXPIRED
-- ORDER_UPDATED        | *                 | * (信息更新)
-- ============================================================
-- 触发来源枚举
-- USER     | 用户主动操作 (如点击取消按钮)
-- SYSTEM   | 系统自动触发 (如 OCO 逻辑自动撤销)
-- EXCHANGE | 交易所推送 (如 WebSocket 推送成交)
-- ============================================================
