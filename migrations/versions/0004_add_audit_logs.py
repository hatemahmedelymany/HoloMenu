"""add audit logs table

Revision ID: 0004_add_audit_logs
Revises: 0003_auth_and_rbac
Create Date: 2026-07-08

Phase 3:
  - Create audit_logs table
  - Add foreign keys to tenants and admins
  - Add index on (tenant_id, created_at)
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_add_audit_logs"
down_revision = "0003_auth_and_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE audit_logs (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            tenant_id CHAR(36) NOT NULL,
            user_id INT NULL,
            action VARCHAR(64) NOT NULL,
            target_type VARCHAR(64) NOT NULL,
            target_id VARCHAR(64) NULL,
            before_state JSON NULL,
            after_state JSON NULL,
            ip_address VARCHAR(45) NULL,
            user_agent VARCHAR(255) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT,
            FOREIGN KEY (user_id) REFERENCES admins(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    op.execute("CREATE INDEX idx_audit_tenant_time ON audit_logs (tenant_id, created_at)")


def downgrade() -> None:
    op.execute("DROP INDEX idx_audit_tenant_time ON audit_logs")
    op.execute("DROP TABLE audit_logs")
