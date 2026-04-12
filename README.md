# arm-hand-teleop

这个项目用于 Agibot O10 单臂 + O10 灵巧手 + 相机的数据采集、遥操作控制、回放和推理。

当前主流程是：

- Pico wrist 位姿控制机械臂
- 宇叠手套控制 O10 手指
- `lerobot_play` 负责 `control / record / replay / infer`
- 录制结果按 LeRobot 3.0 风格落盘

## 目录说明

- `configs/`
  控制、录制、回放、推理用的 YAML 和手复位 JSON。
- `scripts/`
  日常直接启动的脚本。
- `qiuzhi/`
  vendored 的 `lerobot_play` 代码和测试。
- `yudie/`
  宇叠手套、HDService、HDWeb、OmniHand SDK 相关代码。
- `run_lerobot_play.py`
  项目统一入口。

## 环境说明

- 日常直接跑 `scripts/*.sh` 时，不需要手动 `conda activate`。
- 这些脚本已经固定使用：

```bash
~/miniconda3/envs/arm-hand-teleop/bin/python
```

- 只有你想手动跑 Python、装包、跑测试时，才需要自己激活环境：

```bash
conda activate arm-hand-teleop
```

## 最常用启动顺序

先进入项目根目录：

```bash
cd ~/workspace/arm-hand-teleop
```

### 1. 启动手套服务

前台运行：

```bash
./scripts/start_hdservice.sh
```

后台运行：

```bash
./scripts/start_hdservice.sh --background
```

说明：

- 这个脚本会把手套数据转发到本机 `127.0.0.1:5555`
- `AgibotO10GloveTeleoperator` 就是从这个 UDP 端口收手套数据
- 后台模式日志默认写到 `~/workspace/arm-hand-teleop/logs/hdservice.log`

### 2. 启动 HDWeb 页面

```bash
./scripts/start_hdweb.sh
```

正常会打印类似：

```text
Open http://<本机IP>:8088/ in your browser
```

说明：

- HDWeb 的 HTTP 页面默认是 `8088`
- 它连接的 HDService websocket 默认是 `7789`
- 页面里要能看到当前在线手套角色

### 3. 确认手套角色正常

当前 O10 录制/控制会根据 `teleop.handedness` 自动选手套角色：

- `right` 时，优先找名字以 `R` / `RIGHT` 结尾的角色
- `left` 时，优先找名字以 `L` / `LEFT` 结尾的角色

例如：

- 右手：`UDXST4688R`
- 左手：`UDXST4688L`

如果 HDWeb 里没有显示角色，或者角色左右和 YAML 里的 `handedness` 对不上，控制/录制时会收不到新手套数据。

### 4. 启动控制或录制

只做实时控制：

```bash
./scripts/control_o10_right.sh
```

录制 LeRobot 数据：

```bash
./scripts/record_o10_right.sh
```

回放数据集：

```bash
./scripts/replay_o10_right.sh
```

运行模型推理：

```bash
./scripts/infer_o10_right.sh
```

说明：

- `control` 和 `record` 会自动拉起或复用 Pico WebRTC/ZMQ 端口
- 当前默认位姿 / 按键端口是：
  - `vr_pose_port: 8000`
  - `vr_ctrl_port: 8001`
- 一般不需要你再手动开一套额外的 Pico Python 转发程序

### 5. 停止顺序

建议按这个顺序停：

1. 先 `Ctrl+C` 停掉 `control / record / replay / infer`
2. 再停 HDWeb
3. 最后停 HDService

对应脚本：

```bash
./scripts/stop_hdweb.sh
./scripts/stop_hdservice.sh
```

## 常用命令

```bash
cd ~/workspace/arm-hand-teleop
./scripts/start_hdservice.sh --background
./scripts/start_hdweb.sh
./scripts/control_o10_right.sh
./scripts/record_o10_right.sh
./scripts/replay_o10_right.sh
./scripts/infer_o10_right.sh
```

## YAML 里怎么切左手 / 右手

虽然配置文件名里还叫 `right`，但当前这套已经支持直接靠 YAML 切左右。

### `control` / `record`

至少看这几个字段：

- `teleop.handedness`
  选择“哪只 leader 手套”作为输入
- `robot.handedness`
  选择“哪只 O10 follower 手/臂”执行动作
