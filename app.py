import os
import io
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify,session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, date, timedelta
from werkzeug.utils import secure_filename
import uuid
import string
import random
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config
import os
import ssl
import requests
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

users_db = {}

DATABASE_URL = os.getenv('DATABASE_URL')
DATABASE_URL = os.environ.get('DATABASE_URL') or 'sqlite:///medical.db'
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    # PostgreSQL-specific code here
    pass

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
    name=db.Column(db.String(1000),nullable=False)
    member_id=db.Column(db.Integer,db.ForeignKey('member.id'),nullable=False)

class MedicalFile(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    filename=db.Column(db.String(255),nullable=False) #original filename
    file_path=db.Column(db.String(500),nullable=False) #local file for now
    file_size=db.Column(db.Integer) #file size in bytes
    file_type=db.Column(db.String(50)) #MIME type
    description=db.Column(db.String(500)) #user description
    member_id=db.Column(db.Integer,db.ForeignKey('member.id'),nullable=False)
    uploaded_at =db.Column(db.DateTime,default=datetime.now)

    def to_dict(self):
        return {
            'id':self.id,
            'filename':self.filename,
            'file_size':self.file_size,
            'file_type':self.file_type,
            'description':self.description,
            'uploaded_at':self.uploaded_at.isoformat()
        }
    
def setup_r2_config():
    """Setup and validate R2 configuration with better validation"""
    r2_config = {
        'account_id': os.getenv('R2_ACCOUNT_ID'),
        'access_key': os.getenv('R2_ACCESS_KEY_ID'),
        'secret_key': os.getenv('R2_SECRET_ACCESS_KEY'),
        'bucket_name': os.getenv('R2_BUCKET_NAME')
    }
    
    # Debug: Print what we have (without showing full credentials)
    print(f"🔍 R2 Config Check:")
    print(f"  Account ID: {'✓' if r2_config['account_id'] else '✗'} ({r2_config['account_id'][:8]}... if {r2_config['account_id']} else 'Missing')")
    print(f"  Access Key: {'✓' if r2_config['access_key'] else '✗'} ({'Set' if r2_config['access_key'] else 'Missing'})")
    print(f"  Secret Key: {'✓' if r2_config['secret_key'] else '✗'} ({'Set' if r2_config['secret_key'] else 'Missing'})")
    print(f"  Bucket Name: {'✓' if r2_config['bucket_name'] else '✗'} ({r2_config['bucket_name'] or 'Missing'})")
    
    # Validate all required variables are present
    missing_vars = [key for key, value in r2_config.items() if not value]
    if missing_vars:
        print(f"⚠️ Missing R2 environment variables: {missing_vars}")
        print("Files will be stored locally instead of R2")
        return None
    
    print("✅ R2 configuration loaded successfully")
    return r2_config

# Initialize R2 config
R2_CONFIG = setup_r2_config()

def get_r2_client():
    """Create R2 client with environment variables and proper SSL configuration"""

    account_id = os.getenv("R2_ACCOUNT_ID")
    access_key = os.getenv("R2_ACCESS_KEY_ID")
    secret_key = os.getenv("R2_SECRET_ACCESS_KEY")

    if not account_id or not access_key or not secret_key:
        print("❌ Missing one or more R2 environment variables")
        return None

    try:
        config = Config(
            region_name='auto',
            retries={'max_attempts': 3, 'mode': 'adaptive'},
            s3={'addressing_style': 'path'}
        )

        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
        print(f"🔗 Connecting to R2 endpoint: {endpoint_url}")

        client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=config
        )
        return client

    except Exception as e:
        print(f"❌ R2 client creation failed: {e}")
        return None

