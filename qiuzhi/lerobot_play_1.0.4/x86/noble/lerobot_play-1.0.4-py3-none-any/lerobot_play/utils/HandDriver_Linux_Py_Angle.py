import time
import socket
import json
from threading import Thread
from typing import List, Dict, Optional


# Class representing a 3D vector with float values
class Vector3Float:
    def __init__(self, x: float, y: float, z: float):
        self.x = x
        self.y = y
        self.z = z


# Enum-like class to represent server status
class ServerStatus:
    NO_INIT = 0  # Server not initialized
    READY = 1  # Server ready
    IN_LISTENING = 2  # Server is listening for data
    END = 3  # Server has stopped


# Main SDK class for handling glove data and server communication
class UDEGloveSDK:
    def __init__(self):
        self.port = 5555  # Port number for the server
        self.sock = None
        self.server_addr = ("0.0.0.0", self.port)  # Server address and port
        self.name_list: List[str] = []
        self.controller_res = [0.0] * 12
        self.glove_vec_res = [Vector3Float(0, 0, 0) for _ in range(30)]
        self.cur_status = ServerStatus.NO_INIT
        self.recv_thread: Optional[Thread] = None
        self.glove_data_list: List[Dict] = []
        self.controller_data_list: List[Dict] = []

    # Method to initialize the server
    def initialize(self):
        try:
            self.sock = socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM
            )  # Create a UDP socket
            self.sock.bind(self.server_addr)
            self.sock.settimeout(2)
            self.cur_status = ServerStatus.READY
            print("SDK Initialized and Ready")
        except Exception as e:
            print(f"Failed to initialize: {e}")
            self.cur_status = ServerStatus.NO_INIT

    # Method to start listening for incoming data
    def start_listening(self):
        if self.cur_status != ServerStatus.READY:
            print("SDK is not ready to start listening")
            return
        self.cur_status = ServerStatus.IN_LISTENING
        print("Server Start Listening..")
        self.recv_thread = Thread(target=self.recv_func)
        self.recv_thread.start()

    # Method to stop listening for data
    def end_listening(self):
        if self.recv_thread and self.recv_thread.is_alive():
            self.recv_thread.join()
        self.cur_status = ServerStatus.END
        print("Server Stopped Listening")

    # Method to handle receiving data
    def recv_func(self):
        while self.cur_status == ServerStatus.IN_LISTENING:
            try:
                data, addr = self.sock.recvfrom(1024 * 1024)
                # print(f"Received raw bytes: {data}")
                # print(f"Received raw data: {data.decode('utf-8')}")
                self.process_data(data.decode("utf-8"))
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error receiving data: {e}")

    # Method to process received data
    def process_data(self, data: str):
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

                    if name[1] == "_" and (name[0] == "l" or name[0] == "r"):
                        if name[-1] == "X" or name[-1] == "Y":
                            controller_data["controllerDatas"][name] = value
                        else:
                            controller_data["controllerDatas"][name] = value
                    else:
                        glove_data["handDatas"][name] = value

                self.glove_data_list.append(glove_data)
                self.controller_data_list.append(controller_data)
        except Exception as e:
            print(f"Error processing data: {e}")

    # Method to get the list of role names
    def get_role_name_list(self) -> List[str]:
        return [glove["roleName"] for glove in self.glove_data_list]

    # Method to get vector data for fingers
    def get_vec_finger_data(self, role_name: str) -> List[Vector3Float]:
        for glove in self.glove_data_list:
            if glove["roleName"] == role_name:
                hand_data = glove["handDatas"]
                return [
                    Vector3Float(
                        hand_data.get("l2", 0),
                        hand_data.get("l3", 0),
                        hand_data.get("l20", 0),
                    ),
                    Vector3Float(hand_data.get("l1", 0), 0, 0),
                    Vector3Float(hand_data.get("l0", 0), 0, 0),
                    Vector3Float(
                        hand_data.get("l6", 0),
                        hand_data.get("l7", 0),
                        hand_data.get("l21", 0),
                    ),
                    Vector3Float(hand_data.get("l5", 0), 0, 0),
                    Vector3Float(hand_data.get("l4", 0), 0, 0),
                    Vector3Float(hand_data.get("l10", 0), hand_data.get("l11", 0), 0),
                    Vector3Float(hand_data.get("l9", 0), 0, 0),
                    Vector3Float(hand_data.get("l8", 0), 0, 0),
                    Vector3Float(hand_data.get("l14", 0), hand_data.get("l15", 0), 0),
                    Vector3Float(hand_data.get("l13", 0), 0, 0),
                    Vector3Float(hand_data.get("l12", 0), 0, 0),
                    Vector3Float(
                        hand_data.get("l18", 0),
                        hand_data.get("l19", 0),
                        hand_data.get("l22", 0),
                    ),
                    Vector3Float(hand_data.get("l17", 0), 0, 0),
                    Vector3Float(hand_data.get("l16", 0), 0, 0),
                    Vector3Float(
                        hand_data.get("r2", 0),
                        hand_data.get("r3", 0),
                        hand_data.get("r20", 0),
                    ),
                    Vector3Float(hand_data.get("r1", 0), 0, 0),
                    Vector3Float(hand_data.get("r0", 0), 0, 0),
                    Vector3Float(
                        hand_data.get("r6", 0),
                        hand_data.get("r7", 0),
                        hand_data.get("r21", 0),
                    ),
                    Vector3Float(hand_data.get("r5", 0), 0, 0),
                    Vector3Float(hand_data.get("r4", 0), 0, 0),
                    Vector3Float(hand_data.get("r10", 0), hand_data.get("r11", 0), 0),
                    Vector3Float(hand_data.get("r9", 0), 0, 0),
                    Vector3Float(hand_data.get("r8", 0), 0, 0),
                    Vector3Float(hand_data.get("r14", 0), hand_data.get("r15", 0), 0),
                    Vector3Float(hand_data.get("r13", 0), 0, 0),
                    Vector3Float(hand_data.get("r12", 0), 0, 0),
                    Vector3Float(
                        hand_data.get("r18", 0),
                        hand_data.get("r19", 0),
                        hand_data.get("r22", 0),
                    ),
                    Vector3Float(hand_data.get("r17", 0), 0, 0),
                    Vector3Float(hand_data.get("r16", 0), 0, 0),
                ]
        return self.glove_vec_res

    # Method to get controller data as a list of floats
    def get_vec_controller_data(self, role_name: str) -> List[float]:
        for controller in self.controller_data_list:
            if controller["roleName"] == role_name:
                controller_data = controller["controllerDatas"]
                return [
                    controller_data.get("l_joyX", 0.0),
                    controller_data.get("l_joyY", 0.0),
                    controller_data.get("l_aButton", 0.0),
                    controller_data.get("l_bButton", 0.0),
                    controller_data.get("l_joyButton", 0.0),
                    controller_data.get("l_menu", 0.0),
                    controller_data.get("r_joyX", 0.0),
                    controller_data.get("r_joyY", 0.0),
                    controller_data.get("r_aButton", 0.0),
                    controller_data.get("r_bButton", 0.0),
                    controller_data.get("r_joyButton", 0.0),
                    controller_data.get("r_menu", 0.0),
                ]
        return self.controller_res


