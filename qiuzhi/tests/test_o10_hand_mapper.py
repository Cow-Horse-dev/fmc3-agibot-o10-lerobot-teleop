import math
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LEROBOT_PLAY_ROOT = (
    REPO_ROOT / "qiuzhi" / "lerobot_play_1.0.4" / "x86" / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)
if str(LEROBOT_PLAY_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_ROOT))

from lerobot_play.utils.agibot_o10 import (
    AGIBOT_O10_HAND_FEATURE_NAMES,
    O10_DEFAULT_CHANNEL_PARAMS,
    O10ChannelParams,
    O10HandMapper,
    _o10_apply_curve,
)


def test_default_channel_params_has_one_entry_per_hand_feature():
    assert len(O10_DEFAULT_CHANNEL_PARAMS) == len(AGIBOT_O10_HAND_FEATURE_NAMES) == 10


def test_default_channel_params_are_monotonic_and_nonnegative():
    for index, params in enumerate(O10_DEFAULT_CHANNEL_PARAMS):
        assert params.dead_band == 3.0
        assert 0 < params.in_low < params.in_mid < params.in_max, f"channel {index} input breakpoints"
        assert 0 <= params.out_low < params.out_mid < params.out_max, f"channel {index} output breakpoints"


def test_default_channel_params_match_published_table():
    expected = [
        (31.45, None, 17.30, 60.0, 2.40, 18.00),
        (25.50, None, 14.03, 100.0, 4.00, 30.00),
        (51.00, None, 28.05, 49.0, 1.96, 14.70),
        (25.50, None, 14.03, 12.0, 0.48, 3.60),
        (68.85, None, 37.87, 90.0, 3.60, 27.00),
        (68.85, None, 37.87, 90.0, 3.60, 27.00),
        (17.00, None, 9.35, 10.0, 0.40, 3.00),
        (68.85, None, 37.87, 90.0, 3.60, 27.00),
        (25.50, None, 14.03, 10.0, 0.40, 3.00),
        (85.00, None, 46.75, 90.0, 3.60, 27.00),
    ]
    for index, (params, want) in enumerate(zip(O10_DEFAULT_CHANNEL_PARAMS, expected)):
        in_max, _, in_mid, out_max, out_low, out_mid = want
        assert params.in_max == pytest.approx(in_max, abs=0.05), f"channel {index} in_max"
        assert params.in_mid == pytest.approx(in_mid, abs=0.05), f"channel {index} in_mid"
        assert params.out_max == pytest.approx(out_max, abs=0.05), f"channel {index} out_max"
        assert params.out_low == pytest.approx(out_low, abs=0.05), f"channel {index} out_low"
        assert params.out_mid == pytest.approx(out_mid, abs=0.05), f"channel {index} out_mid"


# ----- T2: piecewise curve -----

_SAMPLE_PARAMS = O10ChannelParams(
    in_max=68.85,
    in_low=6.0,
    in_mid=37.87,
    out_max=90.0,
    out_low=3.6,
    out_mid=27.0,
    dead_band=3.0,
)


def test_curve_at_breakpoints_returns_published_outputs():
    assert _o10_apply_curve(_SAMPLE_PARAMS, 0.0) == 0.0
    assert _o10_apply_curve(_SAMPLE_PARAMS, _SAMPLE_PARAMS.in_low) == pytest.approx(_SAMPLE_PARAMS.out_low)
    assert _o10_apply_curve(_SAMPLE_PARAMS, _SAMPLE_PARAMS.in_mid) == pytest.approx(_SAMPLE_PARAMS.out_mid)
    assert _o10_apply_curve(_SAMPLE_PARAMS, _SAMPLE_PARAMS.in_max) == pytest.approx(_SAMPLE_PARAMS.out_max)


