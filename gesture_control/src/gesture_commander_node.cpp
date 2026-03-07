/**
 * gesture_commander_node.cpp
 *
 * ROS2 node that subscribes to /gesture_detection, applies debounce + confidence
 * filtering, and executes robot commands via MoveGroupInterface (arm) and a
 * FollowJointTrajectory action client (gripper).
 *
 * Topics subscribed:
 *   /gesture_detection  (gesture_control/msg/GestureDetection)
 *
 * Topics published:
 *   /gesture_command    (std_msgs/String)   — executed gesture label, for monitoring
 *
 * Gesture mapping:
 *   thumbs_up → MoveIt2 named pose "home"
 *   point     → Y_joint + point_delta_rad (raise arm)
 *   open      → Left_jaw_joint → gripper_open_pos
 *   fist      → Left_jaw_joint → gripper_closed_pos
 *   none      → move_group.stop() (hold current position)
 */

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <std_msgs/msg/string.hpp>

#include <moveit/move_group_interface/move_group_interface.h>

#include <control_msgs/action/follow_joint_trajectory.hpp>
#include <trajectory_msgs/msg/joint_trajectory.hpp>
#include <trajectory_msgs/msg/joint_trajectory_point.hpp>

#include <deque>
#include <atomic>
#include <thread>
#include <mutex>
#include <algorithm>
#include <cmath>
#include <chrono>

#include "gesture_control/msg/gesture_detection.hpp"

using GestureDetection     = gesture_control::msg::GestureDetection;
using FollowJointTraj      = control_msgs::action::FollowJointTrajectory;
using MoveGroupInterface   = moveit::planning_interface::MoveGroupInterface;

// Y_joint limits (degrees → radians, from ros2_controllers.yaml)
static constexpr double Y_LOWER_RAD = -100.0 * M_PI / 180.0;   // -1.7453 rad
static constexpr double Y_UPPER_RAD =  135.0 * M_PI / 180.0;   //  2.3562 rad

// ─────────────────────────────────────────────────────────────────────────────

class GestureCommanderNode : public rclcpp::Node
{
public:
  GestureCommanderNode()
  : Node("gesture_commander_node"),
    executing_(false)
  {
    // ── Parameters ────────────────────────────────────────────────────────────
    this->declare_parameter("confidence_threshold", 0.70);
    this->declare_parameter("stability_frames",     3);
    this->declare_parameter("command_cooldown_sec", 2.0);
    this->declare_parameter("point_delta_rad",      0.3);
    this->declare_parameter("gripper_open_pos",     0.015);
    this->declare_parameter("gripper_closed_pos",   0.0);

    confidence_threshold_ = this->get_parameter("confidence_threshold").as_double();
    stability_frames_     = this->get_parameter("stability_frames").as_int();
    command_cooldown_sec_ = this->get_parameter("command_cooldown_sec").as_double();
    point_delta_rad_      = this->get_parameter("point_delta_rad").as_double();
    gripper_open_pos_     = this->get_parameter("gripper_open_pos").as_double();
    gripper_closed_pos_   = this->get_parameter("gripper_closed_pos").as_double();

    // ── Subscriber ───────────────────────────────────────────────────────────
    gesture_sub_ = this->create_subscription<GestureDetection>(
      "/gesture_detection", 10,
      std::bind(&GestureCommanderNode::gestureCallback, this, std::placeholders::_1));

    // ── Publisher ────────────────────────────────────────────────────────────
    cmd_pub_ = this->create_publisher<std_msgs::msg::String>("/gesture_command", 10);

    // ── Gripper action client ─────────────────────────────────────────────────
    gripper_client_ = rclcpp_action::create_client<FollowJointTraj>(
      this, "/arctos_hand_controller/follow_joint_trajectory");

    last_command_time_ = this->now();

    RCLCPP_INFO(this->get_logger(), "GestureCommanderNode created (move_group not yet ready)");
  }

