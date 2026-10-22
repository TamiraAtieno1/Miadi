"""allow the rescheduled status to hold a slot

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_ACTIVE = sa.text("status = 'booked'")
NEW_ACTIVE = sa.text("status IN ('booked', 'rescheduled')")


def _recreate_slot_index(active: sa.TextClause) -> None:
    """Replace the partial unique index so it covers the given set of statuses."""
    op.drop_index("uq_active_slot", table_name="appointments")
    op.create_index(
        "uq_active_slot",
        "appointments",
        ["doctor_id", "start_time"],
        unique=True,
        postgresql_where=active,
        sqlite_where=active,
    )


def upgrade() -> None:
    # A rescheduled appointment still holds its slot, so the index must cover it too.
    _recreate_slot_index(NEW_ACTIVE)


def downgrade() -> None:
    # The old schema only knows `booked`; a moved appointment is simply booked again.
    op.execute("UPDATE appointments SET status = 'booked' WHERE status = 'rescheduled'")
    _recreate_slot_index(OLD_ACTIVE)
