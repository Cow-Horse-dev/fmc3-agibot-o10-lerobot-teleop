# arm-hand-teleop

Agibot O10 单臂/双臂 + OmniHand 灵巧手 + RealSense/USB 相机的遥操作、数据采集、回放和策略推理系统。

项目基于 vendored `lerobot_play`，主要输入设备是 Pico VR 手柄/腕部位姿，手部输入可使用宇叠手套（`glove`）或 VR 扳机手势（`trigger_gesture`）。

## 目录说明

- `configs/`：控制、录制、推理、回放配置，任务专用模型配置，以及复位姿态 JSON。
- `scripts/`：日常启动脚本、HDService/HDWeb 服务脚本、训练脚本和工具脚本。
- `qiuzhi/`：vendored `lerobot_play` 代码和 Python 回归测试。
- `yudie/`：宇叠手套、OmniHand、HDService、HDWeb 相关代码和 SDK。
- `tests/`：根目录手部、触觉、MediaPipe 和 README 命令检查脚本，部分是人工硬件 demo。
- `run_lerobot_play.py`：项目统一入口，所有 O10 脚本都包装它。

## 环境与解释器

日常使用脚本时通常不需要手动 `conda activate`。`scripts/o10/` 和 `scripts/services/` 下的 shell 脚本会按以下顺序寻找 Python：

```text
ARM_HAND_TELEOP_PYTHON > .venv/bin/python > ~/miniconda3/envs/arm-hand-teleop/bin/python > /opt/conda/envs/arm-hand-teleop/bin/python > python3 > python
```

需要手动运行 Python、装包或跑测试时再进入环境：

```bash
conda activate arm-hand-teleop
```

也可以显式指定解释器：

```bash
ARM_HAND_TELEOP_PYTHON=/your/python ./scripts/o10/right_arm/control_o10_right.sh
```

测试依赖 `pytest`，如环境里没有可安装：

```bash
conda activate arm-hand-teleop
pip install pytest
```

## 统一入口

推荐日常使用 `scripts/o10/.../*.sh`。需要直接调用入口时注意参数名不同：

```bash
python run_lerobot_play.py help

# control 使用 --config_path
python run_lerobot_play.py control --config_path configs/right_arm/o10_right_control.yaml

# record / replay / infer 使用 --yaml
python run_lerobot_play.py record --yaml configs/right_arm/o10_right_record.yaml
python run_lerobot_play.py replay --yaml configs/right_arm/o10_right_replay.yaml
python run_lerobot_play.py infer  --yaml configs/right_arm/o10_right_infer.yaml

# 训练和异步策略服务
python run_lerobot_play.py train [lerobot-train args]
python run_lerobot_play.py async_policy_server [args]

# 其他工具入口
python run_lerobot_play.py set_pose [args]
python run_lerobot_play.py save_reset_pose [args]
python run_lerobot_play.py save_dual_reset_pose [args]
```

## 常用启动命令

先进入项目根目录：

```bash
cd ~/workspace/arm-hand-teleop
```

### 手套服务

`hand_mode: glove` 需要先启动 HDService；`trigger_gesture` 不需要手套服务。

```bash
./scripts/services/start_hdservice.sh              # 前台启动
./scripts/services/start_hdservice.sh --background # 后台启动
./scripts/services/stop_hdservice.sh
./scripts/services/restart_hdservice.sh

./scripts/services/start_hdweb.sh                  # HDWeb 仪表盘
./scripts/services/stop_hdweb.sh
```

### 单右臂

```bash
./scripts/o10/right_arm/control_o10_right.sh       # 实时遥操作
./scripts/o10/right_arm/record_o10_right.sh        # 数据录制
./scripts/o10/right_arm/replay_o10_right.sh        # 轨迹回放
./scripts/o10/right_arm/infer_o10_right.sh         # GPU 策略推理
./scripts/o10/right_arm/infer_o10_right_cpu.sh     # CPU 策略推理示例
```

### 单左臂

```bash
./scripts/o10/left_arm/control_o10_left.sh         # 实时遥操作
./scripts/o10/left_arm/record_o10_left.sh          # 数据录制
./scripts/o10/left_arm/replay_o10_left.sh          # 轨迹回放
./scripts/o10/left_arm/infer_o10_left.sh           # 策略推理
```

### 双臂

