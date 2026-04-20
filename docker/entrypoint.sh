#!/usr/bin/env bash
set -eo pipefail

# ROS setup scripts may read optional unset variables.
set +u
source "/opt/ros/${ROS_DISTRO:-jazzy}/setup.bash"
set -u

cd ~/workspace/arm-hand-teleop
exec "$@"
