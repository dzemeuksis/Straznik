import os
import uuid
import json
import base64
import mimetypes
from datetime import datetime
from flask import Flask, Blueprint, render_template, request, redirect, url_for, send_from_directory, jsonify, make_response
import openai
from openai import OpenAI
from PIL import Image, ExifTags

# Configuration
app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
app.config['DATA_FOLDER'] = os.path.join(BASE_DIR, 'data')
app.config['PROMPTS_FOLDER'] = os.path.join(BASE_DIR, 'prompts')
app.config['AI_MODEL'] = os.environ.get('AI_MODEL', 'gpt-4.1-mini-2025-04-14')

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DATA_FOLDER'], exist_ok=True)

# Set OpenAI API key from environment
openai.api_key = os.environ.get('OPENAI_API_KEY')

# Blueprint setup
main = Blueprint('main', __name__)

# Helper functions for JSON and prompts
def load_json(filename):
    path = os.path.join(app.config['DATA_FOLDER'], filename)
    if not os.path.exists(path):
        with open(path, 'w') as f:
            json.dump([], f)
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        # Corrupted or empty file: reinitialize with empty list
        data = []
        with open(path, 'w') as f:
            json.dump(data, f)
        return data

def save_json(filename, data):
    path = os.path.join(app.config['DATA_FOLDER'], filename)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def load_prompt(filename):
    path = os.path.join(app.config['PROMPTS_FOLDER'], filename)
    with open(path, 'r') as f:
        return f.read()
def get_image_metadata(filepath):
    """
    Read all EXIF metadata from an image file.
    Returns a dict mapping EXIF tag names to values, plus parsed keys:
    - photo_time: original DateTimeOriginal or DateTime
    - exif_lat, exif_lng: GPS coordinates in decimal degrees, if available
    """
    try:
        img = Image.open(filepath)
        exif_raw = img._getexif() or {}
        metadata = {}
        # Map EXIF tags to names
        for tag_id, value in exif_raw.items():
            tag = ExifTags.TAGS.get(tag_id, tag_id)
            metadata[tag] = value
        # Extract photo time
        dt = metadata.get('DateTimeOriginal') or metadata.get('DateTime')
        if dt:
            metadata['photo_time'] = dt
        # Process GPS info if present
        gps_info = metadata.get('GPSInfo')
        if isinstance(gps_info, dict):
            # Map GPS sub-tags to names
            gps_data = {}
            for key, val in gps_info.items():
                subtag = ExifTags.GPSTAGS.get(key, key)
                gps_data[subtag] = val
            metadata['GPSInfo'] = gps_data
            # Convert to decimal degrees
            lat = gps_data.get('GPSLatitude')
            lat_ref = gps_data.get('GPSLatitudeRef')
            lon = gps_data.get('GPSLongitude')
            lon_ref = gps_data.get('GPSLongitudeRef')
            def to_degrees(vals):
                d, m, s = vals
                def conv(x):
                    try:
                        return float(x)
                    except Exception:
                        num, den = x
                        return num / den if den else 0
                return conv(d) + conv(m)/60 + conv(s)/3600

            if lat and lat_ref and lon and lon_ref:
                lat_f = to_degrees(lat)
                if lat_ref != 'N':
                    lat_f = -lat_f
                lon_f = to_degrees(lon)
                if lon_ref != 'E':
                    lon_f = -lon_f
                metadata['exif_lat'] = lat_f
                metadata['exif_lng'] = lon_f
        return metadata
    except Exception:
        return {}

# Routes
@main.route('/', methods=['GET', 'POST'])
def index():
    # Landing page: display the report form (new incident)
    return report()

@main.route('/map')
def map_view():
    # Map view for incidents
    return render_template('index.html')

@main.route('/profile', methods=['GET', 'POST'])
def profile():
    user_id = request.cookies.get('user_id')
    users = load_json('users.json')
    user = next((u for u in users if u['user_id'] == user_id), None)
    if request.method == 'POST':
        profile_text = request.form.get('profile_text', '').strip()
        if user:
            user['profile_text'] = profile_text
        else:
            user_id = str(uuid.uuid4())
            user = {
                'user_id': user_id,
                'profile_text': profile_text,
                'created_at': datetime.utcnow().isoformat() + 'Z'
            }
            users.append(user)
        save_json('users.json', users)
        # After saving profile, redirect directly to new report form
        resp = make_response(redirect(url_for('main.report')))
        resp.set_cookie('user_id', user_id)
        return resp
    profile_text = user['profile_text'] if user else ''
    return render_template('profile.html', profile_text=profile_text)

