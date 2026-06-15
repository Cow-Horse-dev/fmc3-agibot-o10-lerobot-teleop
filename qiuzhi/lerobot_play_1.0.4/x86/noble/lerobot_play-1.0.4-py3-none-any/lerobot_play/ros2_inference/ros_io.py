"""Mechanical glue between ObservationFields/ActionChunkFields and the built ROS2
messages. Kept separate from messages.py so the conversion logic stays unit-testable
without a built workspace."""

from __future__ import annotations

import pickle  # nosec - trusted one-time handshake on a private LAN

from sensor_msgs.msg import CompressedImage, JointState

from lerobot_ros2_msgs.msg import ActionChunk, ActionPoint, Observation, RobotSchema

from .messages import (
    ActionChunkFields,
    ActionPointFields,
    ObservationFields,
)


def observation_fields_to_msg(fields: ObservationFields, clock) -> Observation:
    msg = Observation()
    msg.header.stamp = clock.now().to_msg()
    msg.timestep = fields.timestep
    msg.must_go = fields.must_go
    msg.task = fields.task

    state = JointState()
    state.header.stamp = msg.header.stamp
    state.name = list(fields.state_names)
    state.position = list(fields.state_positions)
    msg.state = state

    images = []
    for key, jpeg in zip(fields.image_keys, fields.image_jpegs):
        image = CompressedImage()
        image.header.stamp = msg.header.stamp
        image.header.frame_id = key
        image.format = "jpeg"
        image.data = list(jpeg)
        images.append(image)
    msg.images = images
    msg.image_keys = list(fields.image_keys)
    return msg


def observation_msg_to_fields(msg: Observation) -> ObservationFields:
    return ObservationFields(
        timestep=int(msg.timestep),
        must_go=bool(msg.must_go),
        task=str(msg.task),
        timestamp=msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
        state_names=list(msg.state.name),
        state_positions=list(msg.state.position),
        image_keys=list(msg.image_keys),
        image_jpegs=[bytes(image.data) for image in msg.images],
    )


def action_chunk_fields_to_msg(fields: ActionChunkFields, clock) -> ActionChunk:
    msg = ActionChunk()
    msg.header.stamp = clock.now().to_msg()
    msg.base_timestep = fields.base_timestep
    msg.joint_names = list(fields.joint_names)
    points = []
    for point in fields.points:
        ap = ActionPoint()
        ap.timestep = point.timestep
        ap.position = list(point.position)
        points.append(ap)
    msg.points = points
    return msg


def action_chunk_msg_to_fields(msg: ActionChunk) -> ActionChunkFields:
    return ActionChunkFields(
        base_timestep=int(msg.base_timestep),
        timestamp=msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
        joint_names=list(msg.joint_names),
        points=[
            ActionPointFields(timestep=int(p.timestep), position=list(p.position))
            for p in msg.points
        ],
    )


def remote_policy_config_to_schema_msg(remote_policy_config, clock) -> RobotSchema:
    msg = RobotSchema()
    msg.header.stamp = clock.now().to_msg()
    msg.remote_policy_config = list(pickle.dumps(remote_policy_config))  # nosec
    msg.policy_type = str(remote_policy_config.policy_type)
    msg.model_path = str(remote_policy_config.pretrained_name_or_path)
    msg.actions_per_chunk = int(remote_policy_config.actions_per_chunk)
    return msg


def schema_msg_to_remote_policy_config(msg: RobotSchema):
    return pickle.loads(bytes(msg.remote_policy_config))  # nosec
