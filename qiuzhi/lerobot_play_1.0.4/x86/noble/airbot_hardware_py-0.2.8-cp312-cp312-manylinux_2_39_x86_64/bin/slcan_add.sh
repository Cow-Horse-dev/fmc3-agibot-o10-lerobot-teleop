#!/bin/sh

# Find an unused CAN index to avoid conflicts with gsusb or other CAN devices
for i in $(seq 0 99); do
    if ! ip link show can$i > /dev/null 2>&1; then
        CAN_INDEX=$i
        break
    fi
done

# Check if we found an available index
if [ -z "$CAN_INDEX" ]; then
    echo "Error: No available CAN index found."
    exit 1
fi

/usr/bin/slcand -o -c -f -s8 -S 3000000 /dev/ttyCAN$1 can$CAN_INDEX

sleep 1

/usr/sbin/ip link set up can$CAN_INDEX
/usr/sbin/ip link set can$CAN_INDEX txqueuelen 1000
