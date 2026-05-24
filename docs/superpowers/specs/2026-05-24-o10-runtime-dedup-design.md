# O10 runtime helper deduplication design

Date: 2026-05-24
Status: Design approved; pending written spec review
Owner: phl

## Problem

The AGIBOT O10 runtime support in vendored `lerobot_play` has grown in two parallel
directions: single-arm classes and dual-arm classes. The follower and leader code now
duplicates several behavior-sensitive blocks:

- O10 action/state/tactile feature names and feature specs.
- Camera color/depth read fallback, cached-frame reuse, zero-frame creation, and recovery logs.
- Reset pose loading and normalized in-memory reset target handling.
- End-effector delta math, IK failure handling, and 4x4 pose to 7D pose conversion.
- Gripper 1D to 10D hand joint conversion and trigger-gesture open/closed pose lookup.

The duplication makes future changes risky because a fix in single-arm code can be missed
in dual-arm code, and vice versa. The current request is intentionally conservative:
reduce duplication without changing runtime behavior, YAML fields, hardware lifecycle, or
dataset schema.

## Goals

- Extract shared O10 helper modules under
  `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/`.
- Keep the existing O10 single-arm and dual-arm follower/leader classes as orchestration
  layers that own hardware objects, side-specific state, and action sending.
- Preserve all public config fields, command entrypoints, action keys, observation keys,
  tactile keys, and dataset feature ordering.
- Add focused pure-Python regression tests before and during refactoring so the helpers
  are locked to current behavior.
- Use the local vendored `lerobot_play` style; do not migrate the project to the newer
  upstream LeRobot package layout in this change.

## Non-goals

- No YAML migration or command-line flag changes.
- No dataset schema changes.
- No hardware connection lifecycle rewrite for arms, hands, cameras, Pico WebRTC, or glove
  threads.
- No conversion to a new shared base class or mixin hierarchy in this first pass.
- No vendored OmniHand SDK or `yudie/` runtime changes.
- No broad cleanup in `record.py`, `infer.py`, `control.py`, or unrelated LeRobot helpers.

## Design

### 1. Helper module boundaries

Add small helper modules that keep behavior-specific logic close to the O10 domain:

- `utils/o10_motion.py`
  - `rotation_matrix_from_rpy(roll, pitch, yaw)`.
  - `apply_eef_delta_to_pose(current_pose, eef_delta)`.
  - `solve_o10_ik(arm_kdl, target_pose, seed_joints)`.
  - `homogeneous_matrix_to_pose(matrix)`.
  - Preserve the current IK compatibility path: try
    `inverse_kinematics(..., force_calculate=True)` first, then fall back to the older
    signature on `TypeError`. Empty IK results still raise `RuntimeError`.

- `utils/o10_camera_io.py`
  - `CameraObservationReader` owns per-camera cached frames and fallback-active flags.
  - Exposes `read(camera_name, camera)` returning `(color_frame, depth_frame_or_none)`.
  - Exposes `features(camera_names, camera_configs)` or equivalent helpers for color/depth
    feature shapes.
  - Keeps camera creation and connection in the follower classes. The helper only handles
    read-time behavior after cameras exist.

- `utils/o10_schema.py`
  - Centralizes single-arm and dual-arm feature name construction.
  - Provides tactile raw keys and tactile feature specs for `none` and `130d` modes.
  - Keeps existing names such as `left.joint1.pos`,
    `observation.tactile.left_raw`, and `observation.tactile.right_raw`.

- `utils/o10_hand_control.py`
  - Wraps gripper value to hand joints and hand joints to gripper value.
  - Wraps trigger gesture open/closed lookup, including reset-pose JSON overrides.
  - Delegates to existing `agibot_o10` functions so the source of gesture constants remains
    stable.

- `utils/o10_reset.py`
  - Adds small reset-loading helpers for `load_reset_poses(...)` plus normalization through
    `PersistentJointTargetStore`.
  - Does not write `configs/reset_poses/o10_dual_reset.json` at runtime.
  - Keeps follower/leader classes responsible for assigning reset values to their own
    side-specific fields.

These helpers are intentionally functions or small state holders, not framework-level
base classes. This keeps the refactor reversible and avoids touching MRO, hardware
construction, or connection sequencing.

### 2. Follower class changes

`PicoFollowerSingleArmAgibotO10` and `PicoFollowerDualArmAgibotO10` keep ownership of:

- `ah.Play` arm objects and executor/io-context objects.
- `AgibotO10Hand` objects.
- Camera creation and connection.
- Per-side current hand joint caches.
- `send_action(...)`, `get_observation(...)`, `connect(...)`, and `disconnect(...)`
  orchestration.

They delegate shared logic as follows:

- Camera read fallback moves to `CameraObservationReader`.
- Feature names and tactile specs come from `o10_schema.py`.
- EEF delta action conversion uses `o10_motion.py`.
- Gripper conversions use `o10_hand_control.py`.
- Reset pose loading uses `o10_reset.py` where doing so does not obscure the per-side state
  assignments.

### 3. Leader class changes

