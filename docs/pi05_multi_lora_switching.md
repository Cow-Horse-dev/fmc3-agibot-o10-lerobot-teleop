# PI0.5 Multi-LoRA Switching

这份文档说明 O10 右臂 PI0.5 多 LoRA 的实现逻辑、运行链路、切换方式和当前限制。

## 1. 目标

这套实现要解决的问题是：

- 只启动一个 PI0.5 推理进程。
- 只加载一份 base model。
- 预加载多个 LoRA adapter。
- 在运行过程中按任务切换当前激活的 adapter。
- 切换时同步更新送给策略的自然语言 `task` 文本。

它的重点不是“多模型并行推理”，而是“同一个 PEFT policy 在多个任务 profile 之间快速切换”。

## 2. 总体思路

当前实现使用四个核心对象：

1. `TaskProfile`
   - 描述一个任务 profile。
   - 包含三个字段：`profile_id`、`adapter_path`、`task_description`。

2. `TaskProfileRegistry`
   - 从 YAML/JSON 配置读取全部 profile。
   - 管理默认 profile、命令文件路径、base model 路径。
   - 负责两种映射：
     - `profile_id -> adapter`
     - `task_description -> profile_id`

3. `TaskSwitchCommandStore`
   - 负责把“切换请求”写到 command file。
   - 写入采用临时文件再 `replace()` 的方式，避免读到半写入状态。

4. `SwitchablePeftPolicy`
   - 对实际 PEFT policy 的一层包装。
   - 初始化时保留默认 adapter 为激活状态。
   - 再把其余 adapter 预加载进同一个 policy。
   - 切换时只调用 `set_adapter(...)`，不重新建模型。

核心代码在 [multi_lora.py](/home/phl/workspace/arm-hand-teleop/qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/multi_lora.py)。

## 3. 配置格式

右臂当前使用的多 LoRA 配置文件是 [o10_right_pi05_lora_tasks.yaml](/home/phl/workspace/arm-hand-teleop/configs/right_arm/o10_right_pi05_lora_tasks.yaml)。

它的结构是：

```yaml
base_model_path: /path/to/pi05_base
default_profile: black_to_yellow
command_file: /tmp/o10_right_pi05_lora_switch.json

profiles:
  black_to_yellow:
    task_description: use the right arm to move the tissue from the black paper to the yellow paper
    adapter_path: /path/to/adapter_a
  yellow_to_black:
    task_description: use the right arm to move the tissue from the yellow paper to the black paper
    adapter_path: /path/to/adapter_b
```

字段含义：

- `base_model_path`
  - base PI0.5 模型目录。
  - 如果不写，代码会尝试从默认 adapter 的 `adapter_config.json` 里读取 `base_model_name_or_path`。

- `default_profile`
  - 启动时默认激活哪个 LoRA。

- `command_file`
  - 切换命令写入的目标文件。
  - 推理循环不会直接监听 shell 命令，而是轮询这个文件。

- `profiles.<profile_id>.task_description`
  - 这个字符串会在推理时作为 `task` 文本送入模型。
  - 同时异步服务端也用它来反查应该切到哪个 LoRA。

- `profiles.<profile_id>.adapter_path`
  - 该任务对应的 LoRA adapter 路径。

## 4. 模型加载逻辑

入口在 [infer.py](/home/phl/workspace/arm-hand-teleop/qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/infer.py)。

加载流程是：

1. 先判断 `model_path` 是不是一个多 LoRA 配置文件。
2. 如果是：
   - 读取 `TaskProfileRegistry`。
   - 取默认 profile 的 adapter。
   - 根据 `base_model_path` 加载 base PI0.5 policy。
   - 调用 `PeftModel.from_pretrained(...)` 加载默认 adapter。
   - 包装成 `SwitchablePeftPolicy`。
   - 调用 `preload_remaining_adapters()` 预加载其他 adapter。

这样启动完成后，内存里是：

- 一份 base model
- 多个已注册的 adapter
- 一个当前激活的 adapter 名称

而不是：