def test_r2_connection():
    """Test R2 connection with better error handling"""
    if not R2_CONFIG:
        return False, "R2 not configured - check environment variables"
    
    print("🧪 Testing R2 connection...")
    
    try:
        # Method 1: Try with boto3 client
        r2_client = get_r2_client()
        if not r2_client:
            return False, "Could not create R2 client"
        
        print("✓ R2 client created successfully")
        
        # Test bucket access with minimal request
        response = r2_client.head_bucket(Bucket=R2_CONFIG['bucket_name'])
        print("✓ Bucket accessible")
        
        return True, f"R2 connection successful! Bucket '{R2_CONFIG['bucket_name']}' is accessible"
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        print(f"❌ ClientError: {error_code}")
        
        if error_code == 'NoSuchBucket':
            return False, f"Bucket '{R2_CONFIG['bucket_name']}' does not exist. Check bucket name in Cloudflare dashboard."
        elif error_code == 'AccessDenied':
            return False, "Access denied. Check your R2 API token permissions."
        elif error_code == 'InvalidAccessKeyId':
            return False, "Invalid access key. Check your R2_ACCESS_KEY_ID."
        elif error_code == 'SignatureDoesNotMatch':
            return False, "Invalid secret key. Check your R2_SECRET_ACCESS_KEY."
        else:
            return False, f"R2 error: {error_code} - {e.response['Error'].get('Message', 'No additional info')}"
            
    except ssl.SSLError as e:
        print(f"❌ SSL Error: {e}")
        return False, f"SSL/TLS error: {str(e)}. This might be a network/firewall issue."
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        
        # Try alternative method - direct HTTP request
        try:
            print("🔄 Trying alternative connection test...")
            endpoint_url = f"https://{R2_CONFIG['account_id']}.r2.cloudflarestorage.com"
            response = requests.head(endpoint_url, timeout=10)
            print(f"✓ HTTP connection to endpoint works (status: {response.status_code})")
            return False, f"R2 endpoint is reachable but boto3 failed: {str(e)}"
        except Exception as http_e:
            return False, f"Connection completely failed. Original error: {str(e)}. HTTP test: {str(http_e)}"

def upload_to_r2(file, filename, member_id):
    """Upload file to R2 with better error handling"""
    if not R2_CONFIG:
        print("⚠️ R2 not configured, using local storage")
        return None
    
    try:
        r2_client = get_r2_client()
        if not r2_client:
            print("❌ Could not create R2 client")
            return None
        
        # Organize files by member ID
        r2_key = f"members/{member_id}/{filename}"
        
        print(f"📤 Uploading to R2: {r2_key}")
        
        # Reset file pointer to beginning
        file.seek(0)
        
        # Get content type - handle both file objects and BytesIO objects
        if hasattr(file, 'content_type') and file.content_type:
            content_type = file.content_type
        else:
            # For BytesIO objects or when content_type is None, determine from filename
            import mimetypes
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = 'application/octet-stream'
        
        print(f"📄 Content type: {content_type}")
        
        # Upload with proper content type
        r2_client.upload_fileobj(
            file,
            R2_CONFIG['bucket_name'],
            r2_key,
            ExtraArgs={
                'ContentType': content_type,
                'Metadata': {
                    'member_id': str(member_id),
                    'uploaded_by': 'medical_app'
                }
            }
        )
        
        print(f"✅ File uploaded successfully: {r2_key}")
        return r2_key
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        print(f"❌ R2 upload failed - {error_code}: {e.response['Error'].get('Message', 'No details')}")
        return None
    except Exception as e:
        print(f"❌ Upload error: {e}")
        return None

def download_from_r2(r2_key):
    """Generate presigned URL for R2 download"""
    if not R2_CONFIG:
        return None
    
    try:
        r2_client = get_r2_client()
        if not r2_client:
            return None
        
        # Generate presigned URL (valid for 1 hour)
        url = r2_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': R2_CONFIG['bucket_name'],
                'Key': r2_key
            },
            ExpiresIn=3600  # 1 hour
        )
        
        print(f"🔗 Generated download URL for: {r2_key}")
        return url
        
    except Exception as e:
        print(f"❌ Error generating download URL: {e}")
        return None

