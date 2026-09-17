import base64

import pytest
from fastapi.testclient import TestClient

from sitewatch.web import jobs, sweep_ops
from sitewatch.web.app import app

client = TestClient(app)


def _basic(user: str, password: str) -> dict:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


AUTH = _basic("u", "p")


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setattr(jobs, "DEFAULT_DB_PATH", db)
    jobs.init_db(db)
    monkeypatch.setenv("SITEWATCH_USER", "u")
    monkeypatch.setenv("SITEWATCH_PASS", "p")
    monkeypatch.delenv("SITEWATCH_DEV_MODE", raising=False)
    monkeypatch.setattr("sitewatch.web.chat._known_site_slugs",
                         lambda: {"matchscout", "privacyscan"})

    calls = []

    def fake_sweep(job_id, site_slug):
        calls.append(("sweep", job_id, site_slug))
        jobs.finish_job(job_id, "complete", summary="0 issues", detail={"origin": "github", "run_id": 1})
        jobs.update_message_for_job(job_id, "0 issues", None)

    def fake_accept(job_id, run_id, site_slug):
        calls.append(("accept", job_id, run_id, site_slug))
        jobs.finish_job(job_id, "complete", summary=f"Accepted from {run_id}")
        jobs.update_message_for_job(job_id, f"Accepted from {run_id}", None)

    monkeypatch.setattr(sweep_ops, "run_sweep_job", fake_sweep)
    monkeypatch.setattr(sweep_ops, "run_accept_job", fake_accept)
    yield calls


def test_chat_page_requires_auth():
    assert client.get("/chat").status_code == 401


def test_chat_page_renders_with_auth():
    r = client.get("/chat", headers=AUTH)
    assert r.status_code == 200
    assert "run a sweep" in r.text.lower()


def test_action_sweep_all_sites(_isolated):
    r = client.post("/chat/action", headers=AUTH, json={"action": "sweep", "site": ""})
    assert r.status_code == 200
    body = r.json()
    assert body["started"] is True
    assert ("sweep", body["job_id"], None) in _isolated

    status = client.get(f"/jobs/{body['job_id']}", headers=AUTH).json()
    assert status["status"] == "complete"


def test_action_sweep_one_site(_isolated):
    r = client.post("/chat/action", headers=AUTH, json={"action": "sweep", "site": "matchscout"})
    assert r.json()["started"] is True
    assert ("sweep", r.json()["job_id"], "matchscout") in _isolated


def test_action_sweep_unknown_site_does_not_start_job(_isolated):
    r = client.post("/chat/action", headers=AUTH, json={"action": "sweep", "site": "not-a-site"})
    assert r.json()["started"] is False
    assert _isolated == []


def test_action_accept_requires_run_id(_isolated):
    r = client.post("/chat/action", headers=AUTH, json={"action": "accept", "run_id": ""})
    assert r.status_code == 400


def test_action_accept_starts_a_job(_isolated):
    r = client.post("/chat/action", headers=AUTH, json={"action": "accept", "run_id": "42"})
    assert r.json()["started"] is True
    assert ("accept", r.json()["job_id"], "42", None) in _isolated


def test_action_rejects_unknown_action():
    r = client.post("/chat/action", headers=AUTH, json={"action": "delete_everything"})
    assert r.status_code == 400


def test_second_sweep_for_busy_target_does_not_start_a_second_job(monkeypatch):
    def hanging(job_id, site_slug):
        pass  # never finishes -- target stays "active"
    monkeypatch.setattr(sweep_ops, "run_sweep_job", hanging)

    first = client.post("/chat/action", headers=AUTH, json={"action": "sweep", "site": ""})
    assert first.json()["started"] is True
    second = client.post("/chat/action", headers=AUTH, json={"action": "sweep", "site": ""})
    assert second.json()["started"] is False


def test_send_sweep_command(_isolated):
    r = client.post("/chat/send", headers=AUTH, json={"text": "run a sweep"})
    assert r.json()["started"] is True
    assert _isolated[0][0] == "sweep"


def test_send_sweep_for_site(_isolated):
    r = client.post("/chat/send", headers=AUTH, json={"text": "sweep matchscout"})
    assert r.json()["started"] is True
    assert _isolated[0][2] == "matchscout"


def test_send_accept_command(_isolated):
    r = client.post("/chat/send", headers=AUTH, json={"text": "accept 42"})
    assert r.json()["started"] is True
    assert _isolated[0] == ("accept", r.json()["job_id"], "42", None)


def test_send_status_command_replies_without_a_job(_isolated):
    r = client.post("/chat/send", headers=AUTH, json={"text": "status"})
    assert r.json()["started"] is False
    assert _isolated == []


def test_send_unparseable_text_does_not_start_a_job(_isolated):
    r = client.post("/chat/send", headers=AUTH, json={"text": "hello there"})
    assert r.json()["started"] is False
    assert _isolated == []


def test_send_empty_text_is_rejected():
    r = client.post("/chat/send", headers=AUTH, json={"text": "   "})
    assert r.status_code == 400


def test_job_status_requires_auth(_isolated):
    r = client.post("/chat/action", headers=AUTH, json={"action": "sweep", "site": ""})
    job_id = r.json()["job_id"]
    assert client.get(f"/jobs/{job_id}").status_code == 401


def test_job_status_404_for_unknown_id():
    assert client.get("/jobs/doesnotexist", headers=AUTH).status_code == 404
