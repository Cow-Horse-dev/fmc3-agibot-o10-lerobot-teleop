# OmniHand Flexible 2025 SDK Python API

## Enumerations

### EFinger

```python
from enum import IntEnum

class EFinger(IntEnum):
    THUMB = 1
    INDEX = 2
    MIDDLE = 3
    RING = 4
    LITTLE = 5
    PALM = 6
    DORSUM = 7
    UNKNOWN = 255
```

### EHandType

```python
class EHandType(IntEnum):
    LEFT = 0      # Left hand
    RIGHT = 1     # Right hand
    UNKNOWN = 10
```

### EControlMode

```python
class EControlMode(IntEnum):
    POSITION = 0         # Position mode
    SERVO = 1            # Servo mode
    VELOCITY = 2         # Velocity mode
    TORQUE = 3           # Torque mode
    POSITION_TORQUE = 4  # Position-Torque mode (Not yet supported)
    VELOCITY_TORQUE = 5  # Velocity-Torque mode (Not yet supported)
    POSITION_VELOCITY_TORQUE = 6 # Position-Velocity-Torque mode (Not yet supported)
    UNKNOWN = 10
```

## Data Structures

### VendorInfo

```python
from typing import Optional, List

class Version:
    # Assuming Version is a simple class or dataclass
    major: int
    minor: int
    patch: int

class VendorInfo:
    product_model: str
    product_seq_num: str
    hardware_version: Version
    software_version: Version
    voltage: int
    dof: int

    def __init__(self) -> None: ...

    def __str__(self) -> str: ...
```

### DeviceInfo

```python
class CommuParams:
    bitrate: int
    sample_point: int
    dbitrate: int
    dsample_point: int

    def __init__(self) -> None: ...

class DeviceInfo:
    device_id: int
    commu_params: CommuParams

    def __init__(self) -> None: ...

    def __str__(self) -> str: ...
```

### JointMotorErrorReport

````python
class JointMotorErrorReport:
    stalled: bool          # Stall flag
    overheat: bool         # Overheat flag
    over_current: bool     # Overcurrent flag
    motor_except: bool     # Motor exception flag
    commu_except: bool     # Communication exception flag```

### MixCtrl (Mixed Control Structure)

