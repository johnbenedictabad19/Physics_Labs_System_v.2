"""backfill class_member null enrollment_status and is_archived

Revision ID: f1a2b3c4d5e6
Revises: 22fe0b2562a1
Create Date: 2026-05-25 00:00:00.000000

"""
from alembic import op

revision = 'f1a2b3c4d5e6'
down_revision = '22fe0b2562a1'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE class_members
        SET enrollment_status = 'approved'
        WHERE enrollment_status IS NULL
    """)
    op.execute("""
        UPDATE class_members
        SET is_archived = false
        WHERE is_archived IS NULL
    """)


def downgrade():
    pass
