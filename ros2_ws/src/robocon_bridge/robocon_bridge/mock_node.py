import json
import math
import random

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import String


class MockNode(Node):
    def __init__(self):
        super().__init__('mock_node')
        self._t = 0.0

        self._telemetry_pub = self.create_publisher(String, '/robot/telemetry', 10)
        self.create_timer(0.1, self._publish_telemetry)

        self.create_subscription(Twist, '/cmd_vel', self._on_cmd_vel, 10)
        self.create_subscription(String, '/robot/command', self._on_command, 10)

        self.get_logger().info('mock_node started')

    def _publish_telemetry(self):
        self._t += 0.1
        payload = {
            'vbat': round(23.8 + 0.4 * math.sin(self._t * 0.3) + random.uniform(-0.05, 0.05), 2),
            'state': 'MANUAL',
            'wheels': [
                {
                    'angle': round(15.0 * math.sin(self._t + i * math.pi / 2) + random.uniform(-0.5, 0.5), 2),
                    'ok': True,
                }
                for i in range(4)
            ],
        }
        msg = String()
        msg.data = json.dumps(payload)
        self._telemetry_pub.publish(msg)

    def _on_cmd_vel(self, msg: Twist):
        self.get_logger().info(
            f'cmd_vel  lx={msg.linear.x:.3f} ly={msg.linear.y:.3f} az={msg.angular.z:.3f}'
        )

    def _on_command(self, msg: String):
        self.get_logger().info(f'command  {msg.data}')


def main(args=None):
    rclpy.init(args=args)
    node = MockNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
