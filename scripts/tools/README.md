# scripts/tools/

运维、调试、数据处理用的一次性脚本。

---

## 硬件调试

### `save_reset_pose.py`
读取单臂当前关节角度并打印，用于人工更新 `configs/reset_poses/` 下的 JSON 文件。

```bash
python scripts/tools/save_reset_pose.py
python scripts/tools/save_reset_pose.py --port can0 --handedness right
```

### `save_dual_reset_pose.py`
读取双臂当前关节角度，写入 reset pose JSON 文件。

```bash
python scripts/tools/save_dual_reset_pose.py
python scripts/tools/save_dual_reset_pose.py --left-port can0 --right-port can1
```

### `save_gesture_reset_poses.py`
读取双臂当前臂关节位置，结合预定义手势（pinch / tripod）的 open 状态，
生成各手势对应的 reset pose JSON，写入 `configs/reset_poses/`。

```bash
python scripts/tools/save_gesture_reset_poses.py                  # 生成所有手势
python scripts/tools/save_gesture_reset_poses.py --gesture pinch
```

### `set_pose.py`
把手臂/手移到指定位置，用于检查 pose 是否正确。

```bash
python scripts/tools/set_pose.py --from-json configs/reset_poses/o10_dual_reset.json
python scripts/tools/set_pose.py --arm 0 0 0 0 0 0 --hand 0 -1.14 0.37 0 0.22 0.09 0.02 0.04 0.02 0.07
python scripts/tools/set_pose.py --read-only   # 只读当前位置
```

### `check_tactile_success.py`
判断"笔触摄像头"任务是否成功：右手拇指/食指/中指触觉均值均超过阈值则视为成功。
可作为函数导入，也可独立运行验证阈值。

```bash
python scripts/tools/check_tactile_success.py --thumb 50 --index 40 --middle 45 --threshold 30
```

---

## 数据处理

### `strip_tactile.py`
从 LeRobot v3.0 数据集中删除 O10 触觉信息，生成新数据集。
`videos/` 和 `images/` 用符号链接代替复制，不占额外磁盘空间。

适用场景：录制时带 `tactile_mode: 130d` 触觉 raw 列，处理后去掉触觉，供 π0/π0.5 等不支持触觉输入的模型训练。

```bash
# 默认在同级目录生成 <数据集名>_no_tactile
python scripts/tools/strip_tactile.py --input ~/workspace/dataset/.../my_dataset

# 指定输出路径
python scripts/tools/strip_tactile.py \
    --input  ~/workspace/dataset/.../my_dataset \
    --output ~/workspace/dataset/.../my_dataset_aloha
```

脚本会自动识别左手、右手或双手触觉列：

- 新 raw schema：删除 `observation.tactile.left_raw` / `observation.tactile.right_raw`，`observation.state` 维度不变。
- 旧 raw schema：如果触觉曾被拼进 `observation.state`，会按 feature name 中的 `tactile` 维度切掉。

输出数据集会额外写入 `meta/o10_no_tactile_schema.json`，记录来源线路和被删除的触觉字段。

### `convert_o10_tactile_heatmap.py`
把 O10 raw 130D 触觉列转成 `lerobot_tactile` 风格的二维触觉热力图字段，生成新数据集。
输出字段 shape 固定为 `float32[12, 32]`：

- `observation.tactile.left_raw`  → `observation.tactile.left`
- `observation.tactile.right_raw` → `observation.tactile.right`

默认保留 `*_raw`，这样以后如果要换热力图布局还能重新转换；加 `--drop-raw` 时只保留热力图字段。
`videos/` 和 `images/` 同样用符号链接代替复制。

```bash
# 默认在同级目录生成 <数据集名>_tactile_heatmap
python scripts/tools/convert_o10_tactile_heatmap.py \
    --input ~/workspace/dataset/.../my_raw_dataset

# 只保留 heatmap，删除 raw 130D
python scripts/tools/convert_o10_tactile_heatmap.py \
    --input    ~/workspace/dataset/.../my_raw_dataset \
    --output   ~/workspace/dataset/.../my_heatmap_dataset \
    --drop-raw

# 覆盖已有输出目录
python scripts/tools/convert_o10_tactile_heatmap.py \
    --input ~/workspace/dataset/.../my_raw_dataset \
    --overwrite
```

脚本会写入 `meta/o10_tactile_heatmap_schema.json`，记录左/右/双手线路、raw 字段到 heatmap 字段的映射，以及 130D 在 12x32 网格中的布局。

### `visualize_o10_tactile_heatmap.py`
实时查看 O10 130D 触觉映射成 12x32 heatmap 后的空间效果。

这个工具有两种布局：

- `--layout training`：训练用的紧凑 `12x32` 布局，与 `convert_o10_tactile_heatmap.py` 输出一致。
- `--layout physical`：默认布局，按 SDK 文档把五指显示成真实的 `8x2` 左右手镜像排列；掌心和手背仍按 `5x5` 近似显示。这个更适合现场按传感器检查映射。

```bash
# 不连硬件，先看模拟左右手热力图，并保存一张预览
python scripts/tools/visualize_o10_tactile_heatmap.py \
    --demo \
    --no-window \
    --save /tmp/o10_tactile_heatmap_demo.png

# 只看左手，默认 left channel_id=0
python scripts/tools/visualize_o10_tactile_heatmap.py --hand left --layout physical

# 只看右手，默认 right channel_id=1
python scripts/tools/visualize_o10_tactile_heatmap.py --hand right --layout physical

# 同时看左右手，窗口里左右并排显示；按 q 或 Esc 退出
python scripts/tools/visualize_o10_tactile_heatmap.py --hand both --layout physical
```

如果现场通道和默认不一样，可以显式指定：

```bash
python scripts/tools/visualize_o10_tactile_heatmap.py \
    --hand both \
    --left-channel-id 0 \
    --right-channel-id 1 \
    --device-id 1 \
    --canfd-id 0
```

实时模式默认会先采集 30 帧 baseline，请保持双手不受力；随后会减掉 baseline，并把小于 `3g` 的变化当噪声过滤掉。O10 触觉采样频率约 10Hz，所以刷新周期默认是 `0.1s`。

```bash
# 关闭 baseline，直接看原始值
python scripts/tools/visualize_o10_tactile_heatmap.py \
    --hand both \
    --baseline-frames 0 \
    --deadband 0

# 每帧自动拉伸颜色范围，适合找微弱信号；默认固定色阶是 0..255g
python scripts/tools/visualize_o10_tactile_heatmap.py \
    --hand both \
    --auto-range
```

录完数据后，也可以从 LeRobot 数据集中抽一帧检查：

```bash
python scripts/tools/visualize_o10_tactile_heatmap.py \
    --dataset ~/workspace/dataset/.../my_raw_dataset \
    --episode-index 0 \
    --frame-index 10 \
    --layout physical \
    --save /tmp/o10_tactile_frame10.png \
    --no-window
```

### `convert_lerobot_to_openpi.py`
LeRobot v3.0 格式 → openpi 训练格式的转换骨架（部分 TODO 待补全）。

```bash
python scripts/tools/convert_lerobot_to_openpi.py \
    --input  ~/workspace/dataset/.../my_dataset \
    --output ~/workspace/dataset/openpi/my_dataset \
    --task   "pick up camera"
```

---

## 运维

### `docker_export_image.sh`
把本地 Docker 镜像打包成 `.tar.gz`，默认输出到 `dist/`。

```bash
bash scripts/tools/docker_export_image.sh
bash scripts/tools/docker_export_image.sh /path/to/output.tar.gz
```
