/**
 * inspection_commander_node.cpp
 *
 * ROS2 C++ node — Visual Inspection state machine.
 *
 * Exposes a /run_inspection action server. When triggered, the node drives the
 * robot arm through 5 fixed inspection poses (P1–P5), collects AI inference
 * votes from /inspection_result at each pose, performs majority-vote
 * classification, then sorts the object to PASS or FAIL tray.
 *
 * Topics subscribed:
 *   /inspection_result  (visual_inspection/msg/InspectionResult)
 *
 * Actions provided:
 *   /run_inspection     (visual_inspection/action/RunInspection)
 *
 * Motion:
 *   FollowJointTrajectory action client → denso_arm_controller (no MoveIt).
 *   Gripper via GripperCommand action → denso_hand_controller.
 *
 * Waypoints (joint values [X,Y,Z,A,B,C] rad) are loaded from ROS2 parameters.
 * Update inspection_config.yaml after hardware calibration.
 *
 * State machine:
 *   IDLE → MOVING_TO_PICK (optional)
 *        → MOVING_TO_P1 → COLLECTING_P1
 *        → MOVING_TO_P2 → COLLECTING_P2
 *        → MOVING_TO_P3 → COLLECTING_P3
 *        → MOVING_TO_P4 → COLLECTING_P4
 *        → MOVING_TO_P5 → COLLECTING_P5
 *        → CLASSIFYING
 *        → MOVING_TO_SORT (PASS or FAIL tray)
 *        → MOVING_HOME → IDLE
 */

#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <control_msgs/action/follow_joint_trajectory.hpp>
#include <control_msgs/action/gripper_command.hpp>
#include <trajectory_msgs/msg/joint_trajectory.hpp>
#include <trajectory_msgs/msg/joint_trajectory_point.hpp>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "visual_inspection/msg/inspection_result.hpp"
#include "visual_inspection/action/run_inspection.hpp"

using InspectionResult      = visual_inspection::msg::InspectionResult;
using RunInspection         = visual_inspection::action::RunInspection;
using GoalHandle            = rclcpp_action::ServerGoalHandle<RunInspection>;
using GripperCommand        = control_msgs::action::GripperCommand;
using FollowJointTrajectory = control_msgs::action::FollowJointTrajectory;

static const std::vector<std::string> JOINT_NAMES = {
  "X_joint", "Y_joint", "Z_joint", "A_joint", "B_joint", "C_joint"
};

// ─────────────────────────────────────────────────────────────────────────────

class InspectionCommanderNode : public rclcpp::Node
{
public:
  InspectionCommanderNode()
  : Node("inspection_commander_node"),
    busy_(false)
  {
    // ── Parameters ────────────────────────────────────────────────────────────
    this->declare_parameter("confidence_threshold", 0.70);
    this->declare_parameter("frames_per_pose",      5);
    this->declare_parameter("settle_time_sec",      0.5);
    this->declare_parameter("move_travel_time_sec", 5.0);
    this->declare_parameter("enable_pick",          false);
    this->declare_parameter("gripper_open_pos",     1.47);
    this->declare_parameter("gripper_closed_pos",   0.10);

    auto declare_wp = [this](const std::string & name) {
      this->declare_parameter(name, std::vector<double>{0.0, 0.0, 0.0, 0.0, 0.0, 0.0});
    };
    declare_wp("waypoints.home");
    declare_wp("waypoints.pick");
    declare_wp("waypoints.inspect_p1");
    declare_wp("waypoints.inspect_p2");
    declare_wp("waypoints.inspect_p3");
    declare_wp("waypoints.inspect_p4");
    declare_wp("waypoints.inspect_p5");
    declare_wp("waypoints.sort_pass");
    declare_wp("waypoints.sort_fail");

    confidence_threshold_  = this->get_parameter("confidence_threshold").as_double();
    frames_per_pose_       = this->get_parameter("frames_per_pose").as_int();
    settle_time_sec_       = this->get_parameter("settle_time_sec").as_double();
    move_travel_time_sec_  = this->get_parameter("move_travel_time_sec").as_double();
    enable_pick_           = this->get_parameter("enable_pick").as_bool();
    gripper_open_pos_      = this->get_parameter("gripper_open_pos").as_double();
    gripper_closed_pos_    = this->get_parameter("gripper_closed_pos").as_double();

    // ── Arm trajectory action client ──────────────────────────────────────────
    arm_client_ = rclcpp_action::create_client<FollowJointTrajectory>(
      this, "/denso_arm_controller/follow_joint_trajectory");

    // ── Gripper action client ─────────────────────────────────────────────────
    gripper_client_ = rclcpp_action::create_client<GripperCommand>(
      this, "/denso_hand_controller/gripper_cmd");

    // ── AI result subscriber ──────────────────────────────────────────────────
    result_sub_ = this->create_subscription<InspectionResult>(
      "/inspection_result", 10,
      std::bind(&InspectionCommanderNode::resultCallback, this, std::placeholders::_1));

    // ── Inspection action server ──────────────────────────────────────────────
    action_server_ = rclcpp_action::create_server<RunInspection>(
      this, "/run_inspection",
      std::bind(&InspectionCommanderNode::handleGoal,     this,
                std::placeholders::_1, std::placeholders::_2),
      std::bind(&InspectionCommanderNode::handleCancel,   this, std::placeholders::_1),
      std::bind(&InspectionCommanderNode::handleAccepted, this, std::placeholders::_1));

    RCLCPP_INFO(this->get_logger(),
                "InspectionCommanderNode ready  [travel=%.1fs  settle=%.1fs]",
                move_travel_time_sec_, settle_time_sec_);
  }

private:
  // ── Parameters ──────────────────────────────────────────────────────────────
  double confidence_threshold_;
  int    frames_per_pose_;
  double settle_time_sec_;
  double move_travel_time_sec_;
  bool   enable_pick_;
  double gripper_open_pos_;
  double gripper_closed_pos_;

