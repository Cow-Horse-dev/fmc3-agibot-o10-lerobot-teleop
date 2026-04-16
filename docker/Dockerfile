FROM osrf/ros:jazzy-desktop-full

SHELL ["/bin/bash", "-lc"]

ARG DEBIAN_FRONTEND=noninteractive

ENV ROS_DISTRO=jazzy
ENV ARM_HAND_TELEOP_HOME=/home/phl/workspace/arm-hand-teleop
ENV VIRTUAL_ENV=/opt/arm-hand-teleop-venv
ENV ARM_HAND_TELEOP_PYTHON=/opt/arm-hand-teleop-venv/bin/python
ENV PATH="/opt/arm-hand-teleop-venv/bin:${PATH}"
ENV PIP_NO_CACHE_DIR=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    can-utils \
    cmake \
    curl \
    ffmpeg \
    git \
    iproute2 \
    iputils-ping \
    libcurl4-openssl-dev \
    libegl1 \
    libgl1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libssl-dev \
    libudev1 \
    libusb-1.0-0 \
    libusb-1.0-0-dev \
    libxext6 \
    libxrender1 \
    lsof \
    net-tools \
    procps \
    python3-dev \
    python3-pip \
    python3-venv \
    udev \
    usbutils \
    v4l-utils \
  && rm -rf /var/lib/apt/lists/*

COPY docker/entrypoint.sh /usr/local/bin/arm-hand-teleop-entrypoint
RUN chmod +x /usr/local/bin/arm-hand-teleop-entrypoint

COPY docker/requirements.runtime.txt /tmp/requirements.runtime.txt
COPY qiuzhi/VR遥操作方案/airbot_vr_1.0.0/x86_noble /tmp/local-wheels/airbot-vr
COPY qiuzhi/lerobot_play_1.0.4/x86/noble /tmp/local-wheels/lerobot-play

RUN python3 -m venv --system-site-packages "${VIRTUAL_ENV}" \
  && python -m pip install --upgrade pip setuptools wheel build \
  && python -m pip install \
    /tmp/local-wheels/airbot-vr/airbot_hardware_py-0.2.8-cp312-cp312-manylinux_2_39_x86_64.whl \
    /tmp/local-wheels/airbot-vr/airbot_vr_py-1.0.0-py3-none-any.whl \
    /tmp/local-wheels/airbot-vr/mmk2_kdl_py-0.1.3-py3-none-any.whl \
    /tmp/local-wheels/lerobot-play/airbot_state_machine-0.1.3-py3-none-any.whl \
  && python -m pip install -r /tmp/requirements.runtime.txt

COPY . ${ARM_HAND_TELEOP_HOME}

RUN source /opt/ros/${ROS_DISTRO}/setup.bash \
  && cd ${ARM_HAND_TELEOP_HOME}/yudie/vendor_sdk/Omnihand-2025-SDK-dev_xuqigui \
  && cp ${ARM_HAND_TELEOP_HOME}/yudie/omnihand_2025/libusbcanfd.so.1.0.10 \
    thirdParty/usbcanfd_libusb_x64_1.0.10_250328/libusbcanfd.so \
  && PATH="/usr/bin:/bin:${PATH}" ./build.sh \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_CPP_EXAMPLES=OFF \
    -DPython3_EXECUTABLE="${VIRTUAL_ENV}/bin/python" \
  && python -m pip install build/omnihand_2025_pkg/dist/omnihand_2025_py-*.whl

WORKDIR ${ARM_HAND_TELEOP_HOME}

RUN mkdir -p \
    ${ARM_HAND_TELEOP_HOME}/logs \
    /home/phl/workspace/dataset \
    /home/phl/workspace/mymodel \
    /home/phl/workspace/mymodels

ENTRYPOINT ["/usr/local/bin/arm-hand-teleop-entrypoint"]
CMD ["/bin/bash"]
