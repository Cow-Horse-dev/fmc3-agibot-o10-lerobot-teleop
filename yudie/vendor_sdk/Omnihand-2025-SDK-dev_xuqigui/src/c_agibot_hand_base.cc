/*
 * @Author: huangshiheng@agibot.com
 * @Date: 2025-11-10 17:22:05
 * @LastEditors: huangshiheng
 * @LastEditTime: 2025-11-10 17:34:35
 * @FilePath: /Omnihand-2025-SDK/src/c_agibot_hand_base.cc
 * @Description: 
 * 
 * Copyright (c) 2025 by huangshiheng@agibot.com, All Rights Reserved. 
 */
// Copyright (c) 2025, Agibot Co., Ltd.
// OmniHand 2025 SDK is licensed under Mulan PSL v2.

#include <c_agibot_hand_base.h>
#include "implementation/c_agibot_hand_can/c_agibot_hand_can.h"
#include "implementation/c_agibot_hand_rs/c_agibot_hand_rs.h"

namespace YAML {
template <>
struct convert<AgibotHandO10::HardwareConf> {
  static bool decode(const Node& node, AgibotHandO10::HardwareConf& hardware_conf) {
    if (!node.IsMap()) return false;
    if (node["type"]) {
      hardware_conf.device = node["type"].as<std::string>();
    }
    if (node["options"]) {
      hardware_conf.options = node["options"];
    } else {
      hardware_conf.options = YAML::Node(YAML::NodeType::Null);
    }
    return true;
  }
};
}  // namespace YAML

std::unique_ptr<AgibotHandO10> AgibotHandO10::createHand(
    EHandType hand_type,
    unsigned char device_id,
    unsigned char canfd_id,
    unsigned char channel_id) {
  std::unique_ptr<AgibotHandO10> hand;

  hand = std::make_unique<AgibotHandCanO10>(canfd_id, channel_id);

  hand->Reset(device_id, hand_type);

  return hand;
}

int AgibotHandO10::findCanfdIdBySerialNumber(const std::string& serial_number) {
  return AgibotHandCanO10::FindCanfdIdBySerialNumber(serial_number);
}

std::vector<int> AgibotHandO10::findCanfdIdsBySerialNumbers(const std::vector<std::string>& serial_numbers) {
  return AgibotHandCanO10::FindCanfdIdsBySerialNumbers(serial_numbers);
}
