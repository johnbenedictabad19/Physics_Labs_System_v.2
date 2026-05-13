from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from models import Class, ClassMember, ClassTeacher, User, Group, GroupMember, ClassSession, SessionAttendance, ClassInvite
from datetime import datetime
import random
import string
import os
from werkzeug.utils import secure_filename

classes = Blueprint('classes', __name__)

BANNER_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), 'uploads', 'banners')

def _notify_class_update(action, class_id):
    try:
        from extensions import socketio
        socketio.emit('class_update', {'action': action, 'class_id': class_id}, namespace='/')
    except Exception as e:
        print(f'[classes] notify error: {e}')
ALLOWED_BANNER_EXTS = {'jpg', 'jpeg', 'png', 'webp'}

def _allowed_banner(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_BANNER_EXTS

# ===== UPLOAD BANNER =====
@classes.route('/upload-banner', methods=['POST'])
@jwt_required()
def upload_banner():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if user.role != 'professor':
        return jsonify({'message': 'Only professors can upload banners!'}), 403

    if 'file' not in request.files:
        return jsonify({'message': 'No file provided!'}), 400
    f = request.files['file']
    if not f or not _allowed_banner(f.filename):
        return jsonify({'message': 'Invalid file type. Use JPG or PNG.'}), 400
    f.stream.seek(0, 2)
    banner_size = f.stream.tell()
    f.stream.seek(0)
    if banner_size > 5 * 1024 * 1024:
        return jsonify({'message': 'File too large. Max 5MB.'}), 400

    os.makedirs(BANNER_UPLOAD_DIR, exist_ok=True)
    ext = f.filename.rsplit('.', 1)[1].lower()
    filename = f'banner_{user_id}_{int(datetime.utcnow().timestamp())}.{ext}'
    f.save(os.path.join(BANNER_UPLOAD_DIR, filename))
    return jsonify({'url': f'/api/classes/banners/{filename}'}), 200

# ===== SERVE BANNER =====
@classes.route('/banners/<filename>', methods=['GET'])
def serve_banner(filename):
    from flask import send_from_directory
    return send_from_directory(BANNER_UPLOAD_DIR, secure_filename(filename))

def generate_class_code():
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        existing = Class.query.filter_by(class_code=code).first()
        if not existing:
            return code

# ===== CREATE CLASS =====
@classes.route('/create', methods=['POST'])
@jwt_required()
def create_class():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can create classes!'}), 403

    data = request.get_json() or {}
    class_name = data.get('class_name')
    subject = data.get('subject')
    section = data.get('section')

    if not class_name or not subject or not section:
        return jsonify({'message': 'Please fill in all fields!'}), 400

    theme        = int(data.get('theme', 0))
    banner_image = data.get('banner_image', None)

    new_class = Class(
        class_name=class_name,
        subject=subject,
        section=section,
        class_code=generate_class_code(),
        professor_id=user.id,
        theme=theme,
        banner_image=banner_image
    )
    db.session.add(new_class)
    db.session.commit()

    return jsonify({
        'message': 'Class created successfully!',
        'class_code': new_class.class_code,
        'class_name': new_class.class_name
    }), 201


# ===== GET MY CLASSES =====
@classes.route('/my-classes', methods=['GET'])
@jwt_required()
def get_my_classes():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role == 'professor':
        my_classes = Class.query.filter_by(professor_id=user.id, is_archived=False).all()
        result = []
        for c in my_classes:
            member_count = ClassMember.query.filter_by(class_id=c.id).count()
            result.append({
                'id': c.id,
                'class_name': c.class_name,
                'subject': c.subject,
                'section': c.section,
                'class_code': c.class_code,
                'student_count': member_count,
                'theme': c.theme or 0,
                'banner_image': c.banner_image or ''
            })
    else:
        memberships = ClassMember.query.filter_by(student_id=user.id, is_archived=False).all()
        result = []
        for m in memberships:
            c = Class.query.get(m.class_id)
            if not c:
                db.session.delete(m)
                continue
            if c.is_archived:
                continue  # prof archived this class — hide from student dashboard
            professor = User.query.get(c.professor_id)
            if not professor:
                continue
            result.append({
                'id': c.id,
                'class_name': c.class_name,
                'subject': c.subject,
                'section': c.section,
                'class_code': c.class_code,
                'professor_name': professor.full_name,
                'theme': c.theme or 0,
                'banner_image': c.banner_image or '',
                'enrollment_status': m.enrollment_status or 'approved'
            })
        db.session.commit()

    return jsonify(result), 200


# ===== GET ARCHIVED CLASSES =====
@classes.route('/archived', methods=['GET'])
@jwt_required()
def get_archived():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role == 'professor':
        archived = Class.query.filter_by(professor_id=user.id, is_archived=True).all()
        result = []
        for c in archived:
            member_count = ClassMember.query.filter_by(class_id=c.id).count()
            result.append({
                'id': c.id, 'class_name': c.class_name, 'subject': c.subject,
                'section': c.section, 'class_code': c.class_code,
                'student_count': member_count, 'theme': c.theme or 0,
                'banner_image': c.banner_image or ''
            })
    else:
        # Show classes that are either: student soft-archived, OR prof-archived
        memberships = ClassMember.query.filter_by(student_id=user.id).all()
        result = []
        seen = set()
        for m in memberships:
            c = Class.query.get(m.class_id)
            if not c or c.id in seen:
                continue
            if not (m.is_archived or c.is_archived):
                continue  # still active — skip
            professor = User.query.get(c.professor_id)
            if not professor:
                continue
            seen.add(c.id)
            result.append({
                'id': c.id, 'class_name': c.class_name, 'subject': c.subject,
                'section': c.section, 'class_code': c.class_code,
                'professor_name': professor.full_name, 'theme': c.theme or 0,
                'banner_image': c.banner_image or '',
                'archived_by_prof': c.is_archived  # so frontend can show context
            })

    return jsonify(result), 200


# ===== STUDENT ARCHIVE/UNARCHIVE MEMBERSHIP =====
@classes.route('/<int:class_id>/archive-member', methods=['POST'])
@jwt_required()
def archive_member(class_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    m = ClassMember.query.filter_by(class_id=class_id, student_id=user.id).first()
    if not m:
        return jsonify({'message': 'Membership not found!'}), 404
    m.is_archived = not m.is_archived
    db.session.commit()
    status = 'archived' if m.is_archived else 'unarchived'
    return jsonify({'message': f'Class {status}!', 'is_archived': m.is_archived}), 200


# ===== JOIN CLASS =====
@classes.route('/join', methods=['POST'])
@jwt_required()
def join_class():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role != 'student':
        return jsonify({'message': 'Only students can join classes!'}), 403

    data = request.get_json() or {}
    class_code = data.get('class_code', '').strip().upper()

    c = Class.query.filter_by(class_code=class_code).first()
    if not c:
        return jsonify({'message': 'Class not found! Check the class code.'}), 404

    already_joined = ClassMember.query.filter_by(class_id=c.id, student_id=user.id).first()
    if already_joined:
        if already_joined.enrollment_status == 'pending':
            return jsonify({'message': 'Your request is still pending approval!'}), 400
        if already_joined.enrollment_status == 'rejected':
            return jsonify({'message': 'Your request was declined by the professor.'}), 400
        return jsonify({'message': 'You are already a member of this class!'}), 400

    status = 'approved' if c.auto_accept else 'pending'
    new_member = ClassMember(class_id=c.id, student_id=user.id, enrollment_status=status)
    db.session.add(new_member)
    db.session.commit()

    # Notify professor
    try:
        from notifications import notify
        if status == 'approved':
            notify(c.professor_id,
                   f'{user.full_name} joined your class {c.class_name}',
                   f'/class_detail?id={c.id}', 'joined')
        else:
            notify(c.professor_id,
                   f'{user.full_name} requested to join {c.class_name}',
                   f'/class_detail?id={c.id}', 'joined')
    except Exception:
        pass

    if status == 'pending':
        return jsonify({
            'message': f'Request sent! Waiting for professor\'s approval.',
            'status': 'pending',
            'class_name': c.class_name,
            'subject': c.subject
        }), 200

    return jsonify({
        'message': f'Successfully joined {c.class_name}!',
        'status': 'approved',
        'class_name': c.class_name,
        'subject': c.subject
    }), 200


# ===== PENDING REQUESTS =====
@classes.route('/<int:class_id>/pending', methods=['GET'])
@jwt_required()
def get_pending(class_id):
    user_id = int(get_jwt_identity())
    c = Class.query.get(class_id)
    if not c or not _is_class_prof(c.id, user_id):
        return jsonify({'message': 'Unauthorized'}), 403
    pending = ClassMember.query.filter_by(class_id=class_id, enrollment_status='pending').all()
    result = []
    for m in pending:
        s = User.query.get(m.student_id)
        if s:
            result.append({
                'member_id': m.id,
                'student_id': s.id,
                'full_name': s.full_name,
                'student_number': s.student_number or '—',
                'avatar': s.avatar or None,
                'requested_at': m.joined_at.isoformat() + 'Z'
            })
    return jsonify(result), 200


@classes.route('/<int:class_id>/approve/<int:member_id>', methods=['POST'])
@jwt_required()
def approve_member(class_id, member_id):
    user_id = int(get_jwt_identity())
    c = Class.query.get(class_id)
    if not c or not _is_class_prof(c.id, user_id):
        return jsonify({'message': 'Unauthorized'}), 403
    m = ClassMember.query.filter_by(id=member_id, class_id=class_id).first()
    if not m:
        return jsonify({'message': 'Request not found'}), 404
    m.enrollment_status = 'approved'
    db.session.commit()
    try:
        from notifications import notify
        student = User.query.get(m.student_id)
        notify(m.student_id,
               f'Your request to join {c.class_name} was approved!',
               f'/class_detail?id={c.id}', 'joined')
    except Exception:
        pass
    return jsonify({'message': 'Student approved!'}), 200


@classes.route('/<int:class_id>/reject/<int:member_id>', methods=['POST'])
@jwt_required()
def reject_member(class_id, member_id):
    user_id = int(get_jwt_identity())
    c = Class.query.get(class_id)
    if not c or not _is_class_prof(c.id, user_id):
        return jsonify({'message': 'Unauthorized'}), 403
    m = ClassMember.query.filter_by(id=member_id, class_id=class_id).first()
    if not m:
        return jsonify({'message': 'Request not found'}), 404
    m.enrollment_status = 'rejected'
    db.session.commit()
    try:
        from notifications import notify
        notify(m.student_id,
               f'Your request to join {c.class_name} was declined.',
               f'/login', 'joined')
    except Exception:
        pass
    return jsonify({'message': 'Student rejected!'}), 200


@classes.route('/<int:class_id>/auto-accept', methods=['POST'])
@jwt_required()
def toggle_auto_accept(class_id):
    user_id = int(get_jwt_identity())
    c = Class.query.get(class_id)
    if not c or not _is_class_prof(c.id, user_id):
        return jsonify({'message': 'Unauthorized'}), 403
    data = request.get_json() or {}
    c.auto_accept = bool(data.get('auto_accept', True))
    db.session.commit()
    return jsonify({'auto_accept': c.auto_accept}), 200


# ===== GET CLASS DETAIL =====
@classes.route('/<int:class_id>', methods=['GET'])
@jwt_required()
def get_class_detail(class_id):
    c = Class.query.get(class_id)
    if not c:
        return jsonify({'message': 'Class not found!'}), 404

    professor = User.query.get(c.professor_id)
    return jsonify({
        'id': c.id,
        'class_name': c.class_name,
        'subject': c.subject,
        'section': c.section,
        'class_code': c.class_code,
        'professor_id': c.professor_id,
        'professor_name':   professor.full_name if professor else '—',
        'professor_email':  professor.email     if professor else '—',
        'professor_avatar': professor.avatar    if professor else '',
        'theme':        c.theme or 0,
        'banner_image': c.banner_image or '',
        'auto_accept':  c.auto_accept if c.auto_accept is not None else True
    }), 200


# ===== UPDATE CLASS =====
@classes.route('/<int:class_id>', methods=['PUT'])
@jwt_required()
def update_class(class_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    c = Class.query.get(class_id)
    if not c:
        return jsonify({'message': 'Class not found!'}), 404
    if not _is_class_prof(c.id, user.id):
        return jsonify({'message': 'Not authorized!'}), 403

    data = request.get_json() or {}
    if 'class_name'   in data: c.class_name   = data['class_name']
    if 'subject'      in data: c.subject      = data['subject']
    if 'section'      in data: c.section      = data['section']
    if 'theme'        in data: c.theme        = int(data['theme'])
    if 'banner_image' in data: c.banner_image = data['banner_image'] or None

    db.session.commit()
    _notify_class_update('updated', class_id)
    return jsonify({'message': 'Class updated successfully!', 'theme': c.theme, 'banner_image': c.banner_image or ''}), 200


# ===== GET STUDENTS IN CLASS =====
@classes.route('/<int:class_id>/students', methods=['GET'])
@jwt_required()
def get_students(class_id):
    members = ClassMember.query.filter_by(class_id=class_id).order_by(ClassMember.joined_at.asc()).all()
    result = []
    for index, m in enumerate(members):
        if m.enrollment_status == 'pending':
            continue
        student = User.query.get(m.student_id)
        result.append({
            'id': student.id,
            'full_name': student.full_name,
            'email': student.email or '',
            'student_number': student.student_number or '',
            'role': student.role,
            'joined_at': m.joined_at.strftime('%b %d, %Y'),
            'number': index + 1,
            'avatar': student.avatar or '',
            'enrollment_status': m.enrollment_status
        })
    return jsonify(result), 200


# ===== CO-TEACHERS LIST =====
@classes.route('/<int:class_id>/teachers', methods=['GET'])
@jwt_required()
def get_teachers(class_id):
    c = Class.query.get(class_id)
    if not c:
        return jsonify([]), 200
    result = []
    main = User.query.get(c.professor_id)
    if main:
        result.append({
            'id': main.id, 'full_name': main.full_name,
            'email': main.email or '', 'avatar': main.avatar or '',
            'is_owner': True
        })
    for ct in ClassTeacher.query.filter_by(class_id=class_id).all():
        t = User.query.get(ct.teacher_id)
        if t:
            result.append({
                'id': t.id, 'full_name': t.full_name,
                'email': t.email or '', 'avatar': t.avatar or '',
                'is_owner': False, 'joined_at': ct.joined_at.strftime('%b %d, %Y')
            })
    return jsonify(result), 200


# ===== ANNOUNCEMENTS =====
@classes.route('/<int:class_id>/announcements', methods=['GET'])
@jwt_required()
def get_announcements(class_id):
    from models import Announcement
    announcements = Announcement.query.filter_by(class_id=class_id).order_by(Announcement.created_at.desc()).all()
    result = []
    for a in announcements:
        poster = User.query.get(a.posted_by_id)
        result.append({
            'message': a.message,
            'posted_by': poster.full_name,
            'created_at': a.created_at.isoformat() + 'Z'
        })
    return jsonify(result), 200


@classes.route('/<int:class_id>/announcements', methods=['POST'])
@jwt_required()
def post_announcement(class_id):
    from models import Announcement
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can post announcements!'}), 403
    if not _is_class_prof(class_id, int(user_id)):
        return jsonify({'message': 'Not authorized!'}), 403

    data = request.get_json() or {}
    message = data.get('message')
    if not message:
        return jsonify({'message': 'Message cannot be empty!'}), 400
    if len(message) > 1000:
        return jsonify({'message': 'Announcement cannot exceed 1000 characters!'}), 400

    new_announcement = Announcement(
        class_id=class_id,
        posted_by_id=user.id,
        message=message
    )
    db.session.add(new_announcement)
    db.session.commit()
    return jsonify({'message': 'Announcement posted!'}), 201


# ============================================================
# GROUPS
# ============================================================

def _serialize_group(g, group_number=None):
    """Helper — serialize a Group to dict including members + leader name."""
    leader = User.query.get(g.leader_id) if g.leader_id else None
    members_data = []
    for gm in g.members:
        student = User.query.get(gm.student_id)
        if student:
            members_data.append({
                'id': student.id,
                'full_name': student.full_name,
                'email': student.email or '',
                'student_number': student.student_number or '',
                'role': student.role,
                'is_leader': student.id == g.leader_id,
                'avatar': student.avatar or ''
            })
    # Sort: leader first, then members alphabetically
    members_data.sort(key=lambda m: (0 if m['is_leader'] else 1, m['full_name'].lower()))
    return {
        'id': g.id,
        'group_number': group_number,   # position within the class (1-based)
        'name': g.name,
        'leader_id': g.leader_id,
        'leader': leader.full_name if leader else None,
        'members': members_data,
        'created_at': g.created_at.strftime('%b %d, %Y')
    }


@classes.route('/<int:class_id>/groups', methods=['GET'])
@jwt_required()
def get_groups(class_id):
    """Get all groups for a class. Students only see their own group."""
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    groups = Group.query.filter_by(class_id=class_id).order_by(Group.created_at.asc()).all()

    # All class members (students and professors) see all groups
    return jsonify([_serialize_group(g, group_number=idx + 1) for idx, g in enumerate(groups)]), 200


@classes.route('/<int:class_id>/groups', methods=['POST'])
@jwt_required()
def create_group(class_id):
    """Create a new group (professor only)."""
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can create groups!'}), 403
    if not _is_class_prof(class_id, int(user_id)):
        return jsonify({'message': 'Not authorized!'}), 403

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    leader_id = data.get('leader_id')
    member_ids = data.get('member_ids', [])

    if not name:
        return jsonify({'message': 'Group name is required!'}), 400
    if not leader_id:
        return jsonify({'message': 'Please select a group leader!'}), 400

    # Ensure leader is included in members
    leader_id = int(leader_id)
    member_ids = [int(m) for m in member_ids]
    if leader_id not in member_ids:
        member_ids.append(leader_id)

    new_group = Group(
        class_id=class_id,
        name=name,
        leader_id=leader_id
    )
    db.session.add(new_group)
    db.session.flush()  # get new_group.id before commit

    for sid in member_ids:
        db.session.add(GroupMember(group_id=new_group.id, student_id=sid))

    db.session.commit()
    all_class_groups = Group.query.filter_by(class_id=class_id).order_by(Group.created_at.asc()).all()
    gnum = next((i+1 for i,g in enumerate(all_class_groups) if g.id == new_group.id), None)
    return jsonify({'message': 'Group created!', 'group': _serialize_group(new_group, group_number=gnum)}), 201


@classes.route('/<int:class_id>/groups/<int:group_id>', methods=['PUT'])
@jwt_required()
def update_group(class_id, group_id):
    """Edit an existing group (professor only)."""
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can edit groups!'}), 403

    group = Group.query.filter_by(id=group_id, class_id=class_id).first()
    if not group:
        return jsonify({'message': 'Group not found!'}), 404

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    leader_id = data.get('leader_id')
    member_ids = data.get('member_ids', [])

    if not name:
        return jsonify({'message': 'Group name is required!'}), 400
    if not leader_id:
        return jsonify({'message': 'Please select a group leader!'}), 400

    leader_id = int(leader_id)
    member_ids = [int(m) for m in member_ids]
    if leader_id not in member_ids:
        member_ids.append(leader_id)

    group.name = name
    group.leader_id = leader_id

    # Replace members
    GroupMember.query.filter_by(group_id=group.id).delete()
    for sid in member_ids:
        db.session.add(GroupMember(group_id=group.id, student_id=sid))

    db.session.commit()
    all_class_groups = Group.query.filter_by(class_id=class_id).order_by(Group.created_at.asc()).all()
    gnum = next((i+1 for i,g in enumerate(all_class_groups) if g.id == group.id), None)
    return jsonify({'message': 'Group updated!', 'group': _serialize_group(group, group_number=gnum)}), 200


@classes.route('/<int:class_id>/groups/<int:group_id>', methods=['DELETE'])
@jwt_required()
def delete_group(class_id, group_id):
    """Delete a group (professor only)."""
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can delete groups!'}), 403

    group = Group.query.filter_by(id=group_id, class_id=class_id).first()
    if not group:
        return jsonify({'message': 'Group not found!'}), 404

    db.session.delete(group)
    db.session.commit()
    return jsonify({'message': 'Group deleted!'}), 200


@classes.route('/<int:class_id>/my-group', methods=['GET'])
@jwt_required()
def get_my_group(class_id):
    """Get the current student's group info (used by create_activity auto-populate)."""
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    membership = GroupMember.query.join(Group).filter(
        Group.class_id == class_id,
        GroupMember.student_id == user.id
    ).first()

    if not membership:
        return jsonify({'message': 'You are not in a group yet.'}), 404

    group = membership.group
    # Compute the 1-based position of this group within the class
    all_class_groups = Group.query.filter_by(class_id=class_id).order_by(Group.created_at.asc()).all()
    group_number = next((idx + 1 for idx, g in enumerate(all_class_groups) if g.id == group.id), None)
    return jsonify(_serialize_group(group, group_number=group_number)), 200


# ============================================================
# SESSION ATTENDANCE
# ============================================================

@classes.route('/<int:class_id>/sessions', methods=['GET'])
@jwt_required()
def get_sessions(class_id):
    """Get all sessions with attendance summary."""
    sessions = ClassSession.query.filter_by(class_id=class_id).order_by(ClassSession.created_at.asc()).all()
    result = []
    for s in sessions:
        present = sum(1 for a in s.attendance if a.status == 'present')
        late    = sum(1 for a in s.attendance if a.status == 'late')
        absent  = sum(1 for a in s.attendance if a.status == 'absent')
        result.append({
            'id': s.id,
            'session_date': s.session_date,
            'present_count': present,
            'late_count': late,
            'absent_count': absent,
            'attendance': [
                {'student_id': a.student_id, 'status': a.status}
                for a in s.attendance
            ]
        })
    return jsonify(result), 200


@classes.route('/<int:class_id>/sessions', methods=['POST'])
@jwt_required()
def create_session(class_id):
    """Create a new session with attendance (professor only)."""
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can record sessions!'}), 403
    if not _is_class_prof(class_id, int(user_id)):
        return jsonify({'message': 'Not authorized!'}), 403

    data = request.get_json() or {}
    session_date = data.get('session_date', '')
    attendance_records = data.get('attendance', [])

    new_session = ClassSession(
        class_id=class_id,
        session_date=session_date,
        created_by=user.id
    )
    db.session.add(new_session)
    db.session.flush()

    for record in attendance_records:
        db.session.add(SessionAttendance(
            session_id=new_session.id,
            student_id=int(record['student_id']),
            status=record.get('status', 'present')
        ))

    db.session.commit()
    return jsonify({'message': 'Session recorded!', 'session_id': new_session.id}), 201


@classes.route('/<int:class_id>/sessions/<int:session_id>', methods=['PUT'])
@jwt_required()
def update_session(class_id, session_id):
    """Edit attendance for an existing session (professor only)."""
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can edit sessions!'}), 403

    session = ClassSession.query.filter_by(id=session_id, class_id=class_id).first()
    if not session:
        return jsonify({'message': 'Session not found!'}), 404

    data = request.get_json() or {}
    attendance_records = data.get('attendance', [])

    if 'session_date' in data:
        session.session_date = data['session_date']

    # Replace attendance records
    SessionAttendance.query.filter_by(session_id=session.id).delete()
    for record in attendance_records:
        db.session.add(SessionAttendance(
            session_id=session.id,
            student_id=int(record['student_id']),
            status=record.get('status', 'present')
        ))

    db.session.commit()
    return jsonify({'message': 'Attendance updated!'}), 200


@classes.route('/<int:class_id>/sessions/<int:session_id>', methods=['DELETE'])
@jwt_required()
def delete_session(class_id, session_id):
    """Delete a session (professor only)."""
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can delete sessions!'}), 403

    session = ClassSession.query.filter_by(id=session_id, class_id=class_id).first()
    if not session:
        return jsonify({'message': 'Session not found!'}), 404

    db.session.delete(session)
    db.session.commit()
    return jsonify({'message': 'Session deleted!'}), 200


# ============================================================
# GRADING (group-based)
# ============================================================

@classes.route('/<int:class_id>/groups/<int:group_id>/grade', methods=['POST'])
@jwt_required()
def grade_group_submission(class_id, group_id):
    """
    Grade a group's submission for a specific activity.
    Applies same grade + feedback to ALL members of the group.
    """
    from models import Submission, Activity
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can grade!'}), 403

    data = request.get_json() or {}
    activity_id = data.get('activity_id')
    grade = data.get('grade')
    feedback = data.get('feedback', '')

    if grade is None:
        return jsonify({'message': 'Grade is required!'}), 400
    try:
        grade = float(grade)
    except (TypeError, ValueError):
        return jsonify({'message': 'Grade must be a number!'}), 400
    if grade < 0 or grade > 100:
        return jsonify({'message': 'Grade must be between 0 and 100!'}), 400

    group = Group.query.filter_by(id=group_id, class_id=class_id).first()
    if not group:
        return jsonify({'message': 'Group not found!'}), 404

    activity = Activity.query.get(activity_id)
    if not activity:
        return jsonify({'message': 'Activity not found!'}), 404

    graded_count = 0
    for gm in group.members:
        # 1) Try to find submission that belongs to THIS group specifically
        sub = Submission.query.filter_by(
            activity_id=activity_id,
            student_id=gm.student_id,
            group_id=group_id
        ).first()

        # 2) Fallback: find any submission by this student for this activity
        #    BUT only if group_id is null/unset (not yet assigned to another group)
        if not sub:
            sub = Submission.query.filter_by(
                activity_id=activity_id,
                student_id=gm.student_id
            ).filter(
                (Submission.group_id == None) | (Submission.group_id == group_id)
            ).first()

        if sub:
            # Update existing submission
            sub.grade       = float(grade)
            sub.feedback    = feedback
            sub.graded_by   = user.id
            sub.graded_at   = datetime.utcnow()
            sub.status      = 'graded'
            sub.group_id    = group_id
            graded_count += 1
        else:
            # Only create a new graded record if student has NO submission at all
            # (don't create if they submitted under a different group)
            any_sub = Submission.query.filter_by(
                activity_id=activity_id,
                student_id=gm.student_id
            ).first()
            if not any_sub:
                new_sub = Submission(
                    activity_id=activity_id,
                    student_id=gm.student_id,
                    grade=float(grade),
                    feedback=feedback,
                    graded_by=user.id,
                    graded_at=datetime.utcnow(),
                    status='graded',
                    group_id=group_id
                )
                db.session.add(new_sub)
                graded_count += 1

    db.session.commit()

    # Notify all graded members via WebSocket + in-app notification
    try:
        from extensions import socketio as _sio
        from notifications import notify
        act_title = activity.title if activity else ''
        for gm in group.members:
            _sio.emit('submission_graded', {
                'student_id':  gm.student_id,
                'activity_id': activity_id,
                'grade':       float(grade),
                'feedback':    feedback or '',
            }, namespace='/')
            try:
                notify(gm.student_id,
                       f'Your submission for "{act_title}" has been graded',
                       f'/activity?id={activity_id}', 'grade')
            except Exception as e:
                print(f'[grade_group notify] {e}')
    except Exception as e:
        print(f'[grade_group emit] {e}')

    return jsonify({
        'message': f'Graded {graded_count} member(s) in group!',
        'grade': grade,
        'group_name': group.name
    }), 200


@classes.route('/<int:class_id>/groups/<int:group_id>/grade', methods=['GET'])
@jwt_required()
def get_group_grade(class_id, group_id):
    """Get current grade for a group's activity submission."""
    from models import Submission
    activity_id = request.args.get('activity_id', type=int)
    if not activity_id:
        return jsonify({'message': 'activity_id is required'}), 400

    group = Group.query.filter_by(id=group_id, class_id=class_id).first()
    if not group:
        return jsonify({'message': 'Group not found!'}), 404

    # Get grade from leader's submission (or first graded member)
    leader_sub = Submission.query.filter_by(
        activity_id=activity_id,
        student_id=group.leader_id,
        status='graded'
    ).first()

    if not leader_sub:
        # fallback: any graded member
        for gm in group.members:
            sub = Submission.query.filter_by(
                activity_id=activity_id,
                student_id=gm.student_id,
                status='graded'
            ).first()
            if sub:
                leader_sub = sub
                break

    if not leader_sub:
        return jsonify({'graded': False}), 200

    return jsonify({
        'graded': True,
        'grade': leader_sub.grade,
        'feedback': leader_sub.feedback,
        'graded_at': (leader_sub.graded_at.isoformat() + 'Z') if leader_sub.graded_at else None
    }), 200


# ===== DELETE CLASS (professor) =====
@classes.route('/<int:class_id>', methods=['DELETE'])
@jwt_required()
def delete_class(class_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    c = Class.query.get(class_id)
    if not c:
        return jsonify({'message': 'Class not found!'}), 404
    if not _is_class_prof(c.id, user.id):
        return jsonify({'message': 'Not authorized!'}), 403
    # Cascade delete all related records
    from models import Activity, Submission, EditedContent, StreamPost, StreamComment, FeedEvent, Group, ClassSession, Announcement
    # Sessions + groups (cascade via relationship handles children)
    for s in ClassSession.query.filter_by(class_id=class_id).all():
        db.session.delete(s)
    for g in Group.query.filter_by(class_id=class_id).all():
        db.session.delete(g)
    # Delete stream posts first (they reference activities via activity_id FK)
    for post in StreamPost.query.filter_by(class_id=class_id).all():
        db.session.delete(post)
    db.session.flush()
    # Delete submissions + edited content for each activity
    for act in Activity.query.filter_by(class_id=class_id).all():
        Submission.query.filter_by(activity_id=act.id).delete()
        EditedContent.query.filter_by(activity_id=act.id).delete()
        db.session.delete(act)
    # Delete remaining related tables
    Announcement.query.filter_by(class_id=class_id).delete()
    ClassMember.query.filter_by(class_id=class_id).delete()
    ClassInvite.query.filter_by(class_id=class_id).delete()
    FeedEvent.query.filter_by(class_id=class_id).delete()
    db.session.delete(c)
    db.session.commit()
    _notify_class_update('deleted', class_id)
    return jsonify({'message': 'Class deleted successfully!'}), 200


# ===== ARCHIVE CLASS (professor) =====
@classes.route('/<int:class_id>/archive', methods=['POST'])
@jwt_required()
def archive_class(class_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    c = Class.query.get(class_id)
    if not c:
        return jsonify({'message': 'Class not found!'}), 404
    if not _is_class_prof(c.id, user.id):
        return jsonify({'message': 'Not authorized!'}), 403
    c.is_archived = not c.is_archived
    db.session.commit()
    status = 'archived' if c.is_archived else 'unarchived'
    _notify_class_update(status, class_id)
    return jsonify({'message': f'Class {status}!', 'is_archived': c.is_archived}), 200


# ===== DUPLICATE CLASS (professor) =====
@classes.route('/<int:class_id>/duplicate', methods=['POST'])
@jwt_required()
def duplicate_class(class_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    c = Class.query.get(class_id)
    if not c:
        return jsonify({'message': 'Class not found!'}), 404
    if not _is_class_prof(c.id, user.id):
        return jsonify({'message': 'Not authorized!'}), 403
    new_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    while Class.query.filter_by(class_code=new_code).first():
        new_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    dup = Class(
        class_name=c.class_name + ' (Copy)',
        subject=c.subject,
        section=c.section,
        class_code=new_code,
        professor_id=user.id,
        theme=c.theme,
        banner_image=c.banner_image
    )
    db.session.add(dup)
    db.session.commit()
    return jsonify({'message': 'Class duplicated!', 'id': dup.id, 'class_code': new_code}), 200


# ===== UNENROLL (student) =====
@classes.route('/<int:class_id>/unenroll', methods=['DELETE'])
@jwt_required()
def unenroll_class(class_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    m = ClassMember.query.filter_by(class_id=class_id, student_id=user.id).first()
    if not m:
        return jsonify({'message': 'You are not a member of this class!'}), 404
    db.session.delete(m)
    db.session.commit()
    return jsonify({'message': 'Successfully unenrolled!'}), 200


# ===== REMOVE STUDENT (professor) =====
@classes.route('/<int:class_id>/students/<int:student_id>', methods=['DELETE'])
@jwt_required()
def remove_student(class_id, student_id):
    user_id = int(get_jwt_identity())
    if not _is_class_prof(class_id, user_id):
        return jsonify({'message': 'Not authorized!'}), 403
    m = ClassMember.query.filter_by(class_id=class_id, student_id=student_id).first()
    if not m:
        return jsonify({'message': 'Student not found in this class!'}), 404
    db.session.delete(m)
    db.session.commit()
    return jsonify({'message': 'Student removed!'}), 200


# ============================================================
# ANALYTICS
# ============================================================

@classes.route('/<int:class_id>/analytics', methods=['GET'])
@jwt_required()
def get_analytics(class_id):
    from models import Activity, Submission, StreamPost
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)

    c = Class.query.get(class_id)
    if not c:
        return jsonify({'message': 'Class not found!'}), 404

    # Only include activities that have been posted to the stream
    posted_ids = {
        sp.activity_id
        for sp in StreamPost.query.filter_by(class_id=class_id).all()
        if sp.activity_id is not None
    }
    activities = Activity.query.filter(
        Activity.class_id == class_id,
        Activity.id.in_(posted_ids)
    ).order_by(Activity.created_at.asc()).all() if posted_ids else []
    act_labels = {a.id: f'A{i+1}' for i, a in enumerate(activities)}
    act_list = [{'id': a.id, 'label': act_labels[a.id], 'title': a.title} for a in activities]

    if user.role == 'professor':
        if not _is_class_prof(class_id, user_id):
            return jsonify({'message': 'Not authorized!'}), 403

        members = ClassMember.query.filter_by(class_id=class_id).all()
        students_data = []
        all_averages = []

        for m in members:
            s = User.query.get(m.student_id)
            if not s:
                continue

            grades = {}
            graded_scores = []
            for a in activities:
                sub = Submission.query.filter_by(
                    activity_id=a.id, student_id=s.id, status='graded'
                ).first()
                if sub and sub.grade is not None:
                    grades[a.id] = round(sub.grade, 2)
                    graded_scores.append(sub.grade)
                else:
                    grades[a.id] = None

            avg = round(sum(graded_scores) / len(graded_scores), 2) if graded_scores else None
            if avg is not None:
                all_averages.append(avg)

            # Surname-first sort key
            surname = s.last_name.strip().lower() if s.last_name else s.full_name.lower()
            students_data.append({
                'student_number': s.student_number or '',
                'full_name': s.full_name,
                'last_name': surname,
                'grades': grades,
                'average': avg
            })

        # Sort A-Z by surname
        students_data.sort(key=lambda x: x['last_name'])
        for s in students_data:
            del s['last_name']

        # Per-activity averages (for bar chart)
        act_averages = []
        for a in activities:
            scores = []
            for m in members:
                sub = Submission.query.filter_by(
                    activity_id=a.id, student_id=m.student_id, status='graded'
                ).first()
                if sub and sub.grade is not None:
                    scores.append(sub.grade)
            act_averages.append(round(sum(scores)/len(scores), 2) if scores else None)

        # Submission rate
        total_possible = len(members) * len(activities)
        total_submitted = Submission.query.join(Activity).filter(
            Activity.class_id == class_id
        ).count()
        submission_rate = round((total_submitted / total_possible * 100), 1) if total_possible else 0

        # Score distribution buckets
        all_grades = []
        for m in members:
            for a in activities:
                sub = Submission.query.filter_by(
                    activity_id=a.id, student_id=m.student_id, status='graded'
                ).first()
                if sub and sub.grade is not None:
                    all_grades.append(sub.grade)

        distribution = {
            '90-100': sum(1 for g in all_grades if g >= 90),
            '80-89':  sum(1 for g in all_grades if 80 <= g < 90),
            '70-79':  sum(1 for g in all_grades if 70 <= g < 80),
            '60-69':  sum(1 for g in all_grades if 60 <= g < 70),
            'Below 60': sum(1 for g in all_grades if g < 60),
        }

        return jsonify({
            'role': 'professor',
            'activities': act_list,
            'students': students_data,
            'act_averages': act_averages,
            'class_average': round(sum(all_averages)/len(all_averages), 2) if all_averages else None,
            'highest': max(all_averages) if all_averages else None,
            'lowest': min(all_averages) if all_averages else None,
            'submission_rate': submission_rate,
            'distribution': distribution,
            'class_name': c.class_name,
            'subject': c.subject,
            'section': c.section,
            'professor_name': user.full_name,
        }), 200

    else:
        # Student view — personal grades only
        membership = ClassMember.query.filter_by(class_id=class_id, student_id=user_id).first()
        if not membership:
            return jsonify({'message': 'Not enrolled!'}), 403

        grades = []
        graded_scores = []
        for a in activities:
            sub = Submission.query.filter_by(
                activity_id=a.id, student_id=user_id, status='graded'
            ).first()
            grade_val = round(sub.grade, 2) if sub and sub.grade is not None else None
            if grade_val is not None:
                graded_scores.append(grade_val)
            grades.append({
                'activity_id': a.id,
                'label': act_labels[a.id],
                'title': a.title,
                'grade': grade_val,
                'status': sub.status if sub else 'not_submitted',
                'due_date': a.due_date.strftime('%b %d, %Y') if a.due_date else '—'
            })

        my_avg = round(sum(graded_scores)/len(graded_scores), 2) if graded_scores else None
        return jsonify({
            'role': 'student',
            'activities': act_list,
            'grades': grades,
            'my_average': my_avg,
            'best': max(graded_scores) if graded_scores else None,
            'lowest': min(graded_scores) if graded_scores else None,
            'completed': len(graded_scores),
            'total': len(activities),
        }), 200


# ============================================================
# INVITES
# ============================================================

def _is_class_prof(class_id, user_id):
    c = Class.query.get(class_id)
    if c and c.professor_id == user_id:
        return True
    return ClassTeacher.query.filter_by(class_id=class_id, teacher_id=user_id).first() is not None


# ===== LOOKUP STUDENT (before sending invite) =====
@classes.route('/<int:class_id>/invite/lookup', methods=['GET'])
@jwt_required()
def invite_lookup(class_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if user.role != 'professor':
        return jsonify({'message': 'Only professors can invite students!'}), 403
    c = Class.query.get(class_id)
    if not c or not _is_class_prof(class_id, user.id):
        return jsonify({'message': 'Not authorized!'}), 403

    sn = request.args.get('student_number', '').strip()
    if not sn:
        return jsonify({'message': 'Student number required!'}), 400

    student = User.query.filter_by(student_number=sn, role='student').first()
    if not student:
        return jsonify({'message': 'Student not found!'}), 404

    if ClassMember.query.filter_by(class_id=class_id, student_id=student.id).first():
        return jsonify({'message': 'Student is already enrolled in this class!'}), 400

    if ClassInvite.query.filter_by(class_id=class_id, student_id=student.id, status='pending').first():
        return jsonify({'message': 'An invite is already pending for this student!'}), 400

    return jsonify({
        'id': student.id,
        'full_name': student.full_name,
        'student_number': student.student_number,
        'avatar': student.avatar or ''
    }), 200


# ===== SEND INVITE =====
@classes.route('/<int:class_id>/invite', methods=['POST'])
@jwt_required()
def send_invite(class_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if user.role != 'professor':
        return jsonify({'message': 'Only professors can invite students!'}), 403
    c = Class.query.get(class_id)
    if not c or not _is_class_prof(c.id, user.id):
        return jsonify({'message': 'Not authorized!'}), 403

    data = request.get_json() or {}
    student_id = data.get('student_id')
    if not student_id:
        return jsonify({'message': 'Student ID required!'}), 400

    student = User.query.get(int(student_id))
    if not student or student.role != 'student':
        return jsonify({'message': 'Student not found!'}), 404

    if ClassMember.query.filter_by(class_id=class_id, student_id=student.id).first():
        return jsonify({'message': 'Student is already enrolled!'}), 400
    if ClassInvite.query.filter_by(class_id=class_id, student_id=student.id, status='pending').first():
        return jsonify({'message': 'Invite already pending!'}), 400

    invite = ClassInvite(class_id=class_id, student_id=student.id, invited_by=user.id)
    db.session.add(invite)
    db.session.commit()

    try:
        from notifications import notify
        notify(student.id,
               f'{user.full_name} invited you to join {c.class_name}',
               f'invite:{invite.id}',
               'invite')
    except Exception as e:
        print(f'[invite] notify error: {e}')

    return jsonify({'message': f'Invite sent to {student.full_name}!', 'invite_id': invite.id}), 201


# ===== GET PENDING INVITES FOR CLASS (prof) =====
@classes.route('/<int:class_id>/invites', methods=['GET'])
@jwt_required()
def get_class_invites(class_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if user.role != 'professor':
        return jsonify({'message': 'Not authorized!'}), 403
    c = Class.query.get(class_id)
    if not c or not _is_class_prof(c.id, user.id):
        return jsonify({'message': 'Not authorized!'}), 403

    invites = ClassInvite.query.filter_by(class_id=class_id, status='pending').all()
    result = []
    for inv in invites:
        s = User.query.get(inv.student_id)
        if s:
            result.append({
                'invite_id': inv.id,
                'student_id': s.id,
                'full_name': s.full_name,
                'student_number': s.student_number or '',
                'avatar': s.avatar or '',
                'sent_at': inv.created_at.strftime('%b %d, %Y')
            })
    return jsonify(result), 200


# ===== CANCEL INVITE (prof) =====
@classes.route('/<int:class_id>/invites/<int:invite_id>', methods=['DELETE'])
@jwt_required()
def cancel_invite(class_id, invite_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    c = Class.query.get(class_id)
    if not c or not _is_class_prof(c.id, user.id):
        return jsonify({'message': 'Not authorized!'}), 403

    invite = ClassInvite.query.filter_by(id=invite_id, class_id=class_id).first()
    if not invite:
        return jsonify({'message': 'Invite not found!'}), 404

    db.session.delete(invite)
    db.session.commit()
    return jsonify({'message': 'Invite cancelled!'}), 200


# ===== LOOKUP TEACHER (before sending invite) =====
@classes.route('/<int:class_id>/invite/lookup-teacher', methods=['GET'])
@jwt_required()
def invite_lookup_teacher(class_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if user.role != 'professor':
        return jsonify({'message': 'Only professors can invite teachers!'}), 403
    if not _is_class_prof(class_id, user.id):
        return jsonify({'message': 'Not authorized!'}), 403
    email = request.args.get('email', '').strip().lower()
    if not email:
        return jsonify({'message': 'Email is required!'}), 400
    teacher = User.query.filter(User.email.ilike(email), User.role == 'professor').first()
    if not teacher:
        return jsonify({'message': 'No professor found with that email!'}), 404
    if teacher.id == user.id:
        return jsonify({'message': 'You cannot invite yourself!'}), 400
    c = Class.query.get(class_id)
    if c and c.professor_id == teacher.id:
        return jsonify({'message': 'This professor is already the class owner!'}), 400
    if ClassTeacher.query.filter_by(class_id=class_id, teacher_id=teacher.id).first():
        return jsonify({'message': 'This professor is already a co-teacher!'}), 400
    if ClassInvite.query.filter_by(class_id=class_id, student_id=teacher.id, invite_type='teacher', status='pending').first():
        return jsonify({'message': 'An invite is already pending for this professor!'}), 400
    return jsonify({'id': teacher.id, 'full_name': teacher.full_name, 'email': teacher.email, 'avatar': teacher.avatar or ''}), 200


@classes.route('/<int:class_id>/invite-teacher', methods=['POST'])
@jwt_required()
def send_teacher_invite(class_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if user.role != 'professor':
        return jsonify({'message': 'Only professors can invite teachers!'}), 403
    if not _is_class_prof(class_id, user.id):
        return jsonify({'message': 'Not authorized!'}), 403
    data = request.get_json() or {}
    teacher_id = data.get('teacher_id')
    teacher = User.query.get(teacher_id)
    if not teacher or teacher.role != 'professor':
        return jsonify({'message': 'Teacher not found!'}), 404
    c = Class.query.get(class_id)
    if not c:
        return jsonify({'message': 'Class not found!'}), 404
    if ClassTeacher.query.filter_by(class_id=class_id, teacher_id=teacher.id).first():
        return jsonify({'message': 'Already a co-teacher!'}), 400
    if ClassInvite.query.filter_by(class_id=class_id, student_id=teacher.id, invite_type='teacher', status='pending').first():
        return jsonify({'message': 'Invite already pending!'}), 400
    invite = ClassInvite(class_id=class_id, student_id=teacher.id, invited_by=user.id, invite_type='teacher')
    db.session.add(invite)
    db.session.commit()
    try:
        from notifications import notify
        notify(teacher.id,
               f'{user.full_name} invited you to co-teach {c.class_name}',
               f'invite:{invite.id}',
               'invite')
    except Exception as e:
        print(f'[invite-teacher] notify error: {e}')
    return jsonify({'message': f'Invite sent to {teacher.full_name}!', 'invite_id': invite.id}), 201


@classes.route('/<int:class_id>/teacher-invites', methods=['GET'])
@jwt_required()
def get_teacher_invites(class_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if not _is_class_prof(class_id, user.id):
        return jsonify([]), 200
    invites = ClassInvite.query.filter_by(class_id=class_id, invite_type='teacher', status='pending').all()
    result = []
    for inv in invites:
        t = User.query.get(inv.student_id)
        if t:
            result.append({
                'invite_id': inv.id,
                'teacher_id': t.id,
                'full_name': t.full_name,
                'email': t.email or '',
                'avatar': t.avatar or '',
                'sent_at': inv.created_at.strftime('%b %d, %Y')
            })
    return jsonify(result), 200


# ===== RESPOND TO INVITE (student: accept/decline) =====
@classes.route('/invites/<int:invite_id>/respond', methods=['POST'])
@jwt_required()
def respond_invite(invite_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    invite = ClassInvite.query.get(invite_id)
    if not invite:
        return jsonify({'message': 'Invite not found!'}), 404
    if invite.student_id != user.id:
        return jsonify({'message': 'Not authorized!'}), 403
    if invite.status != 'pending':
        return jsonify({'message': 'This invite has already been responded to.'}), 400

    data = request.get_json() or {}
    action = data.get('action')
    if action not in ('accept', 'decline'):
        return jsonify({'message': 'Invalid action!'}), 400

    invite.status = 'accepted' if action == 'accept' else 'declined'

    if action == 'accept':
        c = Class.query.get(invite.class_id)
        if invite.invite_type == 'teacher':
            if not ClassTeacher.query.filter_by(class_id=invite.class_id, teacher_id=user.id).first():
                db.session.add(ClassTeacher(class_id=invite.class_id, teacher_id=user.id))
        else:
            if not ClassMember.query.filter_by(class_id=invite.class_id, student_id=user.id).first():
                db.session.add(ClassMember(class_id=invite.class_id, student_id=user.id))
        try:
            from notifications import notify
            from extensions import socketio
            notify(c.professor_id,
                   f'{user.full_name} accepted your invite to co-teach {c.class_name}' if invite.invite_type == 'teacher' else f'{user.full_name} accepted your invite to {c.class_name}',
                   f'/class_detail?id={c.id}',
                   'joined')
            socketio.emit('student_joined', {'class_id': invite.class_id}, namespace='/')
        except Exception as e:
            print(f'[invite] accept notify error: {e}')

    db.session.commit()
    return jsonify({
        'message': 'Invite accepted!' if action == 'accept' else 'Invite declined.',
        'class_id': invite.class_id,
        'class_name': c.class_name if c else ''
    }), 200


# ===== GET PENDING INVITES FOR STUDENT/PROFESSOR =====
@classes.route('/invites/pending', methods=['GET'])
@jwt_required()
def get_pending_invites():
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    invites = ClassInvite.query.filter_by(student_id=user.id, status='pending').all()
    result = []
    for inv in invites:
        c = Class.query.get(inv.class_id)
        inviter = User.query.get(inv.invited_by) if c else None
        if c and inviter:
            result.append({
                'invite_id':      inv.id,
                'class_id':       c.id,
                'class_name':     c.class_name,
                'subject':        c.subject,
                'section':        c.section,
                'professor_name': inviter.full_name,
                'invite_type':    inv.invite_type or 'student',
                'sent_at':        inv.created_at.strftime('%b %d, %Y')
            })
    return jsonify(result), 200
