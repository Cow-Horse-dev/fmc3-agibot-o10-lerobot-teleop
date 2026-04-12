"""
Copyright: qiuzhi.tech
Author: hanyang
Date: 2025-09-09
LastEditTime: 2025-09-09 18:15:02
Description: LeRobot dataset visualization using Rerun - based on official lerobot visualize_dataset.py
"""

import argparse
import gc
import logging
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import rerun as rr
import torch
import torch.utils.data
import tqdm

from lerobot.scripts.lerobot_dataset_viz import EpisodeSampler, to_hwc_uint8_numpy
from lerobot_play.utils.lerobot_dataset import LeRobotDataset, LeRobotDatasetMetadata
from lerobot_play.utils.agibot_o10 import (
    AGIBOT_O10_ARM_FEATURE_NAMES,
    AGIBOT_O10_HAND_FEATURE_NAMES,
    AGIBOT_O10_POSE_FEATURE_NAMES,
)


def log_robot_state_grouped(
    batch, batch_idx, dataset, robot_type="airbot_PTK_follower"
):
    """Log robot states with robot type specific grouping"""

    if robot_type == "airbot_play_follower":
        # Single arm robot: 7 states (6 joints + 1 eef)
        motor_names = [
            "joint1",
            "joint2",
            "joint3",
            "joint4",
            "joint5",
            "joint6",
            "eef",
        ]

        # Log joint positions (observation.state)
        if "observation.state" in batch:
            joint_positions = batch["observation.state"][batch_idx]
            for name, val in zip(motor_names, joint_positions):
                rr.log(f"state/{name}", rr.Scalars(val.item()))

        # Log actions
        if "action" in batch:
            actions = batch["action"][batch_idx]
            for name, val in zip(motor_names, actions):
                rr.log(f"action/{name}", rr.Scalars(val.item()))

    elif (
        robot_type == "airbot_PTK_follower"
        or robot_type == "airbot_TOK4_follower"
        or robot_type == "quest3_follower"
        or robot_type == "airbot_TOK2_follower"
    ):
        # Dual arm robot: 14 states (left 7 + right 7)
        motor_names = [
            "left_joint1",
            "left_joint2",
            "left_joint3",
            "left_joint4",
            "left_joint5",
            "left_joint6",
            "left_eef",
            "right_joint1",
            "right_joint2",
            "right_joint3",
            "right_joint4",
            "right_joint5",
            "right_joint6",
            "right_eef",
        ]

        # Log joint positions (observation.state)
        if "observation.state" in batch:
            joint_positions = batch["observation.state"][batch_idx]

            # Left arm joints (indices 0-6)
            left_arm_names = motor_names[:7]
            left_arm_positions = joint_positions[:7]
            for name, val in zip(left_arm_names, left_arm_positions):
                rr.log(f"state/left_arm/{name}", rr.Scalars(val.item()))

            # Right arm joints (indices 7-13)
            right_arm_names = motor_names[7:]
            right_arm_positions = joint_positions[7:]
            for name, val in zip(right_arm_names, right_arm_positions):
                rr.log(f"state/right_arm/{name}", rr.Scalars(val.item()))

        # Log actions with the same grouping
        if "action" in batch:
            actions = batch["action"][batch_idx]

            # Left arm actions (indices 0-6)
            left_arm_actions = actions[:7]
            for name, val in zip(left_arm_names, left_arm_actions):
                rr.log(f"action/left_arm/{name}", rr.Scalars(val.item()))

            # Right arm actions (indices 7-13)
            right_arm_actions = actions[7:]
            for name, val in zip(right_arm_names, right_arm_actions):
                rr.log(f"action/right_arm/{name}", rr.Scalars(val.item()))
    elif robot_type == "pico_follower_single_arm_agibot_o10":
        if "observation.state" in batch:
            joint_positions = batch["observation.state"][batch_idx]

            for index, name in enumerate(AGIBOT_O10_ARM_FEATURE_NAMES):
                rr.log(f"state/arm/{name}", rr.Scalars(joint_positions[index].item()))

            hand_offset = len(AGIBOT_O10_ARM_FEATURE_NAMES)
            for index, name in enumerate(AGIBOT_O10_HAND_FEATURE_NAMES):
                rr.log(
                    f"state/hand/{name}",
                    rr.Scalars(joint_positions[hand_offset + index].item()),
                )

            pose_offset = hand_offset + len(AGIBOT_O10_HAND_FEATURE_NAMES)
            for index, name in enumerate(AGIBOT_O10_POSE_FEATURE_NAMES):
                rr.log(
                    f"state/pose/{name}",
                    rr.Scalars(joint_positions[pose_offset + index].item()),
                )

        if "action" in batch:
            actions = batch["action"][batch_idx]

            for index, name in enumerate(AGIBOT_O10_ARM_FEATURE_NAMES):
                rr.log(f"action/arm/{name}", rr.Scalars(actions[index].item()))

            hand_offset = len(AGIBOT_O10_ARM_FEATURE_NAMES)
            for index, name in enumerate(AGIBOT_O10_HAND_FEATURE_NAMES):
                rr.log(
                    f"action/hand/{name}",
                    rr.Scalars(actions[hand_offset + index].item()),
                )
    else:
        raise ValueError(f"Unsupported robot type: {robot_type}")


