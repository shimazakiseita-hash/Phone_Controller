# tudarobo スマホコントローラ 実機確認手順

スマホの操作が `/cmd_vel` → `/joy` → `/pscon_data` まで正しく届くかを、ラズパイ実機で確認する。
この手順では `can_node` が CAN を送信できるところまでを確認する。機体が実際に動くかはチーム側 HAL の修正後。

## 0. 用意するもの
- tudarobo のラズパイ5（電源・SSHできるPC）
- iPhone ＋ ゲームパッド（iPhone に Bluetooth でペアリング済み）
- iPhone とラズパイが同じ Wi‑Fi に入れること
- 機体にモータ電源を入れる場合は、**タイヤを浮かせる**こと・物理非常停止がすぐ押せること
- CAN送信の確認（8章）では、STM32 基板を少なくとも1枚 CAN につないで電源を入れること。走行基板の現ファームは電源投入でモータが回るので、**タイヤを浮かせる**こと。

## 1. 更新とビルド（ラズパイ）
自動起動を有効にしている場合は、ビルド前に `sudo systemctl stop tudarobo` する。
```bash
cd ~/tudarbo2026_kitakamisanti_ros2 && git fetch && git switch fix/can-send-and-stale-stop && git pull
rm -rf build install log && source /opt/ros/jazzy/setup.bash && colcon build

cd ~/Phone_Controller && git pull
cd ros2_ws && rm -rf build install log && colcon build
```
PR #1 がマージされた後は `git switch main && git pull`。
自動起動を有効にしている場合は、ビルド後に `sudo systemctl start tudarobo` で起動し直す。
- [ ] 両方のビルドが成功した

## 2. IPアドレス確認
```bash
ip -br addr show wlan0
```
- [ ] IPアドレスを控えた（以下 `<PiのIP>`）

## 3. 起動（ラズパイ・ターミナル1）
自動起動を有効にしている場合は手動 launch の代わりに、`systemctl status tudarobo` と `journalctl -u tudarobo -f` で状態・ログを確認する。

```bash
source /opt/ros/jazzy/setup.bash
source ~/tudarbo2026_kitakamisanti_ros2/install/setup.bash
source ~/Phone_Controller/ros2_ws/install/setup.bash
ros2 launch robocon_bridge tudarobo.launch.py
```
ログに次が出ること:
- [ ] `cmd_vel_to_joy (axes+buttons merge) started`
- [ ] `pscon node start`
- [ ] `Can_manu node start` と `spi done` の後、`set_start` → `done1`〜`done3` → `set_done` まで出る

補足:
- `SPI open failed` → SPI が無効。`/boot/firmware/config.txt` に `dtparam=spi=on` を入れて再起動。
- `set_start` のあと 0/1 の行が流れ続ける → CANボード(MCP2517FD)が未接続/未応答。SPI配線を確認。`/pscon_data` までの確認（6章まで）はこの状態でもできる。

別ターミナル（以下も同じく3行の source をしてから）:
```bash
ros2 node list
```
- [ ] `/rosbridge_websocket` `/cmd_vel_to_joy` `/pscon_node` `/can_manu_node` がある

## 4. iPhone で接続
1. Safari で `http://<PiのIP>:8080/tudarobo-console.html` を開く
2. 接続先を `ws://<PiのIP>:9090` にして「接続」
3. ゲームパッドのボタンを1回押す（iPhone はボタンを押すまでパッドを認識しない）

- [ ] 接続欄の ● が緑、`20 Hz` 前後
- [ ] 接続欄に「画面ロック防止: 有効」と出る
- [ ] ゲームパッド欄が「● 接続中」
- [ ] スティックを倒すと「前後 / 左右 / 旋回」の数値が動く

## 5. 送出レートの確認（ラズパイ）
```bash
ros2 topic hz /cmd_vel
```
- [ ] average rate が約 20

## 6. `/pscon_data` で操作の中身を確認（ラズパイ）
`/pscon_data` は64bitに詰めた値なので、読みやすく表示する:
```bash
ros2 topic echo /pscon_data --field data | python3 -u -c '
import sys
s8=lambda v: v-256 if v>127 else v
p=None
for l in sys.stdin:
    l=l.strip()
    if not l.isdigit(): continue
    d=int(l)
    if d==p: continue
    p=d
    turn="右" if d>>8&1 else "左" if d>>9&1 else "-"
    print(f"前後={s8(d>>16&0xFF):4d} 左右={s8(d>>24&0xFF):4d} 旋回={turn} RT(高速旋回)={d>>7&1}")
'
```
（同じ値は表示を省いている。左右は左に倒すと負の値になる）

