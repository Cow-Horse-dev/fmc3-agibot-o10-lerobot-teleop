'''
if there is no receive device(only usbcanfd) , the ZCAN_MSG_INFO "txm" use txtype --2, self test
if there is a same baudrate receive device ,  the ZCAN_MSG_INFO "txm" use txtype --0, normal send

ZLG  Zhiyuan Electronics
'''

from ctypes import *
import threading
import time
import platform
import datetime
from baudrate import *
from zuds_API import *


START_RECIEIVE_FLAG=0

ZCAN_DEVICE_TYPE  = c_uint32
ZCAN_DEVICE_INDEX = c_uint32
ZCAN_CHANNEL      = c_uint32
ZCAN_Reserved     = c_uint32
ZCAN_tx_timeout    = c_uint32
canfd_test        = 1
RES_ON            = 1  #Resistance setting
RES_OFF           = 0
CAN_TRES          = 0x18 #Resistance address

USBCANFD_200U =   ZCAN_DEVICE_TYPE(33)
DEVICE_INDEX  =   ZCAN_DEVICE_INDEX(0)
CHANNEL_INDEX =   0
Reserved      =   ZCAN_Reserved(0)



def input_thread():
    input()

####################################### zuds  ###############################################

class PARAM_DATA(Structure):    #用于存放uds的参数内容
    _pack_=1
    _fields_=[("data",c_ubyte*4096)]

class CHANNEL_PARAM(Structure):
    _fields_=[("channel_handle",c_uint32),      #通道句柄,linux中作为通道号
              ("Extend_Flag",c_uint32),         #0-standard_frame, 1-extern_frame
              ("CANFD_type",c_uint32),          #0-can,1-canfd
              ("trans_version",c_uint32),       #0-ISO15765-2004,1-ISO15765-2016
              ]


#设置发送回调实例
@CFUNCTYPE(c_uint32, POINTER(CHANNEL_PARAM), POINTER(ZUDS_FRAME), c_uint32)
def transmit_callback(ctx, frame, count):
    print("frame num is:%d"%count)
    if  ctx.contents.CANFD_type:
        zcanfd_data=(ZCAN_FD_MSG*count)()
        memset(zcanfd_data,0,sizeof(zcanfd_data))
        for i in range(count):
            zcanfd_data[i].msg_header.id = frame[i].id
            if ctx.contents.Extend_Flag:
                zcanfd_data[i].msg_header.info.sef = 1
            zcanfd_data[i].msg_header.len = frame[i].data_len  # frame[i].data_len
            zcanfd_data[i].msg_header.info.echo =1  #设置发送回显
            zcanfd_data[i].msg_header.info.fmt =1  #0-can,1-canfd
            zcanfd_data[i].msg_header.info.brs =0  #canfd加速位
            zcanfd_data[i].msg_header.chn =ctx.contents.channel_handle
            for j in range(frame[i].data_len):
                zcanfd_data[i].dat[j] = frame[i].data[j]
        result = lib.VCI_TransmitFD(USBCANFD_200U,DEVICE_INDEX,ctx.contents.channel_handle,zcanfd_data,count)
    else:
        zcan_data = (ZCAN_20_MSG * count)()
        memset(zcan_data,0,sizeof(zcan_data))#确保队列发送中的“帧间隔为0”
        for i in range(count):
            zcan_data[i].msg_header.id = frame[i].id
            if ctx.contents.Extend_Flag:
                zcan_data[i].msg_header.info.sef = 1
            zcan_data[i].msg_header.len = frame[i].data_len  # frame[i].data_len
            zcan_data[i].msg_header.info.echo =1  #设置发送回显
            zcan_data[i].msg_header.info.fmt =0  #0-can,1-canfd
            zcan_data[i].msg_header.info.brs =0  #canfd加速位
            zcan_data[i].msg_header.chn =ctx.contents.channel_handle
            for j in range(frame[i].data_len):
                zcan_data[i].dat[j] = frame[i].data[j]
        result = lib.VCI_Transmit(USBCANFD_200U,DEVICE_INDEX,ctx.contents.channel_handle,zcan_data,count)
    if result ==count:
        return 0
    else:
        return 1



