# ロボコン手動機 操縦コンソール

スマホ(roslibjs) ⇄ rosbridge ⇄ ROS2(Raspberry Pi 5) ⇄ /joy ⇄ [チーム側] pscon_node → can_node → SPI → クラシックCAN 500kbps → STM32(HAL)

本リポジトリの担当範囲は `/joy` publish まで。CANブリッジは自作せず、チーム側の実装に乗る。

## スマホコントローラ起動方法（実機／ラズパイ）

ラズパイに接続した状態で、以下を順番に実行する。

### プル

```bash
cd ~/torobo2026_ros2_rp
git pull

cd ~/Phone_Controller
git pull
```

### ビルド

ビルドキャッシュが古いまま反映されない事例があったため、**毎回クリーンビルドする**。

```bash
cd ~/torobo2026_ros2_rp
rm -rf build install log
colcon build

cd ~/Phone_Controller/ros2_ws
rm -rf build install log
colcon build
```

### アドレス確認

```bash
sudo netplan apply

ip -br addr show wlan0
```

→ アドレスが `10.152.79.144` ならOK

### ソース（新しいターミナルを開くたびに毎回必要）

```bash
source /opt/ros/jazzy/setup.bash
source ~/torobo2026_ros2_rp/install/setup.bash
source ~/Phone_Controller/ros2_ws/install/setup.bash
```

### ノード起動（ターミナルを分けて、それぞれ上記sourceをした上で）

```bash
# ターミナル1: rosbridge + cmd_vel_to_joy
ros2 launch robocon_bridge bringup.launch.py

# ターミナル2: /joy → pscon_data 変換
ros2 run pscon_node pscon_node

# ターミナル3: pscon_data → SPI/CAN 送信
ros2 run can_ps4_node can_ps4_node

# ターミナル4: スマホ用Webサーバー
cd ~/Phone_Controller/web && python3 -m http.server 8080
```

同じ役割のノードを重複起動しない（`pscon_node`と`ps4con_node`を同時に起動しない、`can_ps4_node`と`can_node`(can_manu_nodeパッケージ)を同時に起動しない）。実PS4パッドを使う場合は`pscon_node`の代わりに`torobo_launch_1`（`joy_node`+`ps4con_node`+`can_ps4_node`）を使う。

### スマホでリンクを開く

`http://10.152.79.144:8080/robot-console.html` を開く → 「接続」を押す → ●が緑になればOK

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

rosbridge(ws://0.0.0.0:9090)・mock_node・cmd_vel_to_joy・nav_node が同時に起動します。

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
ros2 topic pub --once /robot/command std_msgs/msg/String '{data: "intake"}'

# cmd_vel 送信テスト
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.5, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.1}}'

# joy 変換確認（cmd_vel→joy が正しく変換されているか）
ros2 topic echo /joy
```

### cmd_vel_to_joy の安全ゲート確認

`cmd_vel_to_joy` は `/cmd_vel`(軸) と `/robot/command`(ボタン) をマージして `/joy` を20Hz固定で publish する。
`ros2 topic echo /joy` を別ターミナルで実行しながら以下を確認する。

```bash
# ① ボタンパルス確認: axes を出し続けている状態で command を送ると、対応する buttons[index] が
#    約150ms(3フレーム分)だけ1になり、その後自動的に0へ戻ることを確認
#    （実PS4パッドのボタン配置×○△□L1 R1 L2 R2に対応。COMMAND_BUTTON_MAP参照）
ros2 topic pub -r 20 /cmd_vel geometry_msgs/msg/Twist \
  '{linear: {x: 0.5, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}' &
ros2 topic pub --once /robot/command std_msgs/msg/String '{data: "checkpoint"}'   # buttons[7](R2)が一瞬1になる
kill %1

# ② デッドマン確認: cmd_vel の送出を止めて200ms待つと、axes・buttonsが全0になることを確認
#    （上のバックグラウンド送出を止めた直後の /joy を echo で見る）

# ③ estop ラッチ確認: estop 送信後は cmd_vel を送り続けても axes/buttons が全0のままになり、
#    release を送るまで解除されないことを確認
ros2 topic pub --once /robot/command std_msgs/msg/String '{data: "estop"}'
ros2 topic pub --once /robot/command std_msgs/msg/String '{data: "release"}'
```

### nav_node の状態遷移確認（運動学は未実装、配線のみ）

```bash
ros2 topic echo /robot/nav_state   # 別ターミナルで実行しながら以下を確認

