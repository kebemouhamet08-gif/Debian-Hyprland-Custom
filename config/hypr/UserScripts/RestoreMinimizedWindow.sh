#!/usr/bin/env bash

set -euo pipefail

state_file="${XDG_RUNTIME_DIR:-/tmp}/hypr-deblestia/minimized-windows.tsv"
[ -s "$state_file" ] || exit 0

while [ -s "$state_file" ]; do
    entry="$(tail -n 1 "$state_file")"
    address="${entry%%$'\t'*}"
    workspace="${entry#*$'\t'}"
    sed -i '$d' "$state_file"

    if hyprctl clients -j 2>/dev/null | jq -e --arg address "$address" \
            '.[] | select(.address == $address)' >/dev/null; then
        hyprctl dispatch movetoworkspacesilent "${workspace},address:${address}"
        hyprctl dispatch focuswindow "address:${address}"
        exit 0
    fi
done