  // ── State ───────────────────────────────────────────────────────────────────
  std::atomic<bool>             busy_;
  std::mutex                    vote_mutex_;
  std::vector<InspectionResult> vote_buffer_;
  bool                          collecting_{false};

  // ── ROS interfaces ──────────────────────────────────────────────────────────
  rclcpp::Subscription<InspectionResult>::SharedPtr          result_sub_;
  rclcpp_action::Server<RunInspection>::SharedPtr            action_server_;
  rclcpp_action::Client<FollowJointTrajectory>::SharedPtr    arm_client_;
  rclcpp_action::Client<GripperCommand>::SharedPtr           gripper_client_;

  // ── AI result callback ───────────────────────────────────────────────────────
  void resultCallback(const InspectionResult & msg)
  {
    if (!collecting_) return;
    if (msg.confidence < static_cast<float>(confidence_threshold_)) return;
    std::lock_guard<std::mutex> lock(vote_mutex_);
    vote_buffer_.push_back(msg);
  }

  // ── Action server callbacks ──────────────────────────────────────────────────
  rclcpp_action::GoalResponse handleGoal(
    const rclcpp_action::GoalUUID &,
    std::shared_ptr<const RunInspection::Goal> goal)
  {
    if (busy_.load()) {
      RCLCPP_WARN(this->get_logger(),
                  "Inspection already running — rejecting goal for '%s'",
                  goal->object_id.c_str());
      return rclcpp_action::GoalResponse::REJECT;
    }
    RCLCPP_INFO(this->get_logger(),
                "Inspection goal accepted: object_id='%s'", goal->object_id.c_str());
    return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
  }

  rclcpp_action::CancelResponse handleCancel(const std::shared_ptr<GoalHandle>)
  {
    RCLCPP_INFO(this->get_logger(), "Cancel requested.");
    return rclcpp_action::CancelResponse::ACCEPT;
  }

  void handleAccepted(const std::shared_ptr<GoalHandle> goal_handle)
  {
    std::thread([this, goal_handle]() { runSequence(goal_handle); }).detach();
  }