# ① goal受信でactiveになることを確認: nav_state が manual → auto に変わる
ros2 topic pub --once /robot/goal geometry_msgs/msg/PoseStamped \
  '{header: {frame_id: "map"}, pose: {position: {x: 1.0, y: 1.0, z: 0.0}}}'

# ② goal_cancel でmanualへ戻ることを確認
ros2 topic pub --once /robot/goal_cancel std_msgs/msg/Bool '{data: true}'

# ③ 到達判定確認: telemetry の pose を goal に近づけると自動でmanualへ戻る
#   （mock_node は固定のダミーpose推定を持たないため、実機 or 独自スクリプトで
#    /robot/telemetry に goalに近いpose入りJSONを流して確認する）
```

## リポジトリ構成

```
Phone_Controller/
├── web/robot-console.html              # スマホ HMI
├── firmware/CAN_COMMAND_SPEC.md        # STM32ファーム向けCANコマンド仕様書（本リポジトリはコード実装せず仕様のみ）
└── ros2_ws/src/robocon_bridge/
    ├── robocon_bridge/
    │   ├── mock_node.py                # 擬似テレメトリ＋コマンド受信ログ
    │   ├── cmd_vel_to_joy.py           # cmd_vel ⇄ joy 変換（チーム側 pscon_node への入口）
    │   └── nav_node.py                 # /robot/goal → go-to-point走行の状態遷移骨格（運動学は未実装）
    └── launch/bringup.launch.py        # rosbridge + ノード一括起動
```

## トピック契約

| トピック | 型 | 向き | 内容 |
|---|---|---|---|
| `/cmd_vel` | `geometry_msgs/msg/Twist` | 端末→機体 | linear.x=前後, linear.y=横, angular.z=旋回。20Hz。他フィールド(linear.z/angular.x/angular.y)は未使用(0固定) |
| `/robot/command` | `std_msgs/msg/String` | 端末→機体 | 全機構コマンドはエッジ（モーメンタリ）で統一。実PS4パッドのボタン配置（×○△□L1 R1 L2 R2）に1:1対応: `release_suction`(×,吸引切る/設置) / `intake`(〇,回収) / `arm_stow`(△,アーム収納) / `arm_start`(□,スタート初期移動) / `launch_to_intake`(L1,ベル直設置→回収) / `gate`(R1,城門設置高さ) / `descend_adjust`(L2,降下微調整) / `checkpoint`(R2,関所設置高さ) / `estop` / `release`。射出（ベル直の単独発射）は実PS4パイプライン側に未実装のため対象外（`firmware/CAN_COMMAND_SPEC.md`参照） |
| `/robot/telemetry` | `std_msgs/msg/String` | 機体→端末 | JSON ~10Hz。`{"vbat":23.8,"state":"MANUAL","wheels":[...]}` |
| `/joy` | `sensor_msgs/msg/Joy` | ROS2→チーム側 | `/cmd_vel`(軸)と`/robot/command`(ボタン)をマージして20Hz固定でpublish。実PS4パッドが`pscon_node`/`ps4con_node`に送るものと同じ形に合わせる: axes[4]=linear.x(st_ry), axes[3]=linear.y(st_rx), axes[6]=angular.zの符号のみ(-1/0/1)。buttons[0..7]は`/robot/command`のidに対応するindexが約150msだけ1になるエッジパルス（`release_suction`→0, `intake`→1, `arm_stow`→2, `arm_start`→3, `launch_to_intake`→4, `gate`→5, `descend_adjust`→6, `checkpoint`→7。`cmd_vel_to_joy.py`の`COMMAND_BUTTON_MAP`定数）。axesは8要素固定、buttonsは8要素固定。デッドマン(最後の`/cmd_vel`から200ms超で全0)と`estop`/`release`ラッチによる安全ゲートあり |
| `/robot/goal` | `geometry_msgs/msg/PoseStamped` | 端末→機体 | 自陣拡大マップのタップ地点(`frame_id='map'`, pose座標系)。受信で`nav_node`がgo-to-pointをアクティブ化（運動学は未実装） |
| `/robot/goal_cancel` | `std_msgs/msg/Bool` | 端末→機体 | `/robot/goal`のキャンセル。「移動キャンセル」ボタン、またはスティック入力再開時に送出 |
| `/robot/nav_state` | `std_msgs/msg/String` | 機体→端末 | `nav_node`の走行モード。`manual` / `auto` |
