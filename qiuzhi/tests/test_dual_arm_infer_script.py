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
DUAL_PI05_FULLFT_ASYNC_RTC_SCRIPT = (
    REPO_ROOT
    / ".."
    / "scripts/o10/dual_arm/infer_o10_dual_pi05_fullft_async_rtc.sh"
).resolve()
DUAL_OPENPI_JAX_ASYNC_SCRIPT = (
    REPO_ROOT
    / ".."
    / "scripts/o10/dual_arm/infer_o10_dual_openpi_jax_async.sh"
).resolve()
DUAL_OPENPI_JAX_WS_ASYNC_SCRIPT = (
    REPO_ROOT
    / ".."
    / "scripts/o10/dual_arm/infer_o10_dual_openpi_jax_ws_async.sh"
).resolve()
DUAL_OPENPI_JAX_WS_SERVE_SCRIPT = (
    REPO_ROOT
    / ".."
    / "scripts/o10/dual_arm/serve_openpi_jax_policy.sh"
).resolve()
RIGHT_PI05_MULTI_LORA_SCRIPT = (
    REPO_ROOT
    / ".."
    / "scripts/o10/right_arm/infer_o10_right_pi05_multi_lora.sh"
).resolve()
RIGHT_PI05_FULLFT_MERGED_SCRIPT = (
    REPO_ROOT
    / ".."
    / "scripts/o10/right_arm/infer_o10_right_pi05_fullft_merged.sh"
).resolve()
RIGHT_PI05_FULLFT_SWITCH_SCRIPT = (
    REPO_ROOT
    / ".."
    / "scripts/o10/right_arm/switch_o10_right_fullft_task.sh"
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


def test_dual_pi05_fullft_async_rtc_script_uses_training_model_override():
    source = DUAL_PI05_FULLFT_ASYNC_RTC_SCRIPT.read_text(encoding="utf-8")

    assert "arm-hand-teleop-pi0/bin/python" in source
    assert "ARM_HAND_TELEOP_DUAL_PI05_FULLFT_MODEL" in source
    assert "o10_dual_pi05_fullft_infer.yaml" in source
    assert 'fps="${ARM_HAND_TELEOP_ASYNC_FPS:-30}"' in source
    assert 'ARM_HAND_TELEOP_RTC_ENABLED="${ARM_HAND_TELEOP_RTC_ENABLED:-1}"' in source
    assert "async_policy_server" in source
    assert "--policy pi05" in source
    assert "--async_infer" in source


def test_dual_openpi_jax_async_script_separates_robot_and_policy_envs():
    source = DUAL_OPENPI_JAX_ASYNC_SCRIPT.read_text(encoding="utf-8")

    assert "arm-hand-teleop-pi0/bin/python" in source
    assert "ARM_HAND_TELEOP_OPENPI_JAX_PYTHON" in source
    assert "openpi-jax/bin/python" in source
    assert "ARM_HAND_TELEOP_OPENPI_CONFIG" in source
    assert "pi05_parcel_sorting" in source
    assert "mymodels/agi_arm_bot/jax/pi05/parcel_sorting_v21_full/130000" in source
    assert "ARM_HAND_TELEOP_OPENPI_DEFAULT_PROMPT" in source
    assert "sort the express parcels" in source
    assert 'ARM_HAND_TELEOP_RTC_ENABLED="${ARM_HAND_TELEOP_RTC_ENABLED:-1}"' in source
    assert 'ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON="${ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON:-10}"' in source
    assert 'ARM_HAND_TELEOP_RTC_PREFIX_ATTENTION_SCHEDULE="${ARM_HAND_TELEOP_RTC_PREFIX_ATTENTION_SCHEDULE:-EXP}"' in source
    assert '[[ ! -d "$openpi_checkpoint/params" ]]' in source
    assert '[[ ! -d "$openpi_checkpoint/assets" ]]' in source
    assert "openpi_config.get_config(config_name)" in source
    assert '"$arm_hand_teleop_python_bin" \\' in source
    assert "async_policy_server" in source
    assert "--policy openpi_jax" in source
    assert "--async_infer" in source


def test_dual_openpi_jax_ws_async_script_uses_official_openpi_server():
    source = DUAL_OPENPI_JAX_WS_ASYNC_SCRIPT.read_text(encoding="utf-8")

    assert "arm-hand-teleop-pi0/bin/python" in source
    assert "serve_openpi_jax_policy.sh" in source
    assert "openpi-client/src" in source
    assert "openpi_jax_ws" in source
    assert "--server_address \"$server_address\"" in source
    assert 'num_episodes="${ARM_HAND_TELEOP_NUM_EPISODES:-100000}"' in source
    assert 'episode_time_sec="${ARM_HAND_TELEOP_EPISODE_TIME_SEC:-3600}"' in source
    assert "--num_episodes \"$num_episodes\"" in source
    assert "--episode_time_sec \"$episode_time_sec\"" in source
    assert "async_policy_server" not in source
    assert 'ARM_HAND_TELEOP_RTC_ENABLED="${ARM_HAND_TELEOP_RTC_ENABLED:-1}"' in source


def test_dual_openpi_jax_ws_serve_script_runs_openpi_serve_policy_with_rtc():
    source = DUAL_OPENPI_JAX_WS_SERVE_SCRIPT.read_text(encoding="utf-8")

    assert "openpi-jax/bin/python" in source
    assert "scripts/serve_policy.py \\" in source
    assert "policy:checkpoint" in source
    assert "--policy.config=\"$openpi_config\"" in source
    assert "--policy.dir=\"$openpi_checkpoint\"" in source
    assert "mymodels/agi_arm_bot/jax/pi05/parcel_sorting_v21_full/130000" in source
    assert "--default-prompt=\"$default_prompt\"" in source
    assert 'rtc_flag="--rtc-enabled"' in source
    assert 'rtc_flag="--no-rtc-enabled"' in source
    assert "--rtc-actions-per-chunk=\"$actions_per_chunk\"" in source
    assert "--rtc-prefix-attention-schedule=" in source


def test_right_pi05_multi_lora_script_defaults_to_pi0_python_env():
    source = RIGHT_PI05_MULTI_LORA_SCRIPT.read_text(encoding="utf-8")

    assert "arm-hand-teleop-pi0/bin/python" in source
    assert "${ARM_HAND_TELEOP_PYTHON:-" in source


def test_right_pi05_multi_lora_script_defaults_to_training_fps():
    source = RIGHT_PI05_MULTI_LORA_SCRIPT.read_text(encoding="utf-8")

    assert 'fps="${ARM_HAND_TELEOP_ASYNC_FPS:-30}"' in source


def test_right_pi05_fullft_merged_script_starts_async_server_with_rtc_opt_in():
    source = RIGHT_PI05_FULLFT_MERGED_SCRIPT.read_text(encoding="utf-8")

    assert "arm-hand-teleop-pi0/bin/python" in source
    assert "o10_right_pi05_fullft_merged_infer.yaml" in source
    assert "pi05_agi_arm_tissue_move_right_arm_merged_20260512_fullft_bs16_ckpt10000_full" in source
    assert 'fps="${ARM_HAND_TELEOP_ASYNC_FPS:-30}"' in source
    assert "async_policy_server" in source
    assert "--policy pi05" in source
    assert "--async_infer" in source
    assert 'ARM_HAND_TELEOP_RTC_ENABLED="${ARM_HAND_TELEOP_RTC_ENABLED:-0}"' in source


def test_right_pi05_fullft_switch_script_writes_text_task_profile():
    source = RIGHT_PI05_FULLFT_SWITCH_SCRIPT.read_text(encoding="utf-8")

    assert "o10_right_pi05_fullft_merged_tasks.yaml" in source
    assert "switch_lora_task" in source
    assert "black_to_yellow|yellow_to_black" in source
