"""
cleanup_drafts.py
-----------------
Run this ONCE to purge all ghost draft records from the submissions table.
Drafts are auto-save artifacts — they are NOT real submissions.

Usage:
    python cleanup_drafts.py

Place this in your project root (same folder as app.py) before running.
"""

import os, sys

# ── Make sure we can import app context ──────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

try:
    from app import app
    from database import db
    from models import Submission
except ImportError as e:
    print(f"[ERROR] Cannot import app: {e}")
    print("Make sure this script is in your project root folder.")
    sys.exit(1)

with app.app_context():
    # Count before
    total   = Submission.query.count()
    drafts  = Submission.query.filter_by(status='draft').all()
    n_draft = len(drafts)

    print(f"Total submission records : {total}")
    print(f"Draft records found      : {n_draft}")

    if n_draft == 0:
        print("Nothing to clean up.")
        sys.exit(0)

    # Show what will be deleted
    print("\nDraft records to delete:")
    for d in drafts:
        print(f"  id={d.id}  activity_id={d.activity_id}  student_id={d.student_id}  saved_at={d.submitted_at}")

    confirm = input(f"\nDelete all {n_draft} draft record(s)? [yes/no]: ").strip().lower()
    if confirm != 'yes':
        print("Aborted.")
        sys.exit(0)

    for d in drafts:
        db.session.delete(d)
    db.session.commit()

    remaining = Submission.query.count()
    print(f"\nDone. Deleted {n_draft} draft(s). Remaining records: {remaining}")