  /**
   * Call from main() after the node is managed by a shared_ptr and the
   * executor has started spinning. MoveGroupInterface requires the node
   * to be alive and processing callbacks while it connects to move_group.
   */
  void setupMoveGroup(const std::shared_ptr<rclcpp::Node> & node)
  {
    move_group_ = std::make_shared<MoveGroupInterface>(node, "denso_arm");
    move_group_->setMaxVelocityScalingFactor(0.3);
    move_group_->setMaxAccelerationScalingFactor(0.3);
    RCLCPP_INFO(this->get_logger(),
                "MoveGroupInterface ready  [group=denso_arm  planning_frame=%s]",
                move_group_->getPlanningFrame().c_str());
  }

private:
  // ── Parameters ─────────────────────────────────────────────────────────────
  double confidence_threshold_;
  int    stability_frames_;
  double command_cooldown_sec_;
  double point_delta_rad_;
  double gripper_open_pos_;
  double gripper_closed_pos_;

  // ── State ───────────────────────────────────────────────────────────────────
  std::deque<std::string> gesture_buffer_;
  std::mutex              buffer_mutex_;
  rclcpp::Time            last_command_time_;
  std::atomic<bool>       executing_;

  // ── ROS interfaces ──────────────────────────────────────────────────────────
  rclcpp::Subscription<GestureDetection>::SharedPtr gesture_sub_;
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr cmd_pub_;
  rclcpp_action::Client<FollowJointTraj>::SharedPtr gripper_client_;

  // ── MoveIt2 ─────────────────────────────────────────────────────────────────
  std::shared_ptr<MoveGroupInterface> move_group_;

  // ── Gesture callback ────────────────────────────────────────────────────────

  void gestureCallback(const GestureDetection & msg)
  {
    if (!move_group_) {
      return;  // Not yet initialised
    }

    // 1. Filter by confidence
    if (msg.confidence < static_cast<float>(confidence_threshold_)) {
      return;
    }

    // 2. Update rolling buffer
    std::string gesture;
    {
      std::lock_guard<std::mutex> lock(buffer_mutex_);
      gesture_buffer_.push_back(msg.label);
      if (static_cast<int>(gesture_buffer_.size()) > stability_frames_) {
        gesture_buffer_.pop_front();
      }
      if (static_cast<int>(gesture_buffer_.size()) < stability_frames_) {
        return;
      }

      // 3. Check stability: all N entries must be the same
      const std::string & front = gesture_buffer_.front();
      bool all_same = std::all_of(
        gesture_buffer_.begin(), gesture_buffer_.end(),
        [&front](const std::string & s) { return s == front; });
      if (!all_same) {
        return;
      }
      gesture = front;
    }

    // 4. Check cooldown
    double elapsed = (this->now() - last_command_time_).seconds();
    if (elapsed < command_cooldown_sec_) {
      return;
    }

    // 5. Skip if a command is already executing
    if (executing_.load()) {
      return;
    }

    // 6. Commit: reset state, launch execution thread
    last_command_time_ = this->now();
    {
      std::lock_guard<std::mutex> lock(buffer_mutex_);
      gesture_buffer_.clear();
    }
    executing_ = true;

    RCLCPP_INFO(this->get_logger(),
                "Gesture triggered: '%s'  (conf=%.2f)", gesture.c_str(), msg.confidence);

    std::thread([this, gesture]() {
      executeCommand(gesture);
      executing_ = false;
    }).detach();
  }

  // ── Command dispatch ────────────────────────────────────────────────────────

  void executeCommand(const std::string & gesture)
  {
    if      (gesture == "thumbs_up") { executeHome();                       }
    else if (gesture == "point")     { executePointRaise();                 }
    else if (gesture == "open")      { executeGripper(gripper_open_pos_);   }
    else if (gesture == "fist")      { executeGripper(gripper_closed_pos_); }
    else if (gesture == "none")      { executeStop();                       }
    else {
      RCLCPP_WARN(this->get_logger(), "Unknown gesture label: '%s'", gesture.c_str());
      return;
    }

    // Publish for monitoring / logging
    auto cmd_msg = std_msgs::msg::String();
    cmd_msg.data = gesture;
    cmd_pub_->publish(cmd_msg);
  }

  // ── Motion primitives ───────────────────────────────────────────────────────

