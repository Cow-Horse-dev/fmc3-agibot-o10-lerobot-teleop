# arm-hand-teleop

Agibot O10 单臂 + OmniHand 灵巧手 + RealSense 相机的遥操作、数据采集、回放和策略推理系统。

基于 `lerobot_play`，接入 Pico VR 头显 + 宇叠手套作为输入设备。

## 目录说明

- `configs/` — 控制、录制、推理、回放的 yaml/json 配置
- `scripts/` — 日常启动脚本和工具
- `qiuzhi/` — vendored 的 `lerobot_play` 代码和测试
- `yudie/` — 手套、OmniHand、HDService、HDWeb 相关代码和 SDK
- `run_lerobot_play.py` — 项目统一入口

## 环境说明

日常启动脚本时不需要手动 `conda activate`，`scripts/*.sh` 会自动寻找 Python 解释器：

```
ARM_HAND_TELEOP_PYTHON > .venv/bin/python > ~/miniconda3/envs/arm-hand-teleop/bin/python > python3
```

需要手动进虚拟环境的场景：手动跑 `python`、装包、跑测试。

```bash
conda activate arm-hand-teleop
```

显式指定解释器：

```bash
ARM_HAND_TELEOP_PYTHON=/your/python ./scripts/control_o10_right.sh
```

## 常用启动命令

```bash
cd ~/workspace/arm-hand-teleop

# 手套服务
./scripts/start_hdservice.sh              # 前台启动
./scripts/start_hdservice.sh --background # 后台启动
./scripts/stop_hdservice.sh
./scripts/restart_hdservice.sh
./scripts/start_hdweb.sh                  # HDWeb 仪表盘
./scripts/stop_hdweb.sh

# 机械臂 + 手控制
./scripts/control_o10_right.sh            # 实时遥操作
./scripts/record_o10_right.sh             # 数据录制
./scripts/replay_o10_right.sh             # 轨迹回放
./scripts/infer_o10_right.sh              # 策略推理（GPU）
./scripts/infer_o10_right_cpu.sh          # 策略推理（CPU）
```

## 工具脚本

```bash
# 读取当前臂+手关节角度，保存为复位姿态 JSON
python scripts/save_reset_pose.py
python scripts/save_reset_pose.py --output configs/o10_right_reset_pose.json

# 设置臂+手到指定关节角度，用于查看姿态
python scripts/set_pose.py --from-json configs/o10_right_reset_pose.json
python scripts/set_pose.py --arm 0 0 0 0 0 0
python scripts/set_pose.py --read-only   # 只读取当前姿态
```

## 配置文件

常用配置：

- [o10_right_control.yaml](configs/o10_right_control.yaml) — 实时控制
- [o10_right_record.yaml](configs/o10_right_record.yaml) — 数据录制
- [o10_right_replay.yaml](configs/o10_right_replay.yaml) — 轨迹回放
- [o10_right_infer.yaml](configs/o10_right_infer.yaml) — 策略推理
- [o10_right_reset_pose.json](configs/o10_right_reset_pose.json) — 复位姿态

策略专用推理配置：

- [o10_right_infer_act_pick_blue_camera_into_black_tray.yaml](configs/policies/o10_right_infer_act_pick_blue_camera_into_black_tray.yaml)
- [o10_right_infer_diffusion_pick_blue_camera_into_black_tray.yaml](configs/policies/o10_right_infer_diffusion_pick_blue_camera_into_black_tray.yaml)
- [o10_right_infer_pi0_038393_pick_blue_camera_into_black_tray.yaml](configs/policies/o10_right_infer_pi0_038393_pick_blue_camera_into_black_tray.yaml)

切换左右手时，改 yaml 里的：

- `robot.handedness` / `teleop.handedness`
- `robot.channel_id`（`null` 表示自动跟随 handedness，left→0，right→1）

## 复位姿态

复位姿态固定保存在 [o10_right_reset_pose.json](configs/o10_right_reset_pose.json)，包含 arm 6 关节 + hand 10 关节。

- 所有模式（控制、录制、回放、推理）启动时从 JSON 加载复位目标
- 按 `Y` 键复位时，臂和手一起回到 JSON 中的姿态
- 运行过程中不会自动覆盖这个文件
- 需要更新复位姿态时，用 `python scripts/save_reset_pose.py` 手动保存

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
./scripts/record_o10_right.sh \
  --dataset.root ~/workspace/dataset/Robot/agi_arm_bot \
  --dataset.repo_id my_dataset
```

录制内容：

- `action`（16D）：臂 6 关节 + 手 10 关节
- `observation.state`（23D）：臂 6 关节 + 手 10 关节 + 末端位姿 7D
- `observation.images.right` / `observation.images.top`：相机图像

同步方式为软件级对齐：臂和手状态在同一轮 `get_observation()` 读取，相机和手套取后台线程最新值。

## 测试

```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_agibot_o10.py
```

## Docker 迁移

见 [DOCKER_MIGRATION.md](DOCKER_MIGRATION.md)。

## 常见问题

- OpenCV 预览窗口报错 → 无 GUI 环境下设 `run.display_data: false`
- 录制目录已存在 → 换 `repo_id` 或删掉旧空目录
- 手套连不上 → 确认 HDService 已启动、HDWeb 能看到配对、yaml 里 handedness 正确
- 手 CANFD 超时 → 检查手电源、USB-CANFD 线、重插 USB