| # | 画面の設定 | 操作 | 期待する表示 | 結果 |
|---|---|---|---|---|
| 1 | 高速・通常 | 左スティックを前に倒し切る | 前後 ≈ 100 | [ ] |
| 2 | 高速・通常 | 左スティックを後ろに倒し切る | 前後 ≈ -100 | [ ] |
| 3 | 高速・通常 | 左スティックを左に倒し切る | 左右 ≈ -100 | [ ] |
| 4 | 高速・通常 | 左スティックを右に倒し切る | 左右 ≈ 100 | [ ] |
| 5 | 高速・通常 | 右スティックを右に倒し切る | 旋回=右、RT=1 | [ ] |
| 6 | 高速・通常 | 右スティックを左に倒し切る | 旋回=左、RT=1 | [ ] |
| 7 | 高速・通常 | 右スティックを少しだけ右へ | 旋回=右、RT=0 | [ ] |
| 8 | 低速・通常 | 右スティックを右に倒し切る | 旋回=右、RT=0 | [ ] |
| 9 | 中速・通常 | 右スティックを右に倒し切る | 旋回=右、RT=0 | [ ] |
| 10 | 中速・通常 | 左スティックを前に倒し切る | 前後 ≈ 70 | [ ] |
| 11 | 低速・通常 | 左スティックを前に倒し切る | 前後 ≈ 40 | [ ] |
| 12 | 高速・逆転 | 左スティックを前に倒し切る | 前後 ≈ -100 | [ ] |
| 13 | 高速・逆転 | 右スティックを右に倒し切る | 旋回=右（逆転しない） | [ ] |
| 14 | どれでも | スティックを全部離す | 前後=0 左右=0 旋回=- RT=0 | [ ] |

※ `can_node` は前後・左右の絶対値が20以下を「停止」とみなす。

## 7. 安全確認（止まるべきときに止まるか）
ラズパイで `ros2 topic echo /joy --field axes` を出しながら、左スティックを前に倒したまま次を行う:

| # | 操作 | 期待 | 結果 |
|---|---|---|---|
| 1 | 画面の「切断」を押す | 0.2秒以内に axes が全部 0 | [ ] |
| 2 | 再接続後、iPhone の Wi‑Fi を切る | 0.2秒以内に axes が全部 0 | [ ] |
| 3 | 再接続後、Safari を閉じる／ホームに戻る | axes が全部 0 | [ ] |
| 4 | 再接続後、ゲームパッドの電源を切る | 画面が「未検出」、axes が全部 0 | [ ] |
| 5 | Wi‑Fi を戻して待つ | 画面が3秒ごとに自動再接続し ● が緑に戻る | [ ] |

- [ ] 接続後、iPhone を触らず2分以上放置しても画面がロックされず、接続欄の ● が緑のままである

## 8. CAN 送信の確認（ラズパイ＋STM32）
前提: STM32 を少なくとも1枚 CAN（500kbps、終端あり）につないで電源オン。**タイヤを浮かせる**。

1. launch 起動後、ログを確認する。
- [ ] `set_done` が出る

2. 別ターミナルで次を実行する。
```bash
pkill -f lib/pscon_node/pscon_node
```
- [ ] `pscon_data timeout: stop` が出る（送信ループが回っている＝CANフレームがACKされている）

出なければ送信完了待ちで止まっている。CAN H/L 配線・終端抵抗・ボーレート・STM32 の CAN 初期化を確認する。
`/pscon_data` が200ms途絶えると停止指令に切り替わる。`pscon_data timeout: stop` と復帰時の `pscon_data resumed` は、状態が変わったときだけ出る（起動時は `resumed` が出ないことがある）。

確認後は launch を Ctrl+C して起動し直す（自動起動の場合は `sudo systemctl restart tudarobo`。止めた `pscon_node` は自動では戻らない）。

3. （任意）STM32 ファームが受信データを UART に出せる場合、シリアルモニタで期待値を確認する。

| 操作 | [0] | [1] | [2] |
|---|---|---|---|
| スティックを離す | 0x30 | 0 | 0 |
| 左スティック前に倒し切る | 0xF0 | 前後(+100付近) | 左右(0付近) |
| 左スティック右に倒し切る | 0xF0 | 前後(0付近) | 左右(+100付近) |
| 右スティック右に倒し切る(高速) | 0xF1 | 0x01 | 0x02 |
| 右スティック左に少しだけ | 0xF1 | 0x02 | 0x01 |
| iPhone の Wi‑Fi を切る | 0x30 | 0 | 0 |

注: [1][2] は符号付き1バイト（-100〜100）。走行基板は HAL 側の受信フィルタ修正までは受信しない。

## 9. 記録
- 日付 / 確認者:
- iPhone の機種・iOS / ゲームパッドの機種:
- 不合格だった項目と状況:

## うまくいかないとき
| 症状 | 確認すること |
|---|---|
| ページが開かない | `<PiのIP>` が正しいか、launch のログに Webサーバーのエラーがないか、`~/Phone_Controller` が `/home/ubuntu/Phone_Controller` にあるか |
| ● が緑にならない | 接続先の IP・ポート 9090、`ss -tlnp \| grep 9090` |
| パッドが「未検出」のまま | パッドのボタンを押したか、iPhone の Bluetooth 設定で接続済みか |
| `/cmd_vel` は来るが `/pscon_data` が動かない | `ros2 topic echo /joy` が動くか（動かなければ `cmd_vel_to_joy`、動けば `pscon_node`） |
| RT が 1 にならない | launch が `tudarobo.launch.py` か（`bringup.launch.py` 単体だと torobo 扱い） |
| `set_done` が出ない（0/1 が流れ続ける） | CANボードの SPI 配線、`dtparam=spi=on` |
| 8章で `pscon_data timeout: stop` が出ない | STM32 が CAN に1台もつながっていない／電源オフ／配線・終端・ボーレート |
| `pscon_data timeout: stop` が出続ける | `pscon_node` が動いているか、`ros2 topic echo /joy` が流れているか |
