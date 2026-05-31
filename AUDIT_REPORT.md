# Security Audit Report

Repository: `abdelrahmen-zaouidi/ai_campus_access_attendance_control`

Branch: `audit/security-hardening`

Audit date: 2026-05-31

## 1. Project Overview

This repository implements a campus access and attendance control system built around a Flask admin web application, SQLite persistence, face-recognition-based identity checks, and Arduino serial control. An administrator logs in, creates teacher/course schedules, uploads face images or CSV course data, and reviews access logs. Separately, `compare.py` loads uploaded face images, reads webcam frames, checks recognized names against the course schedule in SQLite, logs granted or denied access, and sends a single-character command to an Arduino controller.

## 2. Architecture Summary

```text
Admin browser
    |
    | HTML forms: login, course CRUD, CSV/photo uploads, log review
    v
Flask app (app.py)
    |-- SQLite database: admin, course, access_log
    |-- uploads/: face images and uploaded CSVs
    |-- templates/static assets
    |
    +--> Vercel/Gunicorn deployment config (vercel.json)

Edge workstation / camera process
    |
    | webcam frames
    v
compare.py
    |-- loads face images from uploads/
    |-- imports Flask models from app.py
    |-- queries SQLite schedule/log tables
    |-- writes access_log.txt
    v
Serial COM9
    |
    v
Arduino Nano sketch
    |
    v
LED / lock simulation
```

## 3. Pre-audit Health Score

| Dimension | Score | Justification |
| --- | ---: | --- |
| Security | 2.0/10 | Biometric images, schedules, access logs, and a SQLite database were committed to history; the app creates a default `admin` account with a hard-coded password; CSRF, rate limiting, upload validation, secure session flags, and security headers are absent. |
| Maintainability | 3.0/10 | The web app, schema creation, default-user bootstrap, and edge recognition workflow are tightly coupled; importing `app.py` has side effects; dependencies are duplicated and partially unpinned. |
| Professionalism | 2.0/10 | The repo lacks README, LICENSE, SECURITY.md, CONTRIBUTING.md, CI, Docker assets, and an env example; templates contain mojibake text. |
| Documentation | 1.0/10 | There is no setup, security, deployment, data-retention, or hardware integration documentation. |
| Deployment readiness | 2.0/10 | `vercel.json` exists, but runtime secrets, Python version, native dependency constraints, persistent storage, uploads, and database location are not production-defined. |
| Scalability | 2.0/10 | SQLite and local filesystem uploads are single-instance assumptions; camera processing and web administration are not separated into deployable services. |
| Reliability | 2.5/10 | Limited error handling, direct form indexing, string dates/times, import-time database mutation, no migrations, and hard-coded serial/database paths make failures unpredictable. |
| Code quality | 3.0/10 | The code is readable at small scale, but validation, tests, service boundaries, configuration management, and dependency hygiene are below production baseline. |

## 4. Risk Findings

### CRITICAL

**C1. Biometric images, attendance/security logs, schedules, and a database remain recoverable from git history.**

- Citation: `09daa22:uploads/abdelmounim_zaouidi.jpg`, `09daa22:uploads/abderrahmane_zaouidi.jpg`, `09daa22:uploads/mehdi_zaouidi.jpg`, `09daa22:uploads/mohamed_bengherbia.jpeg`, `09daa22:uploads/mohamed_bengherbia.jpg`, `09daa22:uploads/personne_x.jpg`
- Citation: `09daa22:courses.csv`, `09daa22:uploads/courses.csv`, `09daa22:access_log.txt`, `09daa22:instance/teachers.db`
- Rationale: Face images are biometric identifiers. Course schedules and access logs reveal names, rooms, timestamps, and access decisions. Deleting these files in later commits does not remove them from cloneable history.
- Proposed fix: Ask for approval to scrub history. Default recommendation: orphan reset to a single baseline commit, then reapply the audit/hardening commits. Also rotate default/admin credentials and treat exposed biometric data as compromised.

