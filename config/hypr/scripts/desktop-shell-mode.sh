#!/usr/bin/env bash

# Sélection exclusive entre Deblestia Nova, Caelestia et Waybar.
set -u

active_layout="$(basename "$(readlink -f "$HOME/.config/waybar/config")" 2>/dev/null || true)"
state_file="${XDG_STATE_HOME:-$HOME/.local/state}/deblestia/ui-mode"
layout="${1:-}"
[ -n "$layout" ] || layout="$(cat "$state_file" 2>/dev/null || printf '%s' "$active_layout")"
v2_layout="[CUSTOM] Debian Glass V2 - Immersive"
suite="$HOME/.config/waybar/debian-glass-suite.sh"
caelestia_launcher="$HOME/.config/hypr/scripts/caelestia-v2-launch.sh"
nova_launcher="$HOME/.config/hypr/scripts/deblestia-nova-shell-launch.sh"
palette_sync="$HOME/.config/hypr/UserScripts/WaybarWallpaperSync.sh"

set_hypr_keyword() {
    hyprctl keyword "$1" "$2" >/dev/null 2>&1 || true
}

apply_caelestia_windows() {
    set_hypr_keyword general:layout dwindle
    set_hypr_keyword general:gaps_in 5
    set_hypr_keyword general:gaps_out 8
    set_hypr_keyword general:border_size 2
    set_hypr_keyword decoration:rounding 16
    set_hypr_keyword decoration:active_opacity 0.98
    set_hypr_keyword decoration:inactive_opacity 0.92
    set_hypr_keyword dwindle:preserve_split true
    set_hypr_keyword dwindle:smart_split true
    set_hypr_keyword dwindle:smart_resizing true
    set_hypr_keyword dwindle:use_active_for_splits true
}

restore_debian_windows() {
    set_hypr_keyword general:layout dwindle
    set_hypr_keyword general:gaps_in 6
    set_hypr_keyword general:gaps_out 12
    set_hypr_keyword general:border_size 2
    set_hypr_keyword decoration:rounding 8
    set_hypr_keyword decoration:active_opacity 1.0
    set_hypr_keyword decoration:inactive_opacity 1.0
}

stop_caelestia() {
    if [ -x "$HOME/.nix-profile/bin/caelestia" ]; then
        "$HOME/.nix-profile/bin/caelestia" shell -k >/dev/null 2>&1 || true
    elif command -v caelestia >/dev/null 2>&1; then
        caelestia shell -k >/dev/null 2>&1 || true
    fi
}

stop_nova() {
    local nova_pid

    command -v qs >/dev/null 2>&1 || return 0
    while read -r nova_pid; do
        [ -n "$nova_pid" ] || continue
        qs kill --pid "$nova_pid" >/dev/null 2>&1 || true
        # Un démon Quickshell persistant peut recréer la même interface après
        # `qs kill`; terminer uniquement le PID associé à la configuration Nova.
        kill "$nova_pid" >/dev/null 2>&1 || true
    done < <(
        qs list --all 2>/dev/null | awk '
            /Process ID:/ { pid = $3 }
            /Config path:.*\/deblestia-nova\/shell\.qml/ { print pid }
        '
    )
}

suite_off() {
    if [ -x "$suite" ]; then
        "$suite" off >/dev/null 2>&1 || true
    fi
}

case "$layout" in
    debian-v2|'[CUSTOM] Debian Glass V2 - Immersive') mode="$v2_layout" ;;
    nova2|'[Deblestia] Nova 2') mode='nova2' ;;
    nova-shell) mode='nova-shell' ;;
    *) mode="$layout" ;;
esac

# Un changement explicite devient le mode restauré à la prochaine connexion.
if [ -n "${1:-}" ]; then
    saved_mode="$mode"
    [ "$mode" = "$v2_layout" ] && saved_mode='debian-v2'
    state_dir="$(dirname "$state_file")"
    mkdir -p "$state_dir"
    temporary="$(mktemp "$state_dir/.ui-mode.XXXXXX")"
    trap 'rm -f "$temporary"' EXIT
    printf '%s\n' "$saved_mode" >"$temporary"
    mv "$temporary" "$state_file"
    trap - EXIT
fi

if [ "$mode" = nova-shell ]; then
    suite_off
    pkill -x waybar 2>/dev/null || true
    stop_caelestia
    restore_debian_windows
    if [ -x "$nova_launcher" ]; then
        exec "$nova_launcher" --force
    fi
    exit 1
fi

# Tous les autres profils retirent ensemble la barre, l'horloge et le dock Nova.
stop_nova

if [ "$mode" = "$v2_layout" ]; then
    suite_off
    pkill -x waybar 2>/dev/null || true
    apply_caelestia_windows
    "$caelestia_launcher"
    sleep 0.60
    exec "$HOME/.config/hypr/scripts/caelestia-wallpaper-sync.sh"
fi

stop_caelestia
restore_debian_windows

if [ "$mode" = "no panel" ]; then
    suite_off
    pkill -x waybar 2>/dev/null || true
    exit 0
fi

if [ -x "$palette_sync" ]; then
    "$palette_sync" --no-start >/dev/null 2>&1 || true
fi

suite_off
pkill -x waybar 2>/dev/null || true
sleep 0.20
hyprctl dispatch exec waybar >/dev/null 2>&1 || setsid -f waybar
