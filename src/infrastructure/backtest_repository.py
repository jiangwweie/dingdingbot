"""
Backtest Report Repository - SQLite persistence for backtest reports.

实现回测报告的持久化存储，支持：
- 保存回测报告
- 获取报告详情
- 获取策略历史报告列表
- 获取相同参数组合的历史报告（用于自动调参分析）
- 删除报告
"""
import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any

import aiosqlite

from src.domain.models import PMSBacktestReport, PositionSummary, Direction
from src.domain.models import StrategyDefinition
from src.infrastructure.logger import setup_logger

logger = setup_logger(__name__)


class BacktestReportRepository:
    """
    SQLite repository for persisting backtest reports.

    设计目标:
    - 支持回测报告的历史追踪
    - 支持基于参数哈希的聚类分析（自动调参）
    - 策略快照序列化存储
    """

    def __init__(
        self,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        """
        Initialize BacktestReportRepository.

        Args:
            db_path: Path to SQLite database file
            connection: Optional injected connection (if None, creates own connection)
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = connection
        self._owns_connection = connection is None
        logger.info(f"回测报告仓库初始化完成：{db_path}")

    async def initialize(self) -> None:
        """
        Initialize database connection and create tables.
        Also creates the data/ directory if it doesn't exist.
        """
        # Create connection if not injected
        if self._owns_connection and self._db is None:
            # Create data directory if not exists
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            # Open database connection
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row

            # Enable WAL mode for high concurrency write support
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA synchronous=NORMAL")
            await self._db.execute("PRAGMA wal_autocheckpoint=1000")
            await self._db.execute("PRAGMA cache_size=-64000")  # 64MB cache

        # Create backtest_reports table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS backtest_reports (
                id                  TEXT PRIMARY KEY,
                strategy_id         TEXT NOT NULL,
                strategy_name       TEXT NOT NULL,
                strategy_version    TEXT NOT NULL DEFAULT '1.0.0',
                strategy_snapshot   TEXT NOT NULL,
                parameters_hash     TEXT NOT NULL,
                symbol              TEXT NOT NULL,
                timeframe           TEXT NOT NULL,
                backtest_start      INTEGER NOT NULL,
                backtest_end        INTEGER NOT NULL,
                created_at          INTEGER NOT NULL,
                initial_balance     TEXT NOT NULL,
                final_balance       TEXT NOT NULL,
                total_return        TEXT NOT NULL,
                total_trades        INTEGER NOT NULL DEFAULT 0,
                winning_trades      INTEGER NOT NULL DEFAULT 0,
                losing_trades       INTEGER NOT NULL DEFAULT 0,
                win_rate            TEXT NOT NULL DEFAULT '0',
                total_pnl           TEXT NOT NULL DEFAULT '0',
                total_fees_paid     TEXT NOT NULL DEFAULT '0',
                total_slippage_cost TEXT NOT NULL DEFAULT '0',
                max_drawdown        TEXT NOT NULL DEFAULT '0',
                sharpe_ratio        TEXT,
                positions_summary   TEXT,
                monthly_returns     TEXT
            )
        """)

        # Create indexes
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_backtest_reports_strategy_id
            ON backtest_reports(strategy_id)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_backtest_reports_symbol
            ON backtest_reports(symbol)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_backtest_reports_timeframe
            ON backtest_reports(timeframe)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_backtest_reports_created_at
            ON backtest_reports(created_at)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_backtest_reports_parameters_hash
            ON backtest_reports(parameters_hash)
        """)

        await self._db.commit()
        logger.info("回测报告表初始化完成")

    async def close(self) -> None:
        """Close database connection (only if self-owned)."""
        if self._db and self._owns_connection:
            await self._db.close()
            self._db = None
            logger.info("回测报告仓库连接已关闭")

    # ============================================================
    # 工具方法
    # ============================================================

    def _serialize_strategy_snapshot(self, strategy_def: StrategyDefinition) -> str:
        """
        将策略配置序列化为 JSON 字符串。

        Args:
            strategy_def: 策略定义

        Returns:
            JSON 字符串
        """
        snapshot = {
            "id": strategy_def.id,
            "name": strategy_def.name,
            "logic_tree": None,
            "triggers": [],
            "filters": [],
        }

        # 序列化 logic_tree（如果存在）
        if strategy_def.logic_tree:
            snapshot["logic_tree"] = self._serialize_logic_tree(strategy_def.logic_tree)

        # 向后兼容：提取 triggers 和 filters
        triggers = strategy_def.get_triggers_from_logic_tree()
        filters = strategy_def.get_filters_from_logic_tree()

        snapshot["triggers"] = [t.model_dump(mode="json") for t in triggers]
        snapshot["filters"] = [f.model_dump(mode="json") for f in filters]

        return json.dumps(snapshot, ensure_ascii=False)

    def _serialize_logic_tree(self, node) -> Dict[str, Any]:
        """
        递归序列化逻辑树节点。

        Args:
            node: LogicNode 或 LeafNode

        Returns:
            Dict 表示
        """
        from src.domain.logic_tree import LogicNode, TriggerLeaf, FilterLeaf

        if isinstance(node, LogicNode):
            return {
                "type": "node",
                "gate": node.gate,
                "children": [self._serialize_logic_tree(child) for child in node.children]
            }
        elif isinstance(node, TriggerLeaf):
            return {
                "type": "trigger",
                "id": node.id,
                "config": node.config.model_dump(mode="json")
            }
        elif isinstance(node, FilterLeaf):
            return {
                "type": "filter",
                "id": node.id,
                "config": node.config.model_dump(mode="json")
            }
        else:
            return {}

    def _calculate_parameters_hash(self, strategy_snapshot: str, symbol: str, timeframe: str) -> str:
        """
        计算参数组合的 SHA256 哈希。

        用于聚类分析：相同参数组合的不同回测结果可以通过哈希值快速查找。

        Args:
            strategy_snapshot: 策略快照 JSON 字符串
            symbol: 交易对
            timeframe: 时间周期

        Returns:
            SHA256 哈希字符串（64 字符）
        """
        content = f"{strategy_snapshot}:{symbol}:{timeframe}"
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def _decimal_to_str(self, value: Decimal) -> str:
        """将 Decimal 转换为字符串用于存储

        使用 normalize() 确保 0 显示为 '0.0' 而不是 '0'，
        以避免 SQLite CHECK 约束比较问题。
        """
        normalized = value.normalize()
        # 确保小数点存在，避免 SQLite 字符串比较问题
        result = str(normalized)
        if '.' not in result and 'E' not in result.upper():
            result += '.0'
        return result

    def _str_to_decimal(self, value: Optional[str]) -> Optional[Decimal]:
        """将字符串转换为 Decimal"""
        if value is None:
            return None
        return Decimal(value)

    def _serialize_positions_summary(self, positions: List[PositionSummary]) -> str:
        """
        将仓位摘要列表序列化为 JSON 字符串。

        Args:
            positions: 仓位摘要列表

        Returns:
            JSON 字符串
        """
        data = []
        for pos in positions:
            data.append({
                "position_id": pos.position_id,
                "signal_id": pos.signal_id,
                "symbol": pos.symbol,
                "direction": pos.direction.value,
                "entry_price": self._decimal_to_str(pos.entry_price),
                "exit_price": self._decimal_to_str(pos.exit_price) if pos.exit_price else None,
                "entry_time": pos.entry_time,
                "exit_time": pos.exit_time,
                "realized_pnl": self._decimal_to_str(pos.realized_pnl),
                "exit_reason": pos.exit_reason,
            })
        return json.dumps(data, ensure_ascii=False)

    def _deserialize_positions_summary(self, json_str: Optional[str]) -> List[PositionSummary]:
        """
        将 JSON 字符串反序列化为仓位摘要列表。

        Args:
            json_str: JSON 字符串

        Returns:
            仓位摘要列表
        """
        if not json_str:
            return []

        data = json.loads(json_str)
        positions = []
        for item in data:
            positions.append(PositionSummary(
                position_id=item["position_id"],
                signal_id=item["signal_id"],
                symbol=item["symbol"],
                direction=Direction(item["direction"]),
                entry_price=self._str_to_decimal(item["entry_price"]),
                exit_price=self._str_to_decimal(item.get("exit_price")),
                entry_time=item["entry_time"],
                exit_time=item.get("exit_time"),
                realized_pnl=self._str_to_decimal(item["realized_pnl"]),
                exit_reason=item.get("exit_reason"),
            ))
        return positions

    # ============================================================
    # CRUD 接口
    # ============================================================

    async def save_report(
        self,
        report: PMSBacktestReport,
        strategy_snapshot: str,
        symbol: str,
        timeframe: str
    ) -> None:
        """
        保存回测报告。

        Args:
            report: PMSBacktestReport 实例
            strategy_snapshot: 策略快照 JSON 字符串
            symbol: 交易对
            timeframe: 时间周期

        Raises:
            ValueError: 如果报告数据无效
        """
        if not report.strategy_id:
            raise ValueError("strategy_id 不能为空")

        # 计算参数哈希
        parameters_hash = self._calculate_parameters_hash(
            strategy_snapshot,
            symbol,
            timeframe
        )

        # 生成报告 ID
        report_id = f"rpt_{report.strategy_id}_{report.backtest_start}_{parameters_hash[:8]}"

        # 序列化 positions_summary
        positions_summary = self._serialize_positions_summary(report.positions) if report.positions else None

        # 插入数据库
        await self._db.execute("""
            INSERT INTO backtest_reports (
                id, strategy_id, strategy_name, strategy_version,
                strategy_snapshot, parameters_hash, symbol, timeframe,
                backtest_start, backtest_end, created_at,
                initial_balance, final_balance, total_return,
                total_trades, winning_trades, losing_trades, win_rate,
                total_pnl, total_fees_paid, total_slippage_cost, max_drawdown,
                sharpe_ratio, positions_summary, monthly_returns
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            report_id,
            report.strategy_id,
            report.strategy_name,
            "1.0.0",  # strategy_version
            strategy_snapshot,
            parameters_hash,
            symbol,
            timeframe,
            report.backtest_start,
            report.backtest_end,
            int(datetime.now(timezone.utc).timestamp() * 1000),
            self._decimal_to_str(report.initial_balance),
            self._decimal_to_str(report.final_balance),
            self._decimal_to_str(report.total_return),
            report.total_trades,
            report.winning_trades,
            report.losing_trades,
            self._decimal_to_str(report.win_rate),
            self._decimal_to_str(report.total_pnl),
            self._decimal_to_str(report.total_fees_paid),
            self._decimal_to_str(report.total_slippage_cost),
            self._decimal_to_str(report.max_drawdown),
            self._decimal_to_str(report.sharpe_ratio) if report.sharpe_ratio else None,
            positions_summary,
            None,  # monthly_returns (暂不使用)
        ))

        await self._db.commit()
        logger.info(f"已保存回测报告：{report_id}")

    async def get_report(self, report_id: str) -> Optional[PMSBacktestReport]:
        """
        获取报告详情。

        Args:
            report_id: 报告 ID

        Returns:
            PMSBacktestReport 实例，如果不存在则返回 None
        """
        cursor = await self._db.execute("""
            SELECT * FROM backtest_reports WHERE id = ?
        """, (report_id,))
        row = await cursor.fetchone()

        if not row:
            return None

        return PMSBacktestReport(
            strategy_id=row["strategy_id"],
            strategy_name=row["strategy_name"],
            backtest_start=row["backtest_start"],
            backtest_end=row["backtest_end"],
            initial_balance=self._str_to_decimal(row["initial_balance"]),
            final_balance=self._str_to_decimal(row["final_balance"]),
            total_return=self._str_to_decimal(row["total_return"]),
            total_trades=row["total_trades"],
            winning_trades=row["winning_trades"],
            losing_trades=row["losing_trades"],
            win_rate=self._str_to_decimal(row["win_rate"]),
            total_pnl=self._str_to_decimal(row["total_pnl"]),
            total_fees_paid=self._str_to_decimal(row["total_fees_paid"]),
            total_slippage_cost=self._str_to_decimal(row["total_slippage_cost"]),
            max_drawdown=self._str_to_decimal(row["max_drawdown"]),
            sharpe_ratio=self._str_to_decimal(row["sharpe_ratio"]) if row["sharpe_ratio"] else None,
            positions=self._deserialize_positions_summary(row["positions_summary"]),
        )

    async def get_reports_by_strategy(
        self,
        strategy_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取策略的历史报告列表（仅返回摘要信息）。

        Args:
            strategy_id: 策略 ID
            limit: 返回数量限制

        Returns:
            报告摘要列表，每项包含：
            - id: 报告 ID
            - strategy_name: 策略名称
            - backtest_start: 回测开始时间
            - backtest_end: 回测结束时间
            - total_return: 总收益率
            - win_rate: 胜率
            - total_pnl: 总盈亏
            - max_drawdown: 最大回撤
        """
        cursor = await self._db.execute("""
            SELECT id, strategy_name, backtest_start, backtest_end,
                   total_return, win_rate, total_pnl, max_drawdown,
                   total_trades, winning_trades, losing_trades
            FROM backtest_reports
            WHERE strategy_id = ?
            ORDER BY backtest_start DESC
            LIMIT ?
        """, (strategy_id, limit))

        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "strategy_name": row["strategy_name"],
                "backtest_start": row["backtest_start"],
                "backtest_end": row["backtest_end"],
                "total_return": self._str_to_decimal(row["total_return"]),
                "win_rate": self._str_to_decimal(row["win_rate"]),
                "total_pnl": self._str_to_decimal(row["total_pnl"]),
                "max_drawdown": self._str_to_decimal(row["max_drawdown"]),
                "total_trades": row["total_trades"],
                "winning_trades": row["winning_trades"],
                "losing_trades": row["losing_trades"],
            }
            for row in rows
        ]

    async def get_reports_by_parameters_hash(
        self,
        parameters_hash: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取相同参数组合的历史报告（用于自动调参分析）。

        Args:
            parameters_hash: 参数组合 SHA256 哈希
            limit: 返回数量限制

        Returns:
            报告摘要列表
        """
        cursor = await self._db.execute("""
            SELECT id, strategy_name, backtest_start, backtest_end,
                   total_return, win_rate, total_pnl, max_drawdown,
                   total_trades, winning_trades, losing_trades
            FROM backtest_reports
            WHERE parameters_hash = ?
            ORDER BY backtest_start DESC
            LIMIT ?
        """, (parameters_hash, limit))

        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "strategy_name": row["strategy_name"],
                "backtest_start": row["backtest_start"],
                "backtest_end": row["backtest_end"],
                "total_return": self._str_to_decimal(row["total_return"]),
                "win_rate": self._str_to_decimal(row["win_rate"]),
                "total_pnl": self._str_to_decimal(row["total_pnl"]),
                "max_drawdown": self._str_to_decimal(row["max_drawdown"]),
                "total_trades": row["total_trades"],
                "winning_trades": row["winning_trades"],
                "losing_trades": row["losing_trades"],
            }
            for row in rows
        ]

    async def delete_report(self, report_id: str) -> None:
        """
        删除报告。

        Args:
            report_id: 报告 ID
        """
        await self._db.execute("""
            DELETE FROM backtest_reports WHERE id = ?
        """, (report_id,))
        await self._db.commit()
        logger.info(f"已删除回测报告：{report_id}")

    async def get_report_snapshot(self, report_id: str) -> Optional[str]:
        """
        获取报告关联的策略快照。

        Args:
            report_id: 报告 ID

        Returns:
            策略快照 JSON 字符串，如果报告不存在则返回 None
        """
        cursor = await self._db.execute("""
            SELECT strategy_snapshot FROM backtest_reports WHERE id = ?
        """, (report_id,))
        row = await cursor.fetchone()

        if not row:
            return None

        return row["strategy_snapshot"]

    async def list_reports(
        self,
        strategy_id: Optional[str] = None,
        symbol: Optional[str] = None,
        start_date: Optional[int] = None,
        end_date: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = 'created_at',
        sort_order: str = 'desc'
    ) -> Dict[str, Any]:
        """
        获取回测报告列表（支持筛选、排序、分页）。

        Args:
            strategy_id: 策略 ID 筛选
            symbol: 交易对筛选
            start_date: 开始时间戳（毫秒）
            end_date: 结束时间戳（毫秒）
            page: 页码（从 1 开始）
            page_size: 每页数量
            sort_by: 排序字段 ('total_return' | 'win_rate' | 'created_at')
            sort_order: 排序方向 ('asc' | 'desc')

        Returns:
            {
                "reports": List[BacktestReportSummary],
                "total": int,
                "page": int,
                "pageSize": int
            }
        """
        # 构建 WHERE 子句
        conditions = []
        params = []

        if strategy_id:
            conditions.append("strategy_id = ?")
            params.append(strategy_id)

        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)

        if start_date:
            conditions.append("backtest_start >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("backtest_start <= ?")
            params.append(end_date)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        # 排序字段映射
        sort_column_map = {
            'total_return': 'CAST(REPLACE(total_return, ",", ".") AS REAL)',
            'win_rate': 'CAST(REPLACE(win_rate, ",", ".") AS REAL)',
            'created_at': 'created_at'
        }
        sort_column = sort_column_map.get(sort_by, 'created_at')
        sort_direction = 'ASC' if sort_order.lower() == 'asc' else 'DESC'

        # 计算总数
        count_query = f"""
            SELECT COUNT(*) FROM backtest_reports {where_clause}
        """
        cursor = await self._db.execute(count_query, params)
        total_row = await cursor.fetchone()
        total = total_row[0] if total_row else 0

        # 计算分页
        offset = (page - 1) * page_size

        # 获取数据 - 使用 COALESCE 确保 sharpe_ratio 列不存在时返回 NULL
        query = f"""
            SELECT id, strategy_id, strategy_name, strategy_version,
                   symbol, timeframe, backtest_start, backtest_end,
                   created_at, total_return, total_trades, win_rate,
                   total_pnl, max_drawdown,
                   COALESCE(sharpe_ratio, NULL) as sharpe_ratio
            FROM backtest_reports
            {where_clause}
            ORDER BY {sort_column} {sort_direction}
            LIMIT ? OFFSET ?
        """
        params.extend([page_size, offset])

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()

        reports = [
            {
                "id": row["id"],
                "strategy_id": row["strategy_id"],
                "strategy_name": row["strategy_name"],
                "strategy_version": row["strategy_version"],
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "backtest_start": row["backtest_start"],
                "backtest_end": row["backtest_end"],
                "created_at": row["created_at"],
                "total_return": str(self._str_to_decimal(row["total_return"])),
                "total_trades": row["total_trades"],
                "win_rate": str(self._str_to_decimal(row["win_rate"])),
                "total_pnl": str(self._str_to_decimal(row["total_pnl"])),
                "max_drawdown": str(self._str_to_decimal(row["max_drawdown"])),
                "sharpe_ratio": str(self._str_to_decimal(row["sharpe_ratio"])) if row["sharpe_ratio"] else None,
            }
            for row in rows
        ]

        return {
            "reports": reports,
            "total": total,
            "page": page,
            "pageSize": page_size
        }
