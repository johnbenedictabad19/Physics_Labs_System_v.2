from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from models import Notification, User

notifications_bp = Blueprint('notifications', __name__)


def notify(user_id, message, link, notif_type):
    """Create a notification and push it in real-time."""
    try:
        user = User.query.get(user_id)
        if user and user.notifications_enabled is False:
            return
        n = Notification(user_id=user_id, message=message, link=link, notif_type=notif_type)
        db.session.add(n)
        db.session.commit()
        from extensions import socketio
        payload = {
            'id':      n.id,
            'user_id': user_id,
            'message': message,
            'link':    link,
            'type':    notif_type,
            'ts':      n.created_at.isoformat() + 'Z'
        }
        socketio.emit('new_notification', payload, namespace='/')
    except Exception as e:
        print(f'[notify] error: {e}')


@notifications_bp.route('/', methods=['GET'])
@jwt_required()
def get_notifications():
    user_id = int(get_jwt_identity())
    notifs = Notification.query.filter_by(user_id=user_id)\
        .order_by(Notification.created_at.desc()).limit(50).all()
    return jsonify([{
        'id':      n.id,
        'message': n.message,
        'link':    n.link,
        'type':    n.notif_type,
        'is_read': n.is_read,
        'ts':      n.created_at.isoformat() + 'Z'
    } for n in notifs])


@notifications_bp.route('/read-all', methods=['POST'])
@jwt_required()
def mark_all_read():
    user_id = int(get_jwt_identity())
    Notification.query.filter_by(user_id=user_id, is_read=False)\
        .update({'is_read': True})
    db.session.commit()
    return jsonify({'message': 'All marked as read'})


@notifications_bp.route('/<int:notif_id>/read', methods=['POST'])
@jwt_required()
def mark_read(notif_id):
    user_id = int(get_jwt_identity())
    n = Notification.query.filter_by(id=notif_id, user_id=user_id).first()
    if n:
        n.is_read = True
        db.session.commit()
    return jsonify({'message': 'Marked as read'})
