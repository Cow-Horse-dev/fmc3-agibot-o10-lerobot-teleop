"""
Python bindings for airbot_hardware GPIO
"""
from __future__ import annotations
import collections.abc
import typing
__all__: list[str] = ['ArmParams', 'AsioExecutor', 'BLUE_BREATHING', 'BLUE_CONSTANT', 'BLUE_FLASHING', 'BLUE_MOVEOFF', 'BLUE_MOVEON', 'BLUE_WAVE', 'ButtonState', 'CSP', 'CSPReq', 'CSV', 'CSVReq', 'CYAN_BREATHING', 'CYAN_CONSTANT', 'CYAN_FLASHING', 'CYAN_MOVEOFF', 'CYAN_MOVEON', 'CYAN_WAVE', 'CanCommHandler', 'CanFilter', 'CanFrame', 'DM', 'DOUBLE_CLICKED', 'DexterousHand', 'DexterousHandTypes', 'DisableReq', 'E2', 'EC', 'EEF0', 'EEF1', 'EEFCommand0', 'EEFCommand1', 'EEFState0', 'EEFState1', 'EEFType', 'EnableReq', 'FLAGS', 'FLAGS_FLOAT', 'FLOAT32_BE', 'FLOAT32_LE', 'FrameParser', 'FrameType', 'G2', 'GPIO', 'GPIOType', 'GREEN_BREATHING', 'GREEN_CONSTANT', 'GREEN_FLASHING', 'GREEN_MOVEOFF', 'GREEN_MOVEON', 'GREEN_WAVE', 'GetParamReq', 'GetParamResp', 'HandState', 'IDLE', 'INS_RH56DFTP', 'INS_RH56DFX', 'INT16_BE', 'INT16_LE', 'INT32_BE', 'INT32_LE', 'INT8_BE', 'INT8_LE', 'INVALID', 'InputEvent', 'KeyboardCommHandler', 'LEDCmd', 'LEDCmdResp', 'LONG_PRESSED', 'LightEffect', 'MIT', 'MITReq', 'MotionCmdResp', 'Motor', 'MotorCommand', 'MotorControlMode', 'MotorName', 'MotorParams', 'MotorState', 'MotorType', 'NA', 'NONE', 'OD', 'ODM', 'ORANGE_BREATHING', 'ORANGE_CONSTANT', 'ORANGE_FLASHING', 'ORANGE_MOVEOFF', 'ORANGE_MOVEON', 'ORANGE_WAVE', 'PLAY_BASE_BOARD', 'PLAY_END_BOARD', 'PRESSED', 'PURPLE_BREATHING', 'PURPLE_CONSTANT', 'PURPLE_FLASHING', 'PURPLE_MOVEOFF', 'PURPLE_MOVEON', 'PURPLE_WAVE', 'PVT', 'PVTReq', 'ParamBuilder', 'ParamType', 'ParamValue', 'PersistParamReq', 'PersistParamResp', 'PingReq', 'Play', 'PlayState', 'PlayWithEEF', 'PlayWithEEFState', 'RAINBOW_WAVE', 'RED_BREATHING', 'RED_CONSTANT', 'RED_FLASHING', 'RED_MOVEOFF', 'RED_MOVEON', 'RED_WAVE', 'REPLAY_BASE_BOARD', 'ResetErrReq', 'STRING', 'SerialCommHandler128', 'SerialCommHandler16', 'SerialCommHandler32', 'SerialCommHandler64', 'SerialCommHandler8', 'SerialFrame128', 'SerialFrame16', 'SerialFrame32', 'SerialFrame64', 'SerialFrame8', 'SetParamReq', 'SetParamResp', 'SetZeroReq', 'Stub', 'TTYCommHandler', 'UINT16_BE', 'UINT16_LE', 'UINT32_BE', 'UINT32_LE', 'UINT8_BE', 'UINT8_LE', 'UINT8x4', 'UNTOUCHED', 'Void', 'WHITE_BREATHING', 'WHITE_CONSTANT', 'WHITE_FLASHING', 'WHITE_MOVEOFF', 'WHITE_MOVEON', 'WHITE_WAVE', 'YELLOW_BREATHING', 'YELLOW_CONSTANT', 'YELLOW_FLASHING', 'YELLOW_MOVEOFF', 'YELLOW_MOVEON', 'YELLOW_WAVE', 'create_asio_executor', 'create_dexterous_hand', 'create_serial_comm_handler', 'make_can_frame_ptr', 'make_input_event_ptr', 'make_serial_frame128_ptr', 'make_serial_frame16_ptr', 'make_serial_frame32_ptr', 'make_serial_frame64_ptr', 'make_serial_frame_ptr', 'param_value_from_array', 'unpack_parse_result']
class ArmParams:
    def __bool__(self: collections.abc.Mapping[str, ParamValue]) -> bool:
        """
        Check whether the map is nonempty
        """
    @typing.overload
    def __contains__(self: collections.abc.Mapping[str, ParamValue], arg0: str) -> bool:
        ...
    @typing.overload
    def __contains__(self: collections.abc.Mapping[str, ParamValue], arg0: typing.Any) -> bool:
        ...
    def __delitem__(self: collections.abc.Mapping[str, ParamValue], arg0: str) -> None:
        ...
    def __getitem__(self: collections.abc.Mapping[str, ParamValue], arg0: str) -> ParamValue:
        ...
    def __init__(self) -> None:
        ...
    def __iter__(self: collections.abc.Mapping[str, ParamValue]) -> collections.abc.Iterator[str]:
        ...
    def __len__(self: collections.abc.Mapping[str, ParamValue]) -> int:
        ...
    def __setitem__(self: collections.abc.Mapping[str, ParamValue], arg0: str, arg1: ParamValue) -> None:
        ...
    def items(self: collections.abc.Mapping[str, ParamValue]) -> typing.ItemsView:
        ...
    def keys(self: collections.abc.Mapping[str, ParamValue]) -> typing.KeysView:
        ...
    def values(self: collections.abc.Mapping[str, ParamValue]) -> typing.ValuesView:
        ...
class AsioExecutor:
    @staticmethod
    def create(thread_count: typing.SupportsInt) -> AsioExecutor:
        """
        Create an AsioExecutor with the specified number of worker threads (1-12).
        """
    def get_io_context(self) -> Stub:
        """
        Get the shared io_context pointer.
        """
class ButtonState:
    """
    Members:
    
      IDLE
    
      PRESSED
    
      LONG_PRESSED
    
      DOUBLE_CLICKED
    """
    DOUBLE_CLICKED: typing.ClassVar[ButtonState]  # value = <ButtonState.DOUBLE_CLICKED: 3>
    IDLE: typing.ClassVar[ButtonState]  # value = <ButtonState.IDLE: 0>
    LONG_PRESSED: typing.ClassVar[ButtonState]  # value = <ButtonState.LONG_PRESSED: 2>
    PRESSED: typing.ClassVar[ButtonState]  # value = <ButtonState.PRESSED: 1>
    __members__: typing.ClassVar[dict[str, ButtonState]]  # value = {'IDLE': <ButtonState.IDLE: 0>, 'PRESSED': <ButtonState.PRESSED: 1>, 'LONG_PRESSED': <ButtonState.LONG_PRESSED: 2>, 'DOUBLE_CLICKED': <ButtonState.DOUBLE_CLICKED: 3>}
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class CanCommHandler:
    @staticmethod
    def create(name: str, type: str, interface: str, spin_freq: typing.SupportsInt, io_context: typing.Any) -> CanCommHandler:
        """
        Create a CAN communication handler.
        """
    def add_read_callback(self, name: str, callback: collections.abc.Callable) -> None:
        """
        Add a read callback for incoming CAN frames.
        """
    def delete_read_callback(self, name: str) -> None:
        """
        Delete a previously-registered read callback.
        """
    def start(self) -> bool:
        """
        Start the communication handler.
        """
    def stop(self) -> bool:
        """
        Stop the communication handler.
        """
    def write(self, frame: CanFrame) -> bool:
        """
        Write a CAN frame.
        """
    def write_strong(self, frame: CanFrame) -> bool:
        """
        Write a CAN frame with strong semantics.
        """
    def write_weak(self, frame: CanFrame) -> bool:
        """
        Write a CAN frame with weak semantics.
        """
class CanFilter:
    def __init__(self) -> None:
        """
        Default‐construct a CAN filter.
        """
    @property
    def can_id(self) -> int:
        """
        Filter CAN ID.
        """
    @can_id.setter
    def can_id(self, arg0: typing.SupportsInt) -> None:
        ...
    @property
    def can_mask(self) -> int:
        """
        Filter CAN mask.
        """
    @can_mask.setter
    def can_mask(self, arg0: typing.SupportsInt) -> None:
        ...
class CanFrame:
    data: bytes
    def __init__(self) -> None:
        ...
    def __repr__(self) -> str:
        ...
    @property
    def can_dlc(self) -> int:
        ...
    @can_dlc.setter
    def can_dlc(self, arg0: typing.SupportsInt) -> None:
        ...
    @property
    def can_id(self) -> int:
        ...
    @can_id.setter
    def can_id(self, arg0: typing.SupportsInt) -> None:
        ...
class DexterousHand:
    @staticmethod
    def create(id: typing.SupportsInt, type: DexterousHandTypes) -> DexterousHand:
        """
        Create a DexterousHand instance with given ID and type.
        """
    def init(self, io_context: Stub, interface: str, spin_freq: typing.SupportsInt) -> bool:
        """
        Initialize the dexterous hand.
        """
    def params(self) -> dict[str, ParamValue]:
        """
        Return parameter map.
        """
    def set_force(self, cmd: HandState) -> bool:
        """
        Set hand force command.
        """
    def set_param(self, name: str, value: ParamValue) -> bool:
        """
        Set parameter by name.
        """
    def set_pos(self, cmd: HandState) -> bool:
        """
        Set hand position command.
        """
    def state(self) -> HandState:
        """
        Get latest cached hand state.
        """
    def type(self) -> DexterousHandTypes:
        """
        Get hand type.
        """
    def uninit(self) -> bool:
        """
        Uninitialize the dexterous hand.
        """
    def update_param(self, name: str) -> bool:
        """
        Request parameter update.
        """
    def update_state(self) -> bool:
        """
        Update hand state from hardware.
        """
