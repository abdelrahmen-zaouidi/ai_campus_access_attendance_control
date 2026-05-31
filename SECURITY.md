# Security Policy

## Reporting a Vulnerability

Report security issues privately to:

```text
abdelrahmenzaouidi@gmail.com
```

Do not open public issues for vulnerabilities involving credentials,
biometric images, access logs, schedules, database files, serial control, or
deployment configuration.

Please include:

- affected file, endpoint, or workflow;
- reproduction steps;
- expected impact;
- whether any credentials, biometric data, or logs may have been exposed;
- suggested remediation if known.

## Data Classification

| Data | Classification | Repository policy |
| --- | --- | --- |
| Face images | Biometric / highly sensitive | Never commit |
| SQLite databases | Sensitive operational data | Never commit |
| Access logs | Sensitive security event data | Never commit |
| Course CSV files | PII / schedule / location data | Never commit |
| `.env` files | Secret configuration | Never commit |
| Arduino serial settings | Deployment configuration | Use environment variables |

## Enforcement Matrix

| Control | Status | Notes |
| --- | --- | --- |
| Default admin password removed | Enforced | First admin must be explicitly bootstrapped from env vars. |
| Required `SECRET_KEY` | Enforced | App fails startup when missing. |
| Required `DATABASE_URL` | Enforced | App fails startup when missing. |
| CSRF protection | Enforced | State-changing forms require tokens. |
| Login/upload rate limits | Enforced | Defaults are in env-backed app config. |
| Secure browser headers | Enforced | CSP, frame denial, nosniff, referrer policy, permissions policy, and HSTS. |
| Upload path containment | Enforced | Upload destinations are resolved inside `UPLOAD_FOLDER`. |
| Image content validation | Enforced | JPEG/PNG verification uses Pillow. |
| CSV schema validation | Enforced | CSV imports are parsed from memory and validated. |
| Git ignore rules for sensitive data | Enforced | `.gitignore` and `.dockerignore` cover runtime data. |
| CI lint + smoke test | Enforced | GitHub Actions runs Ruff and pytest. |
| Hardware command authentication | Partial | Worker fails closed on serial failure; protocol authentication remains future work. |
| Biometric consent/retention policy | Operational | Must be defined by the deploying organization. |

## Credential Rotation

Rotate credentials after any suspected exposure:

1. Generate a new `SECRET_KEY`.
2. Rotate administrator passwords.
3. Rebuild deployments with the new environment.
4. Invalidate old sessions by restarting the app after key rotation.
5. Review access logs for suspicious activity.

## Historical Exposure Notice

The audit found biometric images, logs, schedules, and a SQLite database in
recoverable git history. This branch was rebuilt from an orphan baseline to keep
those blobs out of the hardened branch. Treat previously committed biometric and
credential material as exposed.
