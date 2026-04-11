#pragma once

#ifndef AB_API
#define AB_API __attribute__((visibility("default")))
#endif

#include <array>
#include <cstdint>
#include <memory>
#include <string>
#include <string_view>
#include <unordered_map>

#include "airbot_hardware/executors/executor.hpp"
#include "airbot_hardware/utils.hpp"

namespace airbot {
namespace hardware {

/**
 * @brief Enum representing motor names in a dexterous hand.
 */
enum class AB_API MotorName : uint8_t {
  ThumbFlex = 0, /**< Thumb flex motor */
  ThumbAux = 1,  /**< Thumb auxiliary motor */
  Index = 2,     /**< Index finger motor */
  Middle = 3,    /**< Middle finger motor */
  Ring = 4,      /**< Ring finger motor */
  Pinky = 5,     /**< Pinky finger motor */
  Count = 6      /**< Total number of motors */
};

/**
 * @brief Struct representing the state of a dexterous hand.
 *
 * Contains positions, velocities, and force feedback for each finger motor.
 */
struct AB_API HandState {
  /** @brief Standard order of motor names. */
  static constexpr std::array<MotorName, 6> names = {MotorName::ThumbFlex, MotorName::ThumbAux, MotorName::Index,
                                                     MotorName::Middle,    MotorName::Ring,     MotorName::Pinky};

  /** @brief Joint positions for each finger (0~1000; 0=open, 1000=closed). */
  std::array<uint16_t, 6> positions{};

  /** @brief Joint velocities for each finger (-1000~1000). */
  std::array<int16_t, 6> velocities{};

  /** @brief Force feedback for each finger. */
  std::array<int32_t, 6> forces{};
};

/**
 * @brief Enum representing supported dexterous hand types.
 */
enum class DexterousHandTypes : uint8_t {
  INS_RH56DFX = 0x0, /**< INSPIRE RH56 DFX Dexterous Hand */
  INS_RH56BFX = 0x1, /**< INSPIRE RH56 BFX Dexterous Hand */
  INS_RH56E2 = 0x2,  /**< INSPIRE RH56 E2 Dexterous Hand */
  INS_RH56F1 = 0x3,  /**< INSPIRE RH56 F1 Dexterous Hand */

  BRAINCO_REVO1 = 0x20, /**< BrainCo Revo 1 Dexterous Hand */
  BRAINCO_REVO2 = 0x21, /**< BrainCo Revo 2 Dexterous Hand */

  ROH_LITES001 = 0x40, /**< OYMotion LITES001 Dexterous Hand */
  ROH_A002 = 0x41      /**< OYMotion A002 Dexterous Hand */
};

/**
 * @brief Abstract base class representing a generic dexterous hand.
 *
 * This interface supports multiple robotic hand models and provides
 * a unified way to control them and query or modify their parameters.
 */
class AB_API DexterousHand {
 public:
  /**
   * @brief Factory method to create a new dexterous hand instance.
   * @param id Device ID of the hand.
   * @param type Type of the hand model.
   * @return Unique pointer to the created DexterousHand instance.
   */
  [[nodiscard]] static std::unique_ptr<DexterousHand> create(const uint8_t id, DexterousHandTypes type) noexcept;

  /** @brief Virtual destructor. */
  virtual ~DexterousHand() = default;

  /**
   * @brief Initialize the hand.
   *
   * @param io_context Executor providing asynchronous IO handling.
   * @param interface Communication interface name (e.g., "can0").
   * @param spin_freq Control loop frequency in Hz.
   * @return True if successfully initialized, false otherwise.
   */
  virtual bool init(ExecutorPtr io_context, const std::string& interface, uint16_t spin_freq) = 0;

  /**
   * @brief Uninitialize the hand and release resources.
   * @return True if uninitialized successfully.
   */
  virtual bool uninit() noexcept = 0;

  /**
   * @brief Send a target position command to the hand.
   *
   * @param cmd Desired hand state (positions and optionally velocities).
   * @return True if the command was sent successfully.
   */
  virtual bool set_pos(const HandState& cmd) = 0;

  /**
   * @brief Send a target force command to the hand.
   *
   * @param cmd Desired force values for each finger.
   * @return True if the command was sent successfully.
   */
  virtual bool set_force(const HandState& cmd) = 0;

  /**
   * @brief Set a configuration parameter for the hand.
   *
   * The available parameters depend on the specific hand model.
   * For example, BrainCo Revo2 supports "hand_side", "unit_mode", "id_485", and "baudrate".
   *
   * @param name Parameter name (case-sensitive).
   * @param value Parameter value and type.
   * @return True if the parameter was accepted; false if unsupported.
   */
  virtual bool set_param(const std::string_view name, const ParamValue value) noexcept = 0;

  /**
   * @brief Request to update (read) a specific parameter from the hardware.
   *
   * @param name Parameter name to be updated.
   * @return True if the request was accepted; false if the parameter is unsupported.
   */
  virtual bool update_param(const std::string_view name) noexcept = 0;

  /**
   * @brief Retrieve all parameters currently supported by this hand instance.
   *
   * Each hand type exposes a different subset. Example:
   *
   * - BrainCo Revo2 → "hand_side", "unit_mode", "id_485", "baudrate"
   * - INS RH56BFX → "hand_id", "baudrate", "current", "pos_act"
   * - ROH A002 → "hand_id"
   *
   * @return Map of parameter names and their last known values.
   */
  virtual std::unordered_map<std::string_view, ParamValue> params() const noexcept = 0;

  /**
   * @brief Update the hand’s current measured state (positions, velocities, etc.).
   * @return True if the state was successfully updated from the device.
   */
  virtual bool update_state() noexcept = 0;

  /**
   * @brief Get the latest known hand state.
   * @return The last retrieved HandState structure.
   */
  virtual HandState state() const noexcept = 0;

  /**
   * @brief Get the model type of this dexterous hand.
   * @return The corresponding DexterousHandTypes enumeration.
   */
  virtual DexterousHandTypes type() const noexcept = 0;
};

}  // namespace hardware
}  // namespace airbot
