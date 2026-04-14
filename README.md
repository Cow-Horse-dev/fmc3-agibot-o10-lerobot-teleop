# arm-hand-teleop

这个项目用于 Agibot O10 单臂 + 灵巧手 + 相机的数据采集、遥操作控制、回放和推理。

当前主流程基于 `lerobot_play`，并接了宇叠手套、Pico 位姿输入和 O10 手控制。

## 目录说明

- `configs/`
  存放控制、录制、推理、回放的 yaml 配置。
- `scripts/`
  常用启动脚本，日常基本直接跑这里的 `.sh` 就可以。
- `qiuzhi/`
  vendored 的 `lerobot_play` 代码和测试。
- `yudie/`
  手套、OmniHand、HDService、HDWeb 相关代码和 SDK。
- `run_lerobot_play.py`
  项目统一入口。

## 环境说明

- 日常启动脚本时，不需要手动 `conda activate`。
- `scripts/*.sh` 已经直接写死使用：

```bash
~/miniconda3/envs/arm-hand-teleop/bin/python
```

- 只在下面这些场景下，才需要你自己进虚拟环境：

```bash
conda activate arm-hand-teleop
```

- 你想手动跑 `python`
- 你想装包
- 你想跑测试

## 常用启动命令

先进入项目目录：

```bash
cd ~/workspace/arm-hand-teleop
```

启动手套服务：

```bash
./scripts/start_hdservice.sh
```

后台启动手套服务：

```bash
./scripts/start_hdservice.sh --background
```

启动 HDWeb：

```bash
./scripts/start_hdweb.sh
```

停止 HDService：

```bash
./scripts/stop_hdservice.sh
```

停止 HDWeb：

```bash
./scripts/stop_hdweb.sh
```

重启 HDService：

```bash
./scripts/restart_hdservice.sh
```

启动右手实时控制：

```bash
./scripts/control_o10_right.sh
```

启动右手录制：

```bash
./scripts/record_o10_right.sh
```

启动右手回放：

```bash
./scripts/replay_o10_right.sh
```

启动右手推理：

```bash
./scripts/infer_o10_right.sh
```

## 配置文件

当前常用配置文件：

- [o10_right_control.yaml](configs/o10_right_control.yaml)
- [o10_right_record.yaml](configs/o10_right_record.yaml)
- [o10_right_infer.yaml](configs/o10_right_infer.yaml)
- [o10_right_replay.yaml](configs/o10_right_replay.yaml)
- [o10_right_reset_pose.json](configs/o10_right_reset_pose.json)

策略专用推理配置：

- [o10_right_infer_act_pick_blue_camera_into_black_tray.yaml](configs/policies/o10_right_infer_act_pick_blue_camera_into_black_tray.yaml)
- [o10_right_infer_diffusion_pick_blue_camera_into_black_tray.yaml](configs/policies/o10_right_infer_diffusion_pick_blue_camera_into_black_tray.yaml)

如果要切换左手或右手，优先改 yaml 里的这些字段：

- `robot.handedness`
- `teleop.handedness`
- `robot.channel_id`

说明：

- `channel_id: null` 表示自动跟随 `handedness`
- `left -> 0`
- `right -> 1`

## 统一复位姿态

当前 arm + hand 的统一复位姿态保存在：

- [o10_right_reset_pose.json](configs/o10_right_reset_pose.json)

当前逻辑：

- 启动后会加载这个 json
- 按 `Y` 回初始位时，机械臂和手都会一起回
- 手回到的是当前保存的复位手型，不是固定写死在代码里的默认手型

## 当前控制逻辑

当前 O10 遥操作约定：

- 按住左手柄扳机，手和臂才允许动
- `Y` 用来回初始位
- 回初始位时，臂和手一起回

## 数据录制说明

当前录制出的数据集是 LeRobot `v3.0` 格式。

默认录制目录在：

```bash
~/workspace/dataset/Robot/agi_arm_bot
```

录制时会在这个目录下面自动创建数据集子目录，例如：

```bash
~/workspace/dataset/Robot/agi_arm_bot/pick_and_place_20260411
```

如果你想手动指定目录，可以在命令行额外传参数，例如：

```bash
./scripts/record_o10_right.sh \
  --dataset.root ~/workspace/dataset/Robot/agi_arm_bot \
  --dataset.repo_id my_dataset
```

## 当前录制内容

当前新录的数据语义如下：

- `action`
  16 维，只包含真正可执行的命令
- `observation.state`
  23 维，包含臂关节、手关节、末端位姿
- `observation.images.right`
  右侧相机
- `observation.images.top`
  顶部相机

`action` 当前包含：

- 臂 6 个关节
- 手 10 个关节

`observation.state` 当前包含：

- 臂 6 个关节
- 手 10 个关节
- 末端位姿 7 个量

说明：

- `action` 现在不再包含 `pose.x/y/z + quaternion`
- 末端位姿保留在 observation 里，用于观测和训练辅助

## 数据同步说明

当前同步方式和 LeRobot 常见采集方式一致，属于软件级对齐，不是硬件级严格同步。

当前特点：

- 一条样本里会写入同一控制周期内的 `observation + action`
- 机械臂状态和手状态是在同一轮 `get_observation()` 里读取
- 相机取的是后台线程中的最新帧
- 手套数据也是异步线程中的最新值

如果后面要做特别精细的操作，建议继续关注：

- 手套频率和录制 fps 是否一致
- 相机、手、臂是否需要额外保存各自时间戳

## 测试

常用测试命令：

```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_agibot_o10.py
```

```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_runtime_helpers.py
```

## 常见问题

OpenCV 预览窗口报错：

- 如果你在没有 GUI 的环境里录制，确认 yaml 里：
- `run.display_data: false`

录制目录已存在导致失败：

- LeRobot 创建数据集目录时默认要求目标目录不存在
- 换一个新的 `repo_id`
- 或者删掉旧的空目录后再录

手套连不上：

- 先确认 `HDService` 已启动
- 再确认 `HDWeb` 里能看到正确的手套配对
- 再确认 yaml 里的 `handedness` 和实际手套左右一致

## 备注

这个仓库当前更偏向单机可用、直接启动的工程版本。

很多脚本已经故意写成了简单直白的形式，例如直接使用 `~` 路径，方便以后整体迁移目录时一起搬走。
