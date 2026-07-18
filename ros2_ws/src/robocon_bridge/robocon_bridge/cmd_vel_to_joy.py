import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import Joy

AXES_SIZE = 8
BUTTONS_SIZE = 8

# torobo2026_ros2_rp/pscon_node.cpp の実装に合わせる:
# axes[3]=st_rx, axes[4]=st_ry, axes[6]=cross_bt(-1/0/1のみ判定、連続値不可)
AXIS_ST_RX = 3
AXIS_ST_RY = 4
AXIS_CROSS_BT = 6

TURN_DEADZONE = 0.1


class CmdVelToJoyNode(Node):
    def __init__(self):
        super().__init__('cmd_vel_to_joy')
        self._joy_pub = self.create_publisher(Joy, '/joy', 10)
        self.create_subscription(Twist, '/cmd_vel', self._on_cmd_vel, 10)
        self.get_logger().info('cmd_vel_to_joy started')

    def _on_cmd_vel(self, msg: Twist):
        joy = Joy()
        joy.header.stamp = self.get_clock().now().to_msg()
        joy.axes = [0.0] * AXES_SIZE
        joy.axes[AXIS_ST_RY] = msg.linear.x
        joy.axes[AXIS_ST_RX] = msg.linear.y
        if msg.angular.z > TURN_DEADZONE:
            joy.axes[AXIS_CROSS_BT] = 1.0
        elif msg.angular.z < -TURN_DEADZONE:
            joy.axes[AXIS_CROSS_BT] = -1.0
        joy.buttons = [0] * BUTTONS_SIZE
        self._joy_pub.publish(joy)


def main(args=None):
    rclpy.init(args=args)
    node = CmdVelToJoyNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
