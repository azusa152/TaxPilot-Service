"""add nta_target_pages, nta_page_snapshots, nta_crawler_runs tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-16 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add NTA crawler tables for target pages, snapshots, and crawler runs."""
    op.create_table(
        "nta_target_pages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("check_interval_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "nta_crawler_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pages_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pages_changed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pages_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_nta_crawler_runs_started_at", "nta_crawler_runs", ["started_at"])

    op.create_table(
        "nta_page_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("target_page_id", sa.Integer(), sa.ForeignKey("nta_target_pages.id"), nullable=False),
        sa.Column("crawler_run_id", sa.Integer(), sa.ForeignKey("nta_crawler_runs.id"), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_html", sa.Text(), nullable=True),
        sa.Column("raw_markdown", sa.Text(), nullable=True),
        sa.Column("fit_markdown", sa.Text(), nullable=True),
        sa.Column("extracted_tables", JSONB(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="SUCCESS"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_nta_snapshots_target_fetched", "nta_page_snapshots", ["target_page_id", "fetched_at"])
    op.create_index("ix_nta_snapshots_content_hash", "nta_page_snapshots", ["content_hash"])


def downgrade() -> None:
    """Remove NTA crawler tables."""
    op.drop_index("ix_nta_snapshots_content_hash", table_name="nta_page_snapshots")
    op.drop_index("ix_nta_snapshots_target_fetched", table_name="nta_page_snapshots")
    op.drop_table("nta_page_snapshots")
    op.drop_index("ix_nta_crawler_runs_started_at", table_name="nta_crawler_runs")
    op.drop_table("nta_crawler_runs")
    op.drop_table("nta_target_pages")
