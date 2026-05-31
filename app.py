import csv
import io
import os
from datetime import datetime
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
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import IntegrityError
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "login"
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)

ALLOWED_IMAGE_FORMATS = {
    "JPEG": {".jpg", ".jpeg"},
    "PNG": {".png"},
}
ALLOWED_IMAGE_MIMETYPES = {"image/jpeg", "image/png"}
CSV_REQUIRED_FIELDS = {
    "first_name",
    "last_name",
    "room_name",
    "course_date",
    "start_time",
    "end_time",
}
Image.MAX_IMAGE_PIXELS = 10_000_000


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
        WTF_CSRF_TIME_LIMIT=_env_int("WTF_CSRF_TIME_LIMIT", 3600),
        RATELIMIT_STORAGE_URI=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
        LOGIN_RATE_LIMIT=os.environ.get("LOGIN_RATE_LIMIT", "5 per minute"),
        UPLOAD_RATE_LIMIT=os.environ.get("UPLOAD_RATE_LIMIT", "20 per hour"),
    )

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    register_routes(app)
    register_error_handlers(app)
    register_security_headers(app)

    with app.app_context():
        initialize_database()

    return app


def initialize_database():
    db.create_all()
    bootstrap_admin_from_env()


def bootstrap_admin_from_env():
    if Admin.query.count() > 0:
        return

    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    if not username and not password:
        current_app.logger.warning(
            "No admin account exists. Set ADMIN_USERNAME and ADMIN_PASSWORD "
            "once to bootstrap the first administrator.",
        )
        return
    if not username or not password:
        raise RuntimeError(
            "ADMIN_USERNAME and ADMIN_PASSWORD must be provided together",
        )
    if len(password) < 12:
        raise RuntimeError("ADMIN_PASSWORD must be at least 12 characters long")

    hashed_password = generate_password_hash(password, method="pbkdf2:sha256")
    db.session.add(Admin(username=username, password=hashed_password))
    db.session.commit()
    current_app.logger.info("Bootstrapped initial admin user from environment")


def _clean_required_text(form_data, field_name: str, max_length: int = 100) -> str:
    value = (form_data.get(field_name) or "").strip()
    if not value:
        raise ValueError(f"{field_name} is required")
    if len(value) > max_length:
        raise ValueError(f"{field_name} must be {max_length} characters or fewer")
    return value


def _validate_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("course_date must use YYYY-MM-DD format") from exc
    return value


def _validate_time(value: str, field_name: str) -> str:
    try:
        datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise ValueError(f"{field_name} must use HH:MM format") from exc
    return value


def _course_data_from_mapping(mapping) -> dict:
    first_name = _clean_required_text(mapping, "first_name")
    last_name = _clean_required_text(mapping, "last_name")
    room_name = _clean_required_text(mapping, "nom_salle", max_length=100)
    course_date = _validate_date(_clean_required_text(mapping, "date_cours", 10))
    start_time = _validate_time(
        _clean_required_text(mapping, "heure_debut", 5),
        "heure_debut",
    )
    end_time = _validate_time(
        _clean_required_text(mapping, "heure_fin", 5),
        "heure_fin",
    )
    if start_time >= end_time:
        raise ValueError("heure_debut must be earlier than heure_fin")

    return {
        "first_name": first_name,
        "last_name": last_name,
        "room_name": room_name,
        "course_date": course_date,
        "start_time": start_time,
        "end_time": end_time,
    }


def _course_data_from_csv_row(row: dict, line_number: int) -> dict:
    normalized_row = {
        "first_name": row.get("first_name", ""),
        "last_name": row.get("last_name", ""),
        "nom_salle": row.get("room_name", ""),
        "date_cours": row.get("course_date", ""),
        "heure_debut": row.get("start_time", ""),
        "heure_fin": row.get("end_time", ""),
    }
    try:
        return _course_data_from_mapping(normalized_row)
    except ValueError as exc:
        raise ValueError(f"CSV line {line_number}: {exc}") from exc


def _safe_upload_path(filename: str) -> Path:
    safe_name = secure_filename(filename)
    if not safe_name:
        raise ValueError("Uploaded filename is invalid")

    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    destination = (upload_root / safe_name).resolve()
    if destination.parent != upload_root:
        raise ValueError("Uploaded filename escapes the upload directory")
    return destination


def _validate_image_upload(file_storage) -> str:
    if not file_storage or not file_storage.filename:
        raise ValueError("A face image is required")

    extension = Path(file_storage.filename).suffix.lower()
    if extension not in {ext for exts in ALLOWED_IMAGE_FORMATS.values() for ext in exts}:
        raise ValueError("Face image must be a JPEG or PNG file")

    if file_storage.mimetype and file_storage.mimetype not in ALLOWED_IMAGE_MIMETYPES:
        raise ValueError("Face image MIME type must be image/jpeg or image/png")

    file_storage.stream.seek(0)
    try:
        with Image.open(file_storage.stream) as image:
            image.verify()
            if extension not in ALLOWED_IMAGE_FORMATS.get(image.format, set()):
                raise ValueError("Face image extension does not match its content")
    except UnidentifiedImageError as exc:
        raise ValueError("Face image content is not a valid image") from exc
    finally:
        file_storage.stream.seek(0)

    return extension


