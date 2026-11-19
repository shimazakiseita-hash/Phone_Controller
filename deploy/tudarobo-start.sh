#!/usr/bin/env bash

ROS_SETUP=${ROS_SETUP:-/opt/ros/jazzy/setup.bash}
TEAM_WS=${TEAM_WS:-$HOME/tudarbo2026_kitakamisanti_ros2}
PHONE_WS=${PHONE_WS:-$HOME/Phone_Controller/ros2_ws}

for setup in "$ROS_SETUP" "$TEAM_WS/install/setup.bash" "$PHONE_WS/install/setup.bash"; do
    if [[ ! -f "$setup" ]]; then
        echo "エラー: setup.bash が見つかりません: $setup" >&2
        exit 1
    fi
    source "$setup" || exit 1
done

exec ros2 launch robocon_bridge tudarobo.launch.py
