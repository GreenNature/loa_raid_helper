"""화면 캡처만으로 BGR 영상을 제공함."""

import threading

import numpy as np


class ScreenCapture:
    """실제 캡처 스레드에서 모니터 연결을 생성함."""

    def __init__(self, monitor: int = 1):
        if monitor < 1:
            raise ValueError("모니터 번호는 1 이상이어야 함")
        self.monitor = monitor
        self._local = threading.local()

    def next_frame(self) -> np.ndarray:
        if getattr(self._local, "session", None) is None:
            import mss

            self._local.session = mss.mss()
        session = self._local.session
        if self.monitor >= len(session.monitors):
            raise ValueError(f"모니터 {self.monitor}번을 찾을 수 없음")
        screenshot = session.grab(session.monitors[self.monitor])
        return np.asarray(screenshot, dtype=np.uint8)[:, :, :3].copy()

    def close(self):
        """캡처를 수행한 스레드의 연결을 해제함."""
        session = getattr(self._local, "session", None)
        if session is not None:
            session.close()
            self._local.session = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
