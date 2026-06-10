# O10 演示快速命令

这份文档只放现场演示要用的命令，按 demo 分开，方便直接复制粘贴。

仓库路径：

```bash
/home/phl/workspace/arm-hand-teleop
```

## 0. 常用检查

查看相机：

```bash
v4l2-ctl --list-devices
```

查看机械臂 CAN：

```bash
ip -brief link | grep -E '(^|[[:space:]])can[0-9]+'
```

当前约定：

- 左臂：`can0`
- 右臂：`can1`
- 左手通道：`0`
- 右手通道：`1`

## 1. USB 摄像头视觉控制灵巧手

用途：用新插的 USB 相机识别人手，实时控制 O10 右手灵巧手。

状态：已验证可用。

- 虚拟环境：`arm-hand-teleop`
- 摄像头：`JYU2C-2083`
- 图像节点：`/dev/video14`
- 不拔掉这个摄像头时，直接用下面这条。

```bash
cd /home/phl/workspace/arm-hand-teleop
conda activate arm-hand-teleop
python tests/test_mediapipe_right_hand_control.py \
  --camera /dev/video14 \
  --width 640 \
  --height 480
```

停止：在 OpenCV 窗口里按 `q`。

注意：`/dev/video15` 是 metadata，不是图像节点，不要用它。

## 2. 双臂手柄遥操

用途：用 Pico 左右手柄遥操双臂和双手。

```bash
cd /home/phl/workspace/arm-hand-teleop
conda activate arm-hand-teleop
./scripts/o10/dual_arm/control_o10_dual.sh
```

控制方式：

- 左手柄控制左臂/左手。
- 右手柄控制右臂/右手。
- 左手柄 `X`：进入遥操状态。
- 左手柄 `Y`：停止并复位。
- 按住左手柄 `LTr`：双臂双手开始跟随。

停止：终端按 `Ctrl+C`。

## 3. README 里的 PI0.5 双臂异步推理

用途：运行 README 里写的 PI0.5 async + RTC 双臂推理 demo。

```bash
cd /home/phl/workspace/arm-hand-teleop
conda activate arm-hand-teleop-pi0
ARM_HAND_TELEOP_PI05_MODEL_PATH=/home/phl/workspace/mymodels/qiuzhi_agibot/camera_pen_touch_clean_del_52_376/pi0/pi05_camera_pen_touch_clean_del_52_376_selected/120000/pretrained_model \
ARM_HAND_TELEOP_ASYNC_FPS=15 \
ARM_HAND_TELEOP_ASYNC_INFERENCE_LATENCY=0.35 \
ARM_HAND_TELEOP_ASYNC_ACTIONS_PER_CHUNK=50 \
./scripts/o10/dual_arm/infer_o10_dual_pi05_async_rtc.sh
```

停止：终端按 `Ctrl+C`。脚本会一起清理 async policy server。

如果推理报输入维度或相机 key 不匹配，检查 `configs/dual_arm/o10_dual_infer.yaml` 是否和训练数据集 schema 一致。

## 4. 右臂腕带 + 宇叠手套控制

用途：右臂位姿用 Pico wrist/腕带数据，右手手指用宇叠手套数据。

状态：已验证控制正常。

前提：

- 右臂 CAN 是 `can1`。
- 右手 O10 通道是 `1`。
- 宇叠手套已开机。
- 需要启动两个服务：`HDService` 和 `HDWeb`。
- 当前仓库已补齐 HDService 运行库：`yudie/HDW-Regular_V2.2.5_202604021755_Ubuntu22+_x86_64/HDService/lib/libAr1_linear.so`。

终端 1：启动手套服务。

```bash
cd /home/phl/workspace/arm-hand-teleop
conda activate arm-hand-teleop
setsid bash -lc 'cd /home/phl/workspace/arm-hand-teleop && ./scripts/services/start_hdservice.sh > logs/hdservice.log 2>&1' </dev/null >/dev/null 2>&1 &
```

终端 2：启动 HDWeb，看手套是否在线。

```bash
cd /home/phl/workspace/arm-hand-teleop
conda activate arm-hand-teleop
mkdir -p logs
setsid bash -lc 'cd /home/phl/workspace/arm-hand-teleop && ./scripts/services/start_hdweb.sh > logs/hdweb.log 2>&1' </dev/null >/dev/null 2>&1 &
echo "HDWeb: http://$(hostname -I | awk '{print $1}'):8088/"
```