def test_curve_segment_midpoints_interpolate_linearly():
    midpoint_low = _SAMPLE_PARAMS.in_low / 2
    expected_low = _SAMPLE_PARAMS.out_low / 2
    assert _o10_apply_curve(_SAMPLE_PARAMS, midpoint_low) == pytest.approx(expected_low)

    midpoint_mid = (_SAMPLE_PARAMS.in_low + _SAMPLE_PARAMS.in_mid) / 2
    expected_mid = (_SAMPLE_PARAMS.out_low + _SAMPLE_PARAMS.out_mid) / 2
    assert _o10_apply_curve(_SAMPLE_PARAMS, midpoint_mid) == pytest.approx(expected_mid)

    midpoint_high = (_SAMPLE_PARAMS.in_mid + _SAMPLE_PARAMS.in_max) / 2
    expected_high = (_SAMPLE_PARAMS.out_mid + _SAMPLE_PARAMS.out_max) / 2
    assert _o10_apply_curve(_SAMPLE_PARAMS, midpoint_high) == pytest.approx(expected_high)


def test_curve_saturates_above_in_max_and_clamps_negative_to_zero():
    assert _o10_apply_curve(_SAMPLE_PARAMS, _SAMPLE_PARAMS.in_max + 25) == _SAMPLE_PARAMS.out_max
    assert _o10_apply_curve(_SAMPLE_PARAMS, 1e6) == _SAMPLE_PARAMS.out_max
    assert _o10_apply_curve(_SAMPLE_PARAMS, -5.0) == 0.0


def test_curve_is_monotonic_non_decreasing_across_full_range():
    previous = -math.inf
    for x in range(0, int(_SAMPLE_PARAMS.in_max) * 2 + 5):
        current = _o10_apply_curve(_SAMPLE_PARAMS, float(x))
        assert current >= previous, f"non-monotonic at x={x}: {previous} -> {current}"
        previous = current


# ----- T3: mapper class with mirror + thumb roll offset -----


def test_map_returns_radians_with_correct_count():
    mapper = O10HandMapper(handedness="right")
    out = mapper.map([0.0] * 10)
    assert len(out) == 10
    assert all(isinstance(v, float) for v in out)


def test_map_input_length_validation():
    mapper = O10HandMapper(handedness="right")
    with pytest.raises(ValueError):
        mapper.map([0.0] * 5)


def test_map_unsupported_handedness_raises():
    with pytest.raises(ValueError):
        O10HandMapper(handedness="middle")


def test_map_mirrors_left_right_for_sign_flip_channels():
    left_mapper = O10HandMapper(handedness="left")
    right_mapper = O10HandMapper(handedness="right")
    glove = [0.0] * 10
    glove[1] = 20.0
    glove[3] = 18.0
    glove[6] = 12.0
    glove[8] = 22.0

    left_out = left_mapper.map(glove)
    right_out = right_mapper.map(glove)

    for ch in (1, 3, 6, 8):
        assert left_out[ch] == pytest.approx(-right_out[ch], abs=1e-9), f"channel {ch}"


def test_map_keeps_same_sign_for_pitch_channels():
    left_mapper = O10HandMapper(handedness="left")
    right_mapper = O10HandMapper(handedness="right")
    glove = [0.0] * 10
    glove[4] = 40.0
    glove[5] = 40.0
    glove[7] = 40.0
    glove[9] = 40.0

    left_out = left_mapper.map(glove)
    right_out = right_mapper.map(glove)

    for ch in (4, 5, 7, 9):
        assert left_out[ch] == pytest.approx(right_out[ch], abs=1e-9), f"channel {ch}"


def test_thumb_roll_offset_at_zero_input():
    left_mapper = O10HandMapper(handedness="left")
    right_mapper = O10HandMapper(handedness="right")
    left_out = left_mapper.map([0.0] * 10)
    right_out = right_mapper.map([0.0] * 10)
    # Channel 0: curve(0) = 0; left mirror=-1, right mirror=+1; offsets +10 / -10 deg.
    assert left_out[0] == pytest.approx(math.radians(10.0), abs=1e-9)
    assert right_out[0] == pytest.approx(math.radians(-10.0), abs=1e-9)


