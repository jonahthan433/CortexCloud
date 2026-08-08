"""optimization network: jobs, executions, payments, benchmarks, nonces

Revision ID: a1b2c3d4e5f6
Revises: cb172c9fe635
Create Date: 2026-08-08

Creates the five tables the Optimization Network keeps in PostgreSQL.
Legacy tables (models/organizations/users/api_keys/billing_accounts/
usage_logs) are left untouched — the Node gateway shares this database.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "a1b2c3d4e5f6"
down_revision = "cb172c9fe635"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opt_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("problem_type", sa.String(16), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False, server_default="auto"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("request", JSONB(), nullable=True),
        sa.Column("result", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("price_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("backend", sa.String(64), nullable=True),
        sa.Column("algorithm", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_opt_jobs_status", "opt_jobs", ["status"])
    op.create_index("ix_opt_jobs_created_at", "opt_jobs", ["created_at"])

    op.create_table(
        "opt_executions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("opt_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("solver_id", sa.String(64), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("runtime_ms", sa.Integer(), nullable=True),
        sa.Column("objective", sa.Float(), nullable=True),
        sa.Column("quality_note", sa.String(255), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("meta", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_opt_executions_job_id", "opt_executions", ["job_id"])

    op.create_table(
        "x402_payments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("endpoint", sa.String(128), nullable=False),
        sa.Column("payer", sa.String(64), nullable=False),
        sa.Column("amount_atomic", sa.BigInteger(), nullable=False),
        sa.Column("amount_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("mode", sa.String(16), nullable=True),
        sa.Column("n_vars", sa.Integer(), nullable=True),
        sa.Column("nonce", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="settled"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_x402_payments_payer", "x402_payments", ["payer"])
    op.create_index("ix_x402_payments_occurred_at", "x402_payments", ["occurred_at"])

    op.create_table(
        "benchmarks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("problem_type", sa.String(16), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("solver_id", sa.String(64), nullable=False),
        sa.Column("runtime_ms", sa.Integer(), nullable=False),
        sa.Column("objective", sa.Float(), nullable=True),
        sa.Column("meta", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_benchmarks_solver_n", "benchmarks", ["solver_id", "n"])

    op.create_table(
        "x402_nonces",
        sa.Column("nonce", sa.String(128), primary_key=True),
        sa.Column("endpoint", sa.String(128), nullable=True),
        sa.Column("valid_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("x402_nonces")
    op.drop_table("benchmarks")
    op.drop_table("x402_payments")
    op.drop_table("opt_executions")
    op.drop_table("opt_jobs")