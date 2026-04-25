# O10 手套→机械手映射曲线优化设计

**日期**：2026-04-25
**作者**：phl
**状态**：设计已确认，待写实施计划

## 背景

当前的宇叠手套到 AGIBOT O10 机械手映射存在四类手感问题：

1. 拇指抖动 / 漂移（已加 3° 死区，但越界后立即完全跟随，边缘仍有跳变）
2. 其它手指闭合不够（机械手到不了末端）
3. 过度灵敏，难以保持中间位
4. 左右手不一致

根因都指向同一个机制：**单段线性比例 + 单次硬死区**的映射函数表达力不足。
当前实现还存在两份并行（`yudie/AGIBOT/Omnihand_o10_yudie.py`
与 `lerobot_play/utils/agibot_o10.py`），常量手抄同步，左右手限位表本身就不严格镜像。

## 目标

| 类别 | 目标 |
|---|---|
| 手感 | 解决上述 4 类症状 |
| 代码 | 算法集中到一份，左右手参数镜像化（消除"两份手抄"风险）|
| 不在范围 | 配置 YAML 化、用户标定脚本、性能优化、新增手部模型 |

## 总体方案

新增 `O10HandMapper` 类（**有状态**：维护 EMA 上一帧值与 hysteresis anchor），
完全替换现在的 `map_glove_angles_to_agibot_o10` + 两处独立的 thumb 死区分支。

mapper 只负责"10 通道角度（deg, abs） → 10 通道角度（rad, 带符号）"，
不参与手套数据的提取——yudie 那侧从 24-list 取 10 槽位、lerobot_play 那侧
从 finger 对象取 (idx, axis) 的两套 extractor 各保留原样。

### 实现位置

`O10HandMapper` 放在 `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/agibot_o10.py`，
作为该模块共用的单一来源。

`yudie/DexHand_Motion_Control_Program.py` 在 `agibotHand_O10` 分支头部
追加一段 `sys.path.insert` 把 lerobot_play 路径接进来（仅在该 mode 内生效），
然后 `yudie/AGIBOT/Omnihand_o10_yudie.py` 调用 mapper。

代价：yudie 独立 daemon 模式被引入对 lerobot_play 的隐式依赖。
收益：算法只有一份，左右手再也不会因常量抄漏而不对称。

## 信号链路（每路独立）

```
glove_deg(原始, abs)
    │
    ▼
[1] EMA 低通  y_raw = α·x + (1−α)·y_prev_raw       α=0.35 全局
    │
    ▼
[2] Hysteresis 死区（含 anchor 跟随）
        if |y_raw − anchor| < dead_band:
            out = anchor                            ← 静止时锁住
        else:
            anchor ← y_raw − sign·dead_band
            out   = anchor                          ← 越线后跟随，留 dead_band 缝
    │
    ▼
[3] 三段折线 (in_low, in_mid, in_max) ↔ (out_low, out_mid, out_max)
        [0, in_low]   → [0, out_low]               ← 中间位低增益（防漂）
        [in_low, mid] → [out_low, out_mid]         ← 正常段（线性）
        [mid, in_max] → [out_mid, out_max]         ← 末段高增益（保证闭合）
    │
    ▼
[4] 镜像 + 偏置
        out_deg = mirror_sign · out_curve          ← 左右只差符号
        if channel == 0 (thumb_roll):
            out_deg += handedness_offset           ← +10°(left) / −10°(right)
    │
    ▼
deg → rad，输出
```

### 关键设计点

- **EMA 在死区前**：先去高频抖，死区看到平滑信号，杜绝边缘震荡
- **死区作用于全部 10 路**（不再只 thumb 0/1/2）
- **Hysteresis 用 anchor 跟随**：越过 dead_band 后 anchor 跳到
  `x − sign·dead_band`，回头要走完整 dead_band 才再次锁定（Schmitt-trigger 等价）
- **三段折线把 `in_mid` 设到 `in_max` 的 55%**：把"实际人手很难到的最后部分"
  压到末段高增益区间，同样的手势能闭合更彻底
- **镜像**：左右手共用一份**幅值**参数，输出乘 `mirror_sign[i]`
  （从当前 `_ROBOT_HAND_ANGLE_LIMITS["right"]` 的符号位提取）

### Per-mapper 状态

每个 `O10HandMapper` 实例维护：

- `y_prev_raw[10]`：EMA 上一帧
- `anchor[10]`：死区锚点

无定时器、无队列。

## 参数方案

### 数据结构

