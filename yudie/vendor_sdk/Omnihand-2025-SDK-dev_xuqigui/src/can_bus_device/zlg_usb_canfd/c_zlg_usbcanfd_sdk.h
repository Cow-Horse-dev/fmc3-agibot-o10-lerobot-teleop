// Copyright (c) 2025, Agibot Co., Ltd.
// OmniHand 2025 SDK is licensed under Mulan PSL v2.

/**
 * @file c_zlg_usbcanfd_sdk.h
 * @brief
 * @author WSJ
 * @date 25-7-28
 **/

#pragma once

#include "../c_can_bus_device.h"
#include <map>
#include <mutex>
#include <string>
#include <vector>

/**
 * @brief CANFD设备信息结构
 */
struct CanfdDeviceInfo {
  unsigned char canfd_id;      // 设备索引
  std::string serial_number;   // 设备序列号
  std::string device_name;     // 设备名称 (如 "USBCANFD-100U-mini")
  unsigned char num_channels;  // 通道数量
};

/**
 * @brief 基于周立功usbcanfd的SDK的CAN Device类
 * 支持同一设备的多通道使用（设备只打开一次，每个通道独立初始化）
 */
class ZlgUsbcanfdSDK : public CanBusDeviceBase {
 public:
  ZlgUsbcanfdSDK(unsigned char canfd_id = 0, unsigned char channel_id = 0);

  ~ZlgUsbcanfdSDK() override;

  int OpenDevice() override;

  int CloseDevice() override;

  void RecvFrame() override;

  int SendFrame(unsigned int id, unsigned char* data, unsigned char length) override;

  bool IsInit() override;

  /**
   * @brief 通过序列号查找canfd_id
   * @param serial_number 设备序列号 (支持部分匹配)
   * @return canfd_id，找不到返回 -1
   */
  static int FindDeviceBySerialNumber(const std::string& serial_number);

  /**
   * @brief 批量通过序列号查找canfd_id（只扫描一次）
   * @param serial_numbers 序列号列表
   * @return canfd_id列表，找不到的位置返回 -1
   */
  static std::vector<int> FindDevicesBySerialNumbers(const std::vector<std::string>& serial_numbers);

 private:
  unsigned char canfd_id_;
  unsigned char channel_id_;

  // 静态设备管理：跟踪每个设备的打开状态和引用计数
  static std::mutex device_mutex_;
  static std::map<unsigned char, int> device_ref_count_;  // canfd_id -> 引用计数
};
