# O10 Runtime Helper Dedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 AGIBOT O10 单臂/双臂 follower/leader 中重复的 motion、camera、schema、hand-control、reset 逻辑抽成共享 helper，同时保持现有 runtime 行为和数据 schema 不变。

**Architecture:** 第一阶段只抽纯 helper 和小状态对象，不引入 base class/mixin，不改硬件连接生命周期。先用纯 Python 测试锁住 helper 行为，再分批把单臂 follower、双臂 follower、leader 调用点切到 helper。

**Tech Stack:** Python 3, pytest, numpy, vendored `lerobot_play`, existing O10 tests under `qiuzhi/tests/`.

**Spec:** [docs/superpowers/specs/2026-05-24-o10-runtime-dedup-design.md](../specs/2026-05-24-o10-runtime-dedup-design.md)

**Dirty worktree notice:** 计划编写时，`README.md`、多份 `configs/`、`qiuzhi/.../record.py`、O10 follower/config、image writer 和若干测试已经有未提交改动。执行本计划时不要 revert 或覆盖这些改动；每个任务提交前只 stage 本任务实际修改的文件。

---

## File Structure

Create:

- `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/o10_motion.py`  
  O10 pose math, eef_delta application, IK compatibility wrapper, 4x4 pose to 7D pose conversion, rotation matrix to RPY conversion.
- `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/o10_camera_io.py`  
  Camera read fallback state, cached frames, zero frames, camera feature shapes, parallel read helper.
- `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/o10_schema.py`  
  Single/dual action and state feature names, tactile feature names/specs, tactile raw keys.
- `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/o10_hand_control.py`  
  Gripper 1D/10D conversion and trigger gesture lookup wrappers.
- `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/o10_reset.py`  
  Reset pose loading and normalized value helpers.
- `qiuzhi/tests/test_o10_motion_helpers.py`
- `qiuzhi/tests/test_o10_camera_io.py`
- `qiuzhi/tests/test_o10_schema.py`
- `qiuzhi/tests/test_o10_hand_control.py`
- `qiuzhi/tests/test_o10_reset_helpers.py`

Modify:

- `qiuzhi/.../lerobot_play/robots/pico_follower_single_arm_agibot_o10/airbot_pico_follower_single_arm_agibot_o10.py`
- `qiuzhi/.../lerobot_play/robots/pico_follower_dual_arm_agibot_o10/airbot_pico_follower_dual_arm_agibot_o10.py`
- `qiuzhi/.../lerobot_play/teleoperators/pico_leader_single_arm_agibot_o10/pico_leader_single_arm_agibot_o10.py`
- `qiuzhi/.../lerobot_play/teleoperators/pico_leader_dual_arm_agibot_o10/pico_leader_dual_arm_agibot_o10.py`
- Source-based tests may need updating if constants move:
  - `qiuzhi/tests/test_dual_arm_tactile_schema.py`
  - `qiuzhi/tests/test_o10_camera_observation_fallback.py`

---

### Task 1: Baseline and Worktree Guard

**Files:**
- No code changes.

- [ ] **Step 1: Capture dirty worktree state**

Run:
```bash
git status --short --branch
```
Expected: branch `task/express-sorting` and possibly existing modified files. Do not clean or reset them.

- [ ] **Step 2: Run current focused O10 baseline**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest \
  qiuzhi/tests/test_agibot_o10.py \
  qiuzhi/tests/test_dual_arm_o10_trigger_gate.py \
  qiuzhi/tests/test_o10_camera_observation_fallback.py \
  qiuzhi/tests/test_dual_arm_tactile_schema.py \
  qiuzhi/tests/test_o10_tactile_raw_dataset_schema.py -q
```
Expected: PASS. If tests fail because of pre-existing dirty changes, record the failing test names and failure summary in the task notes before touching files.

- [ ] **Step 3: Confirm helper modules do not already exist**

Run:
```bash
ls qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/o10_*.py
```
Expected: either no matches or only files intentionally created by a previous partial run. If files exist, inspect them and continue from the first incomplete task instead of recreating them.

---

### Task 2: Motion Helper

**Files:**
- Create: `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/o10_motion.py`
- Create: `qiuzhi/tests/test_o10_motion_helpers.py`
- Later modify callers in Tasks 7-10.

- [ ] **Step 1: Write failing tests**

Create `qiuzhi/tests/test_o10_motion_helpers.py`:
```python
import sys
from pathlib import Path

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))


def test_rotation_matrix_from_rpy_identity():
    from lerobot_play.utils.o10_motion import rotation_matrix_from_rpy

    assert np.allclose(rotation_matrix_from_rpy(0.0, 0.0, 0.0), np.eye(3))


def test_rpy_from_rotation_matrix_extracts_yaw():
    from lerobot_play.utils.o10_motion import rotation_matrix_from_rpy, rpy_from_rotation_matrix

    rotation = rotation_matrix_from_rpy(0.0, 0.0, 0.25)

    assert rpy_from_rotation_matrix(rotation) == pytest.approx([0.0, 0.0, 0.25])


def test_apply_eef_delta_to_pose_translates_and_rotates():
    from lerobot_play.utils.o10_motion import apply_eef_delta_to_pose

    current_pose = np.eye(4)
    target_pose = apply_eef_delta_to_pose(current_pose, [1.0, 2.0, 3.0, 0.0, 0.0, np.pi / 2])

    assert np.allclose(target_pose[:3, 3], [1.0, 2.0, 3.0])
    assert np.allclose(
        target_pose[:3, :3],
        np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]),
        atol=1e-7,
    )


def test_solve_o10_ik_uses_force_calculate_signature():
    from lerobot_play.utils.o10_motion import solve_o10_ik

    class FakeKdl:
        def __init__(self):
            self.force_calculate = None

        def inverse_kinematics(self, target_pose, seed_joints, force_calculate=False):
            self.force_calculate = force_calculate
            return [[1, 2, 3, 4, 5, 6, 99]]

    kdl = FakeKdl()
    assert solve_o10_ik(kdl, np.eye(4), [0.0] * 6) == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert kdl.force_calculate is True


def test_solve_o10_ik_falls_back_to_old_signature():
    from lerobot_play.utils.o10_motion import solve_o10_ik

    class FakeKdl:
        def inverse_kinematics(self, target_pose, seed_joints, force_calculate=False):
            if force_calculate is not False:
                raise TypeError("old signature")
            return [[6, 5, 4, 3, 2, 1]]

    assert solve_o10_ik(FakeKdl(), np.eye(4), [0.0] * 6) == [6.0, 5.0, 4.0, 3.0, 2.0, 1.0]


def test_solve_o10_ik_rejects_empty_result():
    from lerobot_play.utils.o10_motion import solve_o10_ik

    class FakeKdl:
        def inverse_kinematics(self, target_pose, seed_joints, force_calculate=False):
            return []

    with pytest.raises(RuntimeError, match="eef_delta IK failed"):
        solve_o10_ik(FakeKdl(), np.eye(4), [0.0] * 6)


def test_homogeneous_matrix_to_pose_returns_position_and_quaternion():
    from lerobot_play.utils.o10_motion import homogeneous_matrix_to_pose

    matrix = np.eye(4)
    matrix[:3, 3] = [0.1, 0.2, 0.3]

    assert homogeneous_matrix_to_pose(matrix).tolist() == pytest.approx(
        [0.1, 0.2, 0.3, 0.0, 0.0, 0.0, 1.0]
    )


def test_homogeneous_matrix_to_pose_rejects_non_4x4():
    from lerobot_play.utils.o10_motion import homogeneous_matrix_to_pose

    with pytest.raises(ValueError, match="4x4"):
        homogeneous_matrix_to_pose(np.eye(3))
```

- [ ] **Step 2: Run tests and confirm missing module failure**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_o10_motion_helpers.py -q
```
Expected: FAIL with `ModuleNotFoundError: No module named 'lerobot_play.utils.o10_motion'`.

- [ ] **Step 3: Implement motion helper**

