from flask import Flask, render_template, request, redirect, url_for, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import pandas as pd
import os
import joblib
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from io import BytesIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smartbuild.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Load elements
elements_df = pd.read_excel('elements.xlsx')
ELEMENTS = elements_df.to_dict('records')

# Load ML models
time_model = joblib.load('models/time_model.pkl')
cost_model = joblib.load('models/cost_model.pkl')

# SendGrid setup
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
SENDGRID_SENDER = os.getenv('SENDGRID_SENDER')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL')


# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)


class Estimate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    project_name = db.Column(db.String(100))
    time_frame = db.Column(db.Float)
    elements = db.Column(db.JSON)
    max_workers = db.Column(db.Integer)


class InstallationProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    estimate_id = db.Column(db.Integer, db.ForeignKey('estimate.id'), nullable=False)
    element = db.Column(db.String(100))
    progress_days = db.Column(db.Float)
    allocated_days = db.Column(db.Float)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        project_name = request.form.get('project_name')
        time_frame = float(request.form.get('time_frame', 0))
        selected_elements = []
        for element in ELEMENTS:
            quantity = request.form.get(f'quantity_{element["Element"]}')
            people = request.form.get(f'people_{element["Element"]}')
            if quantity and float(quantity) > 0:
                qty = float(quantity)
                ppl = int(people) if people else element['People_per_Unit']
                time_pred = time_model.predict([[qty, ppl]])[0]
                cost_pred = cost_model.predict([[qty, ppl]])[0]
                allocated_days = time_pred * qty
                selected_elements.append({
                    'Element': element['Element'],
                    'Unit': element['Unit'],
                    'Quantity': qty,
                    'People': ppl,
                    'Allocated_Days': allocated_days,
                    'Cost': cost_pred * qty
                })
        max_workers = max([e['People'] for e in selected_elements], default=0)
        if current_user.is_authenticated:
            estimate = Estimate(
                user_id=current_user.id,
                project_name=project_name,
                time_frame=time_frame,
                elements=selected_elements,
                max_workers=max_workers
            )
            db.session.add(estimate)
            db.session.commit()
        return render_template('index.html', elements=selected_elements, project_name=project_name,
                               time_frame=time_frame, max_workers=max_workers,
                               body_class='logged-in' if current_user.is_authenticated else 'guest')

    # Limit to 1 element for guests
    display_elements = ELEMENTS[:1] if not current_user.is_authenticated else ELEMENTS
    return render_template('index.html', elements=display_elements,
                           body_class='logged-in' if current_user.is_authenticated else 'guest')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid credentials', 'error')
        return redirect(url_for('login'))
    return render_template('login.html', body_class='guest')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # Check if username exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists. Please choose a different username.', 'error')
            return redirect(url_for('register'))
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('index'))
    return render_template('register.html', body_class='guest')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/update_progress', methods=['POST'])
@login_required
def update_progress():
    estimate_id = Estimate.query.filter_by(user_id=current_user.id).order_by(Estimate.id.desc()).first().id
    for element in ELEMENTS:
        progress = request.form.get(f'progress_{element["Element"]}')
        if progress and float(progress) > 0:
            allocated_days = next((e['Allocated_Days'] for e in Estimate.query.get(estimate_id).elements
                                   if e['Element'] == element['Element']), 0)
            if float(progress) > allocated_days:
                message = Mail(
                    from_email=SENDGRID_SENDER,
                    to_emails=ADMIN_EMAIL,
                    subject='2CM SmartBuild: Progress Warning',
                    html_content=f'<strong>Warning: Installation of {element["Element"]} exceeds allocated time ({progress} > {allocated_days} days)</strong>'
                )
                try:
                    sg = SendGridAPIClient(SENDGRID_API_KEY)
                    sg.send(message)
                except Exception as e:
                    print(f"Email error: {e}")
            progress_entry = InstallationProgress(
                estimate_id=estimate_id,
                element=element['Element'],
                progress_days=float(progress),
                allocated_days=allocated_days
            )
            db.session.add(progress_entry)
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/download_pdf')
@login_required
def download_pdf():
    estimate = Estimate.query.filter_by(user_id=current_user.id).order_by(Estimate.id.desc()).first()
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.drawString(100, 750, f"Project: {estimate.project_name}")
    c.drawString(100, 730, f"Time Frame: {estimate.time_frame} days")
    c.drawString(100, 710, f"Max Workers: {estimate.max_workers}")
    y = 690
    for element in estimate.elements:
        c.drawString(100, y, f"{element['Element']}: {element['Quantity']} {element['Unit']}, "
                             f"{element['People']} people, {element['Allocated_Days']:.2f} days, ${element['Cost']:.2f}")
        y -= 20
    c.drawImage('static/images/logo.png', 400, 700, width=100, height=50, preserveAspectRatio=True)
    c.showPage()
    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='estimate.pdf')


with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
