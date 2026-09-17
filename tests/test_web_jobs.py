import pytest

from sitewatch.web import jobs


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    jobs.init_db(p)
    monkeypatch.setattr(jobs, "DEFAULT_DB_PATH", p)
    return p


def test_create_and_get_job(db):
    job_id = jobs.create_job("sweep", "all", "button")
    row = jobs.get_job(job_id)
    assert row["kind"] == "sweep"
    assert row["target"] == "all"
    assert row["status"] == "queued"


def test_second_job_for_busy_target_raises_target_busy(db):
    jobs.create_job("sweep", "matchscout", "button")
    with pytest.raises(jobs.TargetBusyError):
        jobs.create_job("sweep", "matchscout", "typed")


def test_new_job_allowed_once_previous_is_terminal(db):
    first = jobs.create_job("sweep", "matchscout", "button")
    jobs.finish_job(first, "complete", summary="ok")
    second = jobs.create_job("sweep", "matchscout", "button")
    assert second != first


def test_different_targets_do_not_conflict(db):
    jobs.create_job("sweep", "matchscout", "button")
    jobs.create_job("sweep", "privacyscan", "button")  # must not raise


def test_start_and_finish_job_transitions(db):
    job_id = jobs.create_job("sweep", "all", "button")
    jobs.start_job(job_id)
    assert jobs.get_job(job_id)["status"] == "running"
    jobs.finish_job(job_id, "complete", summary="done", detail={"origin": "github"})
    row = jobs.get_job(job_id)
    assert row["status"] == "complete"
    assert row["summary"] == "done"


def test_finish_job_rejects_non_terminal_status(db):
    job_id = jobs.create_job("sweep", "all", "button")
    with pytest.raises(ValueError):
        jobs.finish_job(job_id, "running")


def test_messages_round_trip_and_update(db):
    job_id = jobs.create_job("sweep", "all", "button")
    jobs.add_message("user", "[sweep] all sites")
    msg_id = jobs.add_message("bot", "Working on it…", job_id=job_id)
    jobs.update_message_for_job(job_id, "Done.", [{"label": "View", "url": "https://x"}])
    rows = jobs.list_messages()
    updated = [r for r in rows if r["id"] == msg_id][0]
    assert updated["text"] == "Done."


def test_get_active_job_for_target_none_when_idle(db):
    assert jobs.get_active_job_for_target("all") is None


def test_get_last_complete_sweep_ignores_accept_jobs(db):
    accept_id = jobs.create_job("accept", "accept:123:all", "button")
    jobs.finish_job(accept_id, "complete", summary="accepted")
    assert jobs.get_last_complete_sweep() is None

    sweep_id = jobs.create_job("sweep", "all", "button")
    jobs.finish_job(sweep_id, "complete", summary="swept")
    row = jobs.get_last_complete_sweep()
    assert row["id"] == sweep_id


def test_get_last_complete_sweep_ignores_failed(db):
    job_id = jobs.create_job("sweep", "all", "button")
    jobs.finish_job(job_id, "failed", error="boom")
    assert jobs.get_last_complete_sweep() is None
