"""Make chat session user_id nullable

Revision ID: 91d3f0b2a417
Revises: 34d232deceae
Create Date: 2026-10-31
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "91d3f0b2a417"
down_revision: str | None = "34d232deceae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "chat_sessions",
        "user_id",
        existing_type=sa.UUID(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "chat_sessions",
        "user_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
