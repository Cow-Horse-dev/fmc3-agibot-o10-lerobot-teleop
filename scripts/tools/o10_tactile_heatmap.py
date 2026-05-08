#!/usr/bin/env python3
"""Visualize OmniHand O10 130D tactile data as a heatmap."""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
LEROBOT_PLAY_ROOT = (
    REPO_ROOT
    / "qiuzhi"
    / "lerobot_play_1.0.4"
    / "x86"
    / "noble"
    / "lerobot_play-1.0.4-py3-none-any"
)

FINGER_NAMES = ("thumb", "index", "middle", "ring", "little")
REGION_NAMES = (*FINGER_NAMES, "palm", "dorsum")
HAND_NAMES = ("left", "right")
TACTILE_FULL_COUNT = 130
HAND_HEATMAP_ROWS = 17
HAND_HEATMAP_COLS = 20


Matrix = list[list[float]]
RegionMap = dict[str, Matrix]


def _reshape(values: list[float], rows: int, cols: int) -> Matrix:
    return [
        values[row * cols : (row + 1) * cols]
        for row in range(rows)
    ]


def split_o10_tactile_full(values: Iterable[float]) -> RegionMap:
    """Split 130D O10 tactile values into 5 finger grids, palm and dorsum."""
    data = [float(value) for value in values]
    if len(data) != TACTILE_FULL_COUNT:
        raise ValueError(
            f"Expected {TACTILE_FULL_COUNT} tactile values for O10 130D mode, "
            f"got {len(data)}"
        )

    regions: RegionMap = {}
    offset = 0
    for finger_name in FINGER_NAMES:
        regions[finger_name] = _reshape(data[offset : offset + 16], 4, 4)
        offset += 16
    regions["palm"] = _reshape(data[offset : offset + 25], 5, 5)
    offset += 25
    regions["dorsum"] = _reshape(data[offset : offset + 25], 5, 5)
    return regions


def _empty_matrix(rows: int, cols: int, fill: float = 0.0) -> Matrix:
    return [[fill for _col in range(cols)] for _row in range(rows)]


def _paste_region(canvas: Matrix, region: Matrix, top: int, left: int) -> None:
    for row_index, row in enumerate(region):
        for col_index, value in enumerate(row):
            canvas[top + row_index][left + col_index] = value


def compose_o10_hand_heatmap(values: Iterable[float]) -> Matrix:
    """Compose one hand into a 17x20 heatmap canvas.

    Layout:
    - rows 0..3: thumb/index/middle/ring/little, each as one 4x4 block
    - rows 6..10: palm 5x5, centered
    - rows 12..16: dorsum 5x5, centered
    """
    regions = split_o10_tactile_full(values)
    canvas = _empty_matrix(HAND_HEATMAP_ROWS, HAND_HEATMAP_COLS)

    for finger_index, finger_name in enumerate(FINGER_NAMES):
        _paste_region(canvas, regions[finger_name], top=0, left=finger_index * 4)

    centered_col = (HAND_HEATMAP_COLS - 5) // 2
    _paste_region(canvas, regions["palm"], top=6, left=centered_col)
    _paste_region(canvas, regions["dorsum"], top=12, left=centered_col)
    return canvas


def compose_hands_heatmap(samples: dict[str, Iterable[float]]) -> Matrix:
    """Compose one or two hands into a single heatmap image."""
    ordered_hands = [hand for hand in HAND_NAMES if hand in samples]
    if not ordered_hands:
        raise ValueError("Expected at least one hand sample")

    hand_matrices = [compose_o10_hand_heatmap(samples[hand]) for hand in ordered_hands]
    if len(hand_matrices) == 1:
        return hand_matrices[0]

    spacer = _empty_matrix(HAND_HEATMAP_ROWS, 2)
    return [
        hand_matrices[0][row_index] + spacer[row_index] + hand_matrices[1][row_index]
        for row_index in range(HAND_HEATMAP_ROWS)
    ]


