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

测试依赖 `pytest`，不在 env 默认安装：

```bash
conda activate arm-hand-teleop
pip install pytest
```

## 直接调用统一入口

所有 `.sh` 都是对 `run_lerobot_play.py` 的包装，也可以直接调：

```bash
python run_lerobot_play.py help                                            # 列子命令
python run_lerobot_play.py {control|record|replay|infer|train} --config_path <yaml>
python run_lerobot_play.py {set_pose|save_reset_pose|save_dual_reset_pose} [args]
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
python scripts/tools/save_reset_pose.py                          # 单臂
python scripts/tools/save_reset_pose.py --output configs/reset_poses/o10_dual_reset.json
python scripts/tools/save_dual_reset_pose.py                     # 双臂（左右同时抓取）
python scripts/tools/save_gesture_reset_poses.py                 # 依次保存 pinch/tripod/... 多组手势

# 设置臂+手到指定关节角度，用于查看姿态
python scripts/tools/set_pose.py --from-json configs/reset_poses/o10_dual_reset.json
python scripts/tools/set_pose.py --arm 0 0 0 0 0 0
python scripts/tools/set_pose.py --read-only   # 只读取当前姿态

# 从录制好的 LeRobot 数据集检查触觉通道是否正确采到数据
python scripts/tools/check_tactile_success.py --dataset.root <dir>

# 把 LeRobot v3.0 数据集转成 openpi 训练格式
python scripts/tools/convert_lerobot_to_openpi.py --src <lerobot_dir> --dst <openpi_dir>
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
- `teleop.controller_side` — 哪只手柄驱动手臂（单臂时对侧手柄做 gate 按钮，见下）
- `teleop.wrist_pose_source` — `auto`/`left`/`right`，IK 位姿来源

## 可靠性 / 容错

- `robot.allow_camera_read_failures` (bool, 默认 `false`) —
  设为 `true` 时，`cam.async_read()` 抛异常不会炸 teleop 循环：
  有缓存帧就复用上一帧，没缓存就返回全零帧。适合实时 `control`
  场景下 USB 相机掉帧；`record` 模式建议保持默认 `false` 以免
  误把残缺数据录进数据集。`configs/{left,right,dual}_arm/o10_*_control.yaml`
  默认已开。

## 复位姿态

复位姿态固定保存在 [o10_dual_reset.json](configs/reset_poses/o10_dual_reset.json)，包含 arm 6 关节 + hand 10 关节。

- 所有模式（控制、录制、回放、推理）启动时从 JSON 加载复位目标
- 按 `Y` 键复位时，臂和手一起回到 JSON 中的姿态
- 运行过程中不会自动覆盖这个文件
- 需要更新复位姿态时，用 `python scripts/tools/save_reset_pose.py` 手动保存

## 控制逻辑

### 按键（Pico VR）

启动 / 停止按钮在左右手柄上对应同一侧的"字母键"，扳机是"对侧" gate：

| 模式 | 启动 | 停止 + 复位 | 臂 gate |
|---|---|---|---|
| 单右臂 (`handedness: right`) | X | Y | LTr（左扳机） |
| 单左臂 (`handedness: left`) | A | B | RTr（右扳机） |
| 双臂 | X | Y | 取决于 `teleop.arm_trigger_mode`（见下） |

- 只有按下启动键后进入 teleop 模式，按住 gate 扳机时 IK 才开始跟随。
- 手（`hand_mode: glove`）不需要手动 gate，启动后一直跟随手套。

### 双臂 `arm_trigger_mode`

- `left`（默认推荐）—— 按住 **LTr** 双臂一起跟随
- `right` —— 按住 **RTr** 双臂一起跟随
- `both` —— 同时按住 **LTr + RTr** 双臂才跟随
- `split` —— 左臂看 LTr、右臂看 RTr，分别独立

### 手模式 `hand_mode`

- `glove` —— 接 HDService + 宇叠手套，手指关节实时跟随。需要先 `start_hdservice.sh`。
- `trigger_gesture` —— 手套关掉的简化模式，手只有两个状态：
  - 默认 `open`（放开）
  - 手柄 grip 按下（`LG`/`RG`）或 grip 力 ≥ `teleop.grasp_grip_threshold`（默认 0.2） → `closed`（抓）
  - `trigger_gesture: pinch` / `tripod` 选具体手势（两种闭合姿态）。

### 数据流

- Pico VR WebRTC → `tcp://localhost:8000` (pose) + `tcp://localhost:8001` (buttons) → 臂 IK
- 宇叠手套 → UDP `0.0.0.0:7777` → 手关节映射（`hand_mode: glove` 才走）
- 手 CANFD 走 `multiChannel`（channel 0 = 左，1 = 右）；臂 CAN 见各 yaml 的 `port`（本机 can0/can1 的实际映射用单臂脚本验证）

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

`action` 固定只含关节指令（臂 + 手），不随选项变化：

| 模式 | action 维度 | 组成 |
|---|---|---|
| 单臂 | 16D | 臂 6 + 手 10 |
| 双臂 | 32D | `left.*` 16D + `right.*` 16D |

`observation.state` 随 `robot.include_eef_pose` 和 `robot.tactile_mode` 组合变化：

| include_eef_pose | tactile_mode | 单臂 state | 双臂 state |
|---|---|---|---|
| false | none | 16D | 32D |
| true  | none | 23D（+7D pose） | 46D（+2×7D pose） |
| false | 7d   | 23D（+7D 触觉均值） | **46D（+2×7D 触觉均值，当前 record 默认）** |
| true  | 7d   | 30D | 60D |
| false | 80d  | 96D（+80D 指尖） | 192D |
| false | 130d | 146D（+130D 全手） | 292D |

相机：
- 单臂：`observation.images.{top,right}`（右臂配置，左臂类似）
- 双臂：`observation.images.{top,left_wrist,right_wrist}`

同步方式为软件级对齐：臂和手状态在同一轮 `get_observation()` 读取，相机和手套取后台线程最新值。

## 测试

先装 `pytest`（见"环境说明"），然后：

```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_agibot_o10.py

# 整套一起跑时，draccus 子类注册可能因 test stub 与正式模块同名冲突
# 报 "Cannot register ... because ... is already registered"，单文件跑就没事。
```

## 常见问题

- OpenCV 预览窗口报错 → 无 GUI 环境下设 `run.display_data: false`
- 录制目录已存在 → 换 `repo_id` 或删掉旧空目录
- 手套连不上 → 确认 HDService 已启动、HDWeb 能看到配对、yaml 里 handedness 正确
- 顶部 USB 相机（LRCP 500W 等）`Error reading frame` 刷屏 → yaml 里该相机加 `fourcc: MJPG`，让 OpenCV 跳过 YUYV 自动协商
- USB 相机掉帧就退出 → 在 `control` 场景下把 `robot.allow_camera_read_failures: true` 打开（默认 yaml 已开）
- 双臂"左手柄控制了右臂" → 先排除**视觉错觉**：你面对机器人时，机器人自身的左臂在你视觉的**右**侧。单左/单右脚本各跑一次确认 `port: can0` / `can1` 真正对应哪只硬件臂；确实接反了才改 yaml 里的 `left.port` / `right.port`
- 手 CANFD 超时 → 检查手电源、USB-CANFD 线、重插 USB
- `record` 里按 Y 复位后双臂 IK 参考位姿没跟上 → 本分支已在 `record.py` 加 `_prepare_teleop_waiting_state_after_reset`，如果还遇到，检查 `teleop.pause_event` 是否被别的逻辑挂住
