"""统一 Direction 枚举为大写

Revision ID: 001
Revises:
Create Date: 2026-05-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    升级：将 direction 字段统一为大写

    影响表:
    - signals
    - signal_attempts

    注意：对于新数据库（表不存在），跳过数据转换步骤。
    """
    # SQLite 不支援 ALTER TABLE ... CHECK CONSTRAINT
    # 所以需要分步骤处理

    # 1. 检查表是否存在，只更新存在的表
    from alembic import op
    from sqlalchemy import Inspector

    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    # 更新 signals 表（如果存在）
    if 'signals' in tables:
        op.execute("UPDATE signals SET direction = UPPER(direction) WHERE direction IN ('long', 'short')")

    # 更新 signal_attempts 表（如果存在）
    if 'signal_attempts' in tables:
        op.execute("UPDATE signal_attempts SET direction = UPPER(direction) WHERE direction IN ('long', 'short')")

    # SQLite：添加 CHECK 约束需要重建表
    # 这里先不添加约束，等 Phase 1 新表创建时再添加


def downgrade() -> None:
    """
    降级：恢复为小写

    注意：这会破坏数据一致性，仅用于开发环境回滚
    """
    op.execute("UPDATE signals SET direction = LOWER(direction)")
    op.execute("UPDATE signal_attempts SET direction = LOWER(direction)")
