# arm-hand-teleop

Agibot O10 单臂/双臂 + OmniHand 灵巧手 + RealSense/USB 相机的遥操作、数据采集、回放和策略推理系统。

项目基于 vendored `lerobot_play`，主要输入设备是 Pico VR 手柄/腕部位姿，手部输入可使用宇叠手套（`glove`）或 VR 扳机手势（`trigger_gesture`）。

## 目录说明

- `configs/`：控制、录制、推理、回放配置，以及复位姿态 JSON。
- `scripts/`：日常启动脚本、HDService/HDWeb 服务脚本和工具脚本。
- `qiuzhi/`：vendored `lerobot_play` 代码和 Python 回归测试。
- `yudie/`：宇叠手套、OmniHand、HDService、HDWeb 相关代码和 SDK。
- `run_lerobot_play.py`：项目统一入口，所有 O10 脚本都包装它。

## 环境与解释器

日常使用脚本时通常不需要手动 `conda activate`。`scripts/o10/` 和 `scripts/services/` 下的 shell 脚本会按以下顺序寻找 Python：

```text
ARM_HAND_TELEOP_PYTHON > .venv/bin/python > ~/miniconda3/envs/arm-hand-teleop/bin/python > python3
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

## 手部模式

通过各配置里的 `teleop.hand_mode` 切换：

- `glove`：使用 HDService + 宇叠手套，手指关节实时跟随；需要先启动 HDService。
- `trigger_gesture`：不使用手套，手只有 `open/closed` 两类姿态。
  - 默认 `open`。
  - 闭合条件：工作侧手柄的 grip 按键（左臂看 `LG`，右臂看 `RG`）按下，或 grip 轴值超过阈值。
    - 单臂：阈值硬编码为 `0.2`，不可通过配置修改。
    - 双臂：每侧独立判断（左手看 `LG`/`leftGrip`，右手看 `RG`/`rightGrip`），阈值可用 `teleop.grasp_grip_threshold` 覆盖，默认 `0.2`。
  - `teleop.trigger_gesture` 选择闭合姿态形状，常用 `pinch` / `tripod`。
  - 双臂可在 `teleop.left.trigger_gesture` / `teleop.right.trigger_gesture` 里为左右手分别指定不同手势。

## 配置文件

### 左臂

- `configs/left_arm/o10_left_control.yaml`：实时控制。`controller_side: left`，`wrist_pose_source: left`，相机 `top + left_wrist`。
- `configs/left_arm/o10_left_record.yaml`：数据录制。`controller_side: left`，`wrist_pose_source: left`，相机 `top + left`。
- `configs/left_arm/o10_left_replay.yaml`：轨迹回放。
- `configs/left_arm/o10_left_infer.yaml`：策略推理。相机 key 与左臂录制 schema 保持一致：`top + left`。

### 右臂

- `configs/right_arm/o10_right_control.yaml`：实时控制。`controller_side: right`，`wrist_pose_source: right`，相机 `top + right_wrist`。
- `configs/right_arm/o10_right_record.yaml`：数据录制。`controller_side: right`，`wrist_pose_source: right`，相机 `top + right`。
- `configs/right_arm/o10_right_replay.yaml`：轨迹回放。
- `configs/right_arm/o10_right_infer.yaml`：GPU 策略推理。相机 key 与右臂录制 schema 保持一致：`top + right`。
- `configs/right_arm/o10_right_infer_cpu.yaml`：CPU 推理示例，默认 `policy: act`。

### 双臂

- `configs/dual_arm/o10_dual_control.yaml`：实时控制。`arm_trigger_mode: left`，左右 wrist pose 分别来自 `left/right`。
- `configs/dual_arm/o10_dual_record.yaml`：数据录制。默认 `include_eef_pose: false`，`tactile_mode: "none"`。
- `configs/dual_arm/o10_dual_replay.yaml`：轨迹回放。
- `configs/dual_arm/o10_dual_infer.yaml`：策略推理。必须与双臂录制 schema 对齐：`include_eef_pose`、`tactile_mode`、`hand_action_mode` 和相机 key 都要与训练数据集一致。

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
- 宇叠手套：UDP `0.0.0.0:7777`，仅 `hand_mode: glove` 使用。
- 臂 CAN：当前硬件约定为左臂固定 `can0`、右臂固定 `can1`，单臂和双臂 YAML 都应保持这个映射。
- 手 CANFD：`channel_mode: multiChannel`，`channel_id: null` 时自动按 handedness 选择，`left -> 0`，`right -> 1`。

## 相机配置

- `configs/cameras/o10_cameras.yaml` 只保存 O10 腕部 RealSense 的共享参数：
  `wrist_camera_defaults`、`wrist_cameras.left_wrist/right_wrist` 和 `camera_controls`。
- 各 control/record/infer YAML 自己声明场景 camera key；腕部相机用 `left_wrist` / `right_wrist`
  引用共享设备，加载时会自动展开成完整 RealSense 配置和对应曝光控制。
- 单臂 control 使用双臂配置里的 wrist 相机命名：
  - 左臂：`top + left_wrist`
  - 右臂：`top + right_wrist`
- 单臂 record/infer 使用数据集 schema 命名：
  - 左臂：`top + left`
  - 右臂：`top + right`
- 双臂 control/record/infer 使用：`top + left_wrist + right_wrist`。
- 顶部 USB 相机属于场景配置，直接写在具体 YAML 里；默认 `fourcc: MJPG`，右臂 control 目前显式使用 `fourcc: h264`。
- 腕部 RealSense 的曝光、增益等参数也在共享配置的 `camera_controls` 里，例如右腕是 `camera_controls.right_wrist.exposure_us`。
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

`action` 固定只含关节/夹爪指令：

| 模式 | `hand_action_mode` | action 维度 | 组成 |
|---|---|---:|---|
| 单臂 | `gripper_1d` | 7D | 臂 6 + `gripper.pos` |
| 单臂 | `dexterous_10d` | 16D | 臂 6 + 手 10 |
| 双臂 | `gripper_1d` | 14D | `left.*` 7D + `right.*` 7D |
| 双臂 | `dexterous_10d` | 32D | `left.*` 16D + `right.*` 16D |

### O10 双臂 gripper_1d 映射

双臂 O10 当前可使用 `hand_action_mode: gripper_1d` 录制更紧凑的 action。录制数据是 14D：左臂 6 个 arm joint + `left.gripper.pos`，右臂 6 个 arm joint + `right.gripper.pos`。

录制侧仍先得到每只 O10 手的 10D 手指关节，再按配置的 `gripper_gesture`、`handedness` 和 reset pose 里的 `open` / `closed` 姿态，把当前 10D 手指关节投影到 `0..1` 的 `gripper.pos`。回放侧读取数据集里的 `left.gripper.pos` / `right.gripper.pos`，按同样的 `gripper_gesture` 和 `handedness`，从对应 `open` / `closed` pose 线性插值还原为 10D 手指关节并下发到 O10 手。

当前双臂配置在 `configs/dual_arm/o10_dual_record.yaml` 和 `configs/dual_arm/o10_dual_replay.yaml`：左手使用 `tripod`，右手使用 `pinch`。20260427 数据集 replay 基本能对上，说明录制/回放映射链路没问题。

`robot.tactile_mode` 只支持 `none` 和 `130d`：

- `none`：与旧的无触觉数据集一致，只录 `observation.state`、`action` 和相机。
- `130d`：触觉不再塞进 `observation.state`，而是作为 raw 传感器列独立保存。

推荐三条 raw 采集线路分开存：

| 线路 | `observation.state` | 触觉 raw key |
|---|---:|---|
| 左手单臂 `gripper_1d` | 7D | `observation.tactile.left_raw`，130D |
| 右手单臂 `gripper_1d` | 7D | `observation.tactile.right_raw`，130D |
| 双手 `gripper_1d` | 14D | `observation.tactile.left_raw` + `observation.tactile.right_raw`，各 130D |

`dexterous_10d` 线路仍可用：单臂 `observation.state` 为 16D，双臂为 32D；如果 `include_eef_pose: true`，非 `gripper_1d` 模式会额外加入 7D 末端位姿。触觉 raw key 仍保持独立。

需要训练 π0/π0.5 等不支持触觉输入的模型时，用 `scripts/tools/strip_tactile.py` 从 raw 数据集生成 `_no_tactile` 版本。

需要训练支持二维触觉输入的模型，或模仿 `/home/phl/workspace/lerobot_tactile` 的 tactile 输入格式时，用 `scripts/tools/convert_o10_tactile_heatmap.py` 从 raw 130D 数据集生成 `_tactile_heatmap` 版本：

```bash
python scripts/tools/convert_o10_tactile_heatmap.py \
  --input ~/workspace/dataset/Robot/agi_arm_bot/my_raw_dataset
