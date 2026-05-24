# O10 runtime 共享 helper 去重设计

日期：2026-05-24
状态：设计已确认，待用户阅读书面 spec
作者：phl

## 背景

vendored `lerobot_play` 里的 AGIBOT O10 runtime 现在沿着“单臂”和“双臂”两条线各自扩展。
单臂/双臂 follower 与 leader 里已经重复了不少行为敏感逻辑：

- O10 action/state/tactile feature names 和 feature spec。
- 相机 color/depth 读帧 fallback、缓存帧复用、zero frame 生成和恢复日志。
- reset pose 加载、normalize、内存 reset target 维护。
- eef_delta 数学、IK 失败处理、4x4 pose 转 7D pose。
- gripper 1D 与 10D 手关节互转、trigger gesture open/closed 姿态查找。

这些重复逻辑会让后续改动变危险：单臂修了一个 bug，双臂可能漏改；双臂加了容错，
单臂可能还在旧路径里。这次目标刻意保守：只减少重复，不改变 runtime 行为、YAML 字段、
硬件连接生命周期或数据集 schema。

## 目标

- 在
  `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/`
  下抽出 O10 共享 helper 模块。
- 保留现有 O10 单臂/双臂 follower/leader 类作为 orchestration 层，继续负责硬件对象、
  左右侧状态和 action 发送。
- 保持所有公开配置字段、命令入口、action key、observation key、tactile key 和 dataset
  feature 顺序不变。
- 在重构前后增加聚焦的纯 Python 回归测试，用测试锁住 helper 的当前行为。
- 沿用本项目 vendored `lerobot_play` 的风格；本次不迁移到新版 upstream LeRobot 包结构。

## 非目标

- 不迁移 YAML，不新增 CLI flag。
- 不修改数据集 schema。
- 不重写机械臂、灵巧手、相机、Pico WebRTC、手套线程的连接生命周期。
- 第一阶段不引入新的共享 base class 或 mixin 继承体系。
- 不修改 vendored OmniHand SDK 或 `yudie/` runtime。
- 不顺手清理 `record.py`、`infer.py`、`control.py` 或其他无关 LeRobot helper。

## 设计

### 1. helper 模块边界

新增几个小 helper，让 O10 领域逻辑集中，但不把它变成大框架：

- `utils/o10_motion.py`
  - `rotation_matrix_from_rpy(roll, pitch, yaw)`。
  - `apply_eef_delta_to_pose(current_pose, eef_delta)`。
  - `solve_o10_ik(arm_kdl, target_pose, seed_joints)`。
  - `homogeneous_matrix_to_pose(matrix)`。
  - 保留当前 IK 兼容路径：优先调用
    `inverse_kinematics(..., force_calculate=True)`，遇到 `TypeError` 再回退到旧签名。
    IK 返回空结果时继续抛 `RuntimeError`。

- `utils/o10_camera_io.py`
  - 增加 `CameraObservationReader`，内部持有每个 camera 的缓存帧和 fallback-active 状态。
  - 提供 `read(camera_name, camera)`，返回 `(color_frame, depth_frame_or_none)`。
  - 提供 `features(camera_names, camera_configs)` 或等价 helper，用来生成 color/depth feature
    shape。
  - 相机创建和连接仍留在 follower 类里。helper 只处理相机已经存在之后的读帧行为。

- `utils/o10_schema.py`
  - 集中构造单臂/双臂 feature name。
  - 提供 tactile raw key 和 tactile feature spec，覆盖 `none` 和 `130d` 模式。
  - 保留现有 key，比如 `left.joint1.pos`、`observation.tactile.left_raw`、
    `observation.tactile.right_raw`。

- `utils/o10_hand_control.py`
  - 封装 gripper value 到 hand joints、hand joints 到 gripper value 的互转。
  - 封装 trigger gesture open/closed 查找，包括 reset-pose JSON 覆盖。
  - 内部继续调用现有 `agibot_o10` 函数，gesture 常量的来源不变。

- `utils/o10_reset.py`
  - 增加小型 reset 加载 helper：`load_reset_poses(...)` 加
    `PersistentJointTargetStore` normalize。
  - runtime 仍不写 `configs/reset_poses/o10_dual_reset.json`。
  - follower/leader 类继续负责把 reset 值赋给自己的单臂或左右侧字段。

这些 helper 以函数或小状态对象为主，不做框架级 base class。这样 refactor 更容易回退，也避免碰
MRO、硬件构造和连接顺序。

### 2. follower 类改法

`PicoFollowerSingleArmAgibotO10` 和 `PicoFollowerDualArmAgibotO10` 继续负责：

- `ah.Play` 机械臂对象和 executor/io-context。
- `AgibotO10Hand` 对象。
- 相机创建和连接。
- 每侧当前手关节缓存。
- `send_action(...)`、`get_observation(...)`、`connect(...)`、`disconnect(...)` 编排。

它们把共享逻辑下沉：

- 相机读帧 fallback 交给 `CameraObservationReader`。
- feature names 和 tactile specs 来自 `o10_schema.py`。
- eef_delta action 转换使用 `o10_motion.py`。
- gripper 转换使用 `o10_hand_control.py`。
- reset pose 加载使用 `o10_reset.py`，但只在不掩盖左右侧赋值逻辑的地方使用。

### 3. leader 类改法