Create `qiuzhi/.../lerobot_play/utils/o10_motion.py`:
```python
from __future__ import annotations

import numpy as np


NUM_O10_ARM_JOINTS = 6


def rotation_matrix_from_rpy(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr, sr = np.cos(roll), np.sin(roll)
    cp, sp = np.cos(pitch), np.sin(pitch)
    cy, sy = np.cos(yaw), np.sin(yaw)
    return np.array(
        [
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr],
        ],
        dtype=float,
    )


def rpy_from_rotation_matrix(rotation: np.ndarray) -> list[float]:
    sy = np.sqrt(rotation[0, 0] * rotation[0, 0] + rotation[1, 0] * rotation[1, 0])
    singular = sy < 1e-6
    if not singular:
        roll = np.arctan2(rotation[2, 1], rotation[2, 2])
        pitch = np.arctan2(-rotation[2, 0], sy)
        yaw = np.arctan2(rotation[1, 0], rotation[0, 0])
    else:
        roll = np.arctan2(-rotation[1, 2], rotation[1, 1])
        pitch = np.arctan2(-rotation[2, 0], sy)
        yaw = 0.0
    return [float(roll), float(pitch), float(yaw)]


def apply_eef_delta_to_pose(current_pose: np.ndarray, eef_delta: list[float]) -> np.ndarray:
    target_pose = np.array(current_pose, dtype=float, copy=True)
    target_pose[:3, 3] += np.array(eef_delta[:3], dtype=float)
    target_pose[:3, :3] = target_pose[:3, :3] @ rotation_matrix_from_rpy(*eef_delta[3:6])
    return target_pose


def solve_o10_ik(
    arm_kdl,
    target_pose: np.ndarray,
    seed_joints: list[float],
    *,
    num_arm_joints: int = NUM_O10_ARM_JOINTS,
) -> list[float]:
    try:
        result = arm_kdl.inverse_kinematics(target_pose, seed_joints, force_calculate=True)
    except TypeError:
        result = arm_kdl.inverse_kinematics(target_pose, seed_joints)
    if len(result) == 0:
        raise RuntimeError("Agibot O10 eef_delta IK failed; refusing to send an arm target.")
    return [float(value) for value in result[0][:num_arm_joints]]


def homogeneous_matrix_to_pose(matrix) -> np.ndarray:
    matrix = np.array(matrix)
    if matrix.shape != (4, 4):
        raise ValueError("输入必须是4x4矩阵")

    position = matrix[:3, 3].flatten()
    rotation_matrix = matrix[:3, :3]
    quaternion = rotation_matrix_to_quaternion(rotation_matrix)
    return np.concatenate([position, quaternion])


def rotation_matrix_to_quaternion(rotation: np.ndarray) -> np.ndarray:
    if not np.allclose(np.dot(rotation, rotation.T), np.eye(3), atol=1e-8):
        raise ValueError("旋转矩阵不满足正交条件")

    quaternion = np.zeros(4)
    trace = np.trace(rotation)

    if trace > 0:
        scalar = np.sqrt(trace + 1.0) * 2
        quaternion[3] = 0.25 * scalar
        quaternion[0] = (rotation[2, 1] - rotation[1, 2]) / scalar
        quaternion[1] = (rotation[0, 2] - rotation[2, 0]) / scalar
        quaternion[2] = (rotation[1, 0] - rotation[0, 1]) / scalar
    elif (rotation[0, 0] > rotation[1, 1]) and (rotation[0, 0] > rotation[2, 2]):
        scalar = np.sqrt(1.0 + rotation[0, 0] - rotation[1, 1] - rotation[2, 2]) * 2
        quaternion[3] = (rotation[2, 1] - rotation[1, 2]) / scalar
        quaternion[0] = 0.25 * scalar
        quaternion[1] = (rotation[0, 1] + rotation[1, 0]) / scalar
        quaternion[2] = (rotation[0, 2] + rotation[2, 0]) / scalar
    elif rotation[1, 1] > rotation[2, 2]:
        scalar = np.sqrt(1.0 + rotation[1, 1] - rotation[0, 0] - rotation[2, 2]) * 2
        quaternion[3] = (rotation[0, 2] - rotation[2, 0]) / scalar
        quaternion[0] = (rotation[0, 1] + rotation[1, 0]) / scalar
        quaternion[1] = 0.25 * scalar
        quaternion[2] = (rotation[1, 2] + rotation[2, 1]) / scalar
    else:
        scalar = np.sqrt(1.0 + rotation[2, 2] - rotation[0, 0] - rotation[1, 1]) * 2
        quaternion[3] = (rotation[1, 0] - rotation[0, 1]) / scalar
        quaternion[0] = (rotation[0, 2] + rotation[2, 0]) / scalar
        quaternion[1] = (rotation[1, 2] + rotation[2, 1]) / scalar
        quaternion[2] = 0.25 * scalar

    return quaternion / np.linalg.norm(quaternion)
```

- [ ] **Step 4: Run motion tests**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_o10_motion_helpers.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit motion helper**

```bash
git add \
  qiuzhi/tests/test_o10_motion_helpers.py \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/o10_motion.py
git commit -m "heliangp:add O10 motion helper"
```
Expected: commit includes only the new test and helper file.

---

### Task 3: Camera IO Helper

**Files:**
- Create: `qiuzhi/.../lerobot_play/utils/o10_camera_io.py`
- Create: `qiuzhi/tests/test_o10_camera_io.py`
- Later modify O10 follower callers in Tasks 7-8.

- [ ] **Step 1: Write failing tests**

Create `qiuzhi/tests/test_o10_camera_io.py`:
```python
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))


class FakeColorCamera:
    def __init__(self, frame, failures=0):
        self.frame = frame
        self.failures = failures

    def async_read(self, timeout_ms):
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("read failed")
        return self.frame


class FakeDepthCamera:
    def __init__(self, color, depth, failures=0):
        self.color = color
        self.depth = depth
        self.failures = failures

    def async_read_color_and_depth(self, timeout_ms):
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("depth failed")
        return self.color, self.depth


def _config(width=4, height=3, use_depth=False):
    return SimpleNamespace(width=width, height=height, use_depth=use_depth)


def test_color_read_stores_cache():
    from lerobot_play.utils.o10_camera_io import CameraObservationReader

    frame = np.ones((3, 4, 3), dtype=np.uint8)
    reader = CameraObservationReader(
        camera_configs={"top": _config()},
        allow_read_failures=False,
        timeout_ms=123,
    )

    assert reader.read("top", FakeColorCamera(frame)) == (frame, None)
    assert reader.cache["top"][0] is frame


def test_depth_read_stores_color_and_depth():
    from lerobot_play.utils.o10_camera_io import CameraObservationReader

    color = np.ones((3, 4, 3), dtype=np.uint8)
    depth = np.ones((3, 4), dtype=np.uint16) * 7
    reader = CameraObservationReader(
        camera_configs={"wrist": _config(use_depth=True)},
        allow_read_failures=False,
        timeout_ms=200,
    )

    assert reader.read("wrist", FakeDepthCamera(color, depth)) == (color, depth)


def test_failure_reraises_when_fallback_disabled():
    from lerobot_play.utils.o10_camera_io import CameraObservationReader

    reader = CameraObservationReader(
        camera_configs={"top": _config()},
        allow_read_failures=False,
        timeout_ms=200,
    )

    with pytest.raises(RuntimeError, match="read failed"):
        reader.read("top", FakeColorCamera(np.zeros((3, 4, 3), dtype=np.uint8), failures=1))


def test_failure_reuses_cache_when_fallback_enabled(caplog):
    from lerobot_play.utils.o10_camera_io import CameraObservationReader

    cached = np.ones((3, 4, 3), dtype=np.uint8)
    reader = CameraObservationReader(
        camera_configs={"top": _config()},
        allow_read_failures=True,
        timeout_ms=200,
    )
    reader.cache["top"] = (cached, None)

    with caplog.at_level(logging.WARNING):
        assert reader.read("top", FakeColorCamera(np.zeros((3, 4, 3), dtype=np.uint8), failures=1)) == (cached, None)

    assert "reusing last frame" in caplog.text


def test_failure_without_cache_uses_zero_frame():
    from lerobot_play.utils.o10_camera_io import CameraObservationReader

    reader = CameraObservationReader(
        camera_configs={"wrist": _config(width=5, height=2, use_depth=True)},
        allow_read_failures=True,
        timeout_ms=200,
    )

    color, depth = reader.read(
        "wrist",
        FakeDepthCamera(
            np.ones((2, 5, 3), dtype=np.uint8),
            np.ones((2, 5), dtype=np.uint16),
            failures=1,
        ),
    )

    assert color.shape == (2, 5, 3)
    assert color.dtype == np.uint8
    assert np.all(color == 0)
    assert depth.shape == (2, 5)
    assert depth.dtype == np.uint16
    assert np.all(depth == 0)


def test_recovery_clears_fallback_state(caplog):
    from lerobot_play.utils.o10_camera_io import CameraObservationReader

    frame = np.ones((3, 4, 3), dtype=np.uint8)
    reader = CameraObservationReader(
        camera_configs={"top": _config()},
        allow_read_failures=True,
        timeout_ms=200,
    )
    reader.read("top", FakeColorCamera(frame, failures=1))
    assert reader.fallback_active["top"] is True

    with caplog.at_level(logging.INFO):
        reader.read("top", FakeColorCamera(frame))

    assert "Camera top recovered." in caplog.text
    assert "top" not in reader.fallback_active


def test_camera_feature_shapes_include_depth_key():
    from lerobot_play.utils.o10_camera_io import camera_feature_shapes

    assert camera_feature_shapes(
        ["top", "wrist"],
        {"top": _config(), "wrist": _config(use_depth=True)},
    ) == {
        "top": (3, 4, 3),
        "wrist": (3, 4, 3),
        "wrist_depth": (3, 4, 1),
    }
```

