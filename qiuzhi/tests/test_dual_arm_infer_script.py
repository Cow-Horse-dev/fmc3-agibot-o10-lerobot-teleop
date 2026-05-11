from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DUAL_ACT_INFER_SCRIPT = (
    REPO_ROOT
    / ".."
    / "scripts/o10/dual_arm/infer_o10_dual_act_camera_pen_touch_20260427.sh"
).resolve()
DUAL_INFER_SCRIPT = (
    REPO_ROOT
    / ".."
    / "scripts/o10/dual_arm/infer_o10_dual.sh"
).resolve()
DUAL_SMOLVLA_ASYNC_RTC_SCRIPT = (
    REPO_ROOT
    / ".."
    / "scripts/o10/dual_arm/infer_o10_dual_smolvla_async_rtc.sh"
).resolve()
DUAL_PI05_ASYNC_RTC_SCRIPT = (
    REPO_ROOT
    / ".."
    / "scripts/o10/dual_arm/infer_o10_dual_pi05_async_rtc.sh"
).resolve()


def test_dual_act_infer_script_checks_required_can_interfaces():
    source = DUAL_ACT_INFER_SCRIPT.read_text(encoding="utf-8")

    assert "for required_can_interface in can0 can1; do" in source
    assert 'ip link show "$required_can_interface"' in source
    assert "缺少双臂推理所需 CAN 接口" in source


def test_dual_infer_script_defaults_to_pi0_python_env():
    source = DUAL_INFER_SCRIPT.read_text(encoding="utf-8")

    assert "ARM_HAND_TELEOP_PYTHON" in source
    assert "arm-hand-teleop-pi0/bin/python" in source
    assert "${ARM_HAND_TELEOP_PYTHON:-" in source


def test_dual_smolvla_async_rtc_script_starts_server_and_client():
    source = DUAL_SMOLVLA_ASYNC_RTC_SCRIPT.read_text(encoding="utf-8")

    assert "ARM_HAND_TELEOP_RTC_ENABLED" in source
    assert "async_policy_server" in source
    assert "--async_infer" in source
    assert "checkpoints/${checkpoint}/pretrained_model" in source


def test_dual_pi05_async_rtc_script_uses_pi0_env_and_current_checkpoint():
    source = DUAL_PI05_ASYNC_RTC_SCRIPT.read_text(encoding="utf-8")

    assert "arm-hand-teleop-pi0/bin/python" in source
    assert "ARM_HAND_TELEOP_RTC_ENABLED" in source
    assert 'fps="${ARM_HAND_TELEOP_ASYNC_FPS:-15}"' in source
    assert "pi05_camera_pen_touch_clean_del_52_376_selected/120000/pretrained_model" in source
    assert "async_policy_server" in source
    assert "--policy pi05" in source
    assert "--async_infer" in source
