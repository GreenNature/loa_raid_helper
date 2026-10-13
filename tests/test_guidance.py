"""OCR 오류와 전투 전환에 따른 기믹 안내를 검증함."""

from dataclasses import replace
from pathlib import Path

import pytest

from loa_raid_helper.domain import (
    AppConfig,
    BossReading,
    FrameState,
    RaidRule,
    ScreenPhase,
    TemplateSpec,
)
from loa_raid_helper.guidance import GuidanceEngine


@pytest.fixture
def config():
    return AppConfig(
        raid_anchor=TemplateSpec("raid", "레이드", Path("raid.png")),
        boss_anchor=TemplateSpec("boss", "보스", Path("boss.png")),
        rules=(
            RaidRule("boss-a", 175, "175줄 기믹임"),
            RaidRule("boss-a", 150, "150줄 기믹임"),
            RaidRule("boss-b", 175, "다른 보스 기믹임"),
        ),
    )


@pytest.fixture
def frames():
    timestamp = 0.0

    def frame(hp=None, *, phase=ScreenPhase.RAID, boss_id="boss-a", confidence=0.99, verified=True):
        nonlocal timestamp
        timestamp += 0.5
        return FrameState(timestamp, phase, BossReading(boss_id, hp, confidence, verified))

    return frame


def test_crossing_requires_consecutive_observations_and_fires_once(config, frames):
    engine = GuidanceEngine(config)
    assert engine.process(frames(180)) == ()
    assert engine.process(frames(180)) == ()
    assert engine.process(frames(175)) == ()
    assert engine.process(frames(174)) == ("175줄 기믹임",)
    assert engine.process(frames(174)) == ()
    assert engine.process(frames(170)) == ()


def test_one_frame_ocr_drop_does_not_trigger_guidance(config, frames):
    engine = GuidanceEngine(config)
    for hp in (180, 180, 14, 179, 178):
        assert engine.process(frames(hp)) == ()
    assert engine.process(frames(175)) == ()
    assert engine.process(frames(174)) == ("175줄 기믹임",)


def test_initial_reading_below_threshold_skips_past_mechanics(config, frames):
    engine = GuidanceEngine(config)
    assert engine.process(frames(160)) == ()
    assert engine.process(frames(160)) == ()
    for hp in (180, 180, 174, 174):
        assert engine.process(frames(hp)) == ()
    assert engine.process(frames(150)) == ()
    assert engine.process(frames(149)) == ("150줄 기믹임",)


def test_initial_exact_stable_threshold_notifies_only_that_mechanic(config, frames):
    engine = GuidanceEngine(config)
    assert engine.process(frames(150)) == ()
    assert engine.process(frames(150)) == ("150줄 기믹임",)
    assert engine.process(frames(150)) == ()


def test_first_moving_window_at_threshold_does_not_announce_past_mechanic(config, frames):
    engine = GuidanceEngine(config)
    assert engine.process(frames(175)) == ()
    assert engine.process(frames(174)) == ()
    assert engine.process(frames(174)) == ()


@pytest.mark.parametrize("phase", [ScreenPhase.UNKNOWN, ScreenPhase.LOBBY])
def test_transient_non_raid_keeps_handled_mechanics(config, frames, phase):
    engine = GuidanceEngine(config)
    engine.process(frames(175))
    assert engine.process(frames(175)) == ("175줄 기믹임",)
    assert engine.process(frames(phase=phase)) == ()
    for hp in (180, 180, 175, 175):
        assert engine.process(frames(hp)) == ()


def test_unknown_frames_break_confirmation_without_resetting_fight(config, frames):
    engine = GuidanceEngine(config)
    engine.process(frames(180))
    engine.process(frames(180))
    assert engine.process(frames(174)) == ()
    assert engine.process(frames(14, phase=ScreenPhase.UNKNOWN)) == ()
    assert engine.process(frames(174)) == ()
    assert engine.process(frames(174)) == ("175줄 기믹임",)