- [ ] **Step 2: Run tests and confirm missing module failure**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_o10_camera_io.py -q
```
Expected: FAIL with missing `lerobot_play.utils.o10_camera_io`.

- [ ] **Step 3: Implement camera helper**

Create `qiuzhi/.../lerobot_play/utils/o10_camera_io.py`:
```python
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable

import numpy as np


logger = logging.getLogger(__name__)


def camera_uses_depth(camera_config: Any) -> bool:
    return bool(getattr(camera_config, "use_depth", False))


def depth_observation_name(camera_name: str) -> str:
    return f"{camera_name}_depth"


def camera_feature_shapes(
    camera_names: Iterable[str],
    camera_configs: dict[str, Any],
) -> dict[str, tuple[int, int, int]]:
    camera_features: dict[str, tuple[int, int, int]] = {}
    for camera_name in camera_names:
        camera_config = camera_configs[camera_name]
        camera_features[camera_name] = (
            camera_config.height,
            camera_config.width,
            3,
        )
        if camera_uses_depth(camera_config):
            camera_features[depth_observation_name(camera_name)] = (
                camera_config.height,
                camera_config.width,
                1,
            )
    return camera_features


class CameraObservationReader:
    def __init__(
        self,
        camera_configs: dict[str, Any],
        *,
        allow_read_failures: bool,
        timeout_ms: int,
    ) -> None:
        self.camera_configs = camera_configs
        self.allow_read_failures = bool(allow_read_failures)
        self.timeout_ms = int(timeout_ms)
        self.cache: dict[str, tuple[np.ndarray, np.ndarray | None]] = {}
        self.fallback_active: dict[str, bool] = {}

    def read(self, camera_name: str, camera: Any) -> tuple[np.ndarray, np.ndarray | None]:
        uses_depth = camera_uses_depth(self.camera_configs[camera_name])
        try:
            if uses_depth:
                color_frame, depth_frame = camera.async_read_color_and_depth(timeout_ms=self.timeout_ms)
                self.cache[camera_name] = (color_frame, depth_frame)
                self._mark_success(camera_name)
                return color_frame, depth_frame

            color_frame = camera.async_read(timeout_ms=self.timeout_ms)
            self.cache[camera_name] = (color_frame, None)
            self._mark_success(camera_name)
            return color_frame, None
        except Exception as exc:
            if not self.allow_read_failures:
                raise

            cached_frames = self.cache.get(camera_name)
            if cached_frames is not None:
                self._mark_failure(camera_name, exc, using_cached_frame=True)
                return cached_frames

            zero_color_frame = self.zero_color_frame(camera_name)
            zero_depth_frame = self.zero_depth_frame(camera_name) if uses_depth else None
            self.cache[camera_name] = (zero_color_frame, zero_depth_frame)
            self._mark_failure(camera_name, exc, using_cached_frame=False)
            return zero_color_frame, zero_depth_frame

    def read_all(
        self,
        cameras: dict[str, Any],
        *,
        executor: ThreadPoolExecutor | None = None,
        thread_name_prefix: str = "o10-camera",
    ) -> dict[str, tuple[np.ndarray, np.ndarray | None]]:
        if len(cameras) <= 1:
            return {
                camera_name: self.read(camera_name, camera)
                for camera_name, camera in cameras.items()
            }

        shutdown_executor = False
        if executor is None:
            executor = ThreadPoolExecutor(
                max_workers=len(cameras),
                thread_name_prefix=thread_name_prefix,
            )
            shutdown_executor = True

        futures = {
            executor.submit(self.read, camera_name, camera): camera_name
            for camera_name, camera in cameras.items()
        }
        camera_results: dict[str, tuple[np.ndarray, np.ndarray | None]] = {}
        try:
            for future in as_completed(futures):
                camera_results[futures[future]] = future.result()
        finally:
            if shutdown_executor:
                executor.shutdown(wait=True)

        return {
            camera_name: camera_results[camera_name]
            for camera_name in cameras
        }

    def zero_color_frame(self, camera_name: str) -> np.ndarray:
        camera_config = self.camera_configs[camera_name]
        return np.zeros((camera_config.height, camera_config.width, 3), dtype=np.uint8)

    def zero_depth_frame(self, camera_name: str) -> np.ndarray:
        camera_config = self.camera_configs[camera_name]
        return np.zeros((camera_config.height, camera_config.width), dtype=np.uint16)

    def _mark_success(self, camera_name: str) -> None:
        if self.fallback_active.pop(camera_name, False):
            logger.info("Camera %s recovered.", camera_name)

    def _mark_failure(
        self,
        camera_name: str,
        exc: Exception,
        *,
        using_cached_frame: bool,
    ) -> None:
        if self.fallback_active.get(camera_name):
            return
        self.fallback_active[camera_name] = True
        fallback_mode = "reusing last frame" if using_cached_frame else "using zero frame"
        logger.warning("Camera read failed for %s, %s: %s", camera_name, fallback_mode, exc)
```

- [ ] **Step 4: Run camera tests**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_o10_camera_io.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit camera helper**

```bash
git add \
  qiuzhi/tests/test_o10_camera_io.py \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/o10_camera_io.py
git commit -m "heliangp:add O10 camera IO helper"
```

---

### Task 4: Schema Helper

**Files:**
- Create: `qiuzhi/.../lerobot_play/utils/o10_schema.py`
- Create: `qiuzhi/tests/test_o10_schema.py`
- Later update O10 follower/leader imports in Tasks 7-10.

- [ ] **Step 1: Write failing schema tests**

Create `qiuzhi/tests/test_o10_schema.py`:
```python
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))


def test_single_arm_tactile_feature_spec_uses_existing_names():
    from lerobot_play.utils.o10_schema import TACTILE_FULL_NAMES, tactile_raw_feature_spec, tactile_raw_key

    spec = tactile_raw_feature_spec(TACTILE_FULL_NAMES)

    assert tactile_raw_key("right") == "observation.tactile.right_raw"
    assert spec["shape"] == (130,)
    assert spec["dtype"] == "float32"
    assert spec["names"][0] == "tactile.thumb_0"
    assert spec["names"][-1] == "tactile.dorsum_24"


def test_dual_arm_action_feature_order():
    from lerobot_play.utils import agibot_o10
    from lerobot_play.utils.o10_schema import DUAL_ARM_ACTION_FEATURE_NAMES

    assert DUAL_ARM_ACTION_FEATURE_NAMES == (
        tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES)
        + tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES)
    )


