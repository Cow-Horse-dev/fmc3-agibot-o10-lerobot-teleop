import socket
import json
from threading import Thread
from typing import List, Dict, Optional
from Protobuf import handdriver_teleop_pb2
from Protobuf import PicoTeleop_pb2

# Glove data receive model
# responsible for receiving and analysing data via UDP for main program.

RED = "\033[31m"
GREEN = "\033[32m"
RESET = "\033[0m"

class ServerStatus:
    """
    Status ENUM
    """
    NO_INIT = 0
    READY = 1
    IN_LISTENING = 2
    END = 3

class GloveReceiver:
    """
    Receiver class, for UDP data listening & analysing.
    """
    def __init__(self, server_ip="192.168.5.71", port=7777):
        self.port = port  # Listening port
        self.sock = None  # UDP socket
        self.server_addr = (server_ip, self.port)  # Listening address
        self.cur_status = ServerStatus.NO_INIT  # Current status
        self.recv_thread: Optional[Thread] = None  # Receive thread
        self.glove_data_list: List[Dict] = []  # Glove data list
        self.controller_data_list: List[Dict] = []  # Controller data list
        self.hand_data = None

    def initialize(self, _dataType: str, _roleName: str, _hand: str):
        """
        Initialize UDP listening service
        """
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind(self.server_addr)
            self.sock.settimeout(2)
            self.cur_status = ServerStatus.READY
            self.dataType = _dataType
            self.requestedRole = _roleName
            self.targetRole = _roleName
            self.targetHand = _hand.lower()
            self.LeftHandDataList = None
            self.RightHandDataList = None
            self.hand_data = {}
            print(f"GloveReceiver Initialized and Ready \nCurrent data type: {RED}{_dataType}{RESET}, role name: {RED}{_roleName}{RESET}, hand type: {RED}{_hand}{RESET}")
        except Exception as e:
            print(f"Failed to initialize: {e}")
            self.cur_status = ServerStatus.NO_INIT

    def start_listening(self):
        """
        run data listening thread
        """
        if self.cur_status != ServerStatus.READY:
            print("GloveReceiver is not ready to start listening")
            return
        self.cur_status = ServerStatus.IN_LISTENING
        print(f"GloveReceiver Start Listening. IP:{GREEN}{self.server_addr[0]}{RESET}, Port:{GREEN}{self.server_addr[1]}{RESET}")
        self.recv_thread = Thread(target=self.recv_func)
        self.recv_thread.start()

    def end_listening(self):
        """
        stop listening, terminate thread
        """
        self.cur_status = ServerStatus.END
        if self.recv_thread and self.recv_thread.is_alive():
            self.recv_thread.join(timeout=2)
        print("GloveReceiver Stopped Listening")

    def recv_func(self):
        """
        main data receive & analyse loop
        """
        while self.cur_status == ServerStatus.IN_LISTENING:
            if self.sock is None:
                print("Socket uninitialized")
                break
            try:
                data, addr = self.sock.recvfrom(1024 * 1024)
                if(self.dataType == 'Json'):
                    self.process_data(data.decode("utf-8"))
                elif(self.dataType == 'Protobuf'):
                    self.process_protobuf_data(data)
                elif(self.dataType == 'TeleopProtobuf'):
                    self.process_teleop_protobuf_data(data)
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error receiving data: {e}")

    def process_data(self, data: str):
        """
        Analyse Json string, separate glove and controller data
        """
        try:
            value = json.loads(data)
            self.glove_data_list.clear()
            self.controller_data_list.clear()
            for role_name, device in value.items():
                glove_data = {"roleName": role_name, "handDatas": {}}
                controller_data = {"roleName": role_name, "controllerDatas": {}}
                parameters = device.get("Parameter", [])
                for param in parameters:
                    name = param["Name"]
                    value = (param["Value"]) if "Value" in param else 0.0
                    # controller data is beginned with 'l_' or 'r_'
                    if name[1] == '_' and (name[0] == 'l' or name[0] == 'r'):
                        controller_data["controllerDatas"][name] = value
                    else:
                        glove_data["handDatas"][name] = value
                self.glove_data_list.append(glove_data)
                self.controller_data_list.append(controller_data)

            self.resolve_json_role()
        except Exception as e:
            print(f"Error processing data: {e}")

    def resolve_json_role(self):
        """
        Resolve the role used for Json data. If the requested role is unavailable,
        fall back to the first available role, matching the CLI help text.
        """
        if len(self.glove_data_list) == 0:
            return

        available_roles = [glove["roleName"] for glove in self.glove_data_list]
        resolved_role = self.requestedRole if self.requestedRole in available_roles else available_roles[0]

        if resolved_role != self.targetRole:
            if resolved_role == self.requestedRole:
                print(f"Requested Json role {GREEN}{self.requestedRole}{RESET} is available again.")
            else:
                print(f"Json role {RED}{self.requestedRole}{RESET} not found. Use first available role {GREEN}{resolved_role}{RESET} instead.")

        self.targetRole = resolved_role

    def process_protobuf_data(self, data: bytes):
        """
        Analyse Protobuf data, only collect glove data. (controller data is available but skip here)
        """
        try:
            glove_data = handdriver_teleop_pb2.TeleopDataAngle()
            glove_data.ParseFromString(data)
            if(glove_data.RoleName == self.targetRole):
                self.LeftHandDataList = glove_data.LeftHand.joints
                self.RightHandDataList = glove_data.RightHand.joints
        except Exception as e:
            print(f"Error processing data: {e}")
    
    def process_teleop_protobuf_data(self, data: bytes):
        """
        Analyse Protobuf data from teleop application, only collect glove data. (controller data is available but skip here)
        """
        try:
            glove_data = PicoTeleop_pb2.TeleopData()
            glove_data.ParseFromString(data)
            self.LeftHandDataList = glove_data.LeftHand.joints
            self.RightHandDataList = glove_data.RightHand.joints
        except Exception as e:
            print(f"Error processing data: {e}")

    def get_data_valid(self) -> bool:
        """
        Check whether received data is valid or not.
        """
        return len(self.glove_data_list) > 0 if self.dataType == 'Json' else (self.LeftHandDataList is not None or self.RightHandDataList is not None)
    
    def get_hand_data(self, hand: str):
        if(self.dataType == 'Json'):
            if(len(self.glove_data_list) == 0):
                return [0] * 24

            selected_glove = next((glove for glove in self.glove_data_list if glove["roleName"] == self.targetRole), None)
            if selected_glove is None:
                return [0] * 24

            self.hand_data = selected_glove["handDatas"]
            return [self.hand_data.get(('r' if hand == 'right' else 'l') + str(i), 0) for i in range(24)]
        else:
            if(hand == 'left'):
                return self.LeftHandDataList if self.LeftHandDataList else [0]*24
            else:
                return self.RightHandDataList if self.RightHandDataList else [0]*24
