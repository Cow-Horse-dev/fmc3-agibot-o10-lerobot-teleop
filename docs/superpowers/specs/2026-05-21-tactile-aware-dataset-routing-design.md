# Tactile-aware dataset routing for `record`

Date: 2026-05-21
Status: Approved
Owner: phl

## Problem

`configs/{left_arm,right_arm,dual_arm}/o10_*_record.yaml` 全部把 LeRobot 数据集落在
`~/workspace/dataset/Robot/agi_arm_bot/`。同一个根目录里既会出现 `tactile_mode: none`
的非触觉数据集,也会出现 `tactile_mode: 130d` 的触觉数据集。两类数据 feature schema 不同
(observation/action 维度不一致),混在一起后续训练/推理选择数据集时容易拿错,人工
区分负担也大。用户已经按 `with_tactile/` 和 `without_tactile/` 手工分了子目录,需要在
录制阶段自动归位。

## Goals

- 在 `lerobot_play.record` 调用 `resolve_record_dataset_target` 之前,根据
  `robot.tactile_mode` 把 `dataset.root` 自动追加 `with_tactile/` 或
  `without_tactile/` 子目录。
- 三份 record yaml(左/右/双臂)无需改 `root`,共享同一个根,自动分流。
- 用户手工写的子目录(已经把 `root` 落在 `with_tactile`/`without_tactile`)受到尊重,
  不再二次追加。
- 改动只触碰 vendored `record.py` 一处,以及对应 yaml 的注释。

## Non-goals

- 不调整 `replay` / `infer` / `train` / `control` 的路径解析。这些是读路径,使用方需
  显式指定数据集所在子目录。
- 不迁移已经存在于 `agi_arm_bot/` 顶层的历史数据集(用户屏幕里看到的
  `dual_arm_*_20260521*`、`*.7z`、`_repair_backup_*` 等)。
- 不引入 yaml schema 字段或新的 CLI flag。
- 不针对触觉模式数值做更细分的子目录(例如未来加 `260d` 时仍归入 `with_tactile/`)。

## Design

### 1. 路由规则

入口:`qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/record.py`,
在 `resolve_record_dataset_target(...)` 之前插入约 10 行逻辑。

- 触觉判定:`tactile_mode = cfg.get("robot", {}).get("tactile_mode", "none")`。
  - `tactile_mode in (None, "", "none")` ⇒ `tactile_subdir = "without_tactile"`。
  - 其他任意非空值(当前 `"130d"`、未来其他维度) ⇒ `tactile_subdir = "with_tactile"`。
- 取 `raw_root = cfg["dataset"].get("root")`。若为空,跳过路由(沿用现有行为,后续仍会
  报缺失错误,不引入新行为)。
- 用 `Path(str(raw_root)).expanduser()` 解析路径(`Path` 已在 record.py 顶部导入,
  不新增 import)。
- 改写规则:
  - 若 `raw_root_path.name in ("with_tactile", "without_tactile")`:
    - **不改写**路径。
    - 如果 `raw_root_path.name != tactile_subdir`:用 `print_yellow` 打一条警告
      `dataset.root ends in '<name>' but tactile_mode='<x>' implies '<other>';
      keeping user-provided path.`,让用户自己看见冲突。
  - 否则:`cfg["dataset"]["root"] = str(raw_root_path / tactile_subdir)`,并用
    `print_yellow` 打一条
    `Auto-routed dataset.root to '<tactile_subdir>' based on tactile_mode='<x>'.`
    (颜色选 yellow,与现有 stale-warning 风格一致,不抢主路径行的 green。)
- 之后 `resolve_record_dataset_target(root=cfg["dataset"].get("root"), ...)`、
  `prepare_dataset_root_for_recording(cfg["dataset"]["repo_id"], cfg["dataset"].get("root"))`、
  `LeRobotDataset.create(root=dataset_root, ...)` 都从改写后的 `cfg` 读取,无需进一步
  改动。

### 2. 适用范围

- **生效**:`lerobot_play.record` 命令路径。三份 record yaml(`configs/left_arm/o10_left_record.yaml`、
  `configs/right_arm/o10_right_record.yaml`、`configs/dual_arm/o10_dual_record.yaml`)
  自动获得新行为。