  // ── Main inspection sequence ─────────────────────────────────────────────────
  void runSequence(const std::shared_ptr<GoalHandle> goal_handle)
  {
    busy_ = true;

    auto feedback = std::make_shared<RunInspection::Feedback>();
    auto result   = std::make_shared<RunInspection::Result>();
    int total_pass = 0;
    int total_fail = 0;

    auto publish_feedback = [&](const std::string & state, float progress) {
      feedback->state      = state;
      feedback->progress   = progress;
      feedback->pass_votes = total_pass;
      feedback->fail_votes = total_fail;
      goal_handle->publish_feedback(feedback);
      RCLCPP_INFO(this->get_logger(), "[%s] progress=%.0f%%  pass=%d  fail=%d",
                  state.c_str(), progress * 100.0f, total_pass, total_fail);
    };

    // ── PICK (optional) ───────────────────────────────────────────────────────
    if (enable_pick_) {
      publish_feedback("MOVING_TO_PICK", 0.05f);
      if (!moveToWaypoint("waypoints.pick")) {
        abortGoal(goal_handle, result, "Failed to reach PICK pose");
        busy_ = false; return;
      }
      std::this_thread::sleep_for(
        std::chrono::milliseconds(static_cast<int>(settle_time_sec_ * 1000)));
      publish_feedback("PICKING", 0.08f);
      sendGripper(gripper_closed_pos_);
    }

    // ── Inspection poses ──────────────────────────────────────────────────────
    const std::vector<std::pair<std::string, float>> poses = {
      {"inspect_p1", 0.15f},
      {"inspect_p2", 0.30f},
      {"inspect_p3", 0.45f},
      {"inspect_p4", 0.60f},
      {"inspect_p5", 0.75f},
    };

    for (const auto & [pose_name, progress] : poses) {
      if (goal_handle->is_canceling()) {
        cancelGoal(goal_handle, result);
        busy_ = false; return;
      }

      publish_feedback("MOVING_TO_" + upperCase(pose_name), progress - 0.05f);
      if (!moveToWaypoint("waypoints." + pose_name)) {
        abortGoal(goal_handle, result, "Failed to reach " + pose_name);
        busy_ = false; return;
      }

      std::this_thread::sleep_for(
        std::chrono::milliseconds(static_cast<int>(settle_time_sec_ * 1000)));

      publish_feedback("COLLECTING_" + upperCase(pose_name), progress);
      auto [p, f] = collectVotes(frames_per_pose_);
      total_pass += p;
      total_fail += f;
    }

    // ── Classify ──────────────────────────────────────────────────────────────
    publish_feedback("CLASSIFYING", 0.85f);

    if (total_pass == 0 && total_fail == 0) {
      RCLCPP_WARN(this->get_logger(),
                  "No confident votes collected (threshold=%.2f). Returning to PICK.",
                  confidence_threshold_);
      publish_feedback("RETURNING_TO_PICK", 0.88f);
      moveToWaypoint("waypoints.pick");
      std::this_thread::sleep_for(
        std::chrono::milliseconds(static_cast<int>(settle_time_sec_ * 1000)));
      sendGripper(gripper_open_pos_);
      publish_feedback("MOVING_HOME", 0.95f);
      moveToWaypoint("waypoints.home");
      result->verdict    = "UNCERTAIN";
      result->pass_votes = 0;
      result->fail_votes = 0;
      publish_feedback("DONE", 1.0f);
      goal_handle->succeed(result);
      busy_ = false;
      return;
    }

    std::string verdict = (total_pass > total_fail) ? "PASS" : "FAIL";
    RCLCPP_INFO(this->get_logger(),
                "Verdict: %s  (pass=%d  fail=%d)", verdict.c_str(), total_pass, total_fail);

    // ── Sort ──────────────────────────────────────────────────────────────────
    const std::string sort_wp = (verdict == "PASS") ? "waypoints.sort_pass" : "waypoints.sort_fail";
    publish_feedback("MOVING_TO_SORT_" + verdict, 0.90f);
    if (!moveToWaypoint(sort_wp)) {
      abortGoal(goal_handle, result, "Failed to reach sort pose");
      busy_ = false; return;
    }
    std::this_thread::sleep_for(
      std::chrono::milliseconds(static_cast<int>(settle_time_sec_ * 1000) + 500));
    sendGripper(gripper_open_pos_);
    std::this_thread::sleep_for(std::chrono::milliseconds(800));

    // ── Return home ───────────────────────────────────────────────────────────
    publish_feedback("MOVING_HOME", 0.95f);
    moveToWaypoint("waypoints.home");
    std::this_thread::sleep_for(
      std::chrono::milliseconds(static_cast<int>(settle_time_sec_ * 1000) + 500));

    // ── Succeed ───────────────────────────────────────────────────────────────
    result->verdict    = verdict;
    result->pass_votes = total_pass;
    result->fail_votes = total_fail;
    publish_feedback("DONE", 1.0f);
    goal_handle->succeed(result);
    RCLCPP_INFO(this->get_logger(), "Inspection complete — verdict: %s", verdict.c_str());

    busy_ = false;
  }

  // ── Motion helper ────────────────────────────────────────────────────────────