# 设置诊断通讯参数
def Set_param(uds_handle, chn_param):
    param_15765 = ZUDS_ISO15765_PARAM()
    memset(byref(param_15765), 0, sizeof(param_15765))
    param_15765.version = chn_param.trans_version  #
    param_15765.max_data_len = 8 if chn_param.trans_version else 64
    param_15765.local_st_min = 0
    param_15765.block_size = 8
    param_15765.fill_byte = 0
    param_15765.frame_type = chn_param.Extend_Flag  # 0-标准帧，1-扩展帧
    param_15765.is_modify_ecu_st_min = 0  # 是否修改 ECU 的最小发送时间间隔参数
    param_15765.remote_st_min = 0
    param_15765.fc_timeout = 70  # 等待流控超时时间，单位ms
    param_15765.fill_mode = 1  # 数据长度填充模式，0-不填充，1-小于8字节填充到8，大于8字节就近填充，2-填充至最大字节
    zudslib.Uds_SetParam(uds_handle, 1, param_15765)  # 第二个参数为1对应15765结构体
    
    param_seesion = ZUDS_SESSION_PARAM()
    memset(byref(param_seesion), 0, sizeof(param_seesion))
    param_seesion.timeout = 2000
    param_seesion.enhanced_timeout = 5000
    zudslib.Uds_SetParam(uds_handle, 0, param_seesion)  # 第二个参数为0对应 应用层结构体
    print("set_param completed")

# 独立的循环接收线程，把接收数据丢给UDS库处理。
def Read_Thread_Func(DEVICE_INDEX, CHANNEL_INDEX, uds_handle):
    uds_frame = ZUDS_FRAME()
    channelfd = 0x80000000+(CHANNEL_INDEX &0xf)
    while START_RECIEIVE_FLAG:
        
        ret_can  =  lib.VCI_GetReceiveNum(USBCANFD_200U,DEVICE_INDEX,CHANNEL_INDEX)
        ret_canfd = lib.VCI_GetReceiveNum(USBCANFD_200U, DEVICE_INDEX, channelfd)
        if ret_can:
            rcv_msgs = (ZCAN_20_MSG * ret_can)()
            ret_can = lib.VCI_Receive(USBCANFD_200U, DEVICE_INDEX, CHANNEL_INDEX, byref(rcv_msgs), ret_can, 100)
            for i in range(ret_can):
                memset(byref(uds_frame), 0, sizeof(uds_frame))
                uds_frame.id = rcv_msgs[i].msg_header.id & 0x1fffffff  # 传入真实ID
                uds_frame.extend =rcv_msgs[i].msg_header.info.sef
                uds_frame.data_len = rcv_msgs[i].msg_header.len
                for j in range(uds_frame.data_len):
                    uds_frame.data[j] = rcv_msgs[i].dat[j]
                print("%s : Timestamp:%d, id:%s , type: can ,dlc:%d ,data:%s" % (
                "TX" if rcv_msgs[i].msg_header.info.tx else "RX", (rcv_msgs[i].msg_header.ts),
                hex(rcv_msgs[i].msg_header.id),
                rcv_msgs[i].msg_header.len,
                ''.join(hex(rcv_msgs[i].dat[j]) + ' ' for j in range(rcv_msgs[i].msg_header.len))))
                zudslib.Uds_Onreceive(uds_handle, uds_frame)
        if ret_canfd:
            rcvfd_msgs = (ZCAN_FD_MSG * ret_canfd)()
            ret_canfd = lib.VCI_ReceiveFD(USBCANFD_200U, DEVICE_INDEX, CHANNEL_INDEX, byref(rcvfd_msgs), ret_canfd, 100)
            for i in range(ret_canfd):
                memset(byref(uds_frame), 0, sizeof(uds_frame))
                uds_frame.id = rcvfd_msgs[i].msg_header.id & 0x1fffffff  # 传入真实ID
                uds_frame.extend = rcvfd_msgs[i].msg_header.info.sef
                uds_frame.data_len = rcvfd_msgs[i].msg_header.len
                for j in range(uds_frame.data_len):
                    uds_frame.data[j] = rcvfd_msgs[i].dat[j]
                print("%s : Timestamp:%d, id:%s , type: canfd  ,brs:%d ,dlc:%d ,data:%s" % (
                "TX" if rcvfd_msgs[i].msg_header.info.tx else "RX", (rcvfd_msgs[i].msg_header.ts),
                hex(rcvfd_msgs[i].msg_header.id),
                rcvfd_msgs[i].msg_header.info.brs, rcvfd_msgs[i].msg_header.len,
                ''.join(hex(rcvfd_msgs[i].dat[j]) + ' ' for j in range(rcvfd_msgs[i].msg_header.len))))
                zudslib.Uds_Onreceive(uds_handle, uds_frame)
        time.sleep(0.01)
    print("exit receive")


