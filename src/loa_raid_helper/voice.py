"""운영체제의 한국어 음성 엔진으로 안내를 읽는 모듈임."""

from collections import deque

from PySide6.QtCore import QObject, QLocale, QTimer, Signal
from PySide6.QtTextToSpeech import QTextToSpeech


class VoiceService(QObject):
    """한국어 음성 가용성을 확인하고 짧은 안내 대기열을 관리함."""

    error = Signal(str)

    def __init__(self, parent=None, enabled=True):
        super().__init__(parent)
        self.enabled = enabled
        self.available = False
        self.status = "음성 엔진 없음 · 화면 안내 사용"
        self._engine = None
        self._pending = deque(maxlen=3)
        self._speaking = False
        try:
            engines = [name for name in QTextToSpeech.availableEngines() if name != "mock"]
            if not engines:
                return
            usable_engine = False
            for name in engines:
                engine = QTextToSpeech(name, self)
                if engine.state() == QTextToSpeech.State.Error:
                    engine.deleteLater()
                    continue
                usable_engine = True
                korean_locales = [
                    locale for locale in engine.availableLocales()
                    if locale.language() == QLocale.Language.Korean
                ]
                if korean_locales:
                    engine.setLocale(korean_locales[0])
                korean_voices = [
                    voice for voice in engine.availableVoices()
                    if voice.locale().language() == QLocale.Language.Korean
                ]
                if not korean_voices:
                    engine.deleteLater()
                    continue
                engine.setVoice(korean_voices[0])
                engine.setVolume(0.9)
                if engine.state() == QTextToSpeech.State.Error:
                    engine.deleteLater()
                    continue
                self._engine = engine
                engine.stateChanged.connect(self._on_state)
                self.available = True
                self.status = "한국어 음성 사용 가능"
                return
            self.status = (
                "한국어 음성 미설치 · 화면 안내 사용" if usable_engine
                else "음성 엔진 사용 불가 · 화면 안내 사용"
            )
        except (RuntimeError, OSError) as exc:
            self.status = f"음성 초기화 실패 · {exc}"

    def set_enabled(self, enabled):
        """음성 사용 여부를 바꾸며 비활성화 시 대기 안내를 비움."""
        self.enabled = bool(enabled)
        if not self.enabled:
            self.stop()

    def say(self, message):
        """오래된 안내 누적을 제한하며 문장을 재생함."""
        if not self.enabled or not self.available or not message.strip():
            return
        if self._engine.state() == QTextToSpeech.State.Ready and not self._pending and not self._speaking:
            self._speaking = True
            self._engine.say(message)
        else:
            self._pending.append(message)

    def _on_state(self, state):
        if state == QTextToSpeech.State.Error:
            self.available = False
            self._speaking = False
            self._pending.clear()
            self.status = "음성 재생 실패 · 화면 안내 사용"
            self.error.emit(self.status)
        elif state == QTextToSpeech.State.Ready:
            self._speaking = False
            if self._pending and self.enabled:
                QTimer.singleShot(0, self._speak_pending)

    def _speak_pending(self):
        if self.enabled and self.available and self._pending and not self._speaking:
            self._speaking = True
            self._engine.say(self._pending.popleft())

    def stop(self):
        """재생 중인 음성과 대기 안내를 중지함."""
        self._pending.clear()
        self._speaking = False
        if self._engine is not None:
            self._engine.stop()
