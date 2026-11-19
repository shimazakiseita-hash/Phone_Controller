# tudarobo 試合用操作ページ Implementation Plan

> **For agentic workers:** 実装は Codex（`/usr/bin/codex exec`）が行い、Claude が差分とレビュー指摘を検証する（~/CLAUDE.md の役割分担）。Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** tudarobo（独立ステア機）向けの試合用スマホ操作ページと、旋回高速/低速を `buttons[7]` に出す `robot_profile` を追加する。

**Architecture:** 新規の自己完結HTML `web/tudarobo-console.html` が 20Hz で `/cmd_vel` を送る。`cmd_vel_to_joy.py` は `robot_profile=tudarobo` のときだけ、大きい旋回入力で `buttons[7]=1` を立てる。torobo 用の既存の挙動は変えない。

**Tech Stack:** HTML/JS + roslibjs（ローカル同梱）、ROS2 Jazzy rclpy、pytest（`/usr/bin/python3`、`source /opt/ros/jazzy/setup.bash` 後）。

**Spec:** `docs/superpowers/specs/2026-11-19-tudarobo-match-page-design.md`

## Global Constraints
- `web/robot-console.html` と `demo-web/` は変更しない。
- `robot_profile` の既定値は `torobo`。既定値での `/joy` 出力は現状とバイト単位で同一。
- 画面に非常停止ボタンを置かない。`/cmd_vel` は 20Hz で送り続ける（デッドマン）。
- 低速 scale=0.5 / 高速 scale=1.0、起動時は高速・逆転オフ。maxLin=maxAng=1.0。deadzone 0.08。
- `TUDAROBO_TURN_FAST_THRESHOLD = 0.75`。
- コメントは日本語で必要最低限。

## Review Focus
1. 停止中（デッドマン超過・estop ラッチ中）に tudarobo でも `buttons[7]` が 0 になる → Task 1 のテストで固定。
2. 旋回入力が `TURN_DEADZONE` 以下なら高速ビットが立たない → Task 1 のテストで固定。
3. ゲームパッドが切断されたら画面は 0 速度を送り続ける（最後の値を送り続けない） → Task 2 の手動確認。
4. 未接続時に `/cmd_vel` を publish しない・例外を出さない → Task 2 の手動確認。
5. 低速モードでは旋回を倒し切っても `angular.z` は 0.5 なので常に低速旋回 → Task 1 のテストで固定。

---

### Task 1: `cmd_vel_to_joy.py` に `robot_profile` を追加

**Files:**
- Modify: `ros2_ws/src/robocon_bridge/robocon_bridge/cmd_vel_to_joy.py`
- Modify: `ros2_ws/src/robocon_bridge/launch/bringup.launch.py`
- Test: `ros2_ws/src/robocon_bridge/test/test_turn_fast.py`

**Interfaces:**
- Produces: モジュール関数 `tudarobo_turn_fast(angular_z: float) -> bool`、定数 `TUDAROBO_TURN_FAST_THRESHOLD = 0.75`、ROSパラメータ `robot_profile`（str、既定 `'torobo'`）、launch 引数 `robot_profile`（既定 `'torobo'`）。

- [ ] **Step 1: 失敗するテストを書く**
```python
from robocon_bridge.cmd_vel_to_joy import tudarobo_turn_fast
def test_fast_when_full():      assert tudarobo_turn_fast(1.0) and tudarobo_turn_fast(-1.0)
def test_slow_at_low_speed():   assert not tudarobo_turn_fast(0.5) and not tudarobo_turn_fast(-0.5)
def test_threshold_inclusive(): assert tudarobo_turn_fast(0.75)
def test_deadzone():            assert not tudarobo_turn_fast(0.05)
```
- [ ] **Step 2: 失敗を確認** — `cd ros2_ws/src/robocon_bridge && python3 -m pytest test/test_turn_fast.py -v` → ImportError で FAIL
- [ ] **Step 3: 実装** — `tudarobo_turn_fast` は `abs(z) > TURN_DEADZONE and abs(z) >= TUDAROBO_TURN_FAST_THRESHOLD`。`__init__` で `declare_parameter('robot_profile','torobo')`。`_publish` の非停止ブロック内、ボタンパルス処理の後で `profile=='tudarobo' and tudarobo_turn_fast(self._last_cmd.angular.z)` なら `buttons[7]=1`（停止中は全0のまま）。未知の profile は warn を出して torobo 扱い。launch に `DeclareLaunchArgument('robot_profile', default_value='torobo')` を足し `cmd_vel_to_joy` の `parameters` で渡す。
- [ ] **Step 4: テスト通過を確認** — 同コマンドで 4 件 PASS。`colcon build --packages-select robocon_bridge` が成功。
- [ ] **Step 5: コミット**

### Task 2: `web/tudarobo-console.html` を新規作成

**Files:**
- Create: `web/tudarobo-console.html`

**Interfaces:**
- Consumes: rosbridge `/cmd_vel`（`geometry_msgs/msg/Twist`）、`./roslib.min.js`。

- [ ] **Step 1: 実装** — 設計メモの「画面」節どおり。robot-console.html から接続処理（URL入力・接続/切断・●・Hz・3秒自動再接続）、ゲームパッド読み取り（axes forward=1反転, strafe=0反転, rotate=2反転, deadzone 0.08）、20Hz送出ループ、速度/逆転ボタンのスタイルを移植し、それ以外は持ち込まない。送出式: `linear.x=fx*1.0*scale*rev, linear.y=fy*1.0*scale*rev, angular.z=rz*1.0*scale`。`gamepaddisconnected` とパッド未検出時は drive を 0 にする。操作説明はテキスト「左スティック: 移動 / 右スティック左右: 旋回 / 高速で旋回を倒し切ると高速旋回」。URL初期値は `ws://10.152.79.144:9090`。
- [ ] **Step 2: 構文確認** — `<script>` 部分を抜き出して `node --check` が通る。
- [ ] **Step 3: 手動確認（Claude）** — rosbridge + `cmd_vel_to_joy`（`robot_profile:=tudarobo`）を起動し、`ros2 topic hz /cmd_vel` が約20Hz（ブラウザ接続時）。
- [ ] **Step 4: コミット**

### Task 3: README に tudarobo 起動手順を追記

**Files:**
- Modify: `README.md`（「スマホコントローラ起動方法」の後に節を追加）

- [ ] **Step 1: 追記** — `tudarbo2026_kitakamisanti_ros2` のビルド/ソース、`ros2 launch robocon_bridge bringup.launch.py robot_profile:=tudarobo`、`ros2 run pscon_node pscon_node`、`ros2 run can_node can_node`、URL `http://<PiのIP>:8080/tudarobo-console.html`、確認用 `ros2 topic echo /pscon_data`。
- [ ] **Step 2: コミット**
