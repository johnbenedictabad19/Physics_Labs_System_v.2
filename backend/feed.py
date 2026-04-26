from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from models import FeedEvent, User, Class, ClassMember
from extensions import socketio

feed_bp = Blueprint('feed', __name__)


def emit_feed(class_id, event_type, actor_name, actor_role, message):
    """Save a feed event to DB and broadcast to the class feed room."""
    try:
        ev = FeedEvent(
            class_id=class_id,
            event_type=event_type,
            actor_name=actor_name,
            actor_role=actor_role,
            message=message
        )
        db.session.add(ev)
        db.session.commit()
        socketio.emit('feed_event', {
            'id':       ev.id,
            'class_id': class_id,
            'type':     event_type,
            'actor':    actor_name,
            'role':     actor_role,
            'message':  message,
            'ts':       ev.created_at.isoformat() + 'Z'
        }, namespace='/')
    except Exception as e:
        print(f'[feed] emit error: {e}')


@feed_bp.route('/history', methods=['GET'])
@jwt_required()
def get_history():
    user_id = int(get_jwt_identity())
    user = User.query.get(user_id)
    if user.role == 'professor':
        class_ids = [c.id for c in Class.query.filter_by(professor_id=user_id).all()]
    else:
        class_ids = [m.class_id for m in ClassMember.query.filter_by(student_id=user_id).all()]
    if not class_ids:
        return jsonify([])
    events = FeedEvent.query.filter(FeedEvent.class_id.in_(class_ids))\
        .order_by(FeedEvent.created_at.desc()).limit(100).all()
    return jsonify([{
        'id':       e.id,
        'class_id': e.class_id,
        'type':     e.event_type,
        'actor':    e.actor_name,
        'role':     e.actor_role,
        'message':  e.message,
        'ts':       e.created_at.isoformat()
    } for e in events])