def delete_from_r2(r2_key):
    """Delete file from R2"""
    if not R2_CONFIG:
        return False
    
    try:
        r2_client = get_r2_client()
        if not r2_client:
            return False
        
        r2_client.delete_object(
            Bucket=R2_CONFIG['bucket_name'],
            Key=r2_key
        )
        
        print(f"🗑️ File deleted from R2: {r2_key}")
        return True
        
    except ClientError as e:
        print(f"❌ R2 delete failed: {e}")
        return False

def allowed_file(filename):
    return '.' in filename and \
    filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def generate_unique_filename(filename):
    ext=filename.rsplit('.',1)[1].lower()
    unique_id=str(uuid.uuid4())
    return f"{unique_id}.{ext}"

def split_lines(text):
    """Split text into lines with better handling"""
    if not text or not isinstance(text, str):
        return []
    
    if isinstance(text, list):
        return [item.strip() for item in text if item and item.strip()]
    
    # Handle various separators
    separators = ['\n', ',', ';', '|']
    items = [text]
    
    for sep in separators:
        new_items = []
        for item in items:
            new_items.extend(item.split(sep))
        items = new_items
    
    # Clean and filter items
    return [item.strip() for item in items if item and item.strip() and len(item.strip()) > 0]

def create_tables():
    """Enhanced table creation with better error handling"""
    try:
        with app.app_context():
            app.logger.info("🔧 Starting database setup...")
            
            # Test connection first
            try:
                connection = db.engine.connect()
                connection.close()
                app.logger.info("✅ Database connection successful")
            except Exception as conn_error:
                app.logger.error(f"❌ Database connection failed: {conn_error}")
                # Don't fail here, let SQLAlchemy retry
            
            # Check/create tables
            from sqlalchemy import inspect
            try:
                inspector = inspect(db.engine)
                existing_tables = inspector.get_table_names()
                app.logger.info(f"📋 Existing tables: {existing_tables}")
                
                required_tables = {'member', 'doctor', 'medication', 'diagnosis', 'medical_file'}
                missing_tables = required_tables - set(existing_tables)
                
                if missing_tables:
                    app.logger.info(f"🏗️ Creating missing tables: {missing_tables}")
                    db.create_all()
                    
                    # Verify creation
                    new_tables = inspector.get_table_names()
                    app.logger.info(f"✅ Tables after creation: {new_tables}")
                else:
                    app.logger.info("✅ All required tables exist")
                    
            except Exception as table_error:
                app.logger.error(f"❌ Table management error: {table_error}")
                # Try to create anyway
                try:
                    db.create_all()
                    app.logger.info("✅ Created tables despite inspection error")
                except Exception as create_error:
                    app.logger.error(f"❌ Table creation failed: {create_error}")
                    raise create_error
                    
    except Exception as e:
        app.logger.error(f"❌ Database setup failed: {e}")
        raise e
    
# Add database health check
@app.route('/db-health')
def database_health():
    """Check database health and connection"""
    try:
        # Test connection
        db.engine.connect()
        
        # Test table existence
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        # Test a simple query
        try:
            member_count = Member.query.count()
            query_test = f"✅ Query successful - {member_count} members"
        except Exception as e:
            query_test = f"❌ Query failed: {e}"
        
        return {
            "database_connected": True,
            "database_url": DATABASE_URL[:50] + "..." if len(DATABASE_URL) > 50 else DATABASE_URL,
            "tables": tables,
            "query_test": query_test,
            "sqlalchemy_version": db.__version__ if hasattr(db, '__version__') else "unknown"
        }
        
    except Exception as e:
        return {
            "database_connected": False,
            "error": str(e),
            "database_url": DATABASE_URL[:50] + "..." if DATABASE_URL else "Not set"
        }, 500

