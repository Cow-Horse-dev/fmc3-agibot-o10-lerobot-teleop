// Copyright (c) 2025, Agibot Co., Ltd.
// OmniHand 2025 SDK is licensed under Mulan PSL v2.

/**
 * @file c_zlg_usbcanfd_sdk.cpp
 * @brief
 * @author AgiUser
 * @date 25-7-28
 **/

#include "c_zlg_usbcanfd_sdk.h"

#include <cstring>
#include <iomanip>
#include <iostream>
#include <sstream>

#include "zcan.h"

typedef unsigned int UINT;
typedef unsigned char U8;
typedef unsigned int U32;
#define msleep(ms) usleep((ms)*1000)

#define DEVICE_TYPE_USBCANFD 33  // 设备类型
#define RX_WAIT_TIME 100
#define RX_BUFF_SIZE 1000

std::mutex ZlgUsbcanfdSDK::device_mutex_;
std::map<unsigned char, int> ZlgUsbcanfdSDK::device_ref_count_;

ZlgUsbcanfdSDK::ZlgUsbcanfdSDK(unsigned char canfd_id, unsigned char channel_id)
    : canfd_id_(canfd_id), channel_id_(channel_id) {
  if (ZlgUsbcanfdSDK::OpenDevice() == -1) {
    return;
  }

  pthread_ = new std::thread(&ZlgUsbcanfdSDK::RecvFrame, this);
}

ZlgUsbcanfdSDK::~ZlgUsbcanfdSDK() {
  RequestInterrupt();

  if (pthread_ != nullptr) {
    pthread_->join();
    delete pthread_;
  }

  ZlgUsbcanfdSDK::CloseDevice();
}

bool ZlgUsbcanfdSDK::IsInit() {
  return pthread_ == nullptr ? false : true;
}

int ZlgUsbcanfdSDK::OpenDevice() {
  std::lock_guard<std::mutex> lock(device_mutex_);

  bool device_already_open = (device_ref_count_.count(canfd_id_) > 0 && device_ref_count_[canfd_id_] > 0);
  if (!device_already_open) { /* first */
    if (VCI_OpenDevice(DEVICE_TYPE_USBCANFD, canfd_id_, 0)) {
      std::cout << "[INFO]: Open device " << (int)canfd_id_ << " usbcanfd successfully." << std::endl;
      device_ref_count_[canfd_id_] = 0;
    } else {
      std::cout << "[ERROR]: Open device " << (int)canfd_id_ << " usbcanfd failed!" << std::endl;
      return -1;
    }
  } else {
    std::cout << "[INFO]: Device " << (int)canfd_id_ << " already open, reusing." << std::endl;
  }

  /*初始化并启动指定通道*/
  ZCAN_INIT init;  // TODO 初始化数据根据zcanpro的波特率计算器得出
  init.clk = 60000000;
  init.mode = 0;

  init.aset.tseg1 = 46;  // 仲裁域 1M
  init.aset.tseg2 = 11;
  init.aset.sjw = 3;
  init.aset.smp = 0;
  init.aset.brp = 0;

  init.dset.tseg1 = 7;  // 数据域 5M
  init.dset.tseg2 = 2;
  init.dset.sjw = 1;
  init.dset.smp = 0;
  init.dset.brp = 0;

  /*初始化通道*/
  if (VCI_InitCAN(DEVICE_TYPE_USBCANFD, canfd_id_, channel_id_, &init)) {
    std::cout << "[INFO]: Init canfd device " << (int)canfd_id_ << " channel " << (int)channel_id_ << " successfully." << std::endl;
  } else {
    std::cout << "[ERROR]: Init canfd device " << (int)canfd_id_ << " channel " << (int)channel_id_ << " failed!" << std::endl;
    return -1;
  }

  /*终端电阻*/
  U32 on = 1;
  if (!VCI_SetReference(DEVICE_TYPE_USBCANFD, canfd_id_, channel_id_, CMD_CAN_TRES, &on)) {
    std::cout << "[ERROR]: CMD_CAN_TRES failed for device " << (int)canfd_id_ << " channel " << (int)channel_id_ << std::endl;
  }

  /*合并接收*/
  int isMerge = 0;
  if (!VCI_SetReference(DEVICE_TYPE_USBCANFD, canfd_id_, channel_id_, ZCAN_CMD_SET_CHNL_RECV_MERGE, &isMerge)) {
    std::cout << "[ERROR]: ZCAN_CMD_SET_CHNL_RECV_MERGE failed!" << std::endl;
  }

  /*启动通道*/
  if (VCI_StartCAN(DEVICE_TYPE_USBCANFD, canfd_id_, channel_id_)) {
    std::cout << "[INFO]: Start canfd device " << (int)canfd_id_ << " channel " << (int)channel_id_ << " successfully." << std::endl;
  } else {
    std::cout << "[ERROR]: Start canfd device " << (int)canfd_id_ << " channel " << (int)channel_id_ << " failed!" << std::endl;
    return -1;
  }

  /*增加引用计数*/
  device_ref_count_[canfd_id_]++;
  std::cout << "[INFO]: Device " << (int)canfd_id_ << " ref count: " << device_ref_count_[canfd_id_] << std::endl;

  return 0;
}

