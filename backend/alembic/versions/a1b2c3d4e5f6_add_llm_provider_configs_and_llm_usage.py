"""add llm_provider_configs and llm_usage_logs tables

Revision ID: a1b2c3d4e5f6
Revises: d797ea65ae2f
Create Date: 2026-02-16 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "d797ea65ae2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add LLM provider configuration and usage tracking tables."""
    op.create_table(
        "llm_provider_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("encrypted_api_token", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("monthly_budget_usd", sa.Numeric(precision=10, scale=2), nullable=False, server_default="50.00"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_provider_configs_provider_active", "llm_provider_configs", ["provider", "is_active"])

    op.create_table(
        "llm_usage_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("evolution_run_id", sa.Integer(), nullable=True),
        sa.Column("caller", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_usage_logs_created_at", "llm_usage_logs", ["created_at"])
    op.create_index("ix_llm_usage_logs_evolution_run_id", "llm_usage_logs", ["evolution_run_id"])


def downgrade() -> None:
    """Remove LLM tables."""
    op.drop_index("ix_llm_usage_logs_evolution_run_id", table_name="llm_usage_logs")
    op.drop_index("ix_llm_usage_logs_created_at", table_name="llm_usage_logs")
    op.drop_table("llm_usage_logs")
    op.drop_index("ix_llm_provider_configs_provider_active", table_name="llm_provider_configs")
    op.drop_table("llm_provider_configs")
