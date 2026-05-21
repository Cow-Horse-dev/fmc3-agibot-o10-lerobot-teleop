# Tactile-Aware Dataset Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-route `dataset.root` into `with_tactile/` or `without_tactile/` subfolder in `lerobot_play.record` based on `robot.tactile_mode`, so different tactile schemas never collide in the same parent directory.

**Architecture:** Single surgical edit in vendored `lerobot_play.record` (just before `resolve_record_dataset_target`); three matching yaml comment updates. No new files, no new schema fields, no automated test harness.

**Tech Stack:** Python 3 (vendored `lerobot_play`), YAML configs. Targets the existing record CLI invoked by `scripts/o10/*_arm/record_o10_*.sh`.

**Spec:** [docs/superpowers/specs/2026-05-21-tactile-aware-dataset-routing-design.md](../specs/2026-05-21-tactile-aware-dataset-routing-design.md)

**Current state notice:** `qiuzhi/.../record.py` ALREADY contains a partial pre-brainstorm version of the routing block (lines 919-933 of the file at plan-write time). Task 1 below **replaces** that block to match the spec (adds the yellow `Auto-routed` log line and the mismatch warning that the current partial code is missing). Do NOT just add another block — replace what is there.

**TDD note:** The spec explicitly opts out of automated tests for this 5-line vendored-code change. Verification is via static import + manual diff review + optional hardware dry-run. The plan therefore does NOT include test-first steps.

---

## File Structure

Files modified (no creations):

- `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/record.py` — replace existing routing block with spec-compliant version (adds two `print_yellow` log calls).
- `configs/dual_arm/o10_dual_record.yaml` — extend `robot.tactile_mode` and `dataset.root` comments.
- `configs/left_arm/o10_left_record.yaml` — same comment updates.
- `configs/right_arm/o10_right_record.yaml` — same comment updates.

---

### Task 1: Finalize routing block in vendored record.py

**Files:**
- Modify: `qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/record.py` (around lines 919-933 at plan-write time; line numbers may shift between sessions — locate by the routing comment block instead)

- [ ] **Step 1: Locate the current routing block**

Run:
```bash
grep -n "Route dataset.root into a tactile" /home/phl/workspace/arm-hand-teleop/qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/record.py
```
Expected: a single line number (around 919). If you get 0 matches or >1, stop and investigate before editing — the file state isn't what this plan assumed.

- [ ] **Step 2: Replace the routing block with the spec-compliant version**

Replace this exact block (currently in `record.py`):
```python
        # Route dataset.root into a tactile / non-tactile subfolder so that
        # recordings with different tactile_mode never end up in the same
        # parent directory. Skip if the user already pointed root at one of
        # those subfolders.
        tactile_mode = cfg.get("robot", {}).get("tactile_mode", "none")
        tactile_subdir = (
            "without_tactile"
            if tactile_mode in (None, "", "none")
            else "with_tactile"
        )
        raw_root = cfg["dataset"].get("root")
        if raw_root:
            raw_root_path = Path(str(raw_root)).expanduser()
            if raw_root_path.name not in ("with_tactile", "without_tactile"):
                cfg["dataset"]["root"] = str(raw_root_path / tactile_subdir)
```

with this new block:
```python
        # Route dataset.root into a tactile / non-tactile subfolder so that
        # recordings with different tactile_mode never end up in the same
        # parent directory. Skip if the user already pointed root at one of
        # those subfolders; warn if their subfolder disagrees with tactile_mode.
        tactile_mode = cfg.get("robot", {}).get("tactile_mode", "none")
        tactile_subdir = (
            "without_tactile"
            if tactile_mode in (None, "", "none")
            else "with_tactile"
        )
        raw_root = cfg["dataset"].get("root")
        if raw_root:
            raw_root_path = Path(str(raw_root)).expanduser()
            if raw_root_path.name in ("with_tactile", "without_tactile"):
                if raw_root_path.name != tactile_subdir:
                    print_yellow(
                        f"dataset.root ends in '{raw_root_path.name}' but "
                        f"tactile_mode='{tactile_mode}' implies '{tactile_subdir}'; "
                        f"keeping user-provided path."
                    )
            else:
                cfg["dataset"]["root"] = str(raw_root_path / tactile_subdir)
                print_yellow(
                    f"Auto-routed dataset.root to '{tactile_subdir}' "
                    f"based on tactile_mode='{tactile_mode}'."
                )
```

Use the Edit tool with `old_string` set to the first block and `new_string` set to the second. Both `print_yellow` and `Path` are already imported at the top of the file (lines ~3 and ~60); no new imports needed.

- [ ] **Step 3: Static import smoke check**

Run from the repo root `/home/phl/workspace/arm-hand-teleop/`:
```bash
python -c "import sys; sys.path.insert(0, 'qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any'); import lerobot_play.record; print('OK')"
```
Expected: `OK` on stdout, exit code 0. If the import fails with `SyntaxError` or `IndentationError`, the edit indentation is off (the block sits inside a `try:` block, so the leading whitespace is 8 spaces) — re-check before continuing.

