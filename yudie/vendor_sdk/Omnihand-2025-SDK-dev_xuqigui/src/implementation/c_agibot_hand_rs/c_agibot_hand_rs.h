// Copyright (c) 2025, Agibot Co., Ltd.
// OmniHand 2025 SDK is licensed under Mulan PSL v2.

#pragma once

#include "c_agibot_hand_base.h"
#include "export_symbols.h"
#include "proto.h"
#include "rs_485_device/rs_485_device.h"
#include "yaml-cpp/yaml.h"

#define DEFAULT_DEVICE_ID 0x01

#define DISABLE_FUNC 1

constexpr uint8_t HEADER[] = {0xEE, 0xAA, 0x1, 0x0};

class AGIBOT_EXPORT AgibotHandRsO10 : public AgibotHandO10 {
 public:
  struct Options {
    std::string uart_port = "/dev/ttyUSB0";
    int32_t uart_baudrate = 460800;
  };

 public:
  explicit AgibotHandRsO10();

  ~AgibotHandRsO10() override = default;

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

  std::vector<int16_t> GetAllJointMotorTorque() const override;
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

 protected:
  mutable std::unique_ptr<UartRs485Interface> handrs485_interface_;
};
