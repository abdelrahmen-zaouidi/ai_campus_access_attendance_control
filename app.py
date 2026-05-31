import csv
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, current_app, flash, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "login"


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} environment variable is required")
    return value


def _resolve_runtime_path(path_value: str, app_instance_path: str) -> str:
    path = Path(path_value)
    if not path.is_absolute():
        path = Path(app_instance_path).parent / path
    return str(path.resolve())


class Admin(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)


class AccessLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200))
    timestamp = db.Column(db.String(100))
    status = db.Column(db.String(50))


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    face_id = db.Column(db.String(200), unique=True, nullable=False)
    room_name = db.Column(db.String(100), nullable=False)
    course_date = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.String(100), nullable=False)
    end_time = db.Column(db.String(100), nullable=False)


@login_manager.user_loader
def load_user(admin_id):
    return db.session.get(Admin, int(admin_id))


def create_app():
    load_dotenv()

    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    upload_folder = _resolve_runtime_path(
        os.environ.get("UPLOAD_FOLDER", "uploads"),
        app.instance_path,
    )

    # Centralized config keeps deployment state out of source control and makes
    # app imports safe for tests, workers, and future CLI commands.
    app.config.from_mapping(
        SECRET_KEY=_required_env("SECRET_KEY"),
        SQLALCHEMY_DATABASE_URI=_required_env("DATABASE_URL"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=upload_folder,
        MAX_CONTENT_LENGTH=_env_int("MAX_CONTENT_LENGTH_MB", 8) * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=_env_bool("SESSION_COOKIE_SECURE", True),
        SESSION_COOKIE_SAMESITE=os.environ.get("SESSION_COOKIE_SAMESITE", "Lax"),
    )

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    register_routes(app)

    with app.app_context():
        initialize_database()

    return app


def initialize_database():
    db.create_all()
    if not Admin.query.filter_by(username="admin").first():
        hashed_password = generate_password_hash(
            "admin_password",
            method="pbkdf2:sha256",
        )
        db.session.add(Admin(username="admin", password=hashed_password))
        db.session.commit()


def register_routes(app: Flask) -> None:
    @app.route("/", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("view_courses"))

        if request.method == "POST":
            username = request.form["username"]
            password = request.form["password"]
            admin = Admin.query.filter_by(username=username).first()
            if admin and check_password_hash(admin.password, password):
                login_user(admin)
                flash("Login successful!", "success")
                return redirect(url_for("view_courses"))
            flash("Invalid credentials. Try again.", "danger")
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash("Logged out successfully.", "info")
        return redirect(url_for("login"))

    @app.route("/add_teacher_course", methods=["GET", "POST"])
    @login_required
    def add_teacher_course():
        if request.method == "POST":
            first_name = request.form["first_name"]
            last_name = request.form["last_name"]
            photo = request.files["photo"]
            room_name = request.form["nom_salle"]
            course_date = request.form["date_cours"]
            start_time = request.form["heure_debut"]
            end_time = request.form["heure_fin"]

            filename = secure_filename(f"{first_name}_{last_name}.jpg")
            file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
            photo.save(file_path)

            new_course = Course(
                first_name=first_name,
                last_name=last_name,
                face_id=file_path,
                room_name=room_name,
                course_date=course_date,
                start_time=start_time,
                end_time=end_time,
            )
            db.session.add(new_course)
            db.session.commit()
            flash("Course added successfully!", "success")
            return redirect(url_for("add_teacher_course"))

        return render_template("add_teacher_course.html")

    @app.route("/logs", methods=["GET"])
    @login_required
    def get_logs():
        page = request.args.get("page", 1, type=int)
        logs = AccessLog.query.order_by(AccessLog.timestamp.desc()).paginate(
            page=page,
            per_page=10,
        )
        return render_template("access_logs.html", logs=logs)

    @app.route("/courses", methods=["GET"])
    @login_required
    def view_courses():
        courses = Course.query.all()
        return render_template("view_courses.html", courses=courses)

    @app.route("/upload_csv", methods=["GET", "POST"])
    @login_required
    def upload_csv():
        if request.method == "POST":
            file = request.files.get("file")
            if file and file.filename.endswith(".csv"):
                filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], file.filename)
                file.save(filepath)
                with open(filepath, "r") as csv_file:
                    reader = csv.DictReader(csv_file)
                    for row in reader:
                        photo_filename = secure_filename(
                            f"{row['first_name']}_{row['last_name']}.jpg",
                        )
                        photo_path = os.path.join(
                            current_app.config["UPLOAD_FOLDER"],
                            photo_filename,
                        )
                        if os.path.exists(photo_path):
                            new_course = Course(
                                first_name=row["first_name"],
                                last_name=row["last_name"],
                                room_name=row["room_name"],
                                course_date=row["course_date"],
                                start_time=row["start_time"],
                                end_time=row["end_time"],
                                face_id=photo_path,
                            )
                            db.session.add(new_course)
                    db.session.commit()
                return redirect(url_for("view_courses"))
            return "Invalid File Format. Upload a valid CSV.", 400

        return render_template("excel.html")

    @app.route("/delete_course/<int:course_id>", methods=["POST"])
    @login_required
    def delete_course(course_id):
        course = db.session.get(Course, course_id)
        if course:
            db.session.delete(course)
            db.session.commit()
            flash("Course deleted successfully!", "success")
        return redirect(url_for("view_courses"))

    @app.route("/edit_course/<int:course_id>", methods=["GET", "POST"])
    @login_required
    def edit_course(course_id):
        course = db.session.get(Course, course_id)
        if course is None:
            flash("Course not found.", "danger")
            return redirect(url_for("view_courses"))

        if request.method == "POST":
            course.first_name = request.form["first_name"]
            course.last_name = request.form["last_name"]
            course.room_name = request.form["nom_salle"]
            course.course_date = request.form["date_cours"]
            course.start_time = request.form["heure_debut"]
            course.end_time = request.form["heure_fin"]

            if "photo" in request.files:
                photo = request.files["photo"]
                if photo and photo.filename != "":
                    filename = secure_filename(f"{course.first_name}_{course.last_name}.jpg")
                    file_path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)

                    if course.face_id and os.path.exists(course.face_id):
                        os.remove(course.face_id)

                    photo.save(file_path)
                    course.face_id = file_path

            db.session.commit()
            return redirect(url_for("view_courses"))

        return render_template("edit_course.html", course=course)


app = create_app()


if __name__ == "__main__":
    app.run(debug=_env_bool("FLASK_DEBUG", False))
