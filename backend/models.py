from database import db
from datetime import datetime

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)

    # Name fields
    last_name      = db.Column(db.String(60),  nullable=False)
    first_name     = db.Column(db.String(60),  nullable=False)
    middle_initial = db.Column(db.String(5),   nullable=True)   # optional

    # Login identifier
    student_number = db.Column(db.String(30),  unique=True, nullable=True)  # students only e.g. 234-03631M
    email          = db.Column(db.String(120), unique=True, nullable=True)  # professors/admin only

    # Birthday — used for student forgot password
    birthday       = db.Column(db.String(10),  nullable=True)   # stored as 'YYYY-MM-DD'

    password   = db.Column(db.String(200), nullable=False)
    role       = db.Column(db.String(20),  nullable=False)
    avatar     = db.Column(db.Text,        nullable=True)        # base64 data URL
    created_at = db.Column(db.DateTime,    default=datetime.utcnow)

    # Admin controls
    status    = db.Column(db.String(20), default='active')      # 'active' | 'pending' | 'deactivated'
    is_active = db.Column(db.Boolean,    default=True)           # False = deactivated by admin

    # Helper: full display name — "Dela Cruz, Juan A."
    @property
    def full_name(self):
        mi = f' {self.middle_initial}.' if self.middle_initial else ''
        return f'{self.last_name}, {self.first_name}{mi}'

    # Helper: login identifier
    @property
    def login_id(self):
        return self.student_number if self.role == 'student' else self.email


class Class(db.Model):
    __tablename__ = 'classes'

    id = db.Column(db.Integer, primary_key=True)
    class_name = db.Column(db.String(100), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    section = db.Column(db.String(50), nullable=False)
    class_code = db.Column(db.String(10), unique=True, nullable=False)
    professor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Theme (0=Default, 1=Mechanics, 2=Waves, 3=Electricity, 4=Optics, 5=Electronics, 6=Custom)
    theme        = db.Column(db.Integer, default=0)
    banner_image = db.Column(db.String(255), nullable=True)

    # Admin controls
    is_archived = db.Column(db.Boolean, default=False)       # True = archived by admin

class ClassMember(db.Model):
    __tablename__ = 'class_members'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_archived = db.Column(db.Boolean, default=False)  # student soft-archive


class Announcement(db.Model):
    __tablename__ = 'announcements'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    posted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Activity(db.Model):
    __tablename__ = 'activities'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    file_type = db.Column(db.String(10), nullable=False)
    parsed_content = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class EditedContent(db.Model):
    __tablename__ = 'edited_contents'

    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    section_type = db.Column(db.String(50), nullable=False)
    content_html = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Submission(db.Model):
    __tablename__ = 'submissions'

    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Answers
    answers = db.Column(db.JSON, nullable=True)            # JSON - guide questions
    table_data = db.Column(db.JSON, nullable=True)         # JSON - data sheet
    materials_checked = db.Column(db.JSON, nullable=True)  # JSON - checklist
    student_info = db.Column(db.JSON, nullable=True)       # JSON - name, section, date

    # File upload
    uploaded_file = db.Column(db.String(200), nullable=True)

    # Grading
    grade = db.Column(db.Float, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    graded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    graded_at = db.Column(db.DateTime, nullable=True)

    # Group grading — which group this submission belongs to
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True)

    # Activity attendance
    attendance_status = db.Column(db.String(10), nullable=True)  # 'present' | 'absent'

    # Status
    status = db.Column(db.String(20), default='submitted')  # submitted, graded
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# STREAM
# ============================================================

class StreamPost(db.Model):
    __tablename__ = 'stream_posts'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    posted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_type = db.Column(db.String(20), nullable=False, default='announcement')  # 'announcement' | 'activity' | 'both'
    message = db.Column(db.Text, nullable=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    comments = db.relationship('StreamComment', backref='post', lazy=True, cascade='all, delete-orphan')


class StreamComment(db.Model):
    __tablename__ = 'stream_comments'

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('stream_posts.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# GROUPS
# ============================================================

class Group(db.Model):
    __tablename__ = 'groups'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    leader_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    members = db.relationship('GroupMember', backref='group', lazy=True, cascade='all, delete-orphan')


class GroupMember(db.Model):
    __tablename__ = 'group_members'

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# SESSION ATTENDANCE
# ============================================================

class ClassSession(db.Model):
    __tablename__ = 'class_sessions'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    session_date = db.Column(db.String(50), nullable=False)  # stored as string e.g. "2025-03-05"
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    attendance = db.relationship('SessionAttendance', backref='session', lazy=True, cascade='all, delete-orphan')


class SessionAttendance(db.Model):
    __tablename__ = 'session_attendance'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('class_sessions.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(10), nullable=False, default='present')  # 'present' | 'absent'


# ============================================================
# FEED EVENTS
# ============================================================

class Notification(db.Model):
    __tablename__ = 'notifications'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message    = db.Column(db.String(250), nullable=False)
    link       = db.Column(db.String(200), nullable=True)
    notif_type = db.Column(db.String(30),  nullable=False)  # post|comment|submit|grade|joined
    is_read    = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ClassInvite(db.Model):
    __tablename__ = 'class_invites'

    id         = db.Column(db.Integer, primary_key=True)
    class_id   = db.Column(db.Integer, db.ForeignKey('classes.id'),  nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'),    nullable=False)
    invited_by = db.Column(db.Integer, db.ForeignKey('users.id'),    nullable=False)
    status     = db.Column(db.String(20), default='pending')  # pending|accepted|declined
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class FeedEvent(db.Model):
    __tablename__ = 'feed_events'

    id         = db.Column(db.Integer, primary_key=True)
    class_id   = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    event_type = db.Column(db.String(30),  nullable=False)  # submit|unsubmit|activity_posted|joined|collab_start
    actor_name = db.Column(db.String(120), nullable=True)
    actor_role = db.Column(db.String(20),  nullable=True)   # student|professor
    message    = db.Column(db.String(250), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)