from ctypes import *

lib = cdll.LoadLibrary("./libusbcanfd.so")

class Constant(object):
    # ----------支持的诊断服务列表----------
    ZUDS_SI_DiagnosticSessionControl = 0x10  # 诊断会话控制
    ZUDS_SI_ECUReset = 0x11  # ECU 重置
    ZUDS_SI_ClearDiagnosticInformation = 0x14  # 清除诊断信息
    ZUDS_SI_ReadDTCInformation = 0x19  # 读取 DTC 信息
    ZUDS_SI_ReadDataByIdentifier = 0x22  # 按标识符读取数据
    ZUDS_SI_ReadMemoryByAddress = 0x23  # 按地址读取内容
    ZUDS_SI_ReadScalingDataByIdentifier = 0x24  # 按标识符读取换算数据
    ZUDS_SI_SecurityAccess = 0x27  # 安全访问
    ZUDS_SI_CommunicationControl = 0x28  # 通讯控制
    ZUDS_SI_ReadDataByPeriodicIdentifier = 0x2A  # 按周期性标识符读取数据
    ZUDS_SI_DynamicallyDefineDataIdentifier = 0x2C  # 动态定义数据标识符
    ZUDS_SI_WriteDataByIdentifier = 0x2E  # 按标识符写数据
    ZUDS_SI_InputOutputControlByIdentifier = 0x2F  # 按标识符的输入输出控制
    ZUDS_SI_RoutineControl = 0x31  # 例程控制
    ZUDS_SI_RequestDownload = 0x34  # 文件下载
    ZUDS_SI_RequestUpload = 0x35  # 请求上传
    ZUDS_SI_TransferData = 0x36  # 数据传输
    ZUDS_SI_RequestTransferExit = 0x37  # 请求传输退出
    ZUDS_SI_WriteMemoryByAddress = 0x3D  # 按地址写内存
    ZUDS_SI_TesterPresent = 0x3E  # 会话保持
    ZUDS_SI_AccessTimingParameter = 0x83  # 访问计时参数
    ZUDS_SI_SecuredDataTransmission = 0x84  # 受保护的数据传输
    ZUDS_SI_ControlDTCSetting = 0x85  # 控制 DTC 设置
    ZUDS_SI_ResponseOnEvent = 0x86  # 基于事件响应
    ZUDS_SI_LinkControl = 0x87  # 链路控制
    # ----------接口参数----------
    DoCAN = 0
    PARAM_TYPE_SESSION = 0
    PARAM_TYPE_ISO15765 = 1
    VERSION_0 = 0
    VERSION_1 = 1


class ZUDS_REQUEST(Structure):
    _pack_=1
    _fields_ = [
        ("src_addr", c_uint32),
        ("dst_addr", c_uint32),
        ("suppress_response", c_uint8),
        ("sid", c_uint8),
        ("reserved0", c_uint16),
        ("param", POINTER(c_uint8)),
        ("param_len", c_uint32),
        ("reserved", c_uint32)
    ]


class POSITIVE_DATA(Structure):
    _pack_=1
    _fields_ = [
        ("sid", c_ubyte),
        ("param", POINTER(c_ubyte)),
        ("param_len", c_uint32)
    ]


class NEGATIVE_DATA(Structure):
    _pack_=1
    _fields_ = [
        ("neg_code", c_ubyte),
        ("sid", c_ubyte),
        ("error_code", c_ubyte)
    ]


class RESPONSE_DATA(Union):
    _pack_=1
    _fields_ = [
        ("positive", POSITIVE_DATA),
        ("negative", NEGATIVE_DATA)
    ]

'''
ZCAN_UDS_ERROR说明

#define ZCAN_UDS_ERROR_OK                   0    // 没错误
#define ZCAN_UDS_ERROR_TIMEOUT              1    // 响应超时
#define ZCAN_UDS_ERROR_TRANSPORT            2    // 发送数据失败
#define ZCAN_UDS_ERROR_CANCEL               3    // 取消请求
#define ZCAN_UDS_ERROR_SUPPRESS_RESPONSE    4    // 抑制响应
#define ZCAN_UDS_ERROR_BUSY                 5    // 忙碌中
#define ZCAN_UDS_ERROR_REQ_PARAM            6    // 请求参数错误
#define ZCAN_UDS_ERROR_OTHTER               100
'''

