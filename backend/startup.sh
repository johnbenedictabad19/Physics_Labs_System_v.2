#!/bin/bash
set -e
cd /app/backend

python3 - <<'EOF'
from app import app, db
from sqlalchemy import text, inspect
try:
    with app.app_context():
        insp = inspect(db.engine)
        with db.engine.begin() as conn:
            # Fix alembic_version if missing or wrong
            if not insp.has_table('alembic_version'):
                conn.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL, CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))'))
                conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('d4c0ff760e79')"))
                print('Created and stamped alembic_version to d4c0ff760e79')
            else:
                rows = conn.execute(text('SELECT version_num FROM alembic_version')).fetchall()
                versions = [r[0] for r in rows]
                if not versions or versions == ['800cef0f077e']:
                    conn.execute(text('DELETE FROM alembic_version'))
                    conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('d4c0ff760e79')"))
                    print(f'Updated alembic_version from {versions} to d4c0ff760e79')
                else:
                    print(f'alembic_version already at: {versions}')

            # Add missing columns that db.create_all() cannot add to existing tables
            missing = []
            cm_cols = [c['name'] for c in insp.get_columns('class_members')]
            if 'enrollment_status' not in cm_cols:
                conn.execute(text("ALTER TABLE class_members ADD COLUMN enrollment_status VARCHAR(20)"))
                missing.append('class_members.enrollment_status')

            cl_cols = [c['name'] for c in insp.get_columns('classes')]
            if 'auto_accept' not in cl_cols:
                conn.execute(text("ALTER TABLE classes ADD COLUMN auto_accept BOOLEAN"))
                missing.append('classes.auto_accept')

            ci_cols = [c['name'] for c in insp.get_columns('class_invites')]
            if 'invite_type' not in ci_cols:
                conn.execute(text("ALTER TABLE class_invites ADD COLUMN invite_type VARCHAR(20)"))
                missing.append('class_invites.invite_type')

            if missing:
                print(f'Added missing columns: {missing}')
            else:
                print('All columns present.')
except Exception as e:
    print(f'Startup check error: {e}')
EOF

flask db upgrade
python app.py
