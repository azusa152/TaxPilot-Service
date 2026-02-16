"""add evolution_runs table and llm_usage_logs FK

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-16 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create evolution_runs table
    op.create_table(
        "evolution_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column(
            "nta_snapshot_id",
            sa.Integer(),
            sa.ForeignKey("nta_page_snapshots.id"),
            nullable=True,
        ),
        sa.Column("parsed_changes", JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evolution_runs_status", "evolution_runs", ["status"])
    op.create_index("ix_evolution_runs_started_at", "evolution_runs", ["started_at"])

    # Add FK from llm_usage_logs.evolution_run_id → evolution_runs.id
    op.create_foreign_key(
        "fk_llm_usage_logs_evolution_run_id",
        "llm_usage_logs",
        "evolution_runs",
        ["evolution_run_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_llm_usage_logs_evolution_run_id", "llm_usage_logs", type_="foreignkey"
    )
    op.drop_index("ix_evolution_runs_started_at", table_name="evolution_runs")
    op.drop_index("ix_evolution_runs_status", table_name="evolution_runs")
    op.drop_table("evolution_runs")