int ZlgUsbcanfdSDK::CloseDevice() {
  std::lock_guard<std::mutex> lock(device_mutex_);

  /*复位通道*/
  if (VCI_ResetCAN(DEVICE_TYPE_USBCANFD, canfd_id_, channel_id_)) {
    std::cout << "[INFO]: Reset canfd device " << (int)canfd_id_ << " channel " << (int)channel_id_ << " successfully." << std::endl;
  } else {
    std::cout << "[ERROR]: Reset canfd device " << (int)canfd_id_ << " channel " << (int)channel_id_ << " failed!" << std::endl;
  }

  /*减少引用计数*/
  if (device_ref_count_.count(canfd_id_) > 0) {
    device_ref_count_[canfd_id_]--;
    std::cout << "[INFO]: Device " << (int)canfd_id_ << " ref count: " << device_ref_count_[canfd_id_] << std::endl;

    /*只有当引用计数为0时才关闭设备*/
    if (device_ref_count_[canfd_id_] <= 0) {
      if (VCI_CloseDevice(DEVICE_TYPE_USBCANFD, canfd_id_)) {
        std::cout << "[INFO]: Close canfd device " << (int)canfd_id_ << " successfully." << std::endl;
        device_ref_count_.erase(canfd_id_);
      } else {
        std::cout << "[ERROR]: Close canfd device " << (int)canfd_id_ << " failed!" << std::endl;
        return -1;
      }
    }
  }

  return 0;
}

void ZlgUsbcanfdSDK::RecvFrame() {
  ZCAN_FD_MSG canfd_data[RX_BUFF_SIZE];

  while (!IsInterruptRequested()) {
    memset(canfd_data, 0, sizeof(canfd_data));
    int recvCount = VCI_ReceiveFD(DEVICE_TYPE_USBCANFD, canfd_id_, channel_id_, canfd_data, RX_BUFF_SIZE, RX_WAIT_TIME);
    for (int i = 0; i < recvCount; i++) {
      CanfdFrame rep{};
      rep.can_id_ = canfd_data[i].hdr.id;
      rep.len_ = canfd_data[i].hdr.len;
      memcpy(rep.data_, canfd_data[i].dat, rep.len_);

      if (show_data_details_.load()) {
        auto now = std::chrono::system_clock::now();
        auto now_time_t = std::chrono::system_clock::to_time_t(now);

        // 获取微秒
        auto now_us = std::chrono::duration_cast<std::chrono::microseconds>(now.time_since_epoch()) % 1000000;
        struct tm tm_buf;
        localtime_r(&now_time_t, &tm_buf);
        std::cout << "["
                  << std::put_time(&tm_buf, "%Y-%m-%d %H:%M:%S")
                  << "." << std::dec << std::setfill('0') << std::setw(6) << now_us.count()
                  << "] RCV: " << rep;
      }

      {
        bool matchedReq = false;
        std::lock_guard<std::mutex> lockGuard(mutex_reqRep_);
        for (auto reqId : uset_req_) {
          if (msg_match_judge_) {
            matchedReq = msg_match_judge_(reqId, rep.can_id_);
            if (matchedReq) {
              umap_rep_[rep.can_id_] = rep;
              break;
            }
          }
        }

        if (matchedReq) {
          continue;
        }
      }

      if (callback_) {
        callback_(rep);
      }
    }
  }
}

