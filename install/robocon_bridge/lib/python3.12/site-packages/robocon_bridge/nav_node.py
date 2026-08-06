import json
import math

import rclpy
from geometry_msgs.msg import PoseStamped, Twist
from rclpy.node import Node
from std_msgs.msg import Bool, String

# 到達判定・速度上限・ゲインは仮置き。実際の運動学と一緒に詰める
REACH_DIST_THRESHOLD_M = 0.15
CMD_VEL_MAX_LIN = 0.3
CMD_VEL_MAX_ANG = 0.5
GOTO_KP_LIN = 1.0
GOTO_KP_ANG = 1.0

TICK_HZ = 20.0


class NavNode(Node):
    """/robot/goal を受けて go-to-point 走行をアクティブ化するノードの骨格。

    運動学・制御は未実装。今回はトピック配線と
    goal受信→アクティブ→cancel/到達→解除、の状態遷移だけを正しく作る。
    """

    def __init__(self):
        super().__init__('nav_node')
        self._active = False
        self._goal_xy = None   # (x, y) map frame, m
        self._pose_xy = None   # (x, y) map frame, m（/robot/telemetry の pose）

        self._cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self._nav_state_pub = self.create_publisher(String, '/robot/nav_state', 10)

        self.create_subscription(PoseStamped, '/robot/goal', self._on_goal, 10)
        self.create_subscription(Bool, '/robot/goal_cancel', self._on_goal_cancel, 10)
        self.create_subscription(String, '/robot/telemetry', self._on_telemetry, 10)

        self.create_timer(1.0 / TICK_HZ, self._tick)
        self.get_logger().info('nav_node (skeleton, no kinematics) started')

    def _on_goal(self, msg: PoseStamped):
        self._goal_xy = (msg.pose.position.x, msg.pose.position.y)
        self._active = True
        self.get_logger().info(f'goal received {self._goal_xy}, nav -> auto')

    def _on_goal_cancel(self, msg: Bool):
        if msg.data and self._active:
            self._active = False
            self._goal_xy = None
            self.get_logger().info('goal_cancel received, nav -> manual')

    def _on_telemetry(self, msg: String):
        try:
            data = json.loads(msg.data)
        except (json.JSONDecodeError, TypeError):
            return
        pose = data.get('pose')
        if pose is None:
            return
        self._pose_xy = (float(pose['x']), float(pose['y']))

    def _reached_goal(self) -> bool:
        if self._goal_xy is None or self._pose_xy is None:
            return False
        dx = self._goal_xy[0] - self._pose_xy[0]
        dy = self._goal_xy[1] - self._pose_xy[1]
        return math.hypot(dx, dy) <= REACH_DIST_THRESHOLD_M

    def _tick(self):
        if self._active and self._reached_goal():
            self._active = False
            self._goal_xy = None
            self.get_logger().info('goal reached, nav -> manual')

        if self._active:
            # TODO: go-to-point制御をここに実装する（GOTO_KP_LIN/GOTO_KP_ANG,
            # CMD_VEL_MAX_LIN/CMD_VEL_MAX_ANG を使って goal_xy - pose_xy から /cmd_vel を計算）。
            # 現状はプレースホルダとして 0 を publish するだけ。
            self._cmd_vel_pub.publish(Twist())

        state = String()
        state.data = 'auto' if self._active else 'manual'
        self._nav_state_pub.publish(state)


def main(args=None):
    rclpy.init(args=args)
    node = NavNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
