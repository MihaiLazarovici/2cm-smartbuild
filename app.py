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
     import joblib
     from datetime import datetime
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

     # Twilio configuration (placeholders, updated later)
     TWILIO_SID = os.environ.get('TWILIO_SID', 'your_twilio_sid')
     TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', 'your_twilio_auth_token')
     TWILIO_PHONE = os.environ.get('TWILIO_PHONE', '+1234567890')
     ADMIN_PHONE = os.environ.get('ADMIN_PHONE', '+your_phone_number')
     twilio_client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

     # Load ML models
     time_model = joblib.load(os.path.join(basedir, 'models/time_model.pkl'))
     cost_model = joblib.load(os.path.join(basedir, 'models/cost_model.pkl'))

     # Database Models
     class User(UserMixin, db.Model):
         id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
         username = db.Column(db.String(80), unique=True, nullable=False)
         password_hash = db.Column(db.String(128), nullable=False)
         is_guest = db.Column(db.Boolean, default=False)

     class Estimate(db.Model):
         id = db.Column(db.Integer, primary_key=True)
         user_id = db.Column(db.String(36), db.ForeignKey('user.id'), nullable=False)
         project_name = db.Column(db.String(100), nullable=False)
         country = db.Column(db.String(50), nullable=False)
         estimates = db.Column(db.Text, nullable=False)
         time_frame_days = db.Column(db.Float, nullable=True)
         created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

     class InstallationProgress(db.Model):
         id = db.Column(db.Integer, primary_key=True)
         estimate_id = db.Column(db.Integer, db.ForeignKey('estimate.id'), nullable=False)
         element = db.Column(db.String(100), nullable=False)
         allocated_days = db.Column(db.Float, nullable=False)
         actual_days = db.Column(db.Float, default=0)
         start_date = db.Column(db.DateTime, default=db.func.current_timestamp())
         notification_sent = db.Column(db.Boolean, default=False)

     @login_manager.user_loader
     def load_user(user_id):
         with db.session() as session:
             return session.get(User, user_id)

     def load_elements():
         df = pd.read_excel(os.path.join(basedir, 'elements.xlsx'))
         print(f"Loaded {len(df)} elements")
         return df

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

     def schedule_elements(inputs, total_time_frame):
         total_base_time = sum(item['time_days'] for item in inputs)
         if total_base_time == 0:
             return inputs, 0
         scale_factor = total_time_frame / total_base_time if total_base_time > total_time_frame else 1
         max_simultaneous_people = 0
         for item in inputs:
             item['allocated_days'] = item['time_days'] * scale_factor
             item['people_needed'] = max(1, int(item['people'] * (item['time_days'] / item['allocated_days'])))
             max_simultaneous_people = max(max_simultaneous_people, item['people_needed'])
         return inputs, max_simultaneous_people

     def calculate_estimates(inputs, elements_df, country='UK', time_frame_days=0):
         multiplier = 1.0
         total_cost = 0
         total_time_days = 0
         total_people = 0
         breakdown = []
         for element, data in inputs.items():
             quantity = data.get('quantity', 0)
             people = data.get('people', 0)
             if quantity > 0:
                 # Use ML model for predictions
                 X = pd.DataFrame([[quantity, people]], columns=['Quantity', 'People'])
                 time_per_unit = time_model.predict(X)[0]
                 cost_per_unit = cost_model.predict(X)[0]
                 element_data = elements_df[elements_df['Element'] == element]
                 if not element_data.empty:
                     cost = cost_per_unit * quantity * multiplier
                     time = time_per_unit * quantity
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
         if time_frame_days > 0:
             breakdown, max_simultaneous_people = schedule_elements(breakdown, time_frame_days)
         else:
             max_simultaneous_people = total_people
         return {
             'total_cost': round(total_cost, 2),
             'total_time_days': round(total_time_days, 2),
             'total_time_weeks': round(total_time_days / 7, 2),
             'total_people': total_people,
             'max_simultaneous_people': max_simultaneous_people,
             'breakdown': breakdown
         }

     def generate_pdf(estimates, project_name, filename, time_frame_days):
         os.makedirs(os.path.join(basedir, 'output/estimates'), exist_ok=True)
         pdf_path = os.path.join(basedir, f'output/estimates/{filename}.pdf')
         doc = SimpleDocTemplate(pdf_path, pagesize=A4)
         elements = []
         styles = getSampleStyleSheet()
         username = current_user.username if current_user.is_authenticated else 'Guest'

         # Logo
         logo_path = os.path.join(basedir, 'static/images/logo.png')
         if os.path.exists(logo_path):
             logo = Image(logo_path, width=150, height=50)
             elements.append(logo)
         elements.append(Spacer(1, 12))
         elements.append(Paragraph(f"Estimate for: {project_name}", styles['Heading2']))
         elements.append(Paragraph(f"User: {username}", styles['Normal']))
         elements.append(Paragraph(f"Time Frame: {time_frame_days} days", styles['Normal']))
         elements.append(Spacer(1, 12))

         # Cost and Time Table
         data = [['Element', 'Quantity', 'Unit', 'Cost (£)', 'Time (Days)', 'Time (Weeks)', 'People', 'Allocated Days']]
         for item in estimates['breakdown']:
             data.append([
                 item['element'],
                 item['quantity'],
                 item['unit'],
                 f"£{item['cost']}",
                 item['time_days'],
                 item['time_weeks'],
                 item['people'],
                 item.get('allocated_days', '-')
             ])
         data.append(['Total', '', '', f"£{estimates['total_cost']}",
                      estimates['total_time_days'], estimates['total_time_weeks'],
                      estimates['total_people'], time_frame_days])
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
         time_frame_days = float(request.form.get('time_frame_days', 0))
         inputs = {
             row['Element']: {
                 'quantity': float(request.form.get(f"quantity_{row['Element']}", 0)),
                 'people': int(request.form.get(f"people_{row['Element']}", 0))
             } for _, row in elements.iterrows()
         }
         estimates = calculate_estimates(inputs, elements, country, time_frame_days)
         if current_user.is_authenticated and not current_user.is_guest:
             estimate = Estimate(
                 user_id=current_user.id,
                 project_name=project_name,
                 country=country,
                 estimates=json.dumps(estimates),
                 time_frame_days=time_frame_days
             )
             db.session.add(estimate)
             db.session.commit()
             for item in estimates['breakdown']:
                 progress = InstallationProgress(
                     estimate_id=estimate.id,
                     element=item['element'],
                     allocated_days=item.get('allocated_days', item['time_days']),
                     start_date=datetime.utcnow()
                 )
                 db.session.add(progress)
             db.session.commit()
             pdf_path = generate_pdf(estimates, project_name, str(uuid.uuid4()), time_frame_days)
         else:
             pdf_path = None
         return jsonify({
             'estimates': estimates,
             'pdf_path': pdf_path,
             'estimate_id': estimate.id if current_user.is_authenticated and not current_user.is_guest else None
         })

     @app.route('/download/<filename>')
     @login_required
     def download(filename):
         if current_user.is_guest:
             return redirect(url_for('index'))
         return send_file(os.path.join(basedir, f'output/estimates/{filename}.pdf'), as_attachment=True)

     @app.route('/estimates')
     @login_required
     def estimates():
         if current_user.is_guest:
             return redirect(url_for('index'))
         with db.session() as session:
             user_estimates = session.query(Estimate).filter_by(user_id=current_user.id).all()
         return render_template('estimates.html', estimates=user_estimates, is_guest=False)

     @app.route('/update_progress/<int:estimate_id>', methods=['POST'])
     @login_required
     def update_progress(estimate_id):
         if current_user.is_guest:
             return jsonify({'success': False, 'message': 'Guest users cannot update progress'})
         estimate = Estimate.query.get_or_404(estimate_id)
         if estimate.user_id != current_user.id:
             return jsonify({'success': False, 'message': 'Unauthorized'})
         data = request.form.to_dict()
         for element, actual_days in data.items():
             progress = InstallationProgress.query.filter_by(estimate_id=estimate_id, element=element).first()
             if progress:
                 progress.actual_days = float(actual_days)
                 if progress.actual_days > progress.allocated_days and not progress.notification_sent:
                     send_notification(element, progress.allocated_days, ADMIN_PHONE)
                     progress.notification_sent = True
                 db.session.commit()
         return jsonify({'success': True})

     with app.app_context():
         db.create_all()

     if __name__ == '__main__':
         port = int(os.environ.get('PORT', 5000))
         app.run(host='0.0.0.0', port=port, debug=False)