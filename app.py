from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import os
import json
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = '2cm-smartbuild-secret-2025'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smartbuild.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_guest = db.Column(db.Boolean, default=False)

class Estimate(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
    project_name = db.Column(db.String(100), nullable=False)
    country = db.Column(db.String(50), nullable=False)
    estimates = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

@login_manager.user_loader
def load_user(user_id):
    with db.session() as session:
        return session.get(User, user_id)

def load_elements():
    df = pd.read_excel('elements.xlsx')  # Change to 'elements.csv' if needed
    print(f"Loaded {len(df)} elements")
    return df

def calculate_estimates(inputs, elements_df, country='UK'):
    multiplier = 1.0
    total_cost = 0
    total_time_days = 0
    total_people = 0
    breakdown = []
    for element, data in inputs.items():
        quantity = data.get('quantity', 0)
        people = data.get('people', 0)
        if quantity > 0:
            element_data = elements_df[elements_df['Element'] == element]
            if not element_data.empty:
                cost = element_data['Cost_per_Unit_GBP'].iloc[0] * quantity * multiplier
                time = element_data['Time_per_Unit_Days'].iloc[0] * quantity
                total_cost += cost
                total_time_days += time
                total_people += people
                breakdown.append({
                    'element': element,
                    'quantity': quantity,
                    'unit': element_data['Unit'].iloc[0],
                    'cost': round(cost, 2),
                    'time_days': round(time, 2),
                    'time_weeks': round(time / 7, 2),
                    'people': people
                })
    return {
        'total_cost': round(total_cost, 2),
        'total_time_days': round(total_time_days, 2),
        'total_time_weeks': round(total_time_days / 7, 2),
        'total_people': total_people,
        'breakdown': breakdown
    }

def generate_pdf(estimates, project_name, filename):
    os.makedirs('output/estimates', exist_ok=True)
    pdf_path = f'output/estimates/{filename}.pdf'
    doc = SimpleDocTemplate(pdf_path, pagesize=A4)
    elements = []
    styles = getSampleStyleSheet()
    username = current_user.username if current_user.is_authenticated else 'Guest'

    # Logo
    logo_path = os.path.join('static', 'images', 'logo.png')
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=150, height=50)
        elements.append(logo)
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"Estimate for: {project_name}", styles['Heading2']))
    elements.append(Paragraph(f"User: {username}", styles['Normal']))
    elements.append(Spacer(1, 12))

    # Cost and Time Table
    data = [['Element', 'Quantity', 'Unit', 'Cost (£)', 'Time (Days)', 'Time (Weeks)', 'People']]
    for item in estimates['breakdown']:
        data.append([
            item['element'],
            item['quantity'],
            item['unit'],
            f"£{item['cost']}",
            item['time_days'],
            item['time_weeks'],
            item['people']
        ])
    data.append(['Total', '', '', f"£{estimates['total_cost']}",
                 estimates['total_time_days'], estimates['total_time_weeks'], estimates['total_people']])
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(table)
    elements.append(Spacer(1, 12))

    # Labor Histogram Data
    elements.append(Paragraph("Labor Distribution", styles['Heading2']))
    labor_data = [['Element', 'Number of People']]
    for item in estimates['breakdown']:
        labor_data.append([item['element'], item['people']])
    labor_table = Table(labor_data)
    labor_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(labor_table)

    doc.build(elements)
    return pdf_path

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
        with db.session() as session:
            user = session.query(User).filter_by(username=username).first()
        if user and not user.is_guest and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with db.session() as session:
            if session.query(User).filter_by(username=username).first():
                return render_template('register.html', error='Username exists')
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            is_guest=False
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/calculate', methods=['POST'])
def calculate():
    elements = load_elements()
    project_name = request.form.get('project_name', 'Untitled Project')
    country = request.form.get('country', 'UK')
    inputs = {
        row['Element']: {
            'quantity': float(request.form.get(f"quantity_{row['Element']}", 0)),
            'people': int(request.form.get(f"people_{row['Element']}", 0))
        } for _, row in elements.iterrows()
    }
    estimates = calculate_estimates(inputs, elements, country)
    if current_user.is_authenticated and not current_user.is_guest:
        estimate = Estimate(
            user_id=current_user.id,
            project_name=project_name,
            country=country,
            estimates=json.dumps(estimates)
        )
        db.session.add(estimate)
        db.session.commit()
        pdf_path = generate_pdf(estimates, project_name, str(uuid.uuid4()))
    else:
        pdf_path = None
    return jsonify({
        'estimates': estimates,
        'pdf_path': pdf_path
    })

@app.route('/download/<filename>')
@login_required
def download(filename):
    if current_user.is_guest:
        return redirect(url_for('index'))
    return send_file(f'output/estimates/{filename}.pdf', as_attachment=True)

@app.route('/estimates')
@login_required
def estimates():
    if current_user.is_guest:
        return redirect(url_for('index'))
    with db.session() as session:
        user_estimates = session.query(Estimate).filter_by(user_id=current_user.id).all()
    return render_template('estimates.html', estimates=user_estimates, is_guest=False)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)