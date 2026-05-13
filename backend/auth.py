from flask import Blueprint, request, jsonify
from database import db
from models import User
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
from extensions import limiter
import re

auth = Blueprint('auth', __name__)
bcrypt = Bcrypt()


def _validate_password(password):
    """Returns an error message string, or None if password is valid."""
    if len(password) < 8:
        return 'Password must be at least 8 characters!'
    if not re.search(r'[A-Z]', password):
        return 'Password must contain at least one uppercase letter!'
    if not re.search(r'[a-z]', password):
        return 'Password must contain at least one lowercase letter!'
    if not re.search(r'[0-9]', password):
        return 'Password must contain at least one number!'
    if not re.search(r'[^A-Za-z0-9]', password):
        return 'Password must contain at least one special character!'
    return None


# ============================================================
# REGISTER
# ============================================================
@auth.route('/register', methods=['POST'])
@limiter.limit("10 per hour")
def register():
    data = request.get_json() or {}

    last_name      = (data.get('last_name')      or '').strip()
    first_name     = (data.get('first_name')     or '').strip()
    middle_initial = (data.get('middle_initial') or '').strip()
    password       = data.get('password', '')
    role           = data.get('role', '')         # 'student' | 'professor'

    # Role-specific fields
    student_number = (data.get('student_number') or '').strip()
    email          = (data.get('email')          or '').strip()
    birthday       = (data.get('birthday')       or '').strip()  # 'YYYY-MM-DD'

    # Validation
    if not last_name or not first_name:
        return jsonify({'message': 'Last name and first name are required!'}), 400
    pw_error = _validate_password(password)
    if pw_error:
        return jsonify({'message': pw_error}), 400
    if role not in ('student', 'professor'):
        return jsonify({'message': 'Invalid role!'}), 400

    if role == 'student':
        if not student_number:
            return jsonify({'message': 'Student number is required!'}), 400
        if not birthday:
            return jsonify({'message': 'Birthday is required for password recovery!'}), 400
        if User.query.filter_by(student_number=student_number).first():
            return jsonify({'message': 'Student number already registered!'}), 400

    if role == 'professor':
        if not email:
            return jsonify({'message': 'Email is required!'}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({'message': 'Email already registered!'}), 400

    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
    status    = 'pending' if role == 'professor' else 'active'

    new_user = User(
        last_name      = last_name,
        first_name     = first_name,
        middle_initial = middle_initial or None,
        student_number = student_number or None,
        email          = email or None,
        birthday       = birthday or None,
        password       = hashed_pw,
        role           = role,
        status         = status,
        is_active      = True
    )

    db.session.add(new_user)
    db.session.commit()

    message = (
        'Registration successful! Your account is pending admin approval.'
        if role == 'professor'
        else 'Registration successful!'
    )
    return jsonify({'message': message}), 201


# ============================================================
# DUPLICATE CHECKS (used by registration Step 3)
# ============================================================
@auth.route('/check-student-number', methods=['POST'])
@limiter.limit("20 per minute")
def check_student_number():
    data = request.get_json() or {}
    sn = (data.get('student_number') or '').strip()
    if not sn:
        return jsonify({'available': False}), 400
    exists = User.query.filter_by(student_number=sn).first() is not None
    return jsonify({'available': not exists}), 200


@auth.route('/check-email', methods=['POST'])
@limiter.limit("20 per minute")
def check_email():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({'available': False}), 400
    exists = User.query.filter_by(email=email).first() is not None
    return jsonify({'available': not exists}), 200


# ============================================================
# LOGIN
# ============================================================
@auth.route('/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    data = request.get_json() or {}
    password = data.get('password', '')

    # Try student number first, then email
    student_number = (data.get('student_number') or '').strip()
    email          = (data.get('email')          or '').strip()

    if student_number:
        user = User.query.filter_by(student_number=student_number).first()
    elif email:
        user = User.query.filter_by(email=email).first()
    else:
        return jsonify({'message': 'Please provide student number or email!'}), 400

    if not user or not bcrypt.check_password_hash(user.password, password):
        identifier = 'student number' if student_number else 'email'
        return jsonify({'message': f'Invalid {identifier} or password!'}), 401

    if user.status == 'pending':
        return jsonify({'message': 'Your account is pending admin approval. Please wait.'}), 403

    if not user.is_active or user.status == 'deactivated':
        return jsonify({'message': 'Your account has been deactivated. Please contact admin.'}), 403

    token = create_access_token(identity=str(user.id))

    return jsonify({
        'message':        'Login successful!',
        'token':          token,
        'role':           user.role,
        'full_name':      user.full_name,
        'first_name':     user.first_name,
        'last_name':      user.last_name,
        'middle_initial': user.middle_initial or '',
        'email':          user.email or '',
        'student_number': user.student_number or '',
        'user_id':        user.id,
        'avatar':         user.avatar or '',
        'joined_at':      user.created_at.isoformat() if user.created_at else None
    }), 200


# ============================================================
# FORGOT PASSWORD — Students only (student number + birthday)
# ============================================================
@auth.route('/forgot-password', methods=['POST'])
@limiter.limit("3 per hour")
def forgot_password():
    data           = request.get_json() or {}
    student_number = (data.get('student_number') or '').strip()
    birthday       = (data.get('birthday')       or '').strip()  # 'YYYY-MM-DD'
    new_password   = data.get('new_password', '')

    if not student_number or not birthday or not new_password:
        return jsonify({'message': 'All fields are required!'}), 400
    pw_error = _validate_password(new_password)
    if pw_error:
        return jsonify({'message': pw_error}), 400

    user = User.query.filter_by(student_number=student_number, role='student').first()

    if not user or user.birthday != birthday:
        return jsonify({'message': 'Student number or birthday is incorrect!'}), 401

    user.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    db.session.commit()

    return jsonify({'message': 'Password reset successful! You can now log in.'}), 200


# ============================================================
# GET PROFILE
# ============================================================
@auth.route('/profile', methods=['GET'])
@jwt_required()
def get_profile():
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)

    if not user:
        return jsonify({'message': 'User not found!'}), 404

    return jsonify({
        'id':                    user.id,
        'full_name':             user.full_name,
        'first_name':            user.first_name,
        'last_name':             user.last_name,
        'middle_initial':        user.middle_initial or '',
        'email':                 user.email or '',
        'student_number':        user.student_number or '',
        'role':                  user.role,
        'avatar':                user.avatar or '',
        'joined_at':             user.created_at.isoformat() if user.created_at else None,
        'notifications_enabled': user.notifications_enabled if user.notifications_enabled is not None else True
    }), 200


# ============================================================
# UPDATE PROFILE
# ============================================================
@auth.route('/update-profile', methods=['PUT'])
@jwt_required()
def update_profile():
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)

    if not user:
        return jsonify({'message': 'User not found!'}), 404

    data           = request.get_json() or {}
    last_name      = (data.get('last_name')      or '').strip()
    first_name     = (data.get('first_name')     or '').strip()
    middle_initial = (data.get('middle_initial') or '').strip()

    if not last_name or not first_name:
        return jsonify({'message': 'Last name and first name are required!'}), 400

    # Professors can update email too
    if user.role == 'professor':
        email = (data.get('email') or '').strip()
        if not email:
            return jsonify({'message': 'Email is required!'}), 400
        existing = User.query.filter_by(email=email).first()
        if existing and str(existing.id) != str(user_id):
            return jsonify({'message': 'Email already in use by another account!'}), 400
        user.email = email

    user.last_name      = last_name
    user.first_name     = first_name
    user.middle_initial = middle_initial or None
    db.session.commit()

    return jsonify({
        'message':        'Profile updated successfully!',
        'full_name':      user.full_name,
        'first_name':     user.first_name,
        'last_name':      user.last_name,
        'middle_initial': user.middle_initial or '',
        'email':          user.email or ''
    }), 200


