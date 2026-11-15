from fastapi.testclient import TestClient

from cockpit import create_app


def test_retired_digitalocean_host_redirects_to_azure(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "AUTOREACH_PUBLIC_BASE_URL",
        "https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io",
    )
    app = create_app(db_url=f"sqlite:///{tmp_path / 'redirect.db'}")
    client = TestClient(app)

    response = client.get(
        "/app/landing?from=old",
        headers={"host": "autoreach-ai-j2rdy.ondigitalocean.app"},
        follow_redirects=False,
    )

    assert response.status_code == 308
    assert response.headers["location"] == (
        "https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io"
        "/app/landing?from=old"
    )


def test_canonical_host_does_not_redirect(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "AUTOREACH_PUBLIC_BASE_URL",
        "https://attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io",
    )
    app = create_app(db_url=f"sqlite:///{tmp_path / 'no_redirect.db'}")
    client = TestClient(app)

    response = client.get(
        "/healthz",
        headers={"host": "attainly-web.ashymeadow-644c5a42.swedencentral.azurecontainerapps.io"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
