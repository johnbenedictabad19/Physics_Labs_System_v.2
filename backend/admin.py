from flask import Blueprint, request, jsonify
from database import db
from models import User, Class, Activity, Submission, ClassMember, Announcement, StreamPost, Group, ClassSession, FeedEvent, EditedContent, ClassInvite, ClassTeacher
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_bcrypt import Bcrypt

admin = Blueprint('admin', __name__)
bcrypt = Bcrypt()


# ── HELPER: verify caller is admin ──────────────────────────
def get_admin_or_403():
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)
    if not user or user.role != 'admin':
        return None, jsonify({'message': 'Admin access required!'}), 403
    return user, None, None


# ============================================================
# DASHBOARD STATS
# ============================================================
@admin.route('/admin/stats', methods=['GET'])
@jwt_required()
def get_stats():
    user, err, code = get_admin_or_403()
    if err: return err, code

    total_users       = User.query.filter(User.role != 'admin').count()
    total_professors  = User.query.filter_by(role='professor').count()
    total_students    = User.query.filter_by(role='student').count()
    pending_approvals = User.query.filter_by(role='professor', status='pending').count()
    total_classes     = Class.query.count()
    total_activities  = Activity.query.count()
    total_submissions = Submission.query.count()

    return jsonify({
        'total_users':       total_users,
        'total_professors':  total_professors,
        'total_students':    total_students,
        'pending_approvals': pending_approvals,
        'total_classes':     total_classes,
        'total_activities':  total_activities,
        'total_submissions': total_submissions
    }), 200


# ============================================================
# USERS
# ============================================================

# ── Get all users (exclude admins) ──
@admin.route('/admin/users', methods=['GET'])
@jwt_required()
def get_all_users():
    user, err, code = get_admin_or_403()
    if err: return err, code

    role_filter   = request.args.get('role')    # optional: professor | student
    status_filter = request.args.get('status')  # optional: active | pending | deactivated
    search        = request.args.get('search', '').strip().lower()

    query = User.query.filter(User.role != 'admin')
    if role_filter:   query = query.filter_by(role=role_filter)
    if status_filter: query = query.filter_by(status=status_filter)

    users = query.order_by(User.created_at.desc()).all()

    # Search filter (name or email)
    if search:
        users = [u for u in users if search in u.full_name.lower() or search in (u.email or '').lower() or search in (u.student_number or '').lower()]

    return jsonify([{
        'id':             u.id,
        'full_name':      u.full_name,
        'first_name':     u.first_name,
        'last_name':      u.last_name,
        'middle_initial': u.middle_initial or '',
        'email':          u.email or '',
        'student_number': u.student_number or '',
        'role':           u.role,
        'status':         u.status,
        'is_active':      u.is_active,
        'avatar':         u.avatar or '',
        'joined_at':      u.created_at.isoformat() if u.created_at else None
    } for u in users]), 200


# ── Get pending professor approvals ──
@admin.route('/admin/pending-professors', methods=['GET'])
@jwt_required()
def get_pending_professors():
    user, err, code = get_admin_or_403()
    if err: return err, code

    pending = User.query.filter_by(role='professor', status='pending').order_by(User.created_at.asc()).all()

    return jsonify([{
        'id':        u.id,
        'full_name': u.full_name,
        'email':     u.email or '',
        'joined_at': u.created_at.isoformat() if u.created_at else None
    } for u in pending]), 200


# ── Approve professor ──
@admin.route('/admin/users/<int:user_id>/approve', methods=['POST'])
@jwt_required()
def approve_professor(user_id):
    user, err, code = get_admin_or_403()
    if err: return err, code

    target = User.query.get(user_id)
    if not target:
        return jsonify({'message': 'User not found!'}), 404
    if target.role != 'professor':
        return jsonify({'message': 'User is not a professor!'}), 400

    target.status    = 'active'
    target.is_active = True
    db.session.commit()

    return jsonify({'message': f'{target.full_name} has been approved!'}), 200


# ── Reject / delete pending professor ──
@admin.route('/admin/users/<int:user_id>/reject', methods=['DELETE'])
@jwt_required()
def reject_professor(user_id):
    user, err, code = get_admin_or_403()
    if err: return err, code

    target = User.query.get(user_id)
    if not target:
        return jsonify({'message': 'User not found!'}), 404

    db.session.delete(target)
    db.session.commit()

    return jsonify({'message': f'{target.full_name} has been rejected and removed.'}), 200


# ── Deactivate user ──
@admin.route('/admin/users/<int:user_id>/deactivate', methods=['POST'])
@jwt_required()
def deactivate_user(user_id):
    user, err, code = get_admin_or_403()
    if err: return err, code

    target = User.query.get(user_id)
    if not target:
        return jsonify({'message': 'User not found!'}), 404

    target.is_active = False
    target.status    = 'deactivated'
    db.session.commit()

    return jsonify({'message': f'{target.full_name} has been deactivated.'}), 200


