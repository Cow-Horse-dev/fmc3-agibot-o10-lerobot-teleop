#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <pthread.h>
#include "zcan.h"
#include "zuds.h"

#define msleep(ms) usleep((ms) * 1000)
#define RX_WAIT_TIME 100
#define RX_BUFF_SIZE 1000

// 接收线程上下文
typedef struct
{
    int dev_type;           // 设备类型
    int dev_idx;            // 设备索引
    int chn_idx;            // 通道号
    int total;              // 接收总数
    int stop;               // 线程结束标志
    ZUDS_HANDLE uds_handle; // uds句柄
} THREAD_CTX;

typedef struct
{
    int channel_handle; // 作通道号
    int Extend_Flag;
    int CANFD_type;
    int trans_version;
} CHANNEL_PARAM;

int DevIdx = 0;    // 设备索引号
int USBCANFD = 33; // USBCANFD系列统一33
int CHANNEL_INDEX = 0;

static uint32 transmit_callback(void *ctx, const ZUDS_FRAME *frame, uint count)
{
    CHANNEL_PARAM *pchn_param = (CHANNEL_PARAM *)ctx;
    uint result = 0;

    if (!pchn_param->CANFD_type)
    {
        // can
        ZCAN_20_MSG *zcan_data = (ZCAN_20_MSG *)malloc(sizeof(ZCAN_20_MSG) * count);
        if (zcan_data == NULL)
        {
            return 1; // 内存分配失败处理
        }

        memset(zcan_data, 0, sizeof(ZCAN_20_MSG) * count);

        // 填充消息数据
        for (int i = 0; i < count; i++)
        {
            zcan_data[i].hdr.id = frame[i].id;
            if (pchn_param->Extend_Flag)
            {
                zcan_data[i].hdr.inf.sef = 1;
            }
            zcan_data[i].hdr.len = frame[i].data_len;
            zcan_data[i].hdr.inf.echo = 1;
            zcan_data[i].hdr.inf.fmt = 0;
            zcan_data[i].hdr.inf.brs = 0;
            zcan_data[i].hdr.chn = pchn_param->channel_handle;
            for (int j = 0; j < frame[i].data_len; j++)
            {
                zcan_data[i].dat[j] = frame[i].data[j];
            }
        }

        // 调用发送函数
        result = VCI_Transmit(USBCANFD, DevIdx, pchn_param->channel_handle, zcan_data, count);
        free(zcan_data);
    }
    else
    {
        // canfd
        ZCAN_FD_MSG *zcanfd_data = (ZCAN_FD_MSG *)malloc(sizeof(ZCAN_FD_MSG) * count);
        if (zcanfd_data == NULL)
        {

            return 1; // 内存分配失败处理
        }

        memset(zcanfd_data, 0, sizeof(ZCAN_FD_MSG) * count);

        // 填充消息数据
        for (int i = 0; i < count; i++)
        {
            zcanfd_data[i].hdr.id = frame[i].id;
            if (pchn_param->Extend_Flag)
            {
                zcanfd_data[i].hdr.inf.sef = 1;
            }
            zcanfd_data[i].hdr.len = frame[i].data_len;
            zcanfd_data[i].hdr.inf.echo = 1;
            zcanfd_data[i].hdr.inf.fmt = 1;
            zcanfd_data[i].hdr.inf.brs = 0;
            zcanfd_data[i].hdr.chn = pchn_param->channel_handle;
            for (int j = 0; j < frame[i].data_len; j++)
            {
                zcanfd_data[i].dat[j] = frame[i].data[j];
            }
        }

        // 调用发送函数
        result = VCI_TransmitFD(USBCANFD, DevIdx, pchn_param->channel_handle, zcanfd_data, count);
        free(zcanfd_data);
    }
    printf("result=%d count=%d \r\n", result, count);
    if (result == count)
        return 0;
    else
        return 1;
}
// 接收线程
void *rx_thread_uds(void *data)
{
    THREAD_CTX *ctx = (THREAD_CTX *)data;
    int DevType = ctx->dev_type;
    int DevIdx = ctx->dev_idx;
    int chn_idx = ctx->chn_idx;
    ZUDS_HANDLE UdsHandle = ctx->uds_handle;

    ZCAN_20_MSG can_data[RX_BUFF_SIZE];
    ZCAN_FD_MSG canfd_data[RX_BUFF_SIZE];
    ZUDS_FRAME uds_frame = {0};
    while (!ctx->stop)
    {
        memset(can_data, 0, sizeof(can_data));
        memset(canfd_data, 0, sizeof(canfd_data));

        int rcount = VCI_Receive(DevType, DevIdx, chn_idx, can_data, RX_BUFF_SIZE, RX_WAIT_TIME); // CAN
        for (int i = 0; i < rcount; ++i)
        {
            memset(&uds_frame, 0, sizeof(uds_frame));
            uds_frame.id = can_data[i].hdr.id & 0x1fffffff; // 传入真实ID
            uds_frame.extend = can_data[i].hdr.inf.sef;
            uds_frame.data_len = can_data[i].hdr.len;
            memcpy(uds_frame.data, can_data[i].dat, uds_frame.data_len);
            ZUDS_OnReceive(UdsHandle, &uds_frame);

            printf("[%u] ", can_data[i].hdr.ts);
            printf("chn: %d  ", chn_idx);
            printf("%s  ", can_data[i].hdr.inf.tx == 1 ? "Tx" : "Rx"); // 判断是否回显报文
            printf("CAN ID: 0x%X ", can_data[i].hdr.id & 0x1FFFFFFF);
            printf("%s  ", can_data[i].hdr.inf.sef == 1 ? "扩展帧" : "标准帧");
            printf("Data: ");
            if (can_data[i].hdr.inf.sdf == 0)
            { // 数据帧
                for (int j = 0; j < can_data[i].hdr.len; ++j)
                    printf("%02x ", can_data[i].dat[j]);
            }
            printf("\n");
        }
        ctx->total += rcount;

        rcount = VCI_ReceiveFD(DevType, DevIdx, chn_idx, canfd_data, RX_BUFF_SIZE, RX_WAIT_TIME); // CANFD
        for (int i = 0; i < rcount; ++i)
        {
            memset(&uds_frame, 0, sizeof(uds_frame));
            uds_frame.id = canfd_data[i].hdr.id & 0x1fffffff; // 传入真实ID
            uds_frame.extend = canfd_data[i].hdr.inf.sef;
            uds_frame.data_len = canfd_data[i].hdr.len;
            memcpy(uds_frame.data, canfd_data[i].dat, uds_frame.data_len);
            ZUDS_OnReceive(UdsHandle, &uds_frame);

            printf("[%u] ", canfd_data[i].hdr.ts);
            printf("chn: %d  ", chn_idx);
            printf("%s  ", canfd_data[i].hdr.inf.tx == 1 ? "Tx" : "Rx"); // 判断是否回显报文
            printf("CANFD%s  ", canfd_data[i].hdr.inf.brs == 1 ? "加速" : "");
            printf("ID: 0x%x ", canfd_data[i].hdr.id & 0x1FFFFFFF);
            printf("%s  ", canfd_data[i].hdr.inf.sef == 1 ? "扩展帧" : "标准帧");
            printf("Data: ");
            for (int j = 0; j < canfd_data[i].hdr.len; ++j)
                printf("%02x ", canfd_data[i].dat[j]);
            printf("\n");
        }
        ctx->total += rcount;
        msleep(10);
    }
    printf("chn: %d receive %d\n", chn_idx, ctx->total);
    pthread_exit(0);
}

