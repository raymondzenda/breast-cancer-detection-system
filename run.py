import datetime, sys, os
from datetime import date
from dateutil.relativedelta import *
from werkzeug.utils import secure_filename
from flask import (Flask, render_template, url_for,
                   redirect, request, session, flash, g)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, login_user, logout_user,
                         current_user, login_required)
from flask_bcrypt import Bcrypt

from keras.preprocessing import image
from keras.preprocessing.image import ImageDataGenerator
from keras.models import load_model
import numpy as np


app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config.update({
	'DEBUG':True,
	'SECRET_KEY':'my funny secret key here',
	'SQLALCHEMY_DATABASE_URI': 'sqlite:///database.db',
	'SQLALCHEMY_TRACK_MODIFICATIONS': True,
	'TEMP_DIR': os.path.join(BASE_DIR, 'static/temp')
	})

# instantiate database object
db = SQLAlchemy(app)
login_manager = LoginManager(app)
bcrypt = Bcrypt(app)

login_manager.login_view = '/'

# You can change this to any folder on your system
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}

############################# MODELS ###################################

class User(db.Model):
    __tablename__ = "users"
    id = db.Column('user_id',db.Integer , primary_key=True)
    age = db.Column('age',db.Integer)
    name = db.Column('name', db.String(20), index=True)
    password = db.Column('password' , db.String(10))
    dob = db.Column('dob' , db.String(10))
    email = db.Column('email',db.String(50),unique=True , index=True)
    role = db.Column('role',db.String(50), default='patient')
    status = db.Column('status',db.String(50), default='')
    prognosis = db.Column('prognosis',db.String(50), default='')
    date_joined = db.Column('date_joined' , db.DateTime)


    def __init__(self , name ,password , email, age, dob):
        self.name = name
        self.password = password
        self.email = email
        self.age = age
        self.dob = dob
        self.date_joined = datetime.datetime.utcnow()


    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return self.id

    def __repr__(self):
        return f'User {self.name}'


############################ UTILITY FUNCTIONS #########################

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))


def calculate_age(dob: str):
	"""Calculate the age given the date of birth dd-mm-yyyy"""
	today = date.today()
	year, month, day = map(int, dob.split('-'))
	age = relativedelta(today, date(year, month, day))
	return age.years


train_datagen = ImageDataGenerator(rescale = 1./255,
                                   shear_range = 0.2,
                                   zoom_range = 0.2,
                                   horizontal_flip = True)

test_datagen = ImageDataGenerator(rescale = 1./255)

training_set = train_datagen.flow_from_directory('dataset/training_set',
                                                 target_size = (64, 64),
                                                 batch_size = 32,
                                                 class_mode = 'binary')

test_set = test_datagen.flow_from_directory('dataset/test_set',
                                            target_size = (64, 64),
                                            batch_size = 32,
                                            class_mode = 'binary')

def process_image_and_predict(image_path):
    classifier = load_model('Breast_cancer_predict_model.h5')
    input_image = image.load_img(image_path, target_size = (64, 64))
    input_image = image.img_to_array(input_image)
    input_image = np.expand_dims(input_image, axis = 0)
    result = classifier.predict(input_image)
    training_set.class_indices
    if result[0][0] == 1:
        prediction = 'malignant'
    else:
        prediction = 'benign'
    return prediction

############################# ROUTES ###################################

@app.before_request
def before_request():
    g.user = current_user


@app.route('/', methods=['GET', 'POST'])
def index():
	if request.method == 'GET':
	    return render_template('index.html')
	# get the variable sent through post request
	email = request.form['email']
	pwd = request.form['password']
	patient = User.query.filter_by(email=email).first()

	if patient and bcrypt.check_password_hash(patient.password, pwd):
		session['logged_in'] = True
		login_user(patient)
		return redirect(url_for('dashboard'))
	flash("Wrong login credentials")
	return render_template('index.html')


@app.route('/create_account', methods=['POST'])
def create_account():
	# Create the new patient and save to database
	new_patient = User(name=request.form['name'],
		               email=request.form['email'],
		               dob=request.form['dob'],
		               age=calculate_age(request.form['dob']),
		               password=bcrypt.generate_password_hash(request.form['password'])
		               )
	db.session.add(new_patient)
	db.session.commit()
	flash('Account created successfully')
	return redirect(url_for('index'))


@app.route('/dashboard')
@login_required
def dashboard():
	patients = db.session.query(User).filter_by(role='patient').all()
	info = {
	        'total_patients': db.session.query(User).filter_by(role='patient').count(),
	        'total_benign': db.session.query(User).filter_by(role='patient', status='benign').count(),
	        'total_malignant': db.session.query(User).filter_by(role='patient', status='malignant').count(),
	        'malignant_under_30': db.session.query(User).filter_by(role='patient', status='malignant').filter(User.age<30).count(),
	        'benign_under_30': db.session.query(User).filter_by(role='patient', status='benign').filter(User.age<30).count(),
	        'malignant_over_30': db.session.query(User).filter_by(role='patient', status='malignant').filter(User.age>30).count(),
	        'benign_over_30': db.session.query(User).filter_by(role='patient', status='benign').filter(User.age>30).count(),
	}
	return render_template('dashboard.html', info=info, patients=patients)


@app.route('/predict', methods=['POST'])
@login_required
def predict():
	file = request.files['file']
	if allowed_file(file.filename):
		os.makedirs(app.config['TEMP_DIR'], exist_ok=True)
		file.save(os.path.join(app.config['TEMP_DIR'],secure_filename(file.filename)))
		results = process_image_and_predict(os.path.join(app.config['TEMP_DIR'],secure_filename(file.filename)))
		patient = db.session.query(User).filter_by(id=current_user.id).first()
		patient.status = results
		db.session.commit()
		flash('Image sent successfully. The doctor will notify you of your results.')
		return redirect(url_for('dashboard'))
	flash('Invalid file! Please sent images only')
	return redirect(url_for('dashboard'))


@app.route('/prognosis/<uid>', methods=['POST'])
def prognosis(uid):
	prognosis = request.form['prognosis']
	patient = db.session.query(User).filter_by(id=uid).first()
	patient.prognosis = prognosis
	db.session.commit()
	flash('Recommendation posted successfully')
	return redirect(url_for('dashboard'))


@app.route('/logout')
@login_required
def logout():
	logout_user()
	return redirect(url_for('index'))



if __name__ == '__main__':
	if len(sys.argv) > 1:
		if sys.argv[1] == 'createdb':
			print('Creating the database')
			db.create_all()
			try:
				admin = User(name='doctor',
					         email='doc@doc.com',
					         password=bcrypt.generate_password_hash('doctor'),
					         dob='12-12-1987',
					         age=30,)
				admin.role = 'doctor'
				db.session.add(admin)
				db.session.commit()
			except Exception as e:
				print(e)
	app.run()