def sample_stats(samples: dict[str, Iterable[float]]) -> str:
    parts = []
    for hand in HAND_NAMES:
        if hand not in samples:
            continue
        values = [float(value) for value in samples[hand]]
        peak = max(values) if values else 0.0
        mean = sum(values) / len(values) if values else 0.0
        parts.append(f"{hand}: max={peak:.1f} mean={mean:.1f}")
    return " | ".join(parts)


def _demo_values(step: int = 0, *, hand_phase: float = 0.0) -> list[float]:
    values = [0.0 for _ in range(TACTILE_FULL_COUNT)]
    center = (step * 7 + int(hand_phase * 19)) % TACTILE_FULL_COUNT
    for index in range(TACTILE_FULL_COUNT):
        distance = min(abs(index - center), TACTILE_FULL_COUNT - abs(index - center))
        values[index] = max(0.0, 180.0 - distance * 18.0)
    return values


def _terminal_shade(value: float, *, vmin: float, vmax: float) -> str:
    shades = " .:-=+*#%@"
    if vmax <= vmin:
        return shades[-1] if value > vmin else shades[0]
    ratio = (value - vmin) / (vmax - vmin)
    ratio = max(0.0, min(1.0, ratio))
    return shades[int(round(ratio * (len(shades) - 1)))]


def render_terminal_heatmap(
    samples: dict[str, Iterable[float]],
    *,
    vmin: float,
    vmax: float,
) -> str:
    matrix = compose_hands_heatmap(samples)
    lines = [sample_stats(samples)]
    for row in matrix:
        lines.append("".join(_terminal_shade(value, vmin=vmin, vmax=vmax) for value in row))
    return "\n".join(lines)


def _import_agibot_o10_hand():
    if str(LEROBOT_PLAY_ROOT) not in sys.path:
        sys.path.insert(0, str(LEROBOT_PLAY_ROOT))
    from lerobot_play.utils.agibot_o10 import AgibotO10Hand

    return AgibotO10Hand


def _selected_hands(hand_arg: str) -> tuple[str, ...]:
    if hand_arg == "both":
        return HAND_NAMES
    return (hand_arg,)


def _connect_hands(args: argparse.Namespace):
    AgibotO10Hand = _import_agibot_o10_hand()
    hands = {}
    for hand_name in _selected_hands(args.hand):
        hand = AgibotO10Hand(
            handedness=hand_name,
            channel_mode="multiChannel",
            device_id=args.device_id,
            canfd_id=args.canfd_id,
            channel_id=args.channel_id,
        )
        print(f"Connecting {hand_name} O10 hand...")
        hand.connect()
        hands[hand_name] = hand
    return hands


def _read_samples(
    hands,
    *,
    demo: bool,
    step: int,
) -> dict[str, list[float]]:
    if demo:
        if isinstance(hands, tuple):
            hand_names = hands
        else:
            hand_names = tuple(hands)
        return {
            hand_name: _demo_values(step, hand_phase=float(index))
            for index, hand_name in enumerate(hand_names)
        }

    return {
        hand_name: hand.read_tactile_full()
        for hand_name, hand in hands.items()
    }


def _load_pyplot(output: Path | None, once: bool):
    try:
        import matplotlib

        if output is not None and once:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required for graphical heatmaps. "
            "Install it or run with --backend terminal."
        ) from exc

    return plt


def _matplotlib_ticks(hand_count: int) -> tuple[list[float], list[str], list[float], list[str]]:
    xticks = []
    xlabels = []
    for hand_index in range(hand_count):
        base = hand_index * (HAND_HEATMAP_COLS + 2)
        prefix = "" if hand_count == 1 else f"{HAND_NAMES[hand_index]} "
        for finger_index, finger_name in enumerate(FINGER_NAMES):
            xticks.append(base + finger_index * 4 + 1.5)
            xlabels.append(prefix + finger_name)

    yticks = [1.5, 8.0, 14.0]
    ylabels = ["fingers", "palm", "dorsum"]
    return xticks, xlabels, yticks, ylabels


