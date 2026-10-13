"""인식 작업 스레드와 컨트롤 패널 및 입력 통과 오버레이를 제공함."""

from dataclasses import replace
from datetime import datetime
import os
import time

import mss  # 다른 화면 라이브러리보다 먼저 불러 DPI 초기화 충돌을 줄임.

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QListWidget, QMainWindow, QPlainTextEdit, QPushButton, QSpinBox,
    QVBoxLayout, QWidget,
)

from .domain import AppConfig, BossReading, FrameState, IconMatch, ScreenPhase
from .voice import VoiceService


STYLE = """
QWidget { background: #10141d; color: #e7edf7; font-size: 13px; }
QMainWindow { background: #10141d; }
QLabel#title { font-size: 24px; font-weight: 700; }
QLabel#subtitle, QLabel#secondary { color: #8f9bad; }
QLabel#phase { color: #78dbcc; font-weight: 600; }
QLabel#hp { font-size: 38px; font-weight: 700; color: #eef5ff; }
QFrame#card { background: #1a2030; border: 1px solid #2a3447; border-radius: 12px; }
QFrame#card QLabel { background: transparent; }
QPushButton { background: #2b9388; border: 0; padding: 11px 16px; border-radius: 8px; font-weight: 600; }
QPushButton:hover { background: #32aa9c; }
QPushButton:disabled { background: #333c4d; color: #95a0b0; }
QSpinBox { background: #111724; border: 1px solid #344158; padding: 5px; border-radius: 5px; }
QCheckBox { spacing: 8px; }
QListWidget, QPlainTextEdit { background: #141b28; border: 1px solid #2a3447; border-radius: 7px; padding: 7px; }
QListWidget::item { padding: 5px; }
"""


class MonitorWorker(QObject):
    """화면 캡처와 OCR 및 안내 판단을 작업 스레드에서 처리함."""

    state_ready = Signal(object)
    announcements = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, config, demo=False):
        super().__init__()
        self.config = config
        self.demo = demo

    @Slot()
    def run(self):
        source = None
        try:
            from .capture import ScreenCapture
            from .demo import DemoSource
            from .guidance import GuidanceEngine
            from .vision import FrameAnalyzer

            source = DemoSource() if self.demo else ScreenCapture(self.config.monitor)
            config = source.config if self.demo else self.config
            analyzer = FrameAnalyzer(config)
            guidance = GuidanceEngine(config)
            thread = QThread.currentThread()
            while not thread.isInterruptionRequested():
                started = time.monotonic()
                state = analyzer.analyze(source.next_frame())
                if thread.isInterruptionRequested():
                    break
                self.state_ready.emit(state)
                messages = guidance.process(state)
                if messages:
                    self.announcements.emit(messages)
                deadline = started + config.interval_ms / 1000
                while time.monotonic() < deadline and not thread.isInterruptionRequested():
                    thread.msleep(min(25, max(1, int((deadline - time.monotonic()) * 1000))))
        except Exception as exc:
            self.failed.emit(f"모니터링 실패: {exc}")
        finally:
            if source is not None:
                try:
                    source.close()
                except Exception:
                    pass
            self.finished.emit()


