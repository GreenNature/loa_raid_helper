"""저장된 화면의 인식 결과와 선택적 정답 지표를 평가하는 도구임."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


class NoOCR:
    """아이콘 평가를 위해 OCR을 의도적으로 생략하는 어댑터임."""

    def __call__(self, image):
        return "", 0.0


def image_files(path: Path, recursive: bool):
    """입력 이미지 목록을 정렬하여 반환함."""
    if path.is_file():
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError("지원하지 않는 이미지 확장자임")
        return [path]
    if not path.is_dir():
        raise FileNotFoundError(f"입력 경로가 없음: {path}")
    items = path.rglob("*") if recursive else path.iterdir()
    files = sorted(item for item in items if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES)
    if not files:
        raise ValueError("평가할 이미지가 없음")
    return files


def summarize(records, truth):
    """정답이 있는 프레임에서 아이콘 및 HP 정확도를 집계함."""
    counts = {"true_positive": 0, "false_positive": 0, "false_negative": 0,
              "labeled_frames": 0, "hp_evaluated": 0, "hp_correct": 0,
              "hp_absence_evaluated": 0, "hp_absence_correct": 0,
              "phase_evaluated": 0, "phase_correct": 0,
              "boss_evaluated": 0, "boss_correct": 0}
    for record in records:
        expected = truth.get(record["file"])
        if expected is None:
            continue
        counts["labeled_frames"] += 1
        state = record["state"]
        for kind in ("buffs", "classes"):
            if kind not in expected:
                continue
            target = set(expected[kind])
            found = {match["id"] for match in state[kind]}
            counts["true_positive"] += len(target & found)
            counts["false_positive"] += len(found - target)
            counts["false_negative"] += len(target - found)
        if "hp_lines" in expected:
            if expected["hp_lines"] is None:
                counts["hp_absence_evaluated"] += 1
                counts["hp_absence_correct"] += state["boss"]["hp_lines"] is None
            else:
                counts["hp_evaluated"] += 1
                counts["hp_correct"] += state["boss"]["hp_lines"] == expected["hp_lines"]
        if "phase" in expected:
            counts["phase_evaluated"] += 1
            counts["phase_correct"] += state["phase"] == expected["phase"]
        if "boss_id" in expected:
            counts["boss_evaluated"] += 1
            counts["boss_correct"] += state["boss"]["boss_id"] == expected["boss_id"]
    tp, fp, fn = (counts[key] for key in ("true_positive", "false_positive", "false_negative"))
    return {**counts, "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "hp_exact_match": counts["hp_correct"] / counts["hp_evaluated"] if counts["hp_evaluated"] else None,
            "hp_absence_accuracy": counts["hp_absence_correct"] / counts["hp_absence_evaluated"] if counts["hp_absence_evaluated"] else None,
            "phase_accuracy": counts["phase_correct"] / counts["phase_evaluated"] if counts["phase_evaluated"] else None,
            "boss_accuracy": counts["boss_correct"] / counts["boss_evaluated"] if counts["boss_evaluated"] else None}


def read_truth(path: Path):
    """잘못된 정답 형식이 지표에 섞이지 않도록 검증함."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    truth = raw.get("frames") if isinstance(raw, dict) else None
    if not isinstance(truth, dict):
        raise ValueError("정답 JSON의 frames 객체가 필요함")
    for filename, expected in truth.items():
        if not isinstance(expected, dict):
            raise ValueError(f"프레임 정답이 객체여야 함: {filename}")
        for kind in ("buffs", "classes"):
            if kind in expected and (not isinstance(expected[kind], list) or any(not isinstance(item, str) or not item for item in expected[kind])):
                raise ValueError(f"{kind} 정답은 템플릿 ID 문자열 목록이어야 함: {filename}")
        if "hp_lines" in expected and expected["hp_lines"] is not None:
            hp = expected["hp_lines"]
            if isinstance(hp, bool) or not isinstance(hp, int) or not 0 <= hp <= 999:
                raise ValueError(f"HP 정답은 0~999 정수 또는 null이어야 함: {filename}")
        if "phase" in expected and expected["phase"] not in ("raid", "lobby", "unknown"):
            raise ValueError(f"화면 단계 정답이 올바르지 않음: {filename}")
        if "boss_id" in expected and not isinstance(expected["boss_id"], str):
            raise ValueError(f"boss_id 정답이 문자열이어야 함: {filename}")
    return truth


def main():
    """평가 명령행의 진입점임."""
    parser = argparse.ArgumentParser(description="스크린샷 인식 결과와 처리 시간을 JSON으로 기록함")
    parser.add_argument("input", type=Path, help="이미지 파일 또는 폴더임")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--truth", type=Path, help="문서에 정의된 frames 정답 JSON임")
    parser.add_argument("--output", type=Path, help="새 결과 JSON 경로이며 기존 파일을 보존함")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--no-ocr", action="store_true", help="아이콘 검증만 수행하며 HP OCR을 생략함")
    args = parser.parse_args()
    try:
        from loa_raid_helper.config import load_config
        from loa_raid_helper.vision import FrameAnalyzer

        if args.output and args.output.exists():
            raise FileExistsError(f"기존 결과 파일을 보존함: {args.output}")
        config = load_config(args.config)
        analyzer = FrameAnalyzer(config, ocr=NoOCR() if args.no_ocr else None)
        files = image_files(args.input, args.recursive)
        truth = None
        if args.truth:
            truth = read_truth(args.truth)
        records = []
        started = time.perf_counter()
        for path in files:
            frame = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError(f"이미지를 읽을 수 없음: {path}")
            frame_started = time.perf_counter()
            state = asdict(analyzer.analyze(frame))
            records.append({"file": path.relative_to(args.input).as_posix() if args.input.is_dir() else path.name,
                            "elapsed_ms": round((time.perf_counter() - frame_started) * 1000, 3),
                            "state": state,
                            "detected_labels": {kind: [item["label"] for item in state[kind]] for kind in ("buffs", "classes")}})
        result = {"schema_version": 1, "configuration": str(args.config),
                  "ocr_enabled": not args.no_ocr, "files_evaluated": len(records),
                  "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                  "frames": records, "metrics": summarize(records, truth) if truth is not None else None}
        payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(payload)
        print(payload, end="")
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"오류: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
