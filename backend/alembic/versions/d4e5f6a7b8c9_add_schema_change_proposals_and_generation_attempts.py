"""add schema_change_proposals and generation_attempts tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-02-16 20:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create schema_change_proposals table
    op.create_table(
        "schema_change_proposals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "evolution_run_id",
            sa.Integer(),
            sa.ForeignKey("evolution_runs.id"),
            nullable=False,
        ),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("proposal_data", JSONB(), nullable=False),
        sa.Column("status", sa.String(20), server_default="PENDING", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_schema_change_proposals_evolution_run_id",
        "schema_change_proposals",
        ["evolution_run_id"],
    )
    op.create_index(
        "ix_schema_change_proposals_year",
        "schema_change_proposals",
        ["year"],
    )

    # Create generation_attempts table
    op.create_table(
        "generation_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "evolution_run_id",
            sa.Integer(),
            sa.ForeignKey("evolution_runs.id"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("generated_code", sa.Text(), nullable=False),
        sa.Column("generated_schema", JSONB(), nullable=True),
        sa.Column("validation_passed", sa.Boolean(), nullable=False),
        sa.Column("validation_errors", JSONB(), nullable=True),
        sa.Column("admin_hints", sa.Text(), nullable=True),
        sa.Column("llm_cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_generation_attempts_evolution_run_id",
        "generation_attempts",
        ["evolution_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_generation_attempts_evolution_run_id",
        table_name="generation_attempts",
    )
    op.drop_table("generation_attempts")

    op.drop_index(
        "ix_schema_change_proposals_year",
        table_name="schema_change_proposals",
    )
    op.drop_index(
        "ix_schema_change_proposals_evolution_run_id",
        table_name="schema_change_proposals",
    )
    op.drop_table("schema_change_proposals")