  void executeHome()
  {
    RCLCPP_INFO(this->get_logger(), "Moving to 'home' pose...");
    move_group_->setNamedTarget("home");

    MoveGroupInterface::Plan plan;
    if (move_group_->plan(plan) == moveit::core::MoveItErrorCode::SUCCESS) {
      move_group_->execute(plan);
      RCLCPP_INFO(this->get_logger(), "Home pose reached.");
    } else {
      RCLCPP_WARN(this->get_logger(), "Failed to plan home pose.");
    }
  }

  void executePointRaise()
  {
    RCLCPP_INFO(this->get_logger(),
                "Raising arm (Y_joint += %.3f rad)...", point_delta_rad_);

    // Get current robot state
    auto current_state = move_group_->getCurrentState(5.0);
    if (!current_state) {
      RCLCPP_WARN(this->get_logger(), "Could not get current robot state.");
      return;
    }

    const auto * jmg = current_state->getJointModelGroup("denso_arm");
    std::vector<double> joint_values;
    current_state->copyJointGroupPositions(jmg, joint_values);

    // Find Y_joint index in the planning group's variable list
    const auto & joint_names = jmg->getVariableNames();
    auto it = std::find(joint_names.begin(), joint_names.end(), "Y_joint");
    if (it == joint_names.end()) {
      RCLCPP_ERROR(this->get_logger(), "Y_joint not found in 'denso_arm' group.");
      return;
    }
    const int y_idx = static_cast<int>(std::distance(joint_names.begin(), it));

    // Apply delta, clamped to hardware limits
    const double current_y = joint_values[static_cast<size_t>(y_idx)];
    joint_values[static_cast<size_t>(y_idx)] =
      std::clamp(current_y + point_delta_rad_, Y_LOWER_RAD, Y_UPPER_RAD);

    RCLCPP_INFO(this->get_logger(), "Y_joint: %.4f → %.4f rad",
                current_y, joint_values[static_cast<size_t>(y_idx)]);

    move_group_->setJointValueTarget(joint_values);
    MoveGroupInterface::Plan plan;
    if (move_group_->plan(plan) == moveit::core::MoveItErrorCode::SUCCESS) {
      move_group_->execute(plan);
      RCLCPP_INFO(this->get_logger(), "Arm raised.");
    } else {
      RCLCPP_WARN(this->get_logger(), "Failed to plan arm raise.");
    }
  }

  void executeGripper(double position)
  {
    if (!gripper_client_->wait_for_action_server(std::chrono::seconds(2))) {
      RCLCPP_WARN(this->get_logger(),
                  "Gripper action server not available: "
                  "/arctos_hand_controller/follow_joint_trajectory");
      return;
    }

    auto goal = FollowJointTraj::Goal();
    goal.trajectory.joint_names = {"Left_jaw_joint"};

    trajectory_msgs::msg::JointTrajectoryPoint pt;
    pt.positions          = {position};
    pt.time_from_start    = rclcpp::Duration::from_seconds(1.0);
    goal.trajectory.points.push_back(pt);

    RCLCPP_INFO(this->get_logger(), "Sending gripper to %.4f rad...", position);

    // Fire and forget: the gripper controller handles completion
    gripper_client_->async_send_goal(goal);

    // Give the gripper time to move before the next command can be accepted
    std::this_thread::sleep_for(std::chrono::milliseconds(1500));
    RCLCPP_INFO(this->get_logger(), "Gripper command sent.");
  }

  void executeStop()
  {
    RCLCPP_INFO(this->get_logger(), "Stopping all arm motion (hold position)...");
    move_group_->stop();
    RCLCPP_INFO(this->get_logger(), "Motion stopped.");
  }
};

// ─────────────────────────────────────────────────────────────────────────────

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);

  auto node = std::make_shared<GestureCommanderNode>();

  // The executor must be spinning before MoveGroupInterface connects to
  // /move_group services/actions, so start spinning in a background thread.
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(node);
  std::thread spin_thread([&executor]() { executor.spin(); });

  // Initialise MoveGroupInterface now that the executor is running.
  // Cast to base class pointer as required by MoveGroupInterface constructor.
  node->setupMoveGroup(std::static_pointer_cast<rclcpp::Node>(node));

  RCLCPP_INFO(rclcpp::get_logger("gesture_commander"), "Ready — listening for gestures.");

  spin_thread.join();
  rclcpp::shutdown();
  return 0;
}
