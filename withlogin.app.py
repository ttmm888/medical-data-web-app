import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify,session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, date, timedelta
from werkzeug.utils import secure_filename
import uuid
import string
import random
from flask_login import UserMixin,LoginManager, login_required, current_user,login_user,logout_user
from werkzeug.security import generate_password_hash, check_password_hash
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

users_db = {}

DATABASE_URL = os.getenv('DATABASE_URL')

# Railway can provide PostgreSQL for free
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv('SECRET_KEY')
app.config['R2_ACCOUNT_ID'] = os.getenv('R2_ACCOUNT_ID')
app.config['R2_ACCESS_KEY_ID'] = os.getenv('R2_ACCESS_KEY_ID')  
app.config['R2_SECRET_ACCESS_KEY'] = os.getenv('R2_SECRET_ACCESS_KEY')
app.config['R2_BUCKET_NAME'] = os.getenv('R2_BUCKET_NAME')

# File upload configuration
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16mb max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx'}

# Create uploads directory with error handling
try:
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
except Exception as e:
    print(f"Could not create uploads folder: {e}")
    app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Redirect here if not logged in
login_manager.login_message = 'Please log in to access this page.'

@login_manager.user_loader
def load_user(user_id):
    """Flask-Login needs this to reload user from session"""
    return User.query.get(int(user_id))


class User(UserMixin, db.Model):
    """User authentication model"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='user')  # 'admin', 'doctor', 'nurse', 'user'
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_login = db.Column(db.DateTime)

    def set_password(self, password):
        """Convert plain password to secure hash"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if provided password matches hash"""
        return check_password_hash(self.password_hash, password)
    
    def can_edit_members(self):
        """Check if user can edit member information"""
        return self.role in ['admin', 'doctor', 'nurse']
    
    def can_delete_members(self):
        """Check if user can delete members"""
        return self.role == 'admin'
    
    def __repr__(self):
        return f'<User {self.username}>'

class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.String(6), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10), nullable=False)
    underlying = db.Column(db.String(200), nullable=False, default='')
    drug_allergy = db.Column(db.String(200), nullable=False, default='')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now)

    doctors = db.relationship("Doctor", backref='member', lazy=True, cascade='all,delete-orphan')
    medications = db.relationship('Medication', backref='member', lazy=True, cascade="all,delete-orphan")
    diagnoses = db.relationship("Diagnosis", backref='member', lazy=True, cascade="all,delete-orphan")
    medical_files = db.relationship('MedicalFile', backref='member', lazy=True, cascade='all,delete-orphan')


    def __repr__(self):
        return f'<Member {self.name}>'

    def to_dict(self):
        return{
        "id":self.id,
        "member_id":self.member_id,
        "name":self.name,
        "date_of_birth":self.date_of_birth.strftime('%Y-%m-%d'),
        'age':self.age,
        "gender":self.gender,
        'drug_allergy':self.drug_allergy,
        'underlying':self.underlying,
        "doctors":[doctor.name for doctor in self.doctors],
        'medications':[medication.name for medication in self.medications],
        'diagnoses':[diag.name for diag in self.diagnoses],
        'created_at':self.created_at.isoformat(),
        'updated_at':self.updated_at.isoformat()
    }

    def get_doctors_list(self):
        return [doctor.name for doctor in self.doctors]
    
    def get_medications_list(self):
        return [med.name for med in self.medications]
    
