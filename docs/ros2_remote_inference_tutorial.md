# ROS2 远程推理使用教程

把**策略推理**放在 A 机器（有 GPU、有 checkpoint），把**机械臂 + 相机**接在 B 机器，
两台机器之间用 **ROS2** 传观测和动作。本教程从零讲清楚怎么用。

> 这是**增量功能**：本地/gRPC 的老推理方式完全没变。只有当你要"硬件在 B、策略在 A"
> 的分布式部署时才用这套 ROS2 流程。

---

## 1. 架构与角色

```
   A 机器 (本机, GPU)                         B 机器 (接硬件)
 ┌─────────────────────┐                  ┌──────────────────────────┐
 │ ros2_policy_node     │                  │ ros2_robot_bridge         │
 │  · 加载策略 (RTC)     │   /lerobot/...   │  · 持有机械臂/手/相机/CAN  │
 │  · 收观测→推理→发动作 │◄───── ROS2 ─────►│  · 控制环/队列/聚合/复位   │
 └─────────────────────┘                  └──────────────────────────┘
```

三条 ROS2 topic + 一组服务：

| Topic | 类型 | QoS | 方向 |
|---|---|---|---|
| `/lerobot/observation` | `lerobot_ros2_msgs/Observation` | BEST_EFFORT, 深度 1（只留最新） | B → A |
| `/lerobot/action_chunk` | `lerobot_ros2_msgs/ActionChunk` | RELIABLE, 深度 8 | A → B |
| `/lerobot/robot_schema` | `lerobot_ros2_msgs/RobotSchema` | RELIABLE + TRANSIENT_LOCAL（latched 握手） | B → A |
| `/lerobot_robot_bridge/reset`、`/stop` | `std_srvs/srv/Trigger` | 服务 | 任一机器触发 |

- **观测**：B 把关节/手/eef 标量打成 `JointState`，相机帧 JPEG 压缩成 `CompressedImage`，
  连同整数 `timestep`、`must_go` 打成一条原子 `Observation` 消息发出。
- **动作**：A 推理出一段动作 chunk（N 步），用 `ActionChunk` 发回；B 按控制频率执行，
  执行的同时下一次推理并行进行（异步 chunk 流，和现有 async 推理一致）。
- **握手**：B 启动时把策略类型 + 模型路径 + 特征 schema 打成 latched 的 `RobotSchema`
  发一次；A 收到才加载策略。latched = 谁先启动都行。

---

## 2. 一次性准备

### 2.1 A 机器：推代码到云端

```bash
cd ~/workspace/arm-hand-teleop
git push origin dev/add-vla-jepa-policy
```

> 只会推已提交的内容；本地未提交的改动不会被推走。

### 2.2 B 机器：拉代码

```bash
cd ~/workspace/arm-hand-teleop
git pull
```

### 2.3 两台机器各自构建一次消息包

ROS2 自定义消息包需要在**每台机器**上 `colcon build` 一次（包在仓库里，构建产物不入 git）：

```bash
cd ~/workspace/arm-hand-teleop/ros2_ws
colcon build --packages-select lerobot_ros2_msgs
# 自检（可选）
source install/setup.bash
ros2 interface show lerobot_ros2_msgs/msg/Observation
```

启动脚本会自动 `source` 这个 install，所以平时不用手动 source，但**包必须先 build 过**。

### 2.4 网络

- A、B 设**相同的** `ROS_DOMAIN_ID`（脚本默认 `0`）。
- 不在同一子网时 `ROS_LOCALHOST_ONLY=0`（脚本已默认）。
- 确认两台机器能互相 ping 通，DDS 多播/发现没有被防火墙挡住。

### 2.5 模型 checkpoint 要在两台机器都能解析 ⚠️

`model_path`（YAML 里或 `ARM_HAND_TELEOP_PI05_MODEL_PATH` 环境变量）必须在**两台机器**上都解析得到：

- **B** 启动时要读 `config.json` 做参数校验和 schema 探测；
- **A** 要加载完整 checkpoint 做推理。

最稳的做法：把 checkpoint 同步到 B 的**相同绝对路径**，或者两台都挂同一个共享盘。
B 上至少要有 `config.json`。

---

## 3. 启动

启动顺序无所谓（握手是 latched 的）。

**A 机器（策略）：**