```python
@dataclass(frozen=True)
class O10ChannelParams:
    in_max:    float       # 手套输入饱和点（deg, 超过即截断）
    in_low:    float       # 第 1 折点（deg）
    in_mid:    float       # 第 2 折点（deg, in_low < in_mid < in_max）
    out_max:   float       # 机械手输出饱和值（deg 幅值, 不带符号）
    out_low:   float       # in_low 处输出
    out_mid:   float       # in_mid 处输出
    dead_band: float = 3.0 # 死区宽度（deg）
```

### Mapper 级常量

- `ema_alpha = 0.35`（全局）
- `mirror_sign = [+1, -1, +1, -1, +1, +1, +1, +1, +1, +1]`
  （来源：原 `_ROBOT_HAND_ANGLE_LIMITS["right"]` 的符号位）
- `thumb_roll_offset_deg = +10°(left) | -10°(right)` 维持现状

### 默认值生成规则

以右手 limit 为锚点，左右手共用同一份幅值参数：

```python
in_max[i]  = 0.85 * glove_lim_right[i]
in_low[i]  = min(6.0, 0.30 * in_max[i])     # 防止窄量程通道 in_low ≥ in_mid
in_mid[i]  = 0.55 * in_max[i]
out_max[i] = abs(robot_lim_right[i])
out_low[i] = 0.04 * out_max[i]
out_mid[i] = 0.30 * out_max[i]
dead_band  = 3.0
```

> `in_low` 取 `min(6, 30%·in_max)` 是为了让窄量程通道（如 idx 6 ring_mp_yaw，
> in_max=17）的低段不至于挤掉中段——纯固定 6° 在那个通道下中段只剩 3.4°。

### 默认值展开（10 路）

| idx | 关节 | in_max | in_low | in_mid | out_max | out_low | out_mid |
|-----|---|--------|--------|--------|---------|---------|---------|
| 0 | thumb_cm_roll   | 31.4 | 6 | 17.3 | 60  | 2.4 | 18.0 |
| 1 | thumb_cm_yaw    | 25.5 | 6 | 14.0 | 100 | 4.0 | 30.0 |
| 2 | thumb_cm_pitch  | 51.0 | 6 | 28.1 | 49  | 2.0 | 14.7 |
| 3 | index_mp_yaw    | 25.5 | 6 | 14.0 | 12  | 0.5 | 3.6  |
| 4 | index_mp_pitch  | 68.9 | 6 | 37.9 | 90  | 3.6 | 27.0 |
| 5 | middle_mp_pitch | 68.9 | 6 | 37.9 | 90  | 3.6 | 27.0 |
| 6 | ring_mp_yaw     | 17.0 | 5.1 | 9.4  | 10  | 0.4 | 3.0  |
| 7 | ring_mp_pitch   | 68.9 | 6 | 37.9 | 90  | 3.6 | 27.0 |
| 8 | pinky_mp_yaw    | 25.5 | 6 | 14.0 | 10  | 0.4 | 3.0  |
| 9 | pinky_mp_pitch  | 85.0 | 6 | 46.8 | 90  | 3.6 | 27.0 |

### 调参约定

- 参数仍写死在模块顶部常量；本次不做 YAML 化
- 构造器接受覆盖：
  `O10HandMapper(handedness="right", channel_overrides={"index_mp_pitch": {"in_max": 50}})`
- **最可能需要试机后再调的**：`in_max` 的 85% 系数、`out_mid` 的 30% 系数
- 这两个系数在模块顶部以单独常量列出，便于一次改动影响全通道

## 测试