int ZlgUsbcanfdSDK::SendFrame(unsigned int id, unsigned char* data, unsigned char length) {
  ZCAN_FD_MSG canfd_msg;
  memset(&canfd_msg, 0, sizeof(canfd_msg));

  canfd_msg.hdr.inf.txm = 0;  // 0-正常发送
  canfd_msg.hdr.inf.fmt = 1;  // 0-CAN, 1-CANFD
  canfd_msg.hdr.inf.sdf = 0;  // 0-数据帧 CANFD只有数据帧!
  canfd_msg.hdr.inf.sef = 1;  // 0-标准帧, 1-扩展帧
  canfd_msg.hdr.inf.brs = 1;  // canfd 加速
  // canfd_msg.hdr.inf.echo  = 1;   // 发送回显

  canfd_msg.hdr.id = id;
  canfd_msg.hdr.chn = channel_id_;
  canfd_msg.hdr.len = length;  // 数据长度

  // TODO 注意非法长度
  memcpy(canfd_msg.dat, data, length);

  int sndRet = VCI_TransmitFD(DEVICE_TYPE_USBCANFD, canfd_id_, channel_id_, &canfd_msg, 1);
  if (sndRet == 1) {
    return 0;
  } else {
    return -1;
  }
}

/**
 * @brief 扫描所有连接的USBCANFD设备
 * @param max_devices 最大扫描数量 (默认8)
 * @return 设备信息列表
 */
static std::vector<CanfdDeviceInfo> ScanDevices(int max_devices = 8) {
  std::vector<CanfdDeviceInfo> devices;

  for (int i = 0; i < max_devices; i++) {
    // 尝试打开设备
    if (!VCI_OpenDevice(DEVICE_TYPE_USBCANFD, i, 0)) {
      continue;  // 设备不存在，跳过
    }

    // 读取设备信息
    ZCAN_DEV_INF devInfo;
    memset(&devInfo, 0, sizeof(devInfo));
    if (VCI_ReadBoardInfo(DEVICE_TYPE_USBCANFD, i, &devInfo)) {
      CanfdDeviceInfo info;
      info.canfd_id = i;
      info.serial_number = std::string(reinterpret_cast<char*>(devInfo.sn), 20);
      info.device_name = std::string(reinterpret_cast<char*>(devInfo.id), 40);
      info.num_channels = devInfo.chn;

      // 去除尾部空格和空字符
      size_t pos = info.serial_number.find_last_not_of(" \0");
      if (pos != std::string::npos) info.serial_number.erase(pos + 1);
      pos = info.device_name.find_last_not_of(" \0");
      if (pos != std::string::npos) info.device_name.erase(pos + 1);

      devices.push_back(info);
      std::cout << "[INFO]: Found device " << i << ": " << info.device_name 
                << ", SN=" << info.serial_number 
                << ", Channels=" << (int)info.num_channels << std::endl;
    }

    // 关闭设备（扫描完成后）
    VCI_CloseDevice(DEVICE_TYPE_USBCANFD, i);
  }

  return devices;
}

int ZlgUsbcanfdSDK::FindDeviceBySerialNumber(const std::string& serial_number) {
  auto devices = ScanDevices();
  for (const auto& dev : devices) {
    if (dev.serial_number.find(serial_number) != std::string::npos) {
      return dev.canfd_id;
    }
  }
  return -1;  // 未找到
}

std::vector<int> ZlgUsbcanfdSDK::FindDevicesBySerialNumbers(const std::vector<std::string>& serial_numbers) {
  auto devices = ScanDevices();  // 只扫描一次
  std::vector<int> results(serial_numbers.size(), -1);
  
  for (size_t i = 0; i < serial_numbers.size(); i++) {
    for (const auto& dev : devices) {
      if (dev.serial_number.find(serial_numbers[i]) != std::string::npos) {
        results[i] = dev.canfd_id;
        break;
      }
    }
  }
  return results;
}
