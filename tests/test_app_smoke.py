import importlib
import sys


def _load_app(monkeypatch, tmp_path):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-with-enough-length")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'teachers.db'}")
    monkeypatch.setenv("UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "change-this-test-password")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")

    sys.modules.pop("app", None)
    app_module = importlib.import_module("app")
    return app_module.app, app_module.Admin


def test_login_page_renders_csrf_and_security_headers(monkeypatch, tmp_path):
    app, _ = _load_app(monkeypatch, tmp_path)
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b'csrf_token' in response.data
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_post_without_csrf_is_rejected(monkeypatch, tmp_path):
    app, _ = _load_app(monkeypatch, tmp_path)
    client = app.test_client()

    response = client.post(
        "/",
        data={"username": "admin", "password": "change-this-test-password"},
    )

    assert response.status_code == 400


def test_admin_bootstrap_uses_environment(monkeypatch, tmp_path):
    app, admin_model = _load_app(monkeypatch, tmp_path)

    with app.app_context():
        admin = admin_model.query.filter_by(username="admin").first()

    assert admin is not None