@main.route('/report', methods=['GET', 'POST'])
def report():
    user_id = request.cookies.get('user_id')
    users = load_json('users.json')
    user = next((u for u in users if u['user_id'] == user_id), None)
    if not user:
        return redirect(url_for('main.profile'))
    if request.method == 'POST':
        file = request.files.get('image')
        lat = request.form.get('lat')
        lng = request.form.get('lng')
        if not file or file.filename == '':
            return "No file", 400
        ext = os.path.splitext(file.filename)[1]
        report_id = str(uuid.uuid4())
        filename = report_id + ext
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        # AI description
        image_url = url_for('main.uploaded_file', filename=filename, _external=True)
        # Extract EXIF metadata for prompt
        metadata_dict = get_image_metadata(filepath)
        if metadata_dict:
            metadane = "\n".join(f"{k}: {v}" for k, v in metadata_dict.items())
        else:
            metadane = "Brak metadanych."
        prompt_desc = load_prompt('image_description.txt').format(metadane=metadane)
        # AI description using vision modality via direct image encoding
        # Encode image file as Base64 data URI
        mime_type, _ = mimetypes.guess_type(filepath)
        if not mime_type:
            mime_type = 'application/octet-stream'
        with open(filepath, 'rb') as img_file:
            b64 = base64.b64encode(img_file.read()).decode('utf-8')
        data_uri = f"data:{mime_type};base64,{b64}"
        # Prepare vision client
        client = OpenAI()
        try:
            vision_response = client.responses.create(
                model=app.config['AI_MODEL'],
                input=[{
                    'role': 'user',
                    'content': [
                        {'type': 'input_text', 'text': prompt_desc},
                        {'type': 'input_image', 'image_url': data_uri}
                    ]
                }]
            )
            ai_description = vision_response.output_text.strip()
        except Exception:
            ai_description = 'AI description is unavailable.'
        # AI advice using direct client.responses.create
        prompt_adv = load_prompt('advice.txt').format(
            ai_description=ai_description,
            profile_text=user.get('profile_text', '')
        )
        client = OpenAI()
        try:
            advice_response = client.responses.create(
                model=app.config['AI_MODEL'],
                input=prompt_adv
            )
            ai_advice = advice_response.output_text.strip()
        except Exception:
            ai_advice = 'AI advice is unavailable.'
        # Save report with initial entry, including device and EXIF locations and photo time
        reports = load_json('reports.json')
        created_at = datetime.utcnow().isoformat() + 'Z'
        entry_id = str(uuid.uuid4())
        # EXIF metadata
        exif_meta = get_image_metadata(filepath)
        photo_time = exif_meta.get('photo_time')
        exif_lat = exif_meta.get('exif_lat')
        exif_lng = exif_meta.get('exif_lng')
        # Device location
        try:
            dev_lat = float(lat)
            dev_lng = float(lng)
            device_location = {'lat': dev_lat, 'lng': dev_lng}
        except Exception:
            device_location = None
        entry = {
            'entry_id': entry_id,
            'timestamp': created_at,
            'image_filename': filename,
            'device_location': device_location,
            'photo_time': photo_time,
            'exif_location': {'lat': exif_lat, 'lng': exif_lng} if exif_lat is not None and exif_lng is not None else None,
            'ai_description': ai_description,
            'user_description': '',
            'ai_advice': ai_advice
        }
        # Determine report-level location: prefer device location, fallback to EXIF location if available
        report_location = device_location or entry.get('exif_location')
        report = {
            'report_id': report_id,
            'user_id': user_id,
            'created_at': created_at,
            'location': report_location,
            'entries': [entry],
            # status of confirmation: False = niepotwierdzone
            'confirmed': False
        }
        reports.append(report)
        save_json('reports.json', reports)
        # Save incident
        incidents = load_json('incidents.json')
        incident = {
            'incident_id': str(uuid.uuid4()),
            'reports': [report_id],
            'created_at': created_at
        }
        incidents.append(incident)
        save_json('incidents.json', incidents)
        # After creating a new report, show AI advice in a modal before displaying details
        return redirect(url_for('main.report_detail', report_id=report_id, tip=ai_advice))
    return render_template('report_form.html')