void Set_param(ZUDS_HANDLE puds_handle, CHANNEL_PARAM *pchn_param)
{
    ZUDS_ISO15765_PARAM param_15765 = {0};
    memset(&param_15765, 0, sizeof(param_15765));
    param_15765.version = pchn_param->trans_version;
    if (0 == pchn_param->trans_version)
        param_15765.max_data_len = 8;
    else
        param_15765.max_data_len = 64;

    param_15765.local_st_min = 0;
    param_15765.block_size = 8;
    param_15765.fill_byte = 0;
    param_15765.frame_type = pchn_param->Extend_Flag; // 0-标准帧，1-扩展帧
    param_15765.is_modify_ecu_st_min = 0;             // 是否修改 ECU 的最小发送时间间隔参数
    param_15765.remote_st_min = 0;
    param_15765.fc_timeout = 70;                 // 等待流控超时时间，单位ms
    param_15765.fill_mode = 1;                   // 数据长度填充模式，0-不填充，1-小于8字节填充到8，大于8字节就近填充，2-填充至最大字节
    ZUDS_SetParam(puds_handle, 1, &param_15765); // 第二个参数为1对应15765结构体

    ZUDS_SESSION_PARAM param_seesion = {0};
    memset(&param_seesion, 0, sizeof(param_seesion));
    param_seesion.timeout = 2000;
    param_seesion.enhanced_timeout = 5000;
    ZUDS_SetParam(puds_handle, 0, &param_seesion); // 第二个参数为0对应ZUDS_SESSION_PARAM结构体

    printf("set_param completed");
    return;
}

