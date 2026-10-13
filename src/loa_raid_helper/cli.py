"""앱 실행과 이미지 진단을 제공하는 명령줄 인터페이스임."""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

from . import __version__
from .config import load_config, write_default_config
from .domain import AppConfig


def smoke_test():
    import cv2
    from .demo import DemoSource
    from .domain import ScreenPhase
    from .guidance import GuidanceEngine
    from .vision import FrameAnalyzer

    source = DemoSource()
    try:
        analyzer = FrameAnalyzer(source.config)
        engine = GuidanceEngine(source.config)
        messages = []
        for hp in (180, 180, 175, 175):
            state = analyzer.analyze(source.frame(hp_lines=hp, phase=ScreenPhase.RAID))
            if state.boss.hp_lines != hp or not state.boss.verified:
                raise RuntimeError(f"HP OCR·보스 확인 실패: 기대 {hp}, 실제 {state.boss}")
            if not state.buffs:
                raise RuntimeError("버프 템플릿 인식 실패")
            messages.extend(engine.process(state))
        if len(messages) != 1:
            raise RuntimeError(f"기믹 안내 횟수 불일치: {len(messages)}")
        lobby = analyzer.analyze(source.frame(phase=ScreenPhase.LOBBY))
        if lobby.phase != ScreenPhase.LOBBY or not lobby.classes:
            raise RuntimeError("대기실·클래스 인식 실패")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from .ui import run_smoke_test
        if run_smoke_test(source.config) != 0:
            raise RuntimeError("UI 상태 표시 검증 실패")
        print(json.dumps({"status": "passed", "ocr_hp": [180, 175], "gimmick_messages": messages,
                          "lobby_classes": [item.label for item in lobby.classes],
                          "opencv": cv2.__version__, "ui": "passed"}, ensure_ascii=False))
    finally:
        source.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="로스트아크 레이드 헬퍼")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", type=Path, help="JSON 프로필 경로")
    parser.add_argument("--demo", action="store_true", help="게임 없이 합성 화면으로 데모 실행")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--init-config", type=Path, help="보정 전 기본 JSON 생성")
    actions.add_argument("--analyze", type=Path, help="스크린샷 한 장 인식 후 JSON 출력")
    actions.add_argument("--smoke-test", action="store_true", help="OCR·아이콘·안내·UI 통합 검증")
    args = parser.parse_args(argv)
    try:
        if args.init_config:
            write_default_config(args.init_config)
            print(f"기본 설정 생성: {args.init_config}")
            return 0
        if args.smoke_test:
            smoke_test()
            return 0
        config = load_config(args.config) if args.config else AppConfig()
        if args.analyze:
            import cv2
            import numpy as np
            from .vision import FrameAnalyzer
            image = cv2.imdecode(np.fromfile(args.analyze, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("이미지 파일을 읽을 수 없음")
            state = FrameAnalyzer(config).analyze(image)
            print(json.dumps(asdict(state), ensure_ascii=False))
            return 0
        from .ui import run_ui
        return run_ui(config, demo=args.demo)
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        print(f"실행 실패: {exc}", file=sys.stderr)
        return 1
