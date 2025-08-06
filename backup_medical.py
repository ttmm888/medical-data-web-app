from flask import Flask, render_template,request,redirect,url_for,flash,jsonify
from flask_sqlalchemy import SQLAlchemy
import os
import string
import random
import json 
from datetime import datetime,date
from flask_migrate import Migrate

app = Flask(__name__)
DATA_FILE='members.json'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///medical.db'  # Local SQLite database
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Reduces memory usage
app.secret_key = "secret"

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

    #Timestamps
    created_at=db.Column(db.DateTime,default=datetime.now)
    updated_at=db.Column(db.DateTime,default=datetime.now)

    doctors=db.relationship("Doctor",backref='member',lazy=True,cascade='all,delete-orphan')
    medications=db.relationship('Medication',backref='member',lazy=True,cascade="all,delete-orphan")
    diagnoses=db.relationship("Diagnosis",backref='member',lazy=True,cascade="all,delete-orphan")


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
    return render_template("index.html")

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


if __name__ == '__main__':
    create_tables()

    app.run(debug=True)