"""정규화 ROI와 템플릿·숫자 OCR로 화면 상태를 인식함."""

import math
from pathlib import Path
import re
import time
from typing import Callable

import cv2
import numpy as np

from .domain import AppConfig, BossReading, FrameState, IconMatch, ScreenPhase, TemplateSpec


HP_TEXT = re.compile(r"(?:[xX×]\s*)?([0-9]{1,3})(?:\s*줄)?")
TEMPLATE_SCALES = (0.75, 0.9, 1.0, 1.1, 1.25, 1.5)


def parse_hp_lines(text: str, max_hp_lines: int = 999) -> int | None:
    """전체 문자열이 허용된 HP 표기일 때만 줄 수를 반환함."""
    match = HP_TEXT.fullmatch(text.strip())
    if match is None:
        return None
    value = int(match.group(1))
    return value if 0 <= value <= max_hp_lines else None


class NumericOCR:
    """RapidOCR의 문자 인식 모델 하나만 필요할 때 CPU로 불러옴."""

    def __init__(self):
        self._recognizer = None

    @staticmethod
    def _text_crop(image: np.ndarray) -> np.ndarray | None:
        """단색 HUD 배경의 숫자 여백을 줄이고 일정한 패딩을 붙임."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if int(gray.max()) - int(gray.min()) < 15:
            return None
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if np.count_nonzero(mask) > mask.size * 0.5:
            mask = cv2.bitwise_not(mask)
        x, y, width, height = cv2.boundingRect(mask)
        if min(width, height) < 4:
            return None
        crop = image[y:y + height, x:x + width]
        border = np.concatenate((image[0], image[-1], image[:, 0], image[:, -1]))
        background = tuple(float(value) for value in np.median(border, axis=0))
        return cv2.copyMakeBorder(crop, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=background)

    def __call__(self, image: np.ndarray) -> tuple[str, float]:
        image = self._text_crop(image)
        if image is None:
            return "", 0.0
        if self._recognizer is None:
            import rapidocr_onnxruntime
            from rapidocr_onnxruntime.ch_ppocr_rec import TextRecognizer
            from rapidocr_onnxruntime.utils import read_yaml, update_model_path

            package = Path(rapidocr_onnxruntime.__file__).parent
            settings = update_model_path(read_yaml(package / "config.yaml"))["Rec"]
            settings.update(
                intra_op_num_threads=1,
                inter_op_num_threads=1,
                use_cuda=False,
                use_dml=False,
                rec_batch_num=1,
            )
            self._recognizer = TextRecognizer(settings)
        result, _ = self._recognizer(np.ascontiguousarray(image))
        if not result:
            return "", 0.0
        text, score = result[0][:2]
        return str(text), float(score)


class FrameAnalyzer:
    """두 레이드 앵커가 확인된 화면에서만 HP와 버프를 읽음."""

    def __init__(
        self,
        config: AppConfig,
        ocr: Callable[[np.ndarray], tuple[str, float]] | None = None,
    ):
        self.config = config
        self._ocr = ocr if ocr is not None else NumericOCR()
        self._templates: dict[Path, np.ndarray] = {}
        specs = (
            config.raid_anchor,
            config.boss_anchor,
            config.lobby_anchor,
            *config.buffs,
            *config.classes,
        )
        for spec in specs:
            if spec is not None:
                self._load_template(spec)

    def _load_template(self, spec: TemplateSpec):
        """상수 영상의 무조건 일치를 방지하도록 저분산 템플릿을 거부함."""
        if spec.path in self._templates:
            return
        try:
            encoded = np.frombuffer(Path(spec.path).read_bytes(), dtype=np.uint8)
            template = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
        except (OSError, cv2.error) as error:
            raise ValueError(f"템플릿 파일을 읽을 수 없음: {spec.path}") from error
        if template is None or min(template.shape) < 4:
            raise ValueError(f"템플릿 영상 크기가 올바르지 않음: {spec.path}")
        if float(template.std()) < 5.0:
            raise ValueError(f"구분 가능한 무늬가 없는 템플릿임: {spec.path}")
        self._templates[spec.path] = template

    def _score(self, image: np.ndarray, spec: TemplateSpec | None) -> float:
        if spec is None or image.size == 0:
            return 0.0
        template = self._templates[spec.path]
        best = 0.0
        for scale in TEMPLATE_SCALES:
            width = round(template.shape[1] * scale)
            height = round(template.shape[0] * scale)
            if min(width, height) < 4 or width > image.shape[1] or height > image.shape[0]:
                continue
            scaled = cv2.resize(template, (width, height), interpolation=cv2.INTER_AREA)
            if float(scaled.std()) < 5.0:
                continue
            score = float(cv2.minMaxLoc(cv2.matchTemplate(image, scaled, cv2.TM_CCOEFF_NORMED))[1])
            if math.isfinite(score):
                best = max(best, score)
        return min(best, 1.0)

    def _icons(self, image: np.ndarray, specs: tuple[TemplateSpec, ...]) -> tuple[IconMatch, ...]:
        matches = []
        for spec in specs:
            score = self._score(image, spec)
            if score >= spec.threshold:
                matches.append(IconMatch(spec.id, spec.label, score, spec.synergy))
        return tuple(matches)

    def analyze(self, frame: np.ndarray) -> FrameState:
        if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("입력 화면은 BGR 3채널 영상이어야 함")
        if frame.dtype != np.uint8 or min(frame.shape[:2]) < 2:
            raise ValueError("입력 화면은 비어 있지 않은 uint8 영상이어야 함")
        config = self.config
        timestamp = time.monotonic()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        raid_score = self._score(gray, config.raid_anchor)
        boss_score = self._score(config.boss_roi.crop(gray), config.boss_anchor)
        lobby_image = config.lobby_roi.crop(gray)
        lobby_score = self._score(lobby_image, config.lobby_anchor)
        raid_found = config.raid_anchor is not None and raid_score >= config.raid_anchor.threshold
        boss_found = config.boss_anchor is not None and boss_score >= config.boss_anchor.threshold
        lobby_found = config.lobby_anchor is not None and lobby_score >= config.lobby_anchor.threshold
        verified = raid_found and boss_found
        if verified and not lobby_found:
            text, confidence = self._ocr(config.hp_roi.crop(frame))
            confidence = float(confidence)
            valid_confidence = math.isfinite(confidence) and config.min_ocr_confidence <= confidence <= 1
            hp_lines = parse_hp_lines(text, config.max_hp_lines) if valid_confidence else None
            confidence = min(raid_score, boss_score, confidence) if hp_lines is not None else 0.0
            boss = BossReading(config.boss_anchor.id, hp_lines, confidence, True)
            buffs = self._icons(config.buffs_roi.crop(gray), config.buffs)
            return FrameState(timestamp, ScreenPhase.RAID, boss, buffs)
        if lobby_found and not verified:
            classes = self._icons(lobby_image, config.classes)
            return FrameState(timestamp, ScreenPhase.LOBBY, classes=classes)
        return FrameState(timestamp)
