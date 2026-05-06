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
                conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('800cef0f077e')"))
                print('Stamped alembic_version to 800cef0f077e')
            else:
                count = conn.execute(text('SELECT COUNT(*) FROM alembic_version')).scalar()
                if count == 0:
                    conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('800cef0f077e')"))
                    print('Stamped empty alembic_version to 800cef0f077e')
except Exception as e:
    print(f'Stamp check error: {e}')
EOF

flask db upgrade
python app.py