class ZUDS_RESPONSE(Structure):
    _pack_ = 1
    _fields_ = [
        ("status", c_ubyte),#见ZCAN_UDS_ERROR说明
        ("type", c_ubyte),#0-消极响应,1-积极响应
        ("response", RESPONSE_DATA),
        ("reserved", c_uint32*4)
    ]


class ZUDS_FRAME(Structure):
    _pack_ = 1
    _fields_ = [
        ("id", c_uint32),
        ("extend", c_ubyte),
        ("remote", c_ubyte),
        ("data_len", c_ubyte),
        ("data", c_ubyte * 64),
        ("reserved", c_uint32)
    ]


class ZUDS_SESSION_PARAM(Structure):
    _pack_ = 1
    _fields_ = [
        ("timeout", c_uint16),  # 等待服务器响应的超时时间，单位为毫秒；
        ("enhanced_timeout", c_uint16),  # 在收到负应答（错误码为 0x78）后等待的超时时间，单位为毫秒；
        ("check_any_negative_response", c_uint8, 1),  # 是否检查任意负应答；
        ("wait_if_suppress_response", c_uint8, 1),  # 如果抑制了响应是否等待；
        ("flag", c_uint8, 6),  # 标志位，保留字段；
        ("reserved0", c_uint8 * 3),  # 保留字段；
        ("reserved1", c_uint32)  # 保留字段。
    ]


class ZUDS_ISO15765_PARAM(Structure):
    _fields_ = [
        ("version", c_uint8),  # 版本号，取值为 VERSION_0 或 VERSION_1；
        ("max_data_len", c_uint8),  # 最大数据长度，CAN 总线：8 字节；CAN-FD 总线：64 字节。
        ("local_st_min", c_uint8),  # 最小两帧之间的时间间隔，单位为毫秒；
        ("block_size", c_uint8),  # BS，ISO 15765-2 定义的块大小参数；
        ("fill_byte", c_uint8),  # 填充无效字节的值；
        ("frame_type", c_uint8),  # 帧类型，0：标准帧；1：扩展帧。
        ("is_modify_ecu_st_min", c_uint8),  # 是否修改 ECU 的最小发送时间间隔参数；
        ("remote_st_min", c_uint8),  # 远程传输的最小发送时间间隔参数；
        ("fc_timeout", c_uint16),  # FC 超时时间，单位为毫秒。
        ("fill_mode",c_uint8),     #数据长度填充模式，0-不填充，1-小于8字节填充到8，大于8字节就近填充，2-填充至最大字节
        ("reserved",c_uint8*5),
    ]


class ZUDS_TESTER_PRESENT_PARAM(Structure):
    _fields_ = [
        ("addr", c_uint32),  # 会话保持的请求地址；
        ("cycle", c_uint16),  # 发送周期，单位毫秒；
        ("suppress_response", c_uint8),  # 是否抑制响应，建议设置为 1；
        ("reserved", c_uint32)  # 保留字段，忽略即可。
    ]

# can/canfd messgae info
class ZCAN_MSG_INFO(Structure):
    _fields_=[("txm",c_uint,4), # TXTYPE:0 normal,1 once, 2self
              ("fmt",c_uint,4), # 0-can2.0 frame,  1-canfd frame
              ("sdf",c_uint,1), # 0-data frame, 1-remote frame
              ("sef",c_uint,1), # 0-std_frame, 1-ext_frame
              ("err",c_uint,1), # error flag
              ("brs",c_uint,1), # bit-rate switch ,0-Not speed up ,1-speed up
              ("est",c_uint,1), # error state
              ("tx",c_uint,1),  # received valid, 0-rx 1-tx frame
              ("echo",c_uint,1), #  tx valid, 1-echo frame
              ("qsend_100us",c_uint,1), #queue send delay unit, 1-100us, 0-ms
              ("qsend",c_uint,1), # send valid, queue send frame
              ("pad",c_uint,15)]

