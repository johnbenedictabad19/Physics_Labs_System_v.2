"""add uploaded files

Revision ID: add_uploaded_files
Revises: f39f11d26060
Create Date: 2025-01-01 00:00:00.000000

NOTE: This is a stub migration. The actual uploaded_files column was added
via _migrate_uploaded_files_column() in submissions.py using raw SQL.
This file exists only to keep the Alembic revision chain intact.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_uploaded_files'
down_revision = 'f39f11d26060'
branch_labels = None
depends_on = None


def upgrade():
    # Column was added via raw SQL in _migrate_uploaded_files_column()
    # Nothing to do here — stub only.
    pass


def downgrade():
    pass