@main.route('/report/<report_id>', methods=['GET', 'POST'])
def report_detail(report_id):
    # View and update a report: allows annotating entries or adding new images
    reports = load_json('reports.json')
    report = next((r for r in reports if r['report_id'] == report_id), None)
    if not report:
        return "Report not found", 404
    if request.method == 'POST':
        action = request.form.get('action')
        tip_msg = None
        if action == 'update_description':
            entry_id = request.form.get('entry_id')
            user_desc = request.form.get('user_description', '').strip()
            for entry in report.get('entries', []):
                if entry.get('entry_id') == entry_id:
                    entry['user_description'] = user_desc
                    break
            # No modal for just saving user description
            tip_msg = None
        elif action == 'add_entry':
            # Add a new entry: capture device & EXIF metadata and run vision+advice
            file = request.files.get('image')
            user_desc = request.form.get('user_description', '').strip()
            # Device location
            lat = request.form.get('lat')
            lng = request.form.get('lng')
            try:
                dev_lat = float(lat)
                dev_lng = float(lng)
                device_location = {'lat': dev_lat, 'lng': dev_lng}
            except Exception:
                device_location = None
            if not file or file.filename == '':
                return "No file", 400
            ext = os.path.splitext(file.filename)[1]
            new_entry_id = str(uuid.uuid4())
            new_filename = new_entry_id + ext
            new_filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
            file.save(new_filepath)
            # EXIF metadata
            exif_meta = get_image_metadata(new_filepath)
            photo_time = exif_meta.get('photo_time')
            exif_lat = exif_meta.get('exif_lat')
            exif_lng = exif_meta.get('exif_lng')
            # Build prompt metadata string
            if exif_meta:
                metadane = "\n".join(f"{k}: {v}" for k, v in exif_meta.items())
            else:
                metadane = "Brak metadanych."
            prompt_desc = load_prompt('image_description.txt').format(metadane=metadane)
            # Encode and call vision
            mime_type, _ = mimetypes.guess_type(new_filepath)
            if not mime_type:
                mime_type = 'application/octet-stream'
            with open(new_filepath, 'rb') as img_file:
                b64 = base64.b64encode(img_file.read()).decode('utf-8')
            data_uri = f"data:{mime_type};base64,{b64}"
            client = OpenAI()
            try:
                vision_resp = client.responses.create(
                    model=app.config['AI_MODEL'],
                    input=[{
                        'role': 'user',
                        'content': [
                            {'type': 'input_text', 'text': prompt_desc},
                            {'type': 'input_image', 'image_url': data_uri}
                        ]
                    }]
                )
                ai_description_new = vision_resp.output_text.strip()
            except Exception:
                ai_description_new = 'AI description is unavailable.'
            # Generate advice
            advice_prompt = load_prompt('advice.txt').format(
                ai_description=ai_description_new,
                profile_text=next((u['profile_text'] for u in load_json('users.json') if u['user_id'] == report.get('user_id')), '')
            )
            try:
                advice_resp = client.responses.create(
                    model=app.config['AI_MODEL'],
                    input=advice_prompt
                )
                ai_advice_new = advice_resp.output_text.strip()
            except Exception:
                ai_advice_new = 'AI advice is unavailable.'
            timestamp = datetime.utcnow().isoformat() + 'Z'
            new_entry = {
                'entry_id': new_entry_id,
                'timestamp': timestamp,
                'image_filename': new_filename,
                'device_location': device_location,
                'photo_time': photo_time,
                'exif_location': {'lat': exif_lat, 'lng': exif_lng} if exif_lat is not None and exif_lng is not None else None,
                'ai_description': ai_description_new,
                'user_description': user_desc,
                'ai_advice': ai_advice_new
            }
            report.setdefault('entries', []).append(new_entry)
            # Show AI advice for the new entry in a modal
            tip_msg = ai_advice_new
        # Persist changes
        save_json('reports.json', reports)
        # Redirect to detail view with confirmation tip
        if tip_msg:
            return redirect(url_for('main.report_detail', report_id=report_id, tip=tip_msg))
        return redirect(url_for('main.report_detail', report_id=report_id))
    # Pass any tip message from query parameters to template
    tip = request.args.get('tip')
    return render_template('report_detail.html', report=report, tip=tip)

@main.route('/reports')
def reports_list():
    # List all reports for the current user
    user_id = request.cookies.get('user_id')
    if not user_id:
        return redirect(url_for('main.profile'))
    all_reports = load_json('reports.json')
    user_reports = [r for r in all_reports if r.get('user_id') == user_id]
    return render_template('reports.html', reports=user_reports)

@main.route('/api/incidents')
def api_incidents():
    incidents = load_json('incidents.json')
    reports = load_json('reports.json')
    out = []
    for inc in incidents:
        rep_list = []
        for rid in inc.get('reports', []):
            r = next((rep for rep in reports if rep['report_id'] == rid), None)
            if not r:
                continue
            # include latest entry for marker popup
            entries = r.get('entries', [])
            if not entries:
                continue
            last = entries[-1]
            rep_list.append({
                'report_id': r['report_id'],
                'location': r['location'],
                'ai_description': last.get('ai_description'),
                'ai_advice': last.get('ai_advice'),
                'image_url': url_for('main.uploaded_file', filename=last.get('image_filename')),
                # confirmation status
                'confirmed': r.get('confirmed', False)
            })
        out.append({
            'incident_id': inc.get('incident_id'),
            'created_at': inc.get('created_at'),
            'reports': rep_list
        })
    return jsonify(out)

@main.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

app.register_blueprint(main)

if __name__ == '__main__':
    app.run(debug=True)