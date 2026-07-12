"""billing_and_grace_periods
Revision ID: e9da907f59d5
Revises: 8ea502d6b2c0
Create Date: 2026-07-12 18:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'e9da907f59d5'
down_revision: Union[str, Sequence[str], None] = '8ea502d6b2c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add grace_period_ends_at to tenants
    op.add_column('tenants', sa.Column('grace_period_ends_at', sa.DateTime(), nullable=True))

    # 2. Create stripe_processed_events table
    op.create_table(
        'stripe_processed_events',
        sa.Column('event_id', sa.String(length=255), primary_key=True, nullable=False),
        sa.Column('processed_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False)
    )


def downgrade() -> None:
    op.drop_table('stripe_processed_events')
    op.drop_column('tenants', 'grace_period_ends_at')