**C2. The application bootstraps a default administrator with a hard-coded password.**

- Citation: `app.py:207` checks for username `admin`; `app.py:208` hashes literal `admin_password`; `app.py:209` inserts username `admin`.
- Citation: historical `09daa22:instance/teachers.db` contains username `admin` and a PBKDF2 hash for that default account.
- Rationale: Anyone with source access knows the initial administrator credentials. If a deployment started before password rotation, the admin account is guessable and grants full course/upload/log control.
- Proposed fix: Remove automatic default credentials. Require `ADMIN_USERNAME` and `ADMIN_PASSWORD` or an explicit one-time bootstrap command, fail closed when credentials are missing, and document forced rotation for existing deployments.

### HIGH

**H1. State-changing endpoints lack CSRF protection.**

- Citation: login form `templates/login.html:12`; add-course form `templates/add_teacher_course.html:13`; CSV upload form `templates/excel.html:12`; delete form `templates/view_courses.html:36`; edit form `templates/edit_course.html:13`.
- Citation: state-changing routes `app.py:54`, `app.py:75`, `app.py:126`, `app.py:158`, `app.py:169`.
- Rationale: Any authenticated admin can be tricked into submitting cross-site POST requests that create, edit, delete, or upload records.
- Proposed fix: Add Flask-WTF or `flask-seasurf` CSRF protection, inject CSRF tokens into every form, and ensure tests/smoke checks cover protected POSTs.

**H2. Authentication has no brute-force protection or account lockout.**

- Citation: login logic queries and checks credentials directly at `app.py:56` through `app.py:64`.
- Rationale: The default route is the admin login, and repeated guesses are not rate-limited. This compounds C2 because the known default username/password can be tested cheaply.
- Proposed fix: Add per-IP and per-username rate limiting with `Flask-Limiter`, structured auth logging, generic failure messages, and deployment guidance for reverse-proxy limits.

**H3. File upload handling trusts client-controlled content and paths.**

- Citation: image upload saves the provided file without MIME/content/size checks at `app.py:81` through `app.py:89`.
- Citation: CSV upload checks only `.endswith('.csv')` and saves `file.filename` directly at `app.py:130` through `app.py:134`.
- Citation: photo replacement deletes `course.face_id` and saves replacement content without file-type verification at `app.py:183` through `app.py:196`.
- Rationale: Attackers with admin access, or with CSRF from H1, can upload oversized or malformed files, overwrite unexpected paths via unsafe CSV names, poison the face dataset, or trigger unsafe parser behavior.
- Proposed fix: Use `secure_filename` for every upload, enforce a dedicated upload root with resolved-path containment checks, set `MAX_CONTENT_LENGTH`, validate MIME and magic bytes, store generated filenames, and reject malformed CSV schemas before writing.

**H4. Production secrets and security configuration are not fail-closed.**

- Citation: `app.py:14` reads `SECRET_KEY` with no validation; `app.py:15` hard-codes the SQLite URI; only minimal app config exists at `app.py:13` through `app.py:17`.
- Rationale: Missing or weak secrets break sessions or push teams toward ad hoc runtime fixes. Hard-coded database configuration prevents safe separation of dev/prod data.
- Proposed fix: Centralize config from environment variables, require `SECRET_KEY` and `DATABASE_URL`, fail at startup when required values are absent, and provide `.env.example` with no real secrets.

**H5. Debug server can be started with Werkzeug debugger enabled.**

- Citation: `app.py:212` through `app.py:217` starts `app.run(debug=True)`.
- Rationale: If used outside a controlled local environment, the interactive debugger can expose code execution and sensitive process state.
- Proposed fix: Use `FLASK_DEBUG=false` by default, bind debug mode only to an explicit development env var, and document Gunicorn/Vercel production entrypoints.

### MEDIUM