# ── Reactivate user ──
@admin.route('/admin/users/<int:user_id>/activate', methods=['POST'])
@jwt_required()
def activate_user(user_id):
    user, err, code = get_admin_or_403()
    if err: return err, code

    target = User.query.get(user_id)
    if not target:
        return jsonify({'message': 'User not found!'}), 404

    target.is_active = True
    target.status    = 'active'
    db.session.commit()

    return jsonify({'message': f'{target.full_name} has been reactivated.'}), 200


# ── Permanently delete user ──
@admin.route('/admin/users/<int:user_id>/delete', methods=['DELETE'])
@jwt_required()
def delete_user(user_id):
    user, err, code = get_admin_or_403()
    if err: return err, code

    target = User.query.get(user_id)
    if not target:
        return jsonify({'message': 'User not found!'}), 404

    try:
        from models import (ClassMember, Notification, StreamComment, StreamPost,
                            Announcement, GroupMember, Group, SessionAttendance,
                            ClassSession, ClassInvite, ClassTeacher, Submission,
                            Activity, EditedContent, Class)
        from sqlalchemy import or_

        name = target.full_name

        # 1. Notifications
        Notification.query.filter_by(user_id=user_id).delete()

        # 2. Stream comments by this user
        StreamComment.query.filter_by(user_id=user_id).delete()

        # 3. Group memberships (as member) & nullify leader
        GroupMember.query.filter_by(student_id=user_id).delete()
        Group.query.filter_by(leader_id=user_id).update({'leader_id': None})

        # 4. Session attendance (as student)
        SessionAttendance.query.filter_by(student_id=user_id).delete()

        # 5. Class memberships (as student)
        ClassMember.query.filter_by(student_id=user_id).delete()

        # 6. Class invites involving this user
        ClassInvite.query.filter(
            or_(ClassInvite.student_id == user_id, ClassInvite.invited_by == user_id)
        ).delete(synchronize_session='fetch')

        # 7. Co-teacher records
        ClassTeacher.query.filter_by(teacher_id=user_id).delete()

        # 8. Nullify graded_by on submissions this user graded
        Submission.query.filter_by(graded_by=user_id).update({'graded_by': None})

        # 9. Delete submissions by this student
        Submission.query.filter_by(student_id=user_id).delete()

        # 10. Stream posts & announcements by this user (outside owned classes)
        StreamPost.query.filter_by(posted_by_id=user_id).delete()
        Announcement.query.filter_by(posted_by_id=user_id).delete()

        # 11. Class sessions created by this user (outside owned classes)
        for s in ClassSession.query.filter_by(created_by=user_id).all():
            db.session.delete(s)  # cascade deletes attendance

        # 12. If professor: delete all owned classes and their contents
        for cls in Class.query.filter_by(professor_id=user_id).all():
            cid = cls.id
            ClassMember.query.filter_by(class_id=cid).delete()
            ClassInvite.query.filter_by(class_id=cid).delete()
            ClassTeacher.query.filter_by(class_id=cid).delete()
            Announcement.query.filter_by(class_id=cid).delete()
            StreamPost.query.filter_by(class_id=cid).delete()
            GroupMember.query.filter(
                GroupMember.group_id.in_(
                    db.session.query(Group.id).filter_by(class_id=cid)
                )
            ).delete(synchronize_session='fetch')
            Group.query.filter_by(class_id=cid).delete()
            for session in ClassSession.query.filter_by(class_id=cid).all():
                db.session.delete(session)
            for act in Activity.query.filter_by(class_id=cid).all():
                EditedContent.query.filter_by(activity_id=act.id).delete()
                Submission.query.filter_by(activity_id=act.id).delete()
                db.session.delete(act)
            db.session.delete(cls)

        # 13. Activities uploaded by user in other classes
        for act in Activity.query.filter_by(uploaded_by=user_id).all():
            EditedContent.query.filter_by(activity_id=act.id).delete()
            Submission.query.filter_by(activity_id=act.id).delete()
            db.session.delete(act)

        db.session.delete(target)
        db.session.commit()
        return jsonify({'message': f'{name} has been permanently deleted.'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'message': f'Delete failed: {str(e)}'}), 500


# ── Reset user password ──
@admin.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
@jwt_required()
def reset_password(user_id):
    user, err, code = get_admin_or_403()
    if err: return err, code

    target = User.query.get(user_id)
    if not target:
        return jsonify({'message': 'User not found!'}), 404

    data         = request.get_json() or {}
    new_password = data.get('new_password', '').strip()

    from auth import _validate_password
    pw_error = _validate_password(new_password)
    if pw_error:
        return jsonify({'message': pw_error}), 400

    target.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    db.session.commit()

    return jsonify({'message': f'Password for {target.full_name} has been reset.'}), 200


# ============================================================
# CLASSES
# ============================================================

