# CLAUDE.md — ロボコン手動機 操縦コンソール

## 概要
スマホをHMIにしてロボコン手動機を操縦・監視するシステム。
構成: **スマホ(roslibjs) ⇄ rosbridge ⇄ ROS2(Raspberry Pi 5) ⇄ /joy ⇄ [チーム側] pscon_node → can_node → SPI → クラシックCAN 500kbps → STM32(HAL)**。
半自動シーケンスはボタンでトリガーし、実体はSTM32上のローカル状態機械が閉ループで実行する。

## アーキテクチャ
- **本リポジトリの担当範囲は `/joy` publish まで。** それより先（pscon_node → can_node → SPI → クラシックCAN 500kbps → STM32）はチーム側の実装であり、本リポジトリの管轄外。CANブリッジは自作しない。
- **Raspberry Pi 5 (ROS2)**: コンパニオン計算機 兼 HMIゲートウェイ。`/cmd_vel` を `/joy` に変換して publish する。**ハードな制御ループには絶対に入れない。**
- **スマホ (Web HMI)**: roslibjsでrosbridgeに接続し、トピックに出し入れするだけ。`web/robot-console.html`。
- **抽象境界はROS2トピック**。スマホは `/cmd_vel` に publish する一publisherにすぎない。後から自律ノードや teleop_twist_joy が同じトピックに publish すれば、機体側を変えずに操縦元を差し替えられる。

## トピック契約（インターフェース。実装はこれに従う）
| トピック | 型 | 向き | 内容 |
|---|---|---|---|
| `/cmd_vel` | `geometry_msgs/msg/Twist` | 端末→機体 | linear.x=前後, linear.y=横移動, angular.z=旋回。**20Hzで送出（=デッドマンのハートビート）** |
| `/robot/command` | `std_msgs/msg/String` | 端末→機体 | 半自動トリガー。`align` / `home` / `deploy` / `reset` / `estop` / `release` |
| `/robot/telemetry` | `std_msgs/msg/String` | 機体→端末 | JSON文字列。~10Hz。例: `{"vbat":23.8,"state":"MANUAL","wheels":[{"angle":12.3,"ok":true}, ... ×4]}` |
| `/joy` | `sensor_msgs/msg/Joy` | ROS2→チーム側 | `/cmd_vel` を変換して publish。`pscon_node`（torobo2026_ros2_rp）の実装に合わせる: `axes[4]`=linear.x(st_ry), `axes[3]`=linear.y(st_rx), `axes[6]`=angular.zの符号のみ(-1/0/1, cross_bt)。`axes` 7要素以上・`buttons` 8要素以上が必須（`axes[6]`と`buttons[7]`にアクセスするため）。buttonsはpscon_node側で受信直後に全て0上書きされるため常にダミー(0)。 |

## 安全則（不変条件）
- **デッドマン**: STM32は200ms以内に有効な走行コマンドが来なければモーター停止。
- **物理E-stopは無線・スマホと独立に必ず残す。** 画面E-stopは補助。
- STM32がリアルタイム制御を所有。Pi/スマホは制御の時間critical pathに入らない。
- Wi-Fi切断 → コマンド途絶 → デッドマンで安全停止、という流れを壊さない。

## リポジトリ構成
```
Phone_Controller/
├─ CLAUDE.md
├─ web/robot-console.html              # スマホHMI（実装済み）
└─ ros2_ws/src/robocon_bridge/         # ROS2パッケージ (ament_python)
    ├─ robocon_bridge/
    │   ├─ mock_node.py                # ① 擬似テレメトリ＋cmd受信ログ（実機なしで端末検証）
    │   └─ cmd_vel_to_joy.py           # ② /cmd_vel → /joy 変換（チーム側 pscon_node への入口）
    └─ launch/bringup.launch.py        # rosbridge + ノード
```
STM32/CANまわり（pscon_node → can_node → SPI → クラシックCAN 500kbps → STM32）はチーム側の別リポジトリで管理。

## 環境
- ROS2 **Jazzy**（Ubuntu 24.04）。
- `sudo apt install ros-jazzy-rosbridge-suite`
- ビルド: `cd ros2_ws && colcon build && source install/setup.bash`

## 実行
```bash
ros2 launch robocon_bridge bringup.launch.py      # rosbridge(9090) + ノード起動
ss -tlnp | grep 9090                              # 待ち受け確認
# スマホ: 同一Wi-Fiで web/robot-console.html を開き ws://<pi-ip>:9090 を指定、デモOFF
```

## 作業順
1. **`robocon_bridge` パッケージを scaffold**（ament_python, console_scripts）。
2. **`mock_node.py`**: `/robot/telemetry` を契約通りのJSONで10Hz publish（vbat/state/wheelsを擬似生成）。`/cmd_vel` と `/robot/command` を subscribe してログ出力。
3. **`bringup.launch.py`**: rosbridge_websocket + mock_node を起動。READMEに実行手順。
4. → ここで **HMI↔ROS2の実通信ループ**が通る（スマホでスティックを動かすとPi側ログに出る／擬似テレメトリが画面に出る）。
5. **`cmd_vel_to_joy.py`**: `/cmd_vel`(Twist) を subscribe し `/joy`(sensor_msgs/msg/Joy) に変換して publish。`axes` 7要素以上・`buttons` 8要素以上必須。ここから先はチーム側 pscon_node の担当。

## 規約
- ノードはまずPythonで実装（rclpy）。パッケージ名 `robocon_bridge`。
- トピック名・型・JSONスキーマは上の契約を単一の真実とする。HMIの `CFG`（web/robot-console.html）と必ず一致させること。