def test_dual_arm_gripper_and_eef_delta_feature_orders():
    from lerobot_play.utils import agibot_o10
    from lerobot_play.utils.o10_schema import (
        DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES,
        DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES,
        DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES,
    )

    assert DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES == (
        tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES)
        + tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_GRIPPER_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_GRIPPER_FEATURE_NAMES)
    )
    assert DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES == (
        tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
        + tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES)
    )
    assert DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES == (
        tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
        + tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_GRIPPER_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_GRIPPER_FEATURE_NAMES)
    )


def test_dual_arm_state_feature_order_inserts_pose_after_each_side():
    from lerobot_play.utils import agibot_o10
    from lerobot_play.utils.o10_schema import DUAL_ARM_STATE_FEATURE_NAMES

    side_joint_names = (
        tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES)
        + tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES)
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES)
    )
    side_dim = len(agibot_o10.AGIBOT_O10_ARM_FEATURE_NAMES) + len(agibot_o10.AGIBOT_O10_HAND_FEATURE_NAMES)

    assert DUAL_ARM_STATE_FEATURE_NAMES == (
        side_joint_names[:side_dim]
        + tuple(f"left.{name}" for name in agibot_o10.AGIBOT_O10_POSE_FEATURE_NAMES)
        + side_joint_names[side_dim:]
        + tuple(f"right.{name}" for name in agibot_o10.AGIBOT_O10_POSE_FEATURE_NAMES)
    )


def test_dual_arm_tactile_specs_are_per_side_130d():
    from lerobot_play.utils.o10_schema import (
        TACTILE_FULL_NAMES,
        dual_arm_tactile_raw_feature_spec,
        dual_arm_tactile_raw_key,
    )

    left_spec = dual_arm_tactile_raw_feature_spec("left")
    right_spec = dual_arm_tactile_raw_feature_spec("right")

    assert dual_arm_tactile_raw_key("left") == "observation.tactile.left_raw"
    assert dual_arm_tactile_raw_key("right") == "observation.tactile.right_raw"
    assert left_spec["shape"] == (130,)
    assert right_spec["shape"] == (130,)
    assert left_spec["names"] == [f"left.{name}" for name in TACTILE_FULL_NAMES]
    assert right_spec["names"] == [f"right.{name}" for name in TACTILE_FULL_NAMES]
```

- [ ] **Step 2: Run tests and confirm missing module failure**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_o10_schema.py -q
```
Expected: FAIL with missing `lerobot_play.utils.o10_schema`.

- [ ] **Step 3: Implement schema helper**

Create `qiuzhi/.../lerobot_play/utils/o10_schema.py`:
```python
from __future__ import annotations

from lerobot_play.utils.agibot_o10 import (
    AGIBOT_O10_ARM_FEATURE_NAMES,
    AGIBOT_O10_EEF_DELTA_FEATURE_NAMES,
    AGIBOT_O10_GRIPPER_FEATURE_NAMES,
    AGIBOT_O10_HAND_FEATURE_NAMES,
    AGIBOT_O10_POSE_FEATURE_NAMES,
)


NUM_O10_ARM_JOINTS = len(AGIBOT_O10_ARM_FEATURE_NAMES)
NUM_O10_HAND_JOINTS = len(AGIBOT_O10_HAND_FEATURE_NAMES)
SIDE_ACTION_DIM = NUM_O10_ARM_JOINTS + NUM_O10_HAND_JOINTS

DUAL_ARM_ACTION_FEATURE_NAMES = (
    tuple(f"left.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES)
    + tuple(f"left.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES)
)

DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES = (
    tuple(f"left.{name}" for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
    + tuple(f"left.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_HAND_FEATURE_NAMES)
)

DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES = (
    tuple(f"left.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES)
    + tuple(f"left.{name}" for name in AGIBOT_O10_GRIPPER_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_ARM_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_GRIPPER_FEATURE_NAMES)
)

DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES = (
    tuple(f"left.{name}" for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
    + tuple(f"left.{name}" for name in AGIBOT_O10_GRIPPER_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_EEF_DELTA_FEATURE_NAMES)
    + tuple(f"right.{name}" for name in AGIBOT_O10_GRIPPER_FEATURE_NAMES)
)

DUAL_ARM_JOINT_ONLY_STATE_FEATURE_NAMES = DUAL_ARM_ACTION_FEATURE_NAMES
DUAL_ARM_GRIPPER_STATE_FEATURE_NAMES = DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES
DUAL_ARM_STATE_FEATURE_NAMES = (
    DUAL_ARM_JOINT_ONLY_STATE_FEATURE_NAMES[:SIDE_ACTION_DIM]
    + tuple(f"left.{name}" for name in AGIBOT_O10_POSE_FEATURE_NAMES)
    + DUAL_ARM_JOINT_ONLY_STATE_FEATURE_NAMES[SIDE_ACTION_DIM:]
    + tuple(f"right.{name}" for name in AGIBOT_O10_POSE_FEATURE_NAMES)
)

TACTILE_FINGERTIP_NAMES = tuple(
    f"tactile.{finger}_{index}"
    for finger in ("thumb", "index", "middle", "ring", "little")
    for index in range(16)
)
TACTILE_FULL_NAMES = (
    TACTILE_FINGERTIP_NAMES
    + tuple(f"tactile.palm_{index}" for index in range(25))
    + tuple(f"tactile.dorsum_{index}" for index in range(25))
)

LEFT_TACTILE_RAW_KEY = "observation.tactile.left_raw"
RIGHT_TACTILE_RAW_KEY = "observation.tactile.right_raw"


def tactile_raw_key(handedness: str) -> str:
    return f"observation.tactile.{handedness}_raw"


def tactile_raw_feature_spec(names: tuple[str, ...]) -> dict[str, object]:
    return {
        "dtype": "float32",
        "shape": (len(names),),
        "names": list(names),
    }


def dual_arm_tactile_raw_key(side: str) -> str:
    return LEFT_TACTILE_RAW_KEY if side == "left" else RIGHT_TACTILE_RAW_KEY


def dual_arm_tactile_raw_feature_spec(side: str) -> dict[str, object]:
    return tactile_raw_feature_spec(
        tuple(f"{side}.{name}" for name in TACTILE_FULL_NAMES)
    )
```

- [ ] **Step 4: Run schema tests**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_o10_schema.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit schema helper**

```bash
git add \
  qiuzhi/tests/test_o10_schema.py \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/o10_schema.py
git commit -m "heliangp:add O10 schema helper"
```

---

### Task 5: Hand Control Helper

**Files:**
- Create: `qiuzhi/.../lerobot_play/utils/o10_hand_control.py`
- Create: `qiuzhi/tests/test_o10_hand_control.py`
- Later modify O10 follower/leader callers in Tasks 7-10.

- [ ] **Step 1: Write failing hand-control tests**