```python
class MixCtrl:
    joint_index: int               # Joint index (1-10)
    ctrl_mode: EControlMode        # Control mode
    tgt_posi: Optional[int]        # Target position
    tgt_velo: Optional[int]        # Target velocity
    tgt_torque: Optional[int]      # Target torque
````

## Core Class

### AgibotHandO10

The main class for controlling the dexterous hand, providing all control interfaces.

```python
class AgibotHandO10:
    @staticmethod
    def create_hand(hand_type: EHandType = EHandType.LEFT,
                    device_id: int = 1,
                    canfd_id: int = 0,
                    channel_id: int = 0) -> 'AgibotHandO10': ...
    """Creates a dexterous hand object.

    Args:
        hand_type: The hand type, defaults to the left hand.
        device_id: The device ID, defaults to 1.
        canfd_id: USB CANFD adapter device index, defaults to 0.
        channel_id: CAN channel index, defaults to 0 (USBCANFD-200U has 2 channels).
    """

    @staticmethod
    def find_canfd_id_by_serial_number(serial_number: str) -> int: ...
    """Finds canfd_id by serial number.
    
    Args:
        serial_number: Device serial number (supports partial matching).
    Returns:
        canfd_id, returns -1 if not found.
    """

    @staticmethod
    def find_canfd_ids_by_serial_numbers(serial_numbers: List[str]) -> List[int]: ...
    """Batch find canfd_ids by serial numbers (scans only once).
    
    Args:
        serial_numbers: List of serial numbers.
    Returns:
        List of canfd_ids, -1 for not found positions.
    """

    def __init__(self):
        """Initializes the dexterous hand object."""
        pass

    # Device Information
    def get_vendor_info(self) -> VendorInfo:
        """Gets vendor information."""
        pass

    def get_device_info(self) -> DeviceInfo:
        """Gets device information."""
        pass

    def set_device_id(self, device_id: int) -> None:
        """Sets the device ID."""
        pass

    # Position Control
    def set_joint_position(self, joint_motor_index: int, position: int) -> None:
        """Sets the position of a single joint motor."""
        pass

    def get_joint_position(self, joint_motor_index: int) -> int:
        """Gets the position of a single joint motor."""
        pass

    def set_all_joint_positions(self, positions: List[int]) -> None:
        """Sets the positions of all joint motors in batch."""
        pass

    def get_all_joint_positions(self) -> List[int]:
        """Gets the positions of all joint motors in batch."""
        pass

    # Joint Angle Control
    def set_all_active_joint_angles(self, angles: List[float]) -> None:
        """Sets the angles of all active joints (in radians)."""
        pass

    def get_all_active_joint_angles(self) -> List[float]:
        """Gets the angles of all active joints (in radians)."""
        pass

    def get_all_joint_angles(self) -> List[float]:
        """Gets the angles of all joints (active and passive, in radians)."""
        pass

    # Velocity Control
    def set_joint_velocity(self, joint_motor_index: int, velocity: int) -> None:
        """Sets the velocity of a single joint motor."""
        pass

    def get_joint_velocity(self, joint_motor_index: int) -> int:
        """Gets the velocity of a single joint motor."""
        pass

    def set_all_joint_velocities(self, velocities: List[int]) -> None:
        """Sets the velocities of all joint motors in batch."""
        pass

    def get_all_joint_velocities(self) -> List[int]:
        """Gets the velocities of all joint motors in batch."""
        pass

    # Sensor Data
    def get_tactile_sensor_data(self, eFinger: EFinger) -> List[int]:
        """Gets tactile sensor data (unit: 1g, max: 255g, sampling: 10Hz)."""
        pass

    # Control Mode
    def set_control_mode(self, joint_motor_index: int, mode: int) -> None:
        """Sets the control mode of a single joint motor."""
        pass

    def get_control_mode(self, joint_motor_index: int) -> int:
        """Gets the control mode of a single joint motor."""
        pass

    def set_all_control_modes(self, ctrl_modes: List[int]) -> None:
        """Sets the control modes of all joint motors in batch."""
        pass

    def get_all_control_modes(self) -> List[int]:
        """Gets the control modes of all joint motors in batch."""
        pass

    # Current Threshold Control
    def set_current_threshold(self, joint_motor_index: int, current_threshold: int) -> None:
        """Sets the current threshold of a single joint motor."""
        pass

    def get_current_threshold(self, joint_motor_index: int) -> int:
        """Gets the current threshold of a single joint motor."""
        pass

    def set_all_current_thresholds(self, current_thresholds: List[int]) -> None:
        """Sets the current thresholds of all joint motors in batch."""
        pass

    def get_all_current_thresholds(self) -> List[int]:
        """Gets the current thresholds of all joint motors in batch."""
        pass

    # Mixed Control
    def mix_ctrl_joint_motor(self, mix_ctrls: List[MixCtrl]) -> None:
        """Controls joint motors in mixed mode."""
        pass

    # Error Handling
    def get_error_report(self, joint_motor_index: int) -> JointMotorErrorReport:
        """Gets the error report for a single joint motor."""
        pass

    def get_all_error_reports(self) -> List[JointMotorErrorReport]:
        """Gets the error reports for all joint motors."""
        pass

    # Temperature Monitoring
    def get_temperature_report(self, joint_motor_index: int) -> int:
        """Gets the temperature report for a single joint motor."""
        pass

    def get_all_temperature_reports(self) -> List[int]:
        """Gets the temperature reports for all joint motors."""
        pass

    # Current Monitoring
    def get_current_report(self, joint_motor_index: int) -> int:
        """Gets the current report for a single joint motor."""
        pass

    def get_all_current_reports(self) -> List[int]:
        """Gets the current reports for all joint motors."""
        pass

    # Debugging Features
    def show_data_details(self, show: bool) -> None:
        """Toggles the display of raw send/receive data details."""
        pass
```

## Detailed API Reference

### Device Discovery and Creation (Static Methods)

```python
@staticmethod
def find_canfd_id_by_serial_number(serial_number: str) -> int:
    """Finds canfd_id by serial number.

    Args:
        serial_number: Device serial number (supports partial matching).

    Returns:
        int: canfd_id, returns -1 if not found.

    Example:
        canfd_id = AgibotHandO10.find_canfd_id_by_serial_number("A029A58630B30D14DBB0")
    """

