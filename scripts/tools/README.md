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
从 LeRobot v3.0 数据集的 `observation.state` 中删除触觉列，生成新数据集。
`videos/` 和 `images/` 用符号链接代替复制，不占额外磁盘空间。

适用场景：录制时带触觉（供 diffusion 训练），处理后去掉触觉（供 π0 等 ALOHA 系预训练模型微调）。

```bash
# 默认在同级目录生成 <数据集名>_no_tactile
python scripts/tools/strip_tactile.py --input ~/workspace/dataset/.../my_dataset

# 指定输出路径
python scripts/tools/strip_tactile.py \
    --input  ~/workspace/dataset/.../my_dataset \
    --output ~/workspace/dataset/.../my_dataset_aloha
```

处理后 `observation.state` 维度变化示例：
- `dexterous_10d` + `tactile_mode: 7d`：46D → 32D
- `gripper_1d` + `tactile_mode: 7d`：28D → 14D（与 ALOHA 对齐）

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
