from flask import Flask, render_template,request,redirect,url_for,flash,jsonify
from flask_sqlalchemy import SQLAlchemy
import os
import string
import random
import json 
from datetime import datetime,date,timedelta
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
import uuid
import io


app = Flask(__name__)
DATA_FILE='members.json'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///medical.db'  # Local SQLite database
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Reduces memory usage
app.secret_key = "secret"

app.config['MAX_CONTENT_LENGTH']=16*1024*1024 #16mb max file size
app.config['UPLOAD_FOLDER'] ='uploads'
ALLOWED_EXTENSIONS={'pdf','png','jpg','jpeg','gif','doc','docx'}

#create uploads directory
import os 
os.makedirs(app.config['UPLOAD_FOLDER'],
            exist_ok=True)

db=SQLAlchemy(app)

migrate = Migrate(app, db)

class Member(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    member_id=db.Column(db.String(6),unique=True,nullable=False)
    name=db.Column(db.String(100),nullable=False)
    date_of_birth=db.Column(db.Date,nullable=False)
    age=db.Column(db.Integer)
    gender=db.Column(db.String(10),nullable=False)
    underlying=db.Column(db.String(200),nullable=False,default='')
    drug_allergy=db.Column(db.String(200),nullable=False,default='')

    #Timestamps
    created_at=db.Column(db.DateTime,default=datetime.now)
    updated_at=db.Column(db.DateTime,default=datetime.now)

    doctors=db.relationship("Doctor",backref='member',lazy=True,cascade='all,delete-orphan')
    medications=db.relationship('Medication',backref='member',lazy=True,cascade="all,delete-orphan")
    diagnoses=db.relationship("Diagnosis",backref='member',lazy=True,cascade="all,delete-orphan")
    medical_files=db.relationship('MedicalFile',backref='member',lazy=True,cascade='all,delete-orphan')

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
    

def allowed_file(filename):
    return '.' in filename and \
    filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def generate_unique_filename(filename):
    ext=filename.rsplit('.',1)[1].lower()
    unique_id=str(uuid.uuid4())
    return f"{unique_id}.{ext}"

def create_tables():
    with app.app_context():
        db.create_all()
        print("Database tables created successfully!")

def calculate_age_from_date(dob):
    today=date.today()
    return today.year- dob.year-((today.month,today.day)<(dob.month,dob.day))

def generate_id(length=6):
    while True:
        characters=string.ascii_uppercase + string.digits
        new_id=''.join(random.choice(characters)for _ in range(length))
        if not Member.query.filter_by(member_id=new_id).first():
            return new_id
        
def split_lines(text):
    if isinstance(text,list):
        return text
    if not text:
        return []
    
    return [item.strip() for item in text.replace("\n",",").split(",") if item.strip()]


@app.route('/')
def home():
    total_members = Member.query.count()
    recent_members = Member.query.order_by(Member.created_at.desc()).limit(6).all()
    recent_additions = Member.query.filter(
    Member.created_at >= datetime.now() - timedelta(days=30)).count()
    
    return render_template("index.html", 
                         total_members=total_members,
                         recent_members=recent_members,
                         recent_additions=recent_additions)

@app.route('/add-member',methods=['GET'])
def add_member():
   return render_template('add-member.html')

@app.route('/add-member',methods=['POST'])
def add_member_post():
    try: 
        name=request.form.get('name')
        date_of_birth=request.form.get('date_of_birth')
        gender=request.form.get('gender')
        underlying=request.form.get('underlying')
        underlying=split_lines(underlying)
        drug_allergy=request.form.get('drug_allergy')
        
        if not name or not date_of_birth or not gender:
            flash("Name,date of birth and gender are required!,Error")
            return redirect(url_for('add_member'))
        
        dob=datetime.strptime(date_of_birth,"%Y-%m-%d").date()

        existing_member=Member.query.filter_by(name=name.lower().strip(),date_of_birth=dob).first()

        if existing_member:
            flash("Member with the same name and date of birth already exists!","error")
            return redirect(url_for('home'))

        new_member = Member(
            member_id=generate_id(),
            name= name.strip().lower(),
            date_of_birth= dob,
            age=calculate_age_from_date(dob),
            gender=gender, 
            drug_allergy=drug_allergy,
            underlying=underlying
        )
            
        db.session.add(new_member)
        db.session.flush()

        for doctor_name in split_lines(request.form.get('doctor','')):
            if doctor_name:
                doctor=Doctor(name=doctor_name,member_id=new_member.id)
                db.session.add(doctor)

        for med_name in split_lines(request.form.get('medication',"")):
            if med_name:
                medication=Medication(name=med_name,member_id=new_member.id)
                db.session.add(medication)

        for diag_name in split_lines(request.form.get('diagnosis',"")):
            if diag_name:
                diagnosis=Diagnosis(name=diag_name,member_id=new_member.member_id)
                db.session.add(diagnosis)

        db.session.commit()
        flash("Member added succssfully!","success")
        return redirect(url_for('view_member', member_id=new_member.member_id))
    
    except Exception as e:
        db.session.rollback()
        flash(f"An error occured:{str(e)}","error")
        return redirect(url_for('home')) 
    

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

@app.route('/upload-file/<member_id>',methods=['POST','GET'])
def upload_file(member_id):
    member=Member.query.filter_by(member_id=member_id).first()
    if not member:
        flash("Member not found","error")
        return redirect(url_for('home'))
    
    if request.method=='POST':
        if 'file' not in request.files:
            flash('No file selected',"error")
            return redirect(request.url) 

        file=request.files['file']
        description=request.form.get('description',"").strip()

        if file.filename=='':
            flash("No file selected","error")
            return redirect(request.url) 

        if file and allowed_file(file.filename):
            try:
                original_filename=secure_filename(file.filename)
                unique_filename=generate_unique_filename(original_filename)
                file_path=os.path.join(app.config['UPLOAD_FOLDER'],unique_filename) 

                file.save(file_path)
                medical_file=MedicalFile(filename=original_filename,file_path=file_path,
                                         file_size=os.path.getsize(file_path),
                                         file_type=file.content_type,
                                         description=description,
                                         member_id=member.id
                ) 
                db.session.add(medical_file)
                db.session.commit()

                flash("File uploaded successfully",'success')
                return redirect(url_for('view_member',member_id=member_id))

            except Exception as e:
                db.session.rollback()
                flash(f"Error uploadinf file:{str(e)}","error")
        else:
            flash("Invalid file type: Allowed PDF,Images, Word documents","error")

    return render_template('upload-file.html',member=member)

@app.route('/download-file/<int:file_id>')
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
def delete_file(file_id):
    medical_file=MedicalFile.query.get_or_404(file_id)
    member_id=medical_file.member.member_id

    try:
        if os.path.exists(medical_file.file_path):
            os.remove(medical_file.file_path)

            db.session.delete(medical_file)
            db.session.commit()
            flash('File deleted successfully',"success")

    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting file:{str(e)}","error")
    
    return redirect(url_for('view_member',member_id=member_id))

if __name__ == '__main__':
    create_tables()
    # Get port from environment variable (Railway needs this)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)