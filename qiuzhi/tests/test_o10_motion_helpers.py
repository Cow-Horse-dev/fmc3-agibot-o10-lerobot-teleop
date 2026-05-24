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
        def inverse_kinematics(self, target_pose, seed_joints):
            return [[6, 5, 4, 3, 2, 1]]

    assert solve_o10_ik(FakeKdl(), np.eye(4), [0.0] * 6) == [6.0, 5.0, 4.0, 3.0, 2.0, 1.0]


def test_solve_o10_ik_does_not_hide_internal_type_error():
    from lerobot_play.utils.o10_motion import solve_o10_ik

    class FakeKdl:
        def __init__(self):
            self.calls = []

        def inverse_kinematics(self, target_pose, seed_joints, force_calculate=False):
            self.calls.append(force_calculate)
            if force_calculate:
                raise TypeError("internal failure")
            return [[6, 5, 4, 3, 2, 1]]

    kdl = FakeKdl()
    with pytest.raises(TypeError, match="internal failure"):
        solve_o10_ik(kdl, np.eye(4), [0.0] * 6)

    assert kdl.calls == [True]


def test_solve_o10_ik_falls_back_for_uninspectable_unknown_keyword_error():
    from lerobot_play.utils.o10_motion import solve_o10_ik

    class UninspectableInverseKinematics:
        __signature__ = object()

        def __init__(self):
            self.calls = []

        def __call__(self, target_pose, seed_joints, **kwargs):
            self.calls.append(kwargs)
            if kwargs:
                raise TypeError("got an unexpected keyword argument 'force_calculate'")
            return [[6, 5, 4, 3, 2, 1]]

    class FakeKdl:
        inverse_kinematics = UninspectableInverseKinematics()

    kdl = FakeKdl()
    assert solve_o10_ik(kdl, np.eye(4), [0.0] * 6) == [6.0, 5.0, 4.0, 3.0, 2.0, 1.0]
    assert kdl.inverse_kinematics.calls == [{"force_calculate": True}, {}]


def test_solve_o10_ik_does_not_hide_uninspectable_internal_type_error():
    from lerobot_play.utils.o10_motion import solve_o10_ik

    class UninspectableInverseKinematics:
        __signature__ = object()

        def __init__(self):
            self.calls = []

        def __call__(self, target_pose, seed_joints, **kwargs):
            self.calls.append(kwargs)
            if kwargs:
                raise TypeError("internal failure")
            return [[6, 5, 4, 3, 2, 1]]

    class FakeKdl:
        inverse_kinematics = UninspectableInverseKinematics()

    kdl = FakeKdl()
    with pytest.raises(TypeError, match="internal failure"):
        solve_o10_ik(kdl, np.eye(4), [0.0] * 6)

    assert kdl.inverse_kinematics.calls == [{"force_calculate": True}]


def test_solve_o10_ik_does_not_fallback_for_ambiguous_uninspectable_type_error():
    from lerobot_play.utils.o10_motion import solve_o10_ik

    class UninspectableInverseKinematics:
        __signature__ = object()

        def __init__(self):
            self.calls = []

        def __call__(self, target_pose, seed_joints, **kwargs):
            self.calls.append(kwargs)
            if kwargs:
                raise TypeError("takes no keyword arguments")
            return [[6, 5, 4, 3, 2, 1]]

    class FakeKdl:
        inverse_kinematics = UninspectableInverseKinematics()

    kdl = FakeKdl()
    with pytest.raises(TypeError, match="takes no keyword arguments"):
        solve_o10_ik(kdl, np.eye(4), [0.0] * 6)

    assert kdl.inverse_kinematics.calls == [{"force_calculate": True}]


def test_solve_o10_ik_does_not_fallback_for_internal_keyword_message():
    from lerobot_play.utils.o10_motion import solve_o10_ik

    class UninspectableInverseKinematics:
        __signature__ = object()

        def __init__(self):
            self.calls = []

        def __call__(self, target_pose, seed_joints, **kwargs):
            self.calls.append(kwargs)
            if kwargs:
                raise TypeError("failed handling keyword argument force_calculate internally")
            return [[6, 5, 4, 3, 2, 1]]

    class FakeKdl:
        inverse_kinematics = UninspectableInverseKinematics()

    kdl = FakeKdl()
    with pytest.raises(TypeError, match="failed handling keyword argument"):
        solve_o10_ik(kdl, np.eye(4), [0.0] * 6)

    assert kdl.inverse_kinematics.calls == [{"force_calculate": True}]


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


def test_rotation_matrix_to_quaternion_rejects_non_3x3():
    from lerobot_play.utils.o10_motion import rotation_matrix_to_quaternion

    with pytest.raises(ValueError, match="3x3"):
        rotation_matrix_to_quaternion(np.eye(2))


def test_rotation_matrix_to_quaternion_rejects_non_finite_values():
    from lerobot_play.utils.o10_motion import rotation_matrix_to_quaternion

    rotation = np.eye(3)
    rotation[0, 0] = np.nan

    with pytest.raises(ValueError, match="finite"):
        rotation_matrix_to_quaternion(rotation)


def test_rotation_matrix_to_quaternion_accepts_kdl_level_float_drift():
    from lerobot_play.utils.o10_motion import rotation_matrix_from_rpy, rotation_matrix_to_quaternion

    rotation = rotation_matrix_from_rpy(0.2, -0.1, 0.3)
    rotation[0, 0] += 4e-8

    quaternion = rotation_matrix_to_quaternion(rotation)

    assert np.linalg.norm(quaternion) == pytest.approx(1.0)


def test_rotation_matrix_to_quaternion_rejects_non_orthogonal_matrix():
    from lerobot_play.utils.o10_motion import rotation_matrix_to_quaternion

    rotation = np.eye(3)
    rotation[0, 1] = 0.25

    with pytest.raises(ValueError, match="orthogonal"):
        rotation_matrix_to_quaternion(rotation)


def test_rotation_matrix_to_quaternion_rejects_reflection():
    from lerobot_play.utils.o10_motion import rotation_matrix_to_quaternion

    with pytest.raises(ValueError, match="determinant"):
        rotation_matrix_to_quaternion(np.diag([1.0, 1.0, -1.0]))
