from flask import Flask, render_template, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import uuid
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
import joblib
from datetime import datetime, timedelta
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', '2cm-smartbuild-secret-2025')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'smartbuild.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Twilio configuration
TWILIO_SID = os.environ.get('TWILIO_SID', 'your_twilio_sid')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', 'your_twilio_auth_token')
TWILIO_PHONE = os.environ.get('TWILIO_PHONE', '+1234567890')
ADMIN_PHONE = os.environ.get('ADMIN_PHONE', '+your_phone_number')
twilio_client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

# Load ML models
time_model = joblib.load(os.path.join(basedir, 'models/time_model.pkl'))
cost_model = joblib.load(os.path.join(basedir, 'models/cost_model.pkl'))

class User(db.Model, UserMixin):
    id = db.Column(db.String(36), primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_guest = db.Column(db.Boolean, default=False)

class Estimate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'))
    project_name = db.Column(db.String(100))
    country = db.Column(db.String(50))
    data = db.Column(db.Text)
    time_frame_days = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class InstallationProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    estimate_id = db.Column(db.Integer, db.ForeignKey('estimate.id'))
    element = db.Column(db.String(100))
    allocated_days = db.Column(db.Float)
    actual_days = db.Column(db.Float, default=0)
    start_date = db.Column(db.DateTime)
    notification_sent = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)

def load_elements():
    return pd.read_excel(os.path.join(basedir, 'elements.xlsx'))

def send_notification(element, allocated_days, phone_number):
    try:
        message = twilio_client.messages.create(
            body=f"Warning: Installation of {element} has exceeded allocated time of {allocated_days} days.",
            from_=TWILIO_PHONE,
            to=phone_number
        )
        print(f"Notification sent for {element}: {message.sid}")
    except TwilioRestException as e:
        print(f"Twilio error for {element}: {e}")

def schedule_elements(elements_data, total_time_frame):
    # Simple scheduling: Allocate time proportionally, calculate simultaneous workers
    total_base_time = sum(item['time'] for item in elements_data)
    if total_base_time == 0:
        return elements_data, 0
    scale_factor = total_time_frame / total_base_time if total_base_time > total_time_frame else 1
    max_simultaneous_people = 0
    for item in elements_data:
        item['allocated_days'] = item['time'] * scale_factor
        # Calculate people needed to meet allocated time
        item['people_needed'] = max(1, int(item['people'] * (item['time'] / item['allocated_days'])))
        max_simultaneous_people = max(max_simultaneous_people, item['people_needed'])
    return elements_data, max_simultaneous_people

