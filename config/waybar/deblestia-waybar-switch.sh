#!/usr/bin/env bash

set -euo pipefail

waybar_dir="${XDG_CONFIG_HOME:-$HOME/.config}/waybar"
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/deblestia"
state_file="$state_dir/ui-mode"
mode="${1:-}"

if [ -z "$mode" ]; then
    mode="$(
        printf '%s\n' \
            'Custom Debian V2 Immersive · Caelestia' \
            'Nova 2 Waybar · îlots multi-écran' \
            'Nova Shell Custom Debian · Quickshell' |
            rofi -dmenu -i -p 'Deblestia UI' \
                -theme "$HOME/.config/rofi/DebianGlass.rasi"
    )"
fi

case "$mode" in
    debian-v2|Custom\ Debian\ V2*)
        mode='debian-v2'
        config_name=''
        style_name=''
        label='Custom Debian V2 Immersive'
        ;;
    nova2|Nova\ 2*)
        mode='nova2'
        config_name='[Deblestia] Nova 2'
        style_name='[Deblestia] Nova 2.css'
        label='Nova 2 Waybar'
        ;;
    nova-shell|Nova\ Shell*)
        mode='nova-shell'
        config_name=''
        style_name=''
        label='Nova Shell'
        ;;
    '') exit 0 ;;
    *)
        printf 'Mode inconnu : %s\n' "$mode" >&2
        exit 2
        ;;
esac

if [ "$mode" = nova2 ]; then
    [ -f "$waybar_dir/configs/$config_name" ] || {
        printf 'Configuration absente : %s\n' "$config_name" >&2
        exit 1
    }
    [ -f "$waybar_dir/styles/$style_name" ] || {
        printf 'Style absent : %s\n' "$style_name" >&2
        exit 1
    }
    ln -sfn "$waybar_dir/configs/$config_name" "$waybar_dir/config"
    ln -sfn "$waybar_dir/styles/$style_name" "$waybar_dir/style.css"
fi

mkdir -p "$state_dir"
temporary="$(mktemp "$state_dir/.ui-mode.XXXXXX")"
trap 'rm -f "$temporary"' EXIT
printf '%s\n' "$mode" >"$temporary"
mv "$temporary" "$state_file"
trap - EXIT

"$HOME/.config/hypr/scripts/desktop-shell-mode.sh" "$mode" &
notify-send "Deblestia UI" "$label activé"