```

输出会增加 `observation.tactile.left` / `observation.tactile.right`，shape 为 `float32[12, 32]`。默认保留 `*_raw`；如果只想保留 heatmap，用 `--drop-raw`。

现场检查触觉空间映射时，可以直接连左右手看物理布局热力图：

```bash
python scripts/tools/visualize_o10_tactile_heatmap.py --hand both --layout physical
```

详细字段顺序见 `docs/o10_tactile_raw_schema.md`。

## 推理

支持策略：

- `act`
- `diffusion`
- `pi0`
- `pi05`
- `smolvla`
- `groot`

常用命令：

```bash
./scripts/o10/left_arm/infer_o10_left.sh
./scripts/o10/right_arm/infer_o10_right.sh
./scripts/o10/right_arm/infer_o10_right_cpu.sh
./scripts/o10/dual_arm/infer_o10_dual.sh
```

PI0.5 异步推理演示命令：

```bash
cd /home/phl/workspace/arm-hand-teleop
conda activate arm-hand-teleop-pi0

ARM_HAND_TELEOP_PI05_MODEL_PATH=/home/phl/workspace/mymodels/qiuzhi_agibot/camera_pen_touch_clean_del_52_376/pi0/pi05_camera_pen_touch_clean_del_52_376_selected/120000/pretrained_model \
ARM_HAND_TELEOP_ASYNC_FPS=15 \
ARM_HAND_TELEOP_ASYNC_INFERENCE_LATENCY=0.35 \
ARM_HAND_TELEOP_ASYNC_ACTIONS_PER_CHUNK=50 \
./scripts/o10/dual_arm/infer_o10_dual_pi05_async_rtc.sh
```

推理前检查：

- `infer.model_path` 必须存在，且目录内必须有 `config.json`；权重通常是 `model.safetensors` 或 `pytorch_model.bin`。
- `infer.policy` 必须和模型类型一致。
- `infer.device` 可用 `cuda` 或 `cpu`；CPU 只适合小模型/调试。
- `robot.include_eef_pose`、`robot.tactile_mode`、相机 key 必须与训练数据集一致，否则策略输入 schema 会不匹配。
- `infer.save_data: true` 时推理过程会保存为 LeRobot 数据集；`save_path` 为空时自动写到 `~/.cache/huggingface/lerobot/...`。

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

# 检查录制数据集触觉通道是否采到数据
python scripts/tools/check_tactile_success.py --dataset.root <dataset_dir>

# 转换 LeRobot 数据集到 openpi 训练格式
python scripts/tools/convert_lerobot_to_openpi.py --input <lerobot_dir> --output <openpi_dir>
```

> `save_reset_pose.py` / `save_dual_reset_pose.py` / `save_gesture_reset_poses.py` 输出的是 legacy `groups.arm / groups.hand` 格式，**不能**直接覆盖 `configs/reset_poses/o10_dual_reset.json`。新的关节值请手动合并到集中式 JSON 的 `arm.<side>` / `gestures.<name>.<side>.open|closed` 字段里。

## 测试和检查

```bash
# 全量 Python 回归
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests -q

# 常用聚焦检查
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_dual_arm_config.py -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_infer_save_path.py -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_single_arm_o10_trigger_gate.py -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_dual_arm_o10_trigger_gate.py -q
```

当前全量回归应为 `103 passed, 1 skipped`。`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 用于避免 ROS/外部 pytest 插件污染。

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
