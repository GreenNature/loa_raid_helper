"""설정 검증과 외부 리소스 경로 보존을 검증함."""

import json

import pytest

from loa_raid_helper.config import default_config_data, load_config, write_default_config


def save_config(tmp_path, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_defaults_round_trip_without_resource_requirements(tmp_path):
    path = tmp_path / "settings" / "config.json"
    write_default_config(path)
    config = load_config(path)
    assert config.stable_frames == 2
    assert config.raid_anchor is None
    assert config.boss_anchor is None
    assert config.rules == ()


def test_default_creation_preserves_existing_user_configuration(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"monitor": 2}', encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_default_config(path)
    assert path.read_text(encoding="utf-8") == '{"monitor": 2}'


def test_template_path_is_relative_to_config_not_working_directory(tmp_path, monkeypatch):
    resource = tmp_path / "icons" / "boss.png"
    resource.parent.mkdir()
    resource.write_bytes(b"template")
    data = default_config_data()
    data["boss_anchor"] = {"id": "boss", "label": "보스", "path": "icons/boss.png"}
    path = save_config(tmp_path, data)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    config = load_config(path)
    assert config.boss_anchor.path == resource.resolve()


def test_missing_template_is_reported_before_app_starts(tmp_path):
    data = default_config_data()
    data["raid_anchor"] = {"id": "raid", "label": "레이드", "path": "missing.png"}
    with pytest.raises(ValueError, match="템플릿 파일이 없음"):
        load_config(save_config(tmp_path, data))


def test_unknown_setting_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="알 수 없는 설정 항목"):
        load_config(save_config(tmp_path, {"stable_frame": 2}))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("monitor", 0),
        ("interval_ms", 99),
        ("stable_frames", 0),
        ("max_hp_lines", 0),
        ("min_ocr_confidence", 0),
        ("min_ocr_confidence", 1.1),
    ],
)
def test_invalid_runtime_settings_are_rejected(tmp_path, field, value):
    with pytest.raises(ValueError):
        load_config(save_config(tmp_path, {field: value}))


@pytest.mark.parametrize("field", ["monitor", "interval_ms", "stable_frames", "max_hp_lines"])
@pytest.mark.parametrize("value", [True, 2.0, "2"])
def test_integer_runtime_settings_reject_other_json_types(tmp_path, field, value):
    with pytest.raises(ValueError, match="정수"):
        load_config(save_config(tmp_path, {field: value}))


@pytest.mark.parametrize("value", [1, "true", None])
def test_voice_setting_requires_boolean(tmp_path, value):
    with pytest.raises(ValueError, match="voice_enabled"):
        load_config(save_config(tmp_path, {"voice_enabled": value}))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "0.85"])
def test_ocr_confidence_requires_finite_number(tmp_path, value):
    with pytest.raises(ValueError, match="OCR 신뢰도"):
        load_config(save_config(tmp_path, {"min_ocr_confidence": value}))


@pytest.mark.parametrize("threshold", [0, -0.1, 1.1, True, float("nan")])
def test_invalid_template_threshold_is_rejected(tmp_path, threshold):
    (tmp_path / "boss.png").write_bytes(b"template")
    data = {
        "boss_anchor": {"id": "boss", "label": "보스", "path": "boss.png", "threshold": threshold}
    }
    with pytest.raises(ValueError, match="템플릿 임계값"):
        load_config(save_config(tmp_path, data))


@pytest.mark.parametrize(
    "rule",
    [
        {"boss_id": "", "hp_lines": 175, "message": "안내임"},
        {"boss_id": "boss", "hp_lines": 0, "message": "안내임"},
        {"boss_id": "boss", "hp_lines": 175, "message": "   "},
        {"boss_id": "boss", "hp_lines": 1000, "message": "안내임"},
        {"boss_id": "boss", "hp_lines": True, "message": "안내임"},
        {"boss_id": "boss", "hp_lines": 175.0, "message": "안내임"},
    ],
)
def test_incomplete_raid_rule_is_rejected(tmp_path, rule):
    with pytest.raises(ValueError, match="기믹 규칙"):
        load_config(save_config(tmp_path, {"rules": [rule]}))


def test_duplicate_boss_threshold_is_rejected(tmp_path):
    rules = [
        {"boss_id": "boss", "hp_lines": 175, "message": "첫 안내임"},
        {"boss_id": "boss", "hp_lines": 175, "message": "둘째 안내임"},
    ]
    with pytest.raises(ValueError, match="중복"):
        load_config(save_config(tmp_path, {"rules": rules}))


@pytest.mark.parametrize("data", [[], None, "config"])
def test_profile_root_requires_json_object(tmp_path, data):
    with pytest.raises(ValueError, match="JSON 객체"):
        load_config(save_config(tmp_path, data))


@pytest.mark.parametrize(
    "roi",
    [
        {"x": -0.1, "y": 0, "width": 0.5, "height": 0.5},
        {"x": 0.8, "y": 0, "width": 0.5, "height": 0.5},
        {"x": 0, "y": 0, "width": 0, "height": 0.5},
        {"x": 0, "y": 0, "width": float("nan"), "height": 0.5},
    ],
)
def test_invalid_roi_is_rejected(tmp_path, roi):
    with pytest.raises(ValueError):
        load_config(save_config(tmp_path, {"hp_roi": roi}))