# CAN通讯参数，波特率，电阻等参数
def canfd_start(Devicetype,DeviceIndex,Channel):
    canfd_init = Setbaudrate(500000, 2000000)
    ret=lib.VCI_InitCAN(Devicetype,DeviceIndex,Channel,byref(canfd_init))
    if ret ==0:
        print("init Failed!")
        exit(0)
    else:
        print("init success!")
    ret=lib.VCI_StartCAN(Devicetype,DeviceIndex,Channel)
    if ret ==0:
        print("startcan Failed!")
        exit(0)
    else:
        print("startcan success!")
    
    RES_ON_ =c_uint8(1)
    lib.VCI_SetReference(Devicetype,DeviceIndex,Channel,CAN_TRES,byref(RES_ON_))


    filter_set = 0x14
    filter_table =ZCAN_FILTER_TABLE()
    memset(byref(filter_table),0,sizeof(filter_table))
    filter_table.size =sizeof(ZCAN_FILTER)*1 #设置一组滤波参数
    filter_table.table[0].type=0
    filter_table.table[0].sid =0x0
    filter_table.table[0].eid =0x7FF         #设置滤波标准帧，范围0~0x7FF
    ret=lib.VCI_SetReference(Devicetype,DeviceIndex,Channel,filter_set,byref(filter_table))
    
    wait_tx    = 0x44              #tx_timeout
    tx_timeout    = ZCAN_tx_timeout(200)
    ret=lib.VCI_SetReference(Devicetype,DeviceIndex,Channel,wait_tx,byref(tx_timeout))
    

# 报文发送函数 -普通发送
def can_send(Devicetype,DeviceIndex,Channel):
    can_frame = (ZCAN_20_MSG*10)()
    for i in range(10):
        can_frame[i].msg_header.ts=0
        can_frame[i].msg_header.id=0x100+i
        can_frame[i].msg_header.info.txm = 0 #0--normal send, 2--self test
        can_frame[i].msg_header.info.fmt = 0 #can2.0
        can_frame[i].msg_header.info.sdf = 0 #data frame
        can_frame[i].msg_header.info.sef = 0 #std frame
        can_frame[i].msg_header.info.err = 0
        can_frame[i].msg_header.info.brs = 0
        can_frame[i].msg_header.info.est = 0
        can_frame[i].msg_header.pad      = 0
        can_frame[i].msg_header.chn      = 0
        can_frame[i].msg_header.len      = 8 
        for j in range (can_frame[i].msg_header.len):
            can_frame[i].dat[j]=j
            
    ret= lib.VCI_Transmit(Devicetype,DeviceIndex,Channel,byref(can_frame),10)
    print("Transmit num is:%d"%ret)

    if canfd_test:
        canfd_frame = (ZCAN_FD_MSG*10)()
        for i in range(10):
            canfd_frame[i].msg_header.ts=0
            canfd_frame[i].msg_header.id=0x18000000+i
            canfd_frame[i].msg_header.info.txm = 0 #0--normal send, 2--self test
            canfd_frame[i].msg_header.info.fmt = 1 #canFD
            canfd_frame[i].msg_header.info.sdf = 0 #data frame
            canfd_frame[i].msg_header.info.sef = 1 #0-std frame,1-ext frame
            canfd_frame[i].msg_header.info.err = 0
            canfd_frame[i].msg_header.info.brs = 0
            canfd_frame[i].msg_header.info.est = 0
            canfd_frame[i].msg_header.pad      = 0
            canfd_frame[i].msg_header.chn      = 0
            canfd_frame[i].msg_header.len      = 32
            for j in range (canfd_frame[i].msg_header.len):
                canfd_frame[i].dat[j]=j
    #    ret= lib.VCI_TransmitFD(Devicetype,DeviceIndex,Channel,byref(canfd_frame),10)
    #print("TransmitFD num is:%d"%ret)

