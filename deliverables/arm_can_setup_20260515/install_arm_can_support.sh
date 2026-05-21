#!/usr/bin/env bash
set -euo pipefail

if [ "${EUID}" -ne 0 ]; then
  echo "Please run as root: sudo ./install_arm_can_support.sh" >&2
  exit 1
fi

package_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

apt-get update
apt-get install -y can-utils usbutils

modprobe can || true
modprobe can_raw || true
modprobe slcan || true
modprobe gs_usb || true

install -m 0755 "${package_dir}/can_add.sh" /usr/local/bin/can_add.sh
install -m 0755 "${package_dir}/slcan_add.sh" /usr/local/bin/slcan_add.sh
install -m 0755 "${package_dir}/bind_airbot_device" /usr/local/bin/bind_airbot_device

install -m 0644 "${package_dir}/90-usb-can.rules" /etc/udev/rules.d/90-usb-can.rules
install -m 0644 "${package_dir}/90-usb-slcan.rules" /etc/udev/rules.d/90-usb-slcan.rules
install -m 0644 "${package_dir}/slcan@.service" /etc/systemd/system/slcan@.service

systemctl daemon-reload
udevadm control --reload-rules
udevadm trigger

echo
echo "Arm CAN support installed."
echo "Next:"
echo "  1. Plug in the USB-CAN device(s)."
echo "  2. Run: sudo ./bind_airbot_device"
echo "  3. Enter can0 for left arm and can1 for right arm."
echo "  4. Replug the USB-CAN device(s)."
echo "  5. Check: ip -brief link | grep -E '(^|[[:space:]])can[0-9]+'"