def _save_course_image(file_storage, first_name: str, last_name: str) -> str:
    extension = _validate_image_upload(file_storage)
    image_name = f"{first_name}_{last_name}{extension}"
    destination = _safe_upload_path(image_name)
    file_storage.save(destination)
    return str(destination)


def _parse_course_csv(file_storage):
    if not file_storage or not file_storage.filename:
        raise ValueError("CSV file is required")
    if Path(file_storage.filename).suffix.lower() != ".csv":
        raise ValueError("Upload a valid CSV file")

    file_storage.stream.seek(0)
    text_stream = io.TextIOWrapper(file_storage.stream, encoding="utf-8-sig", newline="")
    reader = csv.DictReader(text_stream)
    missing_fields = CSV_REQUIRED_FIELDS - set(reader.fieldnames or [])
    if missing_fields:
        missing = ", ".join(sorted(missing_fields))
        raise ValueError(f"CSV is missing required fields: {missing}")

    rows = []
    for line_number, row in enumerate(reader, start=2):
        rows.append(_course_data_from_csv_row(row, line_number))
    if not rows:
        raise ValueError("CSV contains no course rows")
    return rows


def register_routes(app: Flask) -> None:
    @app.route("/", methods=["GET", "POST"])
    @limiter.limit(app.config["LOGIN_RATE_LIMIT"])
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
    @limiter.limit(app.config["UPLOAD_RATE_LIMIT"])
    @login_required
    def add_teacher_course():
        if request.method == "POST":
            file_path = None
            try:
                course_data = _course_data_from_mapping(request.form)
                file_path = _save_course_image(
                    request.files.get("photo"),
                    course_data["first_name"],
                    course_data["last_name"],
                )
                new_course = Course(face_id=file_path, **course_data)
                db.session.add(new_course)
                db.session.commit()
                flash("Course added successfully!", "success")
                return redirect(url_for("add_teacher_course"))
            except (IntegrityError, ValueError) as exc:
                db.session.rollback()
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                current_app.logger.warning("Course creation failed: %s", exc)
                flash(str(exc), "danger")

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
    @limiter.limit(app.config["UPLOAD_RATE_LIMIT"])
    @login_required
    def upload_csv():
        if request.method == "POST":
            try:
                imported_count = 0
                for course_data in _parse_course_csv(request.files.get("file")):
                    photo_filename = secure_filename(
                        f"{course_data['first_name']}_{course_data['last_name']}.jpg",
                    )
                    photo_path = _safe_upload_path(photo_filename)
                    if photo_path.exists():
                        db.session.add(Course(face_id=str(photo_path), **course_data))
                        imported_count += 1
                if imported_count == 0:
                    raise ValueError("CSV rows did not match any existing face images")
                db.session.commit()
                flash(f"CSV imported successfully: {imported_count} course(s).", "success")
                return redirect(url_for("view_courses"))
            except (IntegrityError, ValueError) as exc:
                db.session.rollback()
                current_app.logger.warning("CSV import failed: %s", exc)
                flash(str(exc), "danger")

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
            new_file_path = None
            old_face_path = Path(course.face_id).resolve() if course.face_id else None
            try:
                course_data = _course_data_from_mapping(request.form)
                for field_name, value in course_data.items():
                    setattr(course, field_name, value)

                photo = request.files.get("photo")
                if photo and photo.filename:
                    new_file_path = _save_course_image(
                        photo,
                        course.first_name,
                        course.last_name,
                    )
                    if (
                        old_face_path
                        and old_face_path != Path(new_file_path).resolve()
                        and old_face_path.exists()
                    ):
                        os.remove(course.face_id)
                    course.face_id = new_file_path

                db.session.commit()
                flash("Course updated successfully.", "success")
                return redirect(url_for("view_courses"))
            except (IntegrityError, ValueError) as exc:
                db.session.rollback()
                if (
                    new_file_path
                    and Path(new_file_path).resolve() != old_face_path
                    and os.path.exists(new_file_path)
                ):
                    os.remove(new_file_path)
                current_app.logger.warning("Course update failed: %s", exc)
                flash(str(exc), "danger")

        return render_template("edit_course.html", course=course)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        current_app.logger.warning("CSRF validation failed: %s", error.description)
        flash("Security token expired. Please try again.", "danger")
        return redirect(request.referrer or url_for("login")), 400


def register_security_headers(app: Flask) -> None:
    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=()",
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "img-src 'self' data:; "
            "script-src 'self'; "
            "style-src 'self'",
        )
        if current_app.config["SESSION_COOKIE_SECURE"]:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


app = create_app()


if __name__ == "__main__":
    app.run(debug=_env_bool("FLASK_DEBUG", False))
