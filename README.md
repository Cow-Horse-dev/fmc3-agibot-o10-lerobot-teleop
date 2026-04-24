# arm-hand-teleop

Agibot O10 单臂/双臂 + OmniHand 灵巧手 + RealSense 相机的遥操作、数据采集、回放和策略推理系统。

基于 `lerobot_play`，接入 Pico VR 头显 + 宇叠手套作为输入设备。手模式支持宇叠手套（`glove`）与 VR 扳机手势（`trigger_gesture`，通过 yaml 中 `teleop.hand_mode` 切换）。

## 目录说明

- `configs/` — 控制、录制、推理、回放的 yaml/json 配置
- `scripts/` — 日常启动脚本和工具
- `qiuzhi/` — vendored 的 `lerobot_play` 代码和测试
- `yudie/` — 手套、OmniHand、HDService、HDWeb 相关代码和 SDK
- `run_lerobot_play.py` — 项目统一入口

## 环境说明

日常启动脚本时不需要手动 `conda activate`，`scripts/o10/` 和 `scripts/services/` 下的 `.sh` 会自动寻找 Python 解释器：

```
ARM_HAND_TELEOP_PYTHON > .venv/bin/python > ~/miniconda3/envs/arm-hand-teleop/bin/python > python3
```

需要手动进虚拟环境的场景：手动跑 `python`、装包、跑测试。

```bash
conda activate arm-hand-teleop
```

显式指定解释器：

```bash
ARM_HAND_TELEOP_PYTHON=/your/python ./scripts/o10/right_arm/control_o10_right.sh
```

## 常用启动命令

```bash
cd ~/workspace/arm-hand-teleop

# 手套服务
./scripts/services/start_hdservice.sh              # 前台启动
./scripts/services/start_hdservice.sh --background # 后台启动
./scripts/services/stop_hdservice.sh
./scripts/services/restart_hdservice.sh
./scripts/services/start_hdweb.sh                  # HDWeb 仪表盘
./scripts/services/stop_hdweb.sh

# 右臂（单臂）
./scripts/o10/right_arm/control_o10_right.sh            # 实时遥操作
./scripts/o10/right_arm/record_o10_right.sh             # 数据录制
./scripts/o10/right_arm/replay_o10_right.sh             # 轨迹回放
./scripts/o10/right_arm/infer_o10_right.sh              # 策略推理（GPU）
./scripts/o10/right_arm/infer_o10_right_cpu.sh          # 策略推理（CPU）

# 左臂（单臂）
./scripts/o10/left_arm/control_o10_left.sh              # 实时遥操作
./scripts/o10/left_arm/record_o10_left.sh               # 数据录制
./scripts/o10/left_arm/replay_o10_left.sh               # 轨迹回放
./scripts/o10/left_arm/infer_o10_left.sh                # 策略推理

# 双臂
./scripts/o10/dual_arm/control_o10_dual.sh              # 实时遥操作
./scripts/o10/dual_arm/record_o10_dual.sh               # 数据录制
./scripts/o10/dual_arm/replay_o10_dual.sh               # 轨迹回放
./scripts/o10/dual_arm/infer_o10_dual.sh                # 策略推理
```

## 工具脚本

```bash
# 读取当前臂+手关节角度，保存为复位姿态 JSON
python scripts/tools/save_reset_pose.py
python scripts/tools/save_reset_pose.py --output configs/reset_poses/o10_dual_reset.json

# 设置臂+手到指定关节角度，用于查看姿态
python scripts/tools/set_pose.py --from-json configs/reset_poses/o10_dual_reset.json
python scripts/tools/set_pose.py --arm 0 0 0 0 0 0
python scripts/tools/set_pose.py --read-only   # 只读取当前姿态
```

## 配置文件

常用配置：

右臂：
- [o10_right_control.yaml](configs/right_arm/o10_right_control.yaml) — 实时控制
- [o10_right_record.yaml](configs/right_arm/o10_right_record.yaml) — 数据录制
- [o10_right_replay.yaml](configs/right_arm/o10_right_replay.yaml) — 轨迹回放
- [o10_right_infer.yaml](configs/right_arm/o10_right_infer.yaml) — 策略推理