```bash
cd ~/workspace/arm-hand-teleop
./scripts/o10/dual_arm/ros2_policy_o10_dual.sh
```

**B 机器（硬件）：**

```bash
cd ~/workspace/arm-hand-teleop
./scripts/o10/dual_arm/ros2_bridge_o10_dual.sh
```

### 常用环境变量（启动前 export 覆盖默认值）

```bash
# 策略与模型
export ARM_HAND_TELEOP_POLICY=pi05
export ARM_HAND_TELEOP_PI05_MODEL_PATH=/你的/checkpoint/pretrained_model
# 频率与异步参数
export ARM_HAND_TELEOP_ASYNC_FPS=15
export ARM_HAND_TELEOP_ASYNC_ACTIONS_PER_CHUNK=50
export ARM_HAND_TELEOP_ASYNC_CHUNK_SIZE_THRESHOLD=0.8
# 网络
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
# RTC 实时分块（A 机器）
export ARM_HAND_TELEOP_RTC_ENABLED=1
```

脚本里所有 `--policy/--model_path/--fps/...` 后面也支持直接透传额外参数，例如：

```bash
./scripts/o10/dual_arm/ros2_bridge_o10_dual.sh --num_episodes 3
```

---

## 4. 验证在跑

任一机器，先 source ROS：

```bash
source /opt/ros/jazzy/setup.bash
source ~/workspace/arm-hand-teleop/ros2_ws/install/setup.bash

ros2 node list                                # /lerobot_robot_bridge, /lerobot_policy_node
ros2 topic echo /lerobot/robot_schema --once  # 握手是否到位
ros2 topic hz   /lerobot/observation          # ≈ fps（如 15Hz）
ros2 topic hz   /lerobot/action_chunk         # 有动作 chunk 回流
```

四样都正常 = 链路通了。

---

## 5. 复位 / 停止（任一机器）

```bash
ros2 service call /lerobot_robot_bridge/reset std_srvs/srv/Trigger "{}"
ros2 service call /lerobot_robot_bridge/stop  std_srvs/srv/Trigger "{}"
```

- 默认情况下 B 自己跑 episode 循环（`num_episodes`，每轮之间自动归零），和现有 async 推理一样。
- 这两个服务是给操作者**按需**触发用的。`reset` 会先让控制环停手再归零（不会和发动作/读观测并发抢 CAN）。

---

## 6. 首次真机最容易踩的坑

> 目前 ROS2 链路是用"假机器人 + 桩策略"在单机回环测通的（消息、传输、握手都验证过）。
> 真实硬件 + 真实策略的端到端是**明天第一次跑**，下面三点最可能挡路：

1. **B 上的 `model_path` 解析不到** —— 最常见。B 端启动会读 `config.json`，路径不存在就直接报错。
   → 把 checkpoint 同步到 B 的相同绝对路径（见 2.5）。

2. **相机 key 和策略训练时对不上** —— 比如缺 `right_wrist` 相机会导致每个 episode 无限复位。
   → 先 `rs-enumerate-devices` 确认相机都枚举到、序列号正确；确认 B 的 `get_observation()`
   出的相机 key 和模型期望的 `observation.images.*` 一致。

3. **`configs/dual_arm/o10_dual_infer.yaml` 的 `robot` 块和 B 的真实硬件不匹配** ——
   CAN 口、handedness、相机配置要对。这份 YAML 和你平时本地 infer 用的是同一份，确认 B 上这份是对的。

排错时贴 B 端 bridge 或 A 端 policy 的报错即可定位。

---

## 7. 远程启动（可选）

ROS2 本身**不会**帮你在另一台机器上拉起进程（DDS 只在两个节点都起来后负责传数据）。
想在 A 上一键启动 B 的 bridge，用 SSH：

```bash
ssh <用户>@<B的IP> 'cd ~/workspace/arm-hand-teleop && ./scripts/o10/dual_arm/ros2_bridge_o10_dual.sh'
```

> bridge 脚本自带 `pgrep` 去重预检，防止同一台机器上重复启动两个 bridge 抢 CAN 总线。

---

## 8. 一句话流程

**A 推 → B 拉 → 两边各 `colcon build` 一次 → A 起 policy、B 起 bridge → `ros2 topic hz` 看数据流。**
第一个最可能卡住的是 B 上的 `model_path`，先把它准备好。
