// Copyright (c) 2025, Agibot Co., Ltd.
// OmniHand 2025 SDK is licensed under Mulan PSL v2.

/**
 * @file c_agibot_hand_base.h
 * @brief 灵巧手基类
 * @author WSJ
 * @date 25-8-1
 **/

#pragma once

#include <memory>
#include <string>
#include <vector>
#include "export_symbols.h"
#include "kinematics_solver/kinematics_solver.h"
#include "proto.h"
#include "yaml-cpp/yaml.h"

#define DEFAULT_DEVICE_ID 0x01
#define DISABLE_FUNC 1

/**
 * @brief 灵巧手基类
 */
class AGIBOT_EXPORT AgibotHandO10 {
 public:
  struct HardwareConf {
    std::string device = "can";
    YAML::Node options;
  };

 public:
  /**
   * @brief 工厂方法，创建具体的灵巧手实例
   * @param hand_type 手型(左手/右手)
   * @param device_id 设备Id
   * @param canfd_id USB CANFD 适配器设备索引
   * @param channel_id CAN通道索引 (默认为0，USBCANFD-200U有2个通道)
   */
  static std::unique_ptr<AgibotHandO10> createHand(
      EHandType hand_type,
      unsigned char device_id = DEFAULT_DEVICE_ID,
      unsigned char canfd_id = 0,
      unsigned char channel_id = 0);

  /**
   * @brief 通过序列号查找canfd_id
   * @param serial_number 设备序列号 (支持部分匹配)
   * @return canfd_id，找不到返回 -1
   */
  static int findCanfdIdBySerialNumber(const std::string& serial_number);

  /**
   * @brief 批量通过序列号查找canfd_id（只扫描一次）
   * @param serial_numbers 序列号列表
   * @return canfd_id列表，找不到的位置返回 -1
   */
  static std::vector<int> findCanfdIdsBySerialNumbers(const std::vector<std::string>& serial_numbers);
  /**
   * @brief 构造函数
   * @param device_id 设备Id
   * @param hand_type 手型(左手/右手)
   */

  AgibotHandO10() = default;
  virtual ~AgibotHandO10() = default;

  bool Init() {
    return is_init_;
  }

  // 基本信息接口
  virtual VendorInfo GetVendorInfo() const = 0;
  virtual DeviceInfo GetDeviceInfo() const = 0;
  virtual void SetDeviceId(unsigned char device_id) = 0;

  // 关节电机位置控制
  virtual void SetJointMotorPosi(unsigned char joint_motor_index, int16_t posi) = 0;
  virtual int16_t GetJointMotorPosi(unsigned char joint_motor_index) const = 0;
  virtual void SetAllJointMotorPosi(const std::vector<int16_t>& vec_posi) = 0;
  virtual std::vector<int16_t> GetAllJointMotorPosi() const = 0;

  // 关节角度控制
  virtual void SetAllActiveJointAngles(const std::vector<double>& angles) = 0;
  virtual std::vector<double> GetAllActiveJointAngles() const = 0;
  virtual std::vector<double> GetAllJointAngles() const = 0;
  virtual std::vector<double> GetAllJointPos(const std::vector<double>& active_joint_pos) const = 0;

  // 速度控制
  virtual void SetJointMotorVelo(unsigned char joint_motor_index, int16_t velo) = 0;
  virtual int16_t GetJointMotorVelo(unsigned char joint_motor_index) const = 0;
  virtual void SetAllJointMotorVelo(const std::vector<int16_t>& vec_velo) = 0;
  virtual std::vector<int16_t> GetAllJointMotorVelo() const = 0;

  // 传感器接口
  virtual std::vector<uint8_t> GetTactileSensorData(EFinger eFinger) const = 0;

  // 控制模式
  virtual void SetControlMode(unsigned char joint_motor_index, EControlMode mode) = 0;
  virtual EControlMode GetControlMode(unsigned char joint_motor_index) const = 0;
  virtual void SetAllControlMode(const std::vector<unsigned char>& ctrl_modes) = 0;
  virtual std::vector<unsigned char> GetAllControlMode() const = 0;

  // 电流控制
  virtual void SetCurrentThreshold(unsigned char joint_motor_index, int16_t current_threshold) = 0;
  virtual int16_t GetCurrentThreshold(unsigned char joint_motor_index) const = 0;
  virtual void SetAllCurrentThreshold(const std::vector<int16_t>& current_thresholds) = 0;
  virtual std::vector<int16_t> GetAllCurrentThreshold() const = 0;

  // 混合控制
  virtual void MixCtrlJointMotor(const std::vector<MixCtrl>& mix_ctrls) = 0;

  // 错误报告
  virtual JointMotorErrorReport GetErrorReport(unsigned char joint_motor_index) const = 0;
  virtual std::vector<JointMotorErrorReport> GetAllErrorReport() const = 0;
#if !DISABLE_FUNC
  virtual void SetErrorReportPeriod(unsigned char joint_motor_index, uint16_t period) = 0;
  virtual void SetAllErrorReportPeriod(std::vector<uint16_t> vec_period) = 0;
#endif
  // 温度报告
  virtual uint16_t GetTemperatureReport(unsigned char joint_motor_index) const = 0;
  virtual std::vector<uint16_t> GetAllTemperatureReport() const = 0;
#if !DISABLE_FUNC
  virtual void SetTemperReportPeriod(unsigned char joint_motor_index, uint16_t period) = 0;
  virtual void SetAllTemperReportPeriod(std::vector<uint16_t> vec_period) = 0;
#endif
  // 电流报告
  virtual int16_t GetCurrentReport(unsigned char joint_motor_index) const = 0;
  virtual std::vector<uint16_t> GetAllCurrentReport() const = 0;
#if !DISABLE_FUNC
  virtual void SetCurrentReportPeriod(unsigned char joint_motor_index, uint16_t period) = 0;
  virtual void SetAllCurrentReportPeriod(std::vector<uint16_t> vec_period) = 0;
#endif
  // 调试接口
  virtual void ShowDataDetails(bool show) const = 0;

 protected:
  // todo OTA

 protected:
  void Reset(unsigned char device_id, EHandType hand_type) {
    device_id_ = device_id;
    is_left_hand_ = (hand_type == EHandType::eLeft);
    kinematics_solver_ptr_ = std::make_unique<OmnihandCtrl>(is_left_hand_);
  }

  std::unique_ptr<OmnihandCtrl> kinematics_solver_ptr_;
  unsigned char device_id_{DEFAULT_DEVICE_ID};
  bool is_left_hand_{true};

  bool is_init_{false};
};