Create `qiuzhi/tests/test_o10_hand_control.py`:
```python
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))


def test_trigger_gesture_hand_pos_matches_builtin():
    from lerobot_play.utils import agibot_o10
    from lerobot_play.utils.o10_hand_control import trigger_gesture_hand_pos

    assert trigger_gesture_hand_pos(None, "pinch", "left", "open") == pytest.approx(
        agibot_o10.get_agibot_o10_trigger_gesture_joint_angles("pinch", "left", "open")
    )


def test_trigger_gesture_hand_pos_prefers_reset_json(tmp_path):
    from lerobot_play.utils.o10_hand_control import trigger_gesture_hand_pos

    reset_path = tmp_path / "reset.json"
    reset_path.write_text(
        json.dumps(
            {
                "gestures": {
                    "pinch": {
                        "left": {
                            "open": [float(index) for index in range(10)],
                            "closed": [float(index + 10) for index in range(10)],
                        },
                        "right": {
                            "open": [0.0] * 10,
                            "closed": [1.0] * 10,
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert trigger_gesture_hand_pos(reset_path, "pinch", "left", "open") == pytest.approx(
        [float(index) for index in range(10)]
    )


def test_gripper_value_to_hand_joints_clamps_and_interpolates():
    from lerobot_play.utils.o10_hand_control import gripper_value_to_hand_joints, trigger_gesture_hand_pos

    open_pose = trigger_gesture_hand_pos(None, "pinch", "right", "open")
    closed_pose = trigger_gesture_hand_pos(None, "pinch", "right", "closed")

    halfway = gripper_value_to_hand_joints(0.5, "pinch", "right", None)
    assert halfway == pytest.approx(
        [
            open_value + 0.5 * (closed_value - open_value)
            for open_value, closed_value in zip(open_pose, closed_pose, strict=True)
        ]
    )
    assert gripper_value_to_hand_joints(-1.0, "pinch", "right", None) == pytest.approx(open_pose)
    assert gripper_value_to_hand_joints(2.0, "pinch", "right", None) == pytest.approx(closed_pose)


def test_hand_joints_to_gripper_value_projects_onto_gesture_axis():
    from lerobot_play.utils.o10_hand_control import (
        gripper_value_to_hand_joints,
        hand_joints_to_gripper_value,
    )

    joints = gripper_value_to_hand_joints(0.25, "pinch", "left", None)

    assert hand_joints_to_gripper_value(joints, "pinch", "left", None) == pytest.approx(0.25)


def test_default_gripper_gesture_fallback_order():
    from lerobot_play.utils.o10_hand_control import default_gripper_gesture

    assert default_gripper_gesture(None, None, None) == "pinch"
    assert default_gripper_gesture(None, "tripod", "pinch") == "tripod"
    assert default_gripper_gesture("cylindrical", "tripod", "pinch") == "cylindrical"


def test_real_reset_pose_json_can_supply_trigger_gesture():
    from lerobot_play.utils.o10_hand_control import trigger_gesture_hand_pos

    reset_poses_path = WORKSPACE_ROOT / "configs" / "reset_poses" / "o10_dual_reset.json"

    assert len(trigger_gesture_hand_pos(reset_poses_path, "pinch", "left", "open")) == 10
```

- [ ] **Step 2: Run tests and confirm missing module failure**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_o10_hand_control.py -q
```
Expected: FAIL with missing `lerobot_play.utils.o10_hand_control`.

- [ ] **Step 3: Implement hand-control helper**

Create `qiuzhi/.../lerobot_play/utils/o10_hand_control.py`:
```python
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from lerobot_play.utils.agibot_o10 import (
    agibot_o10_gripper_value_from_hand_joints,
    agibot_o10_hand_joints_from_gripper_value,
    get_agibot_o10_reset_pose_gesture_joint_angles,
    get_agibot_o10_trigger_gesture_joint_angles,
)


def default_gripper_gesture(
    gripper_gesture: str | None,
    trigger_gesture: str | None,
    reset_gesture: str | None,
) -> str:
    return gripper_gesture or trigger_gesture or reset_gesture or "pinch"


def trigger_gesture_hand_pos(
    reset_poses_path: str | Path | None,
    gesture_name: str,
    handedness: str,
    state_key: str,
) -> list[float]:
    return get_agibot_o10_reset_pose_gesture_joint_angles(
        reset_poses_path,
        gesture_name,
        handedness,
        state_key,
    ) or get_agibot_o10_trigger_gesture_joint_angles(
        gesture_name,
        handedness,
        state_key,
    )


def gripper_value_to_hand_joints(
    gripper_value: float,
    gesture_name: str,
    handedness: str,
    reset_poses_path: str | Path | None = None,
) -> list[float]:
    return agibot_o10_hand_joints_from_gripper_value(
        gripper_value,
        gesture_name,
        handedness,
        reset_poses_path=reset_poses_path,
    )


def hand_joints_to_gripper_value(
    hand_joints: Sequence[float],
    gesture_name: str,
    handedness: str,
    reset_poses_path: str | Path | None = None,
) -> float:
    return agibot_o10_gripper_value_from_hand_joints(
        hand_joints,
        gesture_name,
        handedness,
        reset_poses_path=reset_poses_path,
    )
```

- [ ] **Step 4: Run hand-control tests**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_o10_hand_control.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit hand-control helper**

```bash
git add \
  qiuzhi/tests/test_o10_hand_control.py \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/o10_hand_control.py
git commit -m "heliangp:add O10 hand control helper"
```

---

### Task 6: Reset Helper

**Files:**
- Create: `qiuzhi/.../lerobot_play/utils/o10_reset.py`
- Create: `qiuzhi/tests/test_o10_reset_helpers.py`
- Later modify O10 follower/leader callers in Tasks 7-10.

- [ ] **Step 1: Write failing reset tests**

Create `qiuzhi/tests/test_o10_reset_helpers.py`:
```python
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))


def test_load_o10_reset_targets_returns_none_without_path_or_gesture():
    from lerobot_play.utils.o10_reset import load_o10_reset_targets

    assert load_o10_reset_targets(None, "left", "pinch") == (None, None)
    assert load_o10_reset_targets("some/path.json", "left", None) == (None, None)


def test_load_o10_reset_targets_loads_real_json():
    from lerobot_play.utils.o10_reset import load_o10_reset_targets

    reset_poses_path = REPO_ROOT.parent / "configs" / "reset_poses" / "o10_dual_reset.json"
    arm, hand = load_o10_reset_targets(reset_poses_path, "left", "pinch")

    assert len(arm) == 6
    assert len(hand) == 10


def test_normalize_joint_values_uses_store():
    from lerobot_play.utils.o10_reset import normalize_joint_values

    class Store:
        def normalize(self, values):
            return [float(value) + 1.0 for value in values]

    assert normalize_joint_values(Store(), [1, 2, 3]) == [2.0, 3.0, 4.0]


def test_load_o10_reset_targets_propagates_json_errors(tmp_path):
    from lerobot_play.utils.o10_reset import load_o10_reset_targets

    reset_path = tmp_path / "bad.json"
    reset_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="arm"):
        load_o10_reset_targets(reset_path, "left", "pinch")
```

- [ ] **Step 2: Run tests and confirm missing module failure**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_o10_reset_helpers.py -q
```
Expected: FAIL with missing `lerobot_play.utils.o10_reset`.

- [ ] **Step 3: Implement reset helper**

Create `qiuzhi/.../lerobot_play/utils/o10_reset.py`:
```python
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from lerobot_play.utils.joint_target_store import load_reset_poses


def load_o10_reset_targets(
    reset_poses_path: str | Path | None,
    side: str,
    reset_gesture: str | None,
) -> tuple[list[float] | None, list[float] | None]:
    if not reset_poses_path or not reset_gesture:
        return None, None
    return load_reset_poses(reset_poses_path, side, reset_gesture)


def normalize_joint_values(store, joint_values: Sequence[float]) -> list[float]:
    return store.normalize(joint_values)
```

- [ ] **Step 4: Run reset tests**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_o10_reset_helpers.py -q
```
Expected: PASS.

- [ ] **Step 5: Commit reset helper**

```bash
git add \
  qiuzhi/tests/test_o10_reset_helpers.py \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/o10_reset.py
git commit -m "heliangp:add O10 reset helper"
```

---

### Task 7: Refactor Single-Arm Follower

**Files:**
- Modify: `qiuzhi/.../lerobot_play/robots/pico_follower_single_arm_agibot_o10/airbot_pico_follower_single_arm_agibot_o10.py`
- Test: `qiuzhi/tests/test_o10_camera_observation_fallback.py`
- Test: `qiuzhi/tests/test_o10_tactile_raw_dataset_schema.py`

- [ ] **Step 1: Update imports and camera reader initialization**

In the single-arm follower:

Remove local private helpers `_rotation_matrix_from_rpy`, `_apply_eef_delta_to_pose`, `_solve_ik`, camera fallback helpers, tactile constants, `_tactile_raw_key`, `_tactile_raw_feature_spec`, and `homogeneous_matrix_to_pose` after replacing their call sites.

Add imports:
```python
from lerobot_play.utils.o10_camera_io import (
    CameraObservationReader,
    camera_feature_shapes,
    depth_observation_name,
)
from lerobot_play.utils.o10_hand_control import (
    default_gripper_gesture,
    gripper_value_to_hand_joints,
    hand_joints_to_gripper_value,
)
from lerobot_play.utils.o10_motion import (
    apply_eef_delta_to_pose,
    homogeneous_matrix_to_pose,
    solve_o10_ik,
)
from lerobot_play.utils.o10_reset import load_o10_reset_targets, normalize_joint_values
from lerobot_play.utils.o10_schema import TACTILE_FULL_NAMES, tactile_raw_feature_spec, tactile_raw_key
```

After `self._camera_read_executor` initialization, add:
```python
        self.camera_reader = CameraObservationReader(
            config.cameras,
            allow_read_failures=getattr(self.config, "allow_camera_read_failures", False),
            timeout_ms=int(getattr(self.config, "camera_read_timeout_ms", 200)),
        )
