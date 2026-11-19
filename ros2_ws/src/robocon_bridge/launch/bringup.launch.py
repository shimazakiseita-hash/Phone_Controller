import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    use_mock_arg = DeclareLaunchArgument('use_mock', default_value='false')

    robot_profile_arg = DeclareLaunchArgument('robot_profile', default_value='torobo')

    web_dir_arg = DeclareLaunchArgument(
        'web_dir', default_value=os.path.expanduser('~/Phone_Controller/web')
    )

    rosbridge = Node(
        package='rosbridge_server',
        executable='rosbridge_websocket',
        name='rosbridge_websocket',
        parameters=[{'port': 9090}],
    )

    mock = Node(
        package='robocon_bridge',
        executable='mock_node',
        name='mock_node',
        output='screen',
        condition=IfCondition(LaunchConfiguration('use_mock')),
    )

    cmd_vel_to_joy = Node(
        package='robocon_bridge',
        executable='cmd_vel_to_joy',
        name='cmd_vel_to_joy',
        parameters=[{'robot_profile': LaunchConfiguration('robot_profile')}],
        output='screen',
    )

    nav_node = Node(
        package='robocon_bridge',
        executable='nav_node',
        name='nav_node',
        output='screen',
    )

    web_server = ExecuteProcess(
        cmd=['python3', '-m', 'http.server', '8080'],
        cwd=LaunchConfiguration('web_dir'),
    )

    return LaunchDescription([use_mock_arg, robot_profile_arg, web_dir_arg, rosbridge, mock, cmd_vel_to_joy, nav_node, web_server])
