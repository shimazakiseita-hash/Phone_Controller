from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
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
    )

    return LaunchDescription([rosbridge, mock])