if __name__=="__main__":
    zudslib = ZUDS()
    ret=lib.VCI_OpenDevice(USBCANFD_200U,DEVICE_INDEX,Reserved)
    if ret ==0:
        print("Opendevice fail!")
        exit(0)
    else:
        print("Opendevice success!")
    canfd_start(USBCANFD_200U,DEVICE_INDEX,CHANNEL_INDEX)
    #can_send(USBCANFD_200U,DEVICE_INDEX,CHANNEL_INDEX)
    START_RECIEIVE_FLAG=1

    ############################## UDS初始化########################################
    uds_handle = zudslib.Uds_Init(0)  # 初始化UDS，获取UDS句柄
    print("uds_handle is %d" % uds_handle)

    chn_param = CHANNEL_PARAM()
    chn_param.channel_handle = CHANNEL_INDEX
    chn_param.Extend_Flag = 0  # 0-标准帧，1-扩展帧
    chn_param.CANFD_type = 0  # 0-CAN,1-CANFD       type = version = 1 才支持一帧报文最大传输64字节
    chn_param.trans_version = 0  # 0-2004版本，1-2016版本
    ret = zudslib.Uds_SetTransmitHandler(uds_handle, byref(chn_param),transmit_callback)  # 设置发送回调,将uds句柄与通道句柄绑定
    if ret == 0:
        print("Uds_SetTransmitHandler success")
    else:
        print("Uds_SetTransmitHandler fail")

    Set_param(uds_handle, chn_param)
    
    
    ###############先打开接收线程###############
    thread=threading.Thread(target=input_thread)
    thread.start()
    thread_rx= threading.Thread(target=Read_Thread_Func,args=(DEVICE_INDEX,CHANNEL_INDEX,uds_handle))
    thread_rx.start()
    print("request ")  
    request= ZUDS_REQUEST()   
    memset(byref(request),0,sizeof(request))
    request.src_addr=0x700
    request.dst_addr=0x701
    request.sid = 0x10
    request.param_len=0x1      #参数长度
    param_data=PARAM_DATA()  #参数的list，成员数量需与request.param_len对应  
    data_1= [0x03]   
    for i in range(request.param_len):
        param_data.data[i]=data_1[i]
    request.param =param_data.data
    response =ZUDS_RESPONSE()

    zudslib.Uds_Request(uds_handle,request,response)
    memset(byref(param_data),0,sizeof(param_data))
    if response.status==0:
        if response.type ==0: 
            print("消极响应：%s 服务号： %s  消极码： %s"%(hex(response.response.negative.neg_code),hex(response.response.negative.sid),hex(response.response.negative.error_code)))
        if response.type ==1:
            print("积极响应,响应id:%s,参数长度:%d,参数内容：%s"%(hex(response.response.positive.sid),response.response.positive.param_len,''.join(hex(response.response.positive.param[i])+' 'for i in range(response.response.positive.param_len))))
    if response.status ==1:
        print("响应超时")
    if response.status ==2:
        print("传输失败，请检查链路层，或请确认流控帧是否回复")
    if response.status ==3:
        print("取消请求")
    if response.status ==4:
        print("抑制响应")
    if response.status ==5:
        print("忙碌中")
    if response.status ==6:
        print("请求参数错误")
    
   
    while True:
        time.sleep(0.1)

        if thread.is_alive() == False:
            START_RECIEIVE_FLAG=0
            break

    ret=lib.VCI_ResetCAN(USBCANFD_200U,DEVICE_INDEX,CHANNEL_INDEX)
    if ret ==0:
         print("ResetCAN Failed!")
    else:
         print("ResetCAN success!")

    ret=lib.VCI_CloseDevice(USBCANFD_200U,DEVICE_INDEX)
    if ret ==0:
         print("Closedevice Failed!")
    else:
         print("Closedevice success!")
    print('done')
