# MediaPipe Camera Control Demo for the O10 Dexterous Hand

完整中文演示命令先看 `docs/demo_runbook.md`。这个文件只保留 MediaPipe
摄像头控制灵巧手的细节说明。

This note documents the verified setup for controlling an Agibot O10 dexterous
hand from a USB camera using MediaPipe hand tracking.

## Verified Setup

- Workspace: `/home/phl/workspace/arm-hand-teleop`
- Python environment: `arm-hand-teleop`
- Demo script: `tests/test_mediapipe_right_hand_control.py`
- Verified USB camera: `JYU2C-2083`
- Verified video device: `/dev/video14`
- Capture size: `640x480`
- Default controlled hand: right hand

The camera also exposes `/dev/video15`, but that node is metadata only. Use
`/dev/video14` for OpenCV/MediaPipe image capture.

## Run the Demo

Open a terminal and activate the environment:

```bash
cd /home/phl/workspace/arm-hand-teleop
conda activate arm-hand-teleop
```

Run the verified hardware demo:

```bash
python tests/test_mediapipe_right_hand_control.py \
  --camera /dev/video14 \
  --width 640 \
  --height 480
```

An OpenCV window named `MediaPipe -> O10 Hand` should appear. Move a human hand
in front of the USB camera. The script detects the hand landmarks, maps them to
O10 hand joint targets, and sends the joint commands to the right dexterous
hand.

Press `q` in the OpenCV window to stop the demo.

## Stable Camera Path

If `/dev/video14` changes after rebooting or reconnecting cameras, use the
stable by-id path:

```bash
/dev/v4l/by-id/usb-JoyandAI_JYU2C-2083_JYU2C-2083-2603103-video-index0
```

Example:

```bash
python tests/test_mediapipe_right_hand_control.py \
  --camera /dev/v4l/by-id/usb-JoyandAI_JYU2C-2083_JYU2C-2083-2603103-video-index0 \
  --width 640 \
  --height 480
```

## Useful Checks

List all connected video devices:

```bash
v4l2-ctl --list-devices
```

Confirm that `/dev/video14` is the image capture node:

```bash
v4l2-ctl -d /dev/video14 --all
```

The image capture node should show `Device Caps` including `Video Capture`.
The metadata node, currently `/dev/video15`, shows `Metadata Capture` instead.

## Troubleshooting

- If the camera window does not open, confirm that the camera is still
  `/dev/video14` or use the by-id path above.
- If MediaPipe is missing, install it in the active `arm-hand-teleop`
  environment before the demo.
- If the hand does not move, first run with `--no-hw` to verify vision tracking,
  then check the O10 hand USB-CANFD connection.
- If the wrong hand is being controlled, pass `--hand left --channel-id 0` for a
  left-hand test, or use the default command for the right hand.
