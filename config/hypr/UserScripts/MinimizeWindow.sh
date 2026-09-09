#!/usr/bin/env bash

set -euo pipefail

command -v hyprctl >/dev/null 2>&1 || exit 1
command -v jq >/dev/null 2>&1 || exit 1

state_dir="${XDG_RUNTIME_DIR:-/tmp}/hypr-deblestia"
state_file="$state_dir/minimized-windows.tsv"
mkdir -p "$state_dir"

window_json="$(hyprctl activewindow -j 2>/dev/null)"
address="$(jq -r '.address // empty' <<<"$window_json")"
workspace="$(jq -r '.workspace.name // empty' <<<"$window_json")"
[ -n "$address" ] && [ -n "$workspace" ] || exit 1

touch "$state_file"
sed -i "\|^${address}[[:space:]]|d" "$state_file"
printf '%s\t%s\n' "$address" "$workspace" >>"$state_file"
hyprctl dispatch movetoworkspacesilent "special:minimized,address:${address}"
