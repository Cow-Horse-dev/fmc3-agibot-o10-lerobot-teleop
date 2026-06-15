cmake_minimum_required(VERSION 3.8)
project(lerobot_ros2_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/ActionPoint.msg"
  "msg/ActionChunk.msg"
  "msg/Observation.msg"
  "msg/RobotSchema.msg"
  DEPENDENCIES std_msgs sensor_msgs
)

ament_package()
