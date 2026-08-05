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
- **`cmd_vel_to_joy.py` は実PS4パッド用パイプライン（`ps4con_node`/`can_ps4_node`、torobo2026_ros2_rp）にそのまま相乗りする設計**。それらのノードは変更せず、`/joy` の中身（axes/buttons）を実PS4パッドが送るものと同じ形に合わせて出力することで、スマホからの操作を実PS4パッドの操作と区別なく扱わせる。

## トピック契約（インターフェース。実装はこれに従う）
| トピック | 型 | 向き | 内容 |
|---|---|---|---|
| `/cmd_vel` | `geometry_msgs/msg/Twist` | 端末→機体 | linear.x=前後, linear.y=横移動, angular.z=旋回。**20Hzで送出（=デッドマンのハートビート）**。他のフィールド（linear.z/angular.x/angular.y）は未使用（0固定）。 |
| `/robot/command` | `std_msgs/msg/String` | 端末→機体 | 半自動トリガー。全機構コマンドは「1ボタン=定型アーム動作起動」のエッジ（モーメンタリ、ホールド無し）で統一。実PS4パッドのボタン配置（×○△□L1 R1 L2 R2）に1:1対応: `release_suction`(×,吸引切る/設置) / `intake`(〇,回収) / `arm_stow`(△,アーム収納) / `arm_start`(□,スタート初期移動) / `launch_to_intake`(L1,ベル直設置→回収) / `gate`(R1,城門設置高さ) / `descend_adjust`(L2,降下微調整) / `checkpoint`(R2,関所設置高さ) / `estop` / `release`。**射出（ベル直の単独発射）は実PS4パイプライン側（`can_ps4_node.cpp`）に未実装のため、本コントローラでも未対応**（`firmware/CAN_COMMAND_SPEC.md`参照）。 |
| `/robot/telemetry` | `std_msgs/msg/String` | 機体→端末 | JSON文字列。~10Hz。例: `{"vbat":23.8,"state":"MANUAL","pose":{"x":1.2,"y":0.4,"theta":1.57},"quality":0.92,"wheels":[{"angle":12.3,"ok":true}, ... ×4]}`。`pose`・`quality`は任意フィールド（下記注記参照）。`pose`は`nav_node`のgo-to-point到達判定にも使う。 |
| `/joy` | `sensor_msgs/msg/Joy` | ROS2→チーム側 | `/cmd_vel`(軸)と`/robot/command`(ボタン)をマージして20Hz固定で publish。**実PS4パッドが `ps4con_node`(`torobo2026_ros2_rp`)に送るものと同じ形**に合わせる: `axes[4]`=linear.x(st_ry), `axes[3]`=linear.y(st_rx), `axes[6]`=angular.zの符号のみ(-1/0/1, cross_bt)。`buttons[0..7]`は`/robot/command`のid→index(`cmd_vel_to_joy.py`の`COMMAND_BUTTON_MAP`定数。`release_suction`→0, `intake`→1, `arm_stow`→2, `arm_start`→3, `launch_to_intake`→4, `gate`→5, `descend_adjust`→6, `checkpoint`→7)に対応するindexが受信後約150ms(3フレーム)だけ1になるエッジパルス。`axes`は8要素固定、`buttons`は8要素固定。**安全ゲート**: 最後の`/cmd_vel`から200ms超のデッドマン、および`estop`/`release`によるラッチで、いずれの停止条件でもaxes・buttons(全要素)を全0にする。CAN側の実際の解釈は`firmware/CAN_COMMAND_SPEC.md`参照。 |
| `/robot/goal` | `geometry_msgs/msg/PoseStamped` | 端末→機体 | 移動コマンドB。フィールドマップの自陣拡大表示をタップした地点（`frame_id='map'`, pose座標系, m）。受信で`nav_node`がgo-to-point走行をアクティブ化する。運動学は未実装（`nav_node.py`のTODO）。 |
| `/robot/goal_cancel` | `std_msgs/msg/Bool` | 端末→機体 | `/robot/goal`によるgo-to-point走行のキャンセル。「移動キャンセル」ボタン、またはスティック入力再開時（手動優先）に送出。 |
| `/robot/nav_state` | `std_msgs/msg/String` | 機体→端末 | `nav_node`の走行モード。`manual` / `auto`。端末のモード表示に反映。 |

`/robot/telemetry` の任意フィールド:
- `pose`: `{x, y, theta}`。x, y は m、theta は rad。位置推定（自己位置）。省略可で、無くても他の表示（vbat/state/wheels等）に影響しない。**`web/robot-console.html` 実装済み**（テレメトリ上部の位置表示欄）。
- `quality`: 0〜1の数値。`pose` 推定の健全性（信頼度）。省略可。**`web/robot-console.html` は現状未消費**（契約定義のみで、表示・警告への反映はまだ実装されていない）。

## 安全則（不変条件）
- **デッドマン**: STM32は200ms以内に有効な走行コマンドが来なければモーター停止。
- **物理E-stopは無線・スマホと独立に必ず残す。** スマホ画面には非常停止ボタンを設けない（唯一の安全停止手段は機体側の物理E-stopとし、画面操作に依存しない）。
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