int main(int argc, char *argv[])
{
    int DevType = USBCANFD; // 设备类型号 33-usbcanfd

    THREAD_CTX rx_ctx;    // 接收线程上下文
    pthread_t rx_threads; // 接收线程

    // 打开设备
    if (!VCI_OpenDevice(DevType, DevIdx, 0))
    {
        printf("Open device fail\n");
        return 0;
    }
    printf("Open device success\n");
    // 初始化，启动通道
    ZCAN_INIT init;      // 波特率结构体，数据根据zcanpro的波特率计算器得出
    init.clk = 60000000; // clock: 60M(V1.01) 80M(V1.03即以上)
    init.mode = 0;       // 0-正常

    init.aset.tseg1 = 14; // 仲裁域 500kbps
    init.aset.tseg2 = 3;
    init.aset.sjw = 2;
    init.aset.smp = 0;
    init.aset.brp = 5;

    init.dset.tseg1 = 10; // 数据域 2000kbps
    init.dset.tseg2 = 2;
    init.dset.sjw = 2;
    init.dset.smp = 0;
    init.dset.brp = 1;

    if (!VCI_InitCAN(DevType, DevIdx, CHANNEL_INDEX, &init)) // 初始化通道
    {
        printf("InitCAN(%d) fail\n", CHANNEL_INDEX);
        return 0;
    }
    printf("InitCAN(%d) success\n", CHANNEL_INDEX);

    U32 on = 1;
    if (!VCI_SetReference(DevType, DevIdx, CHANNEL_INDEX, CMD_CAN_TRES, &on)) // 终端电阻
    {
        printf("CMD_CAN_TRES fail\n");
    }

    if (!VCI_StartCAN(DevType, DevIdx, CHANNEL_INDEX)) // 启动通道
    {
        printf("StartCAN(%d) fail\n", CHANNEL_INDEX);
        return 0;
    }
    printf("StartCAN(%d) success\n", CHANNEL_INDEX);

    // uds初始化;
    CHANNEL_PARAM chn_param = {0};
    ZUDS_HANDLE uds_handle = ZUDS_Init(0);
    printf("uds_handle is %d\r\n", uds_handle);

    chn_param.channel_handle = CHANNEL_INDEX;
    chn_param.Extend_Flag = 0;   // 0-标准帧，1-扩展帧
    chn_param.CANFD_type = 0;    // 0-CAN,1-CANFD
    chn_param.trans_version = 0; // 0-2004版本，1-2016版本

    ZUDS_SetTransmitHandler(uds_handle, &chn_param, transmit_callback); // 设置发送回调,将uds句柄与通道句柄绑定

    Set_param(uds_handle, &chn_param);

    rx_ctx.dev_type = DevType;
    rx_ctx.dev_idx = DevIdx;
    rx_ctx.chn_idx = CHANNEL_INDEX;
    rx_ctx.total = 0;
    rx_ctx.stop = 0;
    rx_ctx.uds_handle = uds_handle;

    pthread_create(&rx_threads, NULL, rx_thread_uds, &rx_ctx); // 创建接收线程

    sleep(1);
    printf("request test\r\n");
    ZUDS_REQUEST request = {0};
    memset(&request, 0, sizeof(request));
    request.src_addr = 0x773;
    request.dst_addr = 0x7b3;
    request.sid = 0x10;
    request.param_len = 0x1; // 参数长度

    request.param = (u_int8_t *)malloc(sizeof(u_int8_t) * request.param_len);
    *(request.param) = 0x03;

    ZUDS_RESPONSE response = {0};
    memset(&response, 0, sizeof(response));
    ZUDS_Request(uds_handle, &request, &response);
    free(request.param);

    if (response.status == 0)
    {
        if (response.type == 0)
        {
            // 消极响应
            printf("消极响应：0x%02X 服务号：0x%02X  消极码：0x%02X\n",
                   response.negative.neg_code,
                   response.negative.sid,
                   response.negative.error_code);
        }
        if (response.type == 1)
        {
            // 积极响应
            printf("积极响应,响应id:0x%02X,参数长度:%d,参数内容：",
                   response.positive.sid,
                   response.positive.param_len);

            // 打印参数内容
            for (int i = 0; i < response.positive.param_len; i++)
            {
                printf("0x%02X ", response.positive.param[i]);
            }
            printf("\n");
        }
    }
    else if (response.status == 1)
    {
        printf("响应超时\n");
    }
    else if (response.status == 2)
    {
        printf("传输失败，请检查链路层，或请确认流控帧是否回复\n");
    }
    else if (response.status == 3)
    {
        printf("取消请求\n");
    }
    else if (response.status == 4)
    {
        printf("抑制响应\n");
    }
    else if (response.status == 5)
    {
        printf("忙碌中\n");
    }
    else if (response.status == 6)
    {
        printf("请求参数错误\n");
    }

    // 阻塞等待
    getchar();

    rx_ctx.stop = 1;
    pthread_join(rx_threads, NULL); // 等待线程退出

    if (!VCI_ResetCAN(DevType, DevIdx, CHANNEL_INDEX)) // 复位通道
        printf("ResetCAN(%d) fail\n", CHANNEL_INDEX);
    else
        printf("ResetCAN(%d) success!\n", CHANNEL_INDEX);

    // 关闭设备
    if (!VCI_CloseDevice(DevType, DevIdx))
        printf("CloseDevice fail\n");
    else
        printf("CloseDevice success\n");
    return 0;
}