```bash
./scripts/o10/dual_arm/control_o10_dual.sh         # 实时遥操作
./scripts/o10/dual_arm/record_o10_dual.sh          # 数据录制
./scripts/o10/dual_arm/replay_o10_dual.sh          # 轨迹回放
./scripts/o10/dual_arm/infer_o10_dual.sh           # 策略推理
./scripts/o10/dual_arm/async_policy_server_o10_dual.sh # PI0/PI0.5 异步策略服务
```

## Pico 控制逻辑

当前配置和代码对齐如下。

| 模式 | 运动输入 | 使能 | 停止 + 复位 | 按住门控 |
|---|---|---|---|---|
| 左臂单臂 | 左手柄控制左臂/左手 | 右手柄 `A` | 右手柄 `B` | 右手柄 `RTr` |
| 右臂单臂 | 右手柄控制右臂/右手 | 左手柄 `X` | 左手柄 `Y` | 左手柄 `LTr` |
| 双臂 | 左手柄控制左臂/左手，右手柄控制右臂/右手 | 左手柄 `X` | 左手柄 `Y` | 左手柄 `LTr` |

说明：

- 先按“使能”进入 teleop 状态；只有同时按住“门控扳机”时，臂 IK 和手控制才会输出跟随。
- 单臂模式中，工作手柄只负责对应臂/手的运动输入；对侧手柄负责使能、复位和门控。
- 双臂配置中 `teleop.arm_trigger_mode: left`，因此双臂双手统一由左手柄 `X/Y/LTr` 门控。
- 双臂 `arm_trigger_mode` 其他可选值：
  - `left`：按住 `LTr`，双臂一起跟随（当前默认）。
  - `right`：按住 `RTr`，双臂一起跟随。
  - `both`：同时按住 `LTr + RTr`，双臂才跟随。
  - `split`：左臂看 `LTr`，右臂看 `RTr`。

## 手部控制模式

手部控制分两层配置：`hand_mode` 选择“手从哪里来”，`hand_action_mode` 选择“手以什么维度写入 action / 下发给机器人”。

### 手部输入来源：`teleop.hand_mode`

- `glove`：使用 HDService + 宇叠手套，手指关节实时跟随。使用前必须先启动 HDService，并在 HDWeb 里确认对应左右手在线。
- `trigger_gesture`：不使用手套，用 VR 手柄 grip 控制预设手势开合。默认 `open`，按下工作侧 grip 或 grip 轴值超过阈值后切到 `closed`。

`trigger_gesture` 细节：

- 单臂左臂：左手柄控制左臂/左手运动，因此手势抓握看左手柄 `LG` / `leftGrip`。
- 单臂右臂：右手柄控制右臂/右手运动，因此手势抓握看右手柄 `RG` / `rightGrip`。
- 双臂：左手看 `LG` / `leftGrip`，右手看 `RG` / `rightGrip`。
- 单臂 grip 阈值硬编码为 `0.2`；双臂阈值可用 `teleop.grasp_grip_threshold` 覆盖，默认 `0.2`。
- `teleop.trigger_gesture` 选择闭合姿态形状，常用 `pinch` / `tripod`。
- 双臂可在 `teleop.left.trigger_gesture` / `teleop.right.trigger_gesture` 里为左右手分别指定不同手势。

### 手部 action 维度：`hand_action_mode`

- `dexterous_10d`：10D 灵巧手关节控制。action/state 中保留 O10 手的 10 个关节，适合完整手指遥操作和录制。
- `gripper_1d`：1D 夹爪控制。action 中只保留 `gripper.pos`，运行时按 `gripper_gesture` 和 reset pose 的 `open` / `closed` 姿态映射回 O10 手 10D 关节。

`hand_mode` 和 `hand_action_mode` 可以组合使用：

| 输入来源 | action 维度 | 效果 |
|---|---|---|
| `glove` | `dexterous_10d` | 手套实时控制 10D 手指关节，录制完整 10D 手动作 |
| `glove` | `gripper_1d` | 手套先映射成 10D，再投影成 1D `gripper.pos` 录制/控制 |
| `trigger_gesture` | `dexterous_10d` | 手柄 grip 在预设 `open/closed` 两个 10D 手势间切换 |
| `trigger_gesture` | `gripper_1d` | 手柄 grip 直接控制 1D `gripper.pos`，再还原成预设手势 |