`PicoLeaderSingleArmAgibotO10` and `PicoLeaderDualArmAgibotO10` keep ownership of:

- Pico event thread startup and control-state dictionaries.
- Per-side LPFs, IK histories, transform poses, and start/reset flags.
- Glove teleoperator objects and trigger-gate decisions.
- `get_action(...)`, `reset_pose(...)`, and hand-commanded-state locks.

They delegate shared logic as follows:

- Action feature selection and feature name lists come from `o10_schema.py`.
- EEF delta computation uses `o10_motion.py` helpers where the current and previous pose
  math is identical.
- Trigger gesture hand pose lookup and gripper interpolation use `o10_hand_control.py`.
- Reset pose file loading uses `o10_reset.py` while side-specific assignment remains local.

### 4. Data flow

The runtime data flow does not change:

1. Teleoperator produces an action dict according to `action_control_mode` and
   `hand_action_mode`.
2. Follower converts that action into arm joints plus 10D hand joints.
3. Follower sends arm PVT targets and hand joint targets to existing hardware adapters.
4. Follower returns observations with the same action/state/tactile/image schema as before.

Helpers only participate in conversion, schema construction, pose math, reset loading, and
camera frame fallback. They do not directly send CAN commands, start threads, or connect
devices.

## Error Handling

The refactor should preserve current behavior:

- IK failure still raises `RuntimeError` and refuses to send an arm target.
- Invalid action lengths still raise `ValueError` with clear expected/got dimensions.
- Camera read failures still follow `allow_camera_read_failures`:
  - false: re-raise the camera exception.
  - true with cache: reuse the last frame.
  - true without cache: create a zero color frame and optional zero depth frame.
- Camera recovery should log once when a previously failing camera succeeds again.
- Reset pose load failures still warn and fall back to the current in-memory/default state.
- Trigger gesture lookup still prefers reset-pose JSON values and then built-in gesture
  constants.

## Testing

Add focused tests under `qiuzhi/tests/`:

- `test_o10_motion_helpers.py`
  - RPY rotation matrix shape and identity case.
  - EEF delta translation and rotation application.
  - IK helper accepts the current `force_calculate=True` signature and the fallback
    signature.
  - Empty IK result raises `RuntimeError`.
  - 4x4 pose conversion returns 7 values and rejects non-4x4 input.

- `test_o10_camera_io.py`
  - Color-only camera read stores cache.
  - Color+depth camera read returns expanded depth via caller-compatible data.
  - Read failure re-raises when fallback is disabled.
  - Read failure reuses cached frames when fallback is enabled.
  - First read failure with no cache creates zero frames with configured dimensions.
  - Recovery clears fallback-active state.

- `test_o10_schema.py`
  - Single-arm action/state feature ordering matches existing `agibot_o10` constants.
  - Dual-arm action/state feature ordering matches current dual-arm constants.
  - Tactile raw key names and 130D feature specs match current behavior.

- `test_o10_hand_control.py`
  - Gripper 1D round trips through current gesture helpers.
  - Trigger gesture open/closed values match existing built-ins.
  - Reset-pose JSON gesture overrides remain preferred.

Run these alongside existing O10 regression tests:

```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest \
  qiuzhi/tests/test_agibot_o10.py \
  qiuzhi/tests/test_dual_arm_o10_trigger_gate.py \
  qiuzhi/tests/test_o10_camera_observation_fallback.py \
  qiuzhi/tests/test_dual_arm_tactile_schema.py \
  qiuzhi/tests/test_o10_tactile_raw_dataset_schema.py
```

Before claiming completion, run the new helper tests plus the broader O10-related tests
that cover any follower or leader files touched.

## Rollout

Implement in small commits or reviewable patches:

1. Add helper modules and tests while existing classes still use old local functions where
   practical.
2. Move single-arm follower call sites to helpers.
3. Move dual-arm follower call sites to helpers.
4. Move single-arm and dual-arm leader call sites to helpers.
5. Remove duplicated private functions/constants only after tests prove the helper-backed
   paths match current behavior.

The first implementation pass should prefer duplication removal with minimal reshaping.
If a helper starts needing many callbacks into a runtime class, leave that code local and
document it as a future extraction candidate.

## Risks

- Feature ordering regressions can silently break dataset compatibility. Schema tests must
  compare exact ordered key sequences.
- Camera fallback is stateful. Moving cache/fallback flags into a helper must preserve one
  reader instance per follower, not a shared global.
- Dual-arm side prefixes are easy to swap. Tests should check both left and right keys and
  trigger gesture behavior.
- Moving reset helpers too aggressively could hide side-specific assignment. Keep state
  assignment in runtime classes for this first pass.

## Success Criteria

- O10 single-arm and dual-arm runtime classes are shorter and contain less repeated helper
  logic.
- Public action/observation/tactile/image keys are unchanged.
- Existing O10 tests continue to pass.
- New helper tests cover the extracted behavior without CAN hardware, cameras, Pico, or
  glove services.
- No unrelated files or vendor artifacts are reformatted.
