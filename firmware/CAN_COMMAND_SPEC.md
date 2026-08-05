# STM32(HAL) CAN コマンド仕様書

対象: STM32 側ファーム実装チーム。本ドキュメントは**現状の実装の記録**であり、STM32ファーム自体（`torobo2026_hal`）・Pi側ROS2ノード（`torobo2026_ros2_rp`）のコードはこのリポジトリの担当範囲外。

経路: スマホ(HMI) → rosbridge → ROS2 `/robot/command` → `cmd_vel_to_joy`(`/joy`) → `ps4con_node`(`pscon_data`) → `can_ps4_node` → SPI → クラシックCAN 500kbps → **STM32(HAL)**

> 本コントローラは実PS4パッド用パイプライン（`ps4con_node`/`can_ps4_node`、`torobo2026_ros2_rp`）にそのまま相乗りする設計。`ps4con_node`/`can_ps4_node`は変更せず、スマホ側が実PS4パッドと同じ形の`/joy`を出力することで、これらのノードが解釈・送信するCANペイロードも実PS4パッド操作時と完全に同一になる。

## 1. 足回り（`MOTORDRIVER4_RUN` 宛、3byte）

| byte | 内容 |
|---|---|
| `can_send_data[0]` | モード種別。`0b11110000`=通常（並進）、`0b11110001`=旋回中 |
| `can_send_data[1]` | 通常時: y値（前後、st_ry由来）／旋回時: 旋回方向ビット(`bit0`=左, `bit1`=右) |
| `can_send_data[2]` | 通常時のみ: x値（左右、st_rx由来） |

## 2. アーム（`MOTORDRIVER4_ARM` 宛、2byte、送信→完了返信のハンドシェイク方式）

`can_ps4_node.cpp`はPS4パッドの8ボタン（×○△□L1 R1 L2 R2）それぞれに1つの定型動作コードを割り当てる。**ビット単位ではなく、1回のボタン押下につき1つの数値コードを送る方式**。

| ボタン | `/robot/command` id | コード(`can_send_data[1]`) | 内容 |
|---|---|---|---|
| □ | `arm_start` | `0x01` | スタート初期移動 |
| 〇 | `intake` | `0x02` | 回収 |
| L2 | `descend_adjust` | `0x03` | 降下微調整 |
| L1 | `launch_to_intake` | `0x04` | ベル直設置→回収 |
| × | `release_suction` | `0x05` | 吸引切る(設置) |
| R2 | `checkpoint` | `0x06` | 関所設置高さ |
| R1 | `gate` | `0x07` | 城門設置高さ |
| △ | `arm_stow` | `0x08` | アーム収納 |

- `can_send_data[0]`は常に`0b11110000`（アーム宛の識別バイト）。
- **送信は複数ボタン同時押しでも1つだけ**（`can_ps4_node.cpp`の判定は`if / else if`の優先順位方式で、優先度は上表の上から順）。
- **ack待ちハンドシェイク**: 1回送信すると`arm_send_ok`フラグが立ち、STM32からの完了返信（`can_read_data[0]==0b00000011 && can_read_data[1]==0b00001111`）を受信するまで次のアーム送信は行わない。STM32側はアーム動作完了時にこの2byteを返す実装になっている前提。

## 3. 射出（ベル直）— **未実装**

- CAN ID `MOTORDRIVER4_LONCH`（"ベル直モタドラ制御"）は定義済みだが、`can_ps4_node.cpp`には送信コードが無く（`// -------------ベル直---------------` というコメントのみ）、Pi側から射出コマンドがCANバスに送出されることは現状無い。
- STM32側（`torobo2026_hal/f446re_motor_BLlaunch/Core/Src/main.c`）も、射出関数`BL_launch()`はUART経由のPCコマンド('2')でのみ呼ばれており、CAN受信からのトリガーは未実装。
- **本コントローラも同じ理由でスマホからの射出操作は対象外**（実PS4パッドでもできないため）。実装するにはPi側(`can_ps4_node.cpp`)とSTM32側(`main.c`)の両方に受信/送信処理を追加する必要がある。

## 4. `pscon_data` の構造（`ps4con_node.cpp`）

`ps4con_node`は`/joy`を購読し、以下の形で`pscon_data`（`std_msgs/msg/UInt32`）をpublishする。

```
pscon_data (uint32, LSB→MSB)
┌─────────────┬─────────────┬───────────────┬─────────────┐
│   byte3     │   byte2     │     byte1      │   byte0     │
│ st_rx_data  │ st_ry_data  │ cross_bt(bit0-1)│  buttons    │
│ (bits24-31) │ (bits16-23) │ (bits8-9)      │ (bits0-7)   │
└─────────────┴─────────────┴───────────────┴─────────────┘
```
- `byte0`(bits0-7) = `/joy.buttons[0..7]`（本書2節のアームボタン。エッジパルスとして観測される）。
- `bit8/9`(byte1の下位2bit) = `cross_bt`（`axes[6]`由来の旋回方向、-1→bit8, +1→bit9）。**機構コマンドではなく走行系の参考情報**。
- `byte2`/`byte3` = `st_ry`/`st_rx`（走行スティックの生値）。
- `can_ps4_node`はこの`pscon_data`を受け取り、本書1・2節の判定ロジックでCANフレームを組み立てて送信する。

## 5. 変更履歴

- 本書 初版: `/robot/command` の id を実機経路（`launch`/`intake`/`checkpoint`/`gate`）に合わせた際に作成。当時はビット単位の仮想プロトコル（bit0-3=定型シーケンス、bit4-7=アーム手動ジョグ、吸着トグル等）を想定していたが、これは実装されなかった。
- **全面改訂**: Pi側で実際に稼働している`ps4con_node`/`can_ps4_node`（`torobo2026_ros2_rp`、keiji実装）の実プロトコルを調査し、本書をその内容に合わせて書き直した。実プロトコルは「ビットごとに機構を割り当てる」方式ではなく「PS4パッドの8ボタンそれぞれに1つの動作コードを割り当て、送信→完了返信のハンドシェイクで多重発射を防ぐ」方式。手動ジョグ・吸着トグルは実プロトコルに存在しないため本書から削除。射出（ベル直）は実プロトコル・STM32ファーム双方で未実装のままのため引き続き対象外と明記。
