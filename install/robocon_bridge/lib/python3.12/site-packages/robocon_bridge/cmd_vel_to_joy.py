import rclpy
from geometry_msgs.msg import Twist
from rclpy.duration import Duration
from rclpy.node import Node
from sensor_msgs.msg import Joy
from std_msgs.msg import String

AXES_SIZE = 8
BUTTONS_SIZE = 8
PUBLISH_HZ = 20.0

# torobo2026_ros2_rp/pscon_node.cpp の実装に合わせる:
# axes[3]=st_rx, axes[4]=st_ry, axes[6]=cross_bt(-1/0/1のみ判定、連続値不可)
AXIS_ST_RX = 4
AXIS_ST_RY = 5
AXIS_CROSS_BT = 6
#AXIS_CROSS_BT_R = 7

TURN_DEADZONE = 0.1

# デッドマン: 最後に /cmd_vel を受信してからこの秒数を超えたら停止（axes/buttons全0）とみなす
DEADMAN_TIMEOUT_S = 0.2

# /robot/command の command_id -> buttons index。
# torobo2026_ros2_rp/can_ps4_node.cpp が bt_data(=buttons[0..7]) を実PS4パッドのボタン配置
# （×○△□L1 R1 L2 R2）としてそのまま解釈するため、ここもそのビット位置に合わせる
# （can_ps4_node.cpp 側は一切変更しない前提）。
COMMAND_BUTTON_MAP = {
    'release_suction': 0,  # A: 吸引切る(設置)
    'intake': 1,           # B: 回収
    'arm_stow': 2,         # RT: アーム収納
    'arm_start': 3,        # X: スタート初期移動
    'launch_to_intake': 4, # L1: ベル直設置→回収
    'gate': 5,             # R1: 城門設置高さ
    'descend_adjust': 6,   # L2: 降下微調整
    'checkpoint': 7,       # R2: 関所設置高さ
}
# 十字キー -> axes index（pscon_node.cpp側の実PS4パッドaxes[0..3]配置に合わせる）
DPAD_AXIS_MAP = {
    'dpad_up': 0,
    'dpad_right': 1,
    'dpad_left': 2,
    'dpad_down': 3,
}

# ボタンは押しっぱなし連射を防ぐため、受信のたびにこの秒数だけ1を出すエッジパルスにする
BUTTON_PULSE_S = 0.15


class CmdVelToJoyNode(Node):
    """/cmd_vel(Twist,軸) と /robot/command(String,ボタン) をマージして /joy を20Hz固定で publish する。

    buttons[0..7] は /robot/command 由来のエッジパルス（実PS4パッドのボタン配置×○△□L1 R1 L2 R2に
    対応する定型アーム動作。COMMAND_BUTTON_MAP参照）。can_ps4_node.cpp 側のプロトコルに合わせているため、
    射出・手動ジョグ・吸着トグルはこの経路には無い（実PS4パイプライン側が未実装のため今回は対象外）。

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
        self._axis_pulse_until = {}  # 追加: axis index -> パルス終了時刻(十字キー用)

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
        elif cmd in DPAD_AXIS_MAP:  # 追加
            idx = DPAD_AXIS_MAP[cmd]
            self._axis_pulse_until[idx] = self.get_clock().now() + Duration(seconds=BUTTON_PULSE_S)
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
            now = self.get_clock().now()
            for idx, until in self._axis_pulse_until.items():
                if now < until:
                    axes[idx] = 1.0

            axes[AXIS_ST_RY] = self._last_cmd.linear.x
            axes[AXIS_ST_RX] = self._last_cmd.linear.y
            if self._last_cmd.angular.z > TURN_DEADZONE:
                axes[AXIS_CROSS_BT] = 1.0
            elif self._last_cmd.angular.z < -TURN_DEADZONE:
                axes[AXIS_CROSS_BT] = -1.0

            #now = self.get_clock().now()
            for idx, until in self._pulse_until.items():
                if now < until:
                    buttons[idx] = 1

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