  bool moveToWaypoint(const std::string & param_name)
  {
    auto joint_values = this->get_parameter(param_name).as_double_array();
    if (joint_values.size() != 6) {
      RCLCPP_ERROR(this->get_logger(),
                   "Waypoint '%s' must have 6 values, got %zu",
                   param_name.c_str(), joint_values.size());
      return false;
    }

    if (!arm_client_->wait_for_action_server(std::chrono::seconds(3))) {
      RCLCPP_ERROR(this->get_logger(), "Arm controller not available.");
      return false;
    }

    // Build single-point trajectory
    trajectory_msgs::msg::JointTrajectoryPoint pt;
    pt.positions  = joint_values;
    pt.velocities = std::vector<double>(6, 0.0);
    pt.time_from_start.sec    = static_cast<int32_t>(move_travel_time_sec_);
    pt.time_from_start.nanosec =
      static_cast<uint32_t>((move_travel_time_sec_ - static_cast<int32_t>(move_travel_time_sec_)) * 1e9);

    trajectory_msgs::msg::JointTrajectory traj;
    traj.joint_names = JOINT_NAMES;
    traj.points      = {pt};

    FollowJointTrajectory::Goal goal;
    goal.trajectory = traj;

    // Block until result using a condition variable
    std::mutex              cv_mutex;
    std::condition_variable cv;
    bool result_received = false;
    bool success         = false;

    auto opts = rclcpp_action::Client<FollowJointTrajectory>::SendGoalOptions();

    opts.goal_response_callback =
      [&](const rclcpp_action::ClientGoalHandle<FollowJointTrajectory>::SharedPtr & handle) {
        if (!handle) {
          RCLCPP_ERROR(this->get_logger(), "Goal rejected by arm controller for '%s'",
                       param_name.c_str());
          std::lock_guard<std::mutex> lk(cv_mutex);
          result_received = true;
          success         = false;
          cv.notify_one();
        }
      };

    opts.result_callback =
      [&](const rclcpp_action::ClientGoalHandle<FollowJointTrajectory>::WrappedResult & res) {
        std::lock_guard<std::mutex> lk(cv_mutex);
        success         = (res.result->error_code == FollowJointTrajectory::Result::SUCCESSFUL);
        result_received = true;
        cv.notify_one();
        if (!success) {
          RCLCPP_WARN(this->get_logger(),
                      "Controller returned error %d for waypoint '%s'",
                      res.result->error_code, param_name.c_str());
        }
      };

    arm_client_->async_send_goal(goal, opts);

    const double timeout_sec = move_travel_time_sec_ + 5.0;
    std::unique_lock<std::mutex> lk(cv_mutex);
    if (!cv.wait_for(lk, std::chrono::duration<double>(timeout_sec),
                     [&] { return result_received; }))
    {
      RCLCPP_ERROR(this->get_logger(), "Motion timeout for waypoint '%s'", param_name.c_str());
      return false;
    }
    return success;
  }

  // ── Gripper helper ───────────────────────────────────────────────────────────

  void sendGripper(double position)
  {
    if (!gripper_client_->wait_for_action_server(std::chrono::seconds(2))) {
      RCLCPP_WARN(this->get_logger(), "Gripper action server not available.");
      return;
    }
    GripperCommand::Goal goal;
    goal.command.position   = position;
    goal.command.max_effort = 0.0;
    gripper_client_->async_send_goal(goal);
    std::this_thread::sleep_for(std::chrono::milliseconds(1200));
  }

  // ── Vote collection ──────────────────────────────────────────────────────────

  std::pair<int, int> collectVotes(int target_frames)
  {
    {
      std::lock_guard<std::mutex> lock(vote_mutex_);
      vote_buffer_.clear();
    }
    collecting_ = true;

    const auto deadline = std::chrono::steady_clock::now()
                          + std::chrono::milliseconds(target_frames * 300);
    while (std::chrono::steady_clock::now() < deadline) {
      {
        std::lock_guard<std::mutex> lock(vote_mutex_);
        if (static_cast<int>(vote_buffer_.size()) >= target_frames) break;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    collecting_ = false;

    std::lock_guard<std::mutex> lock(vote_mutex_);
    int pass = 0, fail = 0;
    for (const auto & r : vote_buffer_) {
      if (r.label == "PASS") ++pass;
      else                   ++fail;
    }
    RCLCPP_INFO(this->get_logger(),
                "  Votes: %zu frames  PASS=%d  FAIL=%d",
                vote_buffer_.size(), pass, fail);
    return {pass, fail};
  }

  // ── Goal helpers ─────────────────────────────────────────────────────────────

  void abortGoal(const std::shared_ptr<GoalHandle> & gh,
                 std::shared_ptr<RunInspection::Result> & res,
                 const std::string & reason)
  {
    RCLCPP_ERROR(this->get_logger(), "Aborting inspection: %s", reason.c_str());
    res->verdict    = "ERROR";
    res->pass_votes = 0;
    res->fail_votes = 0;
    gh->abort(res);
  }

  void cancelGoal(const std::shared_ptr<GoalHandle> & gh,
                  std::shared_ptr<RunInspection::Result> & res)
  {
    RCLCPP_INFO(this->get_logger(), "Inspection cancelled.");
    res->verdict = "CANCELLED";
    gh->canceled(res);
  }

  static std::string upperCase(std::string s)
  {
    for (auto & c : s) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    return s;
  }
};

// ─────────────────────────────────────────────────────────────────────────────

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<InspectionCommanderNode>();
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