# ============================================================
# UPDATE PREFERENCES
# ============================================================
@auth.route('/preferences', methods=['PUT'])
@jwt_required()
def update_preferences():
    user_id = int(get_jwt_identity())
    user    = User.query.get(user_id)
    if not user:
        return jsonify({'message': 'User not found!'}), 404
    data = request.get_json() or {}
    if 'notifications_enabled' in data:
        user.notifications_enabled = bool(data['notifications_enabled'])
    db.session.commit()
    return jsonify({'message': 'Preferences saved!', 'notifications_enabled': user.notifications_enabled}), 200


# ============================================================
# CHANGE PASSWORD
# ============================================================
@auth.route('/change-password', methods=['PUT'])
@limiter.limit("5 per minute")
@jwt_required()
def change_password():
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)

    if not user:
        return jsonify({'message': 'User not found!'}), 404

    data             = request.get_json() or {}
    current_password = data.get('current_password', '')
    new_password     = data.get('new_password', '')

    if not current_password or not new_password:
        return jsonify({'message': 'All fields are required!'}), 400
    if not bcrypt.check_password_hash(user.password, current_password):
        return jsonify({'message': 'Current password is incorrect!'}), 401
    pw_error = _validate_password(new_password)
    if pw_error:
        return jsonify({'message': pw_error}), 400

    user.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    db.session.commit()

    return jsonify({'message': 'Password updated successfully!'}), 200


# ============================================================
# UPLOAD AVATAR
# ============================================================
@auth.route('/upload-avatar', methods=['POST'])
@limiter.limit("10 per minute")
@jwt_required()
def upload_avatar():
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)
    if not user:
        return jsonify({'message': 'User not found!'}), 404

    data   = request.get_json() or {}
    avatar = data.get('avatar', '').strip()

    if not avatar:
        return jsonify({'message': 'No avatar data provided!'}), 400
    if not avatar.startswith('data:image/'):
        return jsonify({'message': 'Invalid image format!'}), 400
    if len(avatar) > 7_000_000:
        return jsonify({'message': 'Image too large! Please use an image under 5MB.'}), 400

    user.avatar = avatar
    db.session.commit()

    return jsonify({'message': 'Avatar updated successfully!', 'avatar': user.avatar}), 200


# ============================================================
# LOGOUT — revoke token server-side
# ============================================================
@auth.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    from extensions import revoked_tokens
    jti = get_jwt()['jti']
    revoked_tokens.add(jti)
    return jsonify({'message': 'Logged out successfully!'}), 200


# ============================================================
# DELETE ACCOUNT
# ============================================================
@auth.route('/delete-account', methods=['DELETE'])
@jwt_required()
def delete_account():
    user_id = get_jwt_identity()
    user    = User.query.get(user_id)

    if not user:
        return jsonify({'message': 'User not found!'}), 404

    db.session.delete(user)
    db.session.commit()

    return jsonify({'message': 'Account deleted successfully!'}), 200