import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from models import StreamPost, User, StreamComment, Activity, User, ClassMember, Class
from datetime import datetime

stream = Blueprint('stream', __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')

def _delete_activity_cascade(activity):
    """Delete an activity and all its related records (submissions, edited content)."""
    from models import Submission, EditedContent
    Submission.query.filter_by(activity_id=activity.id).delete()
    EditedContent.query.filter_by(activity_id=activity.id).delete()
    if activity.filename:
        filepath = os.path.join(UPLOAD_FOLDER, activity.filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except:
                pass
    db.session.delete(activity)


def _notify_stream(class_id):
    try:
        from extensions import socketio
        socketio.emit('stream_update', {'class_id': class_id}, namespace='/')
    except Exception as e:
        print(f'[stream] notify error: {e}')


def format_post(post, current_user_id):
    author = User.query.get(post.posted_by_id)
    activity = None
    if post.activity_id:
        a = Activity.query.get(post.activity_id)
        if a:
            activity = {
                'id': a.id,
                'title': a.title,
                'file_type': a.file_type,
                'due_date_display': a.due_date.strftime('%b %d, %Y %I:%M %p') if a.due_date else None,
                'is_overdue': bool(a.due_date and a.due_date < datetime.utcnow())
            }

    comments = []
    for c in sorted(post.comments, key=lambda x: x.created_at):
        commenter = User.query.get(c.user_id)
        comments.append({
            'id':         c.id,
            'user_id':    c.user_id,
            'user_name':  commenter.full_name if commenter else 'Unknown',
            'user_role':  commenter.role if commenter else '',
            'avatar':     commenter.avatar or '' if commenter else '',
            'message':    c.message,
            'created_at': c.created_at.strftime('%b %d, %Y %I:%M %p'),
            'is_mine':    c.user_id == current_user_id
        })

    return {
        'id':            post.id,
        'post_type':     post.post_type,
        'message':       post.message,
        'activity':      activity,
        'posted_by_id':  post.posted_by_id,
        'posted_by':     author.full_name if author else 'Unknown',
        'avatar':        author.avatar or '' if author else '',
        'is_mine':       post.posted_by_id == current_user_id,
        'created_at':    post.created_at.strftime('%b %d, %Y %I:%M %p'),
        'comments':      comments,
        'comment_count': len(comments)
    }


# ===== GET STREAM =====
@stream.route('/<int:class_id>/stream', methods=['GET'])
@jwt_required()
def get_stream(class_id):
    user_id = int(get_jwt_identity())
    posts = (StreamPost.query
             .filter_by(class_id=class_id)
             .order_by(StreamPost.created_at.desc())
             .all())
    return jsonify([format_post(p, user_id) for p in posts]), 200


# ===== CREATE POST =====
@stream.route('/<int:class_id>/stream', methods=['POST'])
@jwt_required()
def create_post(class_id):
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if user.role != 'professor':
        return jsonify({'message': 'Only professors can post!'}), 403

    data        = request.get_json()
    message     = (data.get('message') or '').strip()
    activity_id = data.get('activity_id')
    post_type   = data.get('post_type', 'announcement')

    if not message and not activity_id:
        return jsonify({'message': 'Post must have a message or an activity!'}), 400

    if activity_id:
        act = Activity.query.get(activity_id)
        if not act or act.class_id != class_id:
            return jsonify({'message': 'Invalid activity!'}), 400

    post = StreamPost(
        class_id=class_id,
        posted_by_id=user_id,
        post_type=post_type,
        message=message or None,
        activity_id=activity_id or None
    )
    db.session.add(post)
    db.session.commit()
    _notify_stream(class_id)
    # Notify all students in class
    try:
        from notifications import notify
        students = ClassMember.query.filter_by(class_id=class_id).all()
        label = f'New activity: "{act.title}"' if activity_id else f'{user.full_name} posted an announcement'
        for s in students:
            notify(s.student_id, label, f'/class_detail?id={class_id}', 'post')
    except Exception:
        pass
    return jsonify(format_post(post, user_id)), 201


# ===== DELETE POST =====
@stream.route('/<int:class_id>/stream/<int:post_id>', methods=['DELETE'])
@jwt_required()
def delete_post(class_id, post_id):
    from models import Class
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    post = StreamPost.query.get(post_id)
    if not post or post.class_id != class_id:
        return jsonify({'message': 'Post not found!'}), 404
    # Professor can delete any post in their class; students can only delete their own
    if user.role == 'professor':
        cls = Class.query.get(class_id)
        if not cls or cls.professor_id != user_id:
            return jsonify({'message': 'Not authorized!'}), 403
    else:
        if post.posted_by_id != user_id:
            return jsonify({'message': 'Not authorized!'}), 403
    # If post has an attached activity, null out FK first then delete activity
    if post.activity_id:
        activity = Activity.query.get(post.activity_id)
        post.activity_id = None
        db.session.flush()
        if activity:
            _delete_activity_cascade(activity)

    db.session.delete(post)
    db.session.commit()
    _notify_stream(class_id)
    return jsonify({'message': 'Post deleted!'}), 200


# ===== ADD COMMENT =====
@stream.route('/<int:class_id>/stream/<int:post_id>/comments', methods=['POST'])
@jwt_required()
def add_comment(class_id, post_id):
    user_id = int(get_jwt_identity())
    post = StreamPost.query.get(post_id)
    if not post or post.class_id != class_id:
        return jsonify({'message': 'Post not found!'}), 404

    data    = request.get_json()
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'message': 'Comment cannot be empty!'}), 400

    comment = StreamComment(post_id=post_id, user_id=user_id, message=message)
    db.session.add(comment)
    db.session.commit()
    _notify_stream(class_id)
    # Notify post owner (not self)
    try:
        from notifications import notify
        if post.posted_by_id != user_id:
            commenter = User.query.get(user_id)
            notify(post.posted_by_id,
                   f'{commenter.full_name} commented on your post',
                   f'/class_detail?id={class_id}', 'comment')
    except Exception:
        pass

    user = User.query.get(user_id)
    return jsonify({
        'id':         comment.id,
        'user_id':    user_id,
        'user_name':  user.full_name,
        'user_role':  user.role,
        'avatar':     user.avatar or '',
        'message':    comment.message,
        'created_at': comment.created_at.strftime('%b %d, %Y %I:%M %p'),
        'is_mine':    True
    }), 201


# ===== DELETE COMMENT =====
@stream.route('/<int:class_id>/stream/<int:post_id>/comments/<int:comment_id>', methods=['DELETE'])
@jwt_required()
def delete_comment(class_id, post_id, comment_id):
    user_id = int(get_jwt_identity())
    user    = User.query.get(user_id)
    comment = StreamComment.query.get(comment_id)
    if not comment or comment.post_id != post_id:
        return jsonify({'message': 'Comment not found!'}), 404
    if comment.user_id != user_id and user.role != 'professor':
        return jsonify({'message': 'Not authorized!'}), 403
    db.session.delete(comment)
    db.session.commit()
    _notify_stream(class_id)
    return jsonify({'message': 'Comment deleted!'}), 200