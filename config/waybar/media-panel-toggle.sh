#!/usr/bin/env bash

set -u

script="$HOME/.config/waybar/media-panel.py"
pid="$(pgrep -f "^/usr/bin/python3 ${script}$" | head -n 1 || true)"

if [ -n "$pid" ]; then
    kill "$pid"
else
    hyprctl dispatch exec "/usr/bin/python3 $script"
fi