`control` 和 `record` 时，`teleop.hand_action_mode` 会默认跟随 `robot.hand_action_mode`；如果两个都写，建议保持一致。`replay` / `infer` 没有 teleop 手部输入，只按 `robot.hand_action_mode` 解释数据集或策略输出。

## 配置文件

### 左臂

- `configs/left_arm/o10_left_control.yaml`：实时控制。`controller_side: right`，`wrist_pose_source: left`，相机 `top + left_wrist`。
- `configs/left_arm/o10_left_record.yaml`：数据录制。`controller_side: right`，`wrist_pose_source: left`，相机 `top + left`。
- `configs/left_arm/o10_left_replay.yaml`：轨迹回放。
- `configs/left_arm/o10_left_infer.yaml`：策略推理。相机 key 与左臂录制 schema 保持一致：`top + left`。

### 右臂

- `configs/right_arm/o10_right_control.yaml`：实时控制。`controller_side: left`，`wrist_pose_source: right`，相机 `top + right_wrist`。
- `configs/right_arm/o10_right_record.yaml`：数据录制。`controller_side: left`，`wrist_pose_source: right`，相机 `top + right`。
- `configs/right_arm/o10_right_replay.yaml`：轨迹回放。
- `configs/right_arm/o10_right_infer.yaml`：GPU 策略推理。相机 key 与右臂录制 schema 保持一致：`top + right`。
- `configs/right_arm/o10_right_infer_cpu.yaml`：CPU 推理示例，默认 `policy: act`。

### 双臂

- `configs/dual_arm/o10_dual_control.yaml`：实时控制。`arm_trigger_mode: left`，左右 wrist pose 分别来自 `left/right`。
- `configs/dual_arm/o10_dual_record.yaml`：数据录制。默认 `include_eef_pose: false`，`tactile_mode: "none"`。
- `configs/dual_arm/o10_dual_replay.yaml`：轨迹回放。
- `configs/dual_arm/o10_dual_infer.yaml`：策略推理。必须与双臂录制 schema 对齐：`include_eef_pose: false`，`tactile_mode: "none"`，相机 `top + left_wrist + right_wrist`。
- `configs/dual_arm/models/*.yaml`：任务专用双臂推理配置，当前包含 camera-pen-touch 的 `act`、`diffusion`、`pi0`、`pi05` 版本；这些文件固定了对应训练 schema 和本机模型路径。

### 复位姿态

- `configs/reset_poses/o10_dual_reset.json`：统一复位姿态文件，结构如下（所有 O10 控制、录制、回放、推理配置默认共用）：
  - `arm.left` / `arm.right`：左右臂 6 个关节的目标角度。
  - `hand.feature_names`：手部关节顺序（10 维）。
  - `gestures.<name>.<side>.open|closed`：每个手势（默认已提供 `pinch`、`tripod`）左右手的 10 维 `open` / `closed` 关节值。YAML 的 `reset_gesture` 字段用来指定 `<name>`。
- 运行时只读不写，不会被自动覆盖。需要更新时手动编辑此 JSON（下文 "工具脚本" 里的 `save_*` 只输出辅助 JSON，不直接写回这份文件）。

## 数据流和硬件通道

- Pico WebRTC 进程发布：
  - 位姿：`tcp://localhost:8000`
  - 按键/扳机：`tcp://localhost:8001`
- Pico 头显里的 VRControl / VR 控制页面需要填写主机 IPv4 地址，端口保持配置里的 `8000/8001`：
  - 主机 WiFi IP：`192.168.1.111`（网卡 `wlo1`）
  - 主机有线 IP：`192.168.1.138`（网卡 `enp4s0`）
  - Pico 和主机连同一个 WiFi 时优先填 WiFi IP；如果 Pico 所在网络能访问主机有线网段，则填有线 IP。
  - 不要填 `127.0.0.1`、Docker、Tailscale 或 `198.18.*` 这类虚拟网卡地址。
  - IP 变化时用 `ip -br addr show wlo1 enp4s0` 重新确认。
- 宇叠手套：HDService 由脚本设置 `HD_UDP_TARGET=127.0.0.1:5555`，O10 teleop 在本机 `5555` 接收；仅 `hand_mode: glove` 使用。
- 臂 CAN：当前硬件约定为左臂固定 `can0`、右臂固定 `can1`，单臂和双臂 YAML 都应保持这个映射。
- 手 CANFD：`channel_mode: multiChannel`，`channel_id: null` 时自动按 handedness 选择，`left -> 0`，`right -> 1`。

