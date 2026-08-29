import json
import math

import rclpy
from geometry_msgs.msg import PoseStamped, Twist
from rclpy.node import Node
from std_msgs.msg import Bool, String

# 到達判定・速度上限・ゲインは仮置き。実機で走らせながら調整する
REACH_DIST_THRESHOLD_M = 0.15
REACH_ANGLE_THRESHOLD_RAD = 0.26  # 約15度。ここから先は操縦者が手動で微調整する前提なので粗くてよい
CMD_VEL_MAX_LIN = 0.3
CMD_VEL_MAX_ANG = 0.5
GOTO_KP_LIN = 1.0
GOTO_KP_ANG = 1.0

TICK_HZ = 20.0


def _yaw_from_quaternion(q) -> float:
    """クォータニオン(Z軸回転のみ想定)からyaw(rad)を取り出す。"""
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def _normalize_angle(a: float) -> float:
    """角度を[-pi, pi]に正規化する。"""
    return math.atan2(math.sin(a), math.cos(a))


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _clamp_vec2(x: float, y: float, max_mag: float):
    """(x,y)をmax_magまでの大きさに制限する。x/yを別々にクランプすると本来の移動方向が
    崩れる(例: x方向だけ大きい誤差でもy方向にわずかに漏れがあると、両方が上限に張り付いて
    45度の斜め移動になってしまう)ため、方向を保ったまま大きさだけ縮める。"""
    mag = math.hypot(x, y)
    if mag <= max_mag or mag == 0.0:
        return x, y
    scale = max_mag / mag
    return x * scale, y * scale


class NavNode(Node):
    """/robot/goal を受けて go-to-point 走行を行うノード。

    全方向駆動(ホロノミック)前提: 目標との位置誤差を機体座標系に回転させてから
    linear.x/yへ、目標角度との差をangular.zへ、それぞれ独立に比例制御で流す。
    """

    def __init__(self):
        super().__init__('nav_node')
        self._active = False
        self._goal_xy = None      # (x, y) map frame, m
        self._goal_theta = None   # rad, map frame
        self._pose_xy = None      # (x, y) map frame, m（/robot/telemetry の pose）
        self._pose_theta = None   # rad

        self._cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self._nav_state_pub = self.create_publisher(String, '/robot/nav_state', 10)

        self.create_subscription(PoseStamped, '/robot/goal', self._on_goal, 10)
        self.create_subscription(Bool, '/robot/goal_cancel', self._on_goal_cancel, 10)
        self.create_subscription(String, '/robot/telemetry', self._on_telemetry, 10)

        self.create_timer(1.0 / TICK_HZ, self._tick)
        self.get_logger().info('nav_node started')

    def _on_goal(self, msg: PoseStamped):
        self._goal_xy = (msg.pose.position.x, msg.pose.position.y)
        self._goal_theta = _yaw_from_quaternion(msg.pose.orientation)
        self._active = True
        self.get_logger().info(f'goal received {self._goal_xy}, theta={self._goal_theta:.2f}, nav -> auto')

    def _on_goal_cancel(self, msg: Bool):
        if msg.data and self._active:
            self._active = False
            self._goal_xy = None
            self._goal_theta = None
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
        self._pose_theta = float(pose['theta'])

    def _reached_goal(self) -> bool:
        if self._goal_xy is None or self._pose_xy is None or self._pose_theta is None:
            return False
        dx = self._goal_xy[0] - self._pose_xy[0]
        dy = self._goal_xy[1] - self._pose_xy[1]
        dtheta = _normalize_angle(self._goal_theta - self._pose_theta)
        return math.hypot(dx, dy) <= REACH_DIST_THRESHOLD_M and abs(dtheta) <= REACH_ANGLE_THRESHOLD_RAD

    def _tick(self):
        if self._active and self._reached_goal():
            self._active = False
            self._goal_xy = None
            self._goal_theta = None
            self.get_logger().info('goal reached, nav -> manual')

        if self._active and self._pose_xy is not None and self._pose_theta is not None:
            ex = self._goal_xy[0] - self._pose_xy[0]
            ey = self._goal_xy[1] - self._pose_xy[1]
            c, s = math.cos(self._pose_theta), math.sin(self._pose_theta)
            # 世界座標系の位置誤差(ex,ey) -> 機体座標系へ回転(world->body、機体はホロノミックなので
            # 向きに関係なくこの方向へそのまま並進できる)
            body_x = ex * c + ey * s
            body_y = -ex * s + ey * c
            dtheta = _normalize_angle(self._goal_theta - self._pose_theta)

            cmd = Twist()
            lx, ly = _clamp_vec2(GOTO_KP_LIN * body_x, GOTO_KP_LIN * body_y, CMD_VEL_MAX_LIN)
            cmd.linear.x = lx
            cmd.linear.y = ly
            cmd.angular.z = _clamp(GOTO_KP_ANG * dtheta, -CMD_VEL_MAX_ANG, CMD_VEL_MAX_ANG)
            self._cmd_vel_pub.publish(cmd)
        elif self._active:
            # まだ自己位置(pose)を受信できていない場合は動かさない
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