左臂：
- [o10_left_control.yaml](configs/left_arm/o10_left_control.yaml) / [record](configs/left_arm/o10_left_record.yaml) / [replay](configs/left_arm/o10_left_replay.yaml) / [infer](configs/left_arm/o10_left_infer.yaml)

双臂：
- [o10_dual_control.yaml](configs/dual_arm/o10_dual_control.yaml) / [record](configs/dual_arm/o10_dual_record.yaml) / [replay](configs/dual_arm/o10_dual_replay.yaml) / [infer](configs/dual_arm/o10_dual_infer.yaml)

复位姿态：
- [o10_dual_reset.json](configs/reset_poses/o10_dual_reset.json) — 左右两侧 + 多手势（`pinch`、`tripod` 等）统一保存，所有模式共用

策略专用推理配置：

- [o10_right_infer_act_pick_blue_camera_into_black_tray.yaml](configs/right_arm/policies/o10_right_infer_act_pick_blue_camera_into_black_tray.yaml)
- [o10_right_infer_diffusion_pick_blue_camera_into_black_tray.yaml](configs/right_arm/policies/o10_right_infer_diffusion_pick_blue_camera_into_black_tray.yaml)
- [o10_right_infer_pi0_038393_pick_blue_camera_into_black_tray.yaml](configs/right_arm/policies/o10_right_infer_pi0_038393_pick_blue_camera_into_black_tray.yaml)

切换左右手时，改 yaml 里的：

- `robot.handedness` / `teleop.handedness`
- `robot.channel_id`（`null` 表示自动跟随 handedness，left→0，right→1）

## 复位姿态

复位姿态固定保存在 [o10_dual_reset.json](configs/reset_poses/o10_dual_reset.json)，包含 arm 6 关节 + hand 10 关节。

- 所有模式（控制、录制、回放、推理）启动时从 JSON 加载复位目标
- 按 `Y` 键复位时，臂和手一起回到 JSON 中的姿态
- 运行过程中不会自动覆盖这个文件
- 需要更新复位姿态时，用 `python scripts/tools/save_reset_pose.py` 手动保存

## 控制逻辑

- 按住 Pico 扳机，臂和手才允许动
- `Y` 键回复位姿态（臂+手一起回）
- 数据流：Pico VR (WebRTC, 8000/8001) → 臂 IK；宇叠手套 (UDP, 7777) → 手关节映射

## 数据录制

录制格式：LeRobot `v3.0`。默认目录：

```
~/workspace/dataset/Robot/agi_arm_bot
```

手动指定目录：

```bash
./scripts/o10/right_arm/record_o10_right.sh \
  --dataset.root ~/workspace/dataset/Robot/agi_arm_bot \
  --dataset.repo_id my_dataset
```

录制内容：

单臂：
- `action`（16D）：臂 6 关节 + 手 10 关节
- `observation.state`（23D）：臂 6 关节 + 手 10 关节 + 末端位姿 7D
- `observation.images.right` / `observation.images.top`：相机图像

双臂：
- `action`（32D）：左侧 16D + 右侧 16D，键名前缀 `left.` / `right.`
- `observation.state`（46D）：双侧 16D 关节 + 7D 末端位姿，前缀同上（`include_eef_pose: false` 时退化为 32D）
- `observation.images.top` / `left_wrist` / `right_wrist`：顶部 + 双腕 RealSense
- 可选触觉：yaml 中 `robot.tactile_mode` 设为 `7d` / `80d` / `130d`

同步方式为软件级对齐：臂和手状态在同一轮 `get_observation()` 读取，相机和手套取后台线程最新值。

## 测试

```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_agibot_o10.py
```

## 常见问题

- OpenCV 预览窗口报错 → 无 GUI 环境下设 `run.display_data: false`
- 录制目录已存在 → 换 `repo_id` 或删掉旧空目录
- 手套连不上 → 确认 HDService 已启动、HDWeb 能看到配对、yaml 里 handedness 正确
- 顶部 USB 相机（LRCP 500W 等）`Error reading frame` 刷屏 → yaml 里该相机加 `fourcc: MJPG`，让 OpenCV 跳过 YUYV 自动协商
- 双臂方向不对 → 先用单左/单右脚本验证 `port: can0` / `can1` 分别对应哪只机械臂，必要时对调 yaml 里的 `left.port` / `right.port`
- 手 CANFD 超时 → 检查手电源、USB-CANFD 线、重插 USB