def test_thumb_roll_symmetric_around_zero_for_nonzero_input():
    left_mapper = O10HandMapper(handedness="left")
    right_mapper = O10HandMapper(handedness="right")
    glove = [0.0] * 10
    glove[0] = 25.0
    left_out = left_mapper.map(glove)
    right_out = right_mapper.map(glove)
    # left[0] = -curve(25) + 10; right[0] = +curve(25) - 10. Sum to 0.
    assert left_out[0] + right_out[0] == pytest.approx(0.0, abs=1e-9)


# ----- T4: EMA low-pass -----


def test_ema_alpha_one_bypasses_smoothing():
    mapper = O10HandMapper(
        handedness="right",
        ema_alpha=1.0,
        channel_overrides={"index_mp_pitch": {"dead_band": 0.0}},
    )
    glove = [0.0] * 10
    glove[4] = 30.0
    first = mapper.map(glove)[4]
    # Channel 4 curve(30) = 3.6 + (30-6)/(37.87-6) * (27 - 3.6) ≈ 21.22°
    assert first == pytest.approx(math.radians(21.22), abs=0.01)


def test_ema_default_alpha_smooths_step_input_below_steady_state():
    mapper = O10HandMapper(handedness="right")
    glove = [0.0] * 10
    glove[4] = 30.0
    first = mapper.map(glove)[4]

    bypass = O10HandMapper(handedness="right", ema_alpha=1.0)
    steady = bypass.map(glove)[4]

    assert first < steady, "first frame should be smoothed below steady state"
    assert first > 0.0, "smoothed output still moves on first frame"


def test_ema_converges_to_steady_state_after_many_frames():
    mapper = O10HandMapper(handedness="right")
    glove = [0.0] * 10
    glove[4] = 30.0
    last = 0.0
    for _ in range(50):
        last = mapper.map(glove)[4]

    bypass = O10HandMapper(handedness="right", ema_alpha=1.0)
    steady = bypass.map(glove)[4]
    assert last == pytest.approx(steady, abs=1e-6)


def test_ema_step_response_is_monotonic_increasing():
    mapper = O10HandMapper(handedness="right")
    glove = [0.0] * 10
    glove[4] = 30.0
    history = [mapper.map(glove)[4] for _ in range(8)]
    for previous, current in zip(history, history[1:]):
        assert current >= previous, f"non-monotonic step response: {history}"


def test_ema_state_is_per_channel_independent():
    mapper = O10HandMapper(handedness="right")
    glove_a = [0.0] * 10
    glove_a[4] = 30.0
    mapper.map(glove_a)  # warm channel 4 only

    glove_b = [0.0] * 10
    glove_b[5] = 30.0
    out = mapper.map(glove_b)  # channel 4 dropped to 0; channel 5 is fresh
    # Channel 5 first frame should match a fresh mapper's first frame on the same input.
    fresh = O10HandMapper(handedness="right")
    fresh_out = fresh.map(glove_b)
    assert out[5] == pytest.approx(fresh_out[5], abs=1e-9)


# ----- T5: hysteresis dead band -----


def test_hysteresis_zero_anchor_holds_output_at_zero_within_dead_band():
    mapper = O10HandMapper(handedness="right", ema_alpha=1.0)
    glove = [0.0] * 10
    glove[4] = 2.5  # within dead_band=3 of initial anchor=0
    assert mapper.map(glove)[4] == 0.0
    # Repeat — should stay at zero.
    glove[4] = 1.0
    assert mapper.map(glove)[4] == 0.0


def test_hysteresis_locks_output_to_anchor_for_perturbations_within_dead_band():
    mapper = O10HandMapper(handedness="right", ema_alpha=1.0)
    glove = [0.0] * 10
    glove[4] = 10.0
    # Frame 1: anchor jumps from 0 to 10-3=7
    locked_value = mapper.map(glove)[4]

    # Inputs within (anchor - dead_band, anchor + dead_band) = (4, 10) hold output.
    for nudge in (4.5, 5.5, 6.5, 7.0, 8.0, 9.5, 9.99):
        glove[4] = nudge
        assert mapper.map(glove)[4] == pytest.approx(locked_value, abs=1e-9), f"nudge={nudge}"


