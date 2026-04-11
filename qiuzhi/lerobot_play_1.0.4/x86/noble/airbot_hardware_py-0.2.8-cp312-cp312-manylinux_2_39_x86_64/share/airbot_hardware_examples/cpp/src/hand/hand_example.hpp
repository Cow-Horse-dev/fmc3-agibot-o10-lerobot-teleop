#pragma once

#include <algorithm>
#include <array>
#include <boost/asio.hpp>
#include <boost/json.hpp>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <vector>

#include "airbot_hardware/handlers/hand.hpp"

void print_hand_state(const airbot::hardware::HandState& state, const std::string& prefix = "") {
  std::cout << prefix << "Positions: ";
  for (auto v : state.positions) std::cout << v << " ";
  std::cout << " | Velocities: ";
  for (auto v : state.velocities) std::cout << v << " ";
  std::cout << " | Forces: ";
  for (auto v : state.forces) std::cout << v << " ";
  std::cout << std::endl;
}

airbot::hardware::DexterousHandTypes parse_hand_type(const std::string& type_str) {
  static const std::unordered_map<std::string, airbot::hardware::DexterousHandTypes> type_map = {
      {"INS_RH56DFX", airbot::hardware::DexterousHandTypes::INS_RH56DFX},
      {"INS_RH56BFX", airbot::hardware::DexterousHandTypes::INS_RH56BFX},
      {"INS_RH56E2", airbot::hardware::DexterousHandTypes::INS_RH56E2},
      {"INS_RH56F1", airbot::hardware::DexterousHandTypes::INS_RH56F1},
      {"BRAINCO_REVO1", airbot::hardware::DexterousHandTypes::BRAINCO_REVO1},
      {"BRAINCO_REVO2", airbot::hardware::DexterousHandTypes::BRAINCO_REVO2},
      {"ROH_LITES001", airbot::hardware::DexterousHandTypes::ROH_LITES001},
      {"ROH_A002", airbot::hardware::DexterousHandTypes::ROH_A002},
  };

  try {
    int num = std::stoi(type_str);
    return static_cast<airbot::hardware::DexterousHandTypes>(num);
  } catch (...) {
  }

  auto it = type_map.find(type_str);
  if (it != type_map.end()) return it->second;

  throw std::runtime_error("Unknown hand type: " + type_str);
}

// Function to create command JSON
boost::json::object commandToJson(const std::string& command_type, const std::vector<double>& positions,
                                  const std::vector<uint16_t>& hand_positions = {}) {
  boost::json::object json_obj;

  if (!positions.empty()) {
    boost::json::array pos_array;
    for (const auto& pos : positions) pos_array.push_back(pos);

    json_obj[command_type + "/position"] = pos_array;
  }

  // Add hand positions if provided
  if (!hand_positions.empty()) {
    boost::json::array hand_array;
    for (const auto& pos : hand_positions) hand_array.push_back(pos);
    json_obj[command_type + "/hand_position"] = hand_array;
  }

  json_obj["timestamp"] = static_cast<double>(std::chrono::duration_cast<std::chrono::microseconds>(
                                                  std::chrono::steady_clock::now().time_since_epoch())
                                                  .count()) /
                          1e6;

  return json_obj;
}

inline boost::json::object commandToJson(const airbot::hardware::HandState& state,
                                         const std::string& command_type = "state") {
  boost::json::object json_obj;

  boost::json::array name_array;
  for (const auto& name : airbot::hardware::HandState::names) {
    switch (name) {
      case airbot::hardware::MotorName::ThumbFlex:
        name_array.push_back("ThumbFlex");
        break;
      case airbot::hardware::MotorName::ThumbAux:
        name_array.push_back("ThumbAux");
        break;
      case airbot::hardware::MotorName::Index:
        name_array.push_back("Index");
        break;
      case airbot::hardware::MotorName::Middle:
        name_array.push_back("Middle");
        break;
      case airbot::hardware::MotorName::Ring:
        name_array.push_back("Ring");
        break;
      case airbot::hardware::MotorName::Pinky:
        name_array.push_back("Pinky");
        break;
      default:
        name_array.push_back("Unknown");
        break;
    }
  }
  json_obj["name"] = name_array;

  // 位置
  boost::json::array pos_array;
  for (const auto& pos : state.positions) pos_array.push_back(pos);
  json_obj[command_type + "/position"] = pos_array;

  // 速度
  boost::json::array vel_array;
  for (const auto& vel : state.velocities) vel_array.push_back(vel);
  json_obj[command_type + "/velocity"] = vel_array;

  // 力
  boost::json::array force_array;
  for (const auto& force : state.forces) force_array.push_back(force);
  json_obj[command_type + "/force"] = force_array;

  // 时间戳
  json_obj["timestamp"] = static_cast<double>(std::chrono::duration_cast<std::chrono::microseconds>(
                                                  std::chrono::steady_clock::now().time_since_epoch())
                                                  .count()) /
                          1e6;

  return json_obj;
}

inline std::string to_string(const airbot::hardware::HandState& state) {
  std::ostringstream oss;

  // 电机名称
  oss << "name: [";
  for (size_t i = 0; i < airbot::hardware::HandState::names.size(); ++i) {
    switch (airbot::hardware::HandState::names[i]) {
      case airbot::hardware::MotorName::ThumbFlex:
        oss << "ThumbFlex";
        break;
      case airbot::hardware::MotorName::ThumbAux:
        oss << "ThumbAux";
        break;
      case airbot::hardware::MotorName::Index:
        oss << "Index";
        break;
      case airbot::hardware::MotorName::Middle:
        oss << "Middle";
        break;
      case airbot::hardware::MotorName::Ring:
        oss << "Ring";
        break;
      case airbot::hardware::MotorName::Pinky:
        oss << "Pinky";
        break;
      default:
        oss << "Unknown";
        break;
    }
    if (i < airbot::hardware::HandState::names.size() - 1) oss << ",";
  }
  oss << "]\n";

  // 位置信息
  oss << "pos: [";
  for (size_t i = 0; i < state.positions.size(); ++i) {
    oss << state.positions[i];
    if (i < state.positions.size() - 1) oss << ",";
  }
  oss << "]\n";

  // 速度信息
  oss << "vel: [";
  for (size_t i = 0; i < state.velocities.size(); ++i) {
    oss << state.velocities[i];
    if (i < state.velocities.size() - 1) oss << ",";
  }
  oss << "]\n";

  // 力信息
  oss << "force: [";
  for (size_t i = 0; i < state.forces.size(); ++i) {
    oss << state.forces[i];
    if (i < state.forces.size() - 1) oss << ",";
  }
  oss << "]";

  return oss.str();
}
