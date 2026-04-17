"""
gesture_control.launch.py

Launches both gesture_control nodes:
  1. gesture_recognition_node  — Python 3.10, spawns inference backend subprocess
  2. gesture_commander_node    — C++, MoveGroupInterface + gripper action client

Launch arguments:
  inference_mode   edgetpu | cpu   (default: cpu)
  camera_id        int              (default: 0)
  python_binary    path             (default: gesture_env Python 3.9.17)
  use_sim_time     true | false     (default: false — set true for Gazebo)
"""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    pkg_share = get_package_share_directory('gesture_control')

    # ── Resolve paths ─────────────────────────────────────────────────────────
    # Backend script is installed under the package share directory
    backend_script = os.path.join(pkg_share, 'scripts', 'gesture_inference_backend.py')

    # AI models live in the workspace source tree (not installed to avoid
    # duplicating large binary files). Navigate from install → workspace root.
    #   install/gesture_control/share/gesture_control  →  (4 levels up)  →  workspace
    workspace_root = os.path.normpath(os.path.join(pkg_share, '..', '..', '..', '..'))
    ai_module_models = os.path.join(
        workspace_root, 'src', 'ros2_arctos_HCMUT',
        'AI_modules', 'gesture_recognition', 'models'
    )
    edgetpu_model = os.path.join(ai_module_models, 'gesture_retrained_int8_edgetpu.tflite')
    cpu_model     = os.path.join(ai_module_models, 'gesture_best.h5')
    metadata      = os.path.join(ai_module_models, 'model_metadata.json')

    # Config file
    gesture_config = os.path.join(pkg_share, 'config', 'gesture_config.yaml')

    # ── Robot description (needed by MoveGroupInterface) ──────────────────────
    # Use the real-hardware URDF xacro — the kinematic model is identical to
    # the Gazebo variant; only the hardware plugin differs, which MoveIt doesn't need.
    moveit_config = (
        MoveItConfigsBuilder("arctos", package_name="arctos_moveit_config")
        .robot_description(file_path="config/arctos.urdf.xacro")
        .robot_description_semantic(file_path="config/arctos.srdf")
        .to_moveit_configs()
    )

    # ── Launch arguments ──────────────────────────────────────────────────────
    inference_mode_arg = DeclareLaunchArgument(
        'inference_mode',
        default_value='cpu',
        description="Inference backend: 'edgetpu' (Coral) or 'cpu' (TensorFlow Keras)")

    camera_id_arg = DeclareLaunchArgument(
        'camera_id',
        default_value='0',
        description='OpenCV camera device index')

    python_binary_arg = DeclareLaunchArgument(
        'python_binary',
        default_value='/home/nam/.pyenv/versions/gesture_env/bin/python',
        description='Python interpreter for the inference backend (must have pycoral/tensorflow)')

    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation clock (true for Gazebo, false for real hardware)')

    inference_mode = LaunchConfiguration('inference_mode')
    camera_id      = LaunchConfiguration('camera_id')
    python_binary  = LaunchConfiguration('python_binary')
    use_sim_time   = LaunchConfiguration('use_sim_time')

    # ── Node: gesture_recognition_node (Python 3.10) ──────────────────────────
    # Model path is chosen by inference_mode at runtime inside the node
    # (both paths are passed; the backend script uses the one for its mode)
    recognition_node = Node(
        package='gesture_control',
        executable='gesture_recognition_node',
        name='gesture_recognition_node',
        output='screen',
        parameters=[{
            'inference_mode':     inference_mode,
            'python_binary':      python_binary,
            'backend_script':     backend_script,
            'edgetpu_model_path': edgetpu_model,
            'cpu_model_path':     cpu_model,
            'metadata_path':      metadata,
            'camera_id':          camera_id,
            'publish_rate':       10.0,
            'use_sim_time':       use_sim_time,
        }],
    )

    # ── Node: gesture_commander_node (C++) ────────────────────────────────────
    commander_node = Node(
        package='gesture_control',
        executable='gesture_commander_node',
        name='gesture_commander_node',
        output='screen',
        parameters=[
            gesture_config,
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            {'use_sim_time': use_sim_time},
        ],
    )

    return LaunchDescription([
        inference_mode_arg,
        camera_id_arg,
        python_binary_arg,
        use_sim_time_arg,
        recognition_node,
        commander_node,
    ])
