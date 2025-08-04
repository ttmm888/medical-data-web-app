

import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, date, timedelta
from werkzeug.utils import secure_filename
import uuid
import string
import random

app = Flask(__name__)

# Database Configuration - Updated for Railway
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///medical.db')

# Handle Railway's PostgreSQL URL format if provided
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

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

# Your existing models (keep these as they are)
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
        return {
            "id": self.id,
            "member_id": self.member_id,
            "name": self.name,
            "date_of_birth": self.date_of_birth.strftime('%Y-%m-%d'),
            'age': self.age,
            "gender": self.gender,
            'drug_allergy': self.drug_allergy,
            'underlying': self.underlying,
            "doctors": [doctor.name for doctor in self.doctors],
            'medications': [medication.name for medication in self.medications],
            'diagnoses': [diag.name for diag in self.diagnoses],
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }

    def get_doctors_list(self):
        return [doctor.name for doctor in self.doctors]
    
    def get_medications_list(self):
        return [med.name for med in self.medications]

class Doctor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)

class Medication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)

class Diagnosis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)

class MedicalFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    file_type = db.Column(db.String(50))
    description = db.Column(db.String(500))
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'file_size': self.file_size,
            'file_type': self.file_type,
            'description': self.description,
            'uploaded_at': self.uploaded_at.isoformat()
        }

# Improved database initialization
def create_tables():
    """Create database tables with proper error handling"""
    try:
        with app.app_context():
            # Check if tables already exist
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            if not existing_tables:
                print("No tables found. Creating new tables...")
                db.create_all()
                print("Database tables created successfully!")
            else:
                print(f"Tables already exist: {existing_tables}")
                # Ensure all required tables exist
                required_tables = ['member', 'doctor', 'medication', 'diagnosis', 'medical_file']
                missing_tables = [table for table in required_tables if table not in existing_tables]
                
                if missing_tables:
                    print(f"Creating missing tables: {missing_tables}")
                    db.create_all()
                    print("Missing tables created successfully!")
            
            # Verify tables were created
            final_tables = inspector.get_table_names()
            print(f"Final database tables: {final_tables}")
            
    except Exception as e:
        print(f"Database creation error: {e}")
        print("Attempting to create tables anyway...")
        try:
            db.create_all()
            print("Tables created on second attempt!")
        except Exception as e2:
            print(f"Second attempt failed: {e2}")
            raise e2

# Database initialization route for manual setup
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

# Keep all your existing utility functions and routes here
# (generate_id, calculate_age_from_date, split_lines, etc.)

# Application startup
if __name__ == '__main__':
    print("Starting Medical App...")
    create_tables()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    # This runs when deployed (gunicorn)
    print("App started by gunicorn...")
    with app.app_context():
        create_tables()