```

- [ ] **Step 2: Replace reset loading call site**

Replace `_load_reset_target_from_file` body with:
```python
    def _load_reset_target_from_file(self) -> None:
        try:
            arm_loaded, hand_loaded = load_o10_reset_targets(
                getattr(self.config, "reset_poses_path", None),
                self.config.handedness,
                getattr(self.config, "reset_gesture", None),
            )
        except Exception as exc:
            logger.warning("Failed to load reset poses: %s", exc)
            arm_loaded, hand_loaded = None, None

        if arm_loaded is not None:
            self.reset_arm_joint_pos = arm_loaded
        if hand_loaded is not None:
            self.reset_hand_joint_pos = hand_loaded
            self.hand_joints = hand_loaded.copy()
        self._log_joint_pos("Reset arm target", AGIBOT_O10_ARM_FEATURE_NAMES, self.reset_arm_joint_pos)
        self._log_joint_pos("Reset hand target", AGIBOT_O10_HAND_FEATURE_NAMES, self.reset_hand_joint_pos)
```

Replace direct store normalize calls in `capture_current_joint_pos_as_reset_target`:
```python
        arm_joint_pos = normalize_joint_values(self.arm_reset_store, arm_joint_pos)
        hand_joint_pos = normalize_joint_values(self.hand_reset_store, hand_joint_pos)
```

- [ ] **Step 3: Replace camera helpers and observation feature logic**

Replace `_read_camera_observations` with:
```python
    def _read_camera_observations(self) -> dict[str, tuple[np.ndarray, np.ndarray | None]]:
        return self.camera_reader.read_all(
            self.cameras,
            executor=getattr(self, "_camera_read_executor", None),
            thread_name_prefix="o10-single-camera",
        )
```

Replace `_cameras_ft` with:
```python
    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return camera_feature_shapes(self.cameras, self.config.cameras)
```

Replace single-arm tactile spec block in `observation_features`:
```python
            tactile_ft = {
                tactile_raw_key(self.config.handedness): tactile_raw_feature_spec(TACTILE_FULL_NAMES)
            }
```

Replace depth key in `get_observation`:
```python
                obs_dict[depth_observation_name(cam_key)] = np.expand_dims(
                    depth_frame, axis=-1
                )
```

- [ ] **Step 4: Replace motion and gripper helpers**

Replace `self.homogeneous_matrix_to_pose(...)` calls with `homogeneous_matrix_to_pose(...)`.

Replace `_gripper_gesture` body:
```python
        return default_gripper_gesture(
            getattr(self.config, "gripper_gesture", None),
            getattr(self.config, "trigger_gesture", None),
            getattr(self.config, "reset_gesture", None),
        )
```

Replace `_hand_joints_to_gripper_value` body:
```python
        return hand_joints_to_gripper_value(
            hand_joints,
            self._gripper_gesture(),
            getattr(self.config, "handedness", "right"),
            reset_poses_path=self._reset_poses_path(),
        )
```

Replace `_gripper_value_to_hand_joints` body:
```python
        return gripper_value_to_hand_joints(
            gripper_value,
            self._gripper_gesture(),
            getattr(self.config, "handedness", "right"),
            reset_poses_path=self._reset_poses_path(),
        )
```

Replace eef_delta send path:
```python
            target_pose = apply_eef_delta_to_pose(current_pose, formatted_action["eef_delta"])
            joints = solve_o10_ik(
                self.arm_kdl,
                target_pose,
                current_arm_joints[: len(AGIBOT_O10_ARM_FEATURE_NAMES)],
            )
```

- [ ] **Step 5: Run focused tests**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest \
  qiuzhi/tests/test_o10_motion_helpers.py \
  qiuzhi/tests/test_o10_camera_io.py \
  qiuzhi/tests/test_o10_schema.py \
  qiuzhi/tests/test_o10_hand_control.py \
  qiuzhi/tests/test_o10_reset_helpers.py \
  qiuzhi/tests/test_o10_camera_observation_fallback.py \
  qiuzhi/tests/test_o10_tactile_raw_dataset_schema.py -q
```
Expected: PASS.

- [ ] **Step 6: Commit single-arm follower refactor**

```bash
git add \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/pico_follower_single_arm_agibot_o10/airbot_pico_follower_single_arm_agibot_o10.py
git commit -m "heliangp:dedup O10 single-arm follower helpers"
```

---

### Task 8: Refactor Dual-Arm Follower

**Files:**
- Modify: `qiuzhi/.../lerobot_play/robots/pico_follower_dual_arm_agibot_o10/airbot_pico_follower_dual_arm_agibot_o10.py`
- Test: `qiuzhi/tests/test_dual_arm_tactile_schema.py`
- Test: `qiuzhi/tests/test_o10_camera_observation_fallback.py`

- [ ] **Step 1: Move dual-arm schema imports**

In dual-arm follower, replace local dual-arm constants by importing from `o10_schema.py`:
```python
from lerobot_play.utils.o10_schema import (
    DUAL_ARM_ACTION_FEATURE_NAMES,
    DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES,
    DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES,
    DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES,
    DUAL_ARM_GRIPPER_STATE_FEATURE_NAMES,
    DUAL_ARM_JOINT_ONLY_STATE_FEATURE_NAMES,
    DUAL_ARM_STATE_FEATURE_NAMES,
    NUM_O10_ARM_JOINTS,
    NUM_O10_HAND_JOINTS,
    SIDE_ACTION_DIM,
    TACTILE_FULL_NAMES,
    dual_arm_tactile_raw_feature_spec,
    dual_arm_tactile_raw_key,
)
```

Then set compatibility aliases near imports so existing local code changes stay small:
```python
_NUM_ARM_JOINTS = NUM_O10_ARM_JOINTS
_NUM_HAND_JOINTS = NUM_O10_HAND_JOINTS
_SIDE_ACTION_DIM = SIDE_ACTION_DIM
```

Delete the duplicated local definitions of dual-arm feature-name constants and tactile constants.

- [ ] **Step 2: Add motion/camera/hand/reset imports and reader initialization**

Add imports:
```python
from lerobot_play.utils.o10_camera_io import (
    CameraObservationReader,
    camera_feature_shapes,
    depth_observation_name,
)
from lerobot_play.utils.o10_hand_control import (
    default_gripper_gesture,
    gripper_value_to_hand_joints,
    hand_joints_to_gripper_value,
)
from lerobot_play.utils.o10_motion import (
    apply_eef_delta_to_pose,
    homogeneous_matrix_to_pose,
    solve_o10_ik,
)
from lerobot_play.utils.o10_reset import load_o10_reset_targets, normalize_joint_values
```

After camera reader fields are initialized in `__init__`, add:
```python
        self.camera_reader = CameraObservationReader(
            config.cameras,
            allow_read_failures=getattr(self.config, "allow_camera_read_failures", False),
            timeout_ms=int(getattr(self.config, "camera_read_timeout_ms", 200)),
        )
```

- [ ] **Step 3: Replace camera helper call sites**

