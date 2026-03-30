"""创建 signals 和 accounts 表

Revision ID: 003
Revises: 002
Create Date: 2026-05-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 signals 和 accounts 表"""

    # ===== 创建 signals 表 =====
    op.create_table(
        'signals',
        sa.Column('id', sa.String(64), nullable=False),
        sa.Column('strategy_id', sa.String(64), nullable=False),
        sa.Column('symbol', sa.String(32), nullable=False),
        sa.Column('direction', sa.String(16), nullable=False),
        sa.Column('timestamp', sa.Integer(), nullable=False),
        sa.Column('expected_entry', sa.String(32), nullable=False),
        sa.Column('expected_sl', sa.String(32), nullable=False),
        sa.Column('pattern_score', sa.Float(), nullable=False),
        sa.Column('is_active', sa.Integer(), nullable=False, server_default="1"),
        sa.Column('created_at', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("direction IN ('LONG', 'SHORT')", name='check_signals_direction'),
        sa.CheckConstraint("pattern_score >= 0.0 AND pattern_score <= 1.0", name='check_pattern_score_range'),
    )

    # signals 表索引
    op.create_index('idx_signals_symbol', 'signals', ['symbol'], unique=False)
    op.create_index('idx_signals_timestamp', 'signals', ['timestamp'], unique=False)
    op.create_index('idx_signals_strategy', 'signals', ['strategy_id'], unique=False)
    op.create_index('idx_signals_is_active', 'signals', ['is_active'], unique=False)

    # ===== 创建 accounts 表 =====
    op.create_table(
        'accounts',
        sa.Column('account_id', sa.String(64), nullable=False),
        sa.Column('total_balance', sa.String(32), nullable=False, server_default="'0'"),
        sa.Column('frozen_margin', sa.String(32), nullable=False, server_default="'0'"),
        sa.Column('created_at', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('account_id'),
    )

    # accounts 表默认记录初始化
    # 注意：SQLite 中无法在迁移中安全地执行 INSERT OR IGNORE
    # 应用层应在首次启动时初始化默认账户


def downgrade() -> None:
    """删除 signals 和 accounts 表"""
    # 删除 accounts 表
    op.drop_table('accounts')

    # 删除 signals 表索引
    op.drop_index('idx_signals_is_active', table_name='signals')
    op.drop_index('idx_signals_strategy', table_name='signals')
    op.drop_index('idx_signals_timestamp', table_name='signals')
    op.drop_index('idx_signals_symbol', table_name='signals')

    # 删除 signals 表
    op.drop_table('signals')
