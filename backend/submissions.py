from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from models import Submission, User, Activity, Class, ClassMember
import json
import os
import time
import difflib
from datetime import datetime, timedelta

_PH = timedelta(hours=8)
def _ph(dt):
    if not dt: return ''
    return (dt + _PH).strftime('%b %d, %Y %I:%M %p')

submissions = Blueprint('submissions', __name__)

UPLOAD_FOLDER = os.environ.get(
    'UPLOAD_FOLDER',
    os.path.join(os.path.dirname(__file__), 'uploads')
)


def _migrate_uploaded_files_column():
    """Add uploaded_files column if missing (safe to call every startup)."""
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='submissions' AND column_name='uploaded_files'"
            ))
            if result.fetchone() is None:
                conn.execute(text("ALTER TABLE submissions ADD COLUMN IF NOT EXISTS uploaded_files JSON"))
                conn.commit()
    except Exception as e:
        print(f'[migration] uploaded_files column: {e}')


# ===== IMMEDIATE ATTACH (data sheet inline images) =====
@submissions.route('/<int:activity_id>/attach', methods=['POST'])
@jwt_required()
def attach_image(activity_id):
    user_id = int(get_jwt_identity())
    ALLOWED = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'pdf'}
    MAX_SIZE = 12 * 1024 * 1024
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'message': 'No file provided'}), 400
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED:
        return jsonify({'message': f'File type .{ext} not allowed'}), 400
    file.stream.seek(0, 2)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > MAX_SIZE:
        return jsonify({'message': 'File exceeds 12 MB limit'}), 400
    safe_name = f"dsattach_{activity_id}_{user_id}_{int(time.time())}.{ext}"
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    file.save(os.path.join(UPLOAD_FOLDER, safe_name))
    return jsonify({'filename': safe_name}), 200


# ===== SERVE UPLOADED FILE =====
@submissions.route('/file/<filename>', methods=['GET'])
@jwt_required()
def serve_uploaded_file(filename):
    if '/' in filename or '\\' in filename or '..' in filename:
        return jsonify({'message': 'Invalid filename'}), 400
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(filepath):
        return jsonify({'message': 'File not found'}), 404
    return send_file(filepath)


