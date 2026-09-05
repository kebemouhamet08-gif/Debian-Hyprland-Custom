#!/usr/bin/env bash

# Navigation Nova 2 déclenchée uniquement par une action utilisateur.
set -euo pipefail

action="${1:-}"
case "$action" in
    previous|next) ;;
    *)
        printf 'Usage : %s previous|next\n' "$0" >&2
        exit 2
        ;;
esac

command -v hyprctl >/dev/null 2>&1 || exit 1
command -v jq >/dev/null 2>&1 || exit 1

cursor_json="$(hyprctl cursorpos -j 2>/dev/null || printf '{}')"
monitors_json="$(hyprctl monitors -j 2>/dev/null || printf '[]')"

read -r cursor_x cursor_y < <(
    jq -r '
        if type == "array" then "\(.[0] // 0) \(.[1] // 0)"
        elif type == "object" then "\(.x // 0) \(.y // 0)"
        else "0 0"
        end
    ' <<<"$cursor_json"
)

monitor_state="$(
    jq -r --argjson x "${cursor_x%.*}" --argjson y "${cursor_y%.*}" '
        (
            first(
                .[]
                | select(
                    $x >= .x and $x < (.x + .width)
                    and $y >= .y and $y < (.y + .height)
                )
            )
            // first(.[] | select(.focused == true))
            // empty
        )
        | "\(.name) \(.activeWorkspace.id)"
    ' <<<"$monitors_json"
)"

[ -n "$monitor_state" ] || exit 1
read -r monitor active_workspace <<<"$monitor_state"

case "$monitor" in
    eDP-1) first_workspace=1; last_workspace=10 ;;
    HDMI-A-1) first_workspace=11; last_workspace=20 ;;
    *)
        # Sortie non gérée : laisser Hyprland appliquer sa navigation locale.
        direction='m-1'
        [ "$action" = next ] && direction='m+1'
        exec hyprctl dispatch workspace "$direction"
        ;;
esac

if [ "$active_workspace" -lt "$first_workspace" ] || \
        [ "$active_workspace" -gt "$last_workspace" ]; then
    target="$first_workspace"
elif [ "$action" = next ]; then
    target=$((active_workspace + 1))
    [ "$target" -le "$last_workspace" ] || target="$first_workspace"
else
    target=$((active_workspace - 1))
    [ "$target" -ge "$first_workspace" ] || target="$last_workspace"
fi

if [ "${DEBLESTIA_DEBUG:-0}" = 1 ]; then
    cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/deblestia"
    mkdir -p "$cache_dir"
    printf '%(%F %T)T monitor=%s active=%s action=%s target=%s\n' -1 \
        "$monitor" "$active_workspace" "$action" "$target" \
        >>"$cache_dir/workspaces.log"
fi

exec hyprctl dispatch workspace "$target"
