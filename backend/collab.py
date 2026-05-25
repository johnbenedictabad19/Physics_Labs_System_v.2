from flask_socketio import join_room, leave_room, emit
from flask import request
from flask_jwt_extended import decode_token
from models import User

# room_id → { users: {sid: info}, fields: {field_key: [sid, ...]} }
_rooms = {}
# sid → room_id — reverse lookup so disconnect is O(1) instead of O(n_rooms)
_sid_to_room: dict = {}

COLORS = ['#667eea', '#f59e0b', '#10b981', '#ef4444', '#3b82f6', '#8b5cf6', '#ec4899', '#14b8a6']


def _rid(activity_id, group_id):
    return f'a{activity_id}g{group_id}'


def _presence(room_id):
    r = _rooms.get(room_id, {})
    users = r.get('users', {})
    fields_out = {}
    for fk, sids in r.get('fields', {}).items():
        focused_users = [users[s] for s in sids if s in users]
        if focused_users:
            fields_out[fk] = focused_users
    return {
        'users': list(users.values()),
        'fields': fields_out
    }


def register_collab(socketio):

    @socketio.on('join_collab')
    def on_join(data):
        d = data or {}
        token       = d.get('token')
        activity_id = d.get('activity_id')
        group_id    = d.get('group_id')
        if not (token and activity_id and group_id):
            return
        try:
            uid  = int(decode_token(token)['sub'])
            user = User.query.get(uid)
            if not user:
                return
        except Exception:
            return

        # Verify user is actually a member of this group
        from models import GroupMember, Group, Activity
        membership = GroupMember.query.filter_by(group_id=group_id, student_id=uid).first()
        if not membership:
            emit('collab_error', {'message': 'Not a member of this group'})
            return

        # Verify group belongs to the activity's class (prevent cross-class room join)
        grp = Group.query.get(group_id)
        act = Activity.query.get(activity_id)
        if not grp or not act or grp.class_id != act.class_id:
            emit('collab_error', {'message': 'Group/activity mismatch'})
            return

        room = _rid(activity_id, group_id)
        join_room(room)
        _sid_to_room[request.sid] = room

        is_first = room not in _rooms or len(_rooms[room]['users']) == 0
        if room not in _rooms:
            _rooms[room] = {'users': {}, 'fields': {}, 'draft': {}}

        taken = {u['color'] for u in _rooms[room]['users'].values()}
        color = next((c for c in COLORS if c not in taken), COLORS[len(_rooms[room]['users']) % len(COLORS)])

        _rooms[room]['users'][request.sid] = {
            'id': uid,
            'name': user.full_name or user.email,
            'avatar': user.avatar or None,
            'color': color
        }
        emit('presence_update', _presence(room), to=room)

        # Send current field state to the joining user only
        current_draft = _rooms[room].get('draft', {})
        if current_draft:
            emit('draft_sync', current_draft)

        # Feed: emit collab_start only when first member opens the activity
        if is_first:
            try:
                from models import Activity
                from feed import emit_feed
                act = Activity.query.get(activity_id)
                if act:
                    emit_feed(act.class_id, 'collab_start',
                              user.full_name or user.email, 'student',
                              f'Group started collaborating on "{act.title}"')
            except Exception:
                pass

    @socketio.on('field_update')
    def on_field_update(data):
        d = data or {}
        room = _rid(d.get('activity_id'), d.get('group_id'))
        if room not in _rooms or request.sid not in _rooms[room]['users']:
            return
        field_type = d.get('field_type')
        field_id   = str(d.get('field_id', ''))
        value      = d.get('value', '')

        # Store in room draft state for late joiners / reconnects
        draft = _rooms[room]['draft']
        draft[f'{field_type}_{field_id}'] = {
            'field_type': field_type,
            'field_id':   field_id,
            'value':      value,
            'user':       _rooms[room]['users'][request.sid]
        }
        if len(draft) > 300:
            for k in list(draft.keys())[:50]:
                del draft[k]

        emit('field_updated', {
            'field_type': field_type,
            'field_id':   field_id,
            'value':      value,
            'user':       _rooms[room]['users'][request.sid]
        }, to=room, include_self=False)

    @socketio.on('field_focus')
    def on_field_focus(data):
        d = data or {}
        room = _rid(d.get('activity_id'), d.get('group_id'))
        if room not in _rooms or request.sid not in _rooms[room]['users']:
            return
        fk = f"{d.get('field_type')}_{d.get('field_id')}"
        sids = _rooms[room]['fields'].get(fk, [])
        if request.sid not in sids:
            sids = sids + [request.sid]
        _rooms[room]['fields'][fk] = sids
        emit('field_focused', {
            'field_type': d.get('field_type'),
            'field_id':   str(d.get('field_id', '')),
            'user':       _rooms[room]['users'][request.sid]
        }, to=room, include_self=False)

    @socketio.on('field_blur')
    def on_field_blur(data):
        d = data or {}
        room = _rid(d.get('activity_id'), d.get('group_id'))
        if room not in _rooms:
            return
        fk = f"{d.get('field_type')}_{d.get('field_id')}"
        sids = [s for s in _rooms[room]['fields'].get(fk, []) if s != request.sid]
        if sids:
            _rooms[room]['fields'][fk] = sids
        else:
            _rooms[room]['fields'].pop(fk, None)
        user = _rooms[room]['users'].get(request.sid, {})
        emit('field_blurred', {
            'field_type': d.get('field_type'),
            'field_id':   str(d.get('field_id', '')),
            'user':       user
        }, to=room, include_self=False)

    @socketio.on('attach_update')
    def on_attach_update(data):
        d = data or {}
        room = _rid(d.get('activity_id'), d.get('group_id'))
        if room not in _rooms or request.sid not in _rooms[room]['users']:
            return
        block_index = str(d.get('block_index', ''))
        files = d.get('files', [])
        draft = _rooms[room]['draft']
        draft[f'attach_{block_index}'] = {
            'field_type': 'attach',
            'block_index': block_index,
            'files': files
        }
        if len(draft) > 300:
            for k in list(draft.keys())[:50]:
                del draft[k]

        emit('attach_updated', {
            'block_index': block_index,
            'files': files,
            'user': _rooms[room]['users'][request.sid]
        }, to=room, include_self=False)

    @socketio.on('disconnect')
    def on_disconnect():
        room_id = _sid_to_room.pop(request.sid, None)
        if room_id is None or room_id not in _rooms:
            return
        rd = _rooms[room_id]
        rd['users'].pop(request.sid, None)
        rd['fields'] = {k: [s for s in sids if s != request.sid]
                        for k, sids in rd['fields'].items()}
        rd['fields'] = {k: v for k, v in rd['fields'].items() if v}
        if not rd['users']:
            del _rooms[room_id]
        else:
            emit('presence_update', _presence(room_id), to=room_id)
