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
except Exception as e:
    print(f'Stamp check error: {e}')
EOF

flask db upgrade
python app.py
