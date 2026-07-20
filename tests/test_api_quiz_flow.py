import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

import pytest


def _signed_init_data(token: str, user_id: int = 42, username: str = "designer") -> str:
    values = {
        "auth_date": str(int(time.time())),
        "query_id": "test-query",
        "user": json.dumps({"id": user_id, "first_name": "D", "username": username}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_FILE", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("TELEGRAM_TOKEN", "test-token-for-pytest")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://dariyxyz.github.io")

    from app.core.config import get_settings
    get_settings.cache_clear()

    # content loader кэширует по test_key через lru_cache - для изоляции тестов
    # не нужен, содержимое не зависит от .env/БД.
    from fastapi.testclient import TestClient
    from app.api import main as api_main

    with TestClient(api_main.app) as test_client:
        yield test_client

    get_settings.cache_clear()


@pytest.fixture()
def auth_headers():
    return {"X-Telegram-Init-Data": _signed_init_data("test-token-for-pytest")}


def test_health(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_me_requires_init_data(client):
    assert client.get("/api/v1/me").status_code == 401


def test_designer_profile_full_flow(client, auth_headers):
    content = client.get("/api/v1/tests/designer-profile", headers=auth_headers).json()
    assert len(content["questions"]) == 30
    for question in content["questions"]:
        for option in question["options"]:
            assert "weights" not in option

    session = client.post(
        "/api/v1/sessions", headers=auth_headers, json={"test_key": "designer-profile"}
    )
    assert session.status_code == 201
    session_id = session.json()["id"]

    for question in content["questions"]:
        resp = client.put(
            f"/api/v1/sessions/{session_id}/answers/{question['id']}",
            headers=auth_headers,
            json={"option_id": question["options"][0]["id"]},
        )
        assert resp.status_code == 200

    resume = client.get(f"/api/v1/sessions/{session_id}", headers=auth_headers).json()
    assert len(resume["answers"]) == 30

    result = client.post(f"/api/v1/sessions/{session_id}/complete", headers=auth_headers).json()
    assert result["primary_narrative_key"]
    assert 0 <= result["primary_score"] <= 100
    assert result["confidence"] == 100
    assert len(result["alternatives"]) == 2

    # повторное завершение идемпотентно, не пересоздаёт результат
    again = client.post(f"/api/v1/sessions/{session_id}/complete", headers=auth_headers).json()
    assert again["primary_narrative_key"] == result["primary_narrative_key"]

    detail = client.get(f"/api/v1/sessions/{session_id}/result", headers=auth_headers).json()
    assert detail["primary_detail"]["advice"]

    blocked = client.put(
        f"/api/v1/sessions/{session_id}/answers/{content['questions'][0]['id']}",
        headers=auth_headers,
        json={"option_id": content["questions"][0]["options"][0]["id"]},
    )
    assert blocked.status_code == 409


def test_project_narrative_requires_project_id(client, auth_headers):
    resp = client.post(
        "/api/v1/sessions", headers=auth_headers, json={"test_key": "project-narrative"}
    )
    assert resp.status_code == 422


def test_project_narrative_full_flow(client, auth_headers):
    project = client.post(
        "/api/v1/projects",
        headers=auth_headers,
        json={"code_name": "Проект тест", "object_type": "office", "area_m2": 500},
    )
    assert project.status_code == 201
    project_id = project.json()["id"]

    content = client.get("/api/v1/tests/project-narrative", headers=auth_headers).json()
    session = client.post(
        "/api/v1/sessions",
        headers=auth_headers,
        json={"test_key": "project-narrative", "project_id": project_id},
    )
    assert session.status_code == 201
    session_id = session.json()["id"]

    for question in content["questions"]:
        client.put(
            f"/api/v1/sessions/{session_id}/answers/{question['id']}",
            headers=auth_headers,
            json={"option_id": question["options"][0]["id"]},
        )

    result = client.post(f"/api/v1/sessions/{session_id}/complete", headers=auth_headers).json()
    assert result["primary_narrative_key"]

    history = client.get("/api/v1/results", headers=auth_headers).json()
    assert len(history) == 1


def test_resume_picks_up_first_unanswered_question(client, auth_headers):
    content = client.get("/api/v1/tests/designer-profile", headers=auth_headers).json()
    session_id = client.post(
        "/api/v1/sessions", headers=auth_headers, json={"test_key": "designer-profile"}
    ).json()["id"]

    for question in content["questions"][:5]:
        client.put(
            f"/api/v1/sessions/{session_id}/answers/{question['id']}",
            headers=auth_headers,
            json={"option_id": question["options"][0]["id"]},
        )

    resume = client.get(f"/api/v1/sessions/{session_id}", headers=auth_headers).json()
    assert len(resume["answers"]) == 5
    assert resume["status"] == "in_progress"


def test_unknown_question_or_option_rejected(client, auth_headers):
    session_id = client.post(
        "/api/v1/sessions", headers=auth_headers, json={"test_key": "designer-profile"}
    ).json()["id"]

    assert client.put(
        f"/api/v1/sessions/{session_id}/answers/does-not-exist",
        headers=auth_headers,
        json={"option_id": "a"},
    ).status_code == 422

    assert client.put(
        f"/api/v1/sessions/{session_id}/answers/q1",
        headers=auth_headers,
        json={"option_id": "does-not-exist"},
    ).status_code == 422


def test_unknown_session_id_is_404(client, auth_headers):
    assert client.get("/api/v1/sessions/nope", headers=auth_headers).status_code == 404


def test_cannot_read_another_users_session(client, auth_headers):
    session_id = client.post(
        "/api/v1/sessions", headers=auth_headers, json={"test_key": "designer-profile"}
    ).json()["id"]

    other_headers = {"X-Telegram-Init-Data": _signed_init_data("test-token-for-pytest", user_id=999, username="other")}
    resp = client.get(f"/api/v1/sessions/{session_id}", headers=other_headers)
    assert resp.status_code == 404


def test_unknown_test_key_is_404(client, auth_headers):
    assert client.get("/api/v1/tests/does-not-exist", headers=auth_headers).status_code == 404
