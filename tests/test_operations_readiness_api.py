from fastapi.testclient import TestClient

FERNET_KEY = "EFONWtQiHXh-5vpx9TVH0qCuVCkqUgJutdYjRM3J_iE="


def _auth_client(tmp_path):
    from cockpit import create_app

    app = create_app(db_url=f"sqlite:///{tmp_path / 'readiness_api.db'}")
    client = TestClient(app, raise_server_exceptions=True)
    response = client.post(
        "/api/auth/signup",
        json={
            "email": "ready@example.com",
            "password": "Password1!",
            "company_name": "Ready Ops",
        },
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_readiness_endpoint_requires_auth(tmp_path):
    client, _ = _auth_client(tmp_path)
    response = client.get("/api/operations/readiness")
    assert response.status_code == 401


def test_readiness_endpoint_returns_report(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("AUTOREACH_JWT_SECRET", "x" * 40)
    monkeypatch.setenv("AUTOREACH_SESSION_SECRET", "y" * 40)
    monkeypatch.setenv("AUTOREACH_CREDENTIAL_ENCRYPTION_KEY", FERNET_KEY)
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    monkeypatch.setenv("AUTOREACH_RUNTIME_SMART_DISPATCH", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("CALCOM_WEBHOOK_SECRET", "cal-secret")
    client, headers = _auth_client(tmp_path)

    response = client.get("/api/operations/readiness", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["is_production_ready"] is True
    assert data["missing_required"] == []
    assert any(check["key"] == "phoenix_endpoint" for check in data["checks"])


def test_readiness_endpoint_deep_mode_runs_dependency_probes(tmp_path, monkeypatch):
    import importlib
    import redis

    class FakeRedis:
        def ping(self):
            return True

        def close(self):
            return None

    class FakeInspect:
        def active_queues(self):
            return {
                "worker-1": [
                    {"name": "engine"},
                    {"name": "maintenance"},
                    {"name": "standard-agents"},
                ],
            }

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/db")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("AUTOREACH_JWT_SECRET", "x" * 40)
    monkeypatch.setenv("AUTOREACH_SESSION_SECRET", "y" * 40)
    monkeypatch.setenv("AUTOREACH_CREDENTIAL_ENCRYPTION_KEY", FERNET_KEY)
    monkeypatch.setenv("AUTOREACH_ENABLE_CONSOLE", "0")
    monkeypatch.setenv("AUTOREACH_RUNTIME_SMART_DISPATCH", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("CALCOM_WEBHOOK_SECRET", "cal-secret")
    monkeypatch.setenv("AUTOREACH_WORKER_QUEUES", "engine,maintenance,standard-agents")
    monkeypatch.setattr(redis.Redis, "from_url", lambda *_args, **_kwargs: FakeRedis())
    celery_module = importlib.import_module("engine.worker.celery_app")
    monkeypatch.setattr(celery_module.celery_app.control, "inspect", lambda timeout=1.0: FakeInspect())
    client, headers = _auth_client(tmp_path)

    response = client.get("/api/operations/readiness?deep=true", headers=headers)

    assert response.status_code == 200
    data = response.json()
    statuses = {check["key"]: check["status"] for check in data["checks"]}
    assert data["is_production_ready"] is True
    assert statuses["database_connectivity"] == "PASS"
    assert statuses["redis_connectivity"] == "PASS"
    assert statuses["celery_worker_queues"] == "PASS"
