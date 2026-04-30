#!/usr/bin/env python3
"""宇叠手套单独控制智元 O10 手。

这个脚本只控制手，不启动机械臂、不录制数据。启动 HDService/HDWeb 后，
让手套数据转发到本机 5555 端口，再运行本脚本。

示例：
    python tests/test_ude_glove_hand_control.py --mode single --hand right
    python tests/test_ude_glove_hand_control.py --mode single --hand left
    python tests/test_ude_glove_hand_control.py --mode dual
    python tests/test_ude_glove_hand_control.py --mode dual --no-hw
"""

from __future__ import annotations

import argparse
import math
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
LEROBOT_PLAY_ROOT = (
    REPO_ROOT
    / "qiuzhi"
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

if str(LEROBOT_PLAY_ROOT) not in sys.path:
    sys.path.insert(0, str(LEROBOT_PLAY_ROOT))

from lerobot_play.teleoperators.pico_leader_single_arm_eef.udexreal_driver import (
    ServerStatus,
    UDEGloveSDK,
)
from lerobot_play.utils.agibot_o10 import (
    AGIBOT_O10_HAND_FEATURE_NAMES,
    O10HandMapper,
    extract_ude_glove_angles,
)


@dataclass(frozen=True)
class HandRuntimeConfig:
    handedness: str
    device_id: int
    canfd_id: int
    channel_id: int | None


@dataclass
class HandRuntime:
    config: HandRuntimeConfig
    hand: object | None
    last_write_error: str | None = None
    write_count: int = 0


class GloveDataReceiver:
    def __init__(self, args: argparse.Namespace):
        configs = build_hand_runtime_configs(args)
        self.handednesses = tuple(config.handedness for config in configs)
        self.control_freq = max(1, int(round(args.freq)))
        self.max_data_age_s = float(args.max_data_age)
        self.ude_glove = UDEGloveSDK()
        self.mappers = {
            handedness: O10HandMapper(handedness=handedness)
            for handedness in self.handednesses
        }
        self.data_lock = threading.Lock()
        self.hand_data = {
            handedness: [0.0] * len(AGIBOT_O10_HAND_FEATURE_NAMES)
            for handedness in self.handednesses
        }
        self.last_update_time = {handedness: 0.0 for handedness in self.handednesses}
        self.is_running = False
        self.listening_thread: threading.Thread | None = None
        self._last_role_warning_t = 0.0

    def start(self) -> bool:
        self.ude_glove.initialize()
        if getattr(self.ude_glove, "cur_status", ServerStatus.READY) != ServerStatus.READY:
            return False

        self.ude_glove.start_listening()
        self.is_running = True
        self.listening_thread = threading.Thread(
            target=self._data_listening_loop,
            name="ude-glove-hand-control",
            daemon=True,
        )
        self.listening_thread.start()
        return True

    def stop(self) -> None:
        self.is_running = False
        if self.listening_thread is not None:
            self.listening_thread.join(timeout=1.0)
            self.listening_thread = None
        self.ude_glove.end_listening()

    def wait_until_ready(self, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if all(self.has_hand_data(handedness) for handedness in self.handednesses):
                return True
            time.sleep(0.02)
        return all(self.has_hand_data(handedness) for handedness in self.handednesses)

    def get_hand_data(self, handedness: str) -> list[float]:
        with self.data_lock:
            return self.hand_data[handedness].copy()

    def has_hand_data(self, handedness: str, max_age_s: float | None = None) -> bool:
        with self.data_lock:
            last_update_time = self.last_update_time[handedness]
        if last_update_time <= 0.0:
            return False
        if max_age_s is None:
            return True
        return (time.monotonic() - last_update_time) <= max_age_s

    def _update_hand_data(self, handedness: str, new_data: Sequence[float]) -> None:
        if len(new_data) != len(AGIBOT_O10_HAND_FEATURE_NAMES):
            raise ValueError(
                f"{handedness} hand data must have "
                f"{len(AGIBOT_O10_HAND_FEATURE_NAMES)} values, got {len(new_data)}"
            )
        with self.data_lock:
            self.hand_data[handedness] = [float(value) for value in new_data]
            self.last_update_time[handedness] = time.monotonic()

    @staticmethod
    def _infer_role_handedness(role_name: str) -> str | None:
        normalized_role = role_name.strip().upper()
        if not normalized_role:
            return None
        if normalized_role.endswith("LEFT") or normalized_role.endswith("_LEFT"):
            return "left"
        if normalized_role.endswith("RIGHT") or normalized_role.endswith("_RIGHT"):
            return "right"
        if normalized_role.endswith("L"):
            return "left"
        if normalized_role.endswith("R"):
            return "right"
        return None

    def _select_role_name(self, role_list: Sequence[str], handedness: str) -> str | None:
        if not role_list:
            return None

        unclassified_roles: list[str] = []
        for role_name in role_list:
            inferred_handedness = self._infer_role_handedness(role_name)
            if inferred_handedness == handedness:
                return role_name
            if inferred_handedness is None:
                unclassified_roles.append(role_name)

        if len(role_list) == 1 and unclassified_roles:
            return unclassified_roles[0]
        return None

    def _data_listening_loop(self) -> None:
        sleep_s = 1.0 / self.control_freq
        while self.is_running:
            try:
                role_list = self.ude_glove.get_role_name_list()
                for handedness in self.handednesses:
                    role_name = self._select_role_name(role_list, handedness)
                    if role_name is None:
                        continue
                    finger_data = self.ude_glove.get_vec_finger_data(role_name)
                    glove_angles = extract_ude_glove_angles(finger_data, handedness)
                    self._update_hand_data(
                        handedness,
                        self.mappers[handedness].map(glove_angles),
                    )
                if (
                    role_list
                    and any(not self.has_hand_data(side) for side in self.handednesses)
                    and time.monotonic() - self._last_role_warning_t > 2.0
                ):
                    self._last_role_warning_t = time.monotonic()
                    print(
                        "Warning: no glove role matched all requested hands. "
                        f"requested={list(self.handednesses)}, available={role_list}"
                    )
            except Exception as exc:
                print(f"宇叠手套 O10 数据读取错误: {exc}")
            time.sleep(sleep_s)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="宇叠手套单独控制智元 O10 手")
    parser.add_argument(
        "--mode",
        choices=("single", "dual"),
        default="single",
        help="single 控一只手，dual 同时控左右手",
    )
    parser.add_argument(
        "--hand",
        choices=("left", "right"),
        default="right",
        help="single 模式下选择控制哪只手",
    )
    parser.add_argument("--device-id", type=int, default=1, help="OmniHand device_id")
    parser.add_argument("--canfd-id", type=int, default=0, help="OmniHand canfd_id")
    parser.add_argument(
        "--channel-id",
        type=int,
        default=None,
        help="single 模式下 O10 channel_id；不传则用手型默认通道",
    )
    parser.add_argument(
        "--left-channel-id",
        type=int,
        default=0,
        help="dual 模式下左手 channel_id，默认 0",
    )
    parser.add_argument(
        "--right-channel-id",
        type=int,
        default=1,
        help="dual 模式下右手 channel_id，默认 1",
    )
    parser.add_argument(
        "--freq",
        type=float,
        default=25.0,
        help="写手频率 Hz，默认 25",
    )
    parser.add_argument(
        "--ready-timeout",
        type=float,
        default=3.0,
        help="启动后等待首帧手套数据的时间，单位秒",
    )
    parser.add_argument(
        "--max-data-age",
        type=float,
        default=0.5,
        help="手套数据超过这个秒数就暂停写入，默认 0.5",
    )
    parser.add_argument(
        "--status-interval",
        type=float,
        default=0.5,
        help="状态打印周期，单位秒，默认 0.5",
    )
    parser.add_argument(
        "--no-hw",
        action="store_true",
        help="只接收手套并打印映射角度，不连接/写入真实 O10 手",
    )
    return parser.parse_args(argv)


def build_hand_runtime_configs(args: argparse.Namespace) -> list[HandRuntimeConfig]:
    if args.mode == "single":
        return [
            HandRuntimeConfig(
                handedness=args.hand,
                device_id=args.device_id,
                canfd_id=args.canfd_id,
                channel_id=args.channel_id,
            )
        ]

    return [
        HandRuntimeConfig(
            handedness="left",
            device_id=args.device_id,
            canfd_id=args.canfd_id,
            channel_id=args.left_channel_id,
        ),
        HandRuntimeConfig(
            handedness="right",
            device_id=args.device_id,
            canfd_id=args.canfd_id,
            channel_id=args.right_channel_id,
        ),
    ]


def _import_hand_class():
    from lerobot_play.utils.agibot_o10 import AgibotO10Hand

    return AgibotO10Hand


def _format_hand_data(values: Sequence[float]) -> str:
    deg_values = [math.degrees(float(value)) for value in values[:10]]
    return " ".join(f"{value:6.1f}" for value in deg_values)


def _connect_runtime(
    config: HandRuntimeConfig,
    *,
    no_hw: bool,
) -> HandRuntime:
    hand = None
    if not no_hw:
        AgibotO10Hand = _import_hand_class()
        hand = AgibotO10Hand(
            handedness=config.handedness,
            channel_mode="multiChannel",
            device_id=config.device_id,
            canfd_id=config.canfd_id,
            channel_id=config.channel_id,
        )
        print(
            f"[{config.handedness}] Connecting O10 hand "
            f"(device_id={config.device_id}, canfd_id={config.canfd_id}, "
            f"channel_id={config.channel_id})..."
        )
        hand.connect()

    return HandRuntime(config=config, hand=hand)


def _disconnect_runtime(runtime: HandRuntime) -> None:
    if runtime.hand is not None:
        runtime.hand.disconnect()


def _write_runtime_once(
    runtime: HandRuntime,
    *,
    receiver: GloveDataReceiver,
    max_data_age_s: float,
) -> None:
    if not receiver.has_hand_data(runtime.config.handedness, max_age_s=max_data_age_s):
        return

    hand_data = receiver.get_hand_data(runtime.config.handedness)
    if runtime.hand is not None:
        runtime.hand.write_active_joint_angles(hand_data)
    runtime.write_count += 1
    runtime.last_write_error = None


def _status_line(
    runtime: HandRuntime,
    *,
    receiver: GloveDataReceiver,
    max_data_age_s: float,
) -> str:
    handedness = runtime.config.handedness
    has_fresh_data = receiver.has_hand_data(handedness, max_age_s=max_data_age_s)
    hand_data = receiver.get_hand_data(handedness)
    mode = "hw" if runtime.hand is not None else "no-hw"
    status = "fresh" if has_fresh_data else "stale"
    error = f" err={runtime.last_write_error}" if runtime.last_write_error else ""
    return (
        f"{runtime.config.handedness}:{status}:{mode}:writes={runtime.write_count} "
        f"deg=[{_format_hand_data(hand_data)}]{error}"
    )


def run_control_loop(args: argparse.Namespace) -> int:
    configs = build_hand_runtime_configs(args)
    control_freq = max(1, int(round(args.freq)))
    sleep_s = 1.0 / control_freq
    runtimes: list[HandRuntime] = []
    receiver = GloveDataReceiver(args)

    try:
        print("[glove] Connecting shared UDE glove receiver on UDP 5555...")
        if not receiver.start():
            raise RuntimeError(
                "宇叠手套未连接。请确认 HDService/HDWeb 已启动，"
                "并把手套数据转发到本机 UDP 5555。"
            )

        for config in configs:
            runtimes.append(
                _connect_runtime(
                    config,
                    no_hw=args.no_hw,
                )
            )

        if receiver.wait_until_ready(timeout_s=args.ready_timeout):
            print("[glove] First requested glove frame received.")
        else:
            print("[glove] Waiting for glove data; no fresh frame yet.")

        print("Running glove -> O10 hand control. Press Ctrl+C to stop.")
        last_status_t = 0.0
        while True:
            for runtime in runtimes:
                try:
                    _write_runtime_once(
                        runtime,
                        receiver=receiver,
                        max_data_age_s=args.max_data_age,
                    )
                except Exception as exc:
                    runtime.last_write_error = str(exc)

            now = time.monotonic()
            if now - last_status_t >= args.status_interval:
                last_status_t = now
                print(
                    " | ".join(
                        _status_line(
                            runtime,
                            receiver=receiver,
                            max_data_age_s=args.max_data_age,
                        )
                        for runtime in runtimes
                    ),
                    flush=True,
                )
            time.sleep(sleep_s)
    except KeyboardInterrupt:
        print("\nStopping glove hand control...")
    finally:
        for runtime in reversed(runtimes):
            _disconnect_runtime(runtime)
        receiver.stop()

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return run_control_loop(args)


if __name__ == "__main__":
    raise SystemExit(main())
