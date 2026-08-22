"""AI/Research payment ledger columns.

Revision ID: d4e5f6a7b8c9
Revises: b2c3d4e5f6a7
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = {
        r[0]
        for r in bind.execute(
            sa.text(
                "select column_name from information_schema.columns "
                "where table_name='x402_payments'"
            )
        ).fetchall()
    }
    if "provider_cost_usd" not in existing:
        op.add_column(
            "x402_payments",
            sa.Column("provider_cost_usd", sa.Numeric(12, 6), nullable=True),
        )
    if "margin_usd" not in existing:
        op.add_column(
            "x402_payments",
            sa.Column("margin_usd", sa.Numeric(12, 6), nullable=True),
        )
    if "category" not in existing:
        op.add_column(
            "x402_payments",
            sa.Column("category", sa.String(16), nullable=True),
        )
    # Index is cheap to (re)create; guard with a name check.
    idx = bind.execute(
        sa.text(
            "select 1 from pg_indexes where indexname='ix_x402_payments_category'"
        )
    ).fetchone()
    if not idx:
        op.create_index("ix_x402_payments_category", "x402_payments", ["category"])


def downgrade():
    bind = op.get_bind()
    idx = bind.execute(
        sa.text(
            "select 1 from pg_indexes where indexname='ix_x402_payments_category'"
        )
    ).fetchone()
    if idx:
        op.drop_index("ix_x402_payments_category", table_name="x402_payments")
    existing = {
        r[0]
        for r in bind.execute(
            sa.text(
                "select column_name from information_schema.columns "
                "where table_name='x402_payments'"
            )
        ).fetchall()
    }
    if "category" in existing:
        op.drop_column("x402_payments", "category")
    if "margin_usd" in existing:
        op.drop_column("x402_payments", "margin_usd")
    if "provider_cost_usd" in existing:
        op.drop_column("x402_payments", "provider_cost_usd")