@staticmethod
def find_canfd_ids_by_serial_numbers(serial_numbers: List[str]) -> List[int]:
    """Batch find canfd_ids by serial numbers (scans only once, more efficient).

    Args:
        serial_numbers: List of serial numbers.

    Returns:
        List[int]: List of canfd_ids, -1 for not found positions.

    Example:
        # Scan once to find both left and right hands
        canfd_ids = AgibotHandO10.find_canfd_ids_by_serial_numbers([
            "LEFT_HAND_SN",
            "RIGHT_HAND_SN"
        ])
        left_hand = AgibotHandO10.create_hand(EHandType.LEFT, 1, canfd_ids[0])
        right_hand = AgibotHandO10.create_hand(EHandType.RIGHT, 1, canfd_ids[1])
    """

@staticmethod
def create_hand(hand_type: EHandType = EHandType.LEFT,
               device_id: int = 1,
               canfd_id: int = 0,
               channel_id: int = 0) -> 'AgibotHandO10':
    """Creates a dexterous hand object.

    Args:
        hand_type: Hand type (EHandType.LEFT or EHandType.RIGHT).
        device_id: Device ID, defaults to 1, determined by the firmware of hand device.
        canfd_id: USB CANFD adapter device index, defaults to 0.
        channel_id: CAN channel index, defaults to 0 (USBCANFD-200U has 2 channels: 0 and 1).

    Returns:
        AgibotHandO10: Dexterous hand instance.
    """
```

### Device Information

```python
def get_vendor_info(self) -> VendorInfo:
    """Gets vendor information.

    Returns:
        VendorInfo: Vendor info structure containing product model,
                    serial number, hardware version, software version, etc.
    """

def get_device_info(self) -> DeviceInfo:
    """Gets device information.

    Returns:
        DeviceInfo: Device info structure containing device ID and communication parameters.

    Note:
        This interface is not supported for serial port communication.
    """

def set_device_id(self, device_id: int) -> None:
    """Sets the device ID.

    Args:
        device_id: The device ID.

    Note:
        This interface is not supported for serial port communication.
    """
```

### Motor Position Control

```python
def set_joint_position(self, joint_motor_index: int, position: int) -> None:
    """Sets the position of a single joint motor.

    Args:
        joint_motor_index: The index of the joint motor (1-10).
        position: The motor position, range: 0~2000.
    """

def get_joint_position(self, joint_motor_index: int) -> int:
    """Gets the position of a single joint motor.

    Args:
        joint_motor_index: The index of the joint motor (1-10).

    Returns:
        int: The current position value. Returns -1 on failure.
    """

def set_all_joint_positions(self, positions: List[int]) -> None:
    """Sets the positions of all joint motors in batch.

    Args:
        positions: A list of target positions for all joints, must have a length of 10.

    Note:
        Position data for all 10 joint motors must be provided.
    """

def get_all_joint_positions(self) -> List[int]:
    """Gets the positions of all joint motors in batch.

    Returns:
        List[int]: A list of the current positions of all joints, with a length of 10.
    """
