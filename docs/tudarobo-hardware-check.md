# tudarobo スマホコントローラ 実機確認手順

スマホの操作が `/cmd_vel` → `/joy` → `/pscon_data` まで正しく届くかを、ラズパイ実機で確認する。
CAN より先（`can_node` の送信・STM32）はチーム側の修正待ちのため、この手順では `/pscon_data` までを合格ラインとする。

## 0. 用意するもの
- tudarobo のラズパイ5（電源・SSHできるPC）
- iPhone ＋ ゲームパッド（iPhone に Bluetooth でペアリング済み）
- iPhone とラズパイが同じ Wi‑Fi に入れること
- 機体にモータ電源を入れる場合は、**タイヤを浮かせる**こと・物理非常停止がすぐ押せること

## 1. 更新とビルド（ラズパイ）
```bash
cd ~/tudarbo2026_kitakamisanti_ros2 && git pull
rm -rf build install log && source /opt/ros/jazzy/setup.bash && colcon build

cd ~/Phone_Controller && git pull
cd ros2_ws && rm -rf build install log && colcon build
```
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
- [ ] `Can_manu node start` と `spi done`

補足:
- `SPI open failed` → SPI が無効。`/boot/firmware/config.txt` に `dtparam=spi=on` を入れて再起動。
- `set_start` のあと 0/1 の行が流れ続ける → CANボード(MCP2517FD)が未接続/未応答。**この確認では問題なし**（`/pscon_data` までは確認できる）。

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
for l in sys.stdin:
    l=l.strip()
    if not l.isdigit(): continue
    d=int(l)
    turn="右" if d>>8&1 else "左" if d>>9&1 else "-"
    print(f"前後={s8(d>>16&0xFF):4d} 左右={s8(d>>24&0xFF):4d} 旋回={turn} RT(高速旋回)={d>>7&1}")
'
```
（`pscon_node` は値が変わったときだけ出す。左右は左に倒すと負の値になる）

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
| 9 | 低速・通常 | 左スティックを前に倒し切る | 前後 ≈ 50 | [ ] |
| 10 | 高速・逆転 | 左スティックを前に倒し切る | 前後 ≈ -100 | [ ] |
| 11 | 高速・逆転 | 右スティックを右に倒し切る | 旋回=右（逆転しない） | [ ] |
| 12 | どれでも | スティックを全部離す | 前後=0 左右=0 旋回=- RT=0 | [ ] |

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

## 8. 記録
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