Replace `_read_camera_observations` with:
```python
    def _read_camera_observations(self) -> dict[str, tuple[np.ndarray, np.ndarray | None]]:
        return self.camera_reader.read_all(
            self.cameras,
            executor=getattr(self, "_camera_read_executor", None),
            thread_name_prefix="o10-dual-camera",
        )
```

Replace `_cameras_ft` with:
```python
    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return camera_feature_shapes(self.cameras, self.config.cameras)
```

Replace depth key usage in `get_observation`:
```python
                obs_dict[depth_observation_name(cam_key)] = np.expand_dims(
                    depth_frame, axis=-1
                )
```

- [ ] **Step 4: Replace dual-arm tactile specs and motion call sites**

In `observation_features`, replace tactile specs with:
```python
            tactile_ft = {
                dual_arm_tactile_raw_key("left"): dual_arm_tactile_raw_feature_spec("left"),
                dual_arm_tactile_raw_key("right"): dual_arm_tactile_raw_feature_spec("right"),
            }
```

Replace `self.homogeneous_matrix_to_pose(...)` with `homogeneous_matrix_to_pose(...)`.

Replace `_solve_eef_delta_side_joints` implementation:
```python
    def _solve_eef_delta_side_joints(
        self,
        current_arm_joints: list[float],
        eef_delta: list[float],
    ) -> list[float]:
        current_pose = self.arm_kdl.forward_kinematics(current_arm_joints[:_NUM_ARM_JOINTS])
        target_pose = apply_eef_delta_to_pose(current_pose, eef_delta)
        return solve_o10_ik(self.arm_kdl, target_pose, current_arm_joints[:_NUM_ARM_JOINTS])
```

- [ ] **Step 5: Replace gripper and reset helper wrappers**

Replace `_side_gripper_gesture` body:
```python
        side_config = self._side_config(side)
        return default_gripper_gesture(
            side_config.get("gripper_gesture"),
            side_config.get("trigger_gesture"),
            side_config.get("reset_gesture") or getattr(self.config, "trigger_gesture", "pinch"),
        )
```

Replace `_hand_joints_to_gripper_value` and `_gripper_value_to_hand_joints` bodies with calls to `hand_joints_to_gripper_value(...)` and `gripper_value_to_hand_joints(...)`.

Replace `load_reset_poses(...)` call sites with:
```python
                arm_loaded, hand_loaded = load_o10_reset_targets(
                    reset_poses_path,
                    side,
                    reset_gesture,
                )
```

Replace direct `store.normalize(...)` calls where straightforward:
```python
            arm_pos = normalize_joint_values(arm_store, arm_pos)
            hand_pos = normalize_joint_values(hand_store, hand_pos)
```

- [ ] **Step 6: Run focused tests**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest \
  qiuzhi/tests/test_o10_motion_helpers.py \
  qiuzhi/tests/test_o10_camera_io.py \
  qiuzhi/tests/test_o10_schema.py \
  qiuzhi/tests/test_o10_hand_control.py \
  qiuzhi/tests/test_o10_reset_helpers.py \
  qiuzhi/tests/test_dual_arm_tactile_schema.py \
  qiuzhi/tests/test_o10_camera_observation_fallback.py \
  qiuzhi/tests/test_o10_tactile_raw_dataset_schema.py -q
```
Expected: PASS. If `test_dual_arm_tactile_schema.py` is source-based and expects constants in the follower file, update it to import/check `o10_schema.py` instead of requiring constants to live in the follower.

- [ ] **Step 7: Commit dual-arm follower refactor**

```bash
git add \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/pico_follower_dual_arm_agibot_o10/airbot_pico_follower_dual_arm_agibot_o10.py \
  qiuzhi/tests/test_dual_arm_tactile_schema.py
git commit -m "heliangp:dedup O10 dual-arm follower helpers"
```

---

### Task 9: Refactor Single-Arm Leader

**Files:**
- Modify: `qiuzhi/.../lerobot_play/teleoperators/pico_leader_single_arm_agibot_o10/pico_leader_single_arm_agibot_o10.py`
- Test: `qiuzhi/tests/test_single_arm_o10_trigger_gate.py`
- Test: `qiuzhi/tests/test_single_arm_trigger_gesture_config.py`

- [ ] **Step 1: Add helper imports and remove duplicated RPY helper**

Add:
```python
from lerobot_play.utils.o10_hand_control import (
    default_gripper_gesture,
    gripper_value_to_hand_joints,
    hand_joints_to_gripper_value,
    trigger_gesture_hand_pos,
)
from lerobot_play.utils.o10_motion import homogeneous_matrix_to_pose, rpy_from_rotation_matrix
from lerobot_play.utils.o10_reset import load_o10_reset_targets, normalize_joint_values
```

Remove local imports of `agibot_o10_gripper_value_from_hand_joints`, `agibot_o10_hand_joints_from_gripper_value`, `get_agibot_o10_reset_pose_gesture_joint_angles`, and `get_agibot_o10_trigger_gesture_joint_angles` once call sites are replaced.

Remove the local `_rpy_from_rotation_matrix` function after replacing its call sites. `rpy_from_rotation_matrix` is created in Task 2, so this task should only import and use it.

- [ ] **Step 2: Confirm motion helper covers RPY extraction**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_o10_motion_helpers.py -q
```
Expected: PASS, including `test_rpy_from_rotation_matrix_extracts_yaw`.

- [ ] **Step 3: Replace single-arm leader call sites**

Replace `_gripper_gesture` body:
```python
        return default_gripper_gesture(
            getattr(self.config, "gripper_gesture", None),
            getattr(self.config, "trigger_gesture", None),
            getattr(self.config, "reset_gesture", None),
        )
```

Replace `_hand_joints_to_gripper_value` body:
```python
        return hand_joints_to_gripper_value(
            hand_joints,
            self._gripper_gesture(),
            getattr(self.config, "handedness", "right"),
            reset_poses_path=self._reset_poses_path(),
        )
```

Replace `_get_trigger_gesture_hand_pos` body:
```python
        return trigger_gesture_hand_pos(
            self._reset_poses_path(),
            getattr(self.config, "trigger_gesture", "pinch"),
            self.handedness,
            state_key,
        )
```

Replace `_get_trigger_gesture_hand_pos_from_gripper_value` body:
```python
        return gripper_value_to_hand_joints(
            gripper_value,
            getattr(self.config, "trigger_gesture", "pinch"),
            self.handedness,
            reset_poses_path=self._reset_poses_path(),
        )
```

Replace `_rpy_from_rotation_matrix(...)` call with `rpy_from_rotation_matrix(...)`.

Replace `self.homogeneous_matrix_to_pose(...)` calls with `homogeneous_matrix_to_pose(...)`.

- [ ] **Step 4: Replace reset loading helpers where straightforward**

Replace `load_reset_poses(...)` calls in `_refresh_reset_targets_from_store` and `_initialize_hand_reset_target` with `load_o10_reset_targets(...)`.

Replace direct normalize calls:
```python
        normalized_joint_pos = normalize_joint_values(self.arm_reset_store, joint_pos)
```
and:
```python
        normalized_joint_pos = normalize_joint_values(self.hand_reset_store, joint_pos)
```

- [ ] **Step 5: Run focused leader tests**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest \
  qiuzhi/tests/test_o10_motion_helpers.py \
  qiuzhi/tests/test_o10_hand_control.py \
  qiuzhi/tests/test_o10_reset_helpers.py \
  qiuzhi/tests/test_single_arm_o10_trigger_gate.py \
  qiuzhi/tests/test_single_arm_trigger_gesture_config.py \
  qiuzhi/tests/test_agibot_o10_glove_teleoperator.py -q
