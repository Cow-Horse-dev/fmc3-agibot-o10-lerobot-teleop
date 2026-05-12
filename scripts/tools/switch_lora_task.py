from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LEROBOT_PLAY_PACKAGE_ROOT = (
    REPO_ROOT
    / "qiuzhi"
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)
if str(LEROBOT_PLAY_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_PACKAGE_ROOT))

from lerobot_play.utils.multi_lora import (  # noqa: E402
    TaskProfileRegistry,
    TaskSwitchCommandStore,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Switch the active multi-LoRA task profile.")
    parser.add_argument("--config", required=True, help="Path to the multi-LoRA task YAML/JSON.")
    parser.add_argument(
        "--profile",
        "--task",
        dest="profile_id",
        required=True,
        help="Task profile id to activate, for example black_to_yellow.",
    )
    return parser.parse_args()


def switch_lora_task(config_path: str | Path, profile_id: str) -> Path:
    registry = TaskProfileRegistry.from_path(config_path)
    profile = registry.profile_for_id(profile_id)
    store = TaskSwitchCommandStore(registry.command_file)
    store.write(profile.profile_id)
    return registry.command_file


def main() -> None:
    args = parse_args()
    command_file = switch_lora_task(args.config, args.profile_id)
    print(f"Requested LoRA task switch to {args.profile_id}")
    print(f"Command file: {command_file}")


if __name__ == "__main__":
    main()
