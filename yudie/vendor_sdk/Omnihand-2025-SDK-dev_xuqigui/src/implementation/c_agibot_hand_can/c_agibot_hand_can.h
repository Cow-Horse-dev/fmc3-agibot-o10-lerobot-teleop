// Copyright (c) 2025, Agibot Co., Ltd.
// OmniHand 2025 SDK is licensed under Mulan PSL v2.

#pragma once

#include <queue>
#include "c_agibot_hand_base.h"
#include "can_bus_device/c_can_bus_device.h"
#include "export_symbols.h"
#include "proto.h"
#include "yaml-cpp/yaml.h"

#define DEFAULT_DEVICE_ID 0x01
#define DISABLE_FUNC 1

class AGIBOT_EXPORT AgibotHandCanO10 : public AgibotHandO10 {
 public:
  struct Options {
    std::string can_driver = "zlg";
  };
  
  /**
   * @brief 通过序列号查找设备
   * @param serial_number 设备序列号
   * @return canfd_id，如果未找到返回-1
   */
  static int FindCanfdIdBySerialNumber(const std::string& serial_number);
  
  /**
   * @brief 通过序列号列表批量查找设备（只扫描一次）
   * @param serial_numbers 序列号列表
   * @return canfd_id列表，未找到的返回-1
   */
  static std::vector<int> FindCanfdIdsBySerialNumbers(const std::vector<std::string>& serial_numbers);

 public:
  explicit AgibotHandCanO10(unsigned char canfd_id, unsigned char channel_id = 0);

  ~AgibotHandCanO10() override = default;

  VendorInfo GetVendorInfo() const override;

  DeviceInfo GetDeviceInfo() const override;

  void SetDeviceId(unsigned char device_id) override;

  void SetJointMotorPosi(unsigned char joint_motor_index, int16_t posi) override;

  int16_t GetJointMotorPosi(unsigned char joint_motor_index) const override;

  void SetAllJointMotorPosi(const std::vector<int16_t>& vec_posi) override;

  std::vector<int16_t> GetAllJointMotorPosi() const override;
#if !DISABLE_FUNC

  void SetActiveJointAngle(unsigned char joint_motor_index, double angle) override;

  double GetActiveJointAngle(unsigned char joint_motor_index) const override;
#endif

  void SetAllActiveJointAngles(const std::vector<double>& angles) override;

  std::vector<double> GetAllActiveJointAngles() const override;

  std::vector<double> GetAllJointAngles() const override;

  std::vector<double> GetAllJointPos(const std::vector<double> &active_joint_pos) const override;

#if !DISABLE_FUNC

  void SetJointMotorTorque(unsigned char joint_motor_index, int16_t torque) override;

  int16_t GetJointMotorTorque(unsigned char joint_motor_index) const override;

  void SetAllJointMotorTorque(const std::vector<int16_t>& vec_torque) override;

  std::vector<int16_t> GetAllJointMotorTorque() const;
#endif

  void SetJointMotorVelo(unsigned char joint_motor_index, int16_t velo) override;

  int16_t GetJointMotorVelo(unsigned char joint_motor_index) const override;

  void SetAllJointMotorVelo(const std::vector<int16_t>& vec_velo) override;

  std::vector<int16_t> GetAllJointMotorVelo() const override;

  std::vector<uint8_t> GetTactileSensorData(EFinger eFinger) const override;

  void SetControlMode(unsigned char joint_motor_index, EControlMode mode) override;

  EControlMode GetControlMode(unsigned char joint_motor_index) const override;

  void SetAllControlMode(const std::vector<unsigned char>& ctrl_modes) override;

  std::vector<unsigned char> GetAllControlMode() const override;

  void SetCurrentThreshold(unsigned char joint_motor_index, int16_t current_threshold) override;

  int16_t GetCurrentThreshold(unsigned char joint_motor_index) const override;

  void SetAllCurrentThreshold(const std::vector<int16_t>& current_thresholds) override;

  std::vector<int16_t> GetAllCurrentThreshold() const override;

  void MixCtrlJointMotor(const std::vector<MixCtrl>& mix_ctrls) override;

  JointMotorErrorReport GetErrorReport(unsigned char joint_motor_index) const override;

  std::vector<JointMotorErrorReport> GetAllErrorReport() const override;

#if !DISABLE_FUNC
  void SetErrorReportPeriod(unsigned char joint_motor_index, uint16_t period) override;

  void SetAllErrorReportPeriod(std::vector<uint16_t> vec_period) override;
#endif
  uint16_t GetTemperatureReport(unsigned char joint_motor_index) const override;

  std::vector<uint16_t> GetAllTemperatureReport() const override;
#if !DISABLE_FUNC
  void SetTemperReportPeriod(unsigned char joint_motor_index, uint16_t period) override;

  void SetAllTemperReportPeriod(std::vector<uint16_t> vec_period) override;
#endif
  int16_t GetCurrentReport(unsigned char joint_motor_index) const override;

  std::vector<uint16_t> GetAllCurrentReport() const override;
#if !DISABLE_FUNC
  void SetCurrentReportPeriod(unsigned char joint_motor_index, uint16_t period) override;

  void SetAllCurrentReportPeriod(std::vector<uint16_t> vec_period) override;
#endif
  void ShowDataDetails(bool show) const override;

 private:
  void ProcessMsg(CanfdFrame frame);

  bool JudgeMsgMatch(unsigned int req_id, unsigned int rep_id);

  unsigned int GetMatchedRepId(unsigned int req_id);

  void UpdateFirmware(std::string file_name);

  void SendPackage();

  void GetUpgradeResult();

  mutable std::unique_ptr<CanBusDeviceBase> canfd_device_;

#if !DISABLE_FUNC
  std::mutex mutex_temper_report_;
  std::vector<uint16_t> vec_temper_report_;

  std::mutex mutex_current_report_;
  std::vector<uint16_t> vec_current_report_;
#endif
  std::queue<std::array<char, 2048> > que_packages_;
};
