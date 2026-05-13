from gevent import monkey
monkey.patch_all()

from flask import Flask, send_from_directory, render_template
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from database import db
from auth import auth, bcrypt
from datetime import timedelta
from stream import stream
import os
from dotenv import load_dotenv
from admin import admin, seed_admin
from extensions import socketio, limiter, revoked_tokens

load_dotenv()

_required = ['DATABASE_URL', 'JWT_SECRET_KEY']
_missing  = [k for k in _required if not os.environ.get(k)]
if _missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(_missing)}")

app = Flask(__name__,
    static_folder='../frontend/static',
    template_folder='../frontend'
)

_origins = os.environ.get('ALLOWED_ORIGINS', '*')
_origins_list = _origins if _origins == '*' else _origins.split(',')
CORS(app, resources={r"/*": {"origins": _origins_list}})
socketio.init_app(app, cors_allowed_origins=_origins_list, async_mode='gevent')
limiter.init_app(app)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=8)

# Connection pooling — handles concurrent users
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size':    10,    # max simultaneous DB connections
    'pool_timeout': 20,    # seconds to wait for a connection
    'pool_recycle': 300,   # recycle connections every 5 minutes
}

# Initialize extensions
db.init_app(app)
bcrypt.init_app(app)
jwt = JWTManager(app)
Migrate(app, db)

@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    return jwt_payload.get('jti') in revoked_tokens

# Register blueprints
from auth import auth
from classes import classes
from activities import activities
from submissions import submissions

app.register_blueprint(auth, url_prefix='/api/auth')
app.register_blueprint(classes, url_prefix='/api/classes')
app.register_blueprint(activities, url_prefix='/api/activities')
app.register_blueprint(submissions, url_prefix='/api/submissions')
app.register_blueprint(stream, url_prefix='/api/stream')
from feed import feed_bp
app.register_blueprint(feed_bp, url_prefix='/api/feed')
from notifications import notifications_bp
app.register_blueprint(notifications_bp, url_prefix='/api/notifications')
app.register_blueprint(admin, url_prefix='/api')

from collab import register_collab
register_collab(socketio)

# ===== PWA =====
@app.route('/manifest.json')
def manifest():
    return send_from_directory('../frontend/static', 'manifest.json', mimetype='application/manifest+json')

@app.route('/sw.js')
def service_worker():
    resp = send_from_directory('../frontend/static', 'sw.js', mimetype='application/javascript')
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp

# ===== FRONTEND ROUTES =====
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login')
def login():
    return send_from_directory('../frontend', 'login.html')

@app.route('/dashboard_student')
def dashboard_student():
    return send_from_directory('../frontend', 'dashboard_student.html')

@app.route('/dashboard_professor')
def dashboard_professor():
    return send_from_directory('../frontend', 'dashboard_professor.html')

@app.route('/class_detail')
def class_detail():
    return send_from_directory('../frontend', 'class_detail.html')

@app.route('/activity')
def activity_page():
    return send_from_directory('../frontend', 'activity.html')

@app.route('/create_activity')
def create_activity_page():
    return send_from_directory('../frontend', 'create_activity.html')

@app.route('/submissions')
def submissions_page():
    return send_from_directory('../frontend', 'submissions.html')

@app.route('/profile')
def profile_page():
    return send_from_directory('../frontend', 'profile.html')

@app.route('/archived')
def archived_page():
    return send_from_directory('../frontend', 'archived.html')

@app.route('/admin_dashboard')
def admin_dashboard():
    return send_from_directory('../frontend', 'admin_dashboard.html')


@app.route('/register')
def register():
    return render_template('register.html')

# ===== RUN =====
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        from submissions import _migrate_uploaded_files_column
        _migrate_uploaded_files_column()
        seed_admin(app)
        print("Database ready!")
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)

    # ── Live reload: watch frontend files and emit dev_reload via SocketIO ──
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class _FrontendWatcher(FileSystemEventHandler):
            def on_modified(self, event):
                if not event.is_directory:
                    socketio.emit('dev_reload', namespace='/')
            def on_created(self, event):
                if not event.is_directory:
                    socketio.emit('dev_reload', namespace='/')

        _frontend_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend')
        _observer = Observer()
        _observer.schedule(_FrontendWatcher(), _frontend_dir, recursive=True)
        _observer.daemon = True
        _observer.start()
        print("Live reload active — watching frontend/")
    except Exception as e:
        print(f"Live reload unavailable: {e}")

    print("PHYSLAB server running on http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000, allow_unsafe_werkzeug=True, use_reloader=False)