## 相机配置

- 单臂 control 使用双臂配置里的 wrist 相机命名：
  - 左臂：`top + left_wrist`
  - 右臂：`top + right_wrist`
- 单臂 record/infer 使用数据集 schema 命名：
  - 左臂：`top + left`
  - 右臂：`top + right`
- 双臂 control/record/infer 使用：`top + left_wrist + right_wrist`。
- 顶部 USB 相机默认使用 `fourcc: MJPG`，避免 OpenCV 自动协商到不稳定格式。
- `robot.allow_camera_read_failures: true` 适合 control/infer 场景：相机启动失败会跳过该相机，读帧失败时有缓存用缓存、无缓存用全零帧。record 建议保持 `false`，避免录进残缺数据。

## 数据录制

录制格式是 LeRobot `v3.0`。默认数据集根目录：

```text
~/workspace/dataset/Robot/agi_arm_bot
```

常用录制：

```bash
./scripts/o10/right_arm/record_o10_right.sh
./scripts/o10/left_arm/record_o10_left.sh
./scripts/o10/dual_arm/record_o10_dual.sh
```

覆盖数据集目录/名称：

```bash
./scripts/o10/right_arm/record_o10_right.sh \
  --dataset.root ~/workspace/dataset/Robot/agi_arm_bot \
  --dataset.repo_id my_dataset
```

默认 `dexterous_10d` 时，`action` 只含臂关节 + 手 10D 关节：

| 模式 | action 维度 | 组成 |
|---|---:|---|
| 单臂 | 16D | 臂 6 + 手 10 |
| 双臂 | 32D | `left.*` 16D + `right.*` 16D |

`gripper_1d` 时，手部 action 会压缩成 1D：

| 模式 | action 维度 | 组成 |
|---|---:|---|
| 单臂 | 7D | 臂 6 + `gripper.pos` |
| 双臂 | 14D | 左臂 6 + `left.gripper.pos`，右臂 6 + `right.gripper.pos` |

### O10 gripper_1d 映射

O10 当前可使用 `hand_action_mode: gripper_1d` 录制更紧凑的 action。单臂录制数据是 7D：6 个 arm joint + `gripper.pos`；双臂录制数据是 14D：左臂 6 个 arm joint + `left.gripper.pos`，右臂 6 个 arm joint + `right.gripper.pos`。

录制侧仍先得到每只 O10 手的 10D 手指关节，再按配置的 `gripper_gesture`、`handedness` 和 reset pose 里的 `open` / `closed` 姿态，把当前 10D 手指关节投影到 `0..1` 的 `gripper.pos`。回放侧读取数据集里的 `left.gripper.pos` / `right.gripper.pos`，按同样的 `gripper_gesture` 和 `handedness`，从对应 `open` / `closed` pose 线性插值还原为 10D 手指关节并下发到 O10 手。

当前双臂配置在 `configs/dual_arm/o10_dual_record.yaml` 和 `configs/dual_arm/o10_dual_replay.yaml`：左手使用 `tripod`，右手使用 `pinch`。20260427 数据集 replay 基本能对上，说明录制/回放映射链路没问题。

`observation.state` 由 `robot.hand_action_mode`、`robot.include_eef_pose` 和 `robot.tactile_mode` 共同决定。`gripper_1d` 模式只保留臂关节 + `gripper.pos`，不会额外写入 EEF pose。

| hand_action_mode | include_eef_pose | tactile_mode | 单臂 state | 双臂 state |
|---|---|---|---:|---:|
| `dexterous_10d` | `false` | `none` | 16D（当前单臂 record 默认） | 32D |
| `dexterous_10d` | `true` | `none` | 23D | 46D |
| `dexterous_10d` | `false` | `7d` | 23D | 46D |
| `dexterous_10d` | `true` | `7d` | 30D | 60D |
| `dexterous_10d` | `false` | `80d` | 96D | 192D |
| `dexterous_10d` | `false` | `130d` | 146D | 292D |
| `gripper_1d` | 任意 | `none` | 7D | 14D（当前双臂 record 默认） |
| `gripper_1d` | 任意 | `7d` | 14D | 28D |
| `gripper_1d` | 任意 | `80d` | 87D | 174D |
| `gripper_1d` | 任意 | `130d` | 137D | 274D |

## 推理

支持策略：

