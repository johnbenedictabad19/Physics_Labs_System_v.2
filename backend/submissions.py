from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from models import Submission, User, Activity, Class, ClassMember
import json
import os
from datetime import datetime

submissions = Blueprint('submissions', __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')


# ===== SUBMIT ACTIVITY =====
@submissions.route('/<int:activity_id>/submit', methods=['POST'])
@jwt_required()
def submit_activity(activity_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    if user.role != 'student':
        return jsonify({'message': 'Only students can submit!'}), 403

    # Block re-submit if already submitted (not draft)
    existing = Submission.query.filter_by(
        activity_id=activity_id,
        student_id=user_id
    ).filter(Submission.status.in_(['submitted', 'graded'])).first()

    if existing:
        # Already submitted — return the existing submission so frontend can show submitted state
        return jsonify({
            'message': 'Already submitted.',
            'id': existing.id,
            'status': existing.status,
            'submitted_at': existing.submitted_at.strftime('%b %d, %Y %I:%M %p') if existing.submitted_at else ''
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

    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'png', 'jpg', 'jpeg'}
    uploaded_filename = None
    if 'file' in request.files:
        file = request.files['file']
        if file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                return jsonify({'message': f'File type .{ext} is not allowed. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
            safe_name = f"submission_{activity_id}_{user_id}_{int(__import__('time').time())}.{ext}"
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            file.save(os.path.join(UPLOAD_FOLDER, safe_name))
            uploaded_filename = safe_name

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
        if uploaded_filename: draft.uploaded_file = uploaded_filename
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
            uploaded_file=uploaded_filename,
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
                ).filter(Submission.status.in_(['submitted', 'graded'])).first()
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

    return jsonify({'message': 'Submitted successfully!', 'id': sub_id}), 200 if draft else 201


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

    return jsonify({'message': 'Submission retracted. You can now edit and resubmit.'}), 200



# ===== GET MY SUBMISSION =====
@submissions.route('/<int:activity_id>/my-submission', methods=['GET'])
@jwt_required()
def get_my_submission(activity_id):
    user_id = int(get_jwt_identity())
    # Only return submissions that are actually submitted or graded (not drafts)
    sub = Submission.query.filter_by(
        activity_id=activity_id,
        student_id=user_id
    ).filter(Submission.status.in_(['submitted', 'graded'])).first()

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
            'submitted_at': sub.submitted_at.strftime('%b %d, %Y %I:%M %p') if sub.submitted_at else '',
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
                'submitted_at': s.submitted_at.strftime('%b %d, %Y %I:%M %p') if s.submitted_at else '',
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

    data = request.get_json()
    sub.grade = data.get('grade')
    sub.feedback = data.get('feedback', '')
    sub.graded_by = user_id
    sub.graded_at = datetime.utcnow()
    sub.status = 'graded'

    db.session.commit()
    # Push real-time grade update to student
    try:
        from extensions import socketio as _sio
        _sio.emit('submission_graded', {
            'student_id':  sub.student_id,
            'activity_id': sub.activity_id,
            'grade':       sub.grade,
            'feedback':    sub.feedback or '',
        }, namespace='/')
    except Exception as e:
        print(f'[grade emit] error: {e}')
    # Notify student
    try:
        from notifications import notify
        act = Activity.query.get(sub.activity_id)
        if act:
            notify(sub.student_id,
                   f'Your submission for "{act.title}" has been graded',
                   f'/activity?id={act.id}', 'grade')
    except Exception as e:
        print(f'[grade notify] error: {e}')
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
        draft.submitted_at      = datetime.utcnow()   # use as "last_saved"
    else:
        draft = Submission(
            activity_id=activity_id,
            student_id=user_id,
            answers=answers,
            table_data=table_data,
            materials_checked=materials_checked,
            student_info=student_info,
            status='draft',
            group_id=group_id
        )
        db.session.add(draft)

    db.session.commit()
    return jsonify({'message': 'Draft saved!', 'saved_at': draft.submitted_at.strftime('%I:%M %p')}), 200


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
        at_str = submitted_at.strftime('%b %d, %Y %I:%M %p') if submitted_at else ''
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
        'student_email': student.email if student else '',
        'student_avatar': student.avatar or '' if student else '',
        'answers': answers,
        'table_data': table_data,
        'materials_checked': safe_json(sub.materials_checked, []),
        'student_info': student_info,
        'uploaded_file': sub.uploaded_file,
        'grade': sub.grade,
        'feedback': sub.feedback,
        'status': sub.status,
        'group_id': getattr(sub, 'group_id', None),
        'attendance_status': getattr(sub, 'attendance_status', None),
        'submitted_at': sub.submitted_at.strftime('%b %d, %Y %I:%M %p') if sub.submitted_at else ''
    }