# STM32(HAL) CAN コマンド仕様書

対象: STM32 側ファーム実装チーム。本ドキュメントは**現状の実装の記録**であり、STM32ファーム自体（`torobo2026_hal`）・Pi側ROS2ノード（`torobo2026_ros2_rp`）のコードはこのリポジトリの担当範囲外。

経路: スマホ(HMI) → rosbridge → ROS2 `/robot/command` → `cmd_vel_to_joy`(`/joy`) → `pscon_node`(`pscon_data`) → `can_node` → SPI → クラシックCAN 500kbps → **STM32(HAL)**

> 本コントローラは実パッド用パイプライン（`pscon_node`/`can_node`、`torobo2026_ros2_rp`）にそのまま相乗りする設計。`pscon_node`/`can_node`は変更せず、スマホ側が実パッドと同じ形の`/joy`を出力することで、これらのノードが解釈・送信するCANペイロードも実パッド操作時と完全に同一になる。
>
> **注意**: 同リポジトリには`ps4con_node`/`can_ps4_node`という似た名前の別ノード一式も存在する。これは**実PS4パッドを直接挿した場合の非常用バックアップ経路**として意図的に残されているもの（型は`ps4con_node`→`can_ps4_node`とも`UInt32`で一致しており動く）。基本の操縦はスマホ（`pscon_node`/`can_node`経由）で行い、ps4con側は「万が一に備えて」の予備。両者は同じ`/joy`を購読するが別トピック実体としてそれぞれ`pscon_data`(UInt32/UInt64)を送るため、**同時に2系統動かすとボタンの意味が食い違う（§2参照）ので、実際に使うのはどちらか一方**。本書は基本のスマホ経路（`pscon_node`/`can_node`）を主として書き、ps4con側は§2-3に別記する（§5参照）。

## 1. 足回り（`MOTORDRIVER4_RUN` 宛、3byte）

| byte | 内容 |
|---|---|
| `can_send_data[0]` | モード種別。`0b11110000`=通常（並進）、`0b11110001`=旋回中、`0b00110001`=Lidar位置補正 |
| `can_send_data[1]` | 通常時: y値（前後、st_ry由来）／旋回時: 旋回方向ビット(`cross_data`の下位2bit) |
| `can_send_data[2]` | 通常時のみ: x値（左右、st_rx由来） |

- 旋回中(`cross_data&0b00000011 != 0`)は最優先。次に、走行スティックの絶対値が閾値(20)を超えていれば通常並進、それ以外は停止命令(`0b00110000`)。
- **Lidar位置補正**: `/circle_center`(`geometry_msgs/msg/PointStamped`)を受信するたびに`0b00110001`を送信する経路だが、現状Lidarの精度が低いため常時自動発火ではなく**RT(`bt_data`のbit7)を押している間だけ**発火するようゲートされている（`lider_callback()`冒頭で`bt_data`のbit7を確認し、立っていなければ即return）。本コントローラのUI側は`lidar_correct` idをホールド中`BUTTON_PULSE_S`(0.15s)より短い間隔で連打し、`bt_data`のbit7を継続的に1に保つことでホールド操作を実現する。

## 2. アーム/ベル直（送信→完了返信のハンドシェイク方式）

`can_node.cpp`はXbox系パッドの8ボタン（A B X Y LB RB LT、`bt_data`のbit0-7）と十字キー4方向（`cross_data`のbit4-7）それぞれに1つの定型動作コードを割り当てる。**ビット単位ではなく、1回の押下につき1つの数値コードを送る方式**。優先順位は`if / else if`の判定順（下表の上から順）。

### 2-1. アーム（`MOTORDRIVER4_ARM` 宛、2byte）

| ボタン | `/robot/command` id | コード(`can_send_data[1]`) | 内容 |
|---|---|---|---|
| X | `arm_start` | `0x01` | 初期（リセット） |
| B | `intake` | `0x02` | 回収 |
| LT | `descend_adjust` | `0x03` | 降下微調整 |
| 十字キー上 | `dpad_up` | `0x04` | ベル直設置 |
| A | `release_suction` | `0x05` | 吸引切る(設置)（＝「放す」） |
| 十字キー下 | `dpad_down` | `0x06` | 関所設置高さ |
| 十字キー左 | `dpad_left` | `0x07` | 城門設置高さ |
| 十字キー右 | `dpad_right` | `0x08` | 2個めボール置き場 |
| LB | `arm_force_stop` | `0x09` | アーム移動強制ストップ |

- `can_send_data[0]`は常に`0b11110000`（アーム宛の識別バイト）。
- **ack待ちハンドシェイク**: A/B/X/LT/LBのボタン群は1回送信すると`arm_send_ok`フラグが立ち、STM32からの完了返信（`can_read_data[0]==0b00000011`または`0b00001100`、かつ`can_read_data[1]==0b00001111`）を受信するまで次のアーム送信は行わない。十字キー4方向も同じ`arm_send_ok`ゲートの対象。

### 2-2. ベル直（`MOTORDRIVER4_LONCH` 宛、2byte）

| ボタン | `/robot/command` id | コード(`can_send_data[1]`) | 内容 |
|---|---|---|---|
| Y | `launch` | `0x01` | 射出 |
| RB | `manual_adjust` | `0x02` | 手動位置調整（ベル直位置調整） |

- `can_send_data[0]`は常に`0b11110000`。
- こちらは2-1のack待ちハンドシェイク（`arm_send_ok`）の対象外（送信後すぐ次を送れる）。

