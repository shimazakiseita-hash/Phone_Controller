import rclpy
from geometry_msgs.msg import Twist
from rclpy.duration import Duration
from rclpy.node import Node
from sensor_msgs.msg import Joy
from std_msgs.msg import String

AXES_SIZE = 8
BUTTONS_SIZE = 9
PUBLISH_HZ = 20.0

# torobo2026_ros2_rp/pscon_node.cpp の実装に合わせる:
# axes[3]=st_rx, axes[4]=st_ry, axes[6]=cross_bt(-1/0/1のみ判定、連続値不可)
AXIS_ST_RX = 3
AXIS_ST_RY = 4
AXIS_CROSS_BT = 6

TURN_DEADZONE = 0.1

# デッドマン: 最後に /cmd_vel を受信してからこの秒数を超えたら停止（axes/buttons全0）とみなす
DEADMAN_TIMEOUT_S = 0.2

# /robot/command の command_id -> buttons index（pscon_node が buttons[0..8] を読む前提。9要素固定）
COMMAND_BUTTON_MAP = {
    'launch': 0,
    'intake': 1,
    'checkpoint': 2,
    'gate': 3,
}

# ボタンは押しっぱなし連射を防ぐため、受信のたびにこの秒数だけ1を出すエッジパルスにする
BUTTON_PULSE_S = 0.15

# 機構手動ジョグ（ホールドで動作、離すと停止）。新規トピックは増やさず、/cmd_vel の未使用フィールド
# linear.z=アーム上下, angular.x=アーム左右 に載せて送られてくる値を、/joy の buttons[4..7] に変換する。
# ハンドは吸着式のため仰角は無い（アームは上下左右の平面2軸ジョグのみ）。
# ホールド中は毎フレーム/cmd_velが再送されるため、上のBUTTON_PULSE_Sのようなパルス処理は不要
# （デッドマン切れやestopで自動的に0へ落ちるので、buttons[0..3]と同じ安全ゲートの中で扱う）。
JOG_DEADZONE = 0.5  # -1/0/+1 のデジタル値想定なので緩めのしきい値でよい
BUTTON_ARM_UP = 4
BUTTON_ARM_DOWN = 5
BUTTON_ARM_LEFT = 6
BUTTON_ARM_RIGHT = 7

# 吸着（トグル、ホールド中のような単発値ではなく画面/パッド側でON/OFF状態そのものを管理）。
# /cmd_vel.angular.y に 0/1 を載せて送られてくる値を /joy の buttons[8] に変換する。
# デッドマン切れ・estopでは他のbuttonsと同様に強制0（吸着解除）になる。
SUCTION_DEADZONE = 0.5
BUTTON_SUCTION = 8


class CmdVelToJoyNode(Node):
    """/cmd_vel(Twist,軸) と /robot/command(String,ボタン) をマージして /joy を20Hz固定で publish する。

    buttons[0..3] は /robot/command 由来のエッジパルス（定型シーケンス起動: launch/intake/checkpoint/gate）、
    buttons[4..7] は /cmd_vel.linear.z / angular.x 由来のホールド値（アーム上下左右の手動ジョグ）、
    buttons[8] は /cmd_vel.angular.y 由来のホールド値（吸着トグルの現在状態）。

    安全ゲート:
      - デッドマン: 最後の /cmd_vel から DEADMAN_TIMEOUT_S 秒を超えたら停止
      - estop: /robot/command で 'estop' を受けたら 'release' が来るまで停止をラッチ
      - 停止中は axes・buttons とも全0（ボタンパルスの途中・ジョグホールド中でも打ち切る）
    """

    def __init__(self):
        super().__init__('cmd_vel_to_joy')
        self._joy_pub = self.create_publisher(Joy, '/joy', 10)
        self.create_subscription(Twist, '/cmd_vel', self._on_cmd_vel, 10)
        self.create_subscription(String, '/robot/command', self._on_command, 10)

        self._last_cmd = Twist()
        self._last_cmd_time = None  # 一度も受信していなければ None（＝デッドマン発動中として扱う）
        self._estop_latched = False
        self._pulse_until = {}  # button index -> パルス終了時刻(rclpy.time.Time)

        self.create_timer(1.0 / PUBLISH_HZ, self._publish)
        self.get_logger().info('cmd_vel_to_joy (axes+buttons merge) started')

    def _on_cmd_vel(self, msg: Twist):
        self._last_cmd = msg
        self._last_cmd_time = self.get_clock().now()

    def _on_command(self, msg: String):
        cmd = msg.data
        if cmd == 'estop':
            self._estop_latched = True
            self.get_logger().warn('estop latched via /robot/command')
        elif cmd == 'release':
            self._estop_latched = False
            self.get_logger().info('estop released via /robot/command')
        elif cmd in COMMAND_BUTTON_MAP:
            idx = COMMAND_BUTTON_MAP[cmd]
            self._pulse_until[idx] = self.get_clock().now() + Duration(seconds=BUTTON_PULSE_S)
        else:
            self.get_logger().warn(f'unknown /robot/command id ignored: {cmd!r}')

    def _deadman_ok(self) -> bool:
        if self._last_cmd_time is None:
            return False
        age_s = (self.get_clock().now() - self._last_cmd_time).nanoseconds / 1e9
        return age_s <= DEADMAN_TIMEOUT_S

    def _publish(self):
        stopped = self._estop_latched or not self._deadman_ok()

        axes = [0.0] * AXES_SIZE
        buttons = [0] * BUTTONS_SIZE

        if not stopped:
            axes[AXIS_ST_RY] = self._last_cmd.linear.x
            axes[AXIS_ST_RX] = self._last_cmd.linear.y
            if self._last_cmd.angular.z > TURN_DEADZONE:
                axes[AXIS_CROSS_BT] = 1.0
            elif self._last_cmd.angular.z < -TURN_DEADZONE:
                axes[AXIS_CROSS_BT] = -1.0

            now = self.get_clock().now()
            for idx, until in self._pulse_until.items():
                if now < until:
                    buttons[idx] = 1

            if self._last_cmd.linear.z > JOG_DEADZONE:
                buttons[BUTTON_ARM_UP] = 1
            elif self._last_cmd.linear.z < -JOG_DEADZONE:
                buttons[BUTTON_ARM_DOWN] = 1
            if self._last_cmd.angular.x > JOG_DEADZONE:
                buttons[BUTTON_ARM_LEFT] = 1
            elif self._last_cmd.angular.x < -JOG_DEADZONE:
                buttons[BUTTON_ARM_RIGHT] = 1

            if self._last_cmd.angular.y > SUCTION_DEADZONE:
                buttons[BUTTON_SUCTION] = 1

        joy = Joy()
        joy.header.stamp = self.get_clock().now().to_msg()
        joy.axes = axes
        joy.buttons = buttons
        self._joy_pub.publish(joy)


def main(args=None):
    rclpy.init(args=args)
    node = CmdVelToJoyNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