- `robot.channel_id`
  保持 `null` 时会自动跟随 `robot.handedness`
- `robot.include_tactile_observation`
  是否把 O10 触觉并进 `observation.state`
- `teleop.hand_reset_joints_path`
  leader 侧保存 / 读取的手复位 JSON
- `teleop.hand_grasp_preset_joints_path`
  固定抓取手型骨架 JSON，只给 `grasp_preset` 模式用
- `robot.hand_reset_joints_path`
  robot 侧执行复位时使用的手复位 JSON
- `teleop.hand_control_mode`
  手控制模式，`full_hand` 或 `grasp_preset`
- `teleop.hand_grasp_preset`
  固定抓取手型，只有 `grasp_preset` 时生效

建议：

- 左右手最好分别用不同 JSON
- `teleop.hand_reset_joints_path` 和 `robot.hand_reset_joints_path` 最好设成同一路径
- `teleop.hand_grasp_preset_joints_path` 单独放另一份 JSON，不要和全手复位共用
- 如果你做的是“托盘里夹取扁平方形摄像头”这类精细抓取，优先试 `grasp_preset`

当前默认映射：

- `left -> channel_id 0`
- `right -> channel_id 1`

### `infer` / `replay`

这两个模式没有 teleop，主要改：

- `robot.handedness`
- `robot.channel_id`
- `robot.include_tactile_observation`

其中：

- 训练数据如果录了触觉，推理时也要保持 `robot.include_tactile_observation: true`
- 训练数据如果没录触觉，推理时就保持 `false`
- `replay` 只回放数据集里的 `action`，不依赖这个触觉开关

## VR 怎么用

这里要分清两件事：

- 键盘负责“录制流程”
- VR 按键负责“机械臂和灵巧手运动”

### 右手配置下的 VR 控制逻辑

当前 `teleop.handedness: right` 时，真实逻辑是：

1. 按 `X`
   进入 VR 控制状态，终端会打印 `start VR control`
2. 按住左手柄扳机 `LTr`
   机械臂和手才会跟随动
3. 松开左扳机
   臂和手保持当前目标，不再继续跟随
4. 按 `Y`
   机械臂回初始位，手回保存好的复位手型，同时退出 VR 控制状态
5. 如果想继续动
   再按一次 `X`，然后继续按住左扳机操作

也就是说：

- `X` 是“开始允许 VR 控制”
- `LTr` 是“真正使能运动”
- `Y` 是“臂 + 手一起复位，并退出控制”

### 左手配置下的 VR 控制逻辑

如果你把 `teleop.handedness` 改成 `left`，按键会变成：

1. 按 `A` 开始 VR 控制
2. 按住右手柄扳机 `RTr` 才允许运动
3. 按 `B` 复位

### 控制模式终端里看到的那些值是什么

`control` 模式里终端打印的：

- `joint1.pos ~ joint6.pos`
- `thumb_cm_roll.pos ~ pinky_mp_pitch.pos`
- `pose.x / pose.y / pose.z / quaternion.*`

这些不是“手套原始数据”，而是当前准备发给机器人或用于显示的动作值，已经经过了映射和格式整理。

## 复位逻辑和手复位 JSON

### 手复位 JSON 放在哪里

当前默认分成两份：

- `configs/o10_right_hand_full_reset_pose.json`
  全手控制默认复位手型
- `configs/o10_right_hand_grasp_preset_pose.json`
  固定抓取手型骨架

真正使用哪个文件，取决于 YAML 里的：

- `teleop.hand_reset_joints_path`
- `teleop.hand_grasp_preset_joints_path`
- `robot.hand_reset_joints_path`

当前默认建议：

- `teleop.hand_reset_joints_path` 和 `robot.hand_reset_joints_path` 指向同一个“全手复位” JSON
- `teleop.hand_grasp_preset_joints_path` 单独指向“固定抓取骨架” JSON

### 这个 JSON 什么时候会被读 / 写

当前逻辑是：

- 如果全手复位 JSON 已存在，启动时直接加载
- 如果全手复位 JSON 不存在，teleop 会在第一次成功收到新鲜手套数据后，把“当前手型”保存进去
- robot 侧复位时会读取同一份全手复位 JSON，把手复位到这份手形，而不是硬编码全零
- 如果固定抓取骨架 JSON 已存在，`grasp_preset` 模式会直接加载它
- 如果固定抓取骨架 JSON 不存在，`grasp_preset` 会先回退到全手复位手型作为骨架

