"""创建 backtest_reports 表

Revision ID: 005
Revises: 004
Create Date: 2026-05-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 backtest_reports 表 (符合 3NF 设计)"""

    op.create_table(
        'backtest_reports',
        # 主键
        sa.Column('id', sa.String(64), nullable=False),

        # 策略标识
        sa.Column('strategy_id', sa.String(64), nullable=False),
        sa.Column('strategy_name', sa.String(128), nullable=False),
        sa.Column('strategy_version', sa.String(16), nullable=False, server_default="'1.0.0'"),

        # 策略快照字段 (符合 3NF 设计)
        sa.Column('strategy_snapshot', sa.Text(), nullable=False),
        sa.Column('parameters_hash', sa.String(64), nullable=False),

        # 基础信息
        sa.Column('symbol', sa.String(32), nullable=False),
        sa.Column('timeframe', sa.String(16), nullable=False),

        # 时间范围
        sa.Column('backtest_start', sa.Integer(), nullable=False),
        sa.Column('backtest_end', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.Integer(), nullable=False),

        # 核心指标 (使用 String 存储 Decimal)
        sa.Column('initial_balance', sa.String(), nullable=False),
        sa.Column('final_balance', sa.String(), nullable=False),
        sa.Column('total_return', sa.String(), nullable=False),
        sa.Column('total_trades', sa.Integer(), nullable=False),
        sa.Column('winning_trades', sa.Integer(), nullable=False),
        sa.Column('losing_trades', sa.Integer(), nullable=False),
        sa.Column('win_rate', sa.String(), nullable=False),
        sa.Column('total_pnl', sa.String(), nullable=False),
        sa.Column('total_fees_paid', sa.String(), nullable=False, server_default="'0'"),
        sa.Column('total_slippage_cost', sa.String(), nullable=False, server_default="'0'"),
        sa.Column('max_drawdown', sa.String(), nullable=False),

        # 详细数据 (JSON 存储)
        sa.Column('positions_summary', sa.Text(), nullable=True),
        sa.Column('monthly_returns', sa.Text(), nullable=True),

        # 约束
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['strategy_id'],
            ['signals.id'],
            ondelete='CASCADE'
        ),
    )

    # 创建索引
    op.create_index(
        'idx_backtest_reports_strategy_id',
        'backtest_reports',
        ['strategy_id'],
        unique=False
    )

    op.create_index(
        'idx_backtest_reports_symbol',
        'backtest_reports',
        ['symbol'],
        unique=False
    )

    op.create_index(
        'idx_backtest_reports_parameters_hash',
        'backtest_reports',
        ['parameters_hash'],
        unique=False
    )

    op.create_index(
        'idx_backtest_reports_created_at',
        'backtest_reports',
        ['created_at'],
        unique=False
    )


def downgrade() -> None:
    """删除 backtest_reports 表"""
    # 删除索引
    op.drop_index('idx_backtest_reports_created_at', table_name='backtest_reports')
    op.drop_index('idx_backtest_reports_parameters_hash', table_name='backtest_reports')
    op.drop_index('idx_backtest_reports_symbol', table_name='backtest_reports')
    op.drop_index('idx_backtest_reports_strategy_id', table_name='backtest_reports')

    # 删除表
    op.drop_table('backtest_reports')