class DexterousHandTypes:
    """
    Members:
    
      INS_RH56DFX
    
      INS_RH56BFX
    
      INS_RH56E2
    
      INS_RH56F1
    
      BRAINCO_REVO1
    
      BRAINCO_REVO2
    
      ROH_LITES001
    
      ROH_A002
    """
    BRAINCO_REVO1: typing.ClassVar[DexterousHandTypes]  # value = <DexterousHandTypes.BRAINCO_REVO1: 32>
    BRAINCO_REVO2: typing.ClassVar[DexterousHandTypes]  # value = <DexterousHandTypes.BRAINCO_REVO2: 33>
    INS_RH56BFX: typing.ClassVar[DexterousHandTypes]  # value = <DexterousHandTypes.INS_RH56BFX: 1>
    INS_RH56DFX: typing.ClassVar[DexterousHandTypes]  # value = <DexterousHandTypes.INS_RH56DFX: 0>
    INS_RH56E2: typing.ClassVar[DexterousHandTypes]  # value = <DexterousHandTypes.INS_RH56E2: 2>
    INS_RH56F1: typing.ClassVar[DexterousHandTypes]  # value = <DexterousHandTypes.INS_RH56F1: 3>
    ROH_A002: typing.ClassVar[DexterousHandTypes]  # value = <DexterousHandTypes.ROH_A002: 65>
    ROH_LITES001: typing.ClassVar[DexterousHandTypes]  # value = <DexterousHandTypes.ROH_LITES001: 64>
    __members__: typing.ClassVar[dict[str, DexterousHandTypes]]  # value = {'INS_RH56DFX': <DexterousHandTypes.INS_RH56DFX: 0>, 'INS_RH56BFX': <DexterousHandTypes.INS_RH56BFX: 1>, 'INS_RH56E2': <DexterousHandTypes.INS_RH56E2: 2>, 'INS_RH56F1': <DexterousHandTypes.INS_RH56F1: 3>, 'BRAINCO_REVO1': <DexterousHandTypes.BRAINCO_REVO1: 32>, 'BRAINCO_REVO2': <DexterousHandTypes.BRAINCO_REVO2: 33>, 'ROH_LITES001': <DexterousHandTypes.ROH_LITES001: 64>, 'ROH_A002': <DexterousHandTypes.ROH_A002: 65>}
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class EEF0:
    @staticmethod
    def create(eef_type: EEFType, motor_type: MotorType) -> EEF0:
        """
                Create a null EEF (0 DOF).
                Valid configurations are:
                  • (EEFType.NA, MotorType.NA)
                Returns a std::unique_ptr<EEF<0>>, or nullptr if unsupported.
        """
    def disable(self) -> bool:
        """
        Disable the EEF.
        """
    def enable(self) -> bool:
        """
        Enable the EEF.
        """
    def get_param(self, name: str) -> bool:
        """
        Request a parameter value by name.
        """
    def init(self, io_context: Stub, interface: str, spin_freq: typing.SupportsInt) -> bool:
        """
        Initialize the EEF with IO context, interface name, and spin frequency.
        """
    def mit(self, cmd: EEFCommand0) -> bool:
        """
        Send a MIT command to the EEF.
        """
    def params(self) -> dict[str, ParamValue]:
        """
        Get the EEF parameters (returns MotorParams).
        """
    def persist_param(self, name: str, value: ParamValue) -> bool:
        """
        Persist a parameter value by name.
        """
    def ping(self) -> bool:
        """
        Ping the EEF to get latest state.
        """
    def pvt(self, cmd: EEFCommand0) -> bool:
        """
        Send a PVT command to the EEF.
        """
    def reset_error(self) -> bool:
        """
        Reset EEF error state.
        """
    @typing.overload
    def set_param(self, name: str, value: ParamValue) -> bool:
        """
        Set a parameter value by name.
        """
    @typing.overload
    def set_param(self, name: str, value: MotorControlMode) -> bool:
        """
        Set a parameter value by name (MotorControlMode overload).
        """
    def set_zero(self) -> bool:
        """
        Set the EEF position reference to zero.
        """
    def state(self) -> EEFState0:
        """
        Get the current EEFState.
        """
    def uninit(self) -> bool:
        """
        Uninitialize the EEF and clean up resources.
        """
class EEF1:
    @staticmethod
    def create(eef_type: EEFType, motor_type: MotorType) -> EEF1:
        """
                Create a single DOF EEF.
                Valid configurations are:
                  • (EEFType.G2, MotorType.DM)
                  • (EEFType.G2, MotorType.ODM)
                Returns a std::unique_ptr<EEF<1>>, or nullptr if unsupported.
        """
    def disable(self) -> bool:
        """
        Disable the EEF.
        """
    def enable(self) -> bool:
        """
        Enable the EEF.
        """
    def get_param(self, name: str) -> bool:
        """
        Request a parameter value by name.
        """
    def init(self, io_context: Stub, interface: str, spin_freq: typing.SupportsInt) -> bool:
        """
        Initialize the EEF with IO context, interface name, and spin frequency.
        """
    def mit(self, cmd: EEFCommand1) -> bool:
        """
        Send a MIT command to the EEF.
        """
    def params(self) -> dict[str, ParamValue]:
        """
        Get the EEF parameters (returns MotorParams).
        """
    def persist_param(self, name: str, value: ParamValue) -> bool:
        """
        Persist a parameter value by name.
        """
    def ping(self) -> bool:
        """
        Ping the EEF to get latest state.
        """
    def pvt(self, cmd: EEFCommand1) -> bool:
        """
        Send a PVT command to the EEF.
        """
    def reset_error(self) -> bool:
        """
        Reset EEF error state.
        """
    @typing.overload
    def set_param(self, name: str, value: ParamValue) -> bool:
        """
        Set a parameter value by name.
        """
    @typing.overload
    def set_param(self, name: str, value: MotorControlMode) -> bool:
        """
        Set a parameter value by name (MotorControlMode overload).
        """
    def set_zero(self) -> bool:
        """
        Set the EEF position reference to zero.
        """
    def state(self) -> EEFState1:
        """
        Get the current EEFState.
        """
    def uninit(self) -> bool:
        """
        Uninitialize the EEF and clean up resources.
        """
