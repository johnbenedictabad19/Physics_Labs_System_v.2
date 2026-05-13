from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import request as flask_request


def _get_real_ip():
    # Railway (and most proxies) set X-Forwarded-For; fall back to REMOTE_ADDR
    forwarded = flask_request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return get_remote_address()


socketio = SocketIO()
limiter  = Limiter(key_func=_get_real_ip, default_limits=[])

# In-memory JWT revocation set (cleared on server restart — acceptable for single-instance Railway)
revoked_tokens: set = set()