# ── Get all classes ──
@admin.route('/admin/classes', methods=['GET'])
@jwt_required()
def get_all_classes():
    user, err, code = get_admin_or_403()
    if err: return err, code

    search = request.args.get('search', '').strip().lower()
    classes = Class.query.order_by(Class.created_at.desc()).all()

    result = []
    for c in classes:
        professor   = User.query.get(c.professor_id)
        member_count = ClassMember.query.filter_by(class_id=c.id).count()
        activity_count = Activity.query.filter_by(class_id=c.id).count()

        if search and search not in c.class_name.lower() and search not in c.subject.lower():
            continue

        result.append({
            'id':             c.id,
            'class_name':     c.class_name,
            'subject':        c.subject,
            'section':        c.section,
            'class_code':     c.class_code,
            'professor_name': professor.full_name if professor else '—',
            'professor_email': professor.email if professor else '—',
            'member_count':   member_count,
            'activity_count': activity_count,
            'created_at':     c.created_at.isoformat() if c.created_at else None,
            'is_archived':    c.is_archived or False
        })

    return jsonify(result), 200


# ── Archive (delete) class ──
@admin.route('/admin/classes/<int:class_id>/delete', methods=['DELETE'])
@jwt_required()
def delete_class(class_id):
    user, err, code = get_admin_or_403()
    if err: return err, code

    target = Class.query.get(class_id)
    if not target:
        return jsonify({'message': 'Class not found!'}), 404

    class_name = target.class_name

    try:
        # 1. Submissions first — has FK to both activities and groups
        activity_ids = [a.id for a in Activity.query.filter_by(class_id=class_id).with_entities(Activity.id).all()]
        if activity_ids:
            Submission.query.filter(Submission.activity_id.in_(activity_ids)).delete(synchronize_session=False)
            EditedContent.query.filter(EditedContent.activity_id.in_(activity_ids)).delete(synchronize_session=False)

        # 2. Stream posts + comments (cascade via relationship)
        for p in StreamPost.query.filter_by(class_id=class_id).all():
            db.session.delete(p)

        # 3. Activities (submissions already gone)
        Activity.query.filter_by(class_id=class_id).delete(synchronize_session=False)

        # 4. Groups + members (cascade via relationship)
        for g in Group.query.filter_by(class_id=class_id).all():
            db.session.delete(g)

        # 5. Sessions + attendance (cascade via relationship)
        for s in ClassSession.query.filter_by(class_id=class_id).all():
            db.session.delete(s)

        Announcement.query.filter_by(class_id=class_id).delete()
        ClassMember.query.filter_by(class_id=class_id).delete()
        ClassInvite.query.filter_by(class_id=class_id).delete()
        ClassTeacher.query.filter_by(class_id=class_id).delete()
        FeedEvent.query.filter_by(class_id=class_id).delete()

        db.session.delete(target)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'message': f'Delete failed: {str(e)}'}), 500

    return jsonify({'message': f'Class "{class_name}" has been deleted.'}), 200


# ============================================================
# SEED DEFAULT ADMIN (run once)
# ============================================================
def seed_admin(app):
    with app.app_context():
        existing = User.query.filter_by(role='admin').first()
        if not existing:
            import os
            admin_password = os.environ.get('ADMIN_PASSWORD')
            if not admin_password:
                print('[seed_admin] ADMIN_PASSWORD not set — skipping admin seed')
                return
            hashed = bcrypt.generate_password_hash(admin_password).decode('utf-8')
            admin_user = User(
                last_name      = 'Admin',
                first_name     = 'System',
                middle_initial = None,
                email          = 'admin@physlab.com',
                student_number = None,
                birthday       = None,
                password       = hashed,
                role           = 'admin',
                status         = 'active',
                is_active      = True
            )
            db.session.add(admin_user)
            db.session.commit()
            print('✅ Default admin created: admin@physlab.com')
        else:
            print('ℹ️  Admin already exists.')


# ── Archive class ──
@admin.route('/admin/classes/<int:class_id>/archive', methods=['POST'])
@jwt_required()
def archive_class(class_id):
    user, err, code = get_admin_or_403()
    if err: return err, code

    target = Class.query.get(class_id)
    if not target:
        return jsonify({'message': 'Class not found!'}), 404
    if target.is_archived:
        return jsonify({'message': 'Class is already archived!'}), 400

    target.is_archived = True
    db.session.commit()
    return jsonify({'message': f'Class "{target.class_name}" has been archived.'}), 200


# ── Unarchive class ──
@admin.route('/admin/classes/<int:class_id>/unarchive', methods=['POST'])
@jwt_required()
def unarchive_class(class_id):
    user, err, code = get_admin_or_403()
    if err: return err, code

    target = Class.query.get(class_id)
    if not target:
        return jsonify({'message': 'Class not found!'}), 404

    target.is_archived = False
    db.session.commit()
    return jsonify({'message': f'Class "{target.class_name}" has been restored.'}), 200