def run_matplotlib(
    samples_source,
    args: argparse.Namespace,
) -> int:
    output = Path(args.output).expanduser() if args.output else None
    plt = _load_pyplot(output, args.once)

    first_samples = samples_source(0)
    first_matrix = compose_hands_heatmap(first_samples)
    hand_count = len(first_samples)

    fig_width = 8 if hand_count == 1 else 14
    fig, ax = plt.subplots(figsize=(fig_width, 6))
    image = ax.imshow(
        first_matrix,
        cmap=args.cmap,
        vmin=args.vmin,
        vmax=args.vmax,
        interpolation="nearest",
        aspect="equal",
    )
    colorbar = fig.colorbar(image, ax=ax, fraction=0.035, pad=0.04)
    colorbar.set_label("pressure (0-255)")

    xticks, xlabels, yticks, ylabels = _matplotlib_ticks(hand_count)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xlabels, rotation=35, ha="right")
    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels)
    ax.set_xlabel("O10 tactile regions")
    ax.set_title(f"O10 tactile heatmap | {sample_stats(first_samples)}")
    fig.tight_layout()

    if output is not None and args.once:
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, dpi=args.dpi)
        print(f"Saved heatmap: {output}")
        return 0

    plt.ion()
    plt.show(block=False)
    step = 0
    while plt.fignum_exists(fig.number):
        samples = first_samples if step == 0 else samples_source(step)
        image.set_data(compose_hands_heatmap(samples))
        ax.set_title(f"O10 tactile heatmap | {sample_stats(samples)}")
        if output is not None and step == 0:
            output.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(output, dpi=args.dpi)
            print(f"Saved first heatmap: {output}")
        fig.canvas.draw_idle()
        plt.pause(args.interval)
        if args.once:
            break
        step += 1
    return 0


def run_terminal(samples_source, args: argparse.Namespace) -> int:
    step = 0
    while True:
        samples = samples_source(step)
        output = render_terminal_heatmap(samples, vmin=args.vmin, vmax=args.vmax)
        if args.once:
            print(output)
            return 0

        terminal_width = shutil.get_terminal_size((120, 20)).columns
        print("\033[H\033[J", end="")
        print(output[: terminal_width * 30])
        time.sleep(args.interval)
        step += 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="O10 130D tactile heatmap viewer")
    parser.add_argument(
        "--hand",
        choices=("left", "right", "both"),
        default="left",
        help="which hand to read; default: left",
    )
    parser.add_argument(
        "--device-id",
        type=int,
        default=1,
        help="OmniHand device_id; default: 1",
    )
    parser.add_argument(
        "--canfd-id",
        type=int,
        default=0,
        help="OmniHand canfd_id; default: 0",
    )
    parser.add_argument(
        "--channel-id",
        type=int,
        default=None,
        help="CANFD channel_id override; by default left=0 and right=1",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.1,
        help="refresh interval in seconds; default: 0.1",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "matplotlib", "terminal"),
        default="auto",
        help="display backend; auto tries matplotlib first, then terminal",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="read one sample and exit",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="save the first/only graphical heatmap image to this path",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="use generated tactile values instead of connecting hardware",
    )
    parser.add_argument(
        "--vmin",
        type=float,
        default=0.0,
        help="heatmap minimum; default: 0",
    )
    parser.add_argument(
        "--vmax",
        type=float,
        default=255.0,
        help="heatmap maximum; default: 255",
    )
    parser.add_argument(
        "--cmap",
        type=str,
        default="inferno",
        help="matplotlib colormap; default: inferno",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=160,
        help="saved image DPI; default: 160",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    hand_names = _selected_hands(args.hand)
    hands = hand_names if args.demo else _connect_hands(args)

    def samples_source(step: int) -> dict[str, list[float]]:
        return _read_samples(hands, demo=args.demo, step=step)

    try:
        if args.backend == "terminal":
            return run_terminal(samples_source, args)

        try:
            return run_matplotlib(samples_source, args)
        except RuntimeError as exc:
            if args.backend != "auto":
                raise
            print(f"{exc} Falling back to terminal heatmap.", file=sys.stderr)
            return run_terminal(samples_source, args)
    except KeyboardInterrupt:
        print("\nStopping tactile heatmap...")
        return 0
    finally:
        if not args.demo:
            for hand in hands.values():
                hand.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
