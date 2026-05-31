import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import csv
from dotenv import load_dotenv

load_dotenv()  

# Initialize Flask App
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")  # Replace with a secure random string
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///teachers.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads/'  # Folder to save uploads

# Initialisation de la base de données
db = SQLAlchemy(app)

# Initialize Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'  # Redirect unauthorized users to login page

# Models
class Admin(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class AccessLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    timestamp = db.Column(db.String(100))
    status = db.Column(db.String(50))

# Définition du modèle Course (Cours)
class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)  # Identifiant unique pour chaque cours
    first_name = db.Column(db.String(100), nullable=False)  # Prénom de l'enseignant
    last_name = db.Column(db.String(100), nullable=False)  # Nom de l'enseignant
    face_id = db.Column(db.String(200), unique=True, nullable=False)  # Chemin vers la photo enregistrée
    room_name = db.Column(db.String(100), nullable=False)  # Nom de la salle de cours
    course_date = db.Column(db.String(100), nullable=False)  # Date du cours
    start_time = db.Column(db.String(100), nullable=False)  # Heure de début du cours
    end_time = db.Column(db.String(100), nullable=False)  # Heure de fin du cours

@login_manager.user_loader
def load_user(admin_id):
    return Admin.query.get(int(admin_id))

# Routes
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password, password):
            login_user(admin)
            flash('Login successful!', 'success')
            return redirect(url_for('view_courses'))
        flash('Invalid credentials. Try again.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

# Route pour ajouter un cours
@app.route('/add_teacher_course', methods=['GET', 'POST'])
@login_required
def add_teacher_course():
    if request.method == 'POST':
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        photo = request.files['photo']
        room_name = request.form['nom_salle']
        course_date = request.form['date_cours']
        start_time = request.form['heure_debut']
        end_time = request.form['heure_fin']

        filename = secure_filename(f"{first_name}_{last_name}.jpg")
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        photo.save(file_path)

        new_course = Course(
            first_name=first_name,
            last_name=last_name,
            face_id=file_path,
            room_name=room_name,
            course_date=course_date,
            start_time=start_time,
            end_time=end_time
        )
        db.session.add(new_course)
        db.session.commit()
        flash('Course added successfully!', 'success')
        return redirect(url_for('add_teacher_course'))

    return render_template('add_teacher_course.html')

# Access Logs Route
@app.route('/logs', methods=['GET'])
@login_required
def get_logs():
    page = request.args.get('page', 1, type=int)
    per_page = 10  # Adjust as needed
    logs = AccessLog.query.order_by(AccessLog.timestamp.desc()).paginate(page=page, per_page=per_page)
    return render_template('access_logs.html', logs=logs)


# Route pour afficher tous les cours enregistrés
@app.route('/courses', methods=['GET'])
@login_required
def view_courses():
    # Récupère tous les cours de la base de données
    courses = Course.query.all()
    # Rendu de la page HTML 'view_courses.html' avec la liste des cours
    return render_template('view_courses.html', courses=courses)

@app.route('/upload_csv', methods=['GET', 'POST'])
@login_required
def upload_csv():
    if request.method == 'POST':
        file = request.files.get('file')
        if file and file.filename.endswith('.csv'):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            with open(filepath, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    photo_filename = secure_filename(f"{row['first_name']}_{row['last_name']}.jpg")
                    photo_path = os.path.join(app.config['UPLOAD_FOLDER'], photo_filename)
                    # Ensure the photo exists before saving
                    if os.path.exists(photo_path):
                        new_course = Course(
                            first_name=row['first_name'],
                            last_name=row['last_name'],
                            room_name=row['room_name'],
                            course_date=row['course_date'],
                            start_time=row['start_time'],
                            end_time=row['end_time'],
                            face_id=photo_path
                        )
                        db.session.add(new_course)
                db.session.commit()
            return redirect(url_for('view_courses'))
        return "Invalid File Format. Upload a valid CSV.", 400

    return render_template('excel.html')

# Route pour supprimer un cours
@app.route('/delete_course/<int:course_id>', methods=['POST'])
@login_required
def delete_course(course_id):
    course = Course.query.get(course_id)
    if course:
        db.session.delete(course)
        db.session.commit()
        flash('Course deleted successfully!', 'success')
    return redirect(url_for('view_courses'))

# Route pour modifier un cours
@app.route('/edit_course/<int:course_id>', methods=['GET', 'POST'])
@login_required
def edit_course(course_id):
    course = Course.query.get(course_id)  # Recherche du cours par son ID
    if request.method == 'POST':
        # Mise à jour des informations du cours
        course.first_name = request.form['first_name']
        course.last_name = request.form['last_name']
        course.room_name = request.form['nom_salle']
        course.course_date = request.form['date_cours']
        course.start_time = request.form['heure_debut']
        course.end_time = request.form['heure_fin']

        # Mise à jour de la photo si une nouvelle est téléchargée
        if 'photo' in request.files:
            photo = request.files['photo']
            if photo and photo.filename != '':
                filename = f"{course.first_name}_{course.last_name}.jpg"
                filename = secure_filename(filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

                # Suppression de l'ancienne photo si elle existe
                if course.face_id and os.path.exists(course.face_id):
                    os.remove(course.face_id)

                # Sauvegarde de la nouvelle photo
                photo.save(file_path)
                course.face_id = file_path  # Mise à jour de face_id avec le nouveau chemin

        db.session.commit()  # Validation des modifications
        return redirect(url_for('view_courses'))

    # Rendu de la page HTML 'edit_course.html' avec les informations du cours
    return render_template('edit_course.html', course=course)

# Initialisation de la base de données lors du premier lancement
with app.app_context():
    db.create_all()
    if not Admin.query.filter_by(username='admin').first():
        hashed_password = generate_password_hash('admin_password', method='pbkdf2:sha256')
        db.session.add(Admin(username='admin', password=hashed_password))
        db.session.commit()

if __name__ == '__main__':
    # Création du dossier de téléchargement s'il n'existe pas
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Démarrage de l'application Flask en mode debug
    app.run(debug=True)