"""검증된 전투 화면의 연속 HP 관측으로 기믹을 안내함."""

from collections import deque
import math

from .domain import AppConfig, FrameState, ScreenPhase


class GuidanceEngine:
    """연속 관측을 안정화하고 전투마다 기믹 중복 안내를 방지함."""

    def __init__(self, config: AppConfig):
        self._config = config
        self._required_frames = max(1, config.stable_frames)
        self._samples: deque[int] = deque(maxlen=self._required_frames)
        self._sample_boss = ""
        self._boss_id = ""
        self._hp: int | None = None
        self._handled: set[tuple[int, str]] = set()
        self._lobby_frames = 0
        self._last_timestamp: float | None = None

    def process(self, state: FrameState) -> tuple[str, ...]:
        """안정화된 임계값 통과에 해당하는 신규 안내 문구를 반환함."""
        if state.phase == ScreenPhase.LOBBY:
            self._lobby_frames += 1
            self._clear_samples()
            if self._lobby_frames >= self._required_frames:
                self._clear_fight()
            return ()
        self._lobby_frames = 0
        boss = state.boss
        valid = (
            self._config.raid_anchor is not None
            and self._config.boss_anchor is not None
            and state.phase == ScreenPhase.RAID
            and boss.verified
            and bool(boss.boss_id)
            and isinstance(boss.hp_lines, int)
            and not isinstance(boss.hp_lines, bool)
            and 0 < boss.hp_lines <= self._config.max_hp_lines
            and math.isfinite(boss.confidence)
            and self._config.min_ocr_confidence <= boss.confidence <= 1.0
            and math.isfinite(state.timestamp)
        )
        if not valid:
            self._clear_samples()
            return ()
        if self._last_timestamp is not None:
            gap = state.timestamp - self._last_timestamp
            if gap <= 0:
                self._clear_samples()
                return ()
            if gap > max(2.0, self._config.interval_ms / 1000 * 4):
                self._clear_samples()
        self._last_timestamp = state.timestamp

        if boss.boss_id != self._sample_boss:
            self._clear_samples()
            self._sample_boss = boss.boss_id
        hp = boss.hp_lines
        if self._samples:
            # 작은 OCR 흔들림만 허용하며 큰 급락과 증가의 후보를 다시 모음.
            change = self._samples[-1] - hp
            max_change = max(3, math.ceil(self._config.max_hp_lines * 0.01))
            if change < -2 or change > max_change:
                self._samples.clear()
        self._samples.append(hp)
        if len(self._samples) < self._required_frames:
            return ()

        # 창 안의 모든 HP가 임계값 이하일 때만 통과를 확인함.
        confirmed_hp = max(self._samples)
        rules = sorted(
            (rule for rule in self._config.rules if rule.boss_id == boss.boss_id),
            key=lambda rule: rule.hp_lines,
            reverse=True,
        )
        messages = []
        if self._boss_id != boss.boss_id:
            self._boss_id = boss.boss_id
            self._handled.clear()
            self._hp = confirmed_hp
            for rule in rules:
                if rule.hp_lines >= confirmed_hp:
                    self._handled.add((rule.hp_lines, rule.message))
                    if rule.hp_lines == confirmed_hp and all(
                        sample == confirmed_hp for sample in self._samples
                    ):
                        messages.append(rule.message)
            return tuple(messages)

        previous_hp = self._hp
        self._hp = confirmed_hp
        for rule in rules:
            key = (rule.hp_lines, rule.message)
            if key in self._handled:
                continue
            if previous_hp is not None and previous_hp > rule.hp_lines >= confirmed_hp:
                self._handled.add(key)
                messages.append(rule.message)
        return tuple(messages)

    def _clear_samples(self):
        """후보 관측만 제거하고 현재 전투 이력은 유지함."""
        self._samples.clear()
        self._sample_boss = ""

    def _clear_fight(self):
        """확인된 대기 화면 이후 보스와 안내 이력을 초기화함."""
        self._boss_id = ""
        self._hp = None
        self._handled.clear()
        self._last_timestamp = None