也就是说，`Y` 复位时：

- 臂回代码里定义的初始位
- 手回“全手复位 JSON”里保存的 10 个手关节角

### 想改默认复位手型怎么办

当前没有单独的“运行时重新采样手复位姿态”按键。

最稳妥的方法是：

1. 把手套摆成你想要的复位手型
2. 删除或手动改掉对应的 `hand_reset_joints_path` JSON
3. 重新启动 `control` 或 `record`
4. 让程序在第一次收到手套数据时重新保存

如果你已经把机器人手直接手动掰到了目标角度，也可以直接读取当前机器人手关节并覆盖 JSON：

```bash
cd ~/workspace/arm-hand-teleop
./scripts/capture_o10_right_full_reset_pose.sh
```

这个脚本会直接读取 O10 右手当前关节，并写回：

- [configs/o10_right_hand_full_reset_pose.json](/home/phl/workspace/arm-hand-teleop/configs/o10_right_hand_full_reset_pose.json)

如果你想改的是固定抓取骨架，而不是全手复位：

1. 直接手动改 `teleop.hand_grasp_preset_joints_path` 指向的那份 JSON
2. 重点改拇指横向姿态和未激活手指姿态

如果你已经把机器人手直接手动掰到了目标抓取骨架，也可以直接执行：

```bash
cd ~/workspace/arm-hand-teleop
./scripts/capture_o10_right_grasp_preset_pose.sh
```

它会把当前机器人手关节写回：

- [configs/o10_right_hand_grasp_preset_pose.json](/home/phl/workspace/arm-hand-teleop/configs/o10_right_hand_grasp_preset_pose.json)

如果你哪天想从“手套当前姿态”而不是“机器人手当前关节”去采样，也可以用通用脚本：

```bash
cd ~/workspace/arm-hand-teleop
python ./scripts/capture_o10_hand_pose.py --handedness right --pose-kind full_reset --source glove
```

## 固定抓取手型怎么用

如果你不想全手自由控制，而是想让 O10 更像“夹子”去拿托盘里的扁平方形摄像头，可以直接用固定抓取手型模式。

### 这个模式会做什么

- `full_hand`
  全手按手套原始数据控制
- `grasp_preset`
  只放开少数用于抓取的关节，其余手指固定在抓取骨架 JSON

当前已经内置：

- `pinch_index`
  拇指 + 食指
- `pinch_middle`
  拇指 + 中指
- `tripod`
  拇指 + 食指 + 中指

### 拇指会不会乱外翻

当前 `grasp_preset` 模式已经专门按“更像夹爪”的逻辑处理了：

- 拇指横向姿态不会跟着手套乱跑
- `thumb_cm_roll.pos` 和 `thumb_cm_yaw.pos` 会锁在抓取骨架 JSON
- 真正参与抓取的主要是 `thumb_cm_pitch.pos`
- `pinch_index` 下，`index_mp_yaw.pos` 也会锁住，只主要使用 `index_mp_pitch.pos`

所以如果你想让拇指保持“更竖直、更像夹子”的姿态，关键不是去追手套的横向姿态，而是先把固定抓取骨架那份 JSON 调好。

### 最推荐的使用步骤

1. 先把 [configs/o10_right_hand_grasp_preset_pose.json](/home/phl/workspace/arm-hand-teleop/configs/o10_right_hand_grasp_preset_pose.json) 调成你想要的抓取骨架。
2. 尤其优先调这几个值，让拇指更像竖直夹爪：
   - `thumb_cm_roll.pos`
   - `thumb_cm_yaw.pos`
   - 如果用 `pinch_index`，也可以一起调 `index_mp_yaw.pos`
3. 再把 YAML 里的 `teleop.hand_control_mode` 改成 `grasp_preset`
4. 最后选择 `teleop.hand_grasp_preset`

如果你想改的是 Y 键复位回去的那只手形，则改：

- [configs/o10_right_hand_full_reset_pose.json](/home/phl/workspace/arm-hand-teleop/configs/o10_right_hand_full_reset_pose.json)

### 推荐配置

