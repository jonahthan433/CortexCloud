"""payment attribution: referer + user_agent on x402_payments

Revision ID: f6a7b8c9d0e1
Revises: d4e5f6a7b8c9
Create Date: 2026-10-12

Discovery attribution for settled x402 payments: who sent the buyer
(referer) and with what client (user-agent). Both nullable so existing
rows and API-only clients keep working.
"""
import sqlalchemy as sa
from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("x402_payments", sa.Column("referer", sa.String(555), nullable=True))
    op.add_column("x402_payments", sa.Column("user_agent", sa.String(555), nullable=True))


def downgrade() -> None:
    op.drop_column("x402_payments", "referer")
    op.drop_column("x402_payments", "user_agent")
