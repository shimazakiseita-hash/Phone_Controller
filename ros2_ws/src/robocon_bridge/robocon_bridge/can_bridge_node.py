import rclpy
from rclpy.node import Node


class CanBridgeNode(Node):
    def __init__(self):
        super().__init__('can_bridge_node')
        # TODO: implement CAN <-> topic relay (SocketCAN or SPI userspace driver)


def main(args=None):
    rclpy.init(args=args)
    node = CanBridgeNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