如果你的目标是“托盘里夹取扁平方形摄像头”，建议先从这组开始：

```yaml
teleop:
  hand_control_mode: grasp_preset
  hand_grasp_preset: pinch_index
```

如果你想要更大的开口，再试：

```yaml
teleop:
  hand_control_mode: grasp_preset
  hand_grasp_preset: pinch_middle
```

如果两指容易滑或者容易转，再试：

```yaml
teleop:
  hand_control_mode: grasp_preset
  hand_grasp_preset: tripod
```

### `pinch_index` / `pinch_middle` / `tripod` 分别会放开什么

- `pinch_index`
  只放开 `thumb_cm_pitch.pos` 和 `index_mp_pitch.pos`
- `pinch_middle`
  只放开 `thumb_cm_pitch.pos` 和 `middle_mp_pitch.pos`
- `tripod`
  只放开 `thumb_cm_pitch.pos`、`index_mp_pitch.pos`、`middle_mp_pitch.pos`

没被放开的那些关节都会固定在 `teleop.hand_grasp_preset_joints_path` 指向的抓取骨架上。

### 控制和录制时怎么开

`control` 和 `record` 都支持，直接改这两个 YAML：

- [configs/o10_right_control.yaml](/home/phl/workspace/arm-hand-teleop/configs/o10_right_control.yaml)
- [configs/o10_right_record.yaml](/home/phl/workspace/arm-hand-teleop/configs/o10_right_record.yaml)

改完后启动命令不需要变：

```bash
./scripts/control_o10_right.sh
./scripts/record_o10_right.sh
```

### 录出来的数据会不会把多余手指删掉

不会。

当前做法是：

- 控制层只让你用少量抓取关节
- 机器人执行层仍然发送完整 10 个手关节
- 录制层仍然保存完整手关节 action
- 没参与抓取的手指会保持在固定值

这样最稳，也最兼容当前 LeRobot 数据格式。

## 数据采集怎么用

### 启动录制

```bash
cd ~/workspace/arm-hand-teleop
./scripts/record_o10_right.sh
```

### 录制开始前按什么

本地桌面模式下，默认提示是：

```text
Recording episode N, press space/enter to start recording or press ESC to exit
After recording starts, use VR controls: X starts arm control, hold left trigger to move, Y resets.
```

这两句话的意思要分开理解：

- `Space / Enter`
  只是开始当前 episode 的录制
- `X + 左扳机`
  才是开始真正控制机器人运动

### 本地桌面模式下，录制时键盘按键

默认 `configs/o10_right_record.yaml` 里：

- `dataset.is_ssh: false`

此时键盘逻辑是：

- `Space` 或 `Enter`
  开始当前 episode
- `Right Arrow`
  提前结束当前 episode，并保存当前 episode
- `Left Arrow`
  丢弃当前 episode，并重录上一个
- `ESC`
  停止整个录制流程并退出

补充说明：

- 一个 episode 到达 `run.episode_time_sec` 上限后，也会自动结束并保存
- 提前结束当前 episode 后，下一个 episode 会重新等待你按 `Space / Enter`

### 远程 / SSH 模式下，录制时输入什么

如果你是在没有 GUI 的机器上跑，建议改：

- `dataset.is_ssh: true`

此时用终端输入命令：

- `[Enter]` 或 `start`
  开始当前 episode
- `next` 或 `n`
  结束并保存当前 episode，然后自动进入下一个
- `rerecord` 或 `r`
  丢弃当前 episode，重录
- `stop`、`q`、`esc`
  停止录制
- `exit`、`quit`
  退出程序

### 录制时 VR 按键负责什么

录制过程中，VR 部分仍然遵循控制模式的逻辑：

- 右手配置：
  - `X` 进入 VR 控制
  - 按住左扳机才会动
  - `Y` 复位臂和手
- 左手配置：
  - `A` 进入 VR 控制
  - 按住右扳机才会动
  - `B` 复位臂和手

注意：

- 复位只会改变机器人状态，不会自动结束当前 episode
- 录制流程是否开始/结束，仍然是键盘或 SSH 命令在管

## 数据集会录到哪里

当前默认录制根目录是：

```bash
~/workspace/dataset/Robot/agi_arm_bot
```

最终真实数据集目录默认会是：

