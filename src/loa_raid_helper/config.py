"""JSON 설정과 외부 리소스를 읽는 모듈임."""

import json
import math
from dataclasses import asdict
from pathlib import Path

from .domain import AppConfig, ROI, RaidRule, TemplateSpec


def load_config(path: str | Path) -> AppConfig:
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("프로필의 최상위 값은 JSON 객체여야 함")
    allowed = set(AppConfig.__dataclass_fields__)
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"알 수 없는 설정 항목: {', '.join(sorted(unknown))}")
    values = dict(data)
    for key in ("monitor", "interval_ms", "stable_frames", "max_hp_lines"):
        if key in values and (type(values[key]) is not int):
            raise ValueError(f"{key} 값은 정수여야 함")
    if "voice_enabled" in values and type(values["voice_enabled"]) is not bool:
        raise ValueError("voice_enabled 값은 참 또는 거짓이어야 함")
    confidence = values.get("min_ocr_confidence", 0.85)
    if type(confidence) not in (int, float) or not math.isfinite(confidence):
        raise ValueError("OCR 신뢰도는 유한한 숫자여야 함")
    for key in ("hp_roi", "boss_roi", "buffs_roi", "lobby_roi"):
        if key in values:
            values[key] = ROI(**values[key])

    def template(value):
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("템플릿은 JSON 객체여야 함")
        value = dict(value)
        if not all(isinstance(value.get(key), str) and value[key].strip() for key in ("id", "label", "path")):
            raise ValueError("템플릿 ID·이름·파일 경로가 필요함")
        value["path"] = (path.parent / value["path"]).resolve()
        if not value["path"].is_file():
            raise ValueError(f"템플릿 파일이 없음: {value['path']}")
        threshold = value.get("threshold", 0.88)
        if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 < threshold <= 1:
            raise ValueError("템플릿 임계값은 0 초과 1 이하여야 함")
        return TemplateSpec(**value)

    for key in ("raid_anchor", "boss_anchor", "lobby_anchor"):
        if key in values:
            values[key] = template(values[key])
    for key in ("buffs", "classes"):
        if key in values:
            values[key] = tuple(template(item) for item in values[key])
    if "rules" in values:
        if not isinstance(values["rules"], list):
            raise ValueError("기믹 규칙은 JSON 배열이어야 함")
        values["rules"] = tuple(RaidRule(**rule) for rule in values["rules"])
    config = AppConfig(**values)
    if config.monitor < 1 or config.interval_ms < 100 or config.stable_frames < 1:
        raise ValueError("모니터·갱신 간격·안정화 프레임 설정이 올바르지 않음")
    if config.max_hp_lines < 1 or not 0 < config.min_ocr_confidence <= 1:
        raise ValueError("HP 범위와 OCR 신뢰도 설정이 올바르지 않음")
    if any(type(rule.hp_lines) is not int or not 1 <= rule.hp_lines <= config.max_hp_lines
           or not isinstance(rule.boss_id, str) or not rule.boss_id.strip()
           or not isinstance(rule.message, str) or not rule.message.strip() for rule in config.rules):
        raise ValueError("기믹 규칙에 보스·HP·안내 문구가 필요함")
    if len({(rule.boss_id, rule.hp_lines) for rule in config.rules}) != len(config.rules):
        raise ValueError("같은 보스의 HP 기믹 규칙을 중복 등록할 수 없음")
    return config


def default_config_data():
    data = asdict(AppConfig())
    return data


def write_default_config(path: str | Path):
    path = Path(path)
    if path.exists():
        raise FileExistsError("기존 설정 파일을 덮어쓸 수 없음")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(default_config_data(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