If the import fails with `ModuleNotFoundError` on a downstream import (cameras, lerobot.*), that's unrelated to this change. Confirm with:
```bash
git stash && python -c "import sys; sys.path.insert(0, 'qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any'); import lerobot_play.record; print('OK')"
```
If the stashed version also fails the same way, restore your change with `git stash pop` and move on — the environment is missing a hardware-side dep that's unrelated to the routing block.

- [ ] **Step 4: Commit the code change**

```bash
git add qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/record.py
git commit -m "$(cat <<'EOF'
record: auto-route dataset.root by tactile_mode

Add a routing block before resolve_record_dataset_target that appends
with_tactile/ or without_tactile/ to dataset.root based on
robot.tactile_mode. User-provided subfolders are respected; a yellow
warning fires when the manually-written subfolder disagrees with
tactile_mode.

Spec: docs/superpowers/specs/2026-05-21-tactile-aware-dataset-routing-design.md
EOF
)"
```
Expected: `1 file changed, ~10 insertions(+), ~3 deletions(-)`.

---

### Task 2: Update yaml comments in three record configs

**Files:**
- Modify: `configs/dual_arm/o10_dual_record.yaml` (tactile_mode line ~103, dataset.root block ~168-169)
- Modify: `configs/left_arm/o10_left_record.yaml` (tactile_mode line ~80, dataset.root block ~193-196)
- Modify: `configs/right_arm/o10_right_record.yaml` (tactile_mode lines ~84-85, dataset.root block ~203-206)

YAML values do NOT change; only comments do.

- [ ] **Step 1: Update dual_arm yaml — `tactile_mode` comment**

In `configs/dual_arm/o10_dual_record.yaml`, replace:
```yaml
  tactile_mode: "none"  # 可选: none, 130d
```
with:
```yaml
  tactile_mode: "none"  # 可选: none, 130d；也决定数据集 root 子目录 (none -> without_tactile, 其他 -> with_tactile)
```

- [ ] **Step 2: Update dual_arm yaml — `dataset.root` comment**

In `configs/dual_arm/o10_dual_record.yaml`, replace:
```yaml
  # 数据集根目录。
  root: ~/workspace/dataset/Robot/agi_arm_bot  # 数据集根目录
```
with:
```yaml
  # 数据集根目录。
  # 最终路径会自动追加 with_tactile / without_tactile 子目录，由 robot.tactile_mode 决定：
  #   none -> ~/workspace/dataset/Robot/agi_arm_bot/without_tactile/<任务名_日期>
  #   其他 -> ~/workspace/dataset/Robot/agi_arm_bot/with_tactile/<任务名_日期>
  # 若手工把 root 末段写成 with_tactile / without_tactile，会被尊重不再追加；
  # 此时若与 tactile_mode 不一致会打 yellow 警告。
  root: ~/workspace/dataset/Robot/agi_arm_bot  # 数据集根目录
```

- [ ] **Step 3: Update left_arm yaml — `tactile_mode` comment**

In `configs/left_arm/o10_left_record.yaml`, replace:
```yaml
  tactile_mode: "none"
```
with:
```yaml
  tactile_mode: "none"  # 也决定数据集 root 子目录 (none -> without_tactile, 其他 -> with_tactile)
```

- [ ] **Step 4: Update left_arm yaml — `dataset.root` comment block**

In `configs/left_arm/o10_left_record.yaml`, replace:
```yaml
  # 数据集根目录。
  # 最终实际路径会是：
  #   ~/workspace/dataset/Robot/agi_arm_bot/<任务名_日期>
  root: ~/workspace/dataset/Robot/agi_arm_bot
```
with:
```yaml
  # 数据集根目录。
  # 最终路径会自动追加 with_tactile / without_tactile 子目录，由 robot.tactile_mode 决定：
  #   none -> ~/workspace/dataset/Robot/agi_arm_bot/without_tactile/<任务名_日期>
  #   其他 -> ~/workspace/dataset/Robot/agi_arm_bot/with_tactile/<任务名_日期>
  # 若手工把 root 末段写成 with_tactile / without_tactile，会被尊重不再追加；
  # 此时若与 tactile_mode 不一致会打 yellow 警告。
  root: ~/workspace/dataset/Robot/agi_arm_bot
```

- [ ] **Step 5: Update right_arm yaml — `tactile_mode` comment**

In `configs/right_arm/o10_right_record.yaml`, replace:
```yaml
  # 右臂录制默认保存 O10 raw 130D 触觉到 observation.tactile.right_raw。
  tactile_mode: "130d"
```
with:
```yaml
  # 右臂录制默认保存 O10 raw 130D 触觉到 observation.tactile.right_raw。
  # tactile_mode 也决定数据集 root 子目录 (none -> without_tactile, 其他 -> with_tactile)。
  tactile_mode: "130d"
```

- [ ] **Step 6: Update right_arm yaml — `dataset.root` comment block**

