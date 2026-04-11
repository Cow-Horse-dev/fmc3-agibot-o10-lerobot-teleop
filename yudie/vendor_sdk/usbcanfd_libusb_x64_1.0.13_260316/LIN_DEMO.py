import ctypes
import time
import threading
from ctypes import *


# 加载动态库
lib = cdll.LoadLibrary("./libusbcanfd.so")

# 常量定义
USBCANFD = 33
MAX_CHANNELS = 2
RX_WAIT_TIME = 100
RX_BUFF_SIZE = 1000
g_thd_run = 1            # 线程运行标志
threads = []             # 接收线程

# class eZLINChkSumMode:
#     DEFAULT = 0
#     CLASSIC_CHKSUM = 1
#     ENHANCE_CHKSUM = 2
#     AUTOMATIC = 3
#
# class ZLINData:
#     MAX_LIN_ID_COUNT = 63
#     MIN_LIN_DLC = 1
#     MAX_LIN_DLC = 8
#     AUTO_LIN_DLC = 255

# 定义结构体和数据类型
class RxData(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("timeStamp", ctypes.c_uint64),
        ("dataLen",ctypes.c_uint8),
        ("dir", ctypes.c_uint8),
        ("chkSum", ctypes.c_uint8),
        ("reserved", ctypes.c_uint8 * 13),
        ("data", ctypes.c_uint8 * 8)

    ]

class ZcanLINPID(ctypes.Union):
    class _PID(ctypes.Structure):
        _pack_ = 1
        _fields_ = [
            ("ID", ctypes.c_uint8, 6),
            ("Parity", ctypes.c_uint8, 2)
        ]

    _fields_ = [
        ("unionVal", _PID),
        ("rawVal", ctypes.c_uint8)
    ]

class ErrDataUnion(ctypes.Union):
    class _Err(ctypes.Structure):
        _pack_ = 1
        _fields_ = [
            ("errStage",ctypes.c_uint16,4),
            ("errReason",ctypes.c_uint16,4),
            ("reserved",ctypes.c_uint16,8)
        ]
    _fields_ = [
        ("struct",_Err),
        ("unionErrData",ctypes.c_uint16)
    ]

class ZCANLINErrData(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("timeStamp",ctypes.c_uint64),
        ("zcanLINPID",ZcanLINPID),
        ("dataLen",ctypes.c_uint8),
        ("data",ctypes.c_uint8 * 8),
        ("errData",ErrDataUnion),
        ("dir",ctypes.c_uint8),
        ("chkSum",ctypes.c_uint8),
        ("reserved",ctypes.c_uint8 * 10)
    ]

class ZCANLINData(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("PID", ZcanLINPID),
        ("RxData", RxData),
        ("reserved", ctypes.c_uint8 * 7)
    ]

class ZCANLINMsgData(ctypes.Union):
    _fields_ = [
        ("zcanLINData", ZCANLINData),
        ("zcanLINErrData", ZCANLINErrData),
        ("raw", ctypes.c_uint8 * 46)
    ]

class ZCAN_LIN_MSG(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("chnl", ctypes.c_uint8),
        ("dataType", ctypes.c_uint8),
        ("data",ZCANLINMsgData)
    ]

class ZcanLININITCONFIG(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("linMode", ctypes.c_uint8),
        ("chkSumMode", ctypes.c_uint8),
        ("reserved", ctypes.c_uint16),
        ("linBaud", ctypes.c_uint32)
    ]


class ZcanLINPUBLISHCFG(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("ID", ctypes.c_uint8),
        ("dataLen", ctypes.c_uint8),
        ("data", ctypes.c_uint8 * 8),
        ("chkSumMode", ctypes.c_uint8),
        ("reserved", ctypes.c_uint8 * 5)
    ]

