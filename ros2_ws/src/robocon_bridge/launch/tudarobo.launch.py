import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node


def generate_launch_description():
    bringup = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('robocon_bridge'),
                'launch',
                'bringup.launch.py',
            )
        ),
        launch_arguments={'robot_profile': 'tudarobo'}.items(),
    )

    pscon = Node(
        package='pscon_node',
        executable='pscon_node',
        name='pscon_node',
        output='screen',
    )

    can = Node(
        package='can_node',
        executable='can_node',
        output='screen',
    )

    return LaunchDescription([bringup, pscon, can])