- 多个独立 policy 实例
- 或每次切换重新 `from_pretrained`

## 5. 切换是怎么触发的

切换触发不是通过 RPC 直接发“切 adapter”，而是通过 command file。

切换命令工具在 [switch_lora_task.py](/home/phl/workspace/arm-hand-teleop/scripts/tools/switch_lora_task.py)。

它做的事情很简单：

1. 读取多 LoRA 配置。
2. 校验 `profile_id` 是否存在。
3. 向 `command_file` 写入：

```json
{
  "profile_id": "yellow_to_black",
  "timestamp": 1710000000.0
}
```

推理循环会轮询这个文件；如果发现 profile 变化，就先记录成 pending switch，等切换边界到来时再真正执行。

## 6. 为什么要等“切换边界”

当前实现不会在任意时刻强切。

原因是 PI0.5 / RTC / action chunk 推理都有内部状态，如果动作还没消费完就切 adapter，容易把上一个任务的 residual state 带到下一个任务里。

所以代码里引入了 `TaskSwitchCoordinator.maybe_switch(is_switch_boundary=...)`：

- 如果命令到了，但还没到边界：
  - 只记为 pending
- 到了边界：
  - 才真正调用 `switch_callback`

切换完成后还会执行：

- `policy.reset()`
- `policy.init_rtc_processor()`

目的是把运行时残留状态清掉。

## 7. 同步推理链路

同步推理在 [infer.py](/home/phl/workspace/arm-hand-teleop/qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/infer.py) 的 `_run_sync_inference(...)` 里。

流程是：

1. 创建 `task_switch_coordinator`
2. 进入 `record_loop(...)`
3. 每次策略推理前检查当前 policy 的 `_action_queue`
4. 如果 action queue 为空，就把它当成切换边界
5. 在边界执行 profile 切换
6. 用切换后的 `current_task` 调 `predict_action(...)`

也就是说，同步模式的切换边界是：

- `policy._action_queue` 为空

这意味着：

- 不会打断当前 chunk
- 新任务会从下一个 chunk 开始生效

## 8. 异步推理链路

异步模式分成两部分：

- 客户端：[robot_client.py](/home/phl/workspace/arm-hand-teleop/qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/async_inference/robot_client.py)
- 服务端：[policy_server.py](/home/phl/workspace/arm-hand-teleop/qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/async_inference/policy_server.py)

### 8.1 客户端负责什么

客户端不直接切 adapter。

它负责：

1. 读取 command file
2. 判断当前 action queue 是否为空
3. 如果为空，认为到了切换边界
4. 把 `current_task` 改成新 profile 对应的 `task_description`
5. 下一帧 observation 里带着新的 `task` 发给服务端

异步模式的切换边界是：

- client 本地 `action_queue.empty()`

这样做的好处是：

- 客户端只在上一批动作已经基本消耗完后才切任务
- 不会让服务端刚发出一半 chunk，客户端就提前按另一个任务执行

### 8.2 服务端负责什么

服务端加载 policy 时也支持多 LoRA 配置文件路径。

服务端的主要工作是：

1. 启动时加载 base model + 默认 adapter + 其他预加载 adapter
2. 根据收到的 observation 里的 `task` 文本，决定当前该用哪个 profile
3. 如果任务文本对应的 profile 变了，就调用 `switch_to_task_description(...)`
4. 重置 RTC / policy runtime state
5. 再继续生成后续 action chunk

所以异步模式里，真正“切 adapter”的动作在服务端，真正“决定什么时候切”的节奏在客户端。

## 9. 实际怎么用

### 9.1 准备 LoRA

先保证两个 adapter 都已经训练完成，路径写进：

- [o10_right_pi05_lora_tasks.yaml](/home/phl/workspace/arm-hand-teleop/configs/right_arm/o10_right_pi05_lora_tasks.yaml)

训练脚本在另一个仓库：

- [/home/phl/workspace/lerobot-versions/fmc3-lerobot/scripts/train/train_pi05_o10_right_tissue_loras.sh](/home/phl/workspace/lerobot-versions/fmc3-lerobot/scripts/train/train_pi05_o10_right_tissue_loras.sh)