# ===== SUBMIT ACTIVITY =====
@submissions.route('/<int:activity_id>/submit', methods=['POST'])
@jwt_required()
def submit_activity(activity_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    if user.role != 'student':
        return jsonify({'message': 'Only students can submit!'}), 403

    # Block re-submit if already submitted (not draft)
    # with_for_update() serializes concurrent submits from the same group at DB level
    existing = Submission.query.filter_by(
        activity_id=activity_id,
        student_id=user_id
    ).filter(Submission.status.in_(['submitted', 'graded'])).with_for_update().first()

    if existing:
        # Already submitted — return the existing submission so frontend can show submitted state
        return jsonify({
            'message': 'Already submitted.',
            'id': existing.id,
            'status': existing.status,
            'submitted_at': _ph(existing.submitted_at)
        }), 200

    def _parse_form_json(val, default):
        if not val:
            return default
        if isinstance(val, (dict, list)):
            return val
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default

    answers           = _parse_form_json(request.form.get('answers', '{}'), {})
    table_data        = _parse_form_json(request.form.get('table_data', '{}'), {})
    materials_checked = _parse_form_json(request.form.get('materials_checked', '[]'), [])
    student_info      = _parse_form_json(request.form.get('student_info', '{}'), {})
    print(f'[submit] activity={activity_id} user={user_id}')

    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'webp', 'gif'}
    MAX_FILES = 5
    MAX_FILE_SIZE = 12 * 1024 * 1024  # 12 MB
    uploaded_file_list = []  # [{file, name}, ...]

    # Re-attach previously uploaded files sent by the frontend as 'retained_file' fields.
    # Look up the proper display name from the existing draft's uploaded_files column.
    retained_names = request.form.getlist('retained_file')
    if retained_names:
        existing_draft = Submission.query.filter_by(
            activity_id=activity_id, student_id=user_id
        ).filter(Submission.status.in_(['draft', 'submitted'])).first()
        existing_files = []
        if existing_draft and existing_draft.uploaded_files:
            raw = existing_draft.uploaded_files
            if isinstance(raw, list):
                existing_files = raw
            else:
                try:
                    existing_files = json.loads(raw)
                except Exception:
                    existing_files = []
        # Build lookup: safe_filename → original display name
        name_lookup = {f['file']: f.get('name', f['file']) for f in existing_files if isinstance(f, dict)}
        for safe_name in retained_names:
            # Security: reject any path traversal attempts
            if '/' in safe_name or '\\' in safe_name or '..' in safe_name:
                continue
            filepath = os.path.join(UPLOAD_FOLDER, safe_name)
            if os.path.exists(filepath):
                disp = name_lookup.get(safe_name, safe_name)
                uploaded_file_list.append({'file': safe_name, 'name': disp})

    for idx, file in enumerate(request.files.getlist('file')[:MAX_FILES]):
        if not file.filename:
            continue
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({'message': f'File type .{ext} not allowed. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
        file.stream.seek(0, 2)
        size = file.stream.tell()
        file.stream.seek(0)
        if size > MAX_FILE_SIZE:
            return jsonify({'message': f'"{file.filename}" exceeds 12 MB limit.'}), 400
        safe_name = f"sub_{activity_id}_{user_id}_{int(time.time())}_{idx}.{ext}"
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        file.save(os.path.join(UPLOAD_FOLDER, safe_name))
        uploaded_file_list.append({'file': safe_name, 'name': file.filename})

    _group_id = None
    try:
        _gid = student_info.get('group_id')
        if _gid: _group_id = int(_gid)
    except Exception:
        pass

    # Upsert: promote existing draft → submitted, or create new
    draft = Submission.query.filter_by(
        activity_id=activity_id,
        student_id=user_id,
        status='draft'
    ).first()

    submitted_at = datetime.utcnow()

    if draft:
        draft.answers           = answers
        draft.table_data        = table_data
        draft.materials_checked = materials_checked
        draft.student_info      = student_info
        draft.status            = 'submitted'
        draft.submitted_at      = submitted_at
        if _group_id: draft.group_id = _group_id
        # Always update uploaded_files: retained + new (overwrite with the full combined list)
        draft.uploaded_files = uploaded_file_list if uploaded_file_list else draft.uploaded_files
        db.session.commit()
        sub_id = draft.id
    else:
        new_sub = Submission(
            activity_id=activity_id,
            student_id=user_id,
            answers=answers,
            table_data=table_data,
            materials_checked=materials_checked,
            student_info=student_info,
            uploaded_files=uploaded_file_list if uploaded_file_list else None,
            status='submitted',
            submitted_at=submitted_at,
            group_id=_group_id
        )
        db.session.add(new_sub)
        db.session.commit()
        sub_id = new_sub.id

    # Cascade: mark all other group members as submitted too
    if _group_id:
        from models import GroupMember
        member_ids = [gm.student_id for gm in GroupMember.query.filter_by(group_id=_group_id).all()]
        for mid in member_ids:
            if mid == user_id:
                continue
            # Promote existing draft
            member_draft = Submission.query.filter_by(
                activity_id=activity_id, student_id=mid, status='draft'
            ).first()
            if member_draft:
                member_draft.answers           = answers
                member_draft.table_data        = table_data
                member_draft.materials_checked = materials_checked
                member_draft.student_info      = student_info
                member_draft.status            = 'submitted'
                member_draft.submitted_at      = submitted_at
                member_draft.group_id          = _group_id
            else:
                # Only create if not already submitted/graded
                already = Submission.query.filter_by(
                    activity_id=activity_id, student_id=mid
                ).filter(Submission.status.in_(['submitted', 'graded'])).with_for_update().first()
                if not already:
                    db.session.add(Submission(
                        activity_id=activity_id,
                        student_id=mid,
                        answers=answers,
                        table_data=table_data,
                        materials_checked=materials_checked,
                        student_info=student_info,
                        status='submitted',
                        submitted_at=submitted_at,
                        group_id=_group_id
                    ))
        db.session.commit()

    _notify_group_submitted(activity_id, _group_id, user_id, submitted_at)

    # Notify professor
    try:
        from notifications import notify
        act = Activity.query.get(activity_id)
        if act:
            cls = Class.query.get(act.class_id)
            if cls:
                notify(cls.professor_id,
                       f'{user.full_name} submitted "{act.title}"',
                       f'/submissions?id={activity_id}&class_id={act.class_id}', 'submit')
    except Exception:
        pass

    return jsonify({'message': 'Submitted successfully!', 'id': sub_id,
                    'uploaded_files': uploaded_file_list}), 200 if draft else 201


# ===== CANCEL / UNSUBMIT (student, only if not yet graded) =====
@submissions.route('/<int:activity_id>/unsubmit', methods=['POST'])
@jwt_required()
def unsubmit_activity(activity_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    if user.role != 'student':
        return jsonify({'message': 'Only students can retract submissions!'}), 403

    sub = Submission.query.filter_by(
        activity_id=activity_id,
        student_id=user_id
    ).first()

    if not sub:
        return jsonify({'message': 'No submission found.'}), 404

    if sub.status == 'graded':
        return jsonify({'message': 'Your submission has already been graded and cannot be retracted.'}), 403

    if sub.status != 'submitted':
        return jsonify({'message': 'Nothing to retract.'}), 400

    # Revert to draft — keeps all answers intact
    sub.status = 'draft'
    db.session.commit()

    # Cascade: revert all other group members back to draft too
    group_id = getattr(sub, 'group_id', None)
    if group_id:
        from models import GroupMember
        member_ids = [gm.student_id for gm in GroupMember.query.filter_by(group_id=group_id).all()]
        for mid in member_ids:
            if mid == user_id:
                continue
            msub = Submission.query.filter_by(
                activity_id=activity_id, student_id=mid, status='submitted'
            ).first()
            if msub:
                msub.status = 'draft'
        db.session.commit()
        # Notify group via WebSocket
        try:
            from extensions import socketio as _sio
            _sio.emit('group_unsubmitted', {'unsubmitted_by': user_id},
                      to=f'a{activity_id}g{group_id}')
        except Exception:
            pass

    # Feed event
    try:
        from feed import emit_feed
        act = Activity.query.get(activity_id)
        if act:
            emit_feed(act.class_id, 'unsubmit', user.full_name, 'student',
                      f'{user.full_name} retracted submission for "{act.title}"')
    except Exception:
        pass

    return jsonify({
        'message': 'Submission retracted. You can now edit and resubmit.',
        'submission': format_submission(sub)
    }), 200



# ===== GET MY SUBMISSION =====
@submissions.route('/<int:activity_id>/my-submission', methods=['GET'])
@jwt_required()
def get_my_submission(activity_id):
    user_id = int(get_jwt_identity())
    # Prefer final states (submitted/graded); if none exists, fall back to latest draft.
    base_query = Submission.query.filter_by(
        activity_id=activity_id,
        student_id=user_id
    )

    sub = (base_query
           .filter(Submission.status.in_(['submitted', 'graded']))
           .order_by(Submission.submitted_at.desc(), Submission.id.desc())
           .first())

    if not sub:
        sub = (base_query
               .filter(Submission.status == 'draft')
               .order_by(Submission.submitted_at.desc(), Submission.id.desc())
               .first())

    if not sub:
        return jsonify(None), 200

    try:
        return jsonify(format_submission(sub)), 200
    except Exception as e:
        print(f"format_submission error: {e}")
        # Return minimal data so frontend doesn't crash
        return jsonify({
            'id': sub.id,
            'activity_id': sub.activity_id,
            'student_id': sub.student_id,
            'status': sub.status or 'submitted',
            'grade': sub.grade,
            'feedback': sub.feedback or '',
            'submitted_at': _ph(sub.submitted_at),
            'answers': {}, 'table_data': {}, 'materials_checked': {},
            'student_info': {}, 'uploaded_file': None,
            'group_id': None, 'attendance_status': None,
            'student_name': '', 'student_email': ''
        }), 200


# ===== GET ALL SUBMISSIONS (Professor) =====
@submissions.route('/<int:activity_id>/all', methods=['GET'])
@jwt_required()
def get_all_submissions(activity_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can view all submissions!'}), 403

    # Only return submitted/graded — never drafts
    subs = Submission.query.filter(
        Submission.activity_id == activity_id,
        Submission.status.in_(['submitted', 'graded'])
    ).all()

    result = []
    for s in subs:
        try:
            result.append(format_submission(s))
        except Exception as e:
            result.append({
                'id': s.id, 'activity_id': s.activity_id,
                'student_id': s.student_id, 'status': s.status,
                'grade': s.grade, 'feedback': s.feedback or '',
                'submitted_at': _ph(s.submitted_at),
                'answers': {}, 'table_data': {}, 'materials_checked': {},
                'student_info': {}, 'uploaded_file': None,
                'group_id': None, 'attendance_status': None,
                'student_name': 'Unknown', 'student_email': ''
            })
    return jsonify(result), 200


# ===== GRADE SUBMISSION =====
@submissions.route('/<int:submission_id>/grade', methods=['POST'])
@jwt_required()
def grade_submission(submission_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can grade!'}), 403

    sub = Submission.query.get(submission_id)
    if not sub:
        return jsonify({'message': 'Submission not found!'}), 404
    from classes import _is_class_prof
    act = Activity.query.get(sub.activity_id)
    if not act or not _is_class_prof(act.class_id, user_id):
        return jsonify({'message': 'Not authorized to grade this submission!'}), 403

    data = request.get_json() or {}
    grade    = data.get('grade')
    feedback = data.get('feedback', '')
    now      = datetime.utcnow()

    if grade is None:
        return jsonify({'message': 'Grade is required!'}), 400
    try:
        grade = float(grade)
    except (TypeError, ValueError):
        return jsonify({'message': 'Grade must be a number!'}), 400
    if grade < 0 or grade > 100:
        return jsonify({'message': 'Grade must be between 0 and 100!'}), 400
    if len(feedback) > 2000:
        return jsonify({'message': 'Feedback cannot exceed 2000 characters!'}), 400

    sub.grade      = grade
    sub.feedback   = feedback
    sub.graded_by  = user_id
    sub.graded_at  = now
    sub.status     = 'graded'

    # Cascade grade to all group members' submissions for the same activity
    graded_students = [sub.student_id]
    if sub.group_id:
        siblings = Submission.query.filter(
            Submission.activity_id == sub.activity_id,
            Submission.group_id    == sub.group_id,
            Submission.id          != sub.id
        ).all()
        for s in siblings:
            s.grade     = grade
            s.feedback  = feedback
            s.graded_by = user_id
            s.graded_at = now
            s.status    = 'graded'
            graded_students.append(s.student_id)

    db.session.commit()

    # Push real-time grade update to all affected students
    try:
        from extensions import socketio as _sio
        act = Activity.query.get(sub.activity_id)
        for sid in graded_students:
            _sio.emit('submission_graded', {
                'student_id':  sid,
                'activity_id': sub.activity_id,
                'grade':       grade,
                'feedback':    feedback or '',
            }, namespace='/')
            try:
                from notifications import notify
                if act:
                    notify(sid,
                           f'Your submission for "{act.title}" has been graded',
                           f'/activity?id={act.id}', 'grade')
            except Exception as e:
                print(f'[grade notify] error: {e}')
    except Exception as e:
        print(f'[grade emit] error: {e}')

    return jsonify({'message': 'Graded successfully!'}), 200


# ===== SAVE DRAFT (auto-save, group-shared) =====
@submissions.route('/<int:activity_id>/draft', methods=['POST'])
@jwt_required()
def save_draft(activity_id):
    """Save a student's draft answers. Group-shared: all members of the same group
       will see the latest draft when they load the activity."""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if user.role != 'student':
        return jsonify({'message': 'Only students can save drafts!'}), 403

    # Already submitted or graded? Don't allow overwriting with a draft
    existing = Submission.query.filter_by(
        activity_id=activity_id, student_id=user_id
    ).filter(Submission.status.in_(['submitted', 'graded'])).first()
    if existing:
        return jsonify({'message': 'Already submitted — cannot save draft.'}), 400

    data = request.get_json() or {}
    answers           = data.get('answers', {})
    table_data        = data.get('table_data', {})
    materials_checked = data.get('materials_checked', {})
    student_info      = data.get('student_info', {})
    group_id          = data.get('group_id') or (student_info or {}).get('group_id') or None
    uploaded_files    = data.get('uploaded_files', None)  # [{file, name}, ...] from upload section

    # Upsert: update existing draft or create new one
    draft = Submission.query.filter_by(
        activity_id=activity_id,
        student_id=user_id,
        status='draft'
    ).first()

    if draft:
        draft.answers           = answers
        draft.table_data        = table_data
        draft.materials_checked = materials_checked
        draft.student_info      = student_info
        if group_id: draft.group_id = group_id
        if uploaded_files is not None: draft.uploaded_files = uploaded_files
        draft.submitted_at      = datetime.utcnow()   # use as "last_saved"
    else:
        draft = Submission(
            activity_id=activity_id,
            student_id=user_id,
            answers=answers,
            table_data=table_data,
            materials_checked=materials_checked,
            student_info=student_info,
            uploaded_files=uploaded_files or [],
            status='draft',
            group_id=group_id
        )
        db.session.add(draft)

    db.session.commit()
    return jsonify({'message': 'Draft saved!', 'saved_at': (draft.submitted_at + _PH).strftime('%I:%M %p') if draft.submitted_at else ''}), 200


# ===== GET GROUP DRAFT (collaborative — load latest draft from any group member) =====
@submissions.route('/<int:activity_id>/group-draft', methods=['GET'])
@jwt_required()
def get_group_draft(activity_id):
    """Return the most recent draft for any member in the same group.
       This enables all group members to see the same progress."""
    user_id  = int(get_jwt_identity())
    group_id = request.args.get('group_id', type=int)

    if not group_id:
        return jsonify(None), 200

    # Find all drafts for this activity that belong to this group
    from models import GroupMember
    member_ids = [gm.student_id for gm in GroupMember.query.filter_by(group_id=group_id).all()]
    if not member_ids:
        return jsonify(None), 200

    # Get the most recently saved draft among all group members
    latest = (Submission.query
              .filter(
                  Submission.activity_id == activity_id,
                  Submission.student_id.in_(member_ids),
                  Submission.status == 'draft'
              )
              .order_by(Submission.submitted_at.desc())
              .first())

    if not latest:
        return jsonify(None), 200

    try:
        return jsonify(format_submission(latest)), 200
    except Exception:
        return jsonify(None), 200


# ===== BATCH STATUS — student sees all their submission statuses for a class =====
@submissions.route('/my-statuses', methods=['GET'])
@jwt_required()
def my_statuses():
    """Returns {activity_id: status} for every activity in a class the student has touched."""
    user_id  = int(get_jwt_identity())
    class_id = request.args.get('class_id', type=int)
    if not class_id:
        return jsonify({}), 200

    from models import Activity
    activity_ids = [a.id for a in Activity.query.filter_by(class_id=class_id).all()]
    if not activity_ids:
        return jsonify({}), 200

    subs = Submission.query.filter(
        Submission.student_id == user_id,
        Submission.activity_id.in_(activity_ids),
        Submission.status.in_(['draft', 'submitted', 'graded'])
    ).all()

    result = {}
    for s in subs:
        # Latest status wins (graded > submitted > draft)
        prev = result.get(s.activity_id)
        rank = {'draft': 1, 'submitted': 2, 'graded': 3}
        if prev is None or rank.get(s.status, 0) > rank.get(prev, 0):
            result[s.activity_id] = s.status

    return jsonify(result), 200



def _notify_group_submitted(activity_id, group_id, submitted_by, submitted_at):
    """Emit group_submitted WebSocket event to notify other group members."""
    if not group_id:
        return
    try:
        from extensions import socketio as _sio
        room = f'a{activity_id}g{group_id}'
        at_str = _ph(submitted_at)
        _sio.emit('group_submitted', {
            'submitted_by': submitted_by,
            'submitted_at': at_str,
            'status': 'submitted'
        }, to=room)
    except Exception:
        pass


# ===== ALL GROUP DRAFTS (professor: progress view) =====
@submissions.route('/<int:activity_id>/all-group-drafts', methods=['GET'])
@jwt_required()
def get_all_group_drafts(activity_id):
    """Professor: returns the latest draft or submission per group for progress tracking."""
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if user.role != 'professor':
        return jsonify({'message': 'Professor only'}), 403

    class_id = request.args.get('class_id', type=int)
    if not class_id:
        return jsonify({}), 200

    from models import Group, GroupMember
    groups = Group.query.filter_by(class_id=class_id).all()

    result = {}
    for group in groups:
        member_ids = [gm.student_id for gm in GroupMember.query.filter_by(group_id=group.id).all()]
        if not member_ids:
            continue
        latest = (Submission.query
                  .filter(
                      Submission.activity_id == activity_id,
                      Submission.student_id.in_(member_ids)
                  )
                  .order_by(Submission.submitted_at.desc())
                  .first())
        if latest:
            try:
                result[str(group.id)] = format_submission(latest)
            except Exception:
                pass

    return jsonify(result), 200


def format_submission(sub):
    student = User.query.get(sub.student_id)

    # Safe JSON parse helper
    def safe_json(val, default):
        if not val:
            return default
        if isinstance(val, (dict, list)):
            return val
        try:
            result = json.loads(val)
            # Handle double-encoded JSON
            if isinstance(result, str):
                result = json.loads(result)
            return result
        except (json.JSONDecodeError, TypeError):
            return default

    answers = safe_json(sub.answers, {})
    table_data = safe_json(sub.table_data, {})
    student_info = safe_json(sub.student_info, {})

    # Enrich group members with live avatar from DB
    if isinstance(student_info.get('members'), list):
        for m in student_info['members']:
            # members can be strings (names) or dicts
            if isinstance(m, dict):
                mid = m.get('id') or m.get('student_id')
                if mid:
                    member_user = User.query.get(mid)
                    m['avatar'] = member_user.avatar or '' if member_user else ''

    return {
        'id': sub.id,
        'activity_id': sub.activity_id,
        'student_id': sub.student_id,
        'student_name': student.full_name if student else 'Unknown',
        'student_number': (student.student_number or '') if student else '',
        'student_email': (student.email or '') if student else '',
        'student_avatar': (student.avatar or '') if student else '',
        'answers': answers,
        'table_data': table_data,
        'materials_checked': safe_json(sub.materials_checked, []),
        'student_info': student_info,
        'uploaded_file': sub.uploaded_file,
        'uploaded_files': (getattr(sub, 'uploaded_files', None) or
                           ([{'file': sub.uploaded_file, 'name': 'Uploaded File'}] if sub.uploaded_file else [])),
        'grade': sub.grade,
        'feedback': sub.feedback,
        'status': sub.status,
        'group_id': getattr(sub, 'group_id', None),
        'attendance_status': getattr(sub, 'attendance_status', None),
        'submitted_at': _ph(sub.submitted_at),
        'analysis': sub.analysis or None,
        'analyzed_at': _ph(sub.analyzed_at) if sub.analyzed_at else None,
        'rubric_scores': sub.rubric_scores or None,
    }


# ============================================================
# SAVE RUBRIC SCORES
# ============================================================
@submissions.route('/<int:submission_id>/rubric', methods=['POST'])
@jwt_required()
def save_rubric_scores(submission_id):
    user_id = get_jwt_identity()
    user    = User.query.get(int(user_id))

    if user.role not in ('professor', 'admin'):
        return jsonify({'message': 'Only professors can save rubric scores!'}), 403

    sub = Submission.query.get(submission_id)
    if not sub:
        return jsonify({'message': 'Submission not found!'}), 404

    data   = request.get_json() or {}
    scores = data.get('rubric_scores', {})  # { "0": 2, "1": 0, ... }

    sub.rubric_scores = scores
    db.session.commit()

    return jsonify({'message': 'Rubric scores saved!', 'rubric_scores': sub.rubric_scores}), 200


# ============================================================
# ANALYZE SUBMISSION — Plagiarism Detection
# ============================================================

def _plagiarism_check(text, activity_id, exclude_submission_id):
    """Compare text against same-activity submissions. Returns best match dict or None."""
    if not text or not text.strip():
        return None

    peers = Submission.query.filter(
        Submission.activity_id == activity_id,
        Submission.id != exclude_submission_id,
        Submission.status.in_(['submitted', 'graded'])
    ).all()

    best_ratio   = 0.0
    best_student = None
    best_sid     = None

    for peer in peers:
        peer_answers = peer.answers or {}
        if isinstance(peer_answers, str):
            try:
                peer_answers = json.loads(peer_answers)
            except Exception:
                continue
        for val in peer_answers.values():
            if not isinstance(val, str) or not val.strip():
                continue
            ratio = difflib.SequenceMatcher(None, text.lower(), val.lower()).ratio()
            if ratio > best_ratio:
                best_ratio   = ratio
                peer_student = User.query.get(peer.student_id)
                best_student = peer_student.full_name if peer_student else 'Unknown'
                best_sid     = peer.student_id

    if best_ratio < 0.30:
        return None
    return {
        'similarity':         round(best_ratio, 4),
        'matched_student':    best_student,
        'matched_student_id': best_sid,
    }


@submissions.route('/<int:submission_id>/analyze', methods=['POST'])
@jwt_required()
def analyze_submission(submission_id):
    user_id = get_jwt_identity()
    user    = User.query.get(int(user_id))

    if user.role not in ('professor', 'admin'):
        return jsonify({'message': 'Only professors can analyze submissions!'}), 403

    sub = Submission.query.get(submission_id)
    if not sub:
        return jsonify({'message': 'Submission not found!'}), 404

    answers = sub.answers or {}
    if isinstance(answers, str):
        try:
            answers = json.loads(answers)
        except Exception:
            answers = {}

    results = {}
    for key, text in answers.items():
        if not isinstance(text, str) or not text.strip():
            results[key] = {'plagiarism': None}
            continue
        results[key] = {
            'plagiarism': _plagiarism_check(text, sub.activity_id, submission_id),
        }

    sub.analysis    = results
    sub.analyzed_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'message':     'Plagiarism check complete.',
        'analysis':    results,
        'analyzed_at': _ph(sub.analyzed_at),
    }), 200