def test_sustained_lobby_resets_same_boss_for_new_entry(config, frames):
    engine = GuidanceEngine(config)
    engine.process(frames(175))
    assert engine.process(frames(175)) == ("175줄 기믹임",)
    engine.process(frames(phase=ScreenPhase.LOBBY))
    engine.process(frames(phase=ScreenPhase.LOBBY))
    assert engine.process(frames(175)) == ()
    assert engine.process(frames(175)) == ("175줄 기믹임",)


def test_boss_swap_requires_confirmation_and_resets_for_confirmed_boss(config, frames):
    engine = GuidanceEngine(config)
    engine.process(frames(175))
    assert engine.process(frames(175)) == ("175줄 기믹임",)
    assert engine.process(frames(175, boss_id="boss-b")) == ()
    assert engine.process(frames(175)) == ()
    assert engine.process(frames(175)) == ()
    assert engine.process(frames(175, boss_id="boss-b")) == ()
    assert engine.process(frames(175, boss_id="boss-b")) == ("다른 보스 기믹임",)


@pytest.mark.parametrize("field", ["raid_anchor", "boss_anchor"])
def test_missing_screen_anchors_disable_guidance(config, frames, field):
    engine = GuidanceEngine(replace(config, **{field: None}))
    assert engine.process(frames(175)) == ()
    assert engine.process(frames(175)) == ()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"verified": False},
        {"phase": ScreenPhase.UNKNOWN},
        {"confidence": 0.84},
        {"confidence": float("nan")},
        {"confidence": 1.1},
        {"boss_id": ""},
    ],
)
def test_invalid_readings_do_not_complete_confirmation(config, frames, kwargs):
    engine = GuidanceEngine(config)
    engine.process(frames(180))
    engine.process(frames(180))
    assert engine.process(frames(175)) == ()
    assert engine.process(frames(175, **kwargs)) == ()
    assert engine.process(frames(175)) == ()
    assert engine.process(frames(175)) == ("175줄 기믹임",)


@pytest.mark.parametrize("hp", [None, 0, -1, 1000, True, 175.0])
def test_missing_or_out_of_range_hp_cannot_complete_confirmation(config, frames, hp):
    engine = GuidanceEngine(config)
    engine.process(frames(180))
    engine.process(frames(180))
    engine.process(frames(175))
    assert engine.process(frames(hp)) == ()
    assert engine.process(frames(175)) == ()
    assert engine.process(frames(175)) == ("175줄 기믹임",)


def test_repeated_timestamp_is_not_a_second_observation(config, frames):
    engine = GuidanceEngine(config)
    engine.process(frames(180))
    engine.process(frames(180))
    below = frames(175)
    assert engine.process(below) == ()
    assert engine.process(below) == ()
    assert engine.process(frames(175)) == ()
    assert engine.process(frames(175)) == ("175줄 기믹임",)


def test_large_increase_breaks_hp_stability(config, frames):
    engine = GuidanceEngine(config)
    engine.process(frames(180))
    engine.process(frames(180))
    assert engine.process(frames(149)) == ()
    assert engine.process(frames(174)) == ()
    assert engine.process(frames(173)) == ("175줄 기믹임",)


def test_sustained_large_drop_is_confirmed_and_orders_crossed_rules(config, frames):
    engine = GuidanceEngine(config)
    engine.process(frames(180))
    engine.process(frames(180))
    assert engine.process(frames(149)) == ()
    assert engine.process(frames(148)) == ("175줄 기믹임", "150줄 기믹임")


def test_configured_stability_of_three_frames_is_observed(config, frames):
    engine = GuidanceEngine(replace(config, stable_frames=3))
    for hp in (180, 180, 180, 175, 174):
        assert engine.process(frames(hp)) == ()
    assert engine.process(frames(173)) == ("175줄 기믹임",)