- `act`
- `diffusion`
- `pi0`
- `pi05`
- `pi0_fast`
- `sac`
- `smolvla`
- `groot`
- `tdmpc`
- `vqbet`
- `wall_x`
- `xvla`

常用命令：

```bash
./scripts/o10/left_arm/infer_o10_left.sh
./scripts/o10/right_arm/infer_o10_right.sh
./scripts/o10/right_arm/infer_o10_right_cpu.sh
./scripts/o10/dual_arm/infer_o10_dual.sh
```

任务专用双臂推理脚本：

```bash
./scripts/o10/dual_arm/infer_o10_dual_act_camera_pen_touch_20260427.sh
./scripts/o10/dual_arm/infer_o10_dual_diffusion_camera_pen_touch_20260427.sh
./scripts/o10/dual_arm/infer_o10_dual_pi0_camera_pen_touch_20260427.sh
```

`pi0` / `pi05` 这类 `async_infer: true` 的配置需要先启动本项目适配过的异步策略服务端，服务默认监听 `localhost:8080`：

```bash
./scripts/o10/dual_arm/async_policy_server_o10_dual.sh
```

推理前检查：

- `infer.model_path` 必须存在，且目录内必须有 `config.json`；权重通常是 `model.safetensors` 或 `pytorch_model.bin`。
- `infer.policy` 必须和模型类型一致。
- `infer.device` 可用 `cuda` 或 `cpu`；CPU 只适合小模型/调试。
- `robot.include_eef_pose`、`robot.tactile_mode`、相机 key 必须与训练数据集一致，否则策略输入 schema 会不匹配。
- `infer.save_data: true` 时推理过程会保存为 LeRobot 数据集；`save_path` 为空时自动写到 `~/.cache/huggingface/lerobot/...`。
- flow-matching 策略（如 `pi0`、`pi05`、`smolvla`）可在 YAML 中使用 `rtc:` 配置 Real-Time Chunking；仅这些策略会读取该块。

## 回放

回放使用各自 replay YAML 里的 `dataset.root` 指向已有数据集：

```bash
./scripts/o10/left_arm/replay_o10_left.sh
./scripts/o10/right_arm/replay_o10_right.sh
./scripts/o10/dual_arm/replay_o10_dual.sh
```

更换回放数据集时修改对应 YAML 的 `dataset.root` / `dataset.repo_id`。

## 工具脚本

这些脚本可以直接跑，也可以通过入口调用（仅前 3 个走 `run_lerobot_play.py`）：

```bash
python run_lerobot_play.py set_pose [args]              # = scripts/tools/set_pose.py
python run_lerobot_play.py save_reset_pose [args]       # = scripts/tools/save_reset_pose.py
python run_lerobot_play.py save_dual_reset_pose [args]  # = scripts/tools/save_dual_reset_pose.py
```

常用操作：

```bash
# 读取单臂当前臂+手关节并导出 legacy 格式 JSON（诊断用，不是集中式复位文件）
python scripts/tools/save_reset_pose.py --port can1 --handedness right \
    --output configs/o10_right_reset_pose.json

# 读取双臂当前关节并导出两份 legacy 格式 JSON（左右分开）
python scripts/tools/save_dual_reset_pose.py \
    --left-port can0 --right-port can1 \
    --left-output configs/o10_left_reset_pose.json \
    --right-output configs/o10_right_reset_pose.json

# 依次为每种手势导出 per-side per-gesture 的 reset 文件（默认 pinch + tripod）
python scripts/tools/save_gesture_reset_poses.py
python scripts/tools/save_gesture_reset_poses.py --gesture pinch

# 设置臂/手到集中式 JSON 中的姿态，或只读当前姿态
python scripts/tools/set_pose.py --from-json configs/reset_poses/o10_dual_reset.json
python scripts/tools/set_pose.py --arm 0 0 0 0 0 0
python scripts/tools/set_pose.py --read-only

# 判断一次触觉成功条件：右手拇指/食指/中指均值都超过阈值
python scripts/tools/check_tactile_success.py --thumb 50 --index 40 --middle 45 --threshold 30

# 实时查看 O10 130D 触觉热力图；无 matplotlib 时可加 --backend terminal
python scripts/tools/o10_tactile_heatmap.py --hand left

# 从 LeRobot v3.0 数据集 observation.state 中删除 tactile 列，默认输出 <input>_no_tactile
python scripts/tools/strip_tactile.py --input <lerobot_dir>
python scripts/tools/strip_tactile.py --input <lerobot_dir> --output <lerobot_no_tactile_dir>

# 转换 LeRobot 数据集到 openpi 训练格式
python scripts/tools/convert_lerobot_to_openpi.py --input <lerobot_dir> --output <openpi_dir>

# 导出本地 Docker 镜像，默认镜像名 ARM_HAND_TELEOP_IMAGE 或 arm-hand-teleop:jazzy
bash scripts/tools/docker_export_image.sh
```

