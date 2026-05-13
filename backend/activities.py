from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from database import db
from models import Activity, User, StreamPost, ClassMember
import os
import json
from datetime import datetime

# Load .env for ANTHROPIC_API_KEY
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, use system env vars

activities = Blueprint('activities', __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'docx', 'pdf'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def format_activity(a):
    return {
        'id': a.id,
        'title': a.title,
        'file_type': a.file_type,
        'created_at': a.created_at.strftime('%b %d, %Y') if a.created_at else '',
        'due_date': a.due_date.strftime('%Y-%m-%dT%H:%M') if a.due_date else None,
        'due_date_display': a.due_date.strftime('%b %d, %Y %I:%M %p') if a.due_date else None
    }


# ===== UPLOAD ACTIVITY =====
@activities.route('/<int:class_id>/upload', methods=['POST'])
@jwt_required()
def upload_activity(class_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can upload activities!'}), 403

    if 'file' not in request.files:
        return jsonify({'message': 'No file uploaded!'}), 400

    file = request.files['file']
    title = request.form.get('title', '').strip()

    if not title:
        return jsonify({'message': 'Please provide an activity title!'}), 400
    if len(title) > 200:
        return jsonify({'message': 'Activity title cannot exceed 200 characters!'}), 400
    if file.filename == '':
        return jsonify({'message': 'No file selected!'}), 400
    if not allowed_file(file.filename):
        return jsonify({'message': 'Only DOCX and PDF files are allowed!'}), 400

    file.stream.seek(0, 2)
    file_size = file.stream.tell()
    file.stream.seek(0)
    if file_size > 20 * 1024 * 1024:
        return jsonify({'message': 'File too large. Maximum size is 20MB.'}), 400

    file_ext = file.filename.rsplit('.', 1)[1].lower()
    safe_filename = f"class{class_id}_{int(__import__('time').time())}.{file_ext}"
    filepath = os.path.join(UPLOAD_FOLDER, safe_filename)
    file.save(filepath)

    parsed_data = None
    if file_ext == 'docx':
        try:
            from parser import parse_docx
            parsed_data = parse_docx(filepath)
        except Exception as e:
            import traceback
            print(f"Parser error: {e}")
            traceback.print_exc()

    new_activity = Activity(
        class_id=class_id,
        uploaded_by=user.id,
        title=title,
        filename=safe_filename,
        file_type=file_ext,
        parsed_content=json.dumps(parsed_data) if parsed_data else None
    )
    db.session.add(new_activity)
    db.session.commit()

    return jsonify({
        'message': 'Activity uploaded successfully!',
        'id': new_activity.id,
        'parsed': parsed_data is not None,
        'file_type': file_ext
    }), 201


# ===== GET ACTIVITIES =====
@activities.route('/<int:class_id>', methods=['GET'])
@jwt_required()
def get_activities(class_id):
    from sqlalchemy import exists
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    # Students must be approved members to see activities
    if user and user.role == 'student':
        membership = ClassMember.query.filter_by(
            class_id=class_id, student_id=user_id
        ).first()
        if not membership or membership.enrollment_status != 'approved':
            return jsonify([]), 200
    acts = Activity.query.filter_by(class_id=class_id)\
        .filter(exists().where(StreamPost.activity_id == Activity.id))\
        .order_by(Activity.created_at.desc()).all()
    return jsonify([format_activity(a) for a in acts]), 200


# ===== GET PARSED CONTENT =====
@activities.route('/<int:activity_id>/parsed', methods=['GET'])
@jwt_required()
def get_parsed(activity_id):
    activity = Activity.query.get(activity_id)
    if not activity:
        return jsonify({'message': 'Activity not found!'}), 404
    if not activity.parsed_content:
        # Return 404 with clear JSON message (not HTML)
        file_type = activity.file_type.upper() if activity.file_type else 'file'
        return jsonify({
            'message': f'No preview available for {file_type} files. Download to view.'
        }), 404
    try:
        data = json.loads(activity.parsed_content)
        data['class_id'] = activity.class_id
        data['title']    = activity.title
        data['file_type'] = activity.file_type
        return jsonify(data), 200
    except (json.JSONDecodeError, TypeError):
        return jsonify({'message': 'Activity data is corrupted. Please re-upload.'}), 500


# ===== RE-PARSE ACTIVITY =====
@activities.route('/<int:activity_id>/reparse', methods=['POST'])
@jwt_required()
def reparse_activity(activity_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))
    if user.role != 'professor':
        return jsonify({'message': 'Only professors can re-parse activities!'}), 403
    activity = Activity.query.get(activity_id)
    if not activity:
        return jsonify({'message': 'Activity not found!'}), 404
    from classes import _is_class_prof
    if not _is_class_prof(activity.class_id, int(user_id)):
        return jsonify({'message': 'Not authorized!'}), 403
    if activity.file_type != 'docx':
        return jsonify({'message': 'Re-parse is only available for DOCX files.'}), 400
    filepath = os.path.join(UPLOAD_FOLDER, activity.filename)
    if not os.path.exists(filepath):
        return jsonify({'message': 'Original file not found on server. Please re-upload.'}), 404
    try:
        from parser import parse_docx
        parsed_data = parse_docx(filepath)
        activity.parsed_content = json.dumps(parsed_data) if parsed_data else None
        db.session.commit()
        return jsonify({'message': 'Activity re-parsed successfully!'}), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'message': f'Parse error: {str(e)}'}), 500


