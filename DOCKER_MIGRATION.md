# Docker Migration Guide

这套方案把项目源码、vendored SDK 和主要 Python 运行环境一起打进镜像，方便迁移到另一台 Linux x86_64 机器。

如果目标机没有 GPU，也可以直接使用当前镜像。
当前导出的镜像已经验证过可以在“不挂载 GPU”的容器里正常导入 `torch`、`omnihand_2025` 和项目入口。
只是镜像里仍然包含 CUDA 相关依赖，所以体积会比纯 CPU 镜像更大。

## 快速迁移清单

下面这份流程适合“旧电脑打包，迁移到另一台只有 CPU 的新电脑”。

### 旧电脑

1. 确认镜像包存在：

```bash
ls -lh /home/phl/workspace/arm-hand-teleop/dist/*.tar.gz
```

2. 把下面两个东西一起拷到新电脑：

- 镜像包：`dist/arm-hand-teleop_*.tar.gz`
- 整个仓库目录：`arm-hand-teleop/`

例如：

```bash
scp /home/phl/workspace/arm-hand-teleop/dist/arm-hand-teleop_20260416_140310.tar.gz user@NEW_PC:/home/user/
rsync -av --exclude '.git' /home/phl/workspace/arm-hand-teleop/ user@NEW_PC:/home/user/arm-hand-teleop/
```

### 新电脑

1. 安装 Docker：

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
newgrp docker
```

2. 导入镜像：

```bash
gunzip -c /home/user/arm-hand-teleop_20260416_140310.tar.gz | docker load
docker images | grep arm-hand-teleop
```

3. 启动容器：

```bash
cd /home/user/arm-hand-teleop
docker compose -f docker/compose.hardware.yaml up -d
docker compose -f docker/compose.hardware.yaml exec arm-hand-teleop /bin/bash
```

4. 容器内运行：

```bash
./scripts/control_o10_right.sh
./scripts/record_o10_right.sh
./scripts/replay_o10_right.sh
./scripts/infer_o10_right_cpu.sh
```

### CPU 目标机注意事项

- 不要叠加 `docker/compose.gpu.yaml`
- 不要在 `docker run` 里加 `--gpus all`
- 推理请使用 `./scripts/infer_o10_right_cpu.sh`
- `control`、`record`、`replay` 不依赖 GPU
- `infer` 可以在 CPU 上运行，但速度会明显慢于 GPU

## 1. 前提假设

- 目标机是 Linux x86_64
- 目标机已经安装 Docker 和 Docker Compose Plugin
- 如果要跑 `infer` 的 `cuda` 模式，目标机还需要安装 NVIDIA Driver 和 NVIDIA Container Toolkit
- CAN、RealSense、USB 相机、手套串口/USB 设备都直接接在宿主机上

## 2. 镜像里包含什么

- 当前仓库源码，固定放在容器内 `/home/phl/workspace/arm-hand-teleop`
- `qiuzhi/` 下 vendored 的 `lerobot_play` 和本地 wheel
- `yudie/` 下 HDService / HDWeb / OmniHand vendored SDK
- ROS 2 Jazzy 运行环境
- 项目主要 Python 依赖
- Docker 构建时现编译的 OmniHand Python 扩展

说明：

- 我保留了容器内的 `/home/phl/workspace/arm-hand-teleop` 路径，这样你现有 yaml 里的绝对路径不需要重写
- 数据集和模型目录建议走宿主机挂载，不建议直接打进镜像

## 3. 本机构建镜像

在当前机器项目根目录执行：

```bash
./scripts/docker_build_image.sh
```

默认镜像名：

```bash
arm-hand-teleop:jazzy
```

如果你想换名字：

```bash
ARM_HAND_TELEOP_IMAGE=my-o10:20260416 ./scripts/docker_build_image.sh
```

## 4. 导出镜像

构建完成后导出成 tar.gz：

```bash
./scripts/docker_export_image.sh
```

或者显式指定导出路径：

```bash
./scripts/docker_export_image.sh ./dist/arm-hand-teleop_20260416.tar.gz
```

把这个 `tar.gz` 拷到目标机即可。

## 5. 目标机导入镜像

```bash
gunzip -c /path/to/arm-hand-teleop_20260416.tar.gz | docker load
```

如果导入后想确认：

```bash
docker images | grep arm-hand-teleop
```

## 6. 目标机运行方式

### 方式 A：仓库也一起拷过去，用 compose 管理

如果你把仓库也同步到了目标机，推荐直接用 compose：

```bash
cd /path/to/arm-hand-teleop
docker compose -f docker/compose.hardware.yaml up -d
```

如果要启用 GPU：

```bash
cd /path/to/arm-hand-teleop
docker compose -f docker/compose.hardware.yaml -f docker/compose.gpu.yaml up -d
```

进入容器：

```bash
docker compose -f docker/compose.hardware.yaml exec arm-hand-teleop /bin/bash
```

容器里继续使用你熟悉的命令：

```bash
./scripts/start_hdservice.sh
./scripts/start_hdweb.sh
./scripts/control_o10_right.sh
./scripts/record_o10_right.sh
./scripts/replay_o10_right.sh
./scripts/infer_o10_right.sh
```

如果目标机只有 CPU，推理请改用：

```bash
./scripts/infer_o10_right_cpu.sh
```

这份脚本会使用：

```bash
configs/o10_right_infer_cpu.yaml
```

也就是把推理设备固定成 `cpu`，避免继续沿用原先的 `cuda` 配置。

如果你希望数据和模型放在宿主机其他目录，可以先导出环境变量再起 compose：

```bash
export DATASET_ROOT=/data/agi_arm_bot
export MODEL_ROOT=/data/mymodels
export MODEL_ROOT_SINGLE=/data/mymodel
docker compose -f docker/compose.hardware.yaml up -d
```

### 方式 B：只带镜像，不拷仓库

也可以直接在目标机手写 `docker run`：

```bash
docker run --rm -it \
  --name arm-hand-teleop \
  --privileged \
  --network host \
  --ipc host \
  -e DISPLAY=$DISPLAY \
  -e QT_X11_NO_MITSHM=1 \
  -v /dev:/dev \
  -v /run/udev:/run/udev:ro \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v /path/to/dataset:/home/phl/workspace/dataset \
  -v /path/to/mymodel:/home/phl/workspace/mymodel \
  -v /path/to/mymodels:/home/phl/workspace/mymodels \
  arm-hand-teleop:jazzy \
  /bin/bash