class EEFCommand0:
    def __init__(self) -> None:
        ...
    @property
    def current_threshold(self) -> typing.Annotated[list[float], "FixedSize(0)"]:
        ...
    @current_threshold.setter
    def current_threshold(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(0)"]) -> None:
        ...
    @property
    def eff(self) -> typing.Annotated[list[float], "FixedSize(0)"]:
        ...
    @eff.setter
    def eff(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(0)"]) -> None:
        ...
    @property
    def mit_kd(self) -> typing.Annotated[list[float], "FixedSize(0)"]:
        ...
    @mit_kd.setter
    def mit_kd(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(0)"]) -> None:
        ...
    @property
    def mit_kp(self) -> typing.Annotated[list[float], "FixedSize(0)"]:
        ...
    @mit_kp.setter
    def mit_kp(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(0)"]) -> None:
        ...
    @property
    def pos(self) -> typing.Annotated[list[float], "FixedSize(0)"]:
        ...
    @pos.setter
    def pos(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(0)"]) -> None:
        ...
    @property
    def vel(self) -> typing.Annotated[list[float], "FixedSize(0)"]:
        ...
    @vel.setter
    def vel(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(0)"]) -> None:
        ...
class EEFCommand1:
    def __init__(self) -> None:
        ...
    @property
    def current_threshold(self) -> typing.Annotated[list[float], "FixedSize(1)"]:
        ...
    @current_threshold.setter
    def current_threshold(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(1)"]) -> None:
        ...
    @property
    def eff(self) -> typing.Annotated[list[float], "FixedSize(1)"]:
        ...
    @eff.setter
    def eff(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(1)"]) -> None:
        ...
    @property
    def mit_kd(self) -> typing.Annotated[list[float], "FixedSize(1)"]:
        ...
    @mit_kd.setter
    def mit_kd(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(1)"]) -> None:
        ...
    @property
    def mit_kp(self) -> typing.Annotated[list[float], "FixedSize(1)"]:
        ...
    @mit_kp.setter
    def mit_kp(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(1)"]) -> None:
        ...
    @property
    def pos(self) -> typing.Annotated[list[float], "FixedSize(1)"]:
        ...
    @pos.setter
    def pos(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(1)"]) -> None:
        ...
    @property
    def vel(self) -> typing.Annotated[list[float], "FixedSize(1)"]:
        ...
    @vel.setter
    def vel(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(1)"]) -> None:
        ...
class EEFState0:
    is_valid: bool
    def __init__(self) -> None:
        ...
    def format(self) -> str:
        ...
    @property
    def eff(self) -> typing.Annotated[list[float], "FixedSize(0)"]:
        ...
    @eff.setter
    def eff(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(0)"]) -> None:
        ...
    @property
    def error_id(self) -> typing.Annotated[list[int], "FixedSize(0)"]:
        ...
    @error_id.setter
    def error_id(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsInt], "FixedSize(0)"]) -> None:
        ...
    @property
    def joint_id(self) -> typing.Annotated[list[int], "FixedSize(0)"]:
        ...
    @joint_id.setter
    def joint_id(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsInt], "FixedSize(0)"]) -> None:
        ...
    @property
    def mos_temp(self) -> typing.Annotated[list[float], "FixedSize(0)"]:
        ...
    @mos_temp.setter
    def mos_temp(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(0)"]) -> None:
        ...
    @property
    def motor_temp(self) -> typing.Annotated[list[float], "FixedSize(0)"]:
        ...
    @motor_temp.setter
    def motor_temp(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(0)"]) -> None:
        ...
    @property
    def pos(self) -> typing.Annotated[list[float], "FixedSize(0)"]:
        ...
    @pos.setter
    def pos(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(0)"]) -> None:
        ...
    @property
    def vel(self) -> typing.Annotated[list[float], "FixedSize(0)"]:
        ...
    @vel.setter
    def vel(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(0)"]) -> None:
        ...
class EEFState1:
    is_valid: bool
    def __init__(self) -> None:
        ...
    def format(self) -> str:
        ...
    @property
    def eff(self) -> typing.Annotated[list[float], "FixedSize(1)"]:
        ...
    @eff.setter
    def eff(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(1)"]) -> None:
        ...
    @property
    def error_id(self) -> typing.Annotated[list[int], "FixedSize(1)"]:
        ...
    @error_id.setter
    def error_id(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsInt], "FixedSize(1)"]) -> None:
        ...
    @property
    def joint_id(self) -> typing.Annotated[list[int], "FixedSize(1)"]:
        ...
    @joint_id.setter
    def joint_id(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsInt], "FixedSize(1)"]) -> None:
        ...
    @property
    def mos_temp(self) -> typing.Annotated[list[float], "FixedSize(1)"]:
        ...
    @mos_temp.setter
    def mos_temp(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(1)"]) -> None:
        ...
    @property
    def motor_temp(self) -> typing.Annotated[list[float], "FixedSize(1)"]:
        ...
    @motor_temp.setter
    def motor_temp(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(1)"]) -> None:
        ...
    @property
    def pos(self) -> typing.Annotated[list[float], "FixedSize(1)"]:
        ...
    @pos.setter
    def pos(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(1)"]) -> None:
        ...
    @property
    def vel(self) -> typing.Annotated[list[float], "FixedSize(1)"]:
        ...
    @vel.setter
    def vel(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(1)"]) -> None:
        ...
class EEFType:
    """
    Members:
    
      NA
    
      G2
    
      E2
    
      INS_RH56DFX
    
      INS_RH56DFTP
    """
    E2: typing.ClassVar[EEFType]  # value = <EEFType.E2: 2>
    G2: typing.ClassVar[EEFType]  # value = <EEFType.G2: 1>
    INS_RH56DFTP: typing.ClassVar[EEFType]  # value = <EEFType.INS_RH56DFTP: 4>
    INS_RH56DFX: typing.ClassVar[EEFType]  # value = <EEFType.INS_RH56DFX: 3>
    NA: typing.ClassVar[EEFType]  # value = <EEFType.NA: 0>
    __members__: typing.ClassVar[dict[str, EEFType]]  # value = {'NA': <EEFType.NA: 0>, 'G2': <EEFType.G2: 1>, 'E2': <EEFType.E2: 2>, 'INS_RH56DFX': <EEFType.INS_RH56DFX: 3>, 'INS_RH56DFTP': <EEFType.INS_RH56DFTP: 4>}
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class FrameParser:
    def __init__(self) -> None:
        ...
    @typing.overload
    def generate(self, type: FrameType, cmd: MotorCommand) -> list[CanFrame]:
        """
        Generate a frame from a motor command.
        """
    @typing.overload
    def generate(self, type: FrameType, name: str, value: ParamValue) -> list[CanFrame]:
        """
        Generate a frame for parameter operations.
        """
    @typing.overload
    def generate(self, type: FrameType) -> list[CanFrame]:
        """
        Generate a frame for ping/enable/disable operations.
        """
    def params(self) -> list[ParamBuilder]:
        """
        Return a vector of ParamBuilder for this motor.
        """
    def parse(self, frame: CanFrame) -> tuple[FrameType, MotorState, dict[str, ParamValue]]:
        """
        Parse a frame and return a ParseResult.
        """
class FrameType:
    """
    Members:
    
      CSPReq
    
      CSVReq
    
      MITReq
    
      PVTReq
    
      GetParamReq
    
      SetParamReq
    
      PersistParamReq
    
      PingReq
    
      EnableReq
    
      DisableReq
    
      SetZeroReq
    
      ResetErrReq
    
      MotionCmdResp
    
      GetParamResp
    
      SetParamResp
    
      PersistParamResp
    
      Void
    
      LEDCmd
    
      LEDCmdResp
    """
    CSPReq: typing.ClassVar[FrameType]  # value = <FrameType.CSPReq: 0>
    CSVReq: typing.ClassVar[FrameType]  # value = <FrameType.CSVReq: 1>
    DisableReq: typing.ClassVar[FrameType]  # value = <FrameType.DisableReq: 9>
    EnableReq: typing.ClassVar[FrameType]  # value = <FrameType.EnableReq: 8>
    GetParamReq: typing.ClassVar[FrameType]  # value = <FrameType.GetParamReq: 4>
    GetParamResp: typing.ClassVar[FrameType]  # value = <FrameType.GetParamResp: 17>
    LEDCmd: typing.ClassVar[FrameType]  # value = <FrameType.LEDCmd: 32>
    LEDCmdResp: typing.ClassVar[FrameType]  # value = <FrameType.LEDCmdResp: 33>
    MITReq: typing.ClassVar[FrameType]  # value = <FrameType.MITReq: 2>
    MotionCmdResp: typing.ClassVar[FrameType]  # value = <FrameType.MotionCmdResp: 16>
    PVTReq: typing.ClassVar[FrameType]  # value = <FrameType.PVTReq: 3>
    PersistParamReq: typing.ClassVar[FrameType]  # value = <FrameType.PersistParamReq: 6>
    PersistParamResp: typing.ClassVar[FrameType]  # value = <FrameType.PersistParamResp: 19>
    PingReq: typing.ClassVar[FrameType]  # value = <FrameType.PingReq: 7>
    ResetErrReq: typing.ClassVar[FrameType]  # value = <FrameType.ResetErrReq: 11>
    SetParamReq: typing.ClassVar[FrameType]  # value = <FrameType.SetParamReq: 5>
    SetParamResp: typing.ClassVar[FrameType]  # value = <FrameType.SetParamResp: 18>
    SetZeroReq: typing.ClassVar[FrameType]  # value = <FrameType.SetZeroReq: 10>
    Void: typing.ClassVar[FrameType]  # value = <FrameType.Void: 255>
    __members__: typing.ClassVar[dict[str, FrameType]]  # value = {'CSPReq': <FrameType.CSPReq: 0>, 'CSVReq': <FrameType.CSVReq: 1>, 'MITReq': <FrameType.MITReq: 2>, 'PVTReq': <FrameType.PVTReq: 3>, 'GetParamReq': <FrameType.GetParamReq: 4>, 'SetParamReq': <FrameType.SetParamReq: 5>, 'PersistParamReq': <FrameType.PersistParamReq: 6>, 'PingReq': <FrameType.PingReq: 7>, 'EnableReq': <FrameType.EnableReq: 8>, 'DisableReq': <FrameType.DisableReq: 9>, 'SetZeroReq': <FrameType.SetZeroReq: 10>, 'ResetErrReq': <FrameType.ResetErrReq: 11>, 'MotionCmdResp': <FrameType.MotionCmdResp: 16>, 'GetParamResp': <FrameType.GetParamResp: 17>, 'SetParamResp': <FrameType.SetParamResp: 18>, 'PersistParamResp': <FrameType.PersistParamResp: 19>, 'Void': <FrameType.Void: 255>, 'LEDCmd': <FrameType.LEDCmd: 32>, 'LEDCmdResp': <FrameType.LEDCmdResp: 33>}
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class GPIO:
    @staticmethod
    def create(type: GPIOType) -> GPIO:
        """
        Create a GPIO instance
        """
    def add_callback(self, name: str, param_name: str, callback: collections.abc.Callable[[ParamValue], None]) -> bool:
        """
        Add a callback to the GPIO
        """
    def get_param(self, name: str) -> bool:
        """
        Get a parameter value from the GPIO
        """
    def init(self, io_context: Stub, interface: str, spin_freq: typing.SupportsInt) -> bool:
        """
        Initialize the GPIO
        """
    def params(self) -> dict[str, ParamValue]:
        """
        Get the parameters of the GPIO
        """
    def persist_param(self, name: str, value: ParamValue) -> bool:
        """
        Persist a parameter value to the GPIO
        """
    def remove_callback(self, name: str, param_name: str) -> bool:
        """
        Remove a callback from the GPIO
        """
    def set_param(self, name: str, value: ParamValue) -> bool:
        """
        Set a parameter value to the GPIO
        """
    def uninit(self) -> bool:
        """
        Uninitialize the GPIO
        """
class GPIOType:
    """
    Members:
    
      NONE
    
      PLAY_BASE_BOARD
    
      PLAY_END_BOARD
    
      REPLAY_BASE_BOARD
    """
    NONE: typing.ClassVar[GPIOType]  # value = <GPIOType.NONE: 0>
    PLAY_BASE_BOARD: typing.ClassVar[GPIOType]  # value = <GPIOType.PLAY_BASE_BOARD: 16>
    PLAY_END_BOARD: typing.ClassVar[GPIOType]  # value = <GPIOType.PLAY_END_BOARD: 17>
    REPLAY_BASE_BOARD: typing.ClassVar[GPIOType]  # value = <GPIOType.REPLAY_BASE_BOARD: 18>
    __members__: typing.ClassVar[dict[str, GPIOType]]  # value = {'NONE': <GPIOType.NONE: 0>, 'PLAY_BASE_BOARD': <GPIOType.PLAY_BASE_BOARD: 16>, 'PLAY_END_BOARD': <GPIOType.PLAY_END_BOARD: 17>, 'REPLAY_BASE_BOARD': <GPIOType.REPLAY_BASE_BOARD: 18>}
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class HandState:
    @staticmethod
    def names() -> typing.Annotated[list[MotorName], "FixedSize(6)"]:
        """
        Motor order list
        """
    def __init__(self) -> None:
        ...
    @property
    def forces(self) -> typing.Annotated[list[int], "FixedSize(6)"]:
        """
        Force feedback (mN)
        """
    @forces.setter
    def forces(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsInt], "FixedSize(6)"]) -> None:
        ...
    @property
    def positions(self) -> typing.Annotated[list[int], "FixedSize(6)"]:
        """
        Finger joint positions [0~1000]
        """
    @positions.setter
    def positions(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsInt], "FixedSize(6)"]) -> None:
        ...
    @property
    def velocities(self) -> typing.Annotated[list[int], "FixedSize(6)"]:
        """
        Finger velocities [-1000~1000]
        """
    @velocities.setter
    def velocities(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsInt], "FixedSize(6)"]) -> None:
        ...
class InputEvent:
    def __init__(self) -> None:
        """
        Default‐construct an empty input event.
        """
    @property
    def code(self) -> int:
        """
        Event code.
        """
    @code.setter
    def code(self, arg0: typing.SupportsInt) -> None:
        ...
    @property
    def time(self) -> timeval:
        """
        Event timestamp.
        """
    @time.setter
    def time(self, arg0: timeval) -> None:
        ...
    @property
    def type(self) -> int:
        """
        Event type.
        """
    @type.setter
    def type(self, arg0: typing.SupportsInt) -> None:
        ...
    @property
    def value(self) -> int:
        """
        Event value.
        """
    @value.setter
    def value(self, arg0: typing.SupportsInt) -> None:
        ...
class KeyboardCommHandler:
    @staticmethod
    def create(name: str, type: str, interface: str, spin_freq: typing.SupportsInt, io_context: typing.Any) -> KeyboardCommHandler:
        """
        Create a keyboard communication handler.
        """
    def add_read_callback(self, name: str, callback: collections.abc.Callable) -> None:
        """
        Add a read callback for incoming input events.
        """
    def delete_read_callback(self, name: str) -> None:
        """
        Delete a previously-registered read callback.
        """
    def start(self) -> bool:
        """
        Start the communication handler.
        """
    def stop(self) -> bool:
        """
        Stop the communication handler.
        """
    def write(self, frame: InputEvent) -> bool:
        """
        Write an input event.
        """
    def write_strong(self, frame: InputEvent) -> bool:
        """
        Write an input event with strong semantics.
        """
    def write_weak(self, frame: InputEvent) -> bool:
        """
        Write an input event with weak semantics.
        """
class LightEffect:
    """
    Members:
    
      NONE
    
      RED_CONSTANT
    
      ORANGE_CONSTANT
    
      YELLOW_CONSTANT
    
      GREEN_CONSTANT
    
      CYAN_CONSTANT
    
      BLUE_CONSTANT
    
      PURPLE_CONSTANT
    
      WHITE_CONSTANT
    
      RED_BREATHING
    
      ORANGE_BREATHING
    
      YELLOW_BREATHING
    
      GREEN_BREATHING
    
      CYAN_BREATHING
    
      BLUE_BREATHING
    
      PURPLE_BREATHING
    
      WHITE_BREATHING
    
      RED_FLASHING
    
      ORANGE_FLASHING
    
      YELLOW_FLASHING
    
      GREEN_FLASHING
    
      CYAN_FLASHING
    
      BLUE_FLASHING
    
      PURPLE_FLASHING
    
      WHITE_FLASHING
    
      RED_WAVE
    
      ORANGE_WAVE
    
      YELLOW_WAVE
    
      GREEN_WAVE
    
      CYAN_WAVE
    
      BLUE_WAVE
    
      PURPLE_WAVE
    
      WHITE_WAVE
    
      RED_MOVEON
    
      ORANGE_MOVEON
    
      YELLOW_MOVEON
    
      GREEN_MOVEON
    
      CYAN_MOVEON
    
      BLUE_MOVEON
    
      PURPLE_MOVEON
    
      WHITE_MOVEON
    
      RED_MOVEOFF
    
      ORANGE_MOVEOFF
    
      YELLOW_MOVEOFF
    
      GREEN_MOVEOFF
    
      CYAN_MOVEOFF
    
      BLUE_MOVEOFF
    
      PURPLE_MOVEOFF
    
      WHITE_MOVEOFF
    
      RAINBOW_WAVE
    """
    BLUE_BREATHING: typing.ClassVar[LightEffect]  # value = <LightEffect.BLUE_BREATHING: 22>
    BLUE_CONSTANT: typing.ClassVar[LightEffect]  # value = <LightEffect.BLUE_CONSTANT: 6>
    BLUE_FLASHING: typing.ClassVar[LightEffect]  # value = <LightEffect.BLUE_FLASHING: 38>
    BLUE_MOVEOFF: typing.ClassVar[LightEffect]  # value = <LightEffect.BLUE_MOVEOFF: 86>
    BLUE_MOVEON: typing.ClassVar[LightEffect]  # value = <LightEffect.BLUE_MOVEON: 70>
    BLUE_WAVE: typing.ClassVar[LightEffect]  # value = <LightEffect.BLUE_WAVE: 54>
    CYAN_BREATHING: typing.ClassVar[LightEffect]  # value = <LightEffect.CYAN_BREATHING: 21>
    CYAN_CONSTANT: typing.ClassVar[LightEffect]  # value = <LightEffect.CYAN_CONSTANT: 5>
    CYAN_FLASHING: typing.ClassVar[LightEffect]  # value = <LightEffect.CYAN_FLASHING: 37>
    CYAN_MOVEOFF: typing.ClassVar[LightEffect]  # value = <LightEffect.CYAN_MOVEOFF: 85>
    CYAN_MOVEON: typing.ClassVar[LightEffect]  # value = <LightEffect.CYAN_MOVEON: 69>
    CYAN_WAVE: typing.ClassVar[LightEffect]  # value = <LightEffect.CYAN_WAVE: 53>
    GREEN_BREATHING: typing.ClassVar[LightEffect]  # value = <LightEffect.GREEN_BREATHING: 20>
    GREEN_CONSTANT: typing.ClassVar[LightEffect]  # value = <LightEffect.GREEN_CONSTANT: 4>
    GREEN_FLASHING: typing.ClassVar[LightEffect]  # value = <LightEffect.GREEN_FLASHING: 36>
    GREEN_MOVEOFF: typing.ClassVar[LightEffect]  # value = <LightEffect.GREEN_MOVEOFF: 84>
    GREEN_MOVEON: typing.ClassVar[LightEffect]  # value = <LightEffect.GREEN_MOVEON: 68>
    GREEN_WAVE: typing.ClassVar[LightEffect]  # value = <LightEffect.GREEN_WAVE: 52>
    NONE: typing.ClassVar[LightEffect]  # value = <LightEffect.NONE: 0>
    ORANGE_BREATHING: typing.ClassVar[LightEffect]  # value = <LightEffect.ORANGE_BREATHING: 18>
    ORANGE_CONSTANT: typing.ClassVar[LightEffect]  # value = <LightEffect.ORANGE_CONSTANT: 2>
    ORANGE_FLASHING: typing.ClassVar[LightEffect]  # value = <LightEffect.ORANGE_FLASHING: 34>
    ORANGE_MOVEOFF: typing.ClassVar[LightEffect]  # value = <LightEffect.ORANGE_MOVEOFF: 82>
    ORANGE_MOVEON: typing.ClassVar[LightEffect]  # value = <LightEffect.ORANGE_MOVEON: 66>
    ORANGE_WAVE: typing.ClassVar[LightEffect]  # value = <LightEffect.ORANGE_WAVE: 50>
    PURPLE_BREATHING: typing.ClassVar[LightEffect]  # value = <LightEffect.PURPLE_BREATHING: 23>
    PURPLE_CONSTANT: typing.ClassVar[LightEffect]  # value = <LightEffect.PURPLE_CONSTANT: 7>
    PURPLE_FLASHING: typing.ClassVar[LightEffect]  # value = <LightEffect.PURPLE_FLASHING: 39>
    PURPLE_MOVEOFF: typing.ClassVar[LightEffect]  # value = <LightEffect.PURPLE_MOVEOFF: 87>
    PURPLE_MOVEON: typing.ClassVar[LightEffect]  # value = <LightEffect.PURPLE_MOVEON: 71>
    PURPLE_WAVE: typing.ClassVar[LightEffect]  # value = <LightEffect.PURPLE_WAVE: 55>
    RAINBOW_WAVE: typing.ClassVar[LightEffect]  # value = <LightEffect.RAINBOW_WAVE: 255>
    RED_BREATHING: typing.ClassVar[LightEffect]  # value = <LightEffect.RED_BREATHING: 17>
    RED_CONSTANT: typing.ClassVar[LightEffect]  # value = <LightEffect.RED_CONSTANT: 1>
    RED_FLASHING: typing.ClassVar[LightEffect]  # value = <LightEffect.RED_FLASHING: 33>
    RED_MOVEOFF: typing.ClassVar[LightEffect]  # value = <LightEffect.RED_MOVEOFF: 81>
    RED_MOVEON: typing.ClassVar[LightEffect]  # value = <LightEffect.RED_MOVEON: 65>
    RED_WAVE: typing.ClassVar[LightEffect]  # value = <LightEffect.RED_WAVE: 49>
    WHITE_BREATHING: typing.ClassVar[LightEffect]  # value = <LightEffect.WHITE_BREATHING: 31>
    WHITE_CONSTANT: typing.ClassVar[LightEffect]  # value = <LightEffect.WHITE_CONSTANT: 15>
    WHITE_FLASHING: typing.ClassVar[LightEffect]  # value = <LightEffect.WHITE_FLASHING: 47>
    WHITE_MOVEOFF: typing.ClassVar[LightEffect]  # value = <LightEffect.WHITE_MOVEOFF: 95>
    WHITE_MOVEON: typing.ClassVar[LightEffect]  # value = <LightEffect.WHITE_MOVEON: 79>
    WHITE_WAVE: typing.ClassVar[LightEffect]  # value = <LightEffect.WHITE_WAVE: 63>
    YELLOW_BREATHING: typing.ClassVar[LightEffect]  # value = <LightEffect.YELLOW_BREATHING: 19>
    YELLOW_CONSTANT: typing.ClassVar[LightEffect]  # value = <LightEffect.YELLOW_CONSTANT: 3>
    YELLOW_FLASHING: typing.ClassVar[LightEffect]  # value = <LightEffect.YELLOW_FLASHING: 35>
    YELLOW_MOVEOFF: typing.ClassVar[LightEffect]  # value = <LightEffect.YELLOW_MOVEOFF: 83>
    YELLOW_MOVEON: typing.ClassVar[LightEffect]  # value = <LightEffect.YELLOW_MOVEON: 67>
    YELLOW_WAVE: typing.ClassVar[LightEffect]  # value = <LightEffect.YELLOW_WAVE: 51>
    __members__: typing.ClassVar[dict[str, LightEffect]]  # value = {'NONE': <LightEffect.NONE: 0>, 'RED_CONSTANT': <LightEffect.RED_CONSTANT: 1>, 'ORANGE_CONSTANT': <LightEffect.ORANGE_CONSTANT: 2>, 'YELLOW_CONSTANT': <LightEffect.YELLOW_CONSTANT: 3>, 'GREEN_CONSTANT': <LightEffect.GREEN_CONSTANT: 4>, 'CYAN_CONSTANT': <LightEffect.CYAN_CONSTANT: 5>, 'BLUE_CONSTANT': <LightEffect.BLUE_CONSTANT: 6>, 'PURPLE_CONSTANT': <LightEffect.PURPLE_CONSTANT: 7>, 'WHITE_CONSTANT': <LightEffect.WHITE_CONSTANT: 15>, 'RED_BREATHING': <LightEffect.RED_BREATHING: 17>, 'ORANGE_BREATHING': <LightEffect.ORANGE_BREATHING: 18>, 'YELLOW_BREATHING': <LightEffect.YELLOW_BREATHING: 19>, 'GREEN_BREATHING': <LightEffect.GREEN_BREATHING: 20>, 'CYAN_BREATHING': <LightEffect.CYAN_BREATHING: 21>, 'BLUE_BREATHING': <LightEffect.BLUE_BREATHING: 22>, 'PURPLE_BREATHING': <LightEffect.PURPLE_BREATHING: 23>, 'WHITE_BREATHING': <LightEffect.WHITE_BREATHING: 31>, 'RED_FLASHING': <LightEffect.RED_FLASHING: 33>, 'ORANGE_FLASHING': <LightEffect.ORANGE_FLASHING: 34>, 'YELLOW_FLASHING': <LightEffect.YELLOW_FLASHING: 35>, 'GREEN_FLASHING': <LightEffect.GREEN_FLASHING: 36>, 'CYAN_FLASHING': <LightEffect.CYAN_FLASHING: 37>, 'BLUE_FLASHING': <LightEffect.BLUE_FLASHING: 38>, 'PURPLE_FLASHING': <LightEffect.PURPLE_FLASHING: 39>, 'WHITE_FLASHING': <LightEffect.WHITE_FLASHING: 47>, 'RED_WAVE': <LightEffect.RED_WAVE: 49>, 'ORANGE_WAVE': <LightEffect.ORANGE_WAVE: 50>, 'YELLOW_WAVE': <LightEffect.YELLOW_WAVE: 51>, 'GREEN_WAVE': <LightEffect.GREEN_WAVE: 52>, 'CYAN_WAVE': <LightEffect.CYAN_WAVE: 53>, 'BLUE_WAVE': <LightEffect.BLUE_WAVE: 54>, 'PURPLE_WAVE': <LightEffect.PURPLE_WAVE: 55>, 'WHITE_WAVE': <LightEffect.WHITE_WAVE: 63>, 'RED_MOVEON': <LightEffect.RED_MOVEON: 65>, 'ORANGE_MOVEON': <LightEffect.ORANGE_MOVEON: 66>, 'YELLOW_MOVEON': <LightEffect.YELLOW_MOVEON: 67>, 'GREEN_MOVEON': <LightEffect.GREEN_MOVEON: 68>, 'CYAN_MOVEON': <LightEffect.CYAN_MOVEON: 69>, 'BLUE_MOVEON': <LightEffect.BLUE_MOVEON: 70>, 'PURPLE_MOVEON': <LightEffect.PURPLE_MOVEON: 71>, 'WHITE_MOVEON': <LightEffect.WHITE_MOVEON: 79>, 'RED_MOVEOFF': <LightEffect.RED_MOVEOFF: 81>, 'ORANGE_MOVEOFF': <LightEffect.ORANGE_MOVEOFF: 82>, 'YELLOW_MOVEOFF': <LightEffect.YELLOW_MOVEOFF: 83>, 'GREEN_MOVEOFF': <LightEffect.GREEN_MOVEOFF: 84>, 'CYAN_MOVEOFF': <LightEffect.CYAN_MOVEOFF: 85>, 'BLUE_MOVEOFF': <LightEffect.BLUE_MOVEOFF: 86>, 'PURPLE_MOVEOFF': <LightEffect.PURPLE_MOVEOFF: 87>, 'WHITE_MOVEOFF': <LightEffect.WHITE_MOVEOFF: 95>, 'RAINBOW_WAVE': <LightEffect.RAINBOW_WAVE: 255>}
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class Motor:
    @staticmethod
    def create(motor_type: MotorType, motor_id: typing.SupportsInt) -> Motor:
        """
                Create a Motor of the given MotorType and motor ID.
                Valid (motor_type, motor_id) combinations are:
                  • (MotorType.OD, 1), (MotorType.OD, 2), (MotorType.OD, 3), (MotorType.OD, 7)
                  • (MotorType.DM, 4), (MotorType.DM, 5), (MotorType.DM, 6), (MotorType.DM, 7)
                  • (MotorType.ODM, 4), (MotorType.ODM, 5), (MotorType.ODM, 6), (MotorType.ODM, 7)
                  • (MotorType.EC, 1), (MotorType.EC, 2), (MotorType.EC, 3), (MotorType.EC, 4), (MotorType.EC, 5), (MotorType.EC, 6), (MotorType.EC, 7)
                Returns a std::unique_ptr<Motor>, or nullptr if unsupported.
        """
    def csp(self, cmd: MotorCommand) -> bool:
        """
        Send a CSP (cyclic synchronous position) command.
        """
    def csv(self, cmd: MotorCommand) -> bool:
        """
        Send a CSV (cyclic synchronous velocity) command.
        """
    def disable(self) -> bool:
        """
        Disable the motor.
        """
    def enable(self) -> bool:
        """
        Enable the motor.
        """
    def get_param(self, name: str) -> bool:
        """
        Request a parameter value by name.
        """
    def init(self, io_context: Stub, interface: str, spin_freq: typing.SupportsInt) -> bool:
        """
        Initialize the motor with IO context, interface name, and spin frequency.
        """
    def mit(self, cmd: MotorCommand) -> bool:
        """
        Send a MIT (MIT mode) command.
        """
    def params(self) -> dict[str, ParamValue]:
        """
        Get the motor parameters.
        """
    def persist_param(self, name: str, value: ParamValue) -> bool:
        """
        Persist a parameter value by name.
        """
    def ping(self) -> bool:
        """
        Ping the motor to get latest state.
        """
    def pvt(self, cmd: MotorCommand) -> bool:
        """
        Send a PVT (position-velocity-time) command.
        """
    def reset_error(self) -> bool:
        """
        Reset motor error state.
        """
    @typing.overload
    def set_param(self, name: str, value: ParamValue) -> bool:
        """
        Set a parameter value by name.
        """
    @typing.overload
    def set_param(self, name: str, value: MotorControlMode) -> bool:
        """
        Set a parameter value by name (MotorControlMode overload).
        """
    def set_zero(self) -> bool:
        """
        Set the motor position reference to zero.
        """
    def state(self) -> MotorState:
        """
        Get the current MotorState.
        """
    def uninit(self) -> bool:
        """
        Uninitialize the motor and clean up resources.
        """
    def update(self, result: tuple[FrameType, MotorState, collections.abc.Mapping[str, ParamValue]]) -> bool:
        """
        Update the motor state given a ParseResult.
        """
class MotorCommand:
    @typing.overload
    def __init__(self) -> None:
        """
        Default‐construct a MotorCommand (all zeros).
        """
    @typing.overload
    def __init__(self, pos: typing.SupportsFloat = 0.0, vel: typing.SupportsFloat = 0.0, eff: typing.SupportsFloat = 0.0, mit_kp: typing.SupportsFloat = 0.0, mit_kd: typing.SupportsFloat = 0.0, current_threshold: typing.SupportsFloat = 0.0) -> None:
        """
        Construct a MotorCommand with specified parameters.
        """
    @property
    def current_threshold(self) -> float:
        """
        Current threshold (Amps).
        """
    @current_threshold.setter
    def current_threshold(self, arg0: typing.SupportsFloat) -> None:
        ...
    @property
    def eff(self) -> float:
        """
        Target torque (Nm).
        """
    @eff.setter
    def eff(self, arg0: typing.SupportsFloat) -> None:
        ...
    @property
    def mit_kd(self) -> float:
        """
        MIT Kd gain.
        """
    @mit_kd.setter
    def mit_kd(self, arg0: typing.SupportsFloat) -> None:
        ...
    @property
    def mit_kp(self) -> float:
        """
        MIT Kp gain.
        """
    @mit_kp.setter
    def mit_kp(self, arg0: typing.SupportsFloat) -> None:
        ...
    @property
    def pos(self) -> float:
        """
        Target position (radians).
        """
    @pos.setter
    def pos(self, arg0: typing.SupportsFloat) -> None:
        ...
    @property
    def vel(self) -> float:
        """
        Target velocity (rad/s).
        """
    @vel.setter
    def vel(self, arg0: typing.SupportsFloat) -> None:
        ...
class MotorControlMode:
    """
    Members:
    
      INVALID
    
      MIT
    
      CSP
    
      CSV
    
      PVT
    """
    CSP: typing.ClassVar[MotorControlMode]  # value = <MotorControlMode.CSP: 2>
    CSV: typing.ClassVar[MotorControlMode]  # value = <MotorControlMode.CSV: 3>
    INVALID: typing.ClassVar[MotorControlMode]  # value = <MotorControlMode.INVALID: 0>
    MIT: typing.ClassVar[MotorControlMode]  # value = <MotorControlMode.MIT: 1>
    PVT: typing.ClassVar[MotorControlMode]  # value = <MotorControlMode.PVT: 4>
    __members__: typing.ClassVar[dict[str, MotorControlMode]]  # value = {'INVALID': <MotorControlMode.INVALID: 0>, 'MIT': <MotorControlMode.MIT: 1>, 'CSP': <MotorControlMode.CSP: 2>, 'CSV': <MotorControlMode.CSV: 3>, 'PVT': <MotorControlMode.PVT: 4>}
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class MotorName:
    """
    Members:
    
      ThumbFlex
    
      ThumbAux
    
      Index
    
      Middle
    
      Ring
    
      Pinky
    
      Count
    """
    Count: typing.ClassVar[MotorName]  # value = <MotorName.Count: 6>
    Index: typing.ClassVar[MotorName]  # value = <MotorName.Index: 2>
    Middle: typing.ClassVar[MotorName]  # value = <MotorName.Middle: 3>
    Pinky: typing.ClassVar[MotorName]  # value = <MotorName.Pinky: 5>
    Ring: typing.ClassVar[MotorName]  # value = <MotorName.Ring: 4>
    ThumbAux: typing.ClassVar[MotorName]  # value = <MotorName.ThumbAux: 1>
    ThumbFlex: typing.ClassVar[MotorName]  # value = <MotorName.ThumbFlex: 0>
    __members__: typing.ClassVar[dict[str, MotorName]]  # value = {'ThumbFlex': <MotorName.ThumbFlex: 0>, 'ThumbAux': <MotorName.ThumbAux: 1>, 'Index': <MotorName.Index: 2>, 'Middle': <MotorName.Middle: 3>, 'Ring': <MotorName.Ring: 4>, 'Pinky': <MotorName.Pinky: 5>, 'Count': <MotorName.Count: 6>}
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class MotorParams:
    def __bool__(self: collections.abc.Mapping[str, ParamValue]) -> bool:
        """
        Check whether the map is nonempty
        """
    @typing.overload
    def __contains__(self: collections.abc.Mapping[str, ParamValue], arg0: str) -> bool:
        ...
    @typing.overload
    def __contains__(self: collections.abc.Mapping[str, ParamValue], arg0: typing.Any) -> bool:
        ...
    def __delitem__(self: collections.abc.Mapping[str, ParamValue], arg0: str) -> None:
        ...
    def __getitem__(self: collections.abc.Mapping[str, ParamValue], arg0: str) -> ParamValue:
        ...
    def __init__(self) -> None:
        ...
    def __iter__(self: collections.abc.Mapping[str, ParamValue]) -> collections.abc.Iterator[str]:
        ...
    def __len__(self: collections.abc.Mapping[str, ParamValue]) -> int:
        ...
    def __setitem__(self: collections.abc.Mapping[str, ParamValue], arg0: str, arg1: ParamValue) -> None:
        ...
    def items(self: collections.abc.Mapping[str, ParamValue]) -> typing.ItemsView:
        ...
    def keys(self: collections.abc.Mapping[str, ParamValue]) -> typing.KeysView:
        ...
    def values(self: collections.abc.Mapping[str, ParamValue]) -> typing.ValuesView:
        ...
class MotorState:
    def __init__(self) -> None:
        """
        Default‐construct a MotorState (valid=true, others zero).
        """
    def format(self) -> str:
        """
        Return a string representation of the MotorState.
        """
    @property
    def eff(self) -> float:
        """
        Torque (Nm).
        """
    @eff.setter
    def eff(self, arg0: typing.SupportsFloat) -> None:
        ...
    @property
    def error_id(self) -> int:
        """
        Error code (0 = no error).
        """
    @error_id.setter
    def error_id(self, arg0: typing.SupportsInt) -> None:
        ...
    @property
    def is_valid(self) -> bool:
        """
        True if the state is valid.
        """
    @is_valid.setter
    def is_valid(self, arg0: bool) -> None:
        ...
    @property
    def joint_id(self) -> int:
        """
        Joint ID (uint16_t).
        """
    @joint_id.setter
    def joint_id(self, arg0: typing.SupportsInt) -> None:
        ...
    @property
    def mos_temp(self) -> int:
        """
        MOSFET temperature (uint8_t).
        """
    @mos_temp.setter
    def mos_temp(self, arg0: typing.SupportsInt) -> None:
        ...
    @property
    def motor_temp(self) -> int:
        """
        Motor temperature (uint8_t).
        """
    @motor_temp.setter
    def motor_temp(self, arg0: typing.SupportsInt) -> None:
        ...
    @property
    def pos(self) -> float:
        """
        Position (radians).
        """
    @pos.setter
    def pos(self, arg0: typing.SupportsFloat) -> None:
        ...
    @property
    def vel(self) -> float:
        """
        Velocity (rad/s).
        """
    @vel.setter
    def vel(self, arg0: typing.SupportsFloat) -> None:
        ...
class MotorType:
    """
    Members:
    
      NA
    
      OD
    
      DM
    
      ODM
    
      EC
    """
    DM: typing.ClassVar[MotorType]  # value = <MotorType.DM: 1>
    EC: typing.ClassVar[MotorType]  # value = <MotorType.EC: 3>
    NA: typing.ClassVar[MotorType]  # value = <MotorType.NA: 255>
    OD: typing.ClassVar[MotorType]  # value = <MotorType.OD: 0>
    ODM: typing.ClassVar[MotorType]  # value = <MotorType.ODM: 2>
    __members__: typing.ClassVar[dict[str, MotorType]]  # value = {'NA': <MotorType.NA: 255>, 'OD': <MotorType.OD: 0>, 'DM': <MotorType.DM: 1>, 'ODM': <MotorType.ODM: 2>, 'EC': <MotorType.EC: 3>}
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class ParamBuilder:
    def __init__(self) -> None:
        """
        Default‐construct a ParamBuilder.
        """
    def deserialize(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsInt], "FixedSize(4)"]) -> ParamValue:
        """
        Deserialize a 4-byte array into a ParamValue.
        """
    def param_len(self) -> int:
        """
        Return the length (in bytes) of this parameter type.
        """
    def serialize(self, arg0: ParamValue) -> typing.Annotated[list[int], "FixedSize(4)"]:
        """
        Serialize a ParamValue to a 4-byte array.
        """
    @property
    def datatype(self) -> ParamType:
        """
        ParamType for the parameter.
        """
    @datatype.setter
    def datatype(self, arg0: ParamType) -> None:
        ...
    @property
    def default_value(self) -> ParamValue:
        """
        Default ParamValue.
        """
    @default_value.setter
    def default_value(self, arg0: ParamValue) -> None:
        ...
    @property
    def description(self) -> str:
        """
        Description of the parameter.
        """
    @description.setter
    def description(self, arg0: str) -> None:
        ...
    @property
    def id(self) -> int:
        """
        Parameter ID (uint8_t).
        """
    @id.setter
    def id(self, arg0: typing.SupportsInt) -> None:
        ...
    @property
    def implemented(self) -> bool:
        """
        True if the parameter is implemented.
        """
    @implemented.setter
    def implemented(self, arg0: bool) -> None:
        ...
    @property
    def name(self) -> str:
        """
        Parameter name (string_view).
        """
    @name.setter
    def name(self, arg0: str) -> None:
        ...
    @property
    def permission(self) -> str:
        """
        Permission string, one of 'rw', 'ro', 'wo'.
        """
    @permission.setter
    def permission(self, arg0: str) -> None:
        ...
class ParamType:
    """
    Members:
    
      UINT8_LE
    
      INT8_LE
    
      UINT16_LE
    
      INT16_LE
    
      UINT32_LE
    
      INT32_LE
    
      FLOAT32_LE
    
      UINT8_BE
    
      INT8_BE
    
      UINT16_BE
    
      INT16_BE
    
      UINT32_BE
    
      INT32_BE
    
      FLOAT32_BE
    
      UINT8x4
    
      UNTOUCHED
    
      STRING
    
      FLAGS
    
      FLAGS_FLOAT
    
      INVALID
    """
    FLAGS: typing.ClassVar[ParamType]  # value = <ParamType.FLAGS: 253>
    FLAGS_FLOAT: typing.ClassVar[ParamType]  # value = <ParamType.FLAGS_FLOAT: 252>
    FLOAT32_BE: typing.ClassVar[ParamType]  # value = <ParamType.FLOAT32_BE: 24>
    FLOAT32_LE: typing.ClassVar[ParamType]  # value = <ParamType.FLOAT32_LE: 8>
    INT16_BE: typing.ClassVar[ParamType]  # value = <ParamType.INT16_BE: 19>
    INT16_LE: typing.ClassVar[ParamType]  # value = <ParamType.INT16_LE: 3>
    INT32_BE: typing.ClassVar[ParamType]  # value = <ParamType.INT32_BE: 21>
    INT32_LE: typing.ClassVar[ParamType]  # value = <ParamType.INT32_LE: 5>
    INT8_BE: typing.ClassVar[ParamType]  # value = <ParamType.INT8_BE: 17>
    INT8_LE: typing.ClassVar[ParamType]  # value = <ParamType.INT8_LE: 1>
    INVALID: typing.ClassVar[ParamType]  # value = <ParamType.INVALID: 255>
    STRING: typing.ClassVar[ParamType]  # value = <ParamType.STRING: 48>
    UINT16_BE: typing.ClassVar[ParamType]  # value = <ParamType.UINT16_BE: 18>
    UINT16_LE: typing.ClassVar[ParamType]  # value = <ParamType.UINT16_LE: 2>
    UINT32_BE: typing.ClassVar[ParamType]  # value = <ParamType.UINT32_BE: 20>
    UINT32_LE: typing.ClassVar[ParamType]  # value = <ParamType.UINT32_LE: 4>
    UINT8_BE: typing.ClassVar[ParamType]  # value = <ParamType.UINT8_BE: 16>
    UINT8_LE: typing.ClassVar[ParamType]  # value = <ParamType.UINT8_LE: 0>
    UINT8x4: typing.ClassVar[ParamType]  # value = <ParamType.UINT8x4: 32>
    UNTOUCHED: typing.ClassVar[ParamType]  # value = <ParamType.UNTOUCHED: 254>
    __members__: typing.ClassVar[dict[str, ParamType]]  # value = {'UINT8_LE': <ParamType.UINT8_LE: 0>, 'INT8_LE': <ParamType.INT8_LE: 1>, 'UINT16_LE': <ParamType.UINT16_LE: 2>, 'INT16_LE': <ParamType.INT16_LE: 3>, 'UINT32_LE': <ParamType.UINT32_LE: 4>, 'INT32_LE': <ParamType.INT32_LE: 5>, 'FLOAT32_LE': <ParamType.FLOAT32_LE: 8>, 'UINT8_BE': <ParamType.UINT8_BE: 16>, 'INT8_BE': <ParamType.INT8_BE: 17>, 'UINT16_BE': <ParamType.UINT16_BE: 18>, 'INT16_BE': <ParamType.INT16_BE: 19>, 'UINT32_BE': <ParamType.UINT32_BE: 20>, 'INT32_BE': <ParamType.INT32_BE: 21>, 'FLOAT32_BE': <ParamType.FLOAT32_BE: 24>, 'UINT8x4': <ParamType.UINT8x4: 32>, 'UNTOUCHED': <ParamType.UNTOUCHED: 254>, 'STRING': <ParamType.STRING: 48>, 'FLAGS': <ParamType.FLAGS: 253>, 'FLAGS_FLOAT': <ParamType.FLAGS_FLOAT: 252>, 'INVALID': <ParamType.INVALID: 255>}
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class ParamValue:
    @typing.overload
    def __init__(self, type: ParamType, value: typing.SupportsInt) -> None:
        """
        Construct a ParamValue by explicitly specifying the ParamType and integer value.
        """
    @typing.overload
    def __init__(self, type: ParamType, value: typing.SupportsFloat) -> None:
        """
        Construct a ParamValue by explicitly specifying the ParamType FLOAT32_LE and the float value.
        """
    @typing.overload
    def __init__(self, type: ParamType, value: typing.Annotated[collections.abc.Sequence[typing.SupportsInt], "FixedSize(4)"]) -> None:
        """
        Construct a ParamValue by explicitly specifying the ParamType UINT8x4 and a 4‐byte array.
        """
    @typing.overload
    def __init__(self, type: ParamType, value: str) -> None:
        """
        Construct a ParamValue by explicitly specifying the ParamType STRING and a string value.
        """
    @typing.overload
    def __init__(self, type: ParamType, start: typing.SupportsInt, length: typing.SupportsInt, value: typing.SupportsInt) -> None:
        """
        Construct a ParamValue by explicitly specifying the ParamType FLAGS and a 3-tuple of start, length, value.
        """
    @typing.overload
    def __init__(self, start: typing.SupportsInt, length: typing.SupportsInt, value: typing.SupportsInt) -> None:
        """
        Construct a ParamValue by explicitly specifying the ParamType FLAGS and a 3-tuple of start, length, value.
        """
    @typing.overload
    def __init__(self, start: typing.SupportsInt, value: typing.SupportsFloat) -> None:
        """
        Construct a ParamValue by explicitly specifying the ParamType FLAGS_FLOAT and a 3-tuple of start, length, value.
        """
    @typing.overload
    def __init__(self, type: ParamType, start: typing.SupportsInt, value: typing.SupportsFloat) -> None:
        """
        Construct a ParamValue by explicitly specifying the ParamType FLAGS_FLOAT and a 3-tuple of start, length, value.
        """
    def __str__(self) -> str:
        """
        Return a string representation of the ParamValue.
        """
    def format(self) -> str:
        """
        Return a string representation of the ParamValue.
        """
    @property
    def type(self) -> ParamType:
        """
        Parameter type (ParamType).
        """
class Play:
    @staticmethod
    def create(m1: MotorType, m2: MotorType, m3: MotorType, m4: MotorType, m5: MotorType, m6: MotorType, eef_type: EEFType, motor_type: MotorType) -> Play:
        """
                Create a 6-DOF Play arm with the given motor types and end-effector configuration.
                Valid configurations are:
                  • (OD, OD, OD, DM, DM, DM, NA, NA)
                  • (OD, OD, OD, ODM, ODM, ODM, NA, NA)
                Returns a std::unique_ptr<Arm<6>>, or nullptr if unsupported.
        """
    def csv(self, vel: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(6)"]) -> bool:
        """
        Send a CSV (velocity) command to the arm.
        """
    def disable(self) -> bool:
        """
        Disable the arm.
        """
    def enable(self) -> bool:
        """
        Enable the arm.
        """
    def get_param(self, name: str) -> bool:
        """
        Request a parameter value by name.
        """
    def init(self, io_context: Stub, interface: str, spin_freq: typing.SupportsInt) -> bool:
        """
        Initialize the arm with IO context, interface name, and spin frequency.
        """
    def mit(self, pos: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(6)"], vel: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(6)"], eff: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(6)"], mit_kp: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(6)"], mit_kd: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(6)"]) -> bool:
        """
        Send a MIT mode command to the arm.
        """
    def params(self) -> dict[str, ParamValue]:
        """
        Get the arm parameters.
        """
    def persist_param(self, name: str, value: ParamValue) -> bool:
        """
        Persist a parameter value by name.
        """
    def ping(self) -> bool:
        """
        Ping the arm to get latest state.
        """
    def pvt(self, pos: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(6)"], max_vel: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(6)"] = [30.0, 30.0, 30.0, 30.0, 30.0, 30.0], max_eff: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(6)"] = [100.0, 100.0, 100.0, 100.0, 100.0, 100.0]) -> bool:
        """
        Send a PVT (position-velocity-torque) command to the arm.
        """
    def reset_error(self) -> bool:
        """
        Reset arm error state.
        """
    @typing.overload
    def set_param(self, name: str, value: ParamValue) -> bool:
        """
        Set a parameter value by name.
        """
    @typing.overload
    def set_param(self, name: str, value: MotorControlMode) -> bool:
        """
        Set a parameter value by name (MotorControlMode overload).
        """
    def set_zero(self) -> bool:
        """
        Set the arm position reference to zero.
        """
    def state(self) -> PlayState:
        """
        Get the current ArmState.
        """
    def uninit(self) -> bool:
        """
        Uninitialize the arm and clean up resources.
        """
class PlayState:
    is_valid: bool
    def __init__(self) -> None:
        ...
    @property
    def eff(self) -> typing.Annotated[list[float], "FixedSize(6)"]:
        ...
    @eff.setter
    def eff(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(6)"]) -> None:
        ...
    @property
    def error_id(self) -> typing.Annotated[list[int], "FixedSize(6)"]:
        ...
    @error_id.setter
    def error_id(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsInt], "FixedSize(6)"]) -> None:
        ...
    @property
    def joint_id(self) -> typing.Annotated[list[int], "FixedSize(6)"]:
        ...
    @joint_id.setter
    def joint_id(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsInt], "FixedSize(6)"]) -> None:
        ...
    @property
    def mos_temp(self) -> typing.Annotated[list[float], "FixedSize(6)"]:
        ...
    @mos_temp.setter
    def mos_temp(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(6)"]) -> None:
        ...
    @property
    def motor_temp(self) -> typing.Annotated[list[float], "FixedSize(6)"]:
        ...
    @motor_temp.setter
    def motor_temp(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(6)"]) -> None:
        ...
    @property
    def pos(self) -> typing.Annotated[list[float], "FixedSize(6)"]:
        ...
    @pos.setter
    def pos(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(6)"]) -> None:
        ...
    @property
    def vel(self) -> typing.Annotated[list[float], "FixedSize(6)"]:
        ...
    @vel.setter
    def vel(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(6)"]) -> None:
        ...
class PlayWithEEF:
    @staticmethod
    def create(m1: MotorType, m2: MotorType, m3: MotorType, m4: MotorType, m5: MotorType, m6: MotorType, eef_type: EEFType, motor_type: MotorType) -> PlayWithEEF:
        """
                Create a 7-DOF PlayWithEEF arm with the given motor types and end-effector configuration.
                Valid configurations are:
                  • (OD, OD, OD, DM, DM, DM, G2, DM)
                  • (OD, OD, OD, DM, DM, DM, G2, ODM)
                  • (OD, OD, OD, DM, DM, DM, E2, OD)
                  • (OD, OD, OD, ODM, ODM, ODM, G2, DM)
                  • (OD, OD, OD, ODM, ODM, ODM, G2, ODM)
                Returns a std::unique_ptr<Arm<7>>, or nullptr if unsupported.
        """
    def csv(self, vel: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(7)"]) -> bool:
        """
        Send a CSV (velocity) command to the arm.
        """
    def disable(self) -> bool:
        """
        Disable the arm.
        """
    def enable(self) -> bool:
        """
        Enable the arm.
        """
    def get_param(self, name: str) -> bool:
        """
        Request a parameter value by name.
        """
    def init(self, io_context: Stub, interface: str, spin_freq: typing.SupportsInt) -> bool:
        """
        Initialize the arm with IO context, interface name, and spin frequency.
        """
    def mit(self, pos: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(7)"], vel: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(7)"], eff: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(7)"], mit_kp: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(7)"], mit_kd: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(7)"]) -> bool:
        """
        Send a MIT mode command to the arm.
        """
    def params(self) -> dict[str, ParamValue]:
        """
        Get the arm parameters.
        """
    def persist_param(self, name: str, value: ParamValue) -> bool:
        """
        Persist a parameter value by name.
        """
    def ping(self) -> bool:
        """
        Ping the arm to get latest state.
        """
    def pvt(self, pos: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(7)"], max_vel: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(7)"] = [30.0, 30.0, 30.0, 30.0, 30.0, 30.0, 30.0], max_eff: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(7)"] = [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0]) -> bool:
        """
        Send a PVT (position-velocity-torque) command to the arm.
        """
    def reset_error(self) -> bool:
        """
        Reset arm error state.
        """
    @typing.overload
    def set_param(self, name: str, value: ParamValue) -> bool:
        """
        Set a parameter value by name.
        """
    @typing.overload
    def set_param(self, name: str, value: MotorControlMode) -> bool:
        """
        Set a parameter value by name (MotorControlMode overload).
        """
    def set_zero(self) -> bool:
        """
        Set the arm position reference to zero.
        """
    def state(self) -> PlayWithEEFState:
        """
        Get the current ArmState.
        """
    def uninit(self) -> bool:
        """
        Uninitialize the arm and clean up resources.
        """
class PlayWithEEFState:
    is_valid: bool
    def __init__(self) -> None:
        ...
    @property
    def eff(self) -> typing.Annotated[list[float], "FixedSize(7)"]:
        ...
    @eff.setter
    def eff(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(7)"]) -> None:
        ...
    @property
    def error_id(self) -> typing.Annotated[list[int], "FixedSize(7)"]:
        ...
    @error_id.setter
    def error_id(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsInt], "FixedSize(7)"]) -> None:
        ...
    @property
    def joint_id(self) -> typing.Annotated[list[int], "FixedSize(7)"]:
        ...
    @joint_id.setter
    def joint_id(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsInt], "FixedSize(7)"]) -> None:
        ...
    @property
    def mos_temp(self) -> typing.Annotated[list[float], "FixedSize(7)"]:
        ...
    @mos_temp.setter
    def mos_temp(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(7)"]) -> None:
        ...
    @property
    def motor_temp(self) -> typing.Annotated[list[float], "FixedSize(7)"]:
        ...
    @motor_temp.setter
    def motor_temp(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(7)"]) -> None:
        ...
    @property
    def pos(self) -> typing.Annotated[list[float], "FixedSize(7)"]:
        ...
    @pos.setter
    def pos(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(7)"]) -> None:
        ...
    @property
    def vel(self) -> typing.Annotated[list[float], "FixedSize(7)"]:
        ...
    @vel.setter
    def vel(self, arg0: typing.Annotated[collections.abc.Sequence[typing.SupportsFloat], "FixedSize(7)"]) -> None:
        ...
class SerialCommHandler128:
    @staticmethod
    def create(name: str, type: str, interface: str, spin_freq: typing.SupportsInt, io_context: typing.Any) -> SerialCommHandler128:
        """
        Create a serial communication handler.
        """
    def add_read_callback(self, name: str, callback: collections.abc.Callable) -> None:
        """
        Add a read callback for incoming serial frames.
        """
    def delete_read_callback(self, name: str) -> None:
        """
        Delete a previously-registered read callback.
        """
    def start(self) -> bool:
        """
        Start the communication handler.
        """
    def stop(self) -> bool:
        """
        Stop the communication handler.
        """
    def write(self, frame: SerialFrame128) -> bool:
        """
        Write a serial frame.
        """
    def write_strong(self, frame: SerialFrame128) -> bool:
        """
        Write a serial frame with strong semantics.
        """
    def write_weak(self, frame: SerialFrame128) -> bool:
        """
        Write a serial frame with weak semantics.
        """
class SerialCommHandler16:
    @staticmethod
    def create(name: str, type: str, interface: str, spin_freq: typing.SupportsInt, io_context: typing.Any) -> SerialCommHandler16:
        """
        Create a serial communication handler.
        """
    def add_read_callback(self, name: str, callback: collections.abc.Callable) -> None:
        """
        Add a read callback for incoming serial frames.
        """
    def delete_read_callback(self, name: str) -> None:
        """
        Delete a previously-registered read callback.
        """
    def start(self) -> bool:
        """
        Start the communication handler.
        """
    def stop(self) -> bool:
        """
        Stop the communication handler.
        """
    def write(self, frame: SerialFrame16) -> bool:
        """
        Write a serial frame.
        """
    def write_strong(self, frame: SerialFrame16) -> bool:
        """
        Write a serial frame with strong semantics.
        """
    def write_weak(self, frame: SerialFrame16) -> bool:
        """
        Write a serial frame with weak semantics.
        """
class SerialCommHandler32:
    @staticmethod
    def create(name: str, type: str, interface: str, spin_freq: typing.SupportsInt, io_context: typing.Any) -> SerialCommHandler32:
        """
        Create a serial communication handler.
        """
    def add_read_callback(self, name: str, callback: collections.abc.Callable) -> None:
        """
        Add a read callback for incoming serial frames.
        """
    def delete_read_callback(self, name: str) -> None:
        """
        Delete a previously-registered read callback.
        """
    def start(self) -> bool:
        """
        Start the communication handler.
        """
    def stop(self) -> bool:
        """
        Stop the communication handler.
        """
    def write(self, frame: SerialFrame32) -> bool:
        """
        Write a serial frame.
        """
    def write_strong(self, frame: SerialFrame32) -> bool:
        """
        Write a serial frame with strong semantics.
        """
    def write_weak(self, frame: SerialFrame32) -> bool:
        """
        Write a serial frame with weak semantics.
        """
class SerialCommHandler64:
    @staticmethod
    def create(name: str, type: str, interface: str, spin_freq: typing.SupportsInt, io_context: typing.Any) -> SerialCommHandler64:
        """
        Create a serial communication handler.
        """
    def add_read_callback(self, name: str, callback: collections.abc.Callable) -> None:
        """
        Add a read callback for incoming serial frames.
        """
    def delete_read_callback(self, name: str) -> None:
        """
        Delete a previously-registered read callback.
        """
    def start(self) -> bool:
        """
        Start the communication handler.
        """
    def stop(self) -> bool:
        """
        Stop the communication handler.
        """
    def write(self, frame: SerialFrame64) -> bool:
        """
        Write a serial frame.
        """
    def write_strong(self, frame: SerialFrame64) -> bool:
        """
        Write a serial frame with strong semantics.
        """
    def write_weak(self, frame: SerialFrame64) -> bool:
        """
        Write a serial frame with weak semantics.
        """
class SerialCommHandler8:
    @staticmethod
    def create(name: str, type: str, interface: str, spin_freq: typing.SupportsInt, io_context: typing.Any) -> SerialCommHandler8:
        """
        Create a serial communication handler.
        """
    def add_read_callback(self, name: str, callback: collections.abc.Callable) -> None:
        """
        Add a read callback for incoming serial frames.
        """
    def delete_read_callback(self, name: str) -> None:
        """
        Delete a previously-registered read callback.
        """
    def start(self) -> bool:
        """
        Start the communication handler.
        """
    def stop(self) -> bool:
        """
        Stop the communication handler.
        """
    def write(self, frame: SerialFrame8) -> bool:
        """
        Write a serial frame.
        """
    def write_strong(self, frame: SerialFrame8) -> bool:
        """
        Write a serial frame with strong semantics.
        """
    def write_weak(self, frame: SerialFrame8) -> bool:
        """
        Write a serial frame with weak semantics.
        """
class SerialFrame128:
    def __getitem__(self, arg0: typing.SupportsInt) -> int:
        ...
    def __init__(self) -> None:
        ...
    def __len__(self) -> int:
        ...
    def __setitem__(self, arg0: typing.SupportsInt, arg1: typing.SupportsInt) -> None:
        ...
class SerialFrame16:
    def __getitem__(self, arg0: typing.SupportsInt) -> int:
        ...
    def __init__(self) -> None:
        ...
    def __len__(self) -> int:
        ...
    def __setitem__(self, arg0: typing.SupportsInt, arg1: typing.SupportsInt) -> None:
        ...
class SerialFrame32:
    def __getitem__(self, arg0: typing.SupportsInt) -> int:
        ...
    def __init__(self) -> None:
        ...
    def __len__(self) -> int:
        ...
    def __setitem__(self, arg0: typing.SupportsInt, arg1: typing.SupportsInt) -> None:
        ...
class SerialFrame64:
    def __getitem__(self, arg0: typing.SupportsInt) -> int:
        ...
    def __init__(self) -> None:
        ...
    def __len__(self) -> int:
        ...
    def __setitem__(self, arg0: typing.SupportsInt, arg1: typing.SupportsInt) -> None:
        ...
class SerialFrame8:
    def __getitem__(self, arg0: typing.SupportsInt) -> int:
        ...
    def __init__(self) -> None:
        ...
    def __len__(self) -> int:
        ...
    def __setitem__(self, arg0: typing.SupportsInt, arg1: typing.SupportsInt) -> None:
        ...
class Stub:
    a: typing_extensions.CapsuleType
    def __init__(self) -> None:
        ...
class TTYCommHandler:
    @staticmethod
    def create(name: str, type: str, interface: str, spin_freq: typing.SupportsInt, io_context: typing.Any) -> TTYCommHandler:
        """
        Create a TTY communication handler.
        """
    def add_read_callback(self, name: str, callback: collections.abc.Callable) -> None:
        """
        Add a read callback for incoming characters.
        """
    def delete_read_callback(self, name: str) -> None:
        """
        Delete a previously-registered read callback.
        """
    def start(self) -> bool:
        """
        Start the communication handler.
        """
    def stop(self) -> bool:
        """
        Stop the communication handler.
        """
def create_asio_executor(thread_count: typing.SupportsInt) -> typing.Any:
    """
    Create an AsioExecutor with the specified number of worker threads (1-12).
    """
def create_dexterous_hand(id: typing.SupportsInt, type: DexterousHandTypes) -> DexterousHand:
    """
    Create a DexterousHand instance with the given ID and type.
    """
def create_serial_comm_handler(name: str, frame_size: typing.SupportsInt, interface: str, spin_freq: typing.SupportsInt, io_context: typing.Any) -> typing.Any:
    """
    Create a serial communication handler with the specified frame size (8, 16, 32, 64, or 128 bytes).
    """
def make_can_frame_ptr(arg0: CanFrame) -> CanFrame:
    ...
def make_input_event_ptr(event: InputEvent) -> InputEvent:
    """
    Create a shared_ptr<const InputEvent> from an InputEvent instance.
    """
def make_serial_frame128_ptr(frame: SerialFrame128) -> SerialFrame128:
    """
    Create a shared_ptr<const SerialFrame128> from a SerialFrame128 instance.
    """
def make_serial_frame16_ptr(frame: SerialFrame16) -> SerialFrame16:
    """
    Create a shared_ptr<const SerialFrame16> from a SerialFrame16 instance.
    """
def make_serial_frame32_ptr(frame: SerialFrame32) -> SerialFrame32:
    """
    Create a shared_ptr<const SerialFrame32> from a SerialFrame32 instance.
    """
def make_serial_frame64_ptr(frame: SerialFrame64) -> SerialFrame64:
    """
    Create a shared_ptr<const SerialFrame64> from a SerialFrame64 instance.
    """
@typing.overload
def make_serial_frame_ptr(frame: SerialFrame8) -> SerialFrame8:
    """
    Create a shared_ptr<const SerialFrame8> from a SerialFrame8 instance.
    """
@typing.overload
def make_serial_frame_ptr(frame_size: typing.SupportsInt, data: collections.abc.Sequence[typing.SupportsInt]) -> typing.Any:
    """
    Create a serial frame pointer with the specified frame size and data.
    """
def param_value_from_array(arr: tuple) -> ParamValue:
    """
    Construct a UINT8x4 ParamValue from a 4-element tuple of uint8.
    """
def unpack_parse_result(arg0: tuple[FrameType, MotorState, collections.abc.Mapping[str, ParamValue]]) -> tuple:
    """
    Unpack a ParseResult into (FrameType, MotorState, MotorParams).
    """
BLUE_BREATHING: LightEffect  # value = <LightEffect.BLUE_BREATHING: 22>
BLUE_CONSTANT: LightEffect  # value = <LightEffect.BLUE_CONSTANT: 6>
BLUE_FLASHING: LightEffect  # value = <LightEffect.BLUE_FLASHING: 38>
BLUE_MOVEOFF: LightEffect  # value = <LightEffect.BLUE_MOVEOFF: 86>
BLUE_MOVEON: LightEffect  # value = <LightEffect.BLUE_MOVEON: 70>
BLUE_WAVE: LightEffect  # value = <LightEffect.BLUE_WAVE: 54>
CSP: MotorControlMode  # value = <MotorControlMode.CSP: 2>
CSPReq: FrameType  # value = <FrameType.CSPReq: 0>
CSV: MotorControlMode  # value = <MotorControlMode.CSV: 3>
CSVReq: FrameType  # value = <FrameType.CSVReq: 1>
CYAN_BREATHING: LightEffect  # value = <LightEffect.CYAN_BREATHING: 21>
CYAN_CONSTANT: LightEffect  # value = <LightEffect.CYAN_CONSTANT: 5>
CYAN_FLASHING: LightEffect  # value = <LightEffect.CYAN_FLASHING: 37>
CYAN_MOVEOFF: LightEffect  # value = <LightEffect.CYAN_MOVEOFF: 85>
CYAN_MOVEON: LightEffect  # value = <LightEffect.CYAN_MOVEON: 69>
CYAN_WAVE: LightEffect  # value = <LightEffect.CYAN_WAVE: 53>
DM: MotorType  # value = <MotorType.DM: 1>
DOUBLE_CLICKED: ButtonState  # value = <ButtonState.DOUBLE_CLICKED: 3>
DisableReq: FrameType  # value = <FrameType.DisableReq: 9>
E2: EEFType  # value = <EEFType.E2: 2>
EC: MotorType  # value = <MotorType.EC: 3>
EnableReq: FrameType  # value = <FrameType.EnableReq: 8>
FLAGS: ParamType  # value = <ParamType.FLAGS: 253>
FLAGS_FLOAT: ParamType  # value = <ParamType.FLAGS_FLOAT: 252>
FLOAT32_BE: ParamType  # value = <ParamType.FLOAT32_BE: 24>
FLOAT32_LE: ParamType  # value = <ParamType.FLOAT32_LE: 8>
G2: EEFType  # value = <EEFType.G2: 1>
GREEN_BREATHING: LightEffect  # value = <LightEffect.GREEN_BREATHING: 20>
GREEN_CONSTANT: LightEffect  # value = <LightEffect.GREEN_CONSTANT: 4>
GREEN_FLASHING: LightEffect  # value = <LightEffect.GREEN_FLASHING: 36>
GREEN_MOVEOFF: LightEffect  # value = <LightEffect.GREEN_MOVEOFF: 84>
GREEN_MOVEON: LightEffect  # value = <LightEffect.GREEN_MOVEON: 68>
GREEN_WAVE: LightEffect  # value = <LightEffect.GREEN_WAVE: 52>
GetParamReq: FrameType  # value = <FrameType.GetParamReq: 4>
GetParamResp: FrameType  # value = <FrameType.GetParamResp: 17>
IDLE: ButtonState  # value = <ButtonState.IDLE: 0>
INS_RH56DFTP: EEFType  # value = <EEFType.INS_RH56DFTP: 4>
INS_RH56DFX: EEFType  # value = <EEFType.INS_RH56DFX: 3>
INT16_BE: ParamType  # value = <ParamType.INT16_BE: 19>
INT16_LE: ParamType  # value = <ParamType.INT16_LE: 3>
INT32_BE: ParamType  # value = <ParamType.INT32_BE: 21>
INT32_LE: ParamType  # value = <ParamType.INT32_LE: 5>
INT8_BE: ParamType  # value = <ParamType.INT8_BE: 17>
INT8_LE: ParamType  # value = <ParamType.INT8_LE: 1>
INVALID: MotorControlMode  # value = <MotorControlMode.INVALID: 0>
LEDCmd: FrameType  # value = <FrameType.LEDCmd: 32>
LEDCmdResp: FrameType  # value = <FrameType.LEDCmdResp: 33>
LONG_PRESSED: ButtonState  # value = <ButtonState.LONG_PRESSED: 2>
MIT: MotorControlMode  # value = <MotorControlMode.MIT: 1>
MITReq: FrameType  # value = <FrameType.MITReq: 2>
MotionCmdResp: FrameType  # value = <FrameType.MotionCmdResp: 16>
NA: EEFType  # value = <EEFType.NA: 0>
NONE: LightEffect  # value = <LightEffect.NONE: 0>
OD: MotorType  # value = <MotorType.OD: 0>
ODM: MotorType  # value = <MotorType.ODM: 2>
ORANGE_BREATHING: LightEffect  # value = <LightEffect.ORANGE_BREATHING: 18>
ORANGE_CONSTANT: LightEffect  # value = <LightEffect.ORANGE_CONSTANT: 2>
ORANGE_FLASHING: LightEffect  # value = <LightEffect.ORANGE_FLASHING: 34>
ORANGE_MOVEOFF: LightEffect  # value = <LightEffect.ORANGE_MOVEOFF: 82>
ORANGE_MOVEON: LightEffect  # value = <LightEffect.ORANGE_MOVEON: 66>
ORANGE_WAVE: LightEffect  # value = <LightEffect.ORANGE_WAVE: 50>
PLAY_BASE_BOARD: GPIOType  # value = <GPIOType.PLAY_BASE_BOARD: 16>
PLAY_END_BOARD: GPIOType  # value = <GPIOType.PLAY_END_BOARD: 17>
PRESSED: ButtonState  # value = <ButtonState.PRESSED: 1>
PURPLE_BREATHING: LightEffect  # value = <LightEffect.PURPLE_BREATHING: 23>
PURPLE_CONSTANT: LightEffect  # value = <LightEffect.PURPLE_CONSTANT: 7>
PURPLE_FLASHING: LightEffect  # value = <LightEffect.PURPLE_FLASHING: 39>
PURPLE_MOVEOFF: LightEffect  # value = <LightEffect.PURPLE_MOVEOFF: 87>
PURPLE_MOVEON: LightEffect  # value = <LightEffect.PURPLE_MOVEON: 71>
PURPLE_WAVE: LightEffect  # value = <LightEffect.PURPLE_WAVE: 55>
PVT: MotorControlMode  # value = <MotorControlMode.PVT: 4>
PVTReq: FrameType  # value = <FrameType.PVTReq: 3>
PersistParamReq: FrameType  # value = <FrameType.PersistParamReq: 6>
PersistParamResp: FrameType  # value = <FrameType.PersistParamResp: 19>
PingReq: FrameType  # value = <FrameType.PingReq: 7>
RAINBOW_WAVE: LightEffect  # value = <LightEffect.RAINBOW_WAVE: 255>
RED_BREATHING: LightEffect  # value = <LightEffect.RED_BREATHING: 17>
RED_CONSTANT: LightEffect  # value = <LightEffect.RED_CONSTANT: 1>
RED_FLASHING: LightEffect  # value = <LightEffect.RED_FLASHING: 33>
RED_MOVEOFF: LightEffect  # value = <LightEffect.RED_MOVEOFF: 81>
RED_MOVEON: LightEffect  # value = <LightEffect.RED_MOVEON: 65>
RED_WAVE: LightEffect  # value = <LightEffect.RED_WAVE: 49>
REPLAY_BASE_BOARD: GPIOType  # value = <GPIOType.REPLAY_BASE_BOARD: 18>
ResetErrReq: FrameType  # value = <FrameType.ResetErrReq: 11>
STRING: ParamType  # value = <ParamType.STRING: 48>
SetParamReq: FrameType  # value = <FrameType.SetParamReq: 5>
SetParamResp: FrameType  # value = <FrameType.SetParamResp: 18>
SetZeroReq: FrameType  # value = <FrameType.SetZeroReq: 10>
UINT16_BE: ParamType  # value = <ParamType.UINT16_BE: 18>
UINT16_LE: ParamType  # value = <ParamType.UINT16_LE: 2>
UINT32_BE: ParamType  # value = <ParamType.UINT32_BE: 20>
UINT32_LE: ParamType  # value = <ParamType.UINT32_LE: 4>
UINT8_BE: ParamType  # value = <ParamType.UINT8_BE: 16>
UINT8_LE: ParamType  # value = <ParamType.UINT8_LE: 0>
UINT8x4: ParamType  # value = <ParamType.UINT8x4: 32>
UNTOUCHED: ParamType  # value = <ParamType.UNTOUCHED: 254>
Void: FrameType  # value = <FrameType.Void: 255>
WHITE_BREATHING: LightEffect  # value = <LightEffect.WHITE_BREATHING: 31>
WHITE_CONSTANT: LightEffect  # value = <LightEffect.WHITE_CONSTANT: 15>
WHITE_FLASHING: LightEffect  # value = <LightEffect.WHITE_FLASHING: 47>
WHITE_MOVEOFF: LightEffect  # value = <LightEffect.WHITE_MOVEOFF: 95>
WHITE_MOVEON: LightEffect  # value = <LightEffect.WHITE_MOVEON: 79>
WHITE_WAVE: LightEffect  # value = <LightEffect.WHITE_WAVE: 63>
YELLOW_BREATHING: LightEffect  # value = <LightEffect.YELLOW_BREATHING: 19>
YELLOW_CONSTANT: LightEffect  # value = <LightEffect.YELLOW_CONSTANT: 3>
YELLOW_FLASHING: LightEffect  # value = <LightEffect.YELLOW_FLASHING: 35>
YELLOW_MOVEOFF: LightEffect  # value = <LightEffect.YELLOW_MOVEOFF: 83>
YELLOW_MOVEON: LightEffect  # value = <LightEffect.YELLOW_MOVEON: 67>
YELLOW_WAVE: LightEffect  # value = <LightEffect.YELLOW_WAVE: 51>
