#!/usr/bin/env bash

set -euo pipefail

if pgrep -x wlogout >/dev/null 2>&1; then
    pkill -x wlogout
    exit 0
fi

if ! command -v wlogout >/dev/null 2>&1; then
    notify-send -u critical "Session Deblestia" "wlogout n'est pas installé" \
        2>/dev/null || true
    exit 1
fi

height="$(
    hyprctl monitors -j 2>/dev/null |
        jq -r 'first(.[] | select(.focused == true) | (.height / .scale | floor)) // 1080'
)"

case "$height" in
    ''|*[!0-9]*) margin=200 ;;
    *)
        if [ "$height" -ge 2160 ]; then margin=600
        elif [ "$height" -ge 1440 ]; then margin=400
        elif [ "$height" -ge 1080 ]; then margin=200
        else margin=50
        fi
        ;;
esac

exec wlogout --protocol layer-shell -b 6 -T "$margin" -B "$margin"