打开上面打印的 HDWeb 地址，确认右手套在线后，再开终端 3。

终端 3：启动右臂腕带 + 手套控制。

```bash
cd /home/phl/workspace/arm-hand-teleop
conda activate arm-hand-teleop
python run_lerobot_play.py control \
  --config_path configs/right_arm/o10_right_wrist_glove_control.yaml
```

控制方式：

- 右臂跟随右侧 wrist/腕带位姿。
- 右手手指跟随宇叠手套。
- 左手柄 `X`：进入遥操状态。
- 左手柄 `Y`：停止并复位。
- 按住左手柄 `LTr`：右臂和右手开始跟随。

停止：终端 3 按 `Ctrl+C`。

如果手套连不上，终端 1 重新执行：

```bash
cd /home/phl/workspace/arm-hand-teleop
conda activate arm-hand-teleop
./scripts/services/stop_hdservice.sh || true
setsid bash -lc 'cd /home/phl/workspace/arm-hand-teleop && ./scripts/services/start_hdservice.sh > logs/hdservice.log 2>&1' </dev/null >/dev/null 2>&1 &
```

然后打开 HDWeb 确认手套配对在线，再重新启动终端 3 的控制命令。

## 5. 右臂全量微调切换任务推理

用途：运行右臂 `PI0.5 fullft merged` 推理，并在运行中切换任务。

启动：

```bash
cd /home/phl/workspace/arm-hand-teleop

ARM_HAND_TELEOP_RTC_ENABLED=1 \
ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON=10 \
ARM_HAND_TELEOP_RTC_MAX_GUIDANCE_WEIGHT=10.0 \
ARM_HAND_TELEOP_RTC_PREFIX_ATTENTION_SCHEDULE=EXP \
./scripts/o10/right_arm/infer_o10_right_pi05_fullft_merged.sh
```

运行中切到 `yellow_to_black`：

```bash
./scripts/o10/right_arm/switch_o10_right_fullft_task.sh yellow_to_black
```

切回 `black_to_yellow`：

```bash
./scripts/o10/right_arm/switch_o10_right_fullft_task.sh black_to_yellow
```

## 6. OpenPI JAX PI0.5 双臂异步推理（D435 top）

用途：运行 OpenPI JAX 版 PI0.5 双臂异步推理，用 D435 作为 top 相机。

任务：

```text
sort the express parcels
```

模型：

```text
/home/phl/workspace/mymodels/agi_arm_bot/jax/pi05/parcel_sorting_v21_full/130000
```

相机：

- top：Intel RealSense D435，serial `419522071539`，不翻转。
- left_wrist：Intel RealSense D405，serial `260322276846`。
- right_wrist：Intel RealSense D405，serial `260322273018`。

启动：

```bash
cd /home/phl/workspace/arm-hand-teleop
DISPLAY= PYTHONUNBUFFERED=1 \
ARM_HAND_TELEOP_OPENPI_WS_PORT=8771 \
ARM_HAND_TELEOP_OPENPI_JAX_WS_INFER_CONFIG=configs/dual_arm/o10_dual_openpi_jax_ws_infer_top_d435.yaml \
./scripts/o10/dual_arm/infer_o10_dual_openpi_jax_ws_async.sh 2>&1 | tee /tmp/infer_dbg2.log

```

停止：终端按 `Ctrl+C`。脚本会一起清理 OpenPI websocket policy server。

回退普通 USB top 相机时，直接使用默认配置启动：

```bash
cd /home/phl/workspace/arm-hand-teleop
./scripts/o10/dual_arm/infer_o10_dual_openpi_jax_ws_async.sh
```

## 7. 现场恢复命令

查看还在跑的 demo 进程：

```bash
pgrep -af 'run_lerobot_play.py|test_mediapipe_right_hand_control.py|async_policy_server|HDService|serve_hdweb'
```

停止单个进程：

```bash
kill <PID>
```

确认机器人安全后，停止常见 demo 进程：

```bash
pkill -f 'test_mediapipe_right_hand_control.py'
pkill -f 'run_lerobot_play.py'
pkill -f 'async_policy_server'
```

停止手套网页：

```bash
./scripts/services/stop_hdweb.sh
```
