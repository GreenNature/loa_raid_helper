"""실제 게임 리소스와 무관한 합성 대기실·레이드 화면을 생성함."""

from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np

from .domain import AppConfig, ROI, RaidRule, ScreenPhase, TemplateSpec


class DemoSource:
    """임시 템플릿을 사용하여 데모 보스의 HP와 아이콘을 재현함."""

    def __init__(self):
        self._directory = TemporaryDirectory(prefix="loa-raid-demo-")
        self._index = 0
        self._closed = False
        self._images = {}
        for seed, name in enumerate(("raid", "boss", "lobby", "buff", "support", "damage"), 1):
            image = self._make_icon(seed)
            self._images[name] = image
            path = Path(self._directory.name) / f"{name}.png"
            if not cv2.imwrite(str(path), image):
                raise RuntimeError("데모 템플릿을 저장할 수 없음")

        def template(name, label, synergy=""):
            return TemplateSpec(name, label, Path(self._directory.name) / f"{name}.png", 0.90, synergy)

        self.config = AppConfig(
            hp_roi=ROI(0.43, 0.025, 0.14, 0.06),
            boss_roi=ROI(0.30, 0.0, 0.40, 0.14),
            buffs_roi=ROI(0.25, 0.75, 0.50, 0.23),
            lobby_roi=ROI(0.05, 0.10, 0.90, 0.65),
            raid_anchor=template("raid", "데모 레이드 표시"),
            boss_anchor=template("boss", "데모 보스"),
            lobby_anchor=template("lobby", "데모 대기실"),
            buffs=(template("buff", "데모 공격력 버프"),),
            classes=(
                template("support", "데모 지원 클래스", "파티 보호"),
                template("damage", "데모 공격 클래스", "피해 증가"),
            ),
            rules=(
                RaidRule("boss", 175, "데모 보스 175줄 기믹 안내임"),
                RaidRule("boss", 100, "데모 보스 100줄 기믹 안내임"),
            ),
            interval_ms=500,
            stable_frames=2,
        )

    @staticmethod
    def _make_icon(seed: int) -> np.ndarray:
        """재현 가능한 서로 다른 무늬의 아이콘을 생성함."""
        generator = np.random.default_rng(seed)
        small = generator.integers(30, 220, size=(6, 6, 3), dtype=np.uint8)
        image = cv2.resize(small, (36, 36), interpolation=cv2.INTER_LINEAR)
        return image

    def _paste(self, frame, name, x, y):
        image = self._images[name]
        frame[y:y + image.shape[0], x:x + image.shape[1]] = image

    def frame(
        self,
        hp_lines: int = 175,
        phase: ScreenPhase = ScreenPhase.RAID,
        show_buff: bool = True,
    ) -> np.ndarray:
        """스모크 검사와 스크린샷 평가용 정적 합성 화면을 생성함."""
        if self._closed:
            raise RuntimeError("데모 소스가 종료됨")
        frame = np.full((720, 1280, 3), (26, 22, 20), dtype=np.uint8)
        cv2.putText(frame, "SYNTHETIC DEMO / NO GAME DATA", (50, 670), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (140, 140, 140), 1)
        if phase == ScreenPhase.LOBBY:
            self._paste(frame, "lobby", 92, 100)
            self._paste(frame, "support", 420, 252)
            self._paste(frame, "damage", 648, 252)
            cv2.putText(frame, "DEMO LOBBY", (470, 185), cv2.FONT_HERSHEY_SIMPLEX, 1, (230, 230, 230), 2)
            return frame
        if phase != ScreenPhase.RAID:
            return frame
        self._paste(frame, "raid", 1100, 40)
        self._paste(frame, "boss", 404, 24)
        x, y, right, bottom = self.config.hp_roi.pixels(frame.shape)
        frame[y:bottom, x:right] = (20, 20, 20)
        cv2.putText(frame, f"x{hp_lines}", (x + 15, bottom - 8), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.rectangle(frame, (470, 86), (860, 96), (65, 45, 185), -1)
        cv2.putText(frame, "DEMO BOSS", (510, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (225, 225, 225), 1)
        if show_buff:
            self._paste(frame, "buff", 584, 592)
        return frame

    def next_frame(self) -> np.ndarray:
        """대기실과 HP 감소 레이드를 반복하여 시연함."""
        step = self._index % 36
        self._index += 1
        if step < 4:
            return self.frame(phase=ScreenPhase.LOBBY)
        hp_lines = max(20, 200 - ((step - 4) // 2) * 12)
        return self.frame(hp_lines=hp_lines, show_buff=step % 8 < 6)

    def close(self):
        if not self._closed:
            self._directory.cleanup()
            self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