# Headers for glove data
GloveDataHeaders = [
    "LeftThumb1",
    "LeftThumb2",
    "LeftThumb3",
    "LeftIndex1",
    "LeftIndex2",
    "LeftIndex3",
    "LeftMiddle1",
    "LeftMiddle2",
    "LeftMiddle3",
    "LeftRing1",
    "LeftRing2",
    "LeftRing3",
    "LeftPinky1",
    "LeftPinky2",
    "LeftPinky3",
    "RightThumb1",
    "RightThumb2",
    "RightThumb3",
    "RightIndex1",
    "RightIndex2",
    "RightIndex3",
    "RightMiddle1",
    "RightMiddle2",
    "RightMiddle3",
    "RightRing1",
    "RightRing2",
    "RightRing3",
    "RightPinky1",
    "RightPinky2",
    "RightPinky3",
]

# Headers for controller data
ControllerHeaders = [
    "Left Joy X",
    "Left Joy Y",
    "Left A Button",
    "Left B Button",
    "Left Joy Button",
    "Left Menu Button",
    "Right Joy X",
    "Right Joy Y",
    "Right A Button",
    "Right B Button",
    "Right Joy Button",
    "Right Menu Button",
]


def main():
    sdk = UDEGloveSDK()  # Create an instance of the SDK
    sdk.initialize()  # Initialize the SDK
    sdk.start_listening()  # Start listening for data
    index = 1
    quit = False

    while not quit:
        try:
            role_list = sdk.get_role_name_list()  # Get the list of role names
            if len(role_list) > 0:
                print(f"-------------- {index} -----------")
                for role_name in role_list:
                    finger_data = sdk.get_vec_finger_data(role_name)  # Get finger data
                    controller_data = sdk.get_vec_controller_data(
                        role_name
                    )  # Get controller data

                    print(f"role_name: {role_name}")
                    for i, header in enumerate(GloveDataHeaders):
                        print(
                            f"{header}: ({finger_data[i].x}, {finger_data[i].y}, {finger_data[i].z})"
                        )
                    for i, header in enumerate(ControllerHeaders):
                        print(f"{header}: {controller_data[i]}")
                    print("-------------------------")

                index += 1

                if index >= 7200 * 20:
                    print(f"End Listening. {index}")
                    sdk.end_listening()  # Stop listening
                    quit = True
                    break

            time.sleep(1 / 130)
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