```
Expected: PASS.

- [ ] **Step 6: Commit single-arm leader refactor**

```bash
git add \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/pico_leader_single_arm_agibot_o10/pico_leader_single_arm_agibot_o10.py
git commit -m "heliangp:dedup O10 single-arm leader helpers"
```

---

### Task 10: Refactor Dual-Arm Leader

**Files:**
- Modify: `qiuzhi/.../lerobot_play/teleoperators/pico_leader_dual_arm_agibot_o10/pico_leader_dual_arm_agibot_o10.py`
- Test: `qiuzhi/tests/test_dual_arm_o10_trigger_gate.py`

- [ ] **Step 1: Import dual-arm schema from helper**

Replace imports from the dual-arm follower module:
```python
from lerobot_play.robots.pico_follower_dual_arm_agibot_o10.airbot_pico_follower_dual_arm_agibot_o10 import (
    DUAL_ARM_ACTION_FEATURE_NAMES,
    DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES,
    DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES,
    DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES,
)
```

with:
```python
from lerobot_play.utils.o10_schema import (
    DUAL_ARM_ACTION_FEATURE_NAMES,
    DUAL_ARM_EEF_DELTA_ACTION_FEATURE_NAMES,
    DUAL_ARM_EEF_DELTA_GRIPPER_ACTION_FEATURE_NAMES,
    DUAL_ARM_GRIPPER_ACTION_FEATURE_NAMES,
)
```

This breaks the leader's import dependency on the follower implementation.

- [ ] **Step 2: Add motion/hand/reset helper imports**

Add:
```python
from lerobot_play.utils.o10_hand_control import (
    default_gripper_gesture,
    gripper_value_to_hand_joints,
    hand_joints_to_gripper_value,
    trigger_gesture_hand_pos,
)
from lerobot_play.utils.o10_motion import homogeneous_matrix_to_pose, rpy_from_rotation_matrix
from lerobot_play.utils.o10_reset import load_o10_reset_targets, normalize_joint_values
```

Remove imports of `agibot_o10_hand_joints_from_gripper_value`, `agibot_o10_gripper_value_from_hand_joints`, `get_agibot_o10_reset_pose_gesture_joint_angles`, `get_agibot_o10_trigger_gesture_joint_angles`, and `load_reset_poses` after call sites are replaced.

- [ ] **Step 3: Replace dual-arm leader call sites**

Replace `_side_gripper_gesture` body:
```python
        side_config = self._side_config(side)
        return default_gripper_gesture(
            side_config.get("gripper_gesture"),
            side_config.get("trigger_gesture"),
            side_config.get("reset_gesture") or getattr(self.config, "trigger_gesture", "pinch"),
        )
```

Replace `_hand_joints_to_gripper_value` body:
```python
        return hand_joints_to_gripper_value(
            hand_joints,
            self._side_gripper_gesture(side),
            self._side_handedness(side),
            reset_poses_path=self._side_reset_poses_path(side),
        )
```

Replace `_get_trigger_gesture_hand_pos` body:
```python
        return trigger_gesture_hand_pos(
            self._side_reset_poses_path(side),
            self._get_trigger_gesture_name(side),
            self._side_handedness(side),
            state_key,
        )
```

Replace `_get_trigger_gesture_hand_pos_from_gripper_value` body:
```python
        return gripper_value_to_hand_joints(
            gripper_value,
            self._get_trigger_gesture_name(side),
            self._side_handedness(side),
            reset_poses_path=self._side_reset_poses_path(side),
        )
```

Replace `_rpy_from_rotation_matrix(...)` calls with `rpy_from_rotation_matrix(...)`.

Replace `self.homogeneous_matrix_to_pose(...)` calls with `homogeneous_matrix_to_pose(...)`.

- [ ] **Step 4: Replace reset helpers**

Replace `load_reset_poses(...)` call sites with:
```python
                arm_loaded, hand_loaded = load_o10_reset_targets(
                    reset_poses_path,
                    side,
                    reset_gesture,
                )
```
and for hand-only initialization:
```python
                _, stored = load_o10_reset_targets(reset_poses_path, side, reset_gesture)
```

Replace straightforward normalize calls with `normalize_joint_values(...)`.

- [ ] **Step 5: Run dual-arm leader tests**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest \
  qiuzhi/tests/test_o10_motion_helpers.py \
  qiuzhi/tests/test_o10_schema.py \
  qiuzhi/tests/test_o10_hand_control.py \
  qiuzhi/tests/test_o10_reset_helpers.py \
  qiuzhi/tests/test_dual_arm_o10_trigger_gate.py \
  qiuzhi/tests/test_dual_arm_config.py -q
```
Expected: PASS. If `test_dual_arm_o10_trigger_gate.py` stubs the old follower import path for feature names, update its stubs to provide `lerobot_play.utils.o10_schema` instead.

- [ ] **Step 6: Commit dual-arm leader refactor**

```bash
git add \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/pico_leader_dual_arm_agibot_o10/pico_leader_dual_arm_agibot_o10.py \
  qiuzhi/tests/test_dual_arm_o10_trigger_gate.py
git commit -m "heliangp:dedup O10 dual-arm leader helpers"
```

---

### Task 11: Cleanup and Full Verification

**Files:**
- Modify only files touched by prior tasks if cleanup is needed.

- [ ] **Step 1: Search for duplicate local helpers that should be gone**

Run:
```bash
rg -n "_rotation_matrix_from_rpy|_apply_eef_delta_to_pose|def _solve_ik|def homogeneous_matrix_to_pose|TACTILE_FINGERTIP_NAMES|def _tactile_raw_key|def _depth_observation_name|def _zero_camera" \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/pico_follower_single_arm_agibot_o10 \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/pico_follower_dual_arm_agibot_o10 \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/pico_leader_single_arm_agibot_o10 \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/pico_leader_dual_arm_agibot_o10
```
Expected: no matches for duplicated helpers that were moved. Matches that are intentional wrappers should be inspected and justified in final notes.

- [ ] **Step 2: Run helper tests**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest \
  qiuzhi/tests/test_o10_motion_helpers.py \
  qiuzhi/tests/test_o10_camera_io.py \
  qiuzhi/tests/test_o10_schema.py \
  qiuzhi/tests/test_o10_hand_control.py \
  qiuzhi/tests/test_o10_reset_helpers.py -q
```
Expected: PASS.

- [ ] **Step 3: Run O10 regression set**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest \
  qiuzhi/tests/test_agibot_o10.py \
  qiuzhi/tests/test_dual_arm_o10_trigger_gate.py \
  qiuzhi/tests/test_o10_camera_observation_fallback.py \
  qiuzhi/tests/test_dual_arm_tactile_schema.py \
  qiuzhi/tests/test_o10_tactile_raw_dataset_schema.py \
  qiuzhi/tests/test_single_arm_o10_trigger_gate.py \
  qiuzhi/tests/test_single_arm_trigger_gesture_config.py \
  qiuzhi/tests/test_dual_arm_config.py -q
```
Expected: PASS.

- [ ] **Step 4: Optional broader qiuzhi regression**

Run:
```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/ -q
```
Expected: PASS or known unrelated failures only. If failures occur, record exact failing tests and whether they touch files modified by this plan.

- [ ] **Step 5: Commit final cleanup if needed**

If Step 1 found leftover imports or dead local helpers and you removed them:
```bash
git add \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/pico_follower_single_arm_agibot_o10/airbot_pico_follower_single_arm_agibot_o10.py \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/robots/pico_follower_dual_arm_agibot_o10/airbot_pico_follower_dual_arm_agibot_o10.py \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/pico_leader_single_arm_agibot_o10/pico_leader_single_arm_agibot_o10.py \
  qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/teleoperators/pico_leader_dual_arm_agibot_o10/pico_leader_dual_arm_agibot_o10.py
git commit -m "heliangp:cleanup O10 helper dedup leftovers"
```
If cleanup touched only a subset of these files, stage only that subset. If no cleanup was needed, do not create an empty commit.

---

## Self-Review Checklist

- Spec coverage:
  - Motion helper: Task 2, Task 7, Task 8, Task 9, Task 10.
  - Camera helper: Task 3, Task 7, Task 8.
  - Schema helper: Task 4, Task 8, Task 10.
  - Hand-control helper: Task 5, Task 7, Task 8, Task 9, Task 10.
  - Reset helper: Task 6, Task 7, Task 8, Task 9, Task 10.
  - Verification: Task 11.
- No YAML, dataset schema, hardware lifecycle, SDK, or `yudie/` changes are planned.
- Every task has an exact test command and expected result.
- Every task stages only files it owns, protecting the existing dirty worktree.