`PicoLeaderSingleArmAgibotO10` 和 `PicoLeaderDualArmAgibotO10` 继续负责：

- Pico event thread 启动和 `ctrl` 状态字典。
- 每侧 LPF、IK history、transform pose、start/reset flag。
- 手套 teleoperator 对象和 trigger gate 判断。
- `get_action(...)`、`reset_pose(...)`、手部 commanded state lock。

它们把共享逻辑下沉：

- action feature 选择和 feature name list 来自 `o10_schema.py`。
- eef_delta 计算中相同的 pose 数学使用 `o10_motion.py`。
- trigger gesture 手姿态查找、gripper 插值使用 `o10_hand_control.py`。
- reset pose 文件加载使用 `o10_reset.py`，左右侧状态赋值仍留在本类。

### 4. 数据流

runtime 数据流不变：

1. Teleoperator 按 `action_control_mode` 和 `hand_action_mode` 产出 action dict。
2. Follower 把 action 转成 arm joints + 10D hand joints。
3. Follower 把 arm PVT target 和 hand joint target 发给现有硬件 adapter。
4. Follower 返回 observation，schema 与之前的 action/state/tactile/image 完全一致。

helper 只参与转换、schema 构造、pose 数学、reset 加载和相机帧 fallback。它们不直接发 CAN、
不启动线程、不连接设备。

## 错误处理

重构后保持当前行为：

- IK 失败仍抛 `RuntimeError`，拒绝发送 arm target。
- action 长度非法仍抛 `ValueError`，错误里说明 expected/got 维度。
- 相机读帧失败仍遵循 `allow_camera_read_failures`：
  - false：重新抛出相机异常。
  - true 且已有缓存：复用上一帧。
  - true 且没有缓存：生成 zero color frame，必要时生成 zero depth frame。
- 曾经失败的相机恢复成功时，只打一条恢复日志。
- reset pose 加载失败仍 warning，并回退到当前内存/default 状态。
- trigger gesture 查找仍优先使用 reset-pose JSON，找不到再使用内置 gesture 常量。

## 测试

新增聚焦测试，放在 `qiuzhi/tests/`：

- `test_o10_motion_helpers.py`
  - RPY rotation matrix 的 shape 和 identity case。
  - eef_delta translation 和 rotation 应用。
  - IK helper 支持当前 `force_calculate=True` 签名，也支持 fallback 旧签名。
  - IK 空结果抛 `RuntimeError`。
  - 4x4 pose conversion 返回 7 个值，非 4x4 输入报错。

- `test_o10_camera_io.py`
  - color-only camera 正常读帧并写入缓存。
  - color+depth camera 正常返回 depth。
  - fallback 关闭时，读帧失败重新抛异常。
  - fallback 开启且有缓存时，读帧失败复用缓存帧。
  - fallback 开启且无缓存时，首次失败生成符合配置尺寸的 zero frame。
  - 相机恢复后清掉 fallback-active 状态。

- `test_o10_schema.py`
  - 单臂 action/state feature 顺序匹配现有 `agibot_o10` 常量。
  - 双臂 action/state feature 顺序匹配当前 dual-arm 常量。
  - tactile raw key 和 130D feature spec 匹配当前行为。

- `test_o10_hand_control.py`
  - gripper 1D 通过当前 gesture helper 往返转换。
  - trigger gesture open/closed 值与现有内置姿态一致。
  - reset-pose JSON gesture 覆盖仍然优先。

同时跑现有 O10 回归测试：

```bash
env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest \
  qiuzhi/tests/test_agibot_o10.py \
  qiuzhi/tests/test_dual_arm_o10_trigger_gate.py \
  qiuzhi/tests/test_o10_camera_observation_fallback.py \
  qiuzhi/tests/test_dual_arm_tactile_schema.py \
  qiuzhi/tests/test_o10_tactile_raw_dataset_schema.py
```

完成前需要跑新增 helper 测试，以及覆盖被改 follower/leader 文件的 O10 相关测试。

## 实施顺序

建议拆成小 patch：

1. 新增 helper 模块和测试；可行时先让旧类暂时不接入 helper，只先锁住行为。
2. 单臂 follower 调用点切到 helper。
3. 双臂 follower 调用点切到 helper。
4. 单臂和双臂 leader 调用点切到 helper。
5. 测试证明 helper 路径行为一致后，再删除重复的 private 函数/常量。

第一轮实现以“减少重复、少改结构”为准。如果某段 helper 开始需要大量 callback 回 runtime 类，
说明边界没切好，这段先保留在原类里，作为后续候选项记录，不强行抽。

## 风险

- feature 顺序回归会悄悄破坏数据集兼容性。schema 测试必须比较完整、有序 key 序列。
- 相机 fallback 有状态。缓存/fallback flag 移到 helper 后，必须保证每个 follower 一个
  reader 实例，不能用全局共享状态。
- 双臂左右前缀容易写反。测试要覆盖 left/right key 和 trigger gesture 行为。
- reset helper 抽得太激进会隐藏左右侧状态赋值。第一阶段把赋值留在 runtime 类里。

## 成功标准

- O10 单臂/双臂 runtime 类更短，重复 helper 逻辑减少。
- 公开 action/observation/tactile/image key 不变。
- 现有 O10 测试继续通过。
- 新增 helper 测试不需要 CAN 硬件、相机、Pico 或手套服务。
- 不格式化无关文件，不碰 vendor artifact。
