"""화면 상태 표시와 오버레이 입력 정책을 확인함."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication

from loa_raid_helper.domain import AppConfig, BossReading, FrameState, IconMatch, ScreenPhase
from loa_raid_helper.ui import ControlPanel, run_smoke_test


class SilentVoice(QObject):
    """테스트 환경에서 운영체제 음성 엔진 접근을 생략함."""

    error = Signal(str)
    available = False
    status = "한국어 음성 미설치 · 화면 안내 사용"

    def __init__(self):
        super().__init__()
        self.messages = []

    def set_enabled(self, enabled):
        self.enabled = enabled

    def say(self, message):
        self.messages.append(message)

    def stop(self):
        pass


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(app):
    window = ControlPanel(AppConfig(), voice_service=SilentVoice())
    yield window
    window.close()
    app.processEvents()


def test_verified_boss_and_synergy_render(panel):
    panel.update_state(FrameState(
        1.0, ScreenPhase.RAID, BossReading("test-boss", 175, 0.98, True),
        (IconMatch("buff", "공격력 증가", 0.95),),
        (IconMatch("bard", "바드", 0.96, "공격력 증가"),),
    ))
    assert panel.phase_label.text() == "레이드 진행 중"
    assert panel.hp_label.text() == "175줄"
    assert panel.buffs_list.item(0).text() == "공격력 증가"
    assert panel.classes_list.item(0).text() == "바드 · 공격력 증가"


def test_unverified_boss_does_not_display_hp(panel):
    panel.update_state(FrameState(1.0, ScreenPhase.RAID, BossReading("", 175, 0.98, False)))
    assert panel.hp_label.text() == "—"
    assert panel.overlay.hp_label.text() == "보스 HP  확인 중"
    assert not panel.overlay.isVisible()


def test_overlay_does_not_capture_input_or_focus(panel):
    flags = panel.overlay.windowFlags()
    assert flags & Qt.WindowType.WindowTransparentForInput
    assert flags & Qt.WindowType.WindowDoesNotAcceptFocus
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert panel.overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert panel.overlay.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    panel.overlay_x.setValue(-120)
    panel.overlay_y.setValue(240)
    assert panel.overlay.x() == -120
    assert panel.overlay.y() == 240


def test_missing_voice_keeps_visual_announcements(panel):
    assert not panel.voice_checkbox.isEnabled()
    panel.show_announcements(("175줄 벨가 패턴 조심하세요",))
    assert panel.last_message.text() == "175줄 벨가 패턴 조심하세요"
    assert "175줄 벨가" in panel.log.toPlainText()


def test_stopped_worker_notifications_are_discarded(panel):
    panel._receive_announcements(("중지 이후 도착한 안내",))
    panel._receive_state(FrameState(1.0, ScreenPhase.RAID, BossReading("boss", 175, 1.0, True)))
    assert panel.log.toPlainText() == ""
    assert panel.voice.messages == []
    assert panel.hp_label.text() == "—"


def test_signal_smoke(app):
    assert run_smoke_test() == 0
