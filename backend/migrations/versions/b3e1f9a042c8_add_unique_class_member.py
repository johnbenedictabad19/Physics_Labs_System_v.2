"""add unique constraint class_members(class_id, student_id)

Revision ID: b3e1f9a042c8
Revises: 7f2c82cb9323
Create Date: 2026-05-13

"""
from alembic import op

revision = 'b3e1f9a042c8'
down_revision = '7f2c82cb9323'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Remove duplicate rows — keep the row with the lowest id per (class_id, student_id)
    op.execute("""
        DELETE FROM class_members
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM class_members
            GROUP BY class_id, student_id
        )
    """)

    # 2. Add unique constraint
    op.create_unique_constraint(
        'uq_class_members_class_student',
        'class_members',
        ['class_id', 'student_id']
    )


def downgrade():
    op.drop_constraint(
        'uq_class_members_class_student',
        'class_members',
        type_='unique'
    )
