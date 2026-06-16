# 双臂 ROS2 远程推理 AI 交接文档

本文档给另一台电脑上的 AI 使用。目标是在两台机器之间运行 AGIBOT O10 双臂远程推理：

- A 机器：GPU / checkpoint / 策略推理，运行 `ros2_policy_node`。
- B 机器：真实双臂、灵巧手、相机、CAN，运行 `ros2_robot_bridge`。
- ROS2 负责传输观测、动作 chunk 和机器人 schema。

本流程只用于“硬件在 B、策略在 A”的分布式部署。本地推理和 gRPC 推理路径不受影响。

## 0. 重要前提

1. A、B 两台机器都有仓库：

   ```bash
   cd ~/workspace/arm-hand-teleop
   ```

2. 两台机器都安装了 ROS2 Jazzy，并且存在：

   ```bash
   /opt/ros/jazzy/setup.bash
   ```

3. 两台机器能互相 ping 通，网络没有阻断 ROS2 DDS 发现。

4. A、B 两台机器必须使用相同的 `ROS_DOMAIN_ID`。脚本默认是 `0`。

5. `ARM_HAND_TELEOP_PI05_MODEL_PATH` 指向的模型路径必须在 A、B 两台机器都能解析：

   - A 机器需要加载完整 checkpoint 做推理。
   - B 机器启动时至少要读到 `config.json` 做 schema 和参数检查。

   最稳妥做法是把 checkpoint 同步到两台机器的相同绝对路径。

## 1. 架构

```text
A 机器：GPU / 策略推理                    B 机器：真实硬件

ros2_policy_node                          ros2_robot_bridge
加载模型                                  连接双臂、手、相机、CAN
订阅 /lerobot/observation                 发布 /lerobot/observation
发布 /lerobot/action_chunk                订阅 /lerobot/action_chunk
接收 /lerobot/robot_schema                发布 /lerobot/robot_schema
```

ROS2 topic 和服务：

| 名称 | 类型 | 方向 | 说明 |
| --- | --- | --- | --- |
| `/lerobot/observation` | `lerobot_ros2_msgs/Observation` | B -> A | B 发关节、手、eef、相机观测 |
| `/lerobot/action_chunk` | `lerobot_ros2_msgs/ActionChunk` | A -> B | A 发推理出的动作 chunk |
| `/lerobot/robot_schema` | `lerobot_ros2_msgs/RobotSchema` | B -> A | latched 握手消息，A 收到后加载策略 |
| `/lerobot_robot_bridge/reset` | `std_srvs/srv/Trigger` | 服务 | 手动复位 |
| `/lerobot_robot_bridge/stop` | `std_srvs/srv/Trigger` | 服务 | 手动停止 |

启动顺序无所谓，因为 `/lerobot/robot_schema` 是 latched / TRANSIENT_LOCAL。

## 2. 两台机器一次性构建 ROS2 消息包

A、B 都执行：

```bash
cd ~/workspace/arm-hand-teleop/ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --packages-select lerobot_ros2_msgs
source install/setup.bash
ros2 interface show lerobot_ros2_msgs/msg/Observation
```

成功判据：

- `colcon build` 成功退出。
- `ros2 interface show ...` 能显示 `Observation` 消息字段。

说明：启动脚本会自动 source `ros2_ws/install/setup.bash`，但消息包必须至少 build 过一次。

## 3. 启动前检查

A、B 两边都建议先设置：

```bash
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
```

如果模型不是脚本默认路径，两边都设置：

```bash
export ARM_HAND_TELEOP_PI05_MODEL_PATH=/你的/checkpoint/pretrained_model
```

可选参数：

```bash
export ARM_HAND_TELEOP_POLICY=pi05
export ARM_HAND_TELEOP_ASYNC_FPS=15
export ARM_HAND_TELEOP_ASYNC_ACTIONS_PER_CHUNK=50
export ARM_HAND_TELEOP_ASYNC_CHUNK_SIZE_THRESHOLD=0.8
```

A 机器可选 RTC 参数：

```bash
export ARM_HAND_TELEOP_RTC_ENABLED=1
export ARM_HAND_TELEOP_RTC_EXECUTION_HORIZON=10
export ARM_HAND_TELEOP_RTC_MAX_GUIDANCE_WEIGHT=10.0
export ARM_HAND_TELEOP_RTC_PREFIX_ATTENTION_SCHEDULE=EXP
```

B 机器还要确认 `configs/dual_arm/o10_dual_infer.yaml` 的 `robot` 块和真实硬件一致，尤其是：

- 左右臂配置。
- CAN 设备。
- 灵巧手配置。
- RealSense 相机序列号和 camera key。
- 模型训练时期望的 image key，例如 `right_wrist`、`left_wrist` 等。

## 4. A 机器启动策略节点

在 A 机器执行：

```bash
cd ~/workspace/arm-hand-teleop
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export ARM_HAND_TELEOP_PI05_MODEL_PATH=/你的/checkpoint/pretrained_model
./scripts/o10/dual_arm/ros2_policy_o10_dual.sh
```

如果使用默认模型路径，可以不 export `ARM_HAND_TELEOP_PI05_MODEL_PATH`。

这个脚本内部会运行：

```bash
run_lerobot_play.py ros2_policy_node --yaml configs/dual_arm/o10_dual_infer.yaml --fps ...
```

## 5. B 机器启动 robot bridge

在 B 机器执行：

