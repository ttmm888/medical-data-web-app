# auto_migration.py
# Automatic migration without user prompts

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import os
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///medical.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Your models (copy from your main app)
class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.String(6), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    doctors = db.relationship('Doctor', backref='member', lazy=True, cascade='all, delete-orphan')
    medications = db.relationship('Medication', backref='member', lazy=True, cascade='all, delete-orphan')
    diagnoses = db.relationship('Diagnosis', backref='member', lazy=True, cascade='all, delete-orphan')

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
    name = db.Column(db.String(200), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)

def calculate_age_from_date(date_of_birth):
    today = date.today()
    return today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))

def migrate_json_to_database():
    """Migrate JSON data to database"""
    JSON_FILE = 'members.json'
    
    print("🏥 STARTING AUTOMATIC MIGRATION")
    print("=" * 40)
    
    # Check if JSON file exists
    if not os.path.exists(JSON_FILE):
        print("❌ members.json not found!")
        print("Make sure the file is in the same directory as this script.")
        return False
    
    with app.app_context():
        # Create all tables
        db.create_all()
        print("✅ Database tables created")
        
        # Load JSON data
        try:
            with open(JSON_FILE, 'r') as file:
                json_data = json.load(file)
            print(f"✅ Loaded {len(json_data)} members from JSON")
        except Exception as e:
            print(f"❌ Error loading JSON: {e}")
            return False
        
        # Check if we already have data in database
        existing_count = Member.query.count()
        if existing_count > 0:
            print(f"⚠️  Database already has {existing_count} members")
            print("Skipping duplicates based on member_id...")
        
        success_count = 0
        skip_count = 0
        error_count = 0
        
        for member_data in json_data:
            try:
                # Check if member already exists
                existing_member = Member.query.filter_by(member_id=member_data['member_id']).first()
                if existing_member:
                    print(f"⏭️  Skipping {member_data['name']} (already exists)")
                    skip_count += 1
                    continue
                
                # Parse date of birth
                dob = datetime.strptime(member_data['date_of_birth'], "%Y-%m-%d").date()
                
                # Create new member
                member = Member(
                    member_id=member_data['member_id'],
                    name=member_data['name'],
                    date_of_birth=dob,
                    age=member_data.get('age', calculate_age_from_date(dob)),
                    gender=member_data['gender']
                )
                
                # Handle created_at if it exists
                if 'created_at' in member_data:
                    try:
                        member.created_at = datetime.fromisoformat(member_data['created_at'])
                    except:
                        pass  # Use default
                
                db.session.add(member)
                db.session.flush()  # Get the member ID
                
                # Add doctors
                for doctor_name in member_data.get('doctors', []):
                    if doctor_name and doctor_name.strip():
                        doctor = Doctor(name=doctor_name.strip(), member_id=member.id)
                        db.session.add(doctor)
                
                # Add medications
                for med_name in member_data.get('medication', []):
                    if med_name and med_name.strip():
                        medication = Medication(name=med_name.strip(), member_id=member.id)
                        db.session.add(medication)
                
                # Add diagnoses
                for diag_name in member_data.get('diagnosis', []):
                    if diag_name and diag_name.strip():
                        diagnosis = Diagnosis(name=diag_name.strip(), member_id=member.id)
                        db.session.add(diagnosis)
                
         
                # Commit this member
                db.session.commit()
                success_count += 1
                print(f"✅ Migrated: {member_data['name']}")
                
            except Exception as e:
                db.session.rollback()
                error_count += 1
                print(f"❌ Error migrating {member_data.get('name', 'Unknown')}: {e}")
                continue
        
        # Final summary
        print("\n" + "=" * 40)
        print("MIGRATION SUMMARY:")
        print(f"✅ Successfully migrated: {success_count}")
        print(f"⏭️  Skipped (already exists): {skip_count}")
        print(f"❌ Errors: {error_count}")
        print(f"📊 Total in database: {Member.query.count()}")
        
        # Show some sample data
        if success_count > 0:
            print("\n--- SAMPLE MIGRATED DATA ---")
            sample = Member.query.first()
            print(f"Name: {sample.name}")
            print(f"Doctors: {len(sample.doctors)}")
            print(f"Medications: {len(sample.medications)}")
            print(f"Diagnoses: {len(sample.diagnoses)}")
        
        return True

if __name__ == '__main__':
    success = migrate_json_to_database()
    
    if success:
        print("\n🎉 Migration completed!")
        print("You can now run your Flask app with SQLAlchemy.")
    else:
        print("\n❌ Migration failed!")
        print("Check the error messages above.")
        