> `save_reset_pose.py` / `save_dual_reset_pose.py` / `save_gesture_reset_poses.py` 输出的是 legacy `groups.arm / groups.hand` 格式，**不能**直接覆盖 `configs/reset_poses/o10_dual_reset.json`。新的关节值请手动合并到集中式 JSON 的 `arm.<side>` / `gestures.<name>.<side>.open|closed` 字段里。

`convert_lerobot_to_openpi.py` 目前是转换骨架：会把 LeRobot episode 转成压缩 `npz`，但脚本里仍有 openpi 原生格式写出相关 TODO。用于正式训练前需要先确认 openpi 数据加载接口。

## 训练

`scripts/train/` 里是本地 LeRobot 训练入口，当前主要面向 AGI arm camera-pen-touch 数据集。开始新训练前先编辑脚本顶部的 `DATASET_ROOT`、`DATASET_REPO_ID`、`RUN_NAME`、`STEPS`、`BATCH_SIZE` 和 `WANDB_PROJECT`。

```bash
./scripts/train/train_act_agi_arm_camera_pen_touch.sh --dry-run
./scripts/train/train_diffusion_agi_arm_camera_pen_touch.sh --dry-run
./scripts/train/train_pi0_agi_arm_camera_pen_touch.sh --dry-run
./scripts/train/train_vqbet_agi_arm_camera_pen_touch.sh --dry-run
```

去掉 `--dry-run` 才会真正启动训练。脚本会拒绝覆盖已存在的 `OUTPUT_BASE/RUN_NAME`，每次新训练都要换新的 `RUN_NAME`。AGI arm 输出默认在：

```text
/home/phl/workspace/mymodels/agi_arm_bot/<RUN_NAME>
/home/phl/workspace/mymodels/agi_arm_bot/_logs/<RUN_NAME>_<timestamp>.log
```

训练检查点目录格式：

```text
<RUN_NAME>/checkpoints/<step>/pretrained_model
```

其他训练辅助：

```bash
./scripts/train/gr2_train.sh
screen -dmS watch_act_then_vqbet bash scripts/train/watch_act_then_train_vqbet.sh
```

## 测试和检查

```bash
# 全量 Python 回归
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests -q

# 根目录脚本/README 检查
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests -q

# 常用聚焦检查
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest tests/test_readme_tool_commands.py -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_dual_arm_config.py -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_infer_save_path.py -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_single_arm_o10_trigger_gate.py -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_dual_arm_o10_trigger_gate.py -q
```

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 用于避免 ROS/外部 pytest 插件污染。根目录 `tests/` 里有部分人工硬件 demo；缺少 `mediapipe`、CAN/相机/手套硬件时，不要把这些 demo 当作无硬件 CI 必跑项。

## 常见问题

- OpenCV 预览窗口报错：无 GUI 环境下把 `display_data` 或 `run.display_data` 设为 `false`。
- `model_path` 报不存在：检查 infer YAML 中 `infer.model_path`，必须指向 `.../pretrained_model` 目录。
- 推理输入维度不匹配：确认 infer YAML 的 `include_eef_pose`、`tactile_mode`、相机 key 与训练时 record YAML 一致。
- 顶部 USB 相机读帧不稳定：确认相机配置里有 `fourcc: MJPG`。
- control/infer 中某路相机不存在：可打开 `robot.allow_camera_read_failures: true`，程序会跳过启动失败的相机。
- record 中相机失败：不建议容错，修相机后重新录，避免数据集混入全零/旧帧。
- 手套连不上：确认 HDService 已启动、HDWeb 能看到配对、YAML `handedness` 正确。
- 手 CANFD 超时：检查手电源、USB-CANFD 线和 `channel_id`。
- 双臂视觉左右混淆：你面对机器人时，机器人自身左臂在视觉右侧；当前 CAN 映射仍是左臂 `can0`、右臂 `can1`。
- 录制目录已存在：换 `dataset.repo_id` 或删除旧空目录。