### 2-3. バックアップ経路（`can_ps4_node.cpp`、実PS4パッド直挿し時）

`can_ps4_node.cpp`は実PS4パッドのボタン配置（×○△□L1 R1 L2 R2）で、`MOTORDRIVER4_ARM`宛にコードを送る（ack待ちハンドシェイクは共通の仕組み）。**2-1と同じコード値は概ね同じ意味**（STM32側は送信元ノードを区別せず同じコードとして解釈するため）だが、`0x04`と`0x08`の意味が2-1と異なる点、`0x09`(アーム移動強制ストップ)がこちら側には無い点に注意。射出・手動位置調整（2-2相当）はこちら側には実装が無い。

| ボタン | コード(`can_send_data[1]`) | 内容 |
|---|---|---|
| □ | `0x01` | スタート初期移動 |
| 〇 | `0x02` | 回収 |
| L2 | `0x03` | 降下微調整 |
| L1 | `0x04` | ベル直設置→回収（2-1の`0x04`＝ベル直設置のみ、とは意味が異なる） |
| × | `0x05` | 吸引切る(設置) |
| R2 | `0x06` | 関所設置高さ |
| R1 | `0x07` | 城門設置高さ |
| △ | `0x08` | アーム収納（2-1の`0x08`＝2個めボール置き場、とは意味が異なる） |

## 3. `pscon_data` の構造（`pscon_node.cpp`、基本経路）

`pscon_node`は`/joy`を購読し、以下の形で`pscon_data`（`std_msgs/msg/UInt64`）をpublishする。

```
pscon_data (uint64, LSB→MSB)
bit 0-7   : buttons（本書2節のA B X Y LB RB LTボタン。エッジパルスとして観測される）
bit 8     : turn_st == -1 (旋回、左)
bit 9     : turn_st == +1 (旋回、右)
bit 12    : cross_bt[3] (十字キー下 dpad_down)
bit 13    : cross_bt[2] (十字キー左 dpad_left)
bit 14    : cross_bt[1] (十字キー右 dpad_right)
bit 15    : cross_bt[0] (十字キー上 dpad_up)
bit 32-39 : sequence_data（`/sequence`由来。本書の対象外）
```

- `can_node`側は`bt_data = ps_data & 0xFF`（bit0-7そのまま）、`cross_data = (ps_data>>8) & 0xFF`（bit8-15を1byteとして読む。結果、十字キーは`cross_data`のbit4-7に現れる）として受け取る。

## 4. 射出（ベル直）— 実装済み

旧版では「射出は未実装」としていたが、`can_node.cpp`にはYボタン(`launch`)経由で`MOTORDRIVER4_LONCH`へ`0x01`を送る処理が実装済み。本コントローラ側でも`/robot/command`の`launch` idとしてボタン化済み（§5参照）。STM32側の受信実装（`torobo2026_hal`）は本リポジトリの担当範囲外のため未確認。

## 5. 変更履歴

- 初版: `/robot/command` の id を実機経路（`launch`/`intake`/`checkpoint`/`gate`）に合わせた際に作成。当時想定していたビット単位の仮想プロトコルは実装されなかった。
- 改訂1: 当時稼働していた`ps4con_node`/`can_ps4_node`の実プロトコルに合わせて全面改訂。「PS4パッドの8ボタンそれぞれに1つの動作コードを割り当て、送信→完了返信のハンドシェイクで多重発射を防ぐ」方式と記載。射出・手動ジョグは実プロトコル・STM32ファーム双方で未実装として対象外と明記。
- **改訂2（本書）**: 基本の操縦経路は`pscon_node`/`can_node`（Xbox系パッド配置、A B X Y LB RB LT）であることが判明したため、本書をそちらの実装内容を主として書き直した。射出(`launch`,Y)・手動位置調整(`manual_adjust`,RB)は実装済みと判明したため実装済みに変更。旧`arm_stow`(△/アーム収納)・`gate`(R1/城門設置高さ)・`launch_to_intake`(L1/ベル直設置→回収)・`checkpoint`(R2/関所設置高さ)のidは`can_node.cpp`側の実際の割り当てと一致しなくなっていたため廃止し、`launch`/`arm_force_stop`/`manual_adjust`/十字キー4方向(`dpad_up`/`dpad_right`/`dpad_left`/`dpad_down`)に置き換えた。当初「`ps4con_node`/`can_ps4_node`は型不一致で機能していない」と誤って記載したが、これは誤り（`ps4con_node`→`can_ps4_node`は`UInt32`同士で型は一致しており動く）。実PS4パッド直挿し時の意図的なバックアップ経路として2-3に別記した。
- **改訂3**: Lidar位置補正（§1）をRT(`lidar_correct`)によるホールド式ゲートに変更。現状Lidarの精度が低く常時自動発火では困るため、押している間だけ有効にする仕様に修正した。あわせて`torobo2026_ros2_rp/can_node.hpp`の`lider_callback`宣言が誤って関数定義（`{`)になっており、以降のprivateメンバ変数群がその関数本体に取り込まれてしまっていた不具合（おそらくコメントアウト解除時の記述ミス）を修正し、`lider_callback`の引数型もヘッダ・実装とも`geometry_msgs::msg::PointStamped::SharedPtr`に統一した（従来は`std_msgs::msg::UInt64::SharedPtr`のままで`msg->point.x`にアクセスしており、型が合っていなかった）。