def test_hysteresis_anchor_follows_when_input_exceeds_dead_band():
    mapper = O10HandMapper(handedness="right", ema_alpha=1.0)
    glove = [0.0] * 10
    glove[4] = 10.0
    initial = mapper.map(glove)[4]
    # Push beyond dead_band of current anchor (which is 7)
    glove[4] = 20.0  # anchor moves to 17
    after = mapper.map(glove)[4]
    assert after > initial


def test_hysteresis_anchor_follows_descent_with_correct_offset():
    mapper = O10HandMapper(handedness="right", ema_alpha=1.0)
    glove = [0.0] * 10
    glove[4] = 30.0
    mapper.map(glove)  # anchor → 27
    high = mapper.map(glove)[4]  # holds at 27 (steady)

    glove[4] = 5.0  # |5-27| > dead_band; anchor → 5+3=8
    after = mapper.map(glove)[4]
    # curve(8) for channel 4 (in_low=6, in_mid=37.87, out_low=3.6, out_mid=27)
    expected = math.radians(3.6 + (8.0 - 6.0) / (37.87 - 6.0) * (27.0 - 3.6))
    assert after < high
    assert after == pytest.approx(expected, abs=0.01)


def test_hysteresis_steady_state_anchor_settles_one_dead_band_below_input():
    mapper = O10HandMapper(handedness="right", ema_alpha=1.0)
    glove = [0.0] * 10
    glove[4] = 30.0
    last = 0.0
    for _ in range(10):
        last = mapper.map(glove)[4]
    # anchor sits at 30 - dead_band = 27
    expected = math.radians(3.6 + (27.0 - 6.0) / (37.87 - 6.0) * (27.0 - 3.6))
    assert last == pytest.approx(expected, abs=0.01)


def test_reset_clears_state():
    mapper = O10HandMapper(handedness="right", ema_alpha=1.0)
    glove = [0.0] * 10
    glove[4] = 30.0
    for _ in range(5):
        mapper.map(glove)

    mapper.reset()
    glove[4] = 2.0  # within dead_band of zero
    # After reset, anchor is back to 0 → small input stays at zero.
    assert mapper.map(glove)[4] == 0.0


# ----- T6: channel independence + sanity vs old linear formula -----


def test_other_channels_unchanged_when_one_channel_oscillates():
    mapper = O10HandMapper(handedness="right")
    glove = [0.0] * 10
    glove[5] = 25.0
    baseline = mapper.map(glove)

    # Drive channel 4 hard while keeping others identical.
    glove[4] = 60.0
    mapper.map(glove)
    glove[4] = 0.0
    mapper.map(glove)
    glove[4] = 60.0
    mapper.map(glove)
    glove[4] = 0.0
    after_oscillation = mapper.map(glove)

    # Channels other than 4 should match the baseline trajectory's evolution exactly,
    # since the same input sequence (constant 0 / constant 25) was fed.
    fresh = O10HandMapper(handedness="right")
    fresh_glove = [0.0] * 10
    fresh_glove[5] = 25.0
    for _ in range(5):
        fresh_baseline = fresh.map(fresh_glove)

    for ch in range(10):
        if ch == 4:
            continue
        assert after_oscillation[ch] == pytest.approx(fresh_baseline[ch], abs=1e-9), (
            f"channel {ch} drifted due to channel 4 activity"
        )