```bash
cd ~/workspace/arm-hand-teleop
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export ARM_HAND_TELEOP_PI05_MODEL_PATH=/你的/checkpoint/pretrained_model
./scripts/o10/dual_arm/ros2_bridge_o10_dual.sh
```

如果只想跑 3 个 episode：

```bash
./scripts/o10/dual_arm/ros2_bridge_o10_dual.sh --num_episodes 3
```

这个脚本会拒绝重复启动已有的 `ros2_robot_bridge`，避免两个进程抢 CAN。

## 6. 验证链路

任一机器新开终端执行：

```bash
source /opt/ros/jazzy/setup.bash
source ~/workspace/arm-hand-teleop/ros2_ws/install/setup.bash

ros2 node list
ros2 topic echo /lerobot/robot_schema --once
ros2 topic hz /lerobot/observation
ros2 topic hz /lerobot/action_chunk
```

成功判据：

1. `ros2 node list` 能看到：

   ```text
   /lerobot_robot_bridge
   /lerobot_policy_node
   ```

2. `ros2 topic echo /lerobot/robot_schema --once` 能输出一次 schema。

3. `ros2 topic hz /lerobot/observation` 接近配置 fps，例如 15Hz。

4. `ros2 topic hz /lerobot/action_chunk` 有动作 chunk 回流。

## 7. 复位和停止

任一机器执行：

```bash
source /opt/ros/jazzy/setup.bash
source ~/workspace/arm-hand-teleop/ros2_ws/install/setup.bash

ros2 service call /lerobot_robot_bridge/reset std_srvs/srv/Trigger "{}"
ros2 service call /lerobot_robot_bridge/stop  std_srvs/srv/Trigger "{}"
```

`reset` 会先让控制环停手再归零，避免和动作发送、观测读取并发抢硬件。

## 8. 从 A 机器远程启动 B 的 bridge

ROS2 只负责通信，不负责帮你启动另一台机器的进程。如果要从 A 上拉起 B：

```bash
ssh <B用户名>@<B机器IP> 'cd ~/workspace/arm-hand-teleop && export ROS_DOMAIN_ID=0 && export ROS_LOCALHOST_ONLY=0 && export ARM_HAND_TELEOP_PI05_MODEL_PATH=/你的/checkpoint/pretrained_model && ./scripts/o10/dual_arm/ros2_bridge_o10_dual.sh'
```

如果模型路径已经写在 B 的 shell 环境或使用默认路径，可以省略 `ARM_HAND_TELEOP_PI05_MODEL_PATH`。

## 9. 常见问题定位

### A 看不到 B，或 topic 没数据

检查：

```bash
echo $ROS_DOMAIN_ID
echo $ROS_LOCALHOST_ONLY
ping <另一台机器IP>
ros2 node list
```

处理：

- A、B 使用相同 `ROS_DOMAIN_ID`。
- 跨机器时 `ROS_LOCALHOST_ONLY=0`。
- 检查防火墙和 DDS 多播发现。

### B 启动时报 model_path / config.json 不存在

原因：B 也需要读取模型目录下的 `config.json`。

处理：

```bash
ls /你的/checkpoint/pretrained_model/config.json
```

如果不存在，把 checkpoint 同步到 B，最好保持和 A 相同的绝对路径。

### A policy node 一直等 schema

原因：B 端 bridge 没启动成功，或者 ROS2 网络没发现。

检查 B 端日志，并在任一机器执行：

```bash
ros2 topic echo /lerobot/robot_schema --once
```

### observation 有频率，但 action_chunk 没有

可能原因：

- A 端模型加载失败。
- A 收到的 observation schema 或 image key 和模型不匹配。
- GPU / checkpoint / policy 配置有问题。

优先看 A 端 `ros2_policy_node` 日志。

### B 端反复复位或 episode 起不来

可能原因：

- `configs/dual_arm/o10_dual_infer.yaml` 的硬件配置不匹配。
- 相机 key 缺失，例如模型要 `right_wrist`，但 B 的 observation 没有。
- RealSense 没枚举到。

检查：

```bash
rs-enumerate-devices
```

并核对 `configs/dual_arm/o10_dual_infer.yaml`。

## 10. 最短执行摘要

A、B 都先 build：

```bash
cd ~/workspace/arm-hand-teleop/ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --packages-select lerobot_ros2_msgs
```

A 起策略：

```bash
cd ~/workspace/arm-hand-teleop
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export ARM_HAND_TELEOP_PI05_MODEL_PATH=/你的/checkpoint/pretrained_model
./scripts/o10/dual_arm/ros2_policy_o10_dual.sh
```

B 起硬件 bridge：

```bash
cd ~/workspace/arm-hand-teleop
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export ARM_HAND_TELEOP_PI05_MODEL_PATH=/你的/checkpoint/pretrained_model
./scripts/o10/dual_arm/ros2_bridge_o10_dual.sh
```

验证：

```bash
source /opt/ros/jazzy/setup.bash
source ~/workspace/arm-hand-teleop/ros2_ws/install/setup.bash
ros2 node list
ros2 topic hz /lerobot/observation
ros2 topic hz /lerobot/action_chunk
```

一句话：两边同代码、同 ROS_DOMAIN_ID、同模型路径；A 跑 `ros2_policy_o10_dual.sh`，B 跑 `ros2_bridge_o10_dual.sh`，最后用 `ros2 topic hz` 看数据流。
