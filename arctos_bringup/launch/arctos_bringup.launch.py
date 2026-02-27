from launch import LaunchDescription
from launch.actions import RegisterEventHandler, DeclareLaunchArgument
from launch.event_handlers import OnProcessExit
from launch.actions import SetEnvironmentVariable, IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, Command, FindExecutable
from ament_index_python.packages import get_package_share_directory
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder
from launch_ros.substitutions import FindPackageShare
import os
import xacro

def generate_launch_description():
    world_file = '/home/nguyen/ros2_ws/src/ros2_arctos_HCMUT/building_robot.sdf'  # Path to your Gazebo world file, if you have one
    ros_gz_sim_pkg_path = get_package_share_directory('ros_gz_sim')
    # example_pkg_path = FindPackageShare('example_package')  # Replace with your own package name
    gz_launch_path = PathJoinSubstitution([ros_gz_sim_pkg_path, 'launch', 'gz_sim.launch.py'])

        # SetEnvironmentVariable(
        #     'GZ_SIM_RESOURCE_PATH',
        #     PathJoinSubstitution([example_pkg_path, 'models'])
        # ),
        # SetEnvironmentVariable(
        #     'GZ_SIM_PLUGIN_PATH',
        #     PathJoinSubstitution([example_pkg_path, 'plugins'])
        # ),
    gazebo = IncludeLaunchDescription(
                PythonLaunchDescriptionSource(gz_launch_path),
                launch_arguments={
                    'gz_args': PathJoinSubstitution([world_file]),  # Replace with your own world file
                    'on_exit_shutdown': 'True'
                }.items(),)

    # Bridging and remapping Gazebo topics to ROS 2 (replace with your own topics)
    gz_bridge = Node(
                package='ros_gz_bridge',
                executable='parameter_bridge',
                arguments=['/example_imu_topic@sensor_msgs/msg/Imu@gz.msgs.IMU',],
                remappings=[('/example_imu_topic',
                            '/remapped_imu_topic'),],
                output='screen'
            )
    package_path = os.path.join(
        get_package_share_directory('arctos_description'),)

    xacro_file = os.path.join(package_path,
                              'urdf',
                              'arctos.urdf')
    doc = xacro.parse(open(xacro_file))
    xacro.process_doc(doc)
    params = {'robot_description': doc.toxml()}
    # Get package paths
    arctos_hardware_interface_dir = get_package_share_directory('arctos_hardware_interface')
    arctos_moveit_dir = get_package_share_directory('arctos_moveit_config')

    # MoveItConfigsBuilder automatically do the following:
    # .robot_description: create urdf file using command: xacro arctos.urdf.xacro
    # .robot_description_semantic
    moveit_config = (
        MoveItConfigsBuilder("arctos")
        .robot_description(file_path="config/arctos.urdf.xacro")
        .robot_description_semantic(file_path="config/arctos.srdf")
        .trajectory_execution(file_path="config/moveit_controllers.yaml")
        .planning_pipelines(pipelines=["ompl", "chomp"])
        .to_moveit_configs()
    )

    rviz_base = os.path.join(get_package_share_directory("arctos_moveit_config"), "config")
    rviz_full_config = os.path.join(rviz_base, "moveit_chomp.rviz")
    rviz_empty_config = os.path.join(rviz_base, "moveit.rviz")

    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        output="screen",
        arguments=["-d", rviz_empty_config],
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.planning_pipelines,
            moveit_config.robot_description_kinematics,
        ],
    )
    # Nodes
    # publish the state of robot to TF (transform)
    robot_state_pub_node = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="both",
        parameters=[moveit_config.robot_description],
    )

    # spawn_entity = Node(package='gazebo_ros', executable='spawn_entity.py',
    #                 arguments=['-topic', 'robot_description',
    #                             '-entity', 'cart'],
    #                 output='screen')

    # Parameters
    robot_controllers = os.path.join(
        arctos_moveit_dir, 'config', 'ros2_controllers.yaml'
    )

    control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[robot_controllers],
        output={'stdout': 'screen', 'stderr': 'screen'},
        arguments=[
            '--ros-args',
            # '--log-level', 'debug',
            '--log-level', 'arctos_hardware_interface:=info',
            '--log-level', 'controller_manager:=info'
        ],
        remappings={
             ("/controller_manager/robot_description", "/robot_description"),
        }
    )

    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["joint_state_broadcaster", "--controller-manager", "/controller_manager"],
    )

    robot_arm_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["denso_arm_controller", "--controller-manager", "/controller_manager"],
    )

    robot_hand_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["arctos_hand_controller", "--controller-manager", "/controller_manager"],
    )

    # # Include CAN Launch
    # can_launch = IncludeLaunchDescription(
    #     PythonLaunchDescriptionSource(
    #         PathJoinSubstitution([arctos_hardware_interface_dir, "launch", "can_interface.launch.py"])
    #     )
    # )

    # Include MoveIt Launch
    move_group_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([arctos_moveit_dir, "launch", "move_group.launch.py"])
        )
    )

    # Ensure joint state broadcaster starts before controllers
    delay_robot_arm_controller_spawner = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=joint_state_broadcaster_spawner,
            on_exit=[robot_arm_controller_spawner, robot_hand_controller_spawner],
        )
    )

    # Delay rviz and moveit launch until controllers are ready
    delay_rviz_and_moveit_launch = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=robot_arm_controller_spawner,
            on_exit=[rviz_node, move_group_launch]
        ))
    camera_node = Node(
        package='v4l2_camera',
        executable='v4l2_camera_node',
        name='v4l2_camera',
        output='screen',
        parameters=[
            {
                # 'video_device': '/dev/video1',     # đổi device tại đây
                # 'image_width': 640,
                # 'image_height': 480,
                # 'pixel_format': 'YUYV',             # hoặc MJPG
                # 'frame_rate': 30.0,
                # 'camera_frame_id': 'camera_link',
                # 'qos_overrides': {
                #     '/camera/image_raw': {
                #         'publisher': {
                #             'reliability': 'best_effort',
                #             'history': 'keep_last',
                #             'depth': 100,
                #         }
                #     }
                # }
                'video_device': '/dev/video0',     
                'image_size': [640, 480],
                'pixel_format': 'YUYV',             
                'output_encoding': 'rgb8', 
                'qos_overrides': {
                    '/camera/image_raw': {
                        'publisher': {
                            'reliability': 'best_effort',
                            'history': 'keep_last',
                            'depth': 100,
                        }
                    }
                }
            }
        ],
        remappings=[
            ('image_raw', '/camera/image_raw'),
            ('camera_info', '/camera/camera_info')
        ]
    )
    # camera_subscriber = Node(
    #     package="v4l2_camera",
    #     executable="camera_subscriber_node",
    #     name="camera_subscriber",
    #     # name="robot_state_publisher",
    # )
    return LaunchDescription([
        LogInfo(msg=["Launching Arctos Bringup with RViz..."]),
        camera_node,
        # camera_subscriber,
        control_node,
        gazebo,
        gz_bridge,
        robot_state_pub_node,
        joint_state_broadcaster_spawner,
        delay_robot_arm_controller_spawner,
        delay_rviz_and_moveit_launch,
        # spawn_entity,
        # can_launch
    ])
