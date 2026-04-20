#!/usr/bin/env python3

from __future__ import annotations

import importlib
import sys
from pathlib import Path


LOCAL_LEROBOT_PLAY_ROOT = (
    Path(__file__).resolve().parent
    / "qiuzhi"
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

COMMAND_MODULES = {
    "record": "lerobot_play.record",
    "replay": "lerobot_play.replay",
    "infer": "lerobot_play.infer",
    "control": "lerobot_play.control",
    "train": "lerobot_play.train",
}

SCRIPT_COMMANDS = {
    "set_pose": "scripts.set_pose",
    "save_reset_pose": "scripts.save_reset_pose",
}


def _bootstrap_local_package() -> None:
    local_root = str(LOCAL_LEROBOT_PLAY_ROOT)
    if local_root not in sys.path:
        sys.path.insert(0, local_root)


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
        repo_root = str(Path(__file__).resolve().parent)
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
