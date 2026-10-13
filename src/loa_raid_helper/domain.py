"""화면 인식 결과와 설정의 공통 자료형임."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import math


class ScreenPhase(str, Enum):
    UNKNOWN = "unknown"
    LOBBY = "lobby"
    RAID = "raid"


@dataclass(frozen=True)
class ROI:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self):
        values = (self.x, self.y, self.width, self.height)
        if not all(type(v) in (int, float) and math.isfinite(v) for v in values):
            raise ValueError("ROI 좌표는 유한한 값이어야 함")
        if min(self.x, self.y) < 0 or min(self.width, self.height) <= 0:
            raise ValueError("ROI 위치와 크기가 올바르지 않음")
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("ROI는 화면 범위 안에 있어야 함")

    def pixels(self, shape):
        height, width = shape[:2]
        x, y = int(self.x * width), int(self.y * height)
        right = min(width, max(x + 1, round((self.x + self.width) * width)))
        bottom = min(height, max(y + 1, round((self.y + self.height) * height)))
        return x, y, right, bottom

    def crop(self, frame):
        x, y, right, bottom = self.pixels(frame.shape)
        return frame[y:bottom, x:right]


@dataclass(frozen=True)
class TemplateSpec:
    id: str
    label: str
    path: Path
    threshold: float = 0.88
    synergy: str = ""


@dataclass(frozen=True)
class RaidRule:
    boss_id: str
    hp_lines: int
    message: str


@dataclass(frozen=True)
class IconMatch:
    id: str
    label: str
    score: float
    synergy: str = ""


@dataclass(frozen=True)
class BossReading:
    boss_id: str = ""
    hp_lines: int | None = None
    confidence: float = 0.0
    verified: bool = False


@dataclass(frozen=True)
class FrameState:
    timestamp: float
    phase: ScreenPhase = ScreenPhase.UNKNOWN
    boss: BossReading = field(default_factory=BossReading)
    buffs: tuple[IconMatch, ...] = ()
    classes: tuple[IconMatch, ...] = ()


@dataclass(frozen=True)
class AppConfig:
    monitor: int = 1
    interval_ms: int = 500
    hp_roi: ROI = field(default_factory=lambda: ROI(0.36, 0.02, 0.28, 0.07))
    boss_roi: ROI = field(default_factory=lambda: ROI(0.30, 0.00, 0.40, 0.13))
    buffs_roi: ROI = field(default_factory=lambda: ROI(0.25, 0.75, 0.50, 0.23))
    lobby_roi: ROI = field(default_factory=lambda: ROI(0.05, 0.10, 0.90, 0.75))
    raid_anchor: TemplateSpec | None = None
    boss_anchor: TemplateSpec | None = None
    lobby_anchor: TemplateSpec | None = None
    buffs: tuple[TemplateSpec, ...] = ()
    classes: tuple[TemplateSpec, ...] = ()
    rules: tuple[RaidRule, ...] = ()
    stable_frames: int = 2
    max_hp_lines: int = 999
    min_ocr_confidence: float = 0.85
    voice_enabled: bool = True
