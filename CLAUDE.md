# CLAUDE.md — ロボコン手動機 操縦コンソール

## 概要
スマホをHMIにしてロボコン手動機を操縦・監視するシステム。
構成: **スマホ(roslibjs) ⇄ rosbridge ⇄ ROS2(Raspberry Pi 5) ⇄ CAN-FD ⇄ STM32(HAL)**。
半自動シーケンスはボタンでトリガーし、実体はSTM32上のローカル状態機械が閉ループで実行する。

## アーキテクチャ
- **STM32 F446RE (HAL)**: ハードリアルタイム制御の唯一の担当。CAN-FDバックボーン(MCP2517FD)で各輪 F303K8×4 (AS5600) を制御。半自動シーケンスもここで回す。
- **Raspberry Pi 5 (ROS2)**: コンパニオン計算機 兼 HMIゲートウェイ。CAN ⇄ ROS2トピックを中継する。**ハードな制御ループには絶対に入れない。**
- **スマホ (Web HMI)**: roslibjsでrosbridgeに接続し、トピックに出し入れするだけ。`web/robot-console.html`。
- **抽象境界はROS2トピック**。スマホは `/cmd_vel` に publish する一publisherにすぎない。後から自律ノードや teleop_twist_joy が同じトピックに publish すれば、機体側を変えずに操縦元を差し替えられる。

## トピック契約（インターフェース。実装はこれに従う）
| トピック | 型 | 向き | 内容 |
|---|---|---|---|
| `/cmd_vel` | `geometry_msgs/msg/Twist` | 端末→機体 | linear.x=前後, linear.y=横移動, angular.z=旋回。**20Hzで送出（=デッドマンのハートビート）** |
| `/robot/command` | `std_msgs/msg/String` | 端末→機体 | 半自動トリガー。`align` / `home` / `deploy` / `reset` / `estop` / `release` |
| `/robot/telemetry` | `std_msgs/msg/String` | 機体→端末 | JSON文字列。~10Hz。例: `{"vbat":23.8,"state":"MANUAL","wheels":[{"angle":12.3,"ok":true}, ... ×4]}` |

## 安全則（不変条件）
- **デッドマン**: STM32は200ms以内に有効な走行コマンドが来なければモーター停止。
- **物理E-stopは無線・スマホと独立に必ず残す。** 画面E-stopは補助。
- STM32がリアルタイム制御を所有。Pi/スマホは制御の時間critical pathに入らない。
- Wi-Fi切断 → コマンド途絶 → デッドマンで安全停止、という流れを壊さない。

## リポジトリ構成
```
robocon-console/
├─ CLAUDE.md
├─ web/robot-console.html              # スマホHMI（実装済み）
├─ ros2_ws/src/robocon_bridge/         # ROS2パッケージ (ament_python)
│   ├─ robocon_bridge/
│   │   ├─ mock_node.py                # ① 擬似テレメトリ＋cmd受信ログ（実機なしで端末検証）
│   │   └─ can_bridge_node.py          # ② CAN ⇄ トピック中継（CAN素性確定後）
│   └─ launch/bringup.launch.py        # rosbridge + ノード
└─ firmware/                           # STM32 HAL側（後段）
```

## 環境
- ROS2 **Humble**（Pi上はUbuntu 22.04 か Docker）。dev用にノートPCにも同じ環境。
- `sudo apt install ros-humble-rosbridge-suite`
- ビルド: `cd ros2_ws && colcon build && source install/setup.bash`

## 実行
```bash
ros2 launch robocon_bridge bringup.launch.py      # rosbridge(9090) + ノード起動
ss -tlnp | grep 9090                              # 待ち受け確認
# スマホ: 同一Wi-Fiで web/robot-console.html を開き ws://<pi-ip>:9090 を指定、デモOFF
```

## 作業順（上から実装。トピック契約より上はCAN確認を待たずに並行可）
1. **`robocon_bridge` パッケージを scaffold**（ament_python, console_scripts）。
2. **`mock_node.py`**: `/robot/telemetry` を契約通りのJSONで10Hz publish（vbat/state/wheelsを擬似生成）。`/cmd_vel` と `/robot/command` を subscribe してログ出力。
3. **`bringup.launch.py`**: rosbridge_websocket + mock_node を起動。READMEに実行手順。
4. → ここで **HMI↔ROS2の実通信ループ**が通る（スマホでスティックを動かすとPi側ログに出る／擬似テレメトリが画面に出る）。
5. （CAN素性確定後）**`can_bridge_node.py`**: `/cmd_vel`→コマンドフレーム、テレメトリフレーム→`/robot/telemetry`。生搬送は `ros2_socketcan`（SocketCANの場合）を土台にする。
6. （後段）**firmware/**: STM32 HAL側のCAN受信・デッドマン・テレメトリ送信、半自動状態機械。

## 未確定事項（保留中）
- **CANの素性**: Pi側CAN基板（MCP2517FD×2 + MCP2562、割り込み未結線＝ポーリング運用）が、`candump can0` の通る **SocketCANネットデバイス**として見えているか、自前のユーザ空間SPIドライバか。
  - SocketCANなら → `ros2_socketcan` をそのまま使う。
  - 自前SPIなら → そのドライバを叩くROS2ノードを書く（②の実装が変わる）。
- 水晶は40MHz（`oscillator=40000000`）。CAN-FDのdbitrateはMCP2562のため控えめに。

## 規約
- ノードはまずPythonで実装（rclpy）。パッケージ名 `robocon_bridge`。
- トピック名・型・JSONスキーマは上の契約を単一の真実とする。HMIの `CFG`（web/robot-console.html）と必ず一致させること。