def _legacy_linear_glove_to_robot_deg(handedness: str, channel: int, x_glove_deg: float) -> float:
    """Reproduces the deleted linear scaling for sanity comparison only."""
    glove_lim_right = (37.0, 30.0, 60.0, 30.0, 81.0, 81.0, 20.0, 81.0, 30.0, 100.0)
    robot_lim_right = (60.0, -100.0, 49.0, -12.0, 90.0, 90.0, 10.0, 90.0, 10.0, 90.0)
    robot_lim_left = (-60.0, 100.0, -49.0, 12.0, 90.0, 90.0, -10.0, 90.0, -10.0, 90.0)
    glove_limits = glove_lim_right
    robot_limits = robot_lim_right if handedness == "right" else robot_lim_left
    thumb_offset = -10.0 if handedness == "right" else 10.0
    clamped = min(abs(x_glove_deg), glove_limits[channel])
    out = clamped / glove_limits[channel] * robot_limits[channel]
    if channel == 0:
        out += thumb_offset
    return out


def test_new_mapping_matches_legacy_direction_at_full_close():
    """At full-close glove input, new mapping should land at out_max (full robot
    closure), with the same sign as the legacy linear formula."""
    mapper = O10HandMapper(handedness="right", ema_alpha=1.0)
    glove = [40.0, 30.0, 60.0, 30.0, 81.0, 81.0, 20.0, 81.0, 30.0, 100.0]

    new_out = mapper.map(glove)
    new_out = mapper.map(glove)  # second frame to settle hysteresis

    for ch in range(10):
        legacy = _legacy_linear_glove_to_robot_deg("right", ch, glove[ch])
        new_deg = math.degrees(new_out[ch])
        assert math.copysign(1, new_deg) == math.copysign(1, legacy), f"channel {ch} sign flip"
        # New mapping at full glove input must reach saturation (|new| ≈ |out_max|).
        out_max_abs = abs((60.0, -100.0, 49.0, -12.0, 90.0, 90.0, 10.0, 90.0, 10.0, 90.0)[ch])
        if ch == 0:
            # Thumb roll has the offset baked in
            assert abs(new_deg + 10.0) == pytest.approx(out_max_abs, abs=0.5), f"channel {ch} not saturating"
        else:
            assert abs(new_deg) == pytest.approx(out_max_abs, abs=0.5), f"channel {ch} not saturating"


def test_new_mapping_softer_in_mid_steeper_in_end_vs_legacy():
    """Concrete hand-feel target: the new convex curve should be softer than legacy
    in the mid range (so middle position holds steady) and steeper than legacy near
    full close (so the end-stop is reachable). Verify on pitch channels."""
    mapper_mid = O10HandMapper(handedness="right", ema_alpha=1.0)
    mapper_high = O10HandMapper(handedness="right", ema_alpha=1.0)
    glove_lim = (37.0, 30.0, 60.0, 30.0, 81.0, 81.0, 20.0, 81.0, 30.0, 100.0)
    glove_mid = [0.50 * lim for lim in glove_lim]
    glove_high = [0.90 * lim for lim in glove_lim]

    out_mid = mapper_mid.map(glove_mid)
    for _ in range(10):
        out_mid = mapper_mid.map(glove_mid)  # settle hysteresis

    out_high = mapper_high.map(glove_high)
    for _ in range(10):
        out_high = mapper_high.map(glove_high)

    for ch in (4, 5, 7, 9):
        legacy_mid = _legacy_linear_glove_to_robot_deg("right", ch, glove_mid[ch])
        legacy_high = _legacy_linear_glove_to_robot_deg("right", ch, glove_high[ch])
        new_mid = math.degrees(out_mid[ch])
        new_high = math.degrees(out_high[ch])
        assert abs(new_mid) < abs(legacy_mid), (
            f"channel {ch}: new mid {new_mid} should be softer than legacy mid {legacy_mid}"
        )
        assert abs(new_high) > abs(legacy_high), (
            f"channel {ch}: new high {new_high} should be steeper than legacy high {legacy_high}"
        )


def test_channel_overrides_apply_to_named_channel_only():
    mapper = O10HandMapper(
        handedness="right",
        channel_overrides={"index_mp_pitch": {"in_max": 40.0}},
    )
    assert mapper.params[4].in_max == 40.0
    # Other channels unchanged
    assert mapper.params[5].in_max == O10_DEFAULT_CHANNEL_PARAMS[5].in_max