#CAN Message Header
class ZCAN_MSG_HDR(Structure):
    _fields_=[("ts",c_uint32),  #timestamp
              ("id",c_uint32),  #can-id
              ("info",ZCAN_MSG_INFO),
              ("pad",c_uint16),
              ("chn",c_uint8),  #channel
              ("len",c_uint8)]  #data length

#CAN2.0-frame
class ZCAN_20_MSG(Structure):
    _fields_=[("msg_header",ZCAN_MSG_HDR),
              ("dat",c_ubyte*8)]


#CANFD frame
class ZCAN_FD_MSG(Structure):
    _fields_=[("msg_header",ZCAN_MSG_HDR),
               ("dat",c_ubyte*64)]

#filter_set
class ZCAN_FILTER(Structure):
    _fields_=[("type",c_uint8),#0-std_frame,1-extend_frame
              ("pad",c_uint8*3),#reserved
              ("sid",c_uint32), #start_ID
              ("eid",c_uint32)] #end_ID

class ZCAN_FILTER_TABLE(Structure):
    _fields_=[("size",c_uint32),#滤波数组table实际生效部分的长度
              ("table",ZCAN_FILTER*64)]


class abit_config(Structure):
    _fields_=[("tseg1",c_uint8),
              ("tseg2",c_uint8),
              ("sjw",c_uint8),
              ("smp",c_uint8),
              ("brp",c_uint16)]

class dbit_config(Structure):
    _fields_=[("tseg1",c_uint8),
              ("tseg2",c_uint8),
              ("sjw",c_uint8),
              ("smp",c_uint8),
              ("brp",c_uint16)]

class ZCANFD_INIT(Structure):
    _fields_=[("clk",c_uint32),
              ("mode",c_uint32),
              ("abit",abit_config),
              ("dbit",dbit_config)]

#Terminating resistor
class Resistance(Structure):
    _fields_=[("res",c_uint8)
              ]

class ZUDS(object):
    def __init__(self):
        self.__dll = cdll.LoadLibrary("./libzuds.so")

    def Uds_Init(self, type_):
        try:
            return self.__dll.ZUDS_Init(type_)
        except:
            print("Excetion on Udsinit")

    def Uds_SetTransmitHandler(self, zuds_handle, ctx, transmit_callback):
        try:
            return self.__dll.ZUDS_SetTransmitHandler(zuds_handle, ctx, transmit_callback)
        except:
            print("Exception on SetTransmitHandler")

    def Uds_Request(self, handle, request, response):
        try:
            return self.__dll.ZUDS_Request(handle, byref(request), byref(response))
        except:
            print("Exception on UDSRequest")

    def Uds_Onreceive(self, handle, uds_frame):
        try:
            return self.__dll.ZUDS_OnReceive(handle, byref(uds_frame))
        except:
            print("Exception on uds_Onreceive")

    def Uds_SetParam(self, handle, type_, param):  # type =0设置ZUDS_SESSION_PARAM，type=1设置ZUDS_ISO15765_PARAM
        try:
            return self.__dll.ZUDS_SetParam(handle, type_, byref(param))
        except:
            print("Exception on uds_SetParam")

    def Uds_SetTesterPresent(self, handle, enable, param):
        try:
            return self._dll.ZUDS_SetTesterPresent(handle, enable, byref(param))
        except:
            print("Exception on SetTesterPresent")

    def Uds_Release(self, handle):
        try:
            return self.__dll.ZUDS_Release(handle)
        except:
            print("Exception on uds_Release")

    def Uds_Stop(self, handle):
        try:
            return self.__dll.ZUDS_Stop(handle)
        except:
            print("Exception on UDS_STOP")