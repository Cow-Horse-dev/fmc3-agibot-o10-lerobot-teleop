# Repository Guidelines

## Project Structure & Module Organization

`yudie/` contains the active glove-to-hand runtime: `DexHand_Motion_Control_Program.py`, `Data_Receiver.py`, `sdk_bootstrap.py`, hand adapters in `AGIBOT/`, and the local `omnihand_2025/` SDK binaries. `qiuzhi/` holds the vendored `lerobot_play` snapshot plus regression tests in `qiuzhi/tests/`. `run_lerobot_play.py` is the root launcher that bootstraps the `qiuzhi` package tree. Treat `*.zip`, `*.whl`, shared libraries, `__pycache__/`, and generated `Protobuf/*_pb2.py` files as vendor artifacts unless regeneration is part of the task.

External LeRobot reference source lives at `/home/phl/workspace/lerobot-versions/lerobot`. When asked to reference, compare, or borrow LeRobot implementation details, inspect that directory first. Treat it as external reference code and do not modify it unless the task explicitly asks for changes there.

## Build, Test, and Development Commands

- `python yudie/DexHand_Motion_Control_Program.py --mode agibotHand_O10 --hand right` starts the main control loop.
- `python run_lerobot_play.py help` lists wrapped `lerobot_play` commands; use `record`, `replay`, `infer`, `control`, or `train`.
- `env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest qiuzhi/tests/test_agibot_o10.py` runs the current Python regression suite without ROS plugin leakage.
- `cd yudie/vendor_sdk/Omnihand-2025-SDK-dev_xuqigui && ./build.sh -DCMAKE_BUILD_TYPE=Release` rebuilds the vendored OmniHand SDK.
- `cd yudie/vendor_sdk/Omnihand-2025-SDK-dev_xuqigui && ./format.sh` formats C++, CMake, and SDK Python helpers.

## Coding Style & Naming Conventions

Use 4-space indentation in Python, `snake_case` for functions and modules, and add type hints on new logic where practical. Preserve existing public flag names even when they use camelCase, such as `--dataType` and `--canType`. Keep hand-specific adapters under `yudie/AGIBOT/` using the existing `*_yudie.py` pattern. For the vendor SDK, follow `.clang-format`; `format.sh` expects `clang-format-15`.
For shell scripts, prefer clear, descriptive variable names over cryptic abbreviations or single-letter names. Use names like `repo_root`, `config_path`, or `python_bin`, and avoid hard-to-read placeholders that make script intent unclear.

## Design Principles

Favor high cohesion and low coupling when adding or reshaping features. Prefer extracting shared logic into focused helpers, stores, adapters, or strategy-style components instead of copying device-specific branches across `record`, `control`, and teleoperator classes. When behavior may vary by hardware or runtime mode, choose an explicit design pattern that fits the problem, such as Strategy for interchangeable control policies, Adapter for SDK/vendor wrappers, Factory for config-driven construction, or Template Method for shared control flows with device-specific hooks. Keep orchestration code thin, push state ownership close to the module that owns it, and make cross-module contracts small and well-named.

## Testing Guidelines

Add Python tests under `qiuzhi/tests/` as `test_<feature>.py`. Prefer pure-Python regression tests that stub SDK imports and verify mapping math, bootstrap discovery, and error messages without requiring CAN hardware. No coverage gate is configured, so each behavior change should ship with a focused test or a short manual validation note.

## Commit & Pull Request Guidelines

History is sparse and uses short summary lines such as `第一次合并` and `宇叠手套控制手跑通版本`. Keep commits short, scoped, and single-purpose. Git commit messages must use the `heliangp:提交内容` format, for example `heliangp:fix JSON role fallback` or `heliangp:更新配置说明`. `qiuzhi/` and `yudie/` each contain their own Git metadata while the root repo tracks gitlinks, so be explicit about whether you changed nested repos, root pointers, or both. PRs should list the affected area, hardware assumptions, exact test commands, and logs or screenshots for runtime control changes.
