#include <argparse/argparse.hpp>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <iostream>
#include <ostream>
#include <thread>

#include "./hand_example.hpp"
#include "airbot_hardware/executors/executor.hpp"
#include "airbot_hardware/handlers/hand.hpp"

using namespace airbot::hardware;
using namespace std::chrono_literals;

std::atomic<bool> stop_flag{false};

void signal_handler(int signal) {
  if (signal == SIGINT) {
    std::cout << "\n[Signal] Caught Ctrl+C, preparing to stop..." << std::endl;
    stop_flag = true;
  }
}

bool all_target(const std::vector<uint16_t>& current_pos, const std::array<uint16_t, 6>& target_pos, double tol = 20) {
  for (size_t i = 0; i < 6; i++)
    if (std::abs(current_pos[i] - target_pos[i]) > tol) return false;
  return true;
}

int main(int argc, char* argv[]) {
  // 注册 Ctrl+C 信号
  std::signal(SIGINT, signal_handler);

  argparse::ArgumentParser program("airbot_ins_hand_ctrl");

  program.add_argument("-j", "--joints")
      .default_value(std::vector<uint16_t>{0, 0, 0, 0, 0, 0})
      .help("Target joint positions for the hand (6 values)")
      .nargs(6)
      .scan<'u', uint16_t>();

  program.add_argument("-t", "--type")
      .default_value(std::string("INS_RH56F1"))
      .help("Specify the DexterousHand type, e.g. INS_RH56F1, INS_RH56E2, or numeric code (0-255)");

  program.add_argument("--hand-id").help("Specify the hand device ID (default: 1)").default_value(1).scan<'i', int>();

  try {
    program.parse_args(argc, argv);
  } catch (const std::exception& err) {
    std::cerr << err.what() << std::endl;
    std::cerr << program;
    return 1;
  }

  DexterousHandTypes hand_type;
  try {
    hand_type = parse_hand_type(program.get<std::string>("-t"));
  } catch (const std::exception& e) {
    std::cerr << e.what() << std::endl;
    return 1;
  }

  int hand_id = program.get<int>("--hand-id");

  std::array<uint16_t, 6> target_pos{};
  auto joint_values = program.get<std::vector<uint16_t>>("-j");
  std::copy_n(joint_values.begin(), 6, target_pos.begin());

  auto executor = AsioExecutor::create(3);

  auto hand = DexterousHand::create(static_cast<uint8_t>(hand_id), hand_type);

  std::cout << "[Init] Initializing hand type: " << static_cast<int>(hand_type) << " with ID: " << hand_id << std::endl;

  if (!hand->init(executor->get_io_context(), "can0", 250)) {
    std::cerr << "[Error] Failed to initialize hand!" << std::endl;
    return 1;
  }

  hand->update_state();

  std::this_thread::sleep_for(20ms);
  auto start_time = std::chrono::steady_clock::now();
  HandState state = hand->state();
  print_hand_state(state, "first hand_state: ");

  std::cout << "[Running] Press Ctrl+C to stop." << std::endl;

  while (!stop_flag && !all_target(std::vector<uint16_t>(state.positions.begin(), state.positions.end()), target_pos) &&
         std::chrono::steady_clock::now() - start_time < 10s) {
    hand->update_state();

    HandState hand_cmd;
    std::copy_n(target_pos.begin(), 6, hand_cmd.positions.begin());
    std::fill_n(hand_cmd.velocities.begin(), 6, 1000);
    // std::fill_n(hand_cmd.forces.begin(), 6, 50);

    hand->set_pos(hand_cmd);
    state = hand->state();
    print_hand_state(state, "hand_state: ");
    std::this_thread::sleep_for(15ms);
  }

  std::cout << "\n[Shutdown] Uninitializing hand..." << std::endl;
  hand->uninit();
  std::cout << "[Exit] Program terminated safely." << std::endl;

  return 0;
}
