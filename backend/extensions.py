from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import request as flask_request
import time


def _get_real_ip():
    # Railway (and most proxies) set X-Forwarded-For; fall back to REMOTE_ADDR
    forwarded = flask_request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return get_remote_address()


socketio = SocketIO()
limiter  = Limiter(key_func=_get_real_ip, default_limits=[])

# In-memory JWT revocation store: {jti: expiry_unix_timestamp}
# Cleared on server restart — acceptable for single-instance Railway.
revoked_tokens: dict = {}


def revoke_token(jti: str, exp: int) -> None:
    """Add a JTI to the revocation store and prune already-expired entries."""
    revoked_tokens[jti] = exp
    _prune_revoked_tokens()


def _prune_revoked_tokens() -> None:
    """Remove JTIs whose tokens have already expired (no longer need blocking)."""
    now = int(time.time())
    expired = [jti for jti, exp in revoked_tokens.items() if exp < now]
    for jti in expired:
        del revoked_tokens[jti]