class Doctor(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    name=db.Column(db.String(100),nullable=False)
    member_id=db.Column(db.Integer,db.ForeignKey('member.id'),nullable=False)


class Medication(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    name=db.Column(db.String(100),nullable=False)
    member_id=db.Column(db.Integer,db.ForeignKey('member.id'),nullable=False)


class Diagnosis(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    name=db.Column(db.String(100),nullable=False)
    member_id=db.Column(db.Integer,db.ForeignKey('member.id'),nullable=False)

class MedicalFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_url = db.Column(db.String(500), nullable=False)  # Changed to store R2 URL
    file_size = db.Column(db.Integer)
    file_type = db.Column(db.String(50))
    description = db.Column(db.String(500))
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # Track who uploaded
    uploaded_at = db.Column(db.DateTime, default=datetime.now)
    uploader = db.relationship('User', backref='uploaded_files')


    def to_dict(self):
        return {
            'id':self.id,
            'filename':self.filename,
            'file_size':self.file_size,
            'file_type':self.file_type,
            'description':self.description,
            'uploaded_at':self.uploaded_at.isoformat(),
            'uploaded_by': self.uploader.username if self.uploader else None
        }
    

def get_r2_client():
    """Create and return R2 client"""
    try:
        return boto3.client(
            's3',
            endpoint_url=f'https://{app.config["R2_ACCOUNT_ID"]}.r2.cloudflarestorage.com',
            aws_access_key_id=app.config['R2_ACCESS_KEY_ID'],
            aws_secret_access_key=app.config['R2_SECRET_ACCESS_KEY']
        )
    except Exception as e:
        print(f"R2 client creation failed: {e}")
        return None

def upload_to_r2(file, filename):
    """Upload file to Cloudflare R2"""
    try:
        r2_client = get_r2_client()
        if not r2_client:
            return None
            
        # Reset file pointer to beginning
        file.seek(0)
        
        # Upload file
        r2_client.upload_fileobj(
            file,
            app.config['R2_BUCKET_NAME'],
            filename,
            ExtraArgs={
                'ContentType': file.content_type,
                'ACL': 'public-read'  # Make file publicly accessible
            }
        )
        
        # Return public URL
        return f"https://pub-{app.config['R2_ACCOUNT_ID']}.r2.dev/{filename}"
        
    except ClientError as e:
        print(f"R2 upload failed: {e}")
        return None

def delete_from_r2(filename):
    """Delete file from R2"""
    try:
        r2_client = get_r2_client()
        if not r2_client:
            return False
            
        r2_client.delete_object(
            Bucket=app.config['R2_BUCKET_NAME'],
            Key=filename
        )
        return True
        
    except ClientError as e:
        print(f"R2 delete failed: {e}")
        return False

def allowed_file(filename):
    return '.' in filename and \
    filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def generate_unique_filename(filename):
    ext=filename.rsplit('.',1)[1].lower()
    unique_id=str(uuid.uuid4())
    return f"{unique_id}.{ext}"

def split_lines(text):
    if isinstance(text,list):
        return text
    if not text:
        return []
    
    return [item.strip() for item in text.replace("\n",",").split(",") if item.strip()]

def create_tables():
    """Create database tables"""
    try:
        with app.app_context():
            db.create_all()
            
            # Create default admin user if none exists
            if not User.query.filter_by(role='admin').first():
                admin = User(
                    username='admin',
                    email='ttchanmail@gmail.com',
                    role='admin'
                )
                admin.set_password('ttmm123') 
                db.session.add(admin)
                db.session.commit()
                print("Default admin user created: admin/ttmm")
                
            print("Database tables created successfully!")
            
    except Exception as e:
        print(f"Database creation error: {e}")


def calculate_age_from_date(dob):
    today=date.today()
    return today.year- dob.year-((today.month,today.day)<(dob.month,dob.day))

def generate_id(length=6):
    while True:
        characters=string.ascii_uppercase + string.digits
        new_id=''.join(random.choice(characters)for _ in range(length))
        if not Member.query.filter_by(member_id=new_id).first():
            return new_id
        
@app.route('/init-db')
def init_db():
    """Manual database initialization endpoint"""
    try:
        with app.app_context():
            db.drop_all()
            db.create_all()
            
            # Create default admin user
            admin = User(
                username='admin',
                email='admin@medical.com',
                role='admin'
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            return f"""
            <h1>Database Initialized Successfully!</h1>
            <p>Tables created: {', '.join(tables)}</p>
            <p>Default admin user created: admin/admin123 (change password!)</p>
            <p><a href="/login">Go to Login</a></p>
            """
    except Exception as e:
        return f"""
        <h1>Database Initialization Failed</h1>
        <p>Error: {str(e)}</p>
        <p><a href="/init-db">Try Again</a></p>
        """
        
@app.route('/admin/users')
@login_required
def admin_users():
    # Only admins can manage users
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('home'))
    
    users = User.query.all()
    return render_template('admin-users.html', users=users)

@app.route('/admin/toggle-user/<int:user_id>', methods=['POST'])
@login_required
def toggle_user_status(user_id):
    if current_user.role != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('home'))
    
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Cannot deactivate your own account.', 'error')
        return redirect(url_for('admin_users'))
    
    user.is_active = not user.is_active
    db.session.commit()
    
    status = 'activated' if user.is_active else 'deactivated'
    flash(f'User {user.username} has been {status}.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/')
@login_required
def home():
    try:
        total_members = Member.query.count()
        recent_members = Member.query.order_by(Member.created_at.desc()).limit(6).all()
        recent_additions = Member.query.filter(
            Member.created_at >= datetime.now() - timedelta(days=30)
        ).count()
        
        return render_template("index.html", 
                             total_members=total_members,
                             recent_members=recent_members,
                             recent_additions=recent_additions,
                             current_user=current_user)
    
    except Exception as e:
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return render_template('error.html', error=str(e))


# Simple test route
@app.route('/test')
def test():
    try:
        # Test database connection
        with app.app_context():
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            # Test if we can count members
            if 'member' in tables:
                count = Member.query.count()
                return f"""
                <h1>✅ Test Successful!</h1>
                <p>Database connected: Yes</p>
                <p>Tables found: {', '.join(tables)}</p>
                <p>Total members: {count}</p>
                <p><a href="/">Go to Main App</a></p>
                """
            else:
                return f"""
                <h1>⚠️ Database Issues</h1>
                <p>Database connected: Yes</p>
                <p>Tables found: {', '.join(tables) if tables else 'None'}</p>
                <p>Member table: Missing</p>
                <p><a href="/init-db">Initialize Database</a></p>
                """
    except Exception as e:
        return f"""
        <h1>❌ Test Failed</h1>
        <p>Error: {str(e)}</p>
        <p><a href="/init-db">Try Database Initialization</a></p>
        """

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Hash the password before storing
        hashed_password = generate_password_hash(password)
        users_db[username] = hashed_password
        
        return "User created successfully!"
    
    return '''
    <form method="post">
        Username: <input name="username" required><br>
        Password: <input name="password" type="password" required><br>
        <button type="submit">Register</button>
    </form>
    '''

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Username and password are required', 'error')
            return render_template('login.html')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password) and user.is_active:
            login_user(user)
            user.last_login = datetime.now()
            db.session.commit()
            
            flash(f'Welcome back, {user.username}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role', 'user')
        
        # Validation
        if not all([username, email, password]):
            flash('All fields are required', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return render_template('register.html')
        
        # Create new user
        user = User(username=username, email=email, role=role)
        user.set_password(password)
        
        try:
            db.session.add(user)
            db.session.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Registration failed: {str(e)}', 'error')
    
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    return f"Welcome, {session['user']}!"

@app.route('/add-member', methods=['GET', 'POST'])
@login_required
def add_member():
    # Check permissions
    if not current_user.can_add_members():
        flash('Access denied. Doctor or admin privileges required.', 'error')
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            date_of_birth = request.form.get('date_of_birth')
            gender = request.form.get('gender')
            underlying = request.form.get('underlying', '').strip()
            drug_allergy = request.form.get('drug_allergy', '').strip()
            
            if not name or not date_of_birth or not gender:
                flash("Name, date of birth and gender are required!", "error")
                return redirect(url_for('add_member'))
            
            dob = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
            
            existing_member = Member.query.filter_by(
                name=name.lower().strip(), 
                date_of_birth=dob
            ).first()
            
            if existing_member:
                flash("Member with the same name and date of birth already exists!", "error")
                return redirect(url_for('home'))

            new_member = Member(
                member_id=generate_id(),
                name=name.strip().lower(),
                date_of_birth=dob,
                age=calculate_age_from_date(dob),
                gender=gender,
                drug_allergy=drug_allergy,
                underlying=underlying,
                created_by=current_user.id  # Track who created
            )
                
            db.session.add(new_member)
            db.session.flush()

            # Add related data
            for doctor_name in split_lines(request.form.get('doctor', '')):
                if doctor_name:
                    doctor = Doctor(name=doctor_name, member_id=new_member.id)
                    db.session.add(doctor)

            for med_name in split_lines(request.form.get('medication', "")):
                if med_name:
                    medication = Medication(name=med_name, member_id=new_member.id)
                    db.session.add(medication)

            for diag_name in split_lines(request.form.get('diagnosis', "")):
                if diag_name:
                    diagnosis = Diagnosis(name=diag_name, member_id=new_member.id)
                    db.session.add(diagnosis)

            db.session.commit()
            flash("Member added successfully!", "success")
            return redirect(url_for('view_member', member_id=new_member.member_id))
        
        except Exception as e:
            db.session.rollback()
            flash(f"An error occurred: {str(e)}", "error")
            return redirect(url_for('home'))
    
    return render_template('add-member.html')

@app.route('/view-member/<member_id>')
@login_required
def view_member(member_id):
    member=Member.query.filter_by(member_id=member_id).first()
    if member:
        return render_template('view-member.html',member=member)
    else:
        flash('Member not found!', 'error')
        return redirect(url_for('home'))
    
@app.route('/update-member/<member_id>', methods=['GET','POST'])
@login_required
def update_member(member_id):
    # Check permissions
    if not current_user.can_edit_members():
        flash('Access denied. Editing privileges required.', 'error')
        return redirect(url_for('view_member', member_id=member_id))
    
    member=Member.query.filter_by(member_id=member_id).first()
    if not member:
        flash("Member not found","error")
        return redirect(url_for('home'))
    
    if request.method=='POST':
        action=request.form.get('action','update_basic')
        try:
            if action=='update_basic':
                update_basic_info(member,request.form)
            elif action in ['add_doctor','edit_doctor','delete_doctor']:
                handle_doctor_actions(member,request.form,action)
            elif action in ['add_medication','edit_medication','delete_medication']:
                handle_medication_actions(member,request.form,action)
            elif action in ['add_diagnosis','edit_diagnosis','delete_diagnosis']:
                handle_diagnosis_actions(member,request.form,action)
            else:
                flash("Invalid action","error")

            member.updated_at=datetime.now()
            db.session.commit()
            flash("Changes saved successfully!","success")

        except Exception as e:
            db.session.rollback()
            flash(F"Error:str{e}","error")
        
        return redirect(url_for('view_member',member_id=member.member_id))
    
    #GET request render the form
    return render_template('update-member.html',member=member)


def update_basic_info(member,form):
    member.name=form.get('name','').strip().lower()
    member.gender=form.get('gender',"")
    dob_str=form.get('date_of_birth',"")
    member.underlying=form.get('underlying','')
    member.drug_allergy=form.get('drug_allergy',"")

    if dob_str:
        member.date_of_birth=datetime.strptime(dob_str,"%Y-%m-%d").date()
        member.age=calculate_age_from_date(member.date_of_birth)

    if not member.name or not member.gender or not dob_str:
        raise ValueError("Name,gender and date of birth are required!")
    
    duplicate=Member.query.filter(
        Member.name==member.name,
        Member.date_of_birth==member.date_of_birth,
        Member.id!=member.id
    ).first()

    if duplicate:
        raise ValueError("Another member with the same name and date_of_birth already exists! ")
    
def handle_doctor_actions(member,form,action):
    if action=='add_doctor':
        doctor_name=form.get('new_doctor',"").strip()
        if doctor_name:
            existing=Doctor.query.filter_by(name=doctor_name,member_id=member.id).first()
            if not existing:
                db.session.add(Doctor(name=doctor_name,member_id=member.id))
            else:
                flash(f"Doctor {doctor_name} already existS!","warning")
    
    elif action=="edit_doctor":
        doctor_id=form.get('doctor_id')
        doctor_new_name=form.get('doctor_new_name',"").strip()
        doctor=Doctor.query.get(doctor_id)
        if doctor and doctor.member_id ==member.id:
            doctor.name=doctor_new_name
        else:
            raise ValueError("Doctor not found!")
    
    elif action=="delete_doctor":
        doctor_id=form.get("doctor_id")
        doctor=Doctor.query.get(doctor_id)
        if doctor and doctor.member_id==member.id:
            db.session.delete(doctor)
        else:
            raise ValueError("Doctor not found!")
        
def handle_medication_actions(member,form,action):
    if action=='add_medication':
        medication_name=form.get('new_medication',"").strip()
        if medication_name:
            existing=Member.query.filter_by(name=medication_name,member_id=member.id).first()
            if not existing:
                db.session.add(Medication(name=medication_name,member_id=member.id))
            else:
                flash(f"Medication {medication_name} already exists!","warning")
    
    elif action=='edit_medication':
        medication_id=form.get('medication_id')
        medication_new_name=form.get('medication_new_name',"").strip()
        medication=Medication.query.get(medication_id)
        if medication and medication.member_id==member.id:
            medication.name=medication_new_name
        else:
            raise ValueError("Medication not found!")
        
    elif action=='delete_medication':
        medication_id=form.get('medication_id')
        medication=Medication.query.get(medication_id)
        if medication and medication.member_id==member.id:
            db.session.delete(medication)
        else:
            raise ValueError("Medication not found!")
        

def handle_diagnosis_actions(member,form,action):
    if action=="add_diagnosis":
        diagnosis_name=form.get('new_diagnosis',"").strip()
        if diagnosis_name:
            existing=Diagnosis.query.filter_by(name=diagnosis_name,member_id=member.id).first()
        if not existing:
            db.session.add(Diagnosis(name=diagnosis_name,member_id=member.id))
        else:
            flash("Diagnosis already exists!","warning")
    
    elif action=='edit_diagnosis':
        diagnosis_id=form.get('diagnosis_id')
        diagnosis_new_name=form.get('diagnosis_new_name',"").strip()
        diagnosis=Diagnosis.query.get(diagnosis_id)
        if diagnosis and diagnosis.member_id==member.id:
            diagnosis.name=diagnosis_new_name
        else:
            raise ValueError("Diagnosis not found")
        
    elif action=='delete_diagnosis':
        diagnosis_id=form.get('diagnosis_id')
        diagnosis=Diagnosis.query.get(diagnosis_id)
        if diagnosis and diagnosis.member_id==member.id:
            db.session.delete(diagnosis)
        else:
            raise ValueError('Diagnosis not found')


@app.route('/delete-member/<member_id>', methods=['POST'])
@login_required
def delete_member(member_id):
    # Check permissions - only admins can delete
    if not current_user.can_delete_members():
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('view_member', member_id=member_id))
    
    member=Member.query.filter_by(member_id=member_id).first()
    if member:
        try:
            db.session.delete(member)
            db.session.commit()
            flash('Member deleted successfully!','success')
        except Exception as e:
            db.session.rollback()
            flash(f"Error deleting member:{str(e)}","error")
    else:
        flash("Member not found!","error")

    return redirect(url_for('home'))

@app.route('/search')
@login_required
def search_member():
    query = request.args.get('query', '').lower()
    if not query:
        flash("Please enter member name or member id!", "error")
        return redirect(url_for('home'))
    
    results = Member.query.filter(
        db.or_(
            Member.name.contains(query),
            Member.member_id.contains(query.upper())
        )
    ).all()
    
    if results:
        return render_template("search-result.html", results=results, query=query)
    else:
        flash("No member found matching your search", "info")
        return redirect(url_for('home'))

@app.route('/api/member/<member_id>')
@login_required
def api_get_member(member_id):
    member=Member.query.filter_by(member_id=member_id).first()
    if member:
        return member.to_dict()
    return {'error':'Member not found'},404

@app.route('/upload-file/<member_id>', methods=['GET', 'POST'])
@login_required
def upload_file(member_id):
    member = Member.query.filter_by(member_id=member_id).first()
    if not member:
        flash("Member not found", "error")
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected', "error")
            return redirect(request.url)

        file = request.files['file']
        description = request.form.get('description', "").strip()

        if file.filename == '':
            flash("No file selected", "error")
            return redirect(request.url)

        if file and allowed_file(file.filename):
            try:
                original_filename = secure_filename(file.filename)
                unique_filename = generate_unique_filename(original_filename)
                
                # Upload to R2 instead of local storage
                if app.config.get('R2_ACCOUNT_ID'):
                    file_url = upload_to_r2(file, unique_filename)
                    if not file_url:
                        flash("Cloud upload failed. Please try again.", "error")
                        return redirect(request.url)
                else:
                    flash("Cloud storage not configured", "error")
                    return redirect(request.url)
                
                medical_file = MedicalFile(
                    filename=original_filename,
                    file_url=file_url,  # Store R2 URL instead of local path
                    file_size=len(file.read()),
                    file_type=file.content_type,
                    description=description,
                    member_id=member.id,
                    uploaded_by=current_user.id  # Track who uploaded
                )
                
                db.session.add(medical_file)
                db.session.commit()

                flash("File uploaded successfully", 'success')
                return redirect(url_for('view_member', member_id=member_id))

            except Exception as e:
                db.session.rollback()
                flash(f"Error uploading file: {str(e)}", "error")
        else:
            flash("Invalid file type. Allowed: PDF, Images, Word documents", "error")

    return render_template('upload-file.html', member=member)

@app.route('/view-file/<int:file_id>')
@login_required
def view_file(file_id):
    medical_file = MedicalFile.query.get_or_404(file_id)
    # Since files are in R2 with public URLs, just redirect
    return redirect(medical_file.file_url)


@app.route('/download-file/<int:file_id>')
@login_required
def download_file(file_id):
    from flask import send_file
    medical_file=MedicalFile.query.get_or_404(file_id)

    try:
        if os.path.exists(medical_file.file_path):
            return send_file(medical_file.file_path,
                             as_attachment=True,
                             download_name=medical_file.filename)
        else:
            flash("File not found on server","error")
            return redirect(url_for('home'))
        
    except Exception as e:
        flash(f"Error downloading file:{str(e)}","error")
        return redirect(url_for('home'))
    

@app.route('/delete-file/<int:file_id>',methods=['POST'])
@login_required
def delete_file(file_id):
    medical_file=MedicalFile.query.get_or_404(file_id)
    member_id=medical_file.member.member_id

    if current_user.role != 'admin' and medical_file.uploaded_by != current_user.id:
        flash('Access denied. You can only delete files you uploaded.', 'error')
        return redirect(url_for('view_member', member_id=member_id))

    try:
        # Extract filename from URL and delete from R2
        filename = medical_file.file_url.split('/')[-1]
        delete_from_r2(filename)
        
        db.session.delete(medical_file)
        db.session.commit()
        flash('File deleted successfully', "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting file: {str(e)}", "error")
    
    return redirect(url_for('view_member', member_id=member_id))

@app.route('/backup-data')
@login_required
def backup_data():
      # Only admins can backup data
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('home'))
    
    try:
        members = Member.query.all()
        backup_data = []
        
        for member in members:
            member_data = {
                'name': member.name,
                'member_id': member.member_id,
                'date_of_birth': member.date_of_birth.strftime('%Y-%m-%d'),
                'gender': member.gender,
                'underlying': member.underlying,
                'drug_allergy': member.drug_allergy,
                'doctors': [d.name for d in member.doctors],
                'medications': [m.name for m in member.medications],
                'diagnoses': [d.name for d in member.diagnoses]
            }
            backup_data.append(member_data)
        
        return jsonify(backup_data)
    
    except Exception as e:
        return f"Backup failed: {str(e)}"
    