**M1. Dependency manifest is duplicated, partially unpinned, and includes OSV-advised vulnerable pinned versions.**

- Citation: unpinned `flask>=2.0.0` at `requirements.txt:1`, `gunicorn>=20.1.0` at `requirements.txt:2`, and `python-dotenv` at `requirements.txt:3`.
- Citation: duplicate/conflicting Flask and Gunicorn entries at `requirements.txt:1`, `requirements.txt:21`, `requirements.txt:2`, and `requirements.txt:29`.
- OSV query results on 2026-05-31 reported advisories for exact pinned versions: Flask 3.0.3, fonttools 4.54.1, Jinja2 3.1.4, Mako 1.3.6, Pillow 10.4.0, protobuf 3.20.3, and Werkzeug 3.0.6.
- Rationale: Unpinned and duplicate requirements make builds non-deterministic, while vulnerable pinned transitive/runtime packages create known supply-chain exposure.
- Proposed fix: Replace `requirements.txt` with a minimal, pinned runtime set tested locally; move tooling-only/desktop dependencies out of server runtime; upgrade packages to non-vulnerable versions; add `pip-audit` or OSV scanning to CI if feasible.

**M2. The recognition worker hard-codes local hardware and database paths.**

- Citation: serial port `COM9` at `compare.py:14`; database URI `sqlite:///C:/Users/Administrator/app/instance/teachers.db` at `compare.py:28`.
- Rationale: The process is not portable across machines, containers, or deployments. It can also point at a different database than the Flask app, creating split-brain access decisions.
- Proposed fix: Use environment variables for serial port, baud rate, camera index, and database URL; share a single config module; fail with actionable logs when configuration is missing.

**M3. Import-time database mutation causes unsafe side effects.**

- Citation: `compare.py:10` imports `Course` and `AccessLog` from `app`; `app.py:205` through `app.py:210` creates tables and possibly inserts an admin user during module import.
- Rationale: Any import for models, tests, CLI utilities, or recognition code can mutate persistent state and create credentials unexpectedly.
- Proposed fix: Move app creation into an application factory, move model definitions into a side-effect-free module, and make database initialization an explicit CLI or migration action.

**M4. Session cookie hardening and security headers are absent.**

- Citation: app config at `app.py:13` through `app.py:17` does not define `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE`, HSTS, CSP, frame protections, or referrer policy.
- Rationale: Admin sessions manage biometric upload and access-control data. Browser-side protections should be explicit, especially when deployed over HTTPS.
- Proposed fix: Add secure cookie defaults and response headers via Flask config and a small `after_request` hook or `Flask-Talisman`.

**M5. Form and CSV inputs are not schema-validated.**

- Citation: direct form indexing at `app.py:57`, `app.py:79` through `app.py:85`, and `app.py:175` through `app.py:180`.
- Citation: CSV rows are trusted at `app.py:136` through `app.py:148`.
- Rationale: Missing fields, malformed dates/times, invalid room names, duplicate face IDs, or unexpected CSV headers can cause 500s or inconsistent schedules.
- Proposed fix: Add server-side validation for all forms and CSV imports, parse dates/times into typed values, validate schedule intervals, and surface user-safe errors.

**M6. Runtime logging writes personal access events to a flat file.**

- Citation: `compare.py:25` configures `access_log.txt`; `compare.py:60` through `compare.py:61` writes name and status.
- Rationale: The repository already committed this file once. Local log files with names, timestamps, and decisions are likely to be copied, backed up, or recommitted unless retention and redaction rules are explicit.
- Proposed fix: Log security events to the database or structured application logs with retention, access controls, and `.gitignore` coverage. Avoid duplicating PII to plaintext files.

**M7. The edge recognition loop does not authenticate or acknowledge device commands.**

