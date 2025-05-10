import os
import uuid
import json
from datetime import datetime
from flask import Flask, Blueprint, render_template, request, redirect, url_for, send_from_directory, jsonify, make_response
import openai

# Configuration
app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
app.config['DATA_FOLDER'] = os.path.join(BASE_DIR, 'data')
app.config['PROMPTS_FOLDER'] = os.path.join(BASE_DIR, 'prompts')
app.config['AI_MODEL'] = os.environ.get('AI_MODEL', 'gpt-4.1-mini')

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
    with open(path, 'r') as f:
        return json.load(f)

def save_json(filename, data):
    path = os.path.join(app.config['DATA_FOLDER'], filename)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def load_prompt(filename):
    path = os.path.join(app.config['PROMPTS_FOLDER'], filename)
    with open(path, 'r') as f:
        return f.read()

# Routes
@main.route('/')
def index():
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
        resp = make_response(redirect(url_for('main.index')))
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
        prompt_desc = load_prompt('image_description.txt').format(image_url=image_url)
        # AI description using configured model
        try:
            resp = openai.ChatCompletion.create(
                model=app.config['AI_MODEL'],
                messages=[{'role': 'user', 'content': prompt_desc}]
            )
            ai_description = resp.choices[0].message.content.strip()
        except Exception:
            ai_description = 'AI description is unavailable.'
        # AI advice
        prompt_adv = load_prompt('advice.txt').format(
            ai_description=ai_description,
            profile_text=user.get('profile_text', '')
        )
        # AI advice using configured model
        try:
            resp2 = openai.ChatCompletion.create(
                model=app.config['AI_MODEL'],
                messages=[{'role': 'user', 'content': prompt_adv}]
            )
            ai_advice = resp2.choices[0].message.content.strip()
        except Exception:
            ai_advice = 'AI advice is unavailable.'
        # Save report
        reports = load_json('reports.json')
        created_at = datetime.utcnow().isoformat() + 'Z'
        report = {
            'report_id': report_id,
            'user_id': user_id,
            'image_filename': filename,
            'created_at': created_at,
            'location': {'lat': float(lat), 'lng': float(lng)},
            'ai_description': ai_description,
            'user_description': '',
            'ai_advice': ai_advice
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
        return redirect(url_for('main.report_detail', report_id=report_id))
    return render_template('report_form.html')

@main.route('/report/<report_id>', methods=['GET', 'POST'])
def report_detail(report_id):
    reports = load_json('reports.json')
    report = next((r for r in reports if r['report_id'] == report_id), None)
    if not report:
        return "Report not found", 404
    if request.method == 'POST':
        user_desc = request.form.get('user_description', '').strip()
        report['user_description'] = user_desc
        save_json('reports.json', reports)
        return redirect(url_for('main.report_detail', report_id=report_id))
    return render_template('report_detail.html', report=report)

@main.route('/api/incidents')
def api_incidents():
    incidents = load_json('incidents.json')
    reports = load_json('reports.json')
    out = []
    for inc in incidents:
        rep_list = []
        for rid in inc.get('reports', []):
            r = next((rep for rep in reports if rep['report_id'] == rid), None)
            if r:
                # Include image URL for thumbnails
                rep_list.append({
                    'report_id': r['report_id'],
                    'location': r['location'],
                    'ai_description': r['ai_description'],
                    'ai_advice': r['ai_advice'],
                    'image_url': url_for('main.uploaded_file', filename=r['image_filename'])
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