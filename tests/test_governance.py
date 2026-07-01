import json
from pathlib import Path

from catalogue_governance.guard import snapshot, verify, validate_offerings


def test_snapshot_and_verify(tmp_path: Path):
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True)
    sample_file = data_root / "sample_course.json"
    sample_file.write_text(json.dumps({"code": "PHI1024F", "name": "Introduction To Philosophy"}), encoding="utf-8")

    manifest_path = tmp_path / "manifest.json"
    snapshot(
        data_root=data_root,
        output=manifest_path,
        release_id="test-baseline",
        academic_year=2026,
        created_by="test",
        force=False,
    )

    result = verify(data_root=data_root, manifest_path=manifest_path)
    assert result["ok"] is True
    assert result["missing"] == []
    assert result["changed"] == []
    assert result["unexpected"] == []
    assert result["expected_count"] == 1
    assert result["actual_count"] == 1


def test_verify_reports_missing_file(tmp_path: Path):
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True)
    sample_file = data_root / "sample_course.json"
    sample_file.write_text(json.dumps({"code": "PHI1024F"}), encoding="utf-8")

    manifest_path = tmp_path / "manifest.json"
    snapshot(
        data_root=data_root,
        output=manifest_path,
        release_id="test-baseline",
        academic_year=2026,
        created_by="test",
        force=False,
    )

    sample_file.unlink()
    result = verify(data_root=data_root, manifest_path=manifest_path)
    assert result["ok"] is False
    assert result["missing"] == ["sample_course.json"]


def test_validate_offerings_ok(tmp_path: Path):
    template = tmp_path / "offerings.json"
    template.write_text(json.dumps([
        {"course_code": "PHI1024F", "term": "2026-S1", "campus": "Upper Campus"}
    ]), encoding="utf-8")
    validate_offerings(template)


def test_validate_offerings_missing_fields(tmp_path: Path):
    template = tmp_path / "offerings.json"
    template.write_text(json.dumps([
        {"course_code": "PHI1024F", "term": "2026-S1"}
    ]), encoding="utf-8")
    try:
        validate_offerings(template)
    except ValueError as e:
        assert "Missing required field 'campus'" in str(e)
    else:
        raise AssertionError("Expected ValueError for missing campus field")
