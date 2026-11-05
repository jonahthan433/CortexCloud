"""Wallet-linked monthly prepaid subscriptions and weighted credits.

Revision ID: c8d9e0f1a2b3
Revises: f6a7b8c9d0e1
"""
from alembic import op
import sqlalchemy as sa

revision = "c8d9e0f1a2b3"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wallet_subscriptions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("wallet_address", sa.String(64), nullable=False),
        sa.Column("plan_id", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("credits_granted", sa.Integer(), nullable=False),
        sa.Column("credits_remaining", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("wallet_address", name="uq_wallet_subscriptions_wallet_address"),
    )
    op.create_index("ix_wallet_subscriptions_wallet_address", "wallet_subscriptions", ["wallet_address"])

    op.create_table(
        "wallet_api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("wallet_address", sa.String(64), nullable=False),
        sa.Column("name", sa.String(64), nullable=False, server_default="subscription"),
        sa.Column("prefix", sa.String(32), nullable=False),
        sa.Column("hashed_key", sa.String(64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("hashed_key", name="uq_wallet_api_keys_hashed_key"),
    )
    op.create_index("ix_wallet_api_keys_wallet_address", "wallet_api_keys", ["wallet_address"])
    op.create_index("ix_wallet_api_keys_hashed_key", "wallet_api_keys", ["hashed_key"])

    op.create_table(
        "wallet_credit_transactions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("wallet_address", sa.String(64), nullable=False),
        sa.Column("amount_credits", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("endpoint", sa.String(128), nullable=True),
        sa.Column("payment_nonce", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("payment_nonce", name="uq_wallet_credit_transactions_payment_nonce"),
    )
    op.create_index("ix_wallet_credit_transactions_wallet_address", "wallet_credit_transactions", ["wallet_address"])
    op.create_index("ix_wallet_credit_transactions_created_at", "wallet_credit_transactions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_wallet_credit_transactions_created_at", table_name="wallet_credit_transactions")
    op.drop_index("ix_wallet_credit_transactions_wallet_address", table_name="wallet_credit_transactions")
    op.drop_table("wallet_credit_transactions")
    op.drop_index("ix_wallet_api_keys_hashed_key", table_name="wallet_api_keys")
    op.drop_index("ix_wallet_api_keys_wallet_address", table_name="wallet_api_keys")
    op.drop_table("wallet_api_keys")
    op.drop_index("ix_wallet_subscriptions_wallet_address", table_name="wallet_subscriptions")
    op.drop_table("wallet_subscriptions")