- **不动**:`replay.py`、`infer.py`、`train.py`、`control.py`。
- **覆盖其他 robot type**:逻辑对所有 robot type 一视同仁。没有 `tactile_mode` 字段
  的 follower(`pico_follower_single_arm_eef` 等)默认走 `without_tactile`,语义正确。

### 3. yaml 注释更新

三份 record yaml(left/right/dual)各更新两处注释,行为字段值**不变**:

- `robot.tactile_mode` 注释末尾加一句 `也决定数据集 root 子目录 (none -> without_tactile, 其他 -> with_tactile)`。
- `dataset.root` 注释块里"最终实际路径"的示例改成
  `~/workspace/dataset/Robot/agi_arm_bot/<with_tactile|without_tactile>/<任务名_日期>`,
  并补一句"`with_tactile`/`without_tactile` 由 `robot.tactile_mode` 自动决定;若手工
  在 `root` 末段写死 `with_tactile`/`without_tactile`,会被尊重(不二次追加),与
  `tactile_mode` 不一致时会有 yellow 警告"。

### 4. 错误与边角

- `cfg["dataset"]["root"]` 为空 / None:不路由,沿用原 `resolve_record_dataset_target`
  报错路径。
- `tactile_mode` 字段缺失:默认 `"none"` → `without_tactile`。
- `tactile_mode` 字段值是大小写不同(如 `"None"` `"NONE"`):**严格按字符串比较**,
  当前 yaml 全部是小写 `"none"` 或 `"130d"`,不引入大小写归一化,保持纯文本对照。
- 用户手工子目录与 `tactile_mode` 矛盾:不改写,只 yellow 警告,让用户能在日志里看见。
- 多次调用 record.py 在同一 cfg 上(测试场景):因为改写后 root 末段会是
  `with_tactile`/`without_tactile`,第二次进来会进入"不二次追加"分支,幂等。

### 5. 数据流影响

`action`/`observation.state`/相机 feature schema 与 `tactile_mode` 已经强相关(由
`build_dataset_features(robot, ...)` 决定)。本设计保证:同一个父目录(`with_tactile/`
或 `without_tactile/`)下的所有 episode dataset feature schema 一致,后续 LeRobot
loader 在父目录扫子目录时不会再混进 schema 不同的 dataset。

## Testing / Verification

- 静态:在 repo 根目录 `/home/phl/workspace/arm-hand-teleop/` 下跑
  `python -c "import importlib, sys; sys.path.insert(0, 'qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any'); importlib.import_module('lerobot_play.record')"`,
  确保改动没有 SyntaxError / 导入挂掉。
- 手工 dry-run:
  - `tactile_mode: "none"` 跑 `record_o10_dual.sh`,Ctrl-C 在 `Dataset will be saved to:`
    打印之后停。检查路径包含 `without_tactile/`。
  - 临时把 `robot.tactile_mode` 改成 `"130d"`,同样 dry-run。检查路径包含 `with_tactile/`。
  - 临时把 `dataset.root` 改成 `~/workspace/dataset/Robot/agi_arm_bot/with_tactile`
    且 `tactile_mode: "none"`。检查日志里有 yellow 不一致警告,且最终路径不再叠子目录。
- 不引入自动化测试:vendored 代码当前没有 record 流程的 unit test,5 行级别改动不值得
  搭测试 harness。

## Rollout / Migration

- 单次改动落到 `qiuzhi/.../record.py` + 三份 record yaml 注释。
- 用户顶层的 4 个历史 `dual_arm_*_20260521*` 数据集**保持不动**;如果之后用户想清理,
  另开一次任务手工迁移。
- 不需要数据迁移 / migration 脚本。
- 不更新 `CLAUDE.md`(项目级行为仍由 vendored 代码 + yaml 注释承担,根说明文档不变)。

## Risks

- Vendored snapshot 被上游升级覆盖时,这处改动会丢。提交信息里应明确标注"本地修改:
  tactile-aware dataset routing",升级 vendor 时人工 re-apply。
- 用户继续手工把数据集塞到顶层目录(绕过 record CLI)不在本次范围内,本设计不防范。
