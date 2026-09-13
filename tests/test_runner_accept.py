from pathlib import Path

from PIL import Image

from sitewatch.runner import accept_baseline


def _make_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "reports" / "20260101T000000Z"
    site_dir = run_dir / "mysite"
    site_dir.mkdir(parents=True)
    Image.new("RGB", (10, 10), (1, 2, 3)).save(site_dir / "root.png")
    Image.new("RGB", (10, 10), (255, 0, 0)).save(site_dir / "root.diff.png")
    return run_dir


def test_accept_copies_screenshots_not_diffs(tmp_path):
    run_dir = _make_run(tmp_path)
    baseline_dir = tmp_path / "baselines"
    count = accept_baseline(run_dir, baseline_dir)
    assert count == 1
    assert (baseline_dir / "mysite" / "root.png").exists()
    assert not (baseline_dir / "mysite" / "root.diff.png").exists()


def test_accept_can_scope_to_one_site(tmp_path):
    run_dir = _make_run(tmp_path)
    other_site = run_dir / "othersite"
    other_site.mkdir()
    Image.new("RGB", (10, 10)).save(other_site / "root.png")

    baseline_dir = tmp_path / "baselines"
    count = accept_baseline(run_dir, baseline_dir, site_slug="mysite")
    assert count == 1
    assert not (baseline_dir / "othersite").exists()
