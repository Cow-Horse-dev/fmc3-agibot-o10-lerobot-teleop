# O10 tactile raw dataset schema

O10 触觉采集只保留两种模式：

- `tactile_mode: "none"`：不录触觉，数据格式与旧的无触觉数据集一致。
- `tactile_mode: "130d"`：录全手 raw 130D 触觉，并把触觉保存为独立字段。

不要再使用 `7d` 或 `80d` 作为数据集 schema。

## 单右手

```text
observation.state                 float32[7]
  joint1.pos ... joint6.pos, gripper.pos

observation.tactile.right_raw      float32[130]
action                             float32[7]
observation.images.<camera>        video/image
```

## 单左手

```text
observation.state                 float32[7]
  joint1.pos ... joint6.pos, gripper.pos

observation.tactile.left_raw       float32[130]
action                             float32[7]
observation.images.<camera>        video/image
```

## 双手

```text
observation.state                 float32[14]
  left.joint1.pos ... left.joint6.pos, left.gripper.pos,
  right.joint1.pos ... right.joint6.pos, right.gripper.pos

observation.tactile.left_raw       float32[130]
observation.tactile.right_raw      float32[130]
action                             float32[14]
observation.images.<camera>        video/image
```

## 130D 顺序

每只手的 raw 130D 顺序固定为：

```text
0..15      tactile.thumb_0 ... tactile.thumb_15
16..31     tactile.index_0 ... tactile.index_15
32..47     tactile.middle_0 ... tactile.middle_15
48..63     tactile.ring_0 ... tactile.ring_15
64..79     tactile.little_0 ... tactile.little_15
80..104    tactile.palm_0 ... tactile.palm_24
105..129   tactile.dorsum_0 ... tactile.dorsum_24
```

双手字段的 `names` 会带 `left.` / `right.` 前缀；单手字段的 tactile raw key 已经包含左右手信息。

## 去触觉训练

π0/π0.5 等不支持触觉输入的模型，先从 raw 数据集生成 no-tactile 数据集：

```bash
python scripts/tools/strip_tactile.py \
    --input  ~/workspace/dataset/Robot/agi_arm_bot/my_raw_dataset \
    --output ~/workspace/dataset/Robot/agi_arm_bot/my_raw_dataset_no_tactile
```

脚本会自动识别左手、右手或双手触觉字段，删除：

- `observation.tactile.left_raw`
- `observation.tactile.right_raw`
- 旧格式中混在 `observation.state` 内的 tactile 维度

输出目录会写入 `meta/o10_no_tactile_schema.json`，记录来源线路和被删除的触觉字段。

## 转成触觉热力图

需要训练或可视化支持二维触觉输入的模型时，先从 raw 数据集生成 heatmap 数据集：

```bash
python scripts/tools/convert_o10_tactile_heatmap.py \
    --input  ~/workspace/dataset/Robot/agi_arm_bot/my_raw_dataset \
    --output ~/workspace/dataset/Robot/agi_arm_bot/my_raw_dataset_tactile_heatmap
```

输出字段兼容 `lerobot_tactile` 的二维 tactile 约定：

```text
observation.tactile.left           float32[12, 32]
observation.tactile.right          float32[12, 32]
```

默认会保留 `observation.tactile.left_raw` / `right_raw`，方便以后改布局后重新转换。
如果只想保留热力图字段：

```bash
python scripts/tools/convert_o10_tactile_heatmap.py \
    --input  ~/workspace/dataset/Robot/agi_arm_bot/my_raw_dataset \
    --output ~/workspace/dataset/Robot/agi_arm_bot/my_heatmap_only_dataset \
    --drop-raw
```

当前 130D 到 12x32 的布局：

| raw 段 | heatmap 位置 |
|---|---|
| `thumb[0:16]` | rows `0:4`, cols `0:4` |
| `index[0:16]` | rows `0:4`, cols `7:11` |
| `middle[0:16]` | rows `0:4`, cols `14:18` |
| `ring[0:16]` | rows `0:4`, cols `21:25` |
| `little[0:16]` | rows `0:4`, cols `28:32` |
| `palm[0:25]` | rows `6:11`, cols `6:11` |
| `dorsum[0:25]` | rows `6:11`, cols `21:26` |

输出目录会写入 `meta/o10_tactile_heatmap_schema.json`，记录来源线路、字段映射和具体布局。