@app.route('/')
def index():
    elements = load_elements()
    if not current_user.is_authenticated:
        guest_user = User(
            id=str(uuid.uuid4()),
            username=f'guest_{uuid.uuid4().hex[:8]}',
            password_hash='',
            is_guest=True
        )
        db.session.add(guest_user)
        db.session.commit()
        login_user(guest_user)
    is_guest = current_user.is_guest if current_user.is_authenticated else False
    print(f"User: {current_user.username if current_user.is_authenticated else 'Anonymous'}, Authenticated: {current_user.is_authenticated}, Is Guest: {is_guest}")
    limited_elements = elements.head(5) if is_guest else elements
    return render_template('index.html', elements=limited_elements, countries=['UK'], is_guest=is_guest)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and not user.is_guest and check_password_hash(user.password_hash, password):
            login_user(user)
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Invalid credentials'})
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'message': 'Username exists'})
        user = User(
            id=str(uuid.uuid4()),
            username=username,
            password_hash=generate_password_hash(password),
            is_guest=False
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return jsonify({'success': True})
    return render_template('register.html')

@app.route('/logout')
def logout():
    logout_user()
    return jsonify({'success': True})

@app.route('/calculate', methods=['POST'])
def calculate():
    data = request.form.to_dict()
    project_name = data.get('project_name', 'Untitled Project')
    country = data.get('country', 'UK')
    time_frame_days = float(data.get('time_frame_days', 0))
    elements = load_elements()
    elements_data = []
    for element in elements['Element']:
        quantity_key = f'quantity_{element}'
        people_key = f'people_{element}'
        if quantity_key in data and float(data[quantity_key]) > 0:
            quantity = float(data[quantity_key])
            people = int(data[people_key])
            # Use ML model to predict time and cost
            X = pd.DataFrame([[quantity, people]], columns=['Quantity', 'People'])
            time_per_unit = time_model.predict(X)[0]
            cost_per_unit = cost_model.predict(X)[0]
            row = elements[elements['Element'] == element].iloc[0]
            cost = quantity * cost_per_unit
            time = quantity * time_per_unit
            elements_data.append({
                'element': element,
                'quantity': quantity,
                'unit': row['Unit'],
                'cost': cost,
                'time': time,
                'people': people,
                'time_per_unit': time_per_unit,
                'cost_per_unit': cost_per_unit
            })
    # Schedule elements
    elements_data, max_simultaneous_people = schedule_elements(elements_data, time_frame_days)
    total_cost = sum(item['cost'] for item in elements_data)
    total_time = sum(item['allocated_days'] for item in elements_data)
    total_people = sum(item['people_needed'] for item in elements_data)
    if current_user.is_authenticated and not current_user.is_guest and elements_data:
        estimate = Estimate(
            user_id=current_user.id,
            project_name=project_name,
            country=country,
            data=str(elements_data),
            time_frame_days=time_frame_days
        )
        db.session.add(estimate)
        db.session.commit()
        # Add installation progress
        for item in elements_data:
            progress = InstallationProgress(
                estimate_id=estimate.id,
                element=item['element'],
                allocated_days=item['allocated_days'],
                start_date=datetime.utcnow()
            )
            db.session.add(progress)
        db.session.commit()
    return jsonify({
        'elements': elements_data,
        'total_cost': total_cost,
        'total_time': total_time,
        'total_people': total_people,
        'max_simultaneous_people': max_simultaneous_people
    })

@app.route('/estimates')
def estimates():
    if not current_user.is_authenticated or current_user.is_guest:
        return jsonify({'success': False, 'message': 'Login required'})
    estimates = Estimate.query.filter_by(user_id=current_user.id).all()
    return render_template('estimates.html', estimates=estimates)

@app.route('/download_pdf/<int:estimate_id>')
def download_pdf(estimate_id):
    estimate = Estimate.query.get_or_404(estimate_id)
    if estimate.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Unauthorized'})
    elements_data = eval(estimate.data)
    pdf_path = os.path.join(basedir, 'output', f'estimate_{estimate_id}.pdf')
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    elements = []
    logo_path = os.path.join(basedir, 'static', 'images', 'logo.png')
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=100, height=50)
        elements.append(logo)
    styles = getSampleStyleSheet()
    elements.append(Paragraph(f"Project: {estimate.project_name}", styles['Heading1']))
    elements.append(Paragraph(f"Country: {estimate.country}", styles['Normal']))
    elements.append(Paragraph(f"Time Frame: {estimate.time_frame_days} days", styles['Normal']))
    data = [['Element', 'Quantity', 'Unit', 'Cost (£)', 'Time (Days)', 'People', 'Allocated Days']]
    for item in elements_data:
        data.append([
            item['element'],
            f"{item['quantity']:.1f}",
            item['unit'],
            f"{item['cost']:.2f}",
            f"{item['time']:.2f}",
            item['people_needed'],
            f"{item['allocated_days']:.2f}"
        ])
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitetext),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(table)
    labor_data = [['Element', 'People Needed']]
    for item in elements_data:
        labor_data.append([item['element'], item['people_needed']])
    elements.append(Paragraph("Labor Allocation", styles['Heading2']))
    labor_table = Table(labor_data)
    labor_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitetext),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(labor_table)
    doc.build(elements)
    return send_file(pdf_path, as_attachment=True)

@app.route('/update_progress/<int:estimate_id>', methods=['POST'])
def update_progress(estimate_id):
    if not current_user.is_authenticated or current_user.is_guest:
        return jsonify({'success': False, 'message': 'Login required'})
    data = request.form.to_dict()
    for element in data:
        progress = InstallationProgress.query.filter_by(estimate_id=estimate_id, element=element).first()
        if progress:
            progress.actual_days = float(data[element])
            if progress.actual_days > progress.allocated_days and not progress.notification_sent:
                send_notification(element, progress.allocated_days, ADMIN_PHONE)
                progress.notification_sent = True
            db.session.commit()
    return jsonify({'success': True})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)