- Citation: `compare.py:16` through `compare.py:22` writes raw serial commands; Arduino accepts `1` or `0` directly at `unlocking_arduino_code/unlocking_arduino_code.ino:10` through `unlocking_arduino_code/unlocking_arduino_code.ino:16`.
- Rationale: A local process or serial-line fault can spoof access decisions. There is no command framing, retry/acknowledgement, or fail-safe state model.
- Proposed fix: Introduce explicit command framing, acknowledgement, timeout/retry handling, and a fail-closed controller state. Treat serial control as a hardware integration boundary, not just a UI signal.

### LOW

**L1. No license is present.**

- Citation: repository file list contains no `LICENSE`.
- Rationale: Reuse, contribution, and distribution rights are unclear.
- Proposed fix: Add Apache License 2.0 with copyright `Abderrahmane Zaouidi`, 2026, unless the owner chooses a different license.

**L2. No contributor, security, or setup documentation is present.**

- Citation: repository file list contains no `README.md`, `SECURITY.md`, or `CONTRIBUTING.md`.
- Rationale: New operators lack documented setup, secret handling, reporting, and contribution rules.
- Proposed fix: Add concise operational documentation covering local setup, env vars, security reporting, data handling, branch/commit conventions, and CI expectations.

**L3. No CI or smoke test exists.**

- Citation: repository file list contains no `.github/workflows/*`.
- Rationale: Security hardening can regress silently without at least linting and an import/smoke test.
- Proposed fix: Add GitHub Actions with pinned Ruff and a lightweight smoke test that avoids hardware/webcam side effects.

**L4. Deployment packaging is incomplete.**

- Citation: repository file list contains no `Dockerfile`, `docker-compose.yml`, or `.dockerignore`.
- Rationale: Operators do not have a reproducible local or container deployment path, and future images may accidentally include `.env`, `.git`, `uploads`, or databases.
- Proposed fix: Add non-root Docker runtime, `.dockerignore`, and compose defaults using environment variables and ignored local volumes.

**L5. Templates contain mojibake / encoding artifacts.**

- Citation: examples include `templates/add_teacher_course.html:17`, `templates/view_courses.html:17`, and `templates/access_logs.html:11`.
- Rationale: Broken French labels reduce professionalism and can indicate inconsistent encoding practices.
- Proposed fix: Normalize files to UTF-8 and correct display text while keeping behavior unchanged.

## 5. Git History Forensics

Command used:

```powershell
git log --all --pretty=format: --name-only --diff-filter=A | Sort-Object -Unique
```

Files ever committed:

```text
.gitignore
access_log.txt
app.py
compare.py
courses.csv
instance/teachers.db
PYTHON.code-workspace
requirements.txt
static/scripts.js
static/scripts_edit.js
static/scripts_login.js
static/scripts_logs.js
static/scripts_view.js
static/styles.css
static/styles_edit.css
static/styles_login.css
static/styles_logs.css
static/styles_view.css
templates/access_logs.html
templates/add_teacher_course.html
templates/edit_course.html
templates/excel.html
templates/login.html
templates/register.html
templates/view_courses.html
unlocking_arduino_code/unlocking_arduino_code.ino
uploads/abdelmounim_zaouidi.jpg
uploads/abderrahmane_zaouidi.jpg
uploads/courses.csv
uploads/mehdi_zaouidi.jpg
uploads/mohamed_bengherbia.jpeg
uploads/mohamed_bengherbia.jpg
uploads/personne_x.jpg
vercel.json
```

Flagged historical files and inspection result:

