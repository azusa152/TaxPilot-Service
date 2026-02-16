"""make_payment_date_nullable

Revision ID: d797ea65ae2f
Revises: e17fd6056432
Create Date: 2026-02-16 04:32:15.028239

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd797ea65ae2f'
down_revision: Union[str, Sequence[str], None] = 'e17fd6056432'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make payment_date nullable for document ingestion entries."""
    op.alter_column(
        "income_entries",
        "payment_date",
        existing_type=sa.Date(),
        nullable=True,
    )


def downgrade() -> None:
    """Revert payment_date to non-nullable."""
    op.alter_column(
        "income_entries",
        "payment_date",
        existing_type=sa.Date(),
        nullable=False,
    )
