# tudarobo 試合用操作ページ 設計

## 目的
第77回津田沼祭ロボコン（tudarobo、独立ステア機）向けに、試合中に使う簡単なスマホ操作ページを用意する。
torobo（オムニ機）用の `web/robot-console.html` の仕組みを流用し、まずは足回りだけ扱う。

## ゴール / 非ゴール
- ゴール: ゲームパッド（スマホにBluetooth接続）で足回りを操縦でき、画面で速度2段階・逆転を切り替えられる。
- 非ゴール: タスク管理、フィールドマップ、機構ボタン、PIDゲイン調整、デモモード、テレメトリ表示。
- アンチゴール: torobo 用の `robot-console.html` や torobo 経路（`robot_profile` 既定値）の挙動を変えること。

## 制約
- 経路: iPhone(Safari, roslibjs) → Wi-Fi → rosbridge(9090) → `/cmd_vel` → `cmd_vel_to_joy` → `/joy` → tudarobo `pscon_node` → `can_node`。
- tudarobo の `pscon_node` は torobo と同一。`/joy` の形式（axes[4]=st_rx, axes[5]=st_ry, axes[6]=旋回向き, axes[7]=旋回大きさ, buttons[0..7]）は既存契約のまま。
- tudarobo の `can_node` は旋回速度を `buttons[7]`(RT) の2段階で決める（1→高速 0x02、0→低速 0x01）。`axes[7]` は無視。並進と旋回は排他（旋回が優先）。
- 画面に非常停止ボタンを置かない（CLAUDE.md 安全則）。デッドマン（20Hz送出）を壊さない。
- 会場はネット無しのため `roslib.min.js` はローカル同梱を使う。

## 検討した方法
- A. 新規HTML `web/tudarobo-console.html` を1枚追加 ← **採用**。torobo の画面に手を入れずに済む。
- B. `robot-console.html` にタブ追加 → torobo 用の CFG・機構ボタンと混ざるため不採用。
- C. チームの tudarobo リポジトリ側に置く → 担当範囲（`/joy` まで）が分散するため不採用。

## 決めた内容
### 画面 `web/tudarobo-console.html`（スマホ縦、1ページ）
```
[ ws://<PiのIP>:9090 ] [接続] ● 20Hz
─ 足回り 速度 ─   [ 高速 ] [ 低速 ]
─ 足回り 逆転 ─   [ 通常 ] [ 逆転 ]
─ 操作説明 ─  左スティック:移動 / 右スティック左右:旋回
```
- 自己完結の1ファイル（`./roslib.min.js` のみ読み込み）。見た目は robot-console.html の配色・ボタンスタイルに合わせる。
- 接続: URL入力・接続/切断ボタン・接続状態●・送出Hz表示。切断/失敗時は3秒ごとに自動再接続（robot-console.html と同じ挙動）。
- ゲームパッド: robot-console.html の `CFG.gamepad.axes` と同じ割り当て（forward=axes1反転, strafe=axes0反転, rotate=axes2反転, deadzone 0.08）。機構ボタンは読まない。
- 送出: 20Hzで `/cmd_vel` を publish（デッドマンのハートビート）。`linear.x = fx*maxLin*scale*rev`, `linear.y = fy*maxLin*scale*rev`, `angular.z = rz*maxAng*scale`（逆転は並進のみ反転）。maxLin=maxAng=1.0。パッド切断時は0を送る。
- 速度: 低速 scale=0.5 / 高速 scale=1.0、起動時は高速。逆転は起動時オフ。
- 操作説明はテキスト（ボタン配置画像は機構確定後に差し替え）。

### `cmd_vel_to_joy.py` に `robot_profile` パラメータ
- 文字列パラメータ、既定 `torobo`（現状と完全に同じ動作）。
- `tudarobo` のとき: 停止中でなく、`|angular.z| > TURN_DEADZONE` かつ `|angular.z| >= TUDAROBO_TURN_FAST_THRESHOLD(0.75)` なら `buttons[7]=1`。
  → 画面の「高速」で旋回を倒し切ると高速旋回、「低速」(最大0.5)では常に低速旋回になる。
- `bringup.launch.py` に launch 引数 `robot_profile`（既定 `torobo`）を追加して渡す。

### README
tudarobo 用の起動手順を追記（ワークスペース `tudarbo2026_kitakamisanti_ros2`、`pscon_node` と `can_node`、`robot_profile:=tudarobo`、ページURL `tudarobo-console.html`）。

## 実装者に任せる点
- CSSやDOMの細部（robot-console.html の見た目に揃える範囲で）。

## 前提（担当外）
tudarobo の `can_node` は現状 `can_T()` を呼んでおらず、STM32 run もCAN指令を無視するテスト状態のため、実機が動くのはチーム側の修正後。それまでは `ros2 topic echo /pscon_data` で確認する。
