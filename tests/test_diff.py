from pathlib import Path

from PIL import Image

from sitewatch.diff import compare


def _save(path: Path, color: tuple[int, int, int], size=(40, 40)):
    Image.new("RGB", size, color).save(path)


def test_no_baseline_is_reported_as_new(tmp_path):
    current = tmp_path / "current.png"
    _save(current, (255, 255, 255))
    result = compare(None, current, tmp_path / "diff.png")
    assert result.is_new
    assert result.changed_pct is None


def test_identical_images_have_zero_diff(tmp_path):
    baseline = tmp_path / "baseline.png"
    current = tmp_path / "current.png"
    _save(baseline, (10, 20, 30))
    _save(current, (10, 20, 30))
    result = compare(baseline, current, tmp_path / "diff.png")
    assert not result.is_new
    assert result.changed_pct == 0.0
    assert result.diff_image_path is None


def test_large_change_is_flagged_with_diff_image(tmp_path):
    baseline = tmp_path / "baseline.png"
    current = tmp_path / "current.png"
    _save(baseline, (255, 255, 255))
    _save(current, (0, 0, 0))
    result = compare(baseline, current, tmp_path / "diff.png")
    assert not result.is_new
    assert result.changed_pct == 100.0
    assert result.diff_image_path is not None
    assert result.diff_image_path.exists()


def test_different_sized_images_are_padded_not_cropped(tmp_path):
    baseline = tmp_path / "baseline.png"
    current = tmp_path / "current.png"
    _save(baseline, (255, 255, 255), size=(40, 40))
    _save(current, (255, 255, 255), size=(40, 80))  # taller -- new content appended
    result = compare(baseline, current, tmp_path / "diff.png")
    # padding is white on both sides where they don't overlap in this all-white
    # case, so no diff should be reported
    assert result.changed_pct == 0.0
