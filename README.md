# ロボコン手動機 操縦コンソール

スマホ(roslibjs) ⇄ rosbridge ⇄ ROS2(Raspberry Pi 5) ⇄ CAN-FD ⇄ STM32(HAL)

## 前提

- ROS2 Humble（Pi: Ubuntu 22.04）または Jazzy（開発PC: Ubuntu 24.04）
- rosbridge インストール済み

```bash
# Humble
sudo apt install ros-humble-rosbridge-suite
# Jazzy
sudo apt install ros-jazzy-rosbridge-suite
```

## セットアップ

```bash
cd ~/CITRobocon/robocon-console/ros2_ws
colcon build --packages-select robocon_bridge
source install/setup.bash
```

## 起動

```bash
ros2 launch robocon_bridge bringup.launch.py
```

rosbridge(ws://0.0.0.0:9090) と mock_node が同時に起動します。

待ち受け確認：

```bash
ss -tlnp | grep 9090
```

## スマホ HMI の接続

1. スマホとPiを同じ Wi-Fi に接続
2. `web/robot-console.html` をブラウザで開く
3. 接続先に `ws://<Pi の IP>:9090` を入力して接続
4. スティック操作 → Pi 側ターミナルに `cmd_vel` ログが出る
5. 画面に擬似テレメトリ（vbat / state / wheels）が表示される

## 動作確認（CLI）

```bash
# テレメトリ確認
ros2 topic echo /robot/telemetry

# コマンド送信テスト
ros2 topic pub --once /robot/command std_msgs/msg/String '{data: "align"}'

# cmd_vel 送信テスト
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.5, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.1}}'
```

## リポジトリ構成

```
robocon-console/
├── web/robot-console.html              # スマホ HMI
├── ros2_ws/src/robocon_bridge/
│   ├── robocon_bridge/
│   │   ├── mock_node.py                # 擬似テレメトリ＋コマンド受信ログ
│   │   └── can_bridge_node.py          # CAN ⇄ トピック中継（CAN確定後）
│   └── launch/bringup.launch.py        # rosbridge + ノード一括起動
└── firmware/                           # STM32 HAL 側（後段）
```

## トピック契約

| トピック | 型 | 向き | 内容 |
|---|---|---|---|
| `/cmd_vel` | `geometry_msgs/msg/Twist` | 端末→機体 | linear.x=前後, linear.y=横, angular.z=旋回。20Hz |
| `/robot/command` | `std_msgs/msg/String` | 端末→機体 | `align` / `home` / `deploy` / `reset` / `estop` / `release` |
| `/robot/telemetry` | `std_msgs/msg/String` | 機体→端末 | JSON ~10Hz。`{"vbat":23.8,"state":"MANUAL","wheels":[...]}` |