def setup_database():
    """Configure database with Railway-specific handling"""
    DATABASE_URL = os.environ.get('DATABASE_URL')
    
    if not DATABASE_URL:
        # Try Railway's PostgreSQL environment variables
        PGHOST = os.environ.get('PGHOST')
        PGPORT = os.environ.get('PGPORT', '5432')
        PGUSER = os.environ.get('PGUSER')
        PGPASSWORD = os.environ.get('PGPASSWORD')
        PGDATABASE = os.environ.get('PGDATABASE')
        
        if all([PGHOST, PGUSER, PGPASSWORD, PGDATABASE]):
            DATABASE_URL = f"postgresql://{PGUSER}:{PGPASSWORD}@{PGHOST}:{PGPORT}/{PGDATABASE}"
            app.logger.info("✅ Constructed DATABASE_URL from Railway variables")
        else:
            # Fallback to SQLite for development
            DATABASE_URL = 'sqlite:///medical.db'
            app.logger.warning("⚠️ Using SQLite fallback - PostgreSQL not configured")
    
    # Fix postgres:// vs postgresql:// issue
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        app.logger.info("✅ Fixed postgres:// URL format")
    
    return DATABASE_URL

# Replace your database configuration with:
DATABASE_URL = setup_database()
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Add connection pooling for Railway
if 'postgresql://' in DATABASE_URL:
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 10,
        'pool_recycle': 120,
        'pool_pre_ping': True,
        'max_overflow': 20,
        'pool_timeout': 30
    }

# Add this debug route to test your database
@app.route('/debug-db')
def debug_database():
    try:
        # Test database connection
        db.engine.connect()
        
        # Check tables
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        # Try to count members
        member_count = Member.query.count()
        
        return f"""
        <h1>Database Debug Info</h1>
        <p>✅ Database connected successfully</p>
        <p>📊 Tables: {', '.join(tables)}</p>
        <p>👥 Total members: {member_count}</p>
        <p><a href="/add-member">Try Add Member</a></p>
        <p><a href="/">Back to Home</a></p>
        """
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        return f"""
        <h1>Database Debug - ERROR</h1>
        <p>❌ Error: {str(e)}</p>
        <pre>{error_trace}</pre>
        <p><a href="/init-db">Initialize Database</a></p>
        """

def calculate_age_from_date(dob):
    today=date.today()
    return today.year- dob.year-((today.month,today.day)<(dob.month,dob.day))

def generate_id(length=6):
    """Generate unique member ID with better error handling"""
    import string
    import random
    
    max_attempts = 50
    for attempt in range(max_attempts):
        try:
            characters = string.ascii_uppercase + string.digits
            new_id = ''.join(random.choice(characters) for _ in range(length))
            
            # Check if ID already exists
            existing = Member.query.filter_by(member_id=new_id).first()
            if not existing:
                return new_id
                
        except Exception as e:
            app.logger.error(f"Error checking member ID uniqueness (attempt {attempt}): {e}")
            if attempt > 10:  # After 10 attempts, try without database check
                characters = string.ascii_uppercase + string.digits
                return ''.join(random.choice(characters) for _ in range(length))
    
    # Fallback: timestamp-based ID
    from datetime import datetime
    timestamp = str(int(datetime.now().timestamp()))[-6:]
    return f"M{timestamp}"

        
@app.route('/init-db')
def init_db():
    """Manual database initialization endpoint"""
    try:
        with app.app_context():
            # Drop and recreate all tables
            db.drop_all()
            db.create_all()
            
            # Verify tables exist
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            return f"""
            <h1>Database Initialized Successfully!</h1>
            <p>Tables created: {', '.join(tables)}</p>
            <p><a href="/">Go to Main App</a></p>
            """
    except Exception as e:
        return f"""
        <h1>Database Initialization Failed</h1>
        <p>Error: {str(e)}</p>
        <p><a href="/init-db">Try Again</a></p>
        """

