# Project: ROS2 Arctos Robot Arm (ros2_arctos_HCMUT)

## Workspace
- Path: `/home/nam/Coding/ros2_ws_rework/`
- Source: `/home/nam/Coding/ros2_ws_rework/src/ros2_arctos_HCMUT/`
- ROS2 distro: Humble
- Branch: `denso_linux`

## Key Architecture
User → RViz / gesture_control → MoveIt2 (`denso_arm` group) → `denso_arm_controller` (JointTrajectoryController) → `arctos_hardware_interface` → UART motors

## Robot
- 6-DOF: `X_joint, Y_joint, Z_joint, A_joint, B_joint, C_joint`
- Gripper: `Left_jaw_joint` (0.0–0.015 rad), controller: `arctos_hand_controller`
- MoveIt2 planning group: `denso_arm`  (in arctos.srdf)
- Named poses: `home` (all joints = 0)
- Y_joint limits: -100° to +135° = -1.745 to 2.356 rad

## Controllers (ros2_controllers.yaml)
- `denso_arm_controller` — arm joints (JointTrajectoryController)
- `arctos_hand_controller` — Left_jaw_joint (JointTrajectoryController, added for gesture control)
- `joint_state_broadcaster`
- Update rate: 5 Hz

## gesture_control Package (new, added 2026-03)
Location: `gesture_control/`
Purpose: Map EdgeTPU/CPU gesture recognition → MoveIt2 robot commands

### Files
- `msg/GestureDetection.msg` — custom ROS2 message
- `scripts/gesture_inference_backend.py` — Python 3.9.17 standalone, outputs JSON to stdout
- `gesture_control/gesture_recognition_node.py` — Python 3.10 ROS2 node, spawns subprocess
- `src/gesture_commander_node.cpp` — C++ node, MoveGroupInterface + gripper action client
- `launch/gesture_control.launch.py` — launch args: inference_mode, camera_id, python_binary
- `config/gesture_config.yaml` — confidence_threshold, stability_frames, cooldown, deltas

### Gesture Mapping
| Gesture    | Action |
|------------|--------|
| thumbs_up  | MoveIt2 named pose "home" |
| point      | Y_joint += 0.3 rad (raise arm) |
| open       | Left_jaw_joint → 0.015 rad |
| fist       | Left_jaw_joint → 0.0 rad |
| none       | move_group.stop() |

### Python Version Architecture
- `gesture_inference_backend.py` runs under pyenv `gesture_env` Python 3.9.17
  (`/home/nam/.pyenv/versions/gesture_env/bin/python`)
- Reason: `pycoral` (EdgeTPU) requires Python 3.9; `rclpy` requires Python 3.10
- Bridge: subprocess stdout pipe (JSON lines, flush=True), ~0.1ms latency
- `ros-humble-moveit-py` does NOT exist — use C++ MoveGroupInterface instead

### CMakeLists.txt Note
- Do NOT call `ament_python_install_package(gesture_control)` alongside `rosidl_generate_interfaces`
  — rosidl already registers the Python package internally, causing duplicate target error

### Run Commands
```bash
# CPU/Keras (no Coral needed)
ros2 launch gesture_control gesture_control.launch.py inference_mode:=cpu

# EdgeTPU (Coral plugged in)
ros2 launch gesture_control gesture_control.launch.py inference_mode:=edgetpu

# Monitor
ros2 topic echo /gesture_detection
ros2 topic echo /gesture_command
```

## AI Modules
Path: `AI_modules/gesture_recognition/`
- Models: `models/gesture_retrained_int8_edgetpu.tflite`, `models/gesture_retrained.h5`
- Classes: fist, open, point, thumbs_up, none
- EdgeTPU latency: 5–10ms; CPU latency: 30–50ms