```text
<dataset.root>/<single_task归一化>_<日期>
```

例如：

```text
~/workspace/dataset/Robot/agi_arm_bot/pick_and_place_20260411
```

说明：

- `dataset.root` 是“父目录”，不是最终数据集目录
- 当前默认 `dataset.auto_name_from_task_date: true`
- 如果同名目录已存在，代码会自动尝试 `_2`、`_3` 这种后缀

### 临时改保存父目录

```bash
./scripts/record_o10_right.sh --dataset.root ~/workspace/dataset/Robot
```

### 临时改任务名

```bash
./scripts/record_o10_right.sh --single_task "pick and place"
```

### 如果你想用固定数据集名字

直接改 `configs/o10_right_record.yaml`：

```yaml
dataset:
  auto_name_from_task_date: false
  repo_id: my_dataset_name
  root: ~/workspace/dataset/Robot/agi_arm_bot
```

## 当前录到的数据是什么

当前 O10 单臂录制出来的数据，核心是：

- `action`
  16 维，只保留真正可执行的关节动作
- `observation.state`
  默认 23 维，包含臂关节、手关节和末端位姿
- `observation.images.right`
  右侧 RealSense 彩图
- `observation.images.right_depth`
  只有在 `robot.cameras.right.use_depth: true` 时才会额外录入
- `observation.images.top`
  顶部 USB 相机彩图

说明：

- `right_depth` 不是 RGB 估计出来的伪深度，而是 RealSense 真深度
- 为了兼容当前 LeRobot 图像链路，代码会把真深度编码成 3 通道图像再写入数据集
- 这样训练时可以把它当成一条额外相机流，直接和 `right`、`top` 一起喂给 `diffusion` / `act`

### `action` 里现在有什么

一共 16 个值：

- `joint1.pos`
- `joint2.pos`
- `joint3.pos`
- `joint4.pos`
- `joint5.pos`
- `joint6.pos`
- `thumb_cm_roll.pos`
- `thumb_cm_yaw.pos`
- `thumb_cm_pitch.pos`
- `index_mp_yaw.pos`
- `index_mp_pitch.pos`
- `middle_mp_pitch.pos`
- `ring_mp_yaw.pos`
- `ring_mp_pitch.pos`
- `pinky_mp_yaw.pos`
- `pinky_mp_pitch.pos`

说明：

- 现在的 `action` 不再包含 `pose.x / quaternion.*`
- 这样更符合“动作只保存真正能直接发给机器人执行的东西”

### `observation.state` 里有什么

默认一共 23 个值：

- 上面那 16 个关节量
- 再加 7 个末端位姿量：
  - `pose.x`
  - `pose.y`
  - `pose.z`
  - `quaternion.qx`
  - `quaternion.qy`
  - `quaternion.qz`
  - `quaternion.qw`

### 如果要把触觉也录进去

直接改 `configs/o10_right_record.yaml`：

```yaml
robot:
  include_tactile_observation: true
```

开启后：

- `action` 还是原来的 16 维，不会混进触觉
- `observation.state` 会从 23 维变成 `23 + 130 = 153` 维
- 额外追加的 130 维触觉字段会长这样：
  - `tactile.thumb.00 ~ tactile.thumb.15`
  - `tactile.index.00 ~ tactile.index.15`
  - `tactile.middle.00 ~ tactile.middle.15`
  - `tactile.ring.00 ~ tactile.ring.15`
  - `tactile.little.00 ~ tactile.little.15`
  - `tactile.palm.00 ~ tactile.palm.24`
  - `tactile.dorsum.00 ~ tactile.dorsum.24`

建议：

- 录制时开了触觉，训练和推理也都保持开启
- 如果只想先跑通整套流程，先保持 `false` 最稳

### 如果已经录了触觉，但后面训练不想用

现在仓库里带了一个导出工具，可以把 O10 数据集里的触觉从 `observation.state` 里裁掉，并导出成一份新的 LeRobot 数据集。

用法：

```bash
cd ~/workspace/arm-hand-teleop
python ./scripts/export_o10_dataset_without_tactile.py \
  --source ~/workspace/dataset/Robot/agi_arm_bot/<原始数据集目录> \
  --output ~/workspace/dataset/Robot/agi_arm_bot/<新数据集目录>
```