# Improved home route with database checks
@app.route('/')
def home():
    try:
        # Ensure database tables exist before any queries
        with app.app_context():
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            # If no tables exist, create them
            if 'member' not in tables:
                print("Member table not found. Creating tables...")
                db.create_all()
        
        # Now safely query the database
        total_members = Member.query.count()
        recent_members = Member.query.order_by(Member.created_at.desc()).limit(6).all()
        recent_additions = Member.query.filter(
            Member.created_at >= datetime.now() - timedelta(days=30)
        ).count()
        
        return render_template("index.html", 
                             total_members=total_members,
                             recent_members=recent_members,
                             recent_additions=recent_additions)
    
    except Exception as e:
        # If templates are missing or other errors, show a simple page
        return f"""
        <html>
        <head><title>Medical App</title></head>
        <body>
            <h1>Medical Records App</h1>
            <h2>Database Status</h2>
            <p>Error: {str(e)}</p>
            <h3>Quick Actions:</h3>
            <ul>
                <li><a href="/init-db">Initialize Database</a></li>
                <li><a href="/test">Test Connection</a></li>
                <li><a href="/add-member">Add Member (if DB works)</a></li>
            </ul>
        </body>
        </html>
        """

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

@app.route('/add-member', methods=['GET', 'POST'])
def add_member():
    if request.method == 'POST':
        try: 
            # Get form data with better validation
            name = request.form.get('name', '').strip()
            date_of_birth = request.form.get('date_of_birth', '').strip()
            gender = request.form.get('gender', '').strip()
            underlying = request.form.get('underlying', '').strip()
            drug_allergy = request.form.get('drug_allergy', '').strip()

            print(f"Debug - Received form data: name='{name}', dob='{date_of_birth}', gender='{gender}'")

            # Validation
            if not name or not date_of_birth or not gender:
                flash("Name, date of birth and gender are required!", "error")
                return redirect(url_for('add_member'))

            # Validate date format
            try:
                dob = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
                print(f"Debug - Parsed date: {dob}")
            except ValueError as e:
                print(f"Debug - Date parsing error: {e}")
                flash("Invalid date format. Please use YYYY-MM-DD format.", "error")
                return redirect(url_for('add_member'))

            # Check duplicate with better logic
            existing_member = Member.query.filter_by(
                name=name.lower(), 
                date_of_birth=dob
            ).first()
            
            if existing_member:
                print(f"Debug - Duplicate member found: {existing_member.name}")
                flash("Member with the same name and date of birth already exists!", "error")
                return redirect(url_for('add_member'))

            # Create new member
            new_member = Member(
                member_id=generate_id(),
                name=name.lower(),  # Store in lowercase for consistency
                date_of_birth=dob,
                age=calculate_age_from_date(dob),
                gender=gender, 
                drug_allergy=drug_allergy,
                underlying=underlying
            )
            
            print(f"Debug - Created new member object: {new_member.name}")
            
            # Add to database
            db.session.add(new_member)
            db.session.flush()  # This gets the ID without committing
            print(f"Debug - Member added to session, ID: {new_member.id}")

            # Add related information
            # Doctors
            doctor_text = request.form.get('doctor', '').strip()
            if doctor_text:
                for doctor_name in split_lines(doctor_text):
                    if doctor_name.strip():
                        doctor = Doctor(name=doctor_name.strip(), member_id=new_member.id)
                        db.session.add(doctor)
                        print(f"Debug - Added doctor: {doctor_name}")

            # Medications
            medication_text = request.form.get('medication', '').strip()
            if medication_text:
                for med_name in split_lines(medication_text):
                    if med_name.strip():
                        medication = Medication(name=med_name.strip(), member_id=new_member.id)
                        db.session.add(medication)
                        print(f"Debug - Added medication: {med_name}")

            # Diagnoses
            diagnosis_text = request.form.get('diagnosis', '').strip()
            if diagnosis_text:
                for diag_name in split_lines(diagnosis_text):
                    if diag_name.strip():
                        diagnosis = Diagnosis(name=diag_name.strip(), member_id=new_member.id)
                        db.session.add(diagnosis)
                        print(f"Debug - Added diagnosis: {diag_name}")

            # Commit all changes
            db.session.commit()
            print(f"Debug - Successfully committed member: {new_member.member_id}")

            flash("Member added successfully!", "success")
            return redirect(url_for('view_member', member_id=new_member.member_id))
        
        except Exception as e:
            # Rollback any changes if error occurs
            db.session.rollback()
            print(f"DEBUG ERROR in add_member: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()  # This prints the full error trace
            
            flash(f"An error occurred while adding member: {str(e)}", "error")
            return redirect(url_for('add_member'))

    # GET request: Show the form
    try:
        return render_template('add-member.html')
    except Exception as e:
        print(f"DEBUG ERROR rendering template: {str(e)}")
        # Return a simple HTML form if template fails
        return '''
        <html>
        <body>
        <h2>Add Member (Backup Form)</h2>
        <form action="/add-member" method="POST">
            <p><label>Name: <input type="text" name="name" required></label></p>
            <p><label>Date of Birth: <input type="date" name="date_of_birth" required></label></p>
            <p><label>Gender: 
                <select name="gender" required>
                    <option value="">Select</option>
                    <option value="Male">Male</option>
                    <option value="Female">Female</option>
                </select>
            </label></p>
            <p><label>Underlying: <textarea name="underlying"></textarea></label></p>
            <p><label>Drug Allergy: <input type="text" name="drug_allergy"></label></p>
            <p><label>Doctor: <textarea name="doctor"></textarea></label></p>
            <p><label>Medication: <textarea name="medication"></textarea></label></p>
            <p><label>Diagnosis: <textarea name="diagnosis"></textarea></label></p>
            <p><input type="submit" value="Submit"></p>
        </form>
        <p><a href="/">Back to Home</a></p>
        </body>
        </html>
        '''


@app.route('/view-member/<member_id>')
def view_member(member_id):
    member=Member.query.filter_by(member_id=member_id).first()
    if member:
        return render_template('view-member.html',member=member)
    else:
        flash('Member not found!', 'error')
        return redirect(url_for('home'))
    
@app.route('/update-member/<member_id>', methods=['GET','POST'])
def update_member(member_id):
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
            existing=Medication.query.filter_by(name=medication_name,member_id=member.id).first()
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
def delete_member(member_id):
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
def search_member():
    query = request.args.get('query', '').lower()
    if not query:
        flash("Please enter member name or member id!","error")
        return redirect(url_for('home'))
    
    results=Member.query.filter(db.or_(Member.name.contains(query),Member.member_id.contains(query.upper())
                                       )).all()
    if results:
        return render_template("search-result.html",results=results,query=query)
    else:
        flash("No member found matching your search","info")
        return redirect(url_for('home'))
    
@app.route('/api/member/<member_id>')
def api_get_member(member_id):
    member=Member.query.filter_by(member_id=member_id).first()
    if member:
        return member.to_dict()
    return {'error':'Member not found'},404
@app.route('/upload-file/<member_id>', methods=['POST', 'GET'])
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
                # Generate secure filename
                original_filename = secure_filename(file.filename)
                unique_filename = generate_unique_filename(original_filename)

                # Get file size and store original content type
                file.seek(0, 2)  # Seek to end
                file_size = file.tell()  # Get position (file size)
                file.seek(0)  # Reset to beginning
                original_content_type = file.content_type

                print(f"📁 Processing file: {original_filename}")
                print(f"📏 File size: {file_size} bytes")
                print(f"📄 Original content type: {original_content_type}")

                # Try to upload to R2 first - pass the original file object
                r2_path = upload_to_r2(file, unique_filename, member_id)

                if r2_path:
                    file_path = r2_path
                    storage_type = 'r2'
                    print(f"✅ File stored in R2: {r2_path}")
                else:
                    # Fallback to local storage
                    print("🔄 Falling back to local storage...")
                    file.seek(0)  # Reset file pointer for local save
                    local_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    file.save(local_path)  # Use Flask's save method
                    file_path = local_path
                    storage_type = 'local'
                    print(f"⚠️ File stored locally: {file_path}")

                # Create database record
                medical_file = MedicalFile(
                    filename=original_filename,
                    file_path=file_path,
                    file_size=file_size,
                    file_type=original_content_type,
                    description=description,
                    member_id=member.id
                )
                
                db.session.add(medical_file)
                db.session.commit()

                if storage_type == 'r2':
                    flash("File uploaded successfully to cloud storage!", 'success')
                else:
                    flash("File uploaded successfully (local backup)!", 'warning')
                    
                return redirect(url_for('view_member', member_id=member_id))

            except Exception as e:
                db.session.rollback()
                flash(f"Error uploading file: {str(e)}", "error")
                print(f"❌ Upload error: {e}")
                import traceback
                traceback.print_exc()
        else:
            flash("Invalid file type. Allowed: PDF, Images, Word documents", "error")

    return render_template('upload-file.html', member=member)

@app.route('/download-file/<int:file_id>')
def download_file(file_id):
    from flask import send_file, redirect
    
    medical_file = MedicalFile.query.get_or_404(file_id)

    try:
        # Check if file is stored in R2 (path starts with 'members/')
        if medical_file.file_path.startswith('members/'):
            # File is in R2 - generate download URL
            download_url = download_from_r2(medical_file.file_path)
            if download_url:
                return redirect(download_url)
            else:
                flash("Could not generate download link", "error")
                return redirect(url_for('home'))
        else:
            # File is stored locally
            if os.path.exists(medical_file.file_path):
                return send_file(
                    medical_file.file_path,
                    as_attachment=True,
                    download_name=medical_file.filename
                )
            else:
                flash("File not found on server", "error")
                return redirect(url_for('home'))
        
    except Exception as e:
        flash(f"Error downloading file: {str(e)}", "error")
        return redirect(url_for('home'))

@app.route('/delete-file/<int:file_id>', methods=['POST'])
def delete_file(file_id):
    medical_file = MedicalFile.query.get_or_404(file_id)
    member_id = medical_file.member.member_id

    try:
        # Delete from storage
        if medical_file.file_path.startswith('members/'):
            # File is in R2
            delete_from_r2(medical_file.file_path)
        else:
            # File is stored locally
            if os.path.exists(medical_file.file_path):
                os.remove(medical_file.file_path)

        # Delete from database
        db.session.delete(medical_file)
        db.session.commit()
        flash('File deleted successfully', "success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting file: {str(e)}", "error")
    
    return redirect(url_for('view_member', member_id=member_id))

@app.route('/backup-data')
def backup_data():
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
    
@app.route('/test-db')
def test_database():
    try:
        # Try to connect to database
        from sqlalchemy import text
        result = db.session.execute(text('SELECT version()'))
        version = result.fetchone()[0]
        return f"✅ Database connected! PostgreSQL version: {version}"
    except Exception as e:
        return f"❌ Database connection failed: {str(e)}"

@app.route('/test-r2')
def test_r2():
    """Enhanced R2 testing with detailed diagnostics"""
    
    # Basic environment check
    env_vars = {
        'R2_ACCOUNT_ID': os.getenv('R2_ACCOUNT_ID'),
        'R2_ACCESS_KEY_ID': os.getenv('R2_ACCESS_KEY_ID'),
        'R2_SECRET_ACCESS_KEY': os.getenv('R2_SECRET_ACCESS_KEY'),
        'R2_BUCKET_NAME': os.getenv('R2_BUCKET_NAME')
    }
    
    # Check which variables are missing
    missing_vars = [key for key, value in env_vars.items() if not value]
    
    html_output = "<h1>🧪 R2 Configuration Test</h1>"
    
    # Environment variables check
    html_output += "<h2>📋 Environment Variables</h2><ul>"
    for key, value in env_vars.items():
        if value:
            if key == 'R2_SECRET_ACCESS_KEY':
                display_value = "***Hidden***"
            elif key == 'R2_ACCESS_KEY_ID':
                display_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***Set***"
            else:
                display_value = value
            html_output += f"<li>✅ {key}: {display_value}</li>"
        else:
            html_output += f"<li>❌ {key}: Missing</li>"
    html_output += "</ul>"
    
    if missing_vars:
        html_output += f"""
        <div style="background: #ffebee; padding: 15px; border-left: 4px solid #f44336; margin: 20px 0;">
            <h3>⚠️ Missing Environment Variables</h3>
            <p>The following variables are not set: <strong>{', '.join(missing_vars)}</strong></p>
            <p>Add these in your Railway dashboard under Variables tab.</p>
        </div>
        """
        return html_output + '<p><a href="/">← Back to Home</a></p>'
    
    # Test R2 connection
    html_output += "<h2>🔗 R2 Connection Test</h2>"
    success, message = test_r2_connection()
    
    if success:
        html_output += f"""
        <div style="background: #e8f5e8; padding: 15px; border-left: 4px solid #4caf50; margin: 20px 0;">
            <h3>✅ R2 Test Successful!</h3>
            <p>{message}</p>
        </div>
        <h3>📊 Configuration Details</h3>
        <ul>
            <li><strong>Bucket:</strong> {env_vars['R2_BUCKET_NAME']}</li>
            <li><strong>Account ID:</strong> {env_vars['R2_ACCOUNT_ID']}</li>
            <li><strong>Endpoint:</strong> https://{env_vars['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com</li>
        </ul>
        
        <h3>🚀 Next Steps</h3>
        <ul>
            <li>✅ Your R2 is configured correctly</li>
            <li>✅ Try uploading a file to test the full workflow</li>
            <li>✅ Files will now be stored in Cloudflare R2</li>
        </ul>
        """
    else:
        html_output += f"""
        <div style="background: #ffebee; padding: 15px; border-left: 4px solid #f44336; margin: 20px 0;">
            <h3>❌ R2 Test Failed</h3>
            <p>{message}</p>
        </div>
        
        <h3>🔧 Troubleshooting Steps</h3>
        <ol>
            <li><strong>Check your R2 API Token:</strong>
                <ul>
                    <li>Go to Cloudflare dashboard → R2 → Manage R2 API tokens</li>
                    <li>Create a new token with <strong>R2:Edit</strong> permissions</li>
                    <li>Use the SAME token for both ACCESS_KEY_ID and SECRET_ACCESS_KEY</li>
                </ul>
            </li>
            <li><strong>Verify your bucket name:</strong>
                <ul>
                    <li>Check that '{env_vars['R2_BUCKET_NAME']}' exists in your Cloudflare R2 dashboard</li>
                    <li>Bucket names are case-sensitive</li>
                </ul>
            </li>
            <li><strong>Check token permissions:</strong>
                <ul>
                    <li>Your token needs <strong>Account:Read</strong> and <strong>R2:Edit</strong> permissions</li>
                    <li>Make sure it's not expired</li>
                </ul>
            </li>
        </ol>
        
        <h3>🆘 Still having issues?</h3>
        <p>Common fixes:</p>
        <ul>
            <li><strong>For Railway users:</strong> Make sure you redeploy after adding environment variables</li>
            <li><strong>SSL issues:</strong> This might be a temporary network issue - try again in a few minutes</li>
            <li><strong>Wrong credentials:</strong> Delete and recreate your R2 API token</li>
        </ul>
        """
    
    html_output += """
    <hr style="margin: 30px 0;">
    <p><strong>🔄 <a href="/test-r2">Refresh Test</a> | <a href="/">← Back to Home</a></strong></p>
    """
    
    return html_output

if __name__ == '__main__':
    print("Starting Medical App...")
    create_tables()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
else:
    # This runs when deployed (gunicorn)
    print("App started by gunicorn...")
    with app.app_context():
        create_tables()