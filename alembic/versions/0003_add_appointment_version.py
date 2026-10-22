"""add a version column for optimistic concurrency

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A database built straight from the current models (create_all) already has it.
    columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("appointments")}
    if "version" in columns:
        return

    # Existing appointments start at version 1.
    op.add_column(
        "appointments",
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )


def downgrade() -> None:
    op.drop_column("appointments", "version")
