import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import joblib
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from twilio.rest import Client
import uuid
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smartbuild.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
basedir = os.path.abspath(os.path.dirname(__file__))

# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_guest = db.Column(db.Boolean, default=False)

class Estimate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    project_name = db.Column(db.String(100))
    country = db.Column(db.String(50))
    estimates = db.Column(db.Text)
    time_frame_days = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class InstallationProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    estimate_id = db.Column(db.Integer, db.ForeignKey('estimate.id'))
    element = db.Column(db.String(100))
    allocated_days = db.Column(db.Float)
    start_date = db.Column(db.DateTime)
    progress_days = db.Column(db.Float, default=0)

# Load models and data
elements_df = pd.read_excel(os.path.join(basedir, 'elements.xlsx'))
time_model = joblib.load(os.path.join(basedir, 'models/time_model.pkl'))
cost_model = joblib.load(os.path.join(basedir, 'models/cost_model.pkl'))
print(f"Loaded time_model from {os.path.join(basedir, 'models/time_model.pkl')}")
print(f"Loaded cost_model from {os.path.join(basedir, 'models/cost_model.pkl')}")

# User loader
@login_manager.user_loader
def load_user(user_id):
    with db.session() as session:
        return session.get(User, user_id)

# Routes
@app.route('/')
def index():
    return render_template('index.html', elements=elements_df.to_dict('records')[:5 if not current_user.is_authenticated else 24])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('index'))
        return "Invalid credentials"
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        hashed_password = generate_password_hash(request.form['password'])
        user = User(username=request.form['username'], password=hashed_password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    print("Redirecting to index")
    return redirect(url_for('index'))

@app.route('/calculate', methods=['POST'])
@login_required
def calculate():
    data = request.get_json()
    project_name = data.get('projectName')
    country = data.get('country', 'UK')
    time_frame_days = int(data.get('timeFrameDays', 0))
    inputs = {k: float(v) for k, v in data.items() if k.startswith('quantity_') or k.startswith('people_')}
    elements = {row['Element']: row for _, row in elements_df.iterrows()}

    def calculate_estimates(inputs, elements_df, country='UK', time_frame_days=0):
        print(f"Inputs: {inputs}")
        print(f"Elements loaded: {len(elements_df)}")
        breakdown = []
        total_cost = 0
        for element, quantity in [(k.replace('quantity_', ''), v) for k, v in inputs.items() if k.startswith('quantity_')]:
            people = inputs.get(f'people_{element}', 1)
            element_data = elements.get(element, {})
            if not element_data:
                continue
            cost_per_unit = element_data['Cost_per_Unit']
            time_per_unit = element_data['Time_per_Unit_Days']
            cost = quantity * cost_per_unit
            time_days = quantity * time_per_unit
            allocated_days = time_days if time_frame_days == 0 else min(time_days, time_frame_days * (quantity / sum(inputs.values())))
            breakdown.append({
                'element': element,
                'quantity': quantity,
                'unit': element_data['Unit'],
                'cost': cost,
                'time_days': time_days,
                'time_weeks': time_days / 7,
                'people': people,
                'allocated_days': allocated_days
            })
            total_cost += cost
        max_people = max(inputs.get(f'people_{e.replace("quantity_", "")}', 1) for e in inputs if e.startswith('quantity_'))
        return {'breakdown': breakdown, 'total_cost': total_cost, 'max_people': max_people}

    estimates = calculate_estimates(inputs, elements_df, country, time_frame_days)
    if current_user.is_authenticated and not current_user.is_guest:
        estimate = Estimate(user_id=current_user.id, project_name=project_name, country=country, estimates=json.dumps(estimates), time_frame_days=time_frame_days)
        db.session.add(estimate)
        db.session.commit()
        for item in estimates['breakdown']:
            if item['allocated_days'] > item['time_days']:
                client = Client(os.getenv('TWILIO_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
                message = client.messages.create(
                    body=f"Warning: Installation of {item['element']} exceeds allocated time ({item['allocated_days']} vs {item['time_days']} days)",
                    from_=os.getenv('TWILIO_PHONE'),
                    to=os.getenv('ADMIN_PHONE')
                )
                print(f"Sent warning SMS: {message.sid}")
        pdf_path = generate_pdf(estimates, project_name, str(uuid.uuid4()), time_frame_days)
        estimates['pdf_path'] = url_for('download_file', filename=os.path.basename(pdf_path))

    return jsonify(estimates)

def generate_pdf(estimates, project_name, pdf_id, time_frame_days):
    pdf_path = os.path.join(basedir, 'output', 'estimates', f'{pdf_id}.pdf')
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    data = [['Element', 'Quantity', 'Unit', 'Cost (£)', 'Time (Days)', 'Allocated Days', 'People']]
    for item in estimates['breakdown']:
        data.append([item['element'], item['quantity'], item['unit'], item['cost'], item['time_days'], item['allocated_days'], item['people']])
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(Paragraph(f"Estimate for {project_name} - Time Frame: {time_frame_days} days", styles['Heading1']))
    elements.append(table)
    elements.append(Paragraph(f"Total Cost: £{estimates['total_cost']}", styles['Normal']))
    doc.build(elements)
    return pdf_path

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(os.path.join(basedir, 'output', 'estimates'), filename, as_attachment=True)

@app.route('/estimates')
@login_required
def estimates():
    estimates = Estimate.query.filter_by(user_id=current_user.id).all()
    return render_template('estimates.html', estimates=estimates)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0')