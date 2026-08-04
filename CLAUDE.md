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
| `/cmd_vel` | `geometry_msgs/msg/Twist` | 端末→機体 | linear.x=前後, linear.y=横移動, angular.z=旋回。**20Hzで送出（=デッドマンのハートビート）**。加えて`linear.z`=アーム上下ジョグ, `angular.x`=アーム左右ジョグ（-1/0/+1、ホールドで動作・離すと停止）, `angular.y`=吸着トグルの現在状態（0/1、ONの間1を送り続ける）。いずれも機構手動操作用に未使用フィールドを流用。新規トピックは増やさずデッドマン/E-stopの安全ゲートに同乗させる（ハンドは吸着式のため仰角機構は無い） |
| `/robot/command` | `std_msgs/msg/String` | 端末→機体 | 半自動トリガー。全機構コマンドは「1ボタン=定型シーケンス起動」のエッジ（モーメンタリ、ホールド無し）で統一。`launch`(射出) / `intake`(回収) / `checkpoint`(関所配置) / `gate`(城門配置) / `estop` / `release` |
| `/robot/telemetry` | `std_msgs/msg/String` | 機体→端末 | JSON文字列。~10Hz。例: `{"vbat":23.8,"state":"MANUAL","pose":{"x":1.2,"y":0.4,"theta":1.57},"quality":0.92,"wheels":[{"angle":12.3,"ok":true}, ... ×4]}`。`pose`・`quality`は任意フィールド（下記注記参照）。`pose`は`nav_node`のgo-to-point到達判定にも使う。 |
| `/joy` | `sensor_msgs/msg/Joy` | ROS2→チーム側 | `/cmd_vel`(軸)と`/robot/command`(ボタン)をマージして20Hz固定で publish。`pscon_node`（torobo2026_ros2_rp）の実装に合わせる: `axes[4]`=linear.x(st_ry), `axes[3]`=linear.y(st_rx), `axes[6]`=angular.zの符号のみ(-1/0/1, cross_bt)。`buttons[0..3]`は`/robot/command`のid→index(`launch`→0, `intake`→1, `checkpoint`→2, `gate`→3。`cmd_vel_to_joy.py`の`COMMAND_BUTTON_MAP`定数)に対応するindexが受信後約150ms(3フレーム)だけ1になるエッジパルス。`buttons[4..7]`は`/cmd_vel.linear.z`/`angular.x`由来のホールド値（アーム上下左右の手動ジョグ。`4`=↑, `5`=↓, `6`=←, `7`=→。`cmd_vel_to_joy.py`の`BUTTON_ARM_UP`等の定数）で、ホールドしている間だけ1、離すと0。`buttons[8]`は`/cmd_vel.angular.y`由来のホールド値（吸着トグルの現在状態。`cmd_vel_to_joy.py`の`BUTTON_SUCTION`定数）で、ONの間1、OFFで0。`axes`は8要素固定、`buttons`は9要素固定。**安全ゲート**: 最後の`/cmd_vel`から200ms超のデッドマン、および`estop`/`release`によるラッチで、いずれの停止条件でもaxes・buttons(全要素)を全0にする。CAN側のビット対応は`firmware/CAN_COMMAND_SPEC.md`参照。 |
| `/robot/goal` | `geometry_msgs/msg/PoseStamped` | 端末→機体 | 移動コマンドB。フィールドマップの自陣拡大表示をタップした地点（`frame_id='map'`, pose座標系, m）。受信で`nav_node`がgo-to-point走行をアクティブ化する。運動学は未実装（`nav_node.py`のTODO）。 |
| `/robot/goal_cancel` | `std_msgs/msg/Bool` | 端末→機体 | `/robot/goal`によるgo-to-point走行のキャンセル。「移動キャンセル」ボタン、またはスティック入力再開時（手動優先）に送出。 |
| `/robot/nav_state` | `std_msgs/msg/String` | 機体→端末 | `nav_node`の走行モード。`manual` / `auto`。端末のモード表示に反映。 |

`/robot/telemetry` の任意フィールド:
- `pose`: `{x, y, theta}`。x, y は m、theta は rad。位置推定（自己位置）。省略可で、無くても他の表示（vbat/state/wheels等）に影響しない。**`web/robot-console.html` 実装済み**（テレメトリ上部の位置表示欄）。
- `quality`: 0〜1の数値。`pose` 推定の健全性（信頼度）。省略可。**`web/robot-console.html` は現状未消費**（契約定義のみで、表示・警告への反映はまだ実装されていない）。

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
├─ firmware/CAN_COMMAND_SPEC.md        # STM32ファーム向けCANコマンド仕様書（本リポジトリはコード実装せず仕様のみ）
└─ ros2_ws/src/robocon_bridge/         # ROS2パッケージ (ament_python)
    ├─ robocon_bridge/
    │   ├─ mock_node.py                # ① 擬似テレメトリ＋cmd受信ログ（実機なしで端末検証）
    │   ├─ cmd_vel_to_joy.py           # ② /cmd_vel → /joy 変換（チーム側 pscon_node への入口）
    │   └─ nav_node.py                 # /robot/goal → go-to-point走行の状態遷移骨格（運動学は未実装）
    └─ launch/bringup.launch.py        # rosbridge + ノード
```
STM32/CANまわり（pscon_node → can_node → SPI → クラシックCAN 500kbps → STM32）はチーム側の別リポジトリで管理。CANペイロードの仕様は`firmware/CAN_COMMAND_SPEC.md`に記載。

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