```

如果目标机有 GPU，并且你明确要跑 CUDA 推理，再额外加上：

```bash
--gpus all
```

进入容器后，项目源码已经在：

```bash
/home/phl/workspace/arm-hand-teleop
```

## 7. 宿主机侧额外注意事项

### 7.1 显示预览

如果你要在容器里看 OpenCV / X11 窗口，宿主机通常需要先执行：

```bash
xhost +local:root
```

### 7.2 CAN 口

容器默认复用宿主机网络栈，所以像 `can0` 这种接口还是由宿主机负责创建和管理。

也就是说：

- 先在宿主机把 `can0` 配好
- 容器里直接按现有配置使用 `can0`

### 7.3 RealSense / USB 相机 / 手套

这套 compose 走的是：

- `--privileged`
- `/dev` 挂载
- `/run/udev` 挂载

这样更接近“整机迁移”，比逐个设备号映射更省心。

## 8. CPU 目标机建议

- `control`、`record`、`replay` 对 GPU 没有硬要求
- `infer` 在 CPU 上可以跑，但速度会明显慢于 GPU
- 不要叠加 `docker/compose.gpu.yaml`
- 不要在 `docker run` 里加 `--gpus all`
- 使用 `./scripts/infer_o10_right_cpu.sh`，或者把你自己的推理 YAML 里的 `infer.device` 改成 `cpu`

## 9. 已知边界

- 当前镜像假设目标机也是 Ubuntu 24.04 / ROS Jazzy 这一代运行时
- HDService 二进制依赖的 `libprotobuf.so.23` 仍然走项目里自带的 `.deb` 解包逻辑
- 如果目标机没有 GPU，请把推理配置里的 `infer.device` 改成 `cpu`，或者不要启用 `compose.gpu.yaml`
- 数据集和模型默认不打进镜像，需要你通过挂载目录提供