# ===== DELETE ACTIVITY =====
@activities.route('/<int:activity_id>/delete', methods=['DELETE'])
@jwt_required()
def delete_activity(activity_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can delete activities!'}), 403

    activity = Activity.query.get(activity_id)
    if not activity:
        return jsonify({'message': 'Activity not found!'}), 404
    from classes import _is_class_prof
    if not _is_class_prof(activity.class_id, int(user_id)):
        return jsonify({'message': 'Not authorized!'}), 403

    from models import Submission, EditedContent
    Submission.query.filter_by(activity_id=activity.id).delete()
    EditedContent.query.filter_by(activity_id=activity.id).delete()

    file_path = os.path.join(UPLOAD_FOLDER, activity.filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except:
            pass

    db.session.delete(activity)
    db.session.commit()
    return jsonify({'message': 'Activity deleted!'}), 200


# ===== SAVE EDITED CONTENT =====
@activities.route('/<int:activity_id>/save-edit', methods=['POST'])
@jwt_required()
def save_edit(activity_id):
    from models import EditedContent
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can edit activities!'}), 403

    activity = Activity.query.get(activity_id)
    if not activity:
        return jsonify({'message': 'Activity not found!'}), 404
    from classes import _is_class_prof
    if not _is_class_prof(activity.class_id, int(user_id)):
        return jsonify({'message': 'Not authorized!'}), 403

    data = request.get_json() or {}
    section_type = data.get('section_type')
    content_html = data.get('content_html')

    if not section_type or not content_html:
        return jsonify({'message': 'Missing data!'}), 400

    existing = EditedContent.query.filter_by(
        activity_id=activity_id,
        section_type=section_type
    ).first()

    if existing:
        existing.content_html = content_html
        existing.updated_at = datetime.utcnow()
    else:
        new_edit = EditedContent(
            activity_id=activity_id,
            section_type=section_type,
            content_html=content_html
        )
        db.session.add(new_edit)

    db.session.commit()
    return jsonify({'message': 'Saved successfully!'}), 200


# ===== GET EDITED CONTENTS =====
@activities.route('/<int:activity_id>/edited', methods=['GET'])
@jwt_required()
def get_edited(activity_id):
    from models import EditedContent
    edits = EditedContent.query.filter_by(activity_id=activity_id).all()
    result = {}
    for e in edits:
        result[e.section_type] = e.content_html
    return jsonify(result), 200


# ===== CREATE MANUAL ACTIVITY =====
@activities.route('/<int:class_id>/create-manual', methods=['POST'])
@jwt_required()
def create_manual(class_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can create activities!'}), 403

    data = request.get_json() or {}
    if not data:
        return jsonify({'message': 'No data received!'}), 400

    title = data.get('title', '').strip()
    activity_data = data.get('activity_data', {})

    if not title:
        return jsonify({'message': 'Please provide a title!'}), 400
    if len(title) > 200:
        return jsonify({'message': 'Activity title cannot exceed 200 characters!'}), 400

    try:
        sec = activity_data.get('sections', {})
        parsed_content = {
            'sections': build_sections_from_manual(activity_data),
            'tables': activity_data.get('tables', []),
            'sections_config': sec.get('sections_config', []),
            'extra_sections':  sec.get('extra_sections',  [])
        }
    except Exception as e:
        print(f"Build sections error: {e}")
        return jsonify({'message': f'Error processing activity data: {str(e)}'}), 500

    new_activity = Activity(
        class_id=class_id,
        uploaded_by=user.id,
        title=title,
        filename=f'manual_{int(__import__("time").time())}.json',
        file_type='manual',
        parsed_content=json.dumps(parsed_content)
    )
    db.session.add(new_activity)
    db.session.commit()

    # Feed event
    try:
        from feed import emit_feed
        emit_feed(class_id, 'activity_posted', user.full_name, 'professor',
                  f'{user.full_name} posted "{title}"')
    except Exception:
        pass

    return jsonify({'message': 'Activity created!', 'id': new_activity.id}), 201

def _is_json_safe_list(value):
    return isinstance(value, list)


def _is_non_empty_list(value):
    return isinstance(value, list) and len(value) > 0


def _safe_merge_docx_sections(activity, docx_sections):
    """
    Merge normalized DOCX editor sections into parsed_content without replacing
    unrelated parser output. Invalid payloads are ignored as a safe fallback.
    """
    if not isinstance(docx_sections, dict) or not docx_sections:
        return False
    if not activity.parsed_content:
        return False

    try:
        parsed = json.loads(activity.parsed_content)
    except (TypeError, json.JSONDecodeError):
        return False

    sections = parsed.get('sections')
    if not isinstance(sections, list):
        return False

    section_by_type = {}
    for sec in sections:
        if isinstance(sec, dict) and sec.get('type'):
            section_by_type[sec['type']] = sec

    applied = False
    structured_section_types = ('materials', 'procedures', 'guide_questions')
    for s_type in structured_section_types:
        incoming = docx_sections.get(s_type)
        if not isinstance(incoming, dict):
            continue
        existing = section_by_type.get(s_type)
        content = incoming.get('content')
        view_html = incoming.get('view_html')
        # Safe fallback: never replace parsed section with empty extracted payload.
        if not existing or not _is_non_empty_list(content):
            continue
        existing['content'] = content
        if isinstance(view_html, str) and view_html.strip():
            existing['view_html'] = view_html
        applied = True

    ds_incoming = docx_sections.get('data_sheet')
    ds_existing = section_by_type.get('data_sheet')
    if isinstance(ds_incoming, dict) and ds_existing:
        ds_view = ds_incoming.get('view_html')
        ds_tables = ds_incoming.get('tables')
        # Data sheet in edit mode can yield empty tables if cells are still in render wrappers.
        # Ignore empty extraction to preserve original parsed table structure.
        if _is_non_empty_list(ds_tables):
            parsed['tables'] = ds_tables
            if isinstance(ds_view, str) and ds_view.strip():
                ds_existing['view_html'] = ds_view
            applied = True

    if applied:
        activity.parsed_content = json.dumps(parsed)
    return applied


# ===== UPDATE ACTIVITY (Option B — preserve original parsed_content, save text overlays only) =====
@activities.route('/<int:activity_id>/update', methods=['PUT'])
@jwt_required()
def update_activity(activity_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can edit activities!'}), 403

    activity = Activity.query.get(activity_id)
    if not activity:
        return jsonify({'message': 'Activity not found!'}), 404

    data = request.get_json() or {}
    if not data:
        return jsonify({'message': 'No data received!'}), 400

    title = data.get('title', '').strip()
    if not title:
        return jsonify({'message': 'Please provide a title!'}), 400
    if len(title) > 200:
        return jsonify({'message': 'Activity title cannot exceed 200 characters!'}), 400

    # Always update title
    activity.title = title

    # For DOCX activities — preserve original parsed_content (with images)
    # Only save text overlays via EditedContent table
    text_overlays = data.get('text_overlays', {})
    if text_overlays:
        from models import EditedContent
        for section_type, html in text_overlays.items():
            if not html:
                continue
            existing = EditedContent.query.filter_by(
                activity_id=activity_id,
                section_type=section_type
            ).first()
            if existing:
                existing.content_html = html
                existing.updated_at = datetime.utcnow()
            else:
                db.session.add(EditedContent(
                    activity_id=activity_id,
                    section_type=section_type,
                    content_html=html
                ))

    # For DOCX activities, merge structured section edits only when payload is valid.
    if activity.file_type == 'docx':
        _safe_merge_docx_sections(activity, data.get('docx_sections'))

    # For manual activities (no original parsed_content with images) — full update
    if activity.file_type == 'manual':
        activity_data = data.get('activity_data')
        if not isinstance(activity_data, dict) or not activity_data:
            return jsonify({
                'message': 'Manual activity updates require non-empty activity_data.'
            }), 400
        try:
            sec = activity_data.get('sections', {})
            parsed_content = {
                'sections': build_sections_from_manual(activity_data),
                'tables': activity_data.get('tables', []),
                'sections_config': sec.get('sections_config', []),
            'extra_sections':  sec.get('extra_sections',  [])
            }
            activity.parsed_content = json.dumps(parsed_content)
        except Exception as e:
            return jsonify({'message': f'Error processing activity data: {str(e)}'}), 500

    db.session.commit()
    return jsonify({'message': 'Activity updated!', 'id': activity.id}), 200

# ===== SET DUE DATE =====
@activities.route('/<int:activity_id>/set-due-date', methods=['POST'])
@jwt_required()
def set_due_date(activity_id):
    user_id = get_jwt_identity()
    user = User.query.get(int(user_id))

    if user.role != 'professor':
        return jsonify({'message': 'Only professors can set due dates!'}), 403

    activity = Activity.query.get(activity_id)
    if not activity:
        return jsonify({'message': 'Activity not found!'}), 404

    data = request.get_json() or {}
    due_date_str = data.get('due_date')

    if due_date_str:
        try:
            activity.due_date = datetime.fromisoformat(due_date_str)
        except ValueError:
            return jsonify({'message': 'Invalid date format!'}), 400
    else:
        activity.due_date = None

    db.session.commit()
    return jsonify({'message': 'Due date updated!'}), 200


# ===== BUILD SECTIONS FROM MANUAL =====
def build_sections_from_manual(data):
    """
    Builds the ordered sections list for a manual activity.
    - When sections_config is present: only includes sections the professor added,
      in the order they appear (supports custom names + Phase 4 duplicates).
    - When sections_config is absent (DOCX import / legacy): includes all
      sections that have content in the default fixed order.
    """
    sec             = data.get('sections', {})
    sections_config = sec.get('sections_config', [])
    extra_sections  = sec.get('extra_sections',  [])

    _key_to_type = {
        'introduction':    'introduction',
        'outcomes':        'outcomes',
        'materials':       'materials',
        'procedures':      'procedures',
        'datasheet':       'data_sheet',
        'guide-questions': 'guide_questions',
        'references':      'references',
    }

    # ── Lab title (always first) ──────────────────────────────────────────
    lab_num   = data.get('lab_number', '') or sec.get('lab_number', 'LABORATORY ACTIVITY')
    lab_title = data.get('lab_title',  '') or sec.get('lab_title',  '')
    result = [{
        'type':    'lab_title',
        'title':   lab_num or 'LABORATORY ACTIVITY',
        'content': [{'text': lab_title}] if lab_title else []
    }]

    # ── Build candidate sections keyed by frontend key ────────────────────
    # Each candidate is only added if it actually has content.
    candidates = {}

    intro_structured = sec.get('introduction_structured', None)
    intro = sec.get('introduction', '')
    if intro_structured and isinstance(intro_structured, list) and intro_structured:
        candidates['introduction'] = {
            'type': 'introduction', 'title': 'INTRODUCTION',
            'content': intro_structured
        }
    elif intro:
        candidates['introduction'] = {
            'type': 'introduction', 'title': 'INTRODUCTION',
            'content': [{'text': intro}]
        }

    outcomes = sec.get('outcomes', '')
    if outcomes:
        candidates['outcomes'] = {
            'type': 'outcomes', 'title': 'TARGET LEARNING OUTCOMES',
            'content': [{'text': outcomes}]
        }

    materials = sec.get('materials', [])
    if materials:
        s = {'type': 'materials', 'title': 'MATERIALS', 'content': materials}
        if sec.get('materials_view_html'): s['view_html'] = sec['materials_view_html']
        candidates['materials'] = s

    procedures = sec.get('procedures', [])
    if procedures:
        s = {'type': 'procedures', 'title': 'PROCEDURES', 'content': procedures}
        if sec.get('procedures_view_html'): s['view_html'] = sec['procedures_view_html']
        candidates['procedures'] = s

    ds = {'type': 'data_sheet', 'title': 'DATA SHEET',
          'content': [{'text': sec.get('datasheet_desc', '')}] if sec.get('datasheet_desc') else []}
    if sec.get('datasheet_view_html'): ds['view_html'] = sec['datasheet_view_html']
    candidates['datasheet'] = ds  # always a candidate (may be empty)

    questions = sec.get('guide_questions', [])
    if questions:
        s = {'type': 'guide_questions', 'title': 'GUIDE QUESTIONS', 'content': questions}
        if sec.get('guide_questions_view_html'): s['view_html'] = sec['guide_questions_view_html']
        candidates['guide-questions'] = s

    references = sec.get('references', '')
    if references:
        candidates['references'] = {
            'type': 'references', 'title': 'REFERENCES',
            'content': [{'text': references}]
        }

    # ── Assemble body sections ────────────────────────────────────────────
    if sections_config:
        # New-style: only include what's in sections_config, in its order.
        dup_lookup = {}
        for es in extra_sections:
            dup_lookup[(es.get('key', ''), es.get('instance', 1))] = es

        for cfg in sections_config:
            k        = cfg.get('key', '')
            name     = cfg.get('name', '').strip()
            instance = cfg.get('instance', 1)

            if instance == 1:
                s = candidates.get(k)
                if s:
                    s = dict(s)
                    if name: s['title'] = name
                    result.append(s)
            else:
                # Duplicate instance (Phase 4)
                es   = dup_lookup.get((k, instance))
                html = es.get('html', '') if es else ''
                if html:
                    stype = _key_to_type.get(k)
                    if stype:
                        result.append({
                            'type':    stype,
                            'title':   name or k.replace('-', ' ').title(),
                            'content': [{'text': html}]
                        })
    else:
        # Legacy / DOCX: include all candidates with content in default order.
        for k in ['introduction', 'outcomes', 'materials', 'procedures',
                  'datasheet', 'guide-questions', 'references']:
            if k in candidates:
                result.append(candidates[k])

    # ── Student info (always last) ────────────────────────────────────────
    student_info = data.get('student_info', {})
    members    = student_info.get('members', [])
    group_id   = student_info.get('group_id')
    group_name = student_info.get('group_name', '')

    si_content = []
    for i, m in enumerate(members):
        si_content.append({
            'field': 'Name', 'type': 'member', 'value': m,
            'is_leader': i == 0
        })
    si_content.append({'field': 'Course/Year/Section', 'type': 'dropdown',
                       'value': student_info.get('section', '')})
    si_content.append({'field': 'Date', 'type': 'date',
                       'value': student_info.get('date', '')})
    result.append({
        'type': 'student_info', 'title': 'STUDENT INFORMATION',
        'content': si_content, 'group_id': group_id, 'group_name': group_name
    })

    return result