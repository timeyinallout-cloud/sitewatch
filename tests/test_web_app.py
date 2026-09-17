import base64
import json

import pytest
from fastapi.testclient import TestClient

from sitewatch.web import jobs
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
    monkeypatch.setattr("sitewatch.web.app._known_sites", lambda: [
        {"name": "MatchScout", "slug": "matchscout"},
        {"name": "PrivacyScan", "slug": "privacyscan"},
    ])
    return tmp_path


def test_index_requires_auth():
    assert client.get("/").status_code == 401


def test_index_renders_with_no_sweeps_yet():
    r = client.get("/", headers=AUTH)
    assert r.status_code == 200
    assert "No sweep has run yet" in r.text
    assert "MatchScout" in r.text


def test_index_shows_last_sweep_summary():
    job_id = jobs.create_job("sweep", "all", "button")
    jobs.finish_job(job_id, "complete", summary="0 issues found", detail={"origin": "github"})
    r = client.get("/", headers=AUTH)
    assert "0 issues found" in r.text


def test_index_flags_local_origin_as_unverified():
    job_id = jobs.create_job("sweep", "all", "button")
    jobs.finish_job(job_id, "complete", summary="ran locally", detail={"origin": "local"})
    r = client.get("/", headers=AUTH)
    assert "unconfirmed" in r.text.lower()


def test_health_needs_no_auth():
    assert client.get("/health").json() == {"status": "ok"}


def test_report_404_for_unknown_job():
    assert client.get("/report/doesnotexist", headers=AUTH).status_code == 404


def test_report_404_for_incomplete_job():
    job_id = jobs.create_job("sweep", "all", "button")
    assert client.get(f"/report/{job_id}", headers=AUTH).status_code == 404


def test_report_serves_the_stored_html(_isolated, tmp_path):
    report_dir = tmp_path / "run1"
    report_dir.mkdir()
    (report_dir / "report.html").write_text("<html>hello</html>")
    job_id = jobs.create_job("sweep", "all", "button")
    jobs.finish_job(job_id, "complete", summary="ok",
                     detail={"origin": "github", "report_path": str(report_dir / "report.html")})
    r = client.get(f"/report/{job_id}", headers=AUTH)
    assert r.status_code == 200
    assert "hello" in r.text


def test_report_asset_serves_sibling_file(tmp_path):
    report_dir = tmp_path / "run1"
    report_dir.mkdir()
    (report_dir / "report.html").write_text("<html></html>")
    (report_dir / "matchscout" / "root.png").parent.mkdir()
    (report_dir / "matchscout" / "root.png").write_bytes(b"\x89PNG")
    job_id = jobs.create_job("sweep", "all", "button")
    jobs.finish_job(job_id, "complete", summary="ok",
                     detail={"origin": "github", "report_path": str(report_dir / "report.html")})
    r = client.get(f"/report/{job_id}/matchscout/root.png", headers=AUTH)
    assert r.status_code == 200
    assert r.content == b"\x89PNG"


def test_report_asset_rejects_path_traversal(tmp_path):
    report_dir = tmp_path / "run1"
    report_dir.mkdir()
    (report_dir / "report.html").write_text("<html></html>")
    secret = tmp_path / "secret.txt"
    secret.write_text("nope")
    job_id = jobs.create_job("sweep", "all", "button")
    jobs.finish_job(job_id, "complete", summary="ok",
                     detail={"origin": "github", "report_path": str(report_dir / "report.html")})
    r = client.get(f"/report/{job_id}/../secret.txt", headers=AUTH)
    assert r.status_code in (400, 404)