```

### Joint Angle Control

#### Joint Angle I/O Order (Right Hand)

| Index | Joint Name         | Min Angle (rad) | Max Angle (rad) | Min Angle (°) | Max Angle (°) | Velocity Limit (rad/s) |
| ----- | ------------------ | --------------- | --------------- | ------------- | ------------- | ---------------------- |
| 1     | R_thumb_roll_joint | -0.03           | 1.12            | -2            | 64            | 0.164                  |
| 2     | R_thumb_abad_joint | -1.64           | 0.05            | -94           | 3             | 0.164                  |
| 3     | R_thumb_mcp_joint  | 0               | 0.84            | 0             | 48            | 0.308                  |
| 4     | R_index_abad_joint | -0.16           | 0               | -9            | 0             | 0.164                  |
| 5     | R_index_pip_joint  | 0               | 1.48            | 0             | 85            | 0.308                  |
| 6     | R_middle_pip_joint | 0               | 1.48            | 0             | 85            | 0.308                  |
| 7     | R_ring_abad_joint  | 0               | 0.17            | 0             | 10            | 0.164                  |
| 8     | R_ring_pip_joint   | 0               | 1.48            | 0             | 85            | 0.308                  |
| 9     | R_pinky_abad_joint | 0               | 0.19            | 0             | 11            | 0.164                  |
| 10    | R_pinky_pip_joint  | 0               | 1.48            | 0             | 85            | 0.308                  |

#### Joint Angle I/O Order (Left Hand)

| Index | Joint Name         | Min Angle (rad) | Max Angle (rad) | Min Angle (°) | Max Angle (°) | Velocity Limit (rad/s) |
| ----- | ------------------ | --------------- | --------------- | ------------- | ------------- | ---------------------- |
| 1     | L_thumb_roll_joint | -1.12           | 0.03            | -64           | 2             | 0.164                  |
| 2     | L_thumb_abad_joint | -0.05           | 1.64            | -3            | 94            | 0.164                  |
| 3     | L_thumb_mcp_joint  | -0.84           | 0               | -48           | 0             | 0.308                  |
| 4     | L_index_abad_joint | 0               | 0.16            | 0             | 9             | 0.164                  |
| 5     | L_index_pip_joint  | 0               | 1.48            | 0             | 85            | 0.308                  |
| 6     | L_middle_pip_joint | 0               | 1.48            | 0             | 85            | 0.308                  |
| 7     | L_ring_abad_joint  | -0.17           | 0               | -10           | 0             | 0.164                  |
| 8     | L_ring_pip_joint   | 0               | 1.48            | 0             | 85            | 0.308                  |
| 9     | L_pinky_abad_joint | -0.19           | 0               | -11           | 0             | 0.164                  |
| 10    | L_pinky_pip_joint  | 0               | 1.48            | 0             | 85            | 0.308                  |

```python
def set_all_active_joint_angles(self, angles: List[float]) -> None:
    """Sets the angles of all active joints (in radians).

    Args:
        angles: A list of target angles for all active joints, must have a length of 10.

    Note:
        For specific order and limits, please refer to the assets model files.
    """

def get_all_active_joint_angles(self) -> List[float]:
    """Gets the angles of all active joints (in radians).

    Returns:
        List[float]: A list of current angles of all active joints, with a length of 10.

    Note:
        For specific order and limits, please refer to the assets model files.
    """

def get_all_joint_angles(self) -> List[float]:
    """Gets the angles of all joints (active and passive, in radians).

    Returns:
        List[float]: A list of current angles of all joints.

    Note:
        For specific order and limits, please refer to the assets model files.
    """
```

### Velocity Control

```python
def set_joint_velocity(self, joint_motor_index: int, velocity: int) -> None:
    """Sets the velocity of a single joint motor.

    Args:
        joint_motor_index: The index of the joint motor (1-10).
        velocity: The target velocity value.

    Note:
        This interface is not supported for serial port communication.
    """

def get_joint_velocity(self, joint_motor_index: int) -> int:
    """Gets the velocity of a single joint motor.

    Args:
        joint_motor_index: The index of the joint motor (1-10).

    Returns:
        int: The current velocity value. Returns -1 on failure.

    Note:
        This interface is not supported for serial port communication.
    """

def set_all_joint_velocities(self, velocities: List[int]) -> None:
    """Sets the velocities of all joint motors in batch.

    Args:
        velocities: A list of target velocities for all joints, must have a length of 10.
    """

def get_all_joint_velocities(self) -> List[int]:
    """Gets the velocities of all joint motors in batch.

    Returns:
        List[int]: A list of the current velocities of all joints, with a length of 10.
    """
```

### Sensor Data

```python
def get_tactile_sensor_data(self, eFinger: EFinger) -> List[int]:
    """Gets the tactile sensor data for a specified part.

    Args:
        eFinger: The finger/palm enum value. Can be one of:
                EFinger.THUMB,
                EFinger.INDEX,
                EFinger.MIDDLE,
                EFinger.RING,
                EFinger.LITTLE,
                EFinger.PALM,
                EFinger.DORSUM

    Returns:
        List[int]: A list of tactile sensor data for the specified part.
                   - Fingers: Returns 16 data points, one per sensor point
                   - Palm: Returns 25 data points, one per 3 sensor points
                   - Dorsum: Returns 25 data points, one per 4 sensor points

    Note:
        Data unit: 1g, Max value: 255g, Sampling frequency: 10Hz
    """
```

**Sensor Specifications:**
- Data unit: 1g
- Max value: 255g
- Sampling frequency: 10Hz

**Return Data Description:**
| Part | Data Length | Description |
| ---- | ----------- | ----------- |
| Fingers | 16 | One data point per sensor |
| Palm | 25 | One data point per 3 sensors |
| Dorsum | 25 | One data point per 4 sensors |

The 16 sensors on a finger are arranged as follows:

![](../pic/tactile_sensor_array.jpg)

### Control Mode

```python
def set_control_mode(self, joint_motor_index: int, mode: int) -> None:
    """Sets the control mode of a single joint motor.

    Args:
        joint_motor_index: The index of the joint motor (1-10).
        mode: The control mode enum value.
    """

