import pytest
import rclpy
from geometry_msgs.msg import Twist
from rclpy.duration import Duration
from std_msgs.msg import String

from robocon_bridge.cmd_vel_to_joy import (
    CmdVelToJoyNode,
    DEADMAN_TIMEOUT_S,
    TURN_DEADZONE,
    tudarobo_turn_fast,
)


@pytest.mark.parametrize('value', [1.0, -1.0, 0.75, -0.75])
def test_fast_at_or_above_threshold(value):
    assert tudarobo_turn_fast(value)


@pytest.mark.parametrize('value', [0.5, -0.5, 0.749, -0.749, 0.05, 0.0,
                                   TURN_DEADZONE, -TURN_DEADZONE])
def test_slow_below_threshold(value):
    assert not tudarobo_turn_fast(value)


@pytest.fixture
def node(request):
    profile = getattr(request, 'param', None)
    args = ['--ros-args', '-p', f'robot_profile:={profile}'] if profile else []
    rclpy.init(args=args)
    bridge = CmdVelToJoyNode()
    messages = []
    bridge._joy_pub = type('Publisher', (), {'publish': lambda _, msg: messages.append(msg)})()
    bridge.messages = messages
    try:
        yield bridge
    finally:
        bridge.destroy_node()
        rclpy.shutdown()


@pytest.mark.parametrize('node', ['tudarobo', 'torobo', 'unknown', None], indirect=True)
@pytest.mark.parametrize('angular_z', [1.0, -1.0, 0.5, 0.1, 0.0])
def test_profile_output(node, angular_z):
    cmd = Twist()
    cmd.linear.x = 0.4
    cmd.linear.y = -0.3
    cmd.angular.z = angular_z
    node._on_cmd_vel(cmd)
    node._publish()
    joy = node.messages[-1]
    assert list(joy.axes) == pytest.approx([
        0.0, 0.0, 0.0, 0.0, -0.3, 0.4,
        (1.0 if angular_z > 0 else -1.0) if abs(angular_z) > TURN_DEADZONE else 0.0,
        abs(angular_z) if abs(angular_z) > TURN_DEADZONE else 0.0,
    ])
    expected_fast = node._robot_profile == 'tudarobo' and tudarobo_turn_fast(angular_z)
    assert list(joy.buttons) == [0] * 7 + [int(expected_fast)]


@pytest.mark.parametrize('node', ['tudarobo'], indirect=True)
@pytest.mark.parametrize('stop', ['never_received', 'deadman', 'estop'])
def test_stopped_clears_fast_bit(node, stop):
    cmd = Twist()
    cmd.angular.z = 1.0
    node._on_cmd_vel(cmd)
    node._on_command(String(data='lidar_correct'))
    if stop == 'never_received':
        node._last_cmd_time = None
    elif stop == 'deadman':
        node._last_cmd_time = node.get_clock().now() - Duration(seconds=DEADMAN_TIMEOUT_S + 0.1)
    else:
        node._on_command(String(data='estop'))
    node._publish()
    assert list(node.messages[-1].axes) == [0.0] * 8
    assert list(node.messages[-1].buttons) == [0] * 8