@app.route('/export-members')
@login_required
def export_members():
    try:
        members = Member.query.all()
        
        # Create CSV-like format
        export_text = "Name,Member ID,Date of Birth,Gender,Underlying,Drug Allergy\n"
        for member in members:
            export_text += f"{member.name},{member.member_id},{member.date_of_birth},{member.gender},{member.underlying},{member.drug_allergy}\n"
        
        return f"<pre>{export_text}</pre><p>Copy and save this data as backup</p>"
        
    except Exception as e:
        return f"Export failed: {str(e)}"
    
def test():
    try:
        with app.app_context():
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            user_count = User.query.count() if 'user' in tables else 0
            member_count = Member.query.count() if 'member' in tables else 0
            
            r2_status = "✅ Configured" if app.config.get('R2_ACCOUNT_ID') else "❌ Not configured"
            
            return f"""
            <h1>System Status Check</h1>
            <h3>Database</h3>
            <p>Tables: {', '.join(tables) if tables else 'None'}</p>
            <p>Users: {user_count}</p>
            <p>Members: {member_count}</p>
            
            <h3>Cloud Storage</h3>
            <p>Cloudflare R2: {r2_status}</p>
            
            <h3>Quick Actions</h3>
            <ul>
                <li><a href="/init-db">Initialize Database</a></li>
                <li><a href="/login">Login</a></li>
                <li><a href="/register">Register</a></li>
                <li><a href="/">Main App</a></li>
            </ul>
            """
    except Exception as e:
        return f"""
        <h1>❌ System Check Failed</h1>
        <p>Error: {str(e)}</p>
        <p><a href="/init-db">Try Database Initialization</a></p>
        """

if __name__ == '__main__':
    print("Starting Enhanced Medical App...")
    create_tables()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    # This runs when deployed (gunicorn)
    print("Enhanced Medical App started by gunicorn...")
    with app.app_context():
        create_tables()