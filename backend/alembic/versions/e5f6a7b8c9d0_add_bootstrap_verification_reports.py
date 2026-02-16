"""add bootstrap_verification_reports table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-02-16 22:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bootstrap_verification_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("function_name", sa.String(100), nullable=False),
        sa.Column("nta_page_name", sa.String(100), nullable=False),
        sa.Column(
            "nta_snapshot_id",
            sa.Integer(),
            sa.ForeignKey("nta_page_snapshots.id"),
            nullable=False,
        ),
        sa.Column(
            "verification_status",
            sa.String(20),
            server_default="MATCH",
            nullable=False,
        ),
        sa.Column("details", JSONB(), nullable=False),
        sa.Column("confidence_score", sa.Numeric(3, 2), nullable=False),
        sa.Column("llm_extracted_rules", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bootstrap_verification_function",
        "bootstrap_verification_reports",
        ["function_name"],
    )
    op.create_index(
        "ix_bootstrap_verification_snapshot",
        "bootstrap_verification_reports",
        ["nta_snapshot_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bootstrap_verification_snapshot",
        table_name="bootstrap_verification_reports",
    )
    op.drop_index(
        "ix_bootstrap_verification_function",
        table_name="bootstrap_verification_reports",
    )
    op.drop_table("bootstrap_verification_reports")
