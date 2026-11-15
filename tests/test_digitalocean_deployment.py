from pathlib import Path

import yaml


def test_digitalocean_app_spec_wires_core_components():
    spec = yaml.safe_load(Path(".do/app.yaml").read_text())

    assert spec["name"] == "autoreach-ai"

    service_names = {service["name"] for service in spec["services"]}
    worker_names = {worker["name"] for worker in spec["workers"]}
    database_names = {database["name"] for database in spec["databases"]}

    assert "autoreach-web" in service_names
    assert {"autoreach-worker", "autoreach-beat"} <= worker_names
    assert {"autoreach-db", "autoreach-redis"} <= database_names


def test_digitalocean_web_env_contains_launch_safety_flags():
    spec = yaml.safe_load(Path(".do/app.yaml").read_text())
    web = next(service for service in spec["services"] if service["name"] == "autoreach-web")
    env = {item["key"]: item for item in web["envs"]}

    assert env["DATABASE_URL"]["value"] == "${autoreach-db.DATABASE_URL}"
    assert env["REDIS_URL"]["value"] == "${autoreach-redis.REDIS_URL}"
    assert env["AUTOREACH_ENABLE_CONSOLE"]["value"] == "0"
    assert env["AUTOREACH_RUNTIME_SMART_DISPATCH"]["value"] == "1"
    assert env["AUTOREACH_WORKER_QUEUES"]["value"] == "engine,maintenance,standard-agents"
    assert env["AUTOREACH_JWT_SECRET"]["type"] == "SECRET"
    assert env["AUTOREACH_CREDENTIAL_ENCRYPTION_KEY"]["type"] == "SECRET"
    assert env["CALCOM_WEBHOOK_SECRET"]["type"] == "SECRET"


def test_digitalocean_worker_and_beat_commands_are_production_safe():
    spec = yaml.safe_load(Path(".do/app.yaml").read_text())
    workers = {worker["name"]: worker for worker in spec["workers"]}

    assert "-Q engine,maintenance,standard-agents" in workers["autoreach-worker"]["run_command"]
    assert "beat --loglevel=info" in workers["autoreach-beat"]["run_command"]

    worker_env = {item["key"]: item for item in workers["autoreach-worker"]["envs"]}
    beat_env = {item["key"]: item for item in workers["autoreach-beat"]["envs"]}

    assert worker_env["AUTOREACH_RUNTIME_SMART_DISPATCH"]["value"] == "1"
    assert worker_env["AUTOREACH_CREDENTIAL_ENCRYPTION_KEY"]["type"] == "SECRET"
    assert beat_env["AUTOREACH_CREDENTIAL_ENCRYPTION_KEY"]["type"] == "SECRET"


def test_dockerfile_builds_react_dashboard_for_digitalocean_image():
    dockerfile = Path("Dockerfile").read_text()

    assert "nodejs npm" in dockerfile
    assert "npm ci --prefix dashboard" in dockerfile
    assert "npm run build --prefix dashboard" in dockerfile
    assert "gunicorn" in dockerfile
