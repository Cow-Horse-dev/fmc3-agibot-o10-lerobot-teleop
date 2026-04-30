#!/usr/bin/env python3

from __future__ import annotations

import importlib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
LOCAL_PLATFORM_ROOT = REPO_ROOT / "qiuzhi" / "lerobot_play_1.0.4" / "x86" / "noble"
LOCAL_LEROBOT_PLAY_ROOT = LOCAL_PLATFORM_ROOT / "lerobot_play-1.0.4-py3-none-any"

COMMAND_MODULES = {
    "record": "lerobot_play.record",
    "replay": "lerobot_play.replay",
    "infer": "lerobot_play.infer",
    "async_policy_server": "lerobot_play.async_inference.policy_server",
    "control": "lerobot_play.control",
    "train": "lerobot_play.train",
}

SCRIPT_COMMANDS = {
    "set_pose": "scripts.tools.set_pose",
    "save_reset_pose": "scripts.tools.save_reset_pose",
    "save_dual_reset_pose": "scripts.tools.save_dual_reset_pose",
}


def _find_local_dependency_root(pattern: str) -> Path | None:
    for candidate in sorted(LOCAL_PLATFORM_ROOT.glob(pattern)):
        if candidate.is_dir():
            return candidate
    return None


LOCAL_AIRBOT_HARDWARE_ROOT = _find_local_dependency_root("airbot_hardware_py-*")
LOCAL_MMK2_KDL_ROOT = _find_local_dependency_root("mmk2_kdl_py-*")


def _prepend_sys_path(path: Path | None) -> None:
    if path is None:
        return

    path_str = str(path)
    if path.exists() and path_str not in sys.path:
        sys.path.insert(0, path_str)


def _bootstrap_local_package() -> None:
    for dependency_root in (
        LOCAL_LEROBOT_PLAY_ROOT,
        LOCAL_AIRBOT_HARDWARE_ROOT,
        LOCAL_MMK2_KDL_ROOT,
    ):
        _prepend_sys_path(dependency_root)


def _print_usage() -> None:
    commands = ", ".join(sorted(COMMAND_MODULES))
    scripts = ", ".join(sorted(SCRIPT_COMMANDS))
    print(
        "Usage: python run_lerobot_play.py <command> [args...]\n"
        f"Commands: {commands}\n"
        f"Scripts: {scripts}"
    )


def main() -> int:
    _bootstrap_local_package()

    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help", "help"}:
        _print_usage()
        return 0

    command = sys.argv[1]
    module_name = COMMAND_MODULES.get(command)
    script_module = SCRIPT_COMMANDS.get(command)

    if module_name is None and script_module is None:
        print(f"Unknown command: {command}")
        _print_usage()
        return 2

    if script_module is not None:
        repo_root = str(REPO_ROOT)
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        module = importlib.import_module(script_module)
    else:
        module = importlib.import_module(module_name)
    entrypoint = getattr(module, "main", None)
    if entrypoint is None:
        raise AttributeError(f"{module_name} does not expose a main() entrypoint")

    sys.argv = [f"{Path(__file__).name} {command}", *sys.argv[2:]]
    entrypoint()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
