#include <string>
#include <memory>

// ROS
#include <rclcpp/rclcpp.hpp>

// Servo
#include <moveit_servo/servo_parameters.h>
#include <moveit_servo/servo.h>
#include <moveit/planning_scene_monitor/planning_scene_monitor.h>
#include <std_srvs/srv/trigger.hpp>

using namespace std::chrono_literals;

static const rclcpp::Logger LOGGER = rclcpp::get_logger("realtime_servo");

// BEGIN_TUTORIAL

// Setup
// ^^^^^
// First we declare pointers to the node and publisher that will publish commands to Servo
rclcpp::Node::SharedPtr node_;
// END_SUB_TUTORIAL

// Next we will set up the node, planning_scene_monitor, and collision object
int main(int argc, char **argv)
{
  rclcpp::init(argc, argv);
  rclcpp::NodeOptions node_options;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr start_servo_service_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr stop_servo_service_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr pause_servo_service_;
  rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr unpause_servo_service_;

  // This is false for now until we fix the QoS settings in moveit to enable intra process comms
  node_options.use_intra_process_comms(true);
  node_ = std::make_shared<rclcpp::Node>("denso_moveit_servo_node", node_options);

  auto planning_scene_monitor = std::make_shared<planning_scene_monitor::PlanningSceneMonitor>(
      node_, "robot_description", "planning_scene_monitor");

  // Initializing Servo
  // ^^^^^^^^^^^^^^^^^^
  // Servo requires a number of parameters to dictate its behavior. These can be read automatically by using the
  // :code:`makeServoParameters` helper function
  // the ns (namespace) should be specified (as the same in launch file), or it'll automatically use "moveit_servo", then invoke panda arm instead.
  auto servo_parameters = moveit_servo::ServoParameters::makeServoParameters(node_, "denso_moveit_servo");
  if (!servo_parameters)
  {
    RCLCPP_FATAL(LOGGER, "Failed to load the servo parameters");
    return EXIT_FAILURE;
  }

  // Here we make sure the planning_scene_monitor is updating in real time from the joint states topic
  if (planning_scene_monitor->getPlanningScene())
  {
    planning_scene_monitor->startStateMonitor(servo_parameters->joint_topic);
    planning_scene_monitor->startSceneMonitor(servo_parameters->monitored_planning_scene_topic);
    planning_scene_monitor->startWorldGeometryMonitor();
    planning_scene_monitor->setPlanningScenePublishingFrequency(25);
    planning_scene_monitor->getStateMonitor()->enableCopyDynamics(true);
    planning_scene_monitor->startPublishingPlanningScene(planning_scene_monitor::PlanningSceneMonitor::UPDATE_SCENE,
                            std::string(node_->get_fully_qualified_name()) +
                                "/publish_planning_scene");
  }
  else
  {
    RCLCPP_ERROR(LOGGER, "Planning scene not configured");
    return EXIT_FAILURE;
  }

  // If the planning scene monitor in servo is the primary one we provide /get_planning_scene service so RViz displays
  // or secondary planning scene monitors can fetch the scene, otherwise we request the planning scene from the
  // primary planning scene monitor (e.g. move_group)
  if (servo_parameters->is_primary_planning_scene_monitor)
    planning_scene_monitor->providePlanningSceneService();
  else
    planning_scene_monitor->requestPlanningSceneState();

  // Initialize the Servo C++ interface by passing a pointer to the node, the parameters, and the PSM
  auto servo = std::make_unique<moveit_servo::Servo>(node_, servo_parameters, planning_scene_monitor);

  // Set up some services for Servo Node

  // Set up services for interacting with Servo
  start_servo_service_ = node_->create_service<std_srvs::srv::Trigger>(
      "~/start_servo",
      [&servo](const std::shared_ptr<std_srvs::srv::Trigger::Request> & /* unused*/,
               const std::shared_ptr<std_srvs::srv::Trigger::Response> &response)
      {
        servo->start();
        response->success = true;
      });

  stop_servo_service_ = node_->create_service<std_srvs::srv::Trigger>(
      "~/stop_servo",
      [&servo](const std::shared_ptr<std_srvs::srv::Trigger::Request> & /* unused*/,
               const std::shared_ptr<std_srvs::srv::Trigger::Response> &response)
      {
        servo->setPaused(true);
        response->success = true;
      });

  pause_servo_service_ = node_->create_service<std_srvs::srv::Trigger>(
      "~/pause_servo",
      [&servo](const std::shared_ptr<std_srvs::srv::Trigger::Request> & /* unused*/,
               const std::shared_ptr<std_srvs::srv::Trigger::Response> &response)
      {
        servo->setPaused(true);
        response->success = true;
      });

  unpause_servo_service_ = node_->create_service<std_srvs::srv::Trigger>(
      "~/unpause_servo",
      [&servo](const std::shared_ptr<std_srvs::srv::Trigger::Request> & /* unused*/,
               const std::shared_ptr<std_srvs::srv::Trigger::Response> &response)
      {
        servo->setPaused(false);
        response->success = true;
      });

  // We use a multithreaded executor here because Servo has concurrent processes for moving the robot and avoiding collisions
  auto executor = std::make_unique<rclcpp::executors::MultiThreadedExecutor>();
  executor->add_node(node_);
  executor->spin();

  // END_TUTORIAL

  rclcpp::shutdown();
  return 0;
}
