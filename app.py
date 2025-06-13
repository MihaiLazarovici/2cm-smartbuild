from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
import pandas as pd
import joblib
from twilio.rest import Client
import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///smartbuild.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)


class Estimate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    project_name = db.Column(db.String(100), nullable=False)
    time_frame = db.Column(db.Float, nullable=False)
    max_workers = db.Column(db.Integer, nullable=False)
    items = db.relationship('EstimateItem', backref='estimate', lazy=True)


class EstimateItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    estimate_id = db.Column(db.Integer, db.ForeignKey('estimate.id'), nullable=False)
    element = db.Column(db.String(100), nullable=False)
    unit = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    cost_per_unit = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)
    time_per_unit = db.Column(db.Float, nullable=False)
    allocated_days = db.Column(db.Float, nullable=False)
    people = db.Column(db.Integer, nullable=False)


class InstallationProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    estimate_id = db.Column(db.Integer, db.ForeignKey('estimate.id'), nullable=False)
    element = db.Column(db.String(100), nullable=False)
    days_spent = db.Column(db.Float, nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
def index():
    elements = pd.read_excel('elements.xlsx').to_dict('records')
    print(f"Loaded {len(elements)} elements")
    is_guest = not current_user.is_authenticated or current_user.username.startswith('guest_')
    limited_elements = elements[:5] if is_guest else elements[:24]
    print(
        f"User: {current_user.get_id() or 'None'}, Authenticated: {current_user.is_authenticated}, Is Guest: {is_guest}")
    return render_template('index.html', elements=limited_elements, countries=['UK'], is_guest=is_guest)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            login_user(user)
            return redirect(url_for('index'))
        return 'Invalid credentials', 401
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User(username=username, password=password)
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
    project_name = request.form['projectName']
    time_frame = float(request.form['timeFrame'])
    elements = pd.read_excel('elements.xlsx').to_dict('records')
    is_guest = not current_user.is_authenticated or current_user.username.startswith('guest_')
    limited_elements = elements[:5] if is_guest else elements[:24]

    time_model = joblib.load('models/time_model.pkl')
    cost_model = joblib.load('models/cost_model.pkl')

    result_items = []  # Renamed to avoid confusion with dict.items
    max_workers = 0
    total_time = 0
    for element in limited_elements:
        quantity_str = request.form.get(f'quantity_{element["Element"]}', '0')
        quantity = float(quantity_str) if quantity_str.strip() else 0.0
        people_str = request.form.get(f'people_{element["Element"]}', '0')
        people = int(people_str) if people_str.strip() else 0
        if quantity > 0:
            X = [[quantity, people]]
            predicted_time = time_model.predict(X)[0]
            predicted_cost = cost_model.predict(X)[0]
            total_cost = quantity * predicted_cost
            allocated_days = (predicted_time * quantity) / people if people > 0 else predicted_time * quantity
            total_time += allocated_days
            max_workers = max(max_workers, people)
            result_items.append({
                'element': element['Element'],
                'unit': element['Unit'],
                'quantity': quantity,
                'cost_per_unit': predicted_cost,
                'total_cost': total_cost,
                'time_per_unit': predicted_time,
                'allocated_days': allocated_days,
                'people': people
            })

    if total_time > time_frame and not is_guest:
        client = Client(os.getenv('TWILIO_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
        client.messages.create(
            body=f"Warning: Project {project_name} exceeds time frame of {time_frame} days",
            from_=os.getenv('TWILIO_PHONE'),
            to=os.getenv('ADMIN_PHONE')
        )

    if not is_guest:
        estimate = Estimate(user_id=current_user.id, project_name=project_name, time_frame=time_frame,
                            max_workers=max_workers)
        db.session.add(estimate)
        db.session.commit()
        for item in result_items:
            estimate_item = EstimateItem(
                estimate_id=estimate.id,
                element=item['element'],
                unit=item['unit'],
                quantity=item['quantity'],
                cost_per_unit=item['cost_per_unit'],
                total_cost=item['total_cost'],
                time_per_unit=item['time_per_unit'],
                allocated_days=item['allocated_days'],
                people=item['people']
            )
            db.session.add(estimate_item)
        db.session.commit()

    return render_template('index.html', elements=limited_elements, result={
        'project_name': project_name,
        'time_frame': time_frame,
        'max_workers': max_workers,
        'items': result_items  # Use list, not dict.items
    }, countries=['UK'], is_guest=is_guest)


@app.route('/estimates')
@login_required
def estimates():
    estimates = Estimate.query.filter_by(user_id=current_user.id).all()
    return render_template('estimates.html', estimates=estimates)


@app.route('/download_pdf/<project_name>')
@login_required
def download_pdf(project_name):
    estimate = Estimate.query.filter_by(user_id=current_user.id, project_name=project_name).first()
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.drawString(100, 800, f"Estimate for {project_name}")
    c.drawImage(f"static/images/{'logo_logged_in.png' if current_user.is_authenticated else 'logo_guest.png'}", 50, 750,
                width=100, height=50)
    y = 700
    for item in estimate.items:
        c.drawString(50, y,
                     f"{item.element}: {item.quantity} {item.unit}, Total Cost: {item.total_cost}, Allocated Days: {item.allocated_days}, People: {item.people}")
        y -= 20
    c.showPage()
    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"{project_name}_estimate.pdf")


@app.route('/progress', methods=['POST'])
@login_required
def progress():
    estimate_id = request.form['estimate_id']
    for key, value in request.form.items():
        if key.startswith('progress_'):
            element = key.replace('progress_', '')
            days_spent = float(value)
            estimate = Estimate.query.get(estimate_id)
            for item in estimate.items:
                if item.element == element and days_spent > item.allocated_days:
                    client = Client(os.getenv('TWILIO_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
                    client.messages.create(
                        body=f"Warning: Installation of {element} in {estimate.project_name} exceeds allocated time of {item.allocated_days} days",
                        from_=os.getenv('TWILIO_PHONE'),
                        to=os.getenv('ADMIN_PHONE')
                    )
                    progress = InstallationProgress(estimate_id=estimate_id, element=element, days_spent=days_spent)
                    db.session.add(progress)
    db.session.commit()
    return redirect(url_for('index'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)