它会顺序训练：

- `black_to_yellow`
- `yellow_to_black`

### 9.2 启动多 LoRA 推理

用右臂启动脚本：

```bash
cd /home/phl/workspace/arm-hand-teleop
./scripts/o10/right_arm/infer_o10_right_pi05_multi_lora.sh
```

这个脚本会：

- 使用 `configs/right_arm/o10_right_pi05_lora_tasks.yaml` 作为 `--model_path`
- 默认任务设为 `black_to_yellow` 对应的自然语言文本
- 默认启动异步 policy server
- 默认打开 RTC 相关环境变量

### 9.3 运行中切任务

方式一，直接用包装脚本：

```bash
./scripts/o10/right_arm/switch_o10_right_lora_task.sh black_to_yellow
./scripts/o10/right_arm/switch_o10_right_lora_task.sh yellow_to_black
```

方式二，直接调统一入口：

```bash
python run_lerobot_play.py switch_lora_task \
  --config configs/right_arm/o10_right_pi05_lora_tasks.yaml \
  --profile yellow_to_black
```

执行后不会立刻硬切，而是：

1. 命令写入 command file
2. 等待当前动作消费到边界
3. 在边界切 LoRA
4. 后续动作按新任务生成

## 10. 当前限制和注意事项

### 10.1 `task_description` 必须精确匹配

当前异步服务端是用任务文本反查 profile。

这意味着：

- 配置里的 `task_description`
- 客户端发给服务端的 `task`

必须一致，才能命中对应 adapter。

### 10.2 更适合在线切任务，不适合边切边录多任务数据

同步推理时，模型推理使用的 `current_task` 会更新；
但当前 `record_loop(...)` 在写数据集时仍然写的是初始 `single_task`。

也就是说，如果你在同步推理里一边切任务一边 `save_data`：

- 控制行为会按新任务切
- 但数据集里的 `task` 字段目前不一定跟着切

如果后面要支持“边切边录成正确多任务数据集”，这里还需要再补一刀。

### 10.3 所有 adapter 会在启动时预加载

优点：

- 切换非常快

代价：

- 启动时间更长
- adapter 越多，占用显存越多

### 10.4 command file 只是切换请求，不是强制同步点

写入 command file 之后，不代表下一毫秒就切成功。

真正切换要等：

- 同步模式：policy action queue 为空
- 异步模式：client action queue 为空

### 10.5 配置文件路径必须都有效

启动时会校验：

- 多 LoRA YAML 是否存在
- 每个 `adapter_path` 是否存在
- base model 路径是否可解析

如果任何一个路径不对，推理会在启动阶段直接报错。

## 11. 关键文件索引

- 核心多 LoRA 封装：
  - [multi_lora.py](/home/phl/workspace/arm-hand-teleop/qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/utils/multi_lora.py)

- 同步 / 总入口集成：
  - [infer.py](/home/phl/workspace/arm-hand-teleop/qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/infer.py)

- 异步客户端：
  - [robot_client.py](/home/phl/workspace/arm-hand-teleop/qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/async_inference/robot_client.py)

- 异步服务端：
  - [policy_server.py](/home/phl/workspace/arm-hand-teleop/qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/async_inference/policy_server.py)

- 切换命令工具：
  - [switch_lora_task.py](/home/phl/workspace/arm-hand-teleop/scripts/tools/switch_lora_task.py)

- 右臂启动脚本：
  - [infer_o10_right_pi05_multi_lora.sh](/home/phl/workspace/arm-hand-teleop/scripts/o10/right_arm/infer_o10_right_pi05_multi_lora.sh)
  - [switch_o10_right_lora_task.sh](/home/phl/workspace/arm-hand-teleop/scripts/o10/right_arm/switch_o10_right_lora_task.sh)

- 任务 profile 配置：
  - [o10_right_pi05_lora_tasks.yaml](/home/phl/workspace/arm-hand-teleop/configs/right_arm/o10_right_pi05_lora_tasks.yaml)
