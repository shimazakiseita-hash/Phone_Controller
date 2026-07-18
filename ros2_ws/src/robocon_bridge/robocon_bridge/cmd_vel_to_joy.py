import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import Joy

AXES_SIZE = 8
BUTTONS_SIZE = 8

# PS4標準レイアウト: 左スティック(0=横,1=前後), 右スティック(3=旋回)
AXIS_STRAFE = 0
AXIS_FORWARD = 1
AXIS_TURN = 3


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
        joy.axes[AXIS_FORWARD] = msg.linear.x
        joy.axes[AXIS_STRAFE] = msg.linear.y
        joy.axes[AXIS_TURN] = msg.angular.z
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
