# ロボコン手動機 操縦コンソール

スマホ(roslibjs) ⇄ rosbridge ⇄ ROS2(Raspberry Pi 5) ⇄ /joy ⇄ [チーム側] pscon_node → can_node → SPI → クラシックCAN 500kbps → STM32(HAL)

本リポジトリの担当範囲は `/joy` publish まで。CANブリッジは自作せず、チーム側の実装に乗る。

## 前提

- ROS2 Jazzy（Ubuntu 24.04）
- rosbridge インストール済み

```bash
sudo apt install ros-jazzy-rosbridge-suite
```

## セットアップ

```bash
cd ~/CITRobocon/Phone_Controller/ros2_ws
colcon build --packages-select robocon_bridge
source install/setup.bash
```

## 起動

```bash
ros2 launch robocon_bridge bringup.launch.py
```

rosbridge(ws://0.0.0.0:9090)・mock_node・cmd_vel_to_joy が同時に起動します。

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

# joy 変換確認（cmd_vel→joy が正しく変換されているか）
ros2 topic echo /joy
```

## リポジトリ構成

```
Phone_Controller/
├── web/robot-console.html              # スマホ HMI
└── ros2_ws/src/robocon_bridge/
    ├── robocon_bridge/
    │   ├── mock_node.py                # 擬似テレメトリ＋コマンド受信ログ
    │   └── cmd_vel_to_joy.py           # cmd_vel ⇄ joy 変換（チーム側 pscon_node への入口）
    └── launch/bringup.launch.py        # rosbridge + ノード一括起動
```

## トピック契約

| トピック | 型 | 向き | 内容 |
|---|---|---|---|
| `/cmd_vel` | `geometry_msgs/msg/Twist` | 端末→機体 | linear.x=前後, linear.y=横, angular.z=旋回。20Hz |
| `/robot/command` | `std_msgs/msg/String` | 端末→機体 | `align` / `home` / `deploy` / `reset` / `estop` / `release` |
| `/robot/telemetry` | `std_msgs/msg/String` | 機体→端末 | JSON ~10Hz。`{"vbat":23.8,"state":"MANUAL","wheels":[...]}` |
| `/joy` | `sensor_msgs/msg/Joy` | ROS2→チーム側 | `/cmd_vel` を変換して publish。pscon_node実装に合わせ axes[4]=linear.x(st_ry), axes[3]=linear.y(st_rx), axes[6]=angular.zの符号のみ(-1/0/1)。axes 7要素以上・buttons 8要素以上必須 |
