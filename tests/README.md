# Tests

This directory contains root-level regression tests and a few manual hardware
diagnostics for the O10 arm-hand teleoperation workspace.

## Run the normal tests

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests
```

These tests should not require CAN hardware, cameras, or RealSense devices.

## Wrist camera exposure diagnostic

`test_wrist_camera_exposure_debug.py` checks whether a wrist RealSense camera is
still over-exposed after applying shared O10 camera controls from
`configs/cameras/o10_cameras.yaml`. It
opens one wrist camera, applies `auto_exposure`, `exposure_us`, and `gain`, reads
frames, and prints brightness statistics:

- `Mean luma`: average image brightness.
- `P95 luma`: 95th percentile brightness.
- `Max luma`: brightest observed pixel.
- `Saturated ratio`: fraction of pixels at or above the saturation threshold.

The hardware test is skipped by default. Run it explicitly:

```bash
WRIST_CAMERA_EXPOSURE_HARDWARE=1 pytest tests/test_wrist_camera_exposure_debug.py -s
```

Useful overrides:

```bash
WRIST_CAMERA_EXPOSURE_HARDWARE=1 \
WRIST_CAMERA_CONFIG=configs/dual_arm/o10_dual_record.yaml \
WRIST_CAMERA_NAME=right_wrist \
WRIST_CAMERA_SAMPLES=30 \
WRIST_CAMERA_MAX_SATURATED_RATIO=0.02 \
WRIST_CAMERA_SAVE_DIR=/tmp/wrist_exposure \
pytest tests/test_wrist_camera_exposure_debug.py -s
```

If the test fails, lower the matching camera controls in the config, usually
`camera_controls.<camera>.exposure_us` first and `gain` second. For the current
right wrist config, edit `configs/cameras/o10_cameras.yaml`:

```yaml
camera_controls:
  right_wrist:
    auto_exposure: false
    exposure_us: 14000
    gain: 16
```

For left wrist diagnostics, add or adjust `camera_controls.left_wrist` and
run with `WRIST_CAMERA_NAME=left_wrist`.

## Other manual hardware tests

- `test_eef_delta_arm_control.py`: dry-run or real-arm EEF delta smoke test.
  Use `python tests/test_eef_delta_arm_control.py --help`.
- `test_eef_absolute_pose_arm_control.py`: dry-run or real-arm absolute EEF pose
  smoke test. Use `python tests/test_eef_absolute_pose_arm_control.py --help`.
- `AGIBOT/test_pinch_grasp.py`: manual CAN/O10 pinch grasp check; run directly
  when testing the hand hardware.