In `configs/right_arm/o10_right_record.yaml`, replace:
```yaml
  # 数据集根目录。
  # 最终实际路径会是：
  #   ~/workspace/dataset/Robot/agi_arm_bot/<任务名_日期>
  root: ~/workspace/dataset/Robot/agi_arm_bot
```
with:
```yaml
  # 数据集根目录。
  # 最终路径会自动追加 with_tactile / without_tactile 子目录，由 robot.tactile_mode 决定：
  #   none -> ~/workspace/dataset/Robot/agi_arm_bot/without_tactile/<任务名_日期>
  #   其他 -> ~/workspace/dataset/Robot/agi_arm_bot/with_tactile/<任务名_日期>
  # 若手工把 root 末段写成 with_tactile / without_tactile，会被尊重不再追加；
  # 此时若与 tactile_mode 不一致会打 yellow 警告。
  root: ~/workspace/dataset/Robot/agi_arm_bot
```

Note: Before applying steps 4/6, confirm the original 4-line `root` block actually appears in left/right yaml (the dual yaml uses a single-line `root` comment). Use `grep -nB1 -A2 "root: ~/workspace/dataset/Robot/agi_arm_bot" configs/left_arm/o10_left_record.yaml configs/right_arm/o10_right_record.yaml` to verify before editing — if the surrounding lines differ, adjust `old_string` to match the file exactly.

- [ ] **Step 7: Sanity-check yaml syntax**

Run from repo root:
```bash
python -c "
import yaml
for p in [
    'configs/dual_arm/o10_dual_record.yaml',
    'configs/left_arm/o10_left_record.yaml',
    'configs/right_arm/o10_right_record.yaml',
]:
    with open(p) as f:
        yaml.safe_load(f)
    print(p, 'OK')
"
```
Expected: three `OK` lines. If yaml.safe_load raises, you likely introduced a stray tab or mis-indented comment.

- [ ] **Step 8: Commit the yaml updates**

```bash
git add configs/dual_arm/o10_dual_record.yaml configs/left_arm/o10_left_record.yaml configs/right_arm/o10_right_record.yaml
git commit -m "configs: document tactile-aware dataset routing in record yamls"
```
Expected: `3 files changed, ~21 insertions(+), ~6 deletions(-)`.

---

### Task 3: Verification

**Files:** none (read-only checks).

- [ ] **Step 1: Diff review against the spec**

Run:
```bash
git log --oneline -3
git show HEAD~1 -- qiuzhi/lerobot_play_1.0.4/x86/noble/lerobot_play-1.0.4-py3-none-any/lerobot_play/record.py
```
Read the diff against [the design doc's section 1 (路由规则)](../specs/2026-05-21-tactile-aware-dataset-routing-design.md). Confirm:
- Both `print_yellow` log lines exist (mismatch warning AND auto-route notice).
- `tactile_mode in (None, "", "none")` ⇒ `without_tactile`, else `with_tactile`.
- `raw_root_path.name in ("with_tactile", "without_tactile")` short-circuits the rewrite.
- Block inserted BEFORE `resolve_record_dataset_target(...)`, not after.

If any item fails, return to Task 1 Step 2 and re-apply.

- [ ] **Step 2: Optional hardware dry-run (skip if hardware unavailable)**

Requires CAN0+CAN1, OmniHand glove daemon, and Pico VR reachable. If unavailable, mark this step as N/A and move to Step 3.

Test cases (Ctrl-C each one immediately after the green `Dataset will be saved to:` line prints, BEFORE any data is recorded):

a. **Baseline (none → without_tactile):**
```bash
./scripts/o10/dual_arm/record_o10_dual.sh
```
Expected log lines:
```
Auto-routed dataset.root to 'without_tactile' based on tactile_mode='none'.
Dataset will be saved to: /home/phl/workspace/dataset/Robot/agi_arm_bot/without_tactile/dual_arm_collaborative_express_parcel_sorting_<YYYYMMDD>
```

b. **Tactile case (130d → with_tactile):** temporarily edit `configs/dual_arm/o10_dual_record.yaml` line ~103 to `tactile_mode: "130d"`, run the same script, expect:
```
Auto-routed dataset.root to 'with_tactile' based on tactile_mode='130d'.
Dataset will be saved to: .../with_tactile/...
```
Revert the yaml after the check (do NOT commit the temp edit).

c. **Mismatch warning:** temporarily edit `dataset.root` to `~/workspace/dataset/Robot/agi_arm_bot/with_tactile` while keeping `tactile_mode: "none"`. Expect:
```
dataset.root ends in 'with_tactile' but tactile_mode='none' implies 'without_tactile'; keeping user-provided path.
Dataset will be saved to: .../with_tactile/dual_arm_collaborative_express_parcel_sorting_<YYYYMMDD>
```
Note the final path stays under `with_tactile/` (no double-append). Revert the yaml after the check.

If any case prints a different path or omits a log line, return to Task 1 Step 2 and fix.

- [ ] **Step 3: Final sign-off**

Confirm `git status` is clean (no leftover temp edits from Step 2 cases b/c):
```bash
git status
```
Expected: `nothing to commit, working tree clean`.

No final commit — verification is read-only.
