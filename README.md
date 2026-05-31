# AI Campus Access Attendance Control

Production-oriented campus access and attendance control system using a Flask
admin console, SQLite-backed schedules/logs, a camera-based face recognition
worker, and Arduino serial control.

## Architecture

```text
Admin browser
  -> Flask web app
  -> SQL database: admin, course, access_log
  -> uploads/: validated face images

Recognition workstation
  -> compare.py worker
  -> camera frames + uploads/ face images
  -> SQL schedule lookup
  -> serial command to Arduino controller
```

The web app manages identity enrollment, course schedules, and access logs. The
worker reads the same database and upload directory, performs recognition on the
edge workstation, and fails closed when the serial controller cannot be reached.

## Runtime Requirements

- Python 3.11+
- Web app dependencies: `requirements.txt`
- Recognition worker dependencies: `requirements-worker.txt`
- Development tools: `requirements-dev.txt`
- SQLite for local deployments; use `DATABASE_URL` for production database
  configuration.

## Configuration

Copy `.env.example` to your deployment environment and provide real values.
Do not commit `.env`, databases, uploaded face images, logs, or CSV exports.

Required web settings:

```text
SECRET_KEY
DATABASE_URL
```

First-admin bootstrap:

```text
ADMIN_USERNAME
ADMIN_PASSWORD
```

Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` only when intentionally creating the
first administrator. After the first admin exists, remove those values from the
runtime environment and manage credentials operationally.

Required worker settings:

```text
ARDUINO_SERIAL_PORT
DATABASE_URL or RECOGNITION_DATABASE_URL
```

Optional worker settings:

```text
RECOGNITION_UPLOAD_FOLDER
ARDUINO_BAUDRATE
CAMERA_INDEX
ACCESS_LOG_FILE
```

`ACCESS_LOG_FILE` is intentionally blank by default. Access events are stored in
the database; writing a plaintext PII-bearing log file should be an explicit
operator decision.

## Local Web App

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
$env:SECRET_KEY = "replace-with-a-long-random-secret"
$env:DATABASE_URL = "sqlite:///instance/teachers.db"
$env:ADMIN_USERNAME = "admin"
$env:ADMIN_PASSWORD = "replace-with-a-strong-one-time-password"
flask --app app run
```

Open `http://127.0.0.1:5000`, sign in, confirm the admin account exists, then
remove the one-time admin bootstrap environment variables.

## Recognition Worker

```powershell
python -m pip install -r requirements-worker.txt
$env:SECRET_KEY = "same-web-secret-or-worker-safe-placeholder"
$env:DATABASE_URL = "sqlite:///instance/teachers.db"
$env:ARDUINO_SERIAL_PORT = "COM9"
python compare.py
```

The worker loads face images from `UPLOAD_FOLDER` or
`RECOGNITION_UPLOAD_FOLDER`. Images must be enrolled through the web app so they
pass server-side validation and use the expected `first_last` naming convention.

## Security Controls

- No default admin password is created.
- `SECRET_KEY` and `DATABASE_URL` are required.
- CSRF protection is enforced for state-changing forms.
- Login and upload-heavy routes are rate-limited.
- Session cookies are HTTP-only with secure defaults.
- Security headers include CSP, frame denial, nosniff, referrer policy,
  permissions policy, and HSTS when secure cookies are enabled.
- Uploads are constrained to the configured upload directory.
- Face images are validated as JPEG/PNG content with Pillow.
- CSV imports are parsed from memory and must match the expected schema.
- Biometric images, databases, CSV files, and logs are ignored by git.

## Data Handling

This project handles biometric images, names, schedules, rooms, and access
decisions. Treat all runtime data as sensitive:

- collect only with proper consent and authorization;
- retain only as long as operationally required;
- back up databases through controlled infrastructure, not git;
- rotate exposed credentials after any history or deployment incident;
- never commit uploaded images, CSV rosters, logs, or SQLite files.

## Deployment Notes

The repository includes `runtime.txt` and `.python-version` for Python 3.11.
Use `gunicorn` or the target platform's WSGI adapter for production. The web app
and recognition worker should be deployed as separate processes because the
worker needs camera and serial hardware access while the web app does not.

## Audit

See `AUDIT_REPORT.md` for the Phase 1 findings that drove this hardening work.
The audit branch was intentionally rebuilt from a clean orphan baseline after
historical biometric images, access logs, CSV files, and a SQLite database were
found in recoverable git history.
