#!/bin/bash

# To check if running with root privileges
if [ "$(id -u)" -ne 0 ]; then
    echo "Please run this script with root privileges"
    exit 1
fi

# To create udev rule file
echo "Creating the udev rules..."

cat > /etc/udev/rules.d/80-usb-serial.rules << EOF
# Device 1: VID=1a86, PID=7523
SUBSYSTEM=="usb", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE="0666", GROUP="dialout"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE="0666", GROUP="dialout"
KERNEL=="ttyUSB*", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE="0666", GROUP="dialout"
KERNEL=="ttyACM*", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="7523", MODE="0666", GROUP="dialout"

# Device 2: VID=1915, PID=521f
SUBSYSTEM=="usb", ATTRS{idVendor}=="1915", ATTRS{idProduct}=="521f", MODE="0666", GROUP="dialout"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1915", ATTRS{idProduct}=="521f", MODE="0666", GROUP="dialout"
KERNEL=="ttyUSB*", ATTRS{idVendor}=="1915", ATTRS{idProduct}=="521f", MODE="0666", GROUP="dialout"
KERNEL=="ttyACM*", ATTRS{idVendor}=="1915", ATTRS{idProduct}=="521f", MODE="0666", GROUP="dialout"
EOF

# To add the current user to the group dialout
CURRENT_USER=$(logname || echo $SUDO_USER)
if [ -z "$CURRENT_USER" ]; then
    echo "Unable to confirm the current user, please manually add the user to the group dialout"
    echo "Use the command: sudo usermod -a -G dialout USERNAME"
else
    echo "Add $CURRENT_USER to the group dialout..."
    usermod -a -G dialout "$CURRENT_USER"
    echo "The user $CURRENT_USER has been added to the group dialout"
fi

# To reload udev rule
echo "Reloading the udev rules..."
udevadm control --reload-rules
udevadm trigger

echo "Setting completed!"
echo "Please log out and log in again, or restart the system for the changes to take effect"