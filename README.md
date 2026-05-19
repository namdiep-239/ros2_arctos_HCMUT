# ROS2 Arctos — HCMUT
![Discord](https://img.shields.io/discord/1099629962618748958?logo=discord&logoColor=%23FFFFFF&logoSize=auto)

## Warning

This project is still under development and is not yet ready for production use.

**USE AT YOUR OWN RISK.**

Only operate the robot if you have:
- Ensured the robot arm is securely mounted and cannot tip over.
- Ensured at least **1 metre of clearance** around the arm in all directions.
- Ensured no fragile objects are within the arm's reach.
- Stay close to the robot and be ready to cut power if unexpected motion occurs.

---

## Overview

**ROS2 Arctos HCMUT** controls a 6-DOF Arctos robot arm over UART using MKS stepper motor drivers. It supports real-hardware operation, Gazebo Ignition simulation, gesture-based control, and automated visual inspection with an AI classifier.

### Hardware
- **Robot**: 6-DOF Arctos arm — joints X, Y, Z, A, B, C
- **Gripper**: single servo jaw (`gripper_gear_right_joint`)
- **Motor drivers**: MKS57D (X, Y) and MKS42D (Z, A, B, C, gripper) via UART/Serial
- **Camera**: UGREEN USB webcam (eye-in-hand, for inspection and gesture)
- **AI accelerator**: Google Coral USB (optional, for EdgeTPU inference)

### Software stack
- **ROS2 Humble** on Ubuntu 22.04
- **MoveIt2** (OMPL + CHOMP + Pilz planners)
- **ros2_control** + JointTrajectoryController
- **Gazebo Ignition Fortress** (simulation)
- Python 3.10 (ROS2 nodes) + Python 3.9 via pyenv `gesture_env` (TFLite/EdgeTPU)

---

## Repository Structure

```
ros2_arctos_HCMUT/
├── serial/                      # UART serial library
├── arctos_description/          # URDF / xacro robot model
├── arctos_motor_driver/         # Low-level UART motor driver
├── arctos_hardware_interface/   # ros2_control hardware plugin
├── arctos_moveit_config/        # MoveIt2 config, SRDF, worlds
├── arctos_bringup/              # Top-level launch files
├── denso_interfaces/            # Custom ROS2 msgs/srvs/actions
├── denso_remote_control/        # MoveToPose action server
├── denso_moveit_servo/          # Real-time MoveIt Servo node
├── file_server2/                # ROS-Sharp / Unity URDF bridge
├── gesture_control/             # Gesture recognition → MoveIt2
├── visual_inspection/           # AI visual inspection pipeline
├── AI_modules/
│   ├── gesture_recognition/     # Gesture model training
│   ├── object_detection/        # Cube detection training + dataset_collector
│   └── visual_inspection/       # Inspection model training + dataset tools
└── scripts/                     # Utility scripts
```

---

## Installation

### Requirements

- Ubuntu 22.04 (Jammy)
- ROS2 Humble Desktop
- MoveIt2 (binary)
- Gazebo Ignition Fortress

#### 1 — Install ROS2 Humble

Follow the [official guide](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html).
Install `ros-humble-desktop` and `ros-dev-tools`.

#### 2 — Install MoveIt2

Follow the [MoveIt2 binary install](https://moveit.ai/install-moveit2/binary/).

If ROS2 nodes fail to communicate (UDP blocked), disable the firewall:
```bash
sudo ufw disable
```

#### 3 — Install Gazebo Ignition Fortress

Follow the [Gazebo Fortress install guide](https://gazebosim.org/docs/fortress/install_ubuntu/).

#### 4 — Install ROS2 packages

```bash
sudo apt install -y \
  ros-humble-ros2-control \
  ros-humble-gz-ros2-control \
  ros-humble-gz-ros2-control-demos \
  ros-humble-gripper-controllers \
  ros-humble-moveit-servo \
  ros-humble-v4l2-camera \
  ros-humble-usb-cam \
  ros-humble-rqt-image-view \
  ros-humble-image-transport-plugins \
  ros-humble-rosbridge-server \
  python3-rosdep
```

#### 5 — Set up Python environments with pyenv

The project uses **two Python environments**:

| Environment | Python | Purpose |
|---|---|---|
| `denso` | 3.10.12 | ROS2 nodes |
| `gesture_env` | 3.9.17 | TFLite / EdgeTPU inference (pycoral requires 3.9) |

Install pyenv following the [pyenv guide](https://realpython.com/intro-to-pyenv/), then:

```bash
# Python 3.10 for ROS2 nodes
pyenv install 3.10.12
pyenv virtualenv 3.10.12 denso
pyenv local denso
pip install python-can ruamel.yaml rich keyboard catkin-pkg lark \
            PyQt5 PySide2 empy==3.3.4 tornado numpy pyyaml jinja2 \
            typeguard pymongo Pillow netifaces cbor2

# Python 3.9 for AI inference
pyenv install 3.9.17
pyenv virtualenv 3.9.17 gesture_env
pyenv activate gesture_env
pip install tensorflow==2.13.0 numpy opencv-python pyyaml
# Optional — EdgeTPU (requires Coral USB plugged in):
pip install pycoral
```

### Build the workspace

```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
git clone --recurse-submodules https://github.com/ngoccatt/ros2_arctos_HCMUT.git

cd ~/ros2_ws/src/ros2_arctos_HCMUT/serial
make && make install

cd ~/ros2_ws
source /opt/ros/humble/setup.bash
sudo rosdep init && rosdep update
rosdep install --from-paths src -y --ignore-src

colcon build --symlink-install
source install/setup.bash
```

---

## Running the Robot

Always source the workspace first:
```bash
source ~/ros2_ws/install/setup.bash
```

### Real hardware

**Terminal 1 — Hardware bringup** (controllers + RViz + MoveIt):
```bash
ros2 launch arctos_bringup arctos_bringup.launch.py
```

### Gazebo simulation

```bash
ros2 launch arctos_bringup gz_arctos_bringup.launch.py use_sim_time:=true
```

---

## Optional Packages

### Real-time servo (keyboard / Cartesian control)

```bash
# Terminal 2
ros2 launch denso_moveit_servo denso_moveit_servo.launch.py use_sim_time:=false
# Terminal 3
ros2 run denso_moveit_servo servo_keyboard_input
```

### Remote control (MoveToPose action server)

```bash
ros2 launch denso_remote_control remote_control.launch.py use_sim_time:=false
```

### Unity / ROS-Sharp bridge

```bash
ros2 launch file_server2 ros_sharp_communication.launch.py
```

### Gesture control

```bash
# CPU inference (no Coral needed)
ros2 launch gesture_control gesture_control.launch.py inference_mode:=cpu

# EdgeTPU inference (Coral USB plugged in)
ros2 launch gesture_control gesture_control.launch.py inference_mode:=edgetpu
```

| Gesture | Action |
|---|---|
| thumbs_up | Move to `home` pose |
| point | Raise arm (Y_joint +0.3 rad) |
| open | Open gripper |
| fist | Close gripper |
| none | Stop arm |

### Visual inspection

Requires hardware bringup running first.

```bash
# Terminal 2 — Inspection nodes
ros2 launch visual_inspection visual_inspection.launch.py use_sim_time:=false

# Terminal 3 — Trigger one inspection cycle
ros2 action send_goal /run_inspection visual_inspection/action/RunInspection \
  "{object_id: 'part_001'}"
```

The node drives the arm through 5 inspection poses, collects AI votes at each, classifies the object (PASS/FAIL), then sorts it to the corresponding tray.

See [visual_inspection/README.md](visual_inspection/README.md) for the full pipeline.

---

## Package READMEs

- [arctos_bringup](arctos_bringup/README.md)
- [arctos_description](arctos_description/README.md)
- [arctos_hardware_interface](arctos_hardware_interface/README.md)
- [arctos_motor_driver](arctos_motor_driver/README.md)
- [arctos_moveit_config](arctos_moveit_config/README.md)
- [denso_moveit_servo](denso_moveit_servo/README.md)
- [denso_remote_control](denso_remote_control/README.md)
- [visual_inspection](visual_inspection/README.md)
- [AI_modules/object_detection](AI_modules/object_detection/README.md)

---

## Contributing

Please follow the [Contributing Guidelines](CONTRIBUTING.md) and [Code of Conduct](CODE_OF_CONDUCT.md).

## License

[Apache License 2.0](LICENSE)
