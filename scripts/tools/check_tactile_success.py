#!/usr/bin/env python3
"""触觉成功判定函数。

用于推理阶段判断"笔触摄像头"任务是否成功：
右手拇指、食指、中指的触觉均值全部超过阈值即视为成功。

用法（独立运行示例）：
    python scripts/tools/check_tactile_success.py --thumb 50 --index 40 --middle 45 --threshold 30
"""

from __future__ import annotations


def check_tactile_success(
    right_thumb_avg: float,
    right_index_avg: float,
    right_middle_avg: float,
    threshold: float = 30.0,
) -> bool:
    """判断右手触觉是否表明笔成功触碰了摄像头。

    当拇指、食指、中指三个指尖的触觉均值都超过 *threshold* 时返回 True。

    Args:
        right_thumb_avg: 右手拇指触觉均值（0-255）。
        right_index_avg: 右手食指触觉均值（0-255）。
        right_middle_avg: 右手中指触觉均值（0-255）。
        threshold: 判定阈值，默认 30.0。

    Returns:
        True 表示成功触碰，False 表示未触碰。
    """
    return (
        right_thumb_avg > threshold
        and right_index_avg > threshold
        and right_middle_avg > threshold
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="触觉成功判定")
    parser.add_argument("--thumb", type=float, required=True, help="右手拇指触觉均值")
    parser.add_argument("--index", type=float, required=True, help="右手食指触觉均值")
    parser.add_argument("--middle", type=float, required=True, help="右手中指触觉均值")
    parser.add_argument("--threshold", type=float, default=30.0, help="判定阈值 (default: 30.0)")
    args = parser.parse_args()

    result = check_tactile_success(args.thumb, args.index, args.middle, args.threshold)
    print(f"thumb={args.thumb:.1f}  index={args.index:.1f}  middle={args.middle:.1f}  "
          f"threshold={args.threshold:.1f}  => {'SUCCESS' if result else 'FAIL'}")


if __name__ == "__main__":
    main()