| Historical path | Last inspected content | Risk |
| --- | --- | --- |
| `access_log.txt` | 17 access events with names, timestamps, and Granted/Denied outcomes from 2024-11-28 to 2024-12-02. | PII and physical-access security event exposure. |
| `courses.csv` | 5 course rows containing names, room names, dates, schedules, and face image paths. | PII, schedule, and location exposure. |
| `uploads/courses.csv` | Same content/hash as `courses.csv`. | Duplicate PII/schedule exposure. |
| `instance/teachers.db` | SQLite database with `admin`, `course`, and `access_log` tables; 1 admin row, 5 course rows, 2 access-log rows. | Credential hash, PII, schedules, access decisions. |
| `uploads/abdelmounim_zaouidi.jpg` | JPEG, 538x720, SHA-256 `007b50a94b11f262cfb1877ec28f40b6f09e538e018291aca64ac7ad39b01c8b`. | Biometric face image. |
| `uploads/abderrahmane_zaouidi.jpg` | JPEG, 600x600, SHA-256 `55549385a92d4a78e7baa24923d218afd4745b10102bc3ae93becc8a1ca902a2`. | Biometric face image. |
| `uploads/mehdi_zaouidi.jpg` | JPEG, 600x600, SHA-256 `b317b88741ce27802c455c767735d9ba9cbc8db6a80f1357db85820b727b57a6`. | Biometric face image. |
| `uploads/mohamed_bengherbia.jpeg` | JPEG, 1125x1500, SHA-256 `f24442e77230f2c5438ab74bcb310afdbedc7a3e98ccbd25ca0f253e8da5737f`. | Biometric face image. |
| `uploads/mohamed_bengherbia.jpg` | Same bytes/hash as `uploads/mohamed_bengherbia.jpeg`. | Duplicate biometric face image. |
| `uploads/personne_x.jpg` | JPEG, 537x720, SHA-256 `9fba1704ea5d373cb36bdf97fa3be016b6b8a310a699bb0cd24cfae3d04e3f91`. | Biometric/identity image. |
| `PYTHON.code-workspace` | VS Code workspace paths under `../Desktop/abdelrahmen/...`. | Local path/internal project-structure disclosure. |
| `app.py` | Default admin password and secret/config handling. | Credential and insecure configuration pattern. |
| `compare.py` | Local Windows DB path and COM port. | Internal path/device disclosure and deployment fragility. |

Recommendation: request explicit approval before history rewriting. Given the presence of biometric images, schedules, access logs, and a database in history, my default recommendation is an orphan reset to a single clean baseline commit, then layer this audit branch and hardening commits on top.

## 6. Inline Secret Scan

Current HEAD scan patterns:

```text
api[_-]?key
password\s*=
token\s*=
secret\s*=
bearer
BEGIN.*PRIVATE.*KEY
firebase
service_account
AKIA[0-9A-Z]{16}
SECRET_KEY
admin_password
```

Current HEAD findings:

| File | Finding | Assessment |
| --- | --- | --- |
| `app.py:14` | `SECRET_KEY` is read from the environment without validation. | Not a committed secret, but insecure fail-open/fail-late config. |
| `app.py:207`-`app.py:209` | Default `admin` account with literal password `admin_password`. | Actual credential embedded in source. |
| `static/scripts_login.js:8` | Reads password form field client-side. | Not a secret leak by itself. |

Recoverable history findings:

- The same `app.py` default credential pattern exists across reachable commits.
- Historical `instance/teachers.db` contains a PBKDF2 password hash for username `admin`.
- No API keys, bearer tokens, private keys, Firebase service-account blobs, Google service accounts, or AWS access keys were found by the configured scan patterns.
- Hard-coded environment/device values were found across history: `compare.py:14` (`COM9`), `compare.py:28` (`C:/Users/Administrator/app/instance/teachers.db`), and `app.py:15` (`sqlite:///teachers.db`).

## 7. Dependency Audit

Local scanner status:

- `python -m pip_audit -r requirements.txt` could not run because `pip_audit` is not installed.
- Used OSV public API (`https://api.osv.dev/v1/querybatch`) against `requirements.txt` on 2026-05-31.

Pinned versus unpinned:

- Unpinned/ranged: `flask>=2.0.0` (`requirements.txt:1`), `gunicorn>=20.1.0` (`requirements.txt:2`), `python-dotenv` (`requirements.txt:3`).
- Duplicated/conflicting: Flask appears as both ranged lowercase `flask>=2.0.0` and pinned `Flask==3.0.3`; Gunicorn appears as both ranged lowercase `gunicorn>=20.1.0` and pinned `gunicorn==23.0.0`.
- All other listed packages are pinned with `==`.

