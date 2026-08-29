import rclpy
from geometry_msgs.msg import Twist
from rclpy.duration import Duration
from rclpy.node import Node
from sensor_msgs.msg import Joy
from std_msgs.msg import String
from std_msgs.msg import UInt8

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
# 本コントローラ(スマホ)の基本経路は torobo2026_ros2_rp/pscon_node.cpp → can_node.cpp。
# can_node.cpp が bt_data(=buttons[0..7]) をXbox系パッドのボタン配置（A B X Y LB RB LT）として
# そのまま解釈するため、ここもそのビット位置に合わせる（can_node.cpp 側は一切変更しない前提）。
# なお ps4con_node.cpp/can_ps4_node.cpp という別ノード一式もあるが、これは実PS4パッド直挿し時の
# 非常用バックアップ経路(×○△□L1 R1 L2 R2配置)で、本コントローラの経路とは別物（詳細は
# firmware/CAN_COMMAND_SPEC.md）。
# 旧id(arm_stow/launch_to_intake/gate/checkpoint)はcan_ps4_node.cppのボタン配置に引きずられた古い
# ラベルで、can_node.cpp側の実際の割り当てと一致しなくなっていたため、2026/8時点の実態に合わせて修正した。
# index7(RT)はLidar位置補正のホールド操作に割り当て。ホールド中はUI側がBUTTON_PULSE_Sより短い
# 間隔で'lidar_correct'を送り続けてパルスを継続更新することで「押している間だけ有効」を実現する
# （can_node.cpp側もbt_dataのbit7を読むたびに判定するホールド式なので、この仕組みと相性が良い）。
COMMAND_BUTTON_MAP = {
    'release_suction': 0,  # A: 吸引切る(設置)
    'intake': 1,           # B: 回収
    'launch': 2,           # Y: 射出
    'arm_start': 3,        # X: 初期(リセット)
    'arm_force_stop': 4,   # LB: アーム移動強制ストップ
    'manual_adjust': 5,    # RB: 手動位置調整(ベル直位置調整)
    'descend_adjust': 6,   # LT: 降下微調整
    'lidar_correct': 7,    # RT: ボール回収位置補正起動(ホールド中のみ有効)
}
# 十字キー -> axes index（pscon_node.cpp側の実PS4パッドaxes[0..3]配置に合わせる）
DPAD_AXIS_MAP = {
    'dpad_up': 0,
    'dpad_right': 1,
    'dpad_left': 2,
    'dpad_down': 3,
}

# シーケンス情報 赤青別
SEQUENCE_MAP = {
    'not_started': 0b00000000,
    'sequence_red_1': 0b00000001,
    'sequence_red_2': 0b00000010,
    'sequence_red_3': 0b00000011,
    'sequence_red_4': 0b00000100,
    'sequence_red_5': 0b00000101,
    'sequence_red_6': 0b00000110,
    'sequence_red_7': 0b00000111,
    'sequence_red_8': 0b00001000,
    'sequence_red_9': 0b00001001,

    'sequence_blue_1': 0b10000001,
    'sequence_blue_2': 0b10000010,
    'sequence_blue_3': 0b10000011,
    'sequence_blue_4': 0b10000100,
    'sequence_blue_5': 0b10000101,
    'sequence_blue_6': 0b10000110,
    'sequence_blue_7': 0b10000111,
    'sequence_blue_8': 0b10001000,
    'sequence_blue_9': 0b10001001,
}

# ボタンは押しっぱなし連射を防ぐため、受信のたびにこの秒数だけ1を出すエッジパルスにする
BUTTON_PULSE_S = 0.15

class CmdVelToJoyNode(Node):
    """/cmd_vel(Twist,軸) と /robot/command(String,ボタン) をマージして /joy を20Hz固定で publish する。

    buttons[0..7] は /robot/command 由来のエッジパルス（実Xbox系パッドのボタン配置A B X Y LB RB LTに
    対応する定型アーム動作。COMMAND_BUTTON_MAP参照）。can_node.cpp 側のプロトコルに合わせている。
    射出・手動位置調整はY/RBとして実装済み。十字キー4方向(DPAD_AXIS_MAP)はcan_node.cppのcross_data
    判定（ベル直設置/2個めボール置き場/城門設置高さ/関所設置高さ）に対応する。

    安全ゲート:
      - デッドマン: 最後の /cmd_vel から DEADMAN_TIMEOUT_S 秒を超えたら停止
      - estop: /robot/command で 'estop' を受けたら 'release' が来るまで停止をラッチ
      - 停止中は axes・buttons とも全0（ボタンパルスの途中・ジョグホールド中でも打ち切る）
    """

    def __init__(self):
        super().__init__('cmd_vel_to_joy')
        self._joy_pub = self.create_publisher(Joy, '/joy', 10)
        self._sequence_pub = self.create_publisher(UInt8, '/sequence', 10) #シーケンス用
        self.create_subscription(Twist, '/cmd_vel', self._on_cmd_vel, 10)
        self.create_subscription(String, '/robot/command', self._on_command, 10)

        self._last_cmd = Twist()
        self._last_cmd_time = None  # 一度も受信していなければ None（＝デッドマン発動中として扱う）
        self._estop_latched = False
        self._pulse_until = {}  # button index -> パルス終了時刻(rclpy.time.Time)
        self._axis_pulse_until = {}  # 追加: axis index -> パルス終了時刻(十字キー用)
        self._sequence = SEQUENCE_MAP['not_started']

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
        elif cmd in SEQUENCE_MAP:
            self._sequence = SEQUENCE_MAP[cmd]
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

        sq_msg = UInt8()
        sq_msg.data = self._sequence
        self._sequence_pub.publish(sq_msg)


def main(args=None):
    rclpy.init(args=args)
    node = CmdVelToJoyNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
