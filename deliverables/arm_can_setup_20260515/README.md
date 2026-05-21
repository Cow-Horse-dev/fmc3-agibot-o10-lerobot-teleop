# Arm CAN Setup Bundle

This bundle is for the robot arm CAN interface only.

It does not install the O10 dexterous hand USB-CANFD driver.

## Files

- `install_arm_can_support.sh`: install helper
- `bind_airbot_device`: bind USB-CAN serials to fixed interface names
- `can_add.sh`: bring up native SocketCAN devices at 1 Mbps
- `slcan_add.sh`: bring up SLCAN devices
- `90-usb-can.rules`: udev rule for native SocketCAN USB devices
- `90-usb-slcan.rules`: udev rule for SLCAN USB devices
- `slcan@.service`: systemd service for SLCAN devices

## Install

```bash
cd arm_can_setup_20260515
sudo ./install_arm_can_support.sh
```

## Bind device names

```bash
cd arm_can_setup_20260515
sudo ./bind_airbot_device
```

When prompted:

- enter `can0` for the left arm USB-CAN
- enter `can1` for the right arm USB-CAN

Then unplug and replug the USB-CAN device(s).

## Check

```bash
ip -brief link | grep -E '(^|[[:space:]])can[0-9]+'
```

Expected on a dual-arm machine:

```text
can0
can1
```

## Temporary manual bring-up

If a device already exists but is down, you can bring it up manually.

Native SocketCAN:

```bash
sudo ip link set can0 up type can bitrate 1000000
sudo ip link set can0 txqueuelen 1000
```

SLCAN:

```bash
sudo slcand -o -c -f -s8 -S 3000000 /dev/ttyUSB0 can0
sleep 1
sudo ip link set up can0
sudo ip link set can0 txqueuelen 1000
```

## Usage with this repo

Right arm configs usually use:

```text
can1
```

Left arm configs usually use:

```text
can0
```

If only the right arm is used, either:

- keep the device name as `can1` to match the existing configs, or
- rename it to `can0` and update the YAML config `robot.port`.