OSV advisories reported for exact pinned package versions:

| Package | Version | OSV advisory ids reported |
| --- | --- | --- |
| Flask | 3.0.3 | `GHSA-68rp-wp8r-4726` |
| fonttools | 4.54.1 | `GHSA-768j-98cg-p3fv` |
| Jinja2 | 3.1.4 | `GHSA-cpwx-vrp4-4pq7`, `GHSA-gmj6-6f8f-6699`, `GHSA-q2x7-8rv6-6q7h` |
| Mako | 1.3.6 | `GHSA-2h4p-vjrc-8xpq`, `GHSA-v92g-xgxw-vvmm`, `PYSEC-2026-88` |
| Pillow | 10.4.0 | `GHSA-cfh3-3jmp-rvhc`, `GHSA-pwv6-vv43-88gr`, `GHSA-r73j-pqj5-w3x7`, `GHSA-whj4-6x5x-4v2j`, `GHSA-wjx4-4jcj-g98j`, `PYSEC-2026-165` |
| protobuf | 3.20.3 | `GHSA-7gcm-g887-7qv7`, `GHSA-8qvm-5x2c-j2w7` |
| Werkzeug | 3.0.6 | `GHSA-29vq-49wr-vm6x`, `GHSA-87hc-h4r5-73f7`, `GHSA-hgf8-39gv-g3f2` |

Deprecated/abandoned or questionable packages:

- `face-recognition==1.3.0` was uploaded to PyPI on 2020-02-20 and appears stale for a biometric/security-critical dependency.
- `tk==0.1.0`, `PyQt6`, `tkcalendar`, `ttkbootstrap`, `pyinstaller`, and desktop/packaging libraries appear unrelated to the Flask server runtime and should be separated into optional desktop/dev requirements if still needed.
- Native-heavy packages (`dlib`, OpenCV, SciPy, mediapipe) make serverless deployment fragile and should not be installed in the web admin runtime unless the web process actually needs them.

## 8. What This PR Will Do

- Add this audit report as the first committed artifact.
- After owner approval, harden only findings justified above.
- Preserve application behavior unless a change is required to remove an explicit security, reliability, or deployment risk.
- Pin dependencies to tested versions and remove duplicate requirement entries.
- Add free/open-source CI checks, documentation, license, security policy, and container/deployment hygiene if approved in the Phase 2 plan.

## 9. What This PR Will NOT Do

- It will not rewrite git history, force-push, delete recoverable data, or scrub sensitive blobs without explicit approval.
- It will not deploy the application or rotate real-world credentials on behalf of operators.
- It will not add paid services, telemetry, analytics, or proprietary dependencies.
- It will not redesign the product into a new architecture unless the owner explicitly expands scope beyond MVP hardening.
- It will not claim biometric/legal compliance; it can document and reduce risk, but policy and consent decisions remain owner/operator responsibilities.

## 10. Recommended Next Steps

1. Decide history treatment: do nothing, orphan-reset, or targeted filter-repo for sensitive paths.
2. Rotate any deployed admin credentials and assume the historical default admin password is compromised.
3. Confirm whether deleted biometric/course files should be restored with hardened defaults for local development, or kept out of the repo entirely.
4. Add explicit data retention and consent rules for face images, attendance logs, and room schedules.
5. Split the web admin runtime from the camera/Arduino worker runtime so server deployments do not install or execute camera/native desktop dependencies.
6. Add migrations and typed database fields for dates/times before scaling beyond a single local SQLite instance.
7. Add a hardware protocol boundary for Arduino control: command framing, acknowledgement, timeout, and fail-closed behavior.
8. Decide whether the Phase 2 scope is MVP hardening/professionalism only or includes architecture cleanup.

