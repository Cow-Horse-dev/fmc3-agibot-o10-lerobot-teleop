# O10 Right PI0.5 Multi-LoRA Switching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-process PI0.5 inference path that preloads multiple LoRA adapters and switches the active adapter plus task text at runtime.

**Architecture:** Add a reusable multi-LoRA core with `TaskProfile` config loading, atomic command-file switching, and a `SwitchablePeftPolicy` wrapper around one PEFT base model. Wire the same core into synchronous inference, asynchronous policy server/client, and RTC reset boundaries.

**Tech Stack:** Python, PEFT `PeftModel.load_adapter/set_adapter`, LeRobot `pi05`, existing `lerobot_play` sync/async inference, Bash training/launch scripts.

---

### Task 1: Multi-LoRA Core

**Files:**
- Create: `qiuzhi/.../lerobot_play/utils/multi_lora.py`
- Test: `qiuzhi/tests/test_multi_lora_switching.py`

- [ ] Write tests for loading a profile YAML, resolving the default profile, mapping task text to profile IDs, writing switch commands atomically, and switching a fake PEFT policy.
- [ ] Implement `TaskProfile`, `TaskProfileRegistry`, `TaskSwitchCommandStore`, `TaskSwitchCoordinator`, and `SwitchablePeftPolicy`.
- [ ] Verify with `env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_multi_lora_switching.py -q`.

### Task 2: Inference Integration

**Files:**
- Modify: `qiuzhi/.../lerobot_play/infer.py`
- Modify: `qiuzhi/.../lerobot_play/utils/lerobot_record.py`
- Modify: `qiuzhi/.../lerobot_play/async_inference/robot_client.py`
- Modify: `qiuzhi/.../lerobot_play/async_inference/policy_server.py`
- Test: `qiuzhi/tests/test_multi_lora_switching.py`

- [ ] Extend policy loading so `infer.model_path` may point at a multi-LoRA YAML.
- [ ] Use the first adapter path as the effective pretrained path for config, processors, and observation rename maps.
- [ ] In sync inference, poll the command file at PI0.5 action chunk boundaries and switch task text plus adapter together.
- [ ] In async inference, poll the command file on the client only when the action queue is empty, then let the server switch adapter from the task text on the next observation.
- [ ] Reset policy and RTC leftover state when the active adapter changes.

### Task 3: CLI, Config, Launchers, Training Script, Docs

**Files:**
- Modify: `run_lerobot_play.py`
- Create: `scripts/tools/switch_lora_task.py`
- Create: `configs/right_arm/o10_right_pi05_lora_tasks.yaml`
- Create: `scripts/o10/right_arm/infer_o10_right_pi05_multi_lora.sh`
- Create: `scripts/o10/right_arm/switch_o10_right_lora_task.sh`
- Create: `/home/phl/workspace/lerobot-versions/fmc3-lerobot/scripts/train/train_pi05_o10_right_tissue_loras.sh`
- Modify: `scripts/tools/README.md`
- Modify: `README.md`

- [ ] Add a small command that writes the desired profile ID into the configured command file.
- [ ] Add a right-arm multi-LoRA inference launcher and a switch launcher.
- [ ] Add a PI0.5 LoRA training script that trains the two no-tactile tissue datasets into separate adapter output directories.
- [ ] Document the training, launch, and switch commands.
- [ ] Run focused tests and shell dry-run checks before committing.
