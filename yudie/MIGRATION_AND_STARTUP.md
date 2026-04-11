# 宇叠控制智元迁移与启动说明

本文档对应项目目录 `yudie`，用于把当前这套 `O10` 控制链路迁移到另一台 Linux 机器。

## 1. 打包内容说明

当前迁移包包含两部分:

- `yudie_project.zip`
  - 项目代码
  - `O10` 控制逻辑
  - 本地 `omnihand_2025` SDK
  - `vendor_sdk`
  - 手套 web/service 目录
  - 当前已调整好的配置文件
- `arm-hand-teleop_env.zip`
  - 当前使用的 conda 虚拟环境
  - 已包含运行本项目所需 Python 依赖

## 2. 迁移目标机要求

建议目标机器满足以下条件:

- Linux x86_64
- 能正常连接智元灵巧手的 USB-CAN 设备
- 能正常识别宇叠手套串口设备
- 具备 `unzip` 命令

## 3. 解压方式

假设你要把项目放到:

- 项目目录: `/home/USER/workspace`
- 环境目录: `/home/USER/envs/arm-hand-teleop`

先解压项目:

```bash
mkdir -p /home/USER/workspace
cd /home/USER/workspace
unzip /path/to/yudie_project.zip
```

再解压环境:

```bash
mkdir -p /home/USER/envs/arm-hand-teleop
cd /home/USER/envs/arm-hand-teleop
unzip /path/to/arm-hand-teleop_env.zip
```

## 4. 激活环境

```bash
source /home/USER/envs/arm-hand-teleop/bin/activate
conda-unpack
```

说明:

- `conda-unpack` 只需要在新机器第一次解压后执行一次
- 这个环境包保留了 Linux 符号链接，所以建议在 Linux 下解压和运行

## 5. 启动顺序

### 第一步: 启动宇叠服务

```bash
cd /home/USER/workspace/yudie/HDW-Regular_V2.2.5_202604021755_Ubuntu22+_x86_64
./start_hdservice.sh
```

正常情况下你会看到:

- 手套串口识别成功
- 左右手设备识别成功
- UDP sender started

### 第二步: 启动 web 页面

```bash
cd /home/USER/workspace/yudie/HDW-Regular_V2.2.5_202604021755_Ubuntu22+_x86_64
./start_hdweb.sh
```

正常会提示浏览器访问地址，例如:

```text
Open http://<你的机器IP>:8088/ in your browser
```

### 第三步: 启动 Python 控制程序

新开一个终端:

```bash
source /home/USER/envs/arm-hand-teleop/bin/activate
cd /home/USER/workspace/yudie
python DexHand_Motion_Control_Program.py
```

## 6. 当前代码的关键说明

这套项目当前按 `O10` 路线整理，关键入口如下:

- 主程序: `DexHand_Motion_Control_Program.py`
- O10 控制实现: `AGIBOT/Omnihand_o10_yudie.py`
- 数据接收: `Data_Receiver.py`
- 本地 SDK 引导: `sdk_bootstrap.py`
- 本地 SDK 包: `omnihand_2025/`

其中:

- `DexHand_Motion_Control_Program.py` 已经改为优先加载项目内的 `omnihand_2025`
- 不再依赖把 SDK 只装在某个 conda 环境里
- 当前不依赖 `agibot_hand`，因为你现在只跑 `O10`

## 7. 常见问题

### 7.1 `Open device 0 usbcanfd failed`

通常说明 CAN 设备没打开成功，常见原因:

- USB-CAN 没插好
- 驱动库没有被正常加载
- 设备权限不足
- 设备号或通道号不对

### 7.2 `OmniHand CAN device is not ready`

通常说明:

- CAN 已打开，但手本体没有真正 ready
- 总线连线、供电、通道选择有问题

### 7.3 `AttributeError: 'NoneType' object has no attribute 'get'`

这个问题之前已经处理过。当前 `Data_Receiver.py` 已增加 role fallback 逻辑:

- 如果请求的 role 没有数据
- 会回退到收到的第一个可用 role

### 7.4 `Address already in use`

说明端口已经被占用。当前 web 启动脚本已经做过兼容处理，但如果你手动重复启动，还是建议先确认旧进程是否还在。

## 8. 推荐的运行习惯

- 先启动 `hdservice`
- 再启动 `hdweb`
- 最后启动 Python 主程序
- 停止时先关 Python，再关 web/service

## 9. 如果要重新部署到新的 conda 环境

除了直接使用 `arm-hand-teleop_env.zip`，你也可以用以下文件重建:

- `environment.yml`
- `explicit.txt`

但对这套项目来说，直接解压 `arm-hand-teleop_env.zip` 是最省事、最接近当前运行状态的方式。
