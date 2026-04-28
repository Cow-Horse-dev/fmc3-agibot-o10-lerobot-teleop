from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DUAL_ACT_INFER_SCRIPT = (
    REPO_ROOT
    / ".."
    / "scripts/o10/dual_arm/infer_o10_dual_act_camera_pen_touch_20260427.sh"
).resolve()


def test_dual_act_infer_script_checks_required_can_interfaces():
    source = DUAL_ACT_INFER_SCRIPT.read_text(encoding="utf-8")

    assert "for required_can_interface in can0 can1; do" in source
    assert 'ip link show "$required_can_interface"' in source
    assert "缺少双臂推理所需 CAN 接口" in source