新文件 `qiuzhi/tests/test_o10_hand_mapper.py`，纯函数 + 状态推进，不需要硬件。
延续 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/` 的现有约定。

| # | 测试 | 验证点 |
|---|---|---|
| T1 | 死区 hysteresis | 静止 → 输出锁定；越过 dead_band → anchor 跟随；anchor 跟随后回头要走完整 dead_band 才再次锁定 |
| T2 | EMA 平滑 | 输入阶跃 0→30°，连续 5 帧后输出落在阶跃中段 |
| T3 | 三段折线 | 喂入每段断点 + 段中点，输出落在预期值（含通道 4 / 9 这类 in_max 不同的）|
| T4 | 左右镜像 | 同一组幅值输入 → 左右两 mapper 输出绝对值相等，符号按 `mirror_sign` 翻转 |
| T5 | thumb roll 偏置 | channel 0 输入 0°，左手输出 +10°→rad，右手 -10°→rad |
| T6 | 输入饱和 | 输入 > `in_max` → 输出 = `out_max`（截断而非外推）|
| T7 | 通道独立性 | 给一路高速变化、其它路保持稳定，确认状态不串 |
| T8 | 替换前后差异 | 旧 `map_glove_angles_to_agibot_o10` 在中段输入下，新 mapper 输出**不同**且方向正确（保证手感真在改、不是 no-op）|

现有测试更新：

- `qiuzhi/tests/test_agibot_o10_glove_teleoperator.py::test_update_hand_data_applies_deadband_to_thumb_joints_only`
  语义已变（死区现在覆盖全 10 路且在 mapper 内），改成对应新行为
- `tests/AGIBOT/test_pinch_grasp.py` 已 skip，不受影响

## 迁移路径

### Step 1 — 新增 `O10HandMapper`

文件：`qiuzhi/.../lerobot_play/utils/agibot_o10.py`

- 添加 `O10ChannelParams`、默认参数表生成代码、`O10HandMapper` 类
- 旧的 `_ROBOT_HAND_ANGLE_LIMITS` / `_GLOVE_HAND_ANGLE_LIMITS` /
  `map_glove_angles_to_agibot_o10` / `glove_vec_to_agibot_o10_joint_angles` 全部删除
  （外部无调用，保留只增加歧义）
- `mirror_sign` 与 `out_max` 在 mapper 内重新硬编码（不再依赖被删的常量表），
  数值与原 `_ROBOT_HAND_ANGLE_LIMITS["right"]` 的符号 / 绝对值一致

### Step 2 — lerobot_play teleop 切到 mapper

`agibot_o10_hand.py`：

- 删 `O10_THUMB_DEADBAND_RAD`、`O10_THUMB_JOINT_INDICES`，删 `update_hand_data` 内的拇指死区分支
- `__init__` 实例化 `self.mapper = O10HandMapper(handedness)`
- `_data_listening_loop` 内：`finger_data` → `extract_ude_glove_angles` →
  `self.mapper.map(...)` → `update_hand_data(rad)`
- `update_hand_data` 仅做线程安全写入

### Step 3 — yudie 切到 mapper

`yudie/DexHand_Motion_Control_Program.py`：

- 在 `agibotHand_O10` 分支顶端追加 `sys.path.insert` 把 lerobot_play 路径接进来
  （只在该 mode 内做）

`yudie/AGIBOT/Omnihand_o10_yudie.py`：

- 删 `O10_THUMB_DEADBAND_RAD`、`O10_THUMB_JOINT_INDICES`、
  `_apply_thumb_deadband`、`_last_o10_joint_positions_by_hand_id`
- `set_hand_position` 持有 `_mapper_by_hand_id: dict[int, O10HandMapper]`，
  第一次见到 hand 实例时按 `hand_type` 创建 mapper
- `get_finger_data_for_AgibotHandO10hand_Angles` 缩减为只做 24-list → 10 槽位提取
  （索引 [20, 3, 2, 7, 6, 10, 15, 14, 19, 18]），不含缩放，输出 deg；缩放交给 mapper

### Step 4 — 测试

- 新加 T1–T8（`qiuzhi/tests/test_o10_hand_mapper.py`）
- 修改既有 T9（`test_update_hand_data_applies_deadband_to_thumb_joints_only`）适配新行为

### Step 5 — 试机调参（不在本 PR 内）

- 跑一次 record，主观试 4 个症状是否缓解
- 不行就改 `IN_MAX_RATIO`（85% → 80%/90%）或 `OUT_MID_RATIO`（30% → 25%/35%）
- 这两个系数在模块顶部以单独常量列出

## 风险 & 回滚

| 风险 | 应对 |
|---|---|
| 默认参数手感不对 | Step 5 调参；最坏 `git revert` 整个 PR（旧 limit 表已删但路径全切走，revert 是干净路径）|
| yudie 独立 daemon 引入 lerobot_play 依赖让启动方式坏掉 | 必须本地手测一次 `python yudie/DexHand_Motion_Control_Program.py --mode agibotHand_O10 --hand right` 能起，CI 测不到这条链路 |
| EMA 引入一帧延迟 | 25 Hz 控制频率下 α=0.35 的等效延迟 ≈ 80ms，可接受；如试机感觉钝可将 α 调到 0.5+ |
| `id(hand)` 字典在 Python GC 后被复用 | mapper 实例与 hand 实例同生命周期（不删 hand 就不删 mapper），但仍需在 `init_hand_*` 调用前清理上次缓存（DexHand 单进程一次启动通常只创建一次 hand，影响小）|

## 不在范围内（避免 scope creep）

- 参数 YAML 化、用户标定脚本（下一次"配置化"迭代再做）
- 旧 `map_glove_angles_to_agibot_o10` / `glove_vec_to_agibot_o10_joint_angles` 的去重——
  本设计直接删除，不留 deprecated 包装
- `Omnihand_o12_yudie.py` 的对应优化（O12 不在本次目标内）
- 性能优化（mapper 单次调用 < 100µs，远低于 25 Hz 周期）