# 接收线程函数
def rx_thread(DevType,DevIdx,chn_idx):
    # 创建接收缓冲区
    buff = (ZCAN_LIN_MSG * RX_BUFF_SIZE)()
    global g_thd_run
    while g_thd_run == 1:
        rcount = lib.VCI_ReceiveLIN(DevType, DevIdx, chn_idx, buff, RX_BUFF_SIZE, RX_WAIT_TIME)
        if rcount > 0:
            for i in range(rcount):
                if buff[i].dataType == 0:  # 只显示LIN数据
                    lin_data = buff[i].data.zcanLINData
                    rx_data = lin_data.RxData
                    print(f"[{rx_data.timeStamp}] ", end="")
                    print(f"LIN{buff[i].chnl} ", end="")
                    print("TX " if rx_data.dir == 1 else "RX ", end="")
                    print(f"ID: 0x{lin_data.PID.unionVal.ID:02X}  ", end="")
                    print(f"len:{rx_data.dataLen} ", end="")
                    print("Data: ", end="")
                    for j in range(rx_data.dataLen):
                        print(f"{rx_data.data[j]:X} ", end="")
                    print()
        time.sleep(0.001)  # 短暂休眠避免CPU占用过高

# 主函数
if __name__ == "__main__":

    DevType = USBCANFD
    DevIdx = 0

    # 打开设备
    if not lib.VCI_OpenDevice(DevType, DevIdx, 0):
        print("Open device fail")
        exit(1)
    else:
        print("Open device success!")

    # 初始化并打开LIN通道
    LinCfg = (ZcanLININITCONFIG * MAX_CHANNELS)()

    # LIN0设置为主，LIN1设置为从，波特率设置为9600
    LinCfg[0].linMode = 1
    LinCfg[0].linBaud = 9600
    LinCfg[0].chkSumMode = 1

    LinCfg[1].linMode = 0
    LinCfg[1].linBaud = 9600
    LinCfg[1].chkSumMode = 1

    for i in range(MAX_CHANNELS):
        if not lib.VCI_InitLIN(DevType, DevIdx, i, ctypes.byref(LinCfg[i])):
            print(f"init LIN {i} fail")
            exit(1)
        else:
            print(f"init LIN {i} success!")

        if not lib.VCI_StartLIN(DevType, DevIdx, i):
            print(f"start LIN {i} fail")
            exit(1)
        else:
            print(f"start LIN {i} success!")

        thread = threading.Thread(target=rx_thread, args=(DevType, DevIdx, i,))
        threads.append(thread) # 独立接收线程
        thread.start()

    time.sleep(1)  # 等待1秒

    #设置LIN响应
    len = 5
    lpc = (ZcanLINPUBLISHCFG * len)()
    for i in range(len):
        lpc[i].ID = i
        lpc[i].chkSumMode = 0
        lpc[i].dataLen = 8
        for j in range(8):
            lpc[i].data[j] = i * 10 + j

    # 主站响应
    if not lib.VCI_SetLINPublish(DevType, DevIdx, 0, lpc, 3):
        print("set LIN0 publish failed")
    else:
        print("set LIN0 publish success!")
    # 从站响应
    if not lib.VCI_SetLINPublish(DevType, DevIdx, 1, byref(lpc[3]), 2):
        print("set LIN1 publish failed")
    else:
        print("set LIN1 publish success!")

    # LIN0(主)发送头部
    send_data = (ZCAN_LIN_MSG * len)()
    for i in range(len):
        send_data[i].chnl = 0  # 只有主站才能发送头部
        send_data[i].dataType = 0
        send_data[i].data.zcanLINData.PID.rawVal = i

    scount = lib.VCI_TransmitLIN(DevType, DevIdx, 0, send_data, len)
    print(f"Send LIN count : {scount}")

    time.sleep(1)

    # 阻塞等待
    input()
    g_thd_run = 0

    #清除线程
    for thread in threads:
        if thread.is_alive():
            thread.join()

    # 复位通道
    for i in range(MAX_CHANNELS):
        if not lib.VCI_ResetLIN(DevType, DevIdx, i):
            print(f"ResetLIN({i}) fail")
        else:
            print(f"ResetLIN({i}) success!")

    # 关闭设备
    if not lib.VCI_CloseDevice(DevType, DevIdx):
        print("CloseDevice fail")
    else:
        print("CloseDevice success")




