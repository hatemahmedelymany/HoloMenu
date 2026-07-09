"""add payments table

Revision ID: 0005_add_payments
Revises: 0004_add_audit_logs
Create Date: 2026-07-09

Phase 5:
  - Create payments table for recording order payment transactions
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_add_payments"
down_revision = "0004_add_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE payments (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            tenant_id CHAR(36) NOT NULL,
            order_id INT NOT NULL,
            payment_method VARCHAR(32) NOT NULL,
            amount_tendered DECIMAL(10,2) NULL,
            amount_paid DECIMAL(10,2) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT,
            FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE RESTRICT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    op.execute("CREATE INDEX idx_payments_tenant ON payments (tenant_id)")
    op.execute("CREATE INDEX idx_payments_order ON payments (order_id)")


def downgrade() -> None:
    op.execute("DROP INDEX idx_payments_order ON payments")
    op.execute("DROP INDEX idx_payments_tenant ON payments")
    op.execute("DROP TABLE payments")