def get_control_mode(self, joint_motor_index: int) -> int:
    """Gets the control mode of a single joint motor.

    Args:
        joint_motor_index: The index of the joint motor (1-10).

    Returns:
        int: The current control mode.

    Note:
        This interface is not supported for serial port communication.
    """

def set_all_control_modes(self, ctrl_modes: List[int]) -> None:
    """Sets the control modes of all joint motors in batch.

    Args:
        ctrl_modes: A list of control modes, must have a length of 10.

    Note:
        This interface is not supported for serial port communication.
    """

def get_all_control_modes(self) -> List[int]:
    """Gets the control modes of all joint motors in batch.

    Returns:
        List[int]: A list of control modes, with a length of 10.

    Note:
        This interface is not supported for serial port communication.
    """
```

### Current Threshold Control

```python
def set_current_threshold(self, joint_motor_index: int, current_threshold: int) -> None:
    """Sets the current threshold of a single joint motor.

    Args:
        joint_motor_index: The index of the joint motor (1-10).
        current_threshold: The current threshold value.

    Note:
        This interface is not supported for serial port communication.
    """

def get_current_threshold(self, joint_motor_index: int) -> int:
    """Gets the current threshold of a single joint motor.

    Args:
        joint_motor_index: The index of the joint motor (1-10).

    Returns:
        int: The current threshold value. Returns -1 on failure.

    Note:
        This interface is not supported for serial port communication.
    """

def set_all_current_thresholds(self, current_thresholds: List[int]) -> None:
    """Sets the current thresholds of all joint motors in batch.

    Args:
        current_thresholds: A list of current thresholds, must have a length of 10.

    Note:
        This interface is not supported for serial port communication.
    """

def get_all_current_thresholds(self) -> List[int]:
    """Gets the current thresholds of all joint motors in batch.

    Returns:
        List[int]: A list of current thresholds, with a length of 10.

    Note:
        This interface is not supported for serial port communication.
    """
```

### Mixed Control

```python
def mix_ctrl_joint_motor(self, mix_ctrls: List[MixCtrl]) -> None:
    """Controls joint motors in mixed mode.

    Args:
        mix_ctrls: A list of mixed control parameters.

    Note:
        This interface is not supported for serial port communication.
    """
```

### Error Handling

```python
def get_error_report(self, joint_motor_index: int) -> JointMotorErrorReport:
    """Gets the error report for a single joint motor.

    Args:
        joint_motor_index: The index of the joint motor (1-10).

    Returns:
        JointMotorErrorReport: The error report structure.
    """

def get_all_error_reports(self) -> List[JointMotorErrorReport]:
    """Gets the error reports for all joint motors.

    Returns:
        List[JointMotorErrorReport]: A list of error reports, with a length of 10.
    """
```

### Temperature Monitoring

```python
def get_temperature_report(self, joint_motor_index: int) -> int:
    """Gets the temperature report for a single joint motor.

    Note:
        The reporting period must be set before querying.

    Args:
        joint_motor_index: The index of the joint motor (1-10).

    Returns:
        int: The current temperature value. Returns -1 on failure.
    """

def get_all_temperature_reports(self) -> List[int]:
    """Gets the temperature reports for all joint motors.

    Note:
        The reporting period must be set before querying.

    Returns:
        List[int]: A list of temperature values, with a length of 10.
    """
```

### Current Monitoring

```python
def get_current_report(self, joint_motor_index: int) -> int:
    """Gets the current report for a single joint motor.

    Note:
        The reporting period must be set before querying.

    Args:
        joint_motor_index: The index of the joint motor (1-10).

    Returns:
        int: The current value. Returns -1 on failure.
    """

def get_all_current_reports(self) -> List[int]:
    """Gets the current reports for all joint motors.

    Note:
        The reporting period must be set before querying.

    Returns:
        List[int]: A list of current values, with a length of 10.
    """
```

### Debugging Features

```python
def show_data_details(self, show: bool) -> None:
    """Toggles the display of raw send/receive data details.

    Args:
        show: Whether to show the data details.
    """
```
