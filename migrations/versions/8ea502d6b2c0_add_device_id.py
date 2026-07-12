"""add_device_id
Revision ID: 8ea502d6b2c0
Revises: 957c1834dc0d
Create Date: 2026-07-12 16:35:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '8ea502d6b2c0'
down_revision: Union[str, Sequence[str], None] = '957c1834dc0d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add device_id as nullable columns
    op.add_column('kiosks', sa.Column('device_id', sa.String(length=255), nullable=True))
    op.add_column('websocket_sessions', sa.Column('device_id', sa.String(length=255), nullable=True))

    # 2. Backfill existing records with placeholders
    op.execute("UPDATE kiosks SET device_id = CONCAT('legacy-', id) WHERE device_id IS NULL")
    op.execute("UPDATE websocket_sessions SET device_id = 'legacy-session' WHERE device_id IS NULL")

    # 3. Alter columns to NOT NULL
    op.alter_column('kiosks', 'device_id', nullable=False, existing_type=sa.String(length=255))
    op.alter_column('websocket_sessions', 'device_id', nullable=False, existing_type=sa.String(length=255))


def downgrade() -> None:
    op.drop_column('websocket_sessions', 'device_id')
    op.drop_column('kiosks', 'device_id')
