"""화면 오판정 차단과 실제 CPU 숫자 OCR을 검증함."""

from dataclasses import replace

import cv2
import numpy as np
import pytest

from loa_raid_helper.demo import DemoSource
from loa_raid_helper.domain import ScreenPhase, TemplateSpec
from loa_raid_helper.vision import FrameAnalyzer, NumericOCR, parse_hp_lines


@pytest.mark.parametrize(
    ("text", "expected"),
    [("x175", 175), ("× 175", 175), ("175줄", 175), ("175", 175), (" 0 ", 0),
     ("HP 175", None), ("175/200", None), ("1O0", None), ("1000", None), ("-5", None)],
)
def test_hp_text_requires_complete_numeric_label(text, expected):
    assert parse_hp_lines(text) == expected
    assert parse_hp_lines("175", max_hp_lines=100) is None


def test_verified_raid_recognizes_boss_hp_and_buff():
    with DemoSource() as demo:
        state = FrameAnalyzer(demo.config, ocr=lambda _: ("x175", 0.98)).analyze(demo.frame())
        assert state.phase is ScreenPhase.RAID
        assert state.boss.verified
        assert state.boss.boss_id == "boss"
        assert state.boss.hp_lines == 175
        assert state.boss.confidence >= 0.97
        assert [match.id for match in state.buffs] == ["buff"]


@pytest.mark.parametrize("missing", ["raid_anchor", "boss_anchor"])
def test_single_anchor_cannot_verify_raid_or_load_ocr(missing):
    with DemoSource() as demo:
        config = replace(demo.config, **{missing: None})

        def forbidden_ocr(_):
            raise AssertionError("미확인 화면에서는 OCR을 호출하면 안 됨")

        state = FrameAnalyzer(config, ocr=forbidden_ocr).analyze(demo.frame())
        assert state.phase is ScreenPhase.UNKNOWN
        assert not state.boss.verified
        assert not state.buffs


def test_lobby_returns_classes_and_synergies_without_ocr():
    with DemoSource() as demo:
        ocr = NumericOCR()
        state = FrameAnalyzer(demo.config, ocr=ocr).analyze(demo.frame(phase=ScreenPhase.LOBBY))
        assert state.phase is ScreenPhase.LOBBY
        assert {match.id for match in state.classes} == {"support", "damage"}
        assert all(match.synergy for match in state.classes)
        assert ocr._recognizer is None
        assert not state.boss.verified


@pytest.mark.parametrize("confidence", [0.1, float("nan"), float("inf"), 1.5])
def test_low_or_invalid_ocr_confidence_drops_hp(confidence):
    with DemoSource() as demo:
        state = FrameAnalyzer(demo.config, ocr=lambda _: ("175", confidence)).analyze(demo.frame())
        assert state.boss.hp_lines is None
        assert state.boss.confidence == 0


def test_ambiguous_lobby_and_raid_is_unknown():
    with DemoSource() as demo:
        frame = demo.frame()
        demo._paste(frame, "lobby", 90, 100)
        state = FrameAnalyzer(demo.config, ocr=lambda _: ("175", 1)).analyze(frame)
        assert state.phase is ScreenPhase.UNKNOWN
        assert not state.boss.verified


def test_resolution_change_uses_normalized_rois_and_scaled_templates():
    with DemoSource() as demo:
        frame = cv2.resize(demo.frame(), (960, 540), interpolation=cv2.INTER_AREA)
        state = FrameAnalyzer(demo.config, ocr=lambda _: ("175", 1)).analyze(frame)
        assert state.phase is ScreenPhase.RAID
        assert state.boss.hp_lines == 175
        assert state.buffs


def test_constant_template_is_rejected(tmp_path):
    path = tmp_path / "constant.png"
    cv2.imwrite(str(path), np.full((30, 30, 3), 120, np.uint8))
    with DemoSource() as demo:
        config = replace(demo.config, raid_anchor=TemplateSpec("bad", "저분산", path))
        with pytest.raises(ValueError, match="무늬"):
            FrameAnalyzer(config)


def test_real_cpu_ocr_reads_synthetic_hp():
    with DemoSource() as demo:
        analyzer = FrameAnalyzer(demo.config)
        for hp_lines in (200, 180, 175, 100, 20):
            state = analyzer.analyze(demo.frame(hp_lines=hp_lines))
            assert state.boss.hp_lines == hp_lines
            assert state.boss.confidence >= demo.config.min_ocr_confidence


def test_blank_hp_roi_does_not_load_ocr():
    reader = NumericOCR()
    assert reader(np.full((40, 150, 3), 20, np.uint8)) == ("", 0.0)
    assert reader._recognizer is None


def test_bad_frame_is_rejected():
    with DemoSource() as demo:
        analyzer = FrameAnalyzer(demo.config)
        with pytest.raises(ValueError, match="BGR"):
            analyzer.analyze(np.zeros((20, 20), np.uint8))