class BuffOverlay(QWidget):
    """게임 입력과 포커스를 유지하는 별도 상태 표시 창임."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("레이드 버프 오버레이")
        self.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedWidth(230)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("overlay")
        card.setStyleSheet(
            "QFrame#overlay {background: rgba(17, 23, 35, 210); border: 1px solid #4b716b; border-radius: 10px;}"
            "QLabel {background: transparent; color: #eaf4f1; font-size: 14px;}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(13, 11, 13, 11)
        self.hp_label = QLabel("HP —")
        self.buff_label = QLabel("버프 없음")
        self.buff_label.setWordWrap(True)
        layout.addWidget(self.hp_label)
        layout.addWidget(self.buff_label)
        outer.addWidget(card)

    def update_state(self, state):
        hp = state.boss.hp_lines if state.boss.verified else None
        self.hp_label.setText(f"보스 HP  {hp}줄" if hp is not None else "보스 HP  확인 중")
        self.buff_label.setText("\n".join(match.label for match in state.buffs) or "버프 없음")
        self.adjustSize()


class ControlPanel(QMainWindow):
    """모니터링 설정과 인식 결과 및 안내 기록을 표시함."""

    def __init__(self, config, demo=False, voice_service=None):
        super().__init__()
        self.config = config
        self.demo = demo
        self._thread = None
        self._worker = None
        self._closing = False
        self._last_state = None
        self.voice = voice_service or VoiceService(self, enabled=config.voice_enabled)
        self.overlay = BuffOverlay()
        self.setWindowTitle("로스트아크 레이드 헬퍼")
        self.resize(660, 720)
        self.setMinimumSize(600, 640)
        self.setStyleSheet(STYLE)
        self._build_panel()
        self.voice.error.connect(self._voice_error)
        screens = QApplication.screens()
        if screens:
            screen = screens[min(config.monitor - 1, len(screens) - 1)].availableGeometry()
            self.overlay_x.setValue(screen.x() + screen.width() // 2 + 45)
            self.overlay_y.setValue(screen.y() + screen.height() // 2 - 35)
        self._move_overlay()

    def _build_panel(self):
        body = QWidget()
        self.setCentralWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        title = QLabel("RAID HELPER")
        title.setObjectName("title")
        subtitle = QLabel("로스트아크 · 화면 인식과 기믹 안내" + (" · 합성 데모" if self.demo else ""))
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("card")
        stats = QGridLayout(card)
        stats.setContentsMargins(18, 15, 18, 15)
        self.phase_label = QLabel("화면 확인 전")
        self.phase_label.setObjectName("phase")
        self.hp_label = QLabel("—")
        self.hp_label.setObjectName("hp")
        self.boss_label = QLabel("보스가 확인되면 HP를 표시합니다")
        self.boss_label.setObjectName("secondary")
        self.status_label = QLabel("대기 중")
        stats.addWidget(self.phase_label, 0, 0)
        stats.addWidget(self.hp_label, 1, 0)
        stats.addWidget(self.boss_label, 2, 0)
        stats.addWidget(self.status_label, 0, 1, 3, 1, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(card)

        settings = QHBoxLayout()
        self.monitor_spin = QSpinBox()
        self.monitor_spin.setRange(1, 16)
        self.monitor_spin.setValue(self.config.monitor)
        self.monitor_spin.setEnabled(not self.demo)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(100, 10000)
        self.interval_spin.setSingleStep(100)
        self.interval_spin.setSuffix(" ms")
        self.interval_spin.setValue(self.config.interval_ms)
        self.interval_spin.setEnabled(not self.demo)
        form = QFormLayout()
        form.addRow("캡처 모니터", self.monitor_spin)
        form.addRow("갱신 간격", self.interval_spin)
        settings.addLayout(form, 1)
        self.start_button = QPushButton("모니터링 시작")
        self.start_button.clicked.connect(self.toggle_monitoring)
        settings.addWidget(self.start_button, 1)
        layout.addLayout(settings)

        toggles = QHBoxLayout()
        self.voice_checkbox = QCheckBox("음성 안내")
        self.voice_checkbox.setChecked(self.config.voice_enabled)
        self.voice_checkbox.setEnabled(self.voice.available)
        self.voice_checkbox.toggled.connect(self.voice.set_enabled)
        self.overlay_checkbox = QCheckBox("버프 오버레이")
        self.overlay_checkbox.setChecked(True)
        self.overlay_checkbox.toggled.connect(self._refresh_overlay)
        toggles.addWidget(self.voice_checkbox)
        toggles.addWidget(self.overlay_checkbox)
        toggles.addStretch()
        layout.addLayout(toggles)
        self.voice_status = QLabel(self.voice.status)
        self.voice_status.setObjectName("secondary")
        self.voice_status.setWordWrap(True)
        layout.addWidget(self.voice_status)

        overlay_row = QHBoxLayout()
        overlay_row.addWidget(QLabel("오버레이 위치"))
        self.overlay_x = QSpinBox()
        self.overlay_y = QSpinBox()
        for name, control in (("X", self.overlay_x), ("Y", self.overlay_y)):
            control.setRange(-32768, 32768)
            control.setPrefix(f"{name} ")
            control.valueChanged.connect(self._move_overlay)
            overlay_row.addWidget(control)
        layout.addLayout(overlay_row)

        lists = QHBoxLayout()
        self.buffs_list = QListWidget()
        self.classes_list = QListWidget()
        for label, widget in (("활성 버프", self.buffs_list), ("대기실 클래스 · 시너지", self.classes_list)):
            column = QVBoxLayout()
            column.addWidget(QLabel(label))
            column.addWidget(widget)
            lists.addLayout(column)
        layout.addLayout(lists, 1)
        self.last_message = QLabel("기믹 안내를 기다리는 중입니다")
        self.last_message.setWordWrap(True)
        layout.addWidget(self.last_message)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(100)
        self.log.setMaximumHeight(105)
        self.log.setPlaceholderText("확인된 보스의 기믹 안내가 여기에 기록됩니다")
        layout.addWidget(self.log)

    def toggle_monitoring(self):
        if self._thread is not None:
            self.stop_monitoring()
        else:
            self.start_monitoring()

    def start_monitoring(self):
        """새 작업 스레드를 만들고 실시간 인식을 시작함."""
        if self._thread is not None or self._closing:
            return
        config = replace(
            self.config, monitor=self.monitor_spin.value(), interval_ms=self.interval_spin.value(),
        )
        self._last_state = None
        self._thread = QThread(self)
        self._worker = MonitorWorker(config, self.demo)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.state_ready.connect(self._receive_state)
        self._worker.announcements.connect(self._receive_announcements)
        self._worker.failed.connect(self._monitor_error)
        self._worker.finished.connect(self._thread.quit, Qt.ConnectionType.DirectConnection)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread_finished)
        self.status_label.setText("화면 확인 중")
        self.start_button.setText("모니터링 중지")
        self.monitor_spin.setEnabled(False)
        self.interval_spin.setEnabled(False)
        self._thread.start()

    def stop_monitoring(self):
        """현재 인식 작업을 마친 뒤 스레드를 종료하도록 요청함."""
        if self._thread is None:
            return
        self._thread.requestInterruption()
        self.start_button.setEnabled(False)
        self.status_label.setText("중지하는 중")
        self.overlay.hide()
        self.voice.stop()

    @Slot()
    def _thread_finished(self):
        thread = self._thread
        self._thread = None
        self._worker = None
        if thread is not None:
            thread.deleteLater()
        self.start_button.setEnabled(True)
        self.start_button.setText("모니터링 시작")
        self.monitor_spin.setEnabled(not self.demo)
        self.interval_spin.setEnabled(not self.demo)
        self.overlay.hide()
        if not self.status_label.text().startswith("모니터링 실패"):
            self.status_label.setText("대기 중")
        if self._closing:
            self.close()

    @Slot(object)
    def _receive_state(self, state):
        if self._thread is not None and not self._thread.isInterruptionRequested():
            self.update_state(state)

    @Slot(object)
    def _receive_announcements(self, messages):
        if self._thread is not None and not self._thread.isInterruptionRequested():
            self.show_announcements(messages)

    @Slot(object)
    def update_state(self, state):
        """작업 스레드의 자료만 받아 GUI 스레드에서 위젯을 갱신함."""
        self._last_state = state
        phases = {ScreenPhase.UNKNOWN: "화면 확인 중", ScreenPhase.LOBBY: "레이드 대기실", ScreenPhase.RAID: "레이드 진행 중"}
        self.phase_label.setText(phases[state.phase])
        hp = state.boss.hp_lines if state.boss.verified else None
        self.hp_label.setText(f"{hp}줄" if hp is not None else "—")
        self.boss_label.setText(
            f"확인된 보스 · {state.boss.boss_id}" if state.boss.verified
            else "보스 미확인 · 기믹 음성 대기"
        )
        self.buffs_list.clear()
        self.buffs_list.addItems([match.label for match in state.buffs])
        self.classes_list.clear()
        self.classes_list.addItems([
            f"{match.label} · {match.synergy or '시너지 미등록'}" for match in state.classes
        ])
        if self._thread is not None and not self._thread.isInterruptionRequested():
            self.status_label.setText("인식 중")
        self.overlay.update_state(state)
        self._refresh_overlay()

    @Slot(object)
    def show_announcements(self, messages):
        for message in messages:
            self.last_message.setText(message)
            self.log.appendPlainText(f"{datetime.now():%H:%M:%S}  {message}")
            self.voice.say(message)

    def _refresh_overlay(self):
        active = self._thread is not None and not self._thread.isInterruptionRequested()
        visible = (
            active and self.overlay_checkbox.isChecked()
            and self._last_state is not None and self._last_state.phase == ScreenPhase.RAID
            and not self._closing
        )
        self.overlay.setVisible(visible)

    def _move_overlay(self):
        self.overlay.move(self.overlay_x.value(), self.overlay_y.value())

    @Slot(str)
    def _monitor_error(self, message):
        self.status_label.setText(message)
        self.status_label.setWordWrap(True)
        self.log.appendPlainText(message)

    @Slot(str)
    def _voice_error(self, message):
        self.voice_status.setText(message)
        self.voice_checkbox.setChecked(False)
        self.voice_checkbox.setEnabled(False)

    def closeEvent(self, event):
        """실행 중인 스레드를 강제 파괴하지 않고 종료를 기다림."""
        self._closing = True
        self.overlay.hide()
        self.voice.stop()
        if self._thread is not None:
            self.stop_monitoring()
            self.setEnabled(False)
            event.ignore()
            return
        self.overlay.close()
        event.accept()


def run_ui(config: AppConfig, demo=False) -> int:
    """컨트롤 패널의 Qt 이벤트 루프를 실행함."""
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("로스트아크 레이드 헬퍼")
    window = ControlPanel(config, demo=demo)
    window.show()
    if demo:
        QTimer.singleShot(0, window.start_monitoring)
    return app.exec()


def run_smoke_test(config=None) -> int:
    """화면 서버 없이 상태 신호와 표시 및 종료 경로를 확인함."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    window = ControlPanel(config or AppConfig(), demo=True)
    class StateEmitter(QObject):
        state = Signal(object)

    emitter = StateEmitter()
    emitter.state.connect(window.update_state, Qt.ConnectionType.QueuedConnection)
    state = FrameState(
        timestamp=time.monotonic(), phase=ScreenPhase.RAID,
        boss=BossReading("demo-boss", 175, 1.0, True),
        buffs=(IconMatch("buff", "공격력 증가", 1.0),),
        classes=(IconMatch("class", "바드", 1.0, "공격력 증가"),),
    )
    window.show()
    emitter.state.emit(state)
    app.processEvents()
    try:
        assert window.hp_label.text() == "175줄"
        assert window.buffs_list.item(0).text() == "공격력 증가"
        assert "바드" in window.classes_list.item(0).text()
        assert window.overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput
        assert window.overlay.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
        window.show_announcements(("175줄 기믹 안내",))
        assert window.last_message.text() == "175줄 기믹 안내"
    finally:
        window.close()
        app.processEvents()
    return 0