例如：

```bash
python ./scripts/export_o10_dataset_without_tactile.py \
  --source ~/workspace/dataset/Robot/agi_arm_bot/pick_and_place_20260411 \
  --output ~/workspace/dataset/Robot/agi_arm_bot/pick_and_place_20260411_no_tactile
```

说明：

- 这个工具不会原地改旧数据集，而是导出一份新的
- 会把 `observation.state` 从 `153` 维裁回 `23` 维
- 会同步更新：
  - `data/*.parquet`
  - `meta/info.json`
  - `meta/stats.json`
  - `meta/episodes/*.parquet`
- `action`、相机视频、任务信息会保留不动

## 当前同步/对齐方式

这套录制目前是软件级对齐，和 LeRobot 常见采集方式保持一致：

- 每一条样本都在同一个控制循环里写入 `observation + action`
- 机械臂状态和手状态是在同一次 `robot.get_observation()` 里读的
- 如果开启触觉，触觉也是在同一次 `robot.get_observation()` 里读的
- 相机取的是各自后台线程中的最新帧
- 如果开启 `right_depth` 这类深度流，同一相机的 RGB 和 depth 现在来自同一份快照，不会错开一帧
- 手套取的是当前最新的新鲜数据

默认频率：

- 录制主循环：`run.fps = 30`
- 右侧 RealSense：`30 FPS`
- 顶部相机：`30 FPS`

如果你要做特别精细的操作，建议保持这些频率一致，不要随便把某一路改得特别低。

## 回放和推理

### 回放

先改：

- `configs/o10_right_replay.yaml` 里的 `dataset.root`

它应当直接指向某一个具体数据集目录，例如：

```text
~/workspace/dataset/Robot/agi_arm_bot/pick_and_place_20260411
```

再运行：

```bash
./scripts/replay_o10_right.sh
```

### 推理

先改：

- `configs/o10_right_infer.yaml` 里的 `infer.model_path`
- 如果模型训练时用了触觉，还要把 `robot.include_tactile_observation` 改成 `true`

再运行：

```bash
./scripts/infer_o10_right.sh
```

## 测试

```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_agibot_o10.py
```

```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_runtime_helpers.py
```

## 常见问题

### 1. HDWeb 打开了但看不到手套

先检查：

- HDService 有没有先启动
- 浏览器打开的是不是 `http://<本机IP>:8088/`
- 页面里有没有出现角色名
- 角色左右是否和 YAML 的 `teleop.handedness` 一致

例如：

- `teleop.handedness: right` 时，最好看到 `...R` / `...RIGHT`
- `teleop.handedness: left` 时，最好看到 `...L` / `...LEFT`

### 2. 录制一按空格就报 OpenCV 窗口错误

如果当前机器没有 GUI，确认：

- `configs/o10_right_record.yaml` 里 `run.display_data: false`

控制模式如果也不想开显示，确认：

- `configs/o10_right_control.yaml` 里 `display_data: false`

### 3. 数据集目录已存在导致失败

当前录制不会覆盖一个完整的现有数据集目录。

解决办法：

- 改 `single_task`
- 或改保存父目录
- 或删掉旧数据集

### 4. 手连接失败或提示 hand device not ready

重点检查：

- USB-CANFD 是否识别正常
- O10 手本体是否上电
- `robot.handedness` 和 `channel_id` 是否对应正确
- `device_id` / `canfd_id` 是否还是当前机器真实值

### 5. 右手/左手明明换了，但程序还在读旧手型

先看：

- `teleop.hand_reset_joints_path` 指向的是哪个 JSON
- 那个 JSON 里是不是还是旧的复位手型

如果你想让复位手型换成新的，删掉对应 JSON 后重新启动一次最省事。

### 6. 开了触觉后程序一启动就报错

这是当前故意做的“启动时快失败”检查，不会等到录制中途才炸。

重点检查：

- `configs/o10_right_record.yaml` 或 `configs/o10_right_infer.yaml` 里是不是把 `robot.include_tactile_observation` 设成了 `true`
- 当前这只 O10 手和 SDK 是否真的能返回触觉数据
- 手有没有完全连上，是否存在 CAN/供电问题

如果你现在只是先录基础数据，先把它改回：

```yaml
robot:
  include_tactile_observation: false
```