def visualize_dataset_local(
    repo_id: str,
    root: str,
    episode_index: int = 0,
    max_episodes: int = 5,
    batch_size: int = 32,
    num_workers: int = 0,
    robot_type: str = "airbot_PTK_follower",
) -> None:
    """Visualize dataset stored locally"""

    # Check available episodes
    meta = LeRobotDatasetMetadata(repo_id, root=root)
    available = []
    root_path = Path(root).expanduser()

    print("Checking available episodes...")
    for ep_idx in range(meta.total_episodes):
        parquet_ok = (root_path / meta.get_data_file_path(ep_idx)).is_file()
        videos_ok = all(
            (root_path / meta.get_video_file_path(ep_idx, k)).is_file()
            for k in meta.video_keys
        )
        if parquet_ok and videos_ok:
            available.append(ep_idx)

    if not available:
        print("No complete episodes found!")
        return

    print(f"Found {len(available)} complete episodes: {available}")

    if episode_index not in available:
        print(f"Episode {episode_index} not available. Using episode {available[0]}")
        episode_index = available[0]

    # Load dataset with limited episodes for faster loading
    episodes_to_use = (
        available[:max_episodes] if len(available) > max_episodes else available
    )

    print(f"Loading dataset with episodes: {episodes_to_use}")
    dataset = LeRobotDataset(
        repo_id=repo_id,
        root=root,
        episodes=episodes_to_use,
        download_videos=False,
        video_backend="pyav",
    )

    print("Dataset loaded successfully!")
    print("Dataset features:")
    for key, feature in dataset.features.items():
        print(f"  {key}: {feature}")

    # Setup dataloader
    print("Setting up dataloader...")
    episode_sampler = EpisodeSampler(dataset, episode_index)
    dataloader = torch.utils.data.DataLoader(
        dataset,
        num_workers=num_workers,
        batch_size=batch_size,
        sampler=episode_sampler,
    )

    # Initialize Rerun
    print("Starting Rerun visualization...")
    rr.init(f"{repo_id.replace('/', '_')}_episode_{episode_index}", spawn=True)

    # Manually call python garbage collector after `rr.init`
    gc.collect()

    print("Logging data to Rerun...")
    available_camera_keys = None

    # Iterate through the episode
    for batch in tqdm.tqdm(
        dataloader, total=len(dataloader), desc="Visualizing frames"
    ):
        if available_camera_keys is None:
            available_camera_keys = [
                key for key in dataset.meta.camera_keys if key in batch
            ]
            if available_camera_keys:
                print(f"Showing camera streams: {available_camera_keys}")
            elif dataset.meta.camera_keys:
                print(
                    "No camera streams were found in loaded samples; showing state/action only."
                )
            else:
                print("Dataset contains no camera streams.")

        # Process each sample in the batch
        for i in range(len(batch["index"])):
            # Set timeline
            rr.set_time("frame_index", sequence=batch["frame_index"][i].item())
            rr.set_time("timestamp", timestamp=batch["timestamp"][i].item())

            # Log camera images
            for key in available_camera_keys:
                rr.log(key, rr.Image(to_hwc_uint8_numpy(batch[key][i])))

            # Log robot states with grouping
            log_robot_state_grouped(batch, i, dataset, robot_type)

            # Log additional data if available
            if "next.done" in batch:
                rr.log("next.done", rr.Scalars(batch["next.done"][i].item()))

            if "next.reward" in batch:
                rr.log("next.reward", rr.Scalars(batch["next.reward"][i].item()))

            if "next.success" in batch:
                rr.log("next.success", rr.Scalars(batch["next.success"][i].item()))

    print("Visualization complete! Rerun viewer should be open.")


def main():
    parser = argparse.ArgumentParser(
        description="Visualize LeRobot dataset stored locally with robot type specific grouping"
    )

    parser.add_argument(
        "--repo-id",
        type=str,
        default="test_03",
        help="Repository ID of the dataset (e.g., 'test_03')",
    )

    parser.add_argument(
        "--root",
        type=str,
        default="~/.cache/huggingface/lerobot/test_03",
        help="Root directory where the dataset is stored locally",
    )

    parser.add_argument(
        "--robot-type",
        type=str,
        default="airbot_PTK_follower",
        choices=[
            "airbot_play_follower",
            "airbot_PTK_follower",
            "airbot_TOK4_follower",
            "airbot_TOK2_follower",
            "quest3_follower",
            "pico_follower_single_arm_agibot_o10",
        ],
        help="Robot type: airbot_play_follower (single arm) or airbot_PTK_follower (dual arm)",
    )

    parser.add_argument(
        "--episode-index",
        type=int,
        default=0,
        help="Episode index to visualize (default: 0)",
    )

    parser.add_argument(
        "--max-episodes",
        type=int,
        default=1,
        help="Maximum number of episodes to load for faster initialization (default: 1)",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for DataLoader (default: 32)",
    )

    parser.add_argument(
        "--num-workers",
        type=int,
        default=0,
        help="Number of DataLoader workers (default: 0)",
    )

    args = parser.parse_args()

    # Set default root if not provided
    if args.root is None:
        args.root = f"~/.cache/huggingface/lerobot/lerobot/{args.repo_id}"

    print(f"Visualizing dataset:")
    print(f"  Repository ID: {args.repo_id}")
    print(f"  Root directory: {args.root}")
    print(f"  Robot type: {args.robot_type}")
    print(f"  Episode index: {args.episode_index}")

    visualize_dataset_local(
        repo_id=args.repo_id,
        root=args.root,
        episode_index=args.episode_index,
        max_episodes=args.max_episodes,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        robot_type=args.robot_type,
    )


if __name__ == "__main__":
    main()
