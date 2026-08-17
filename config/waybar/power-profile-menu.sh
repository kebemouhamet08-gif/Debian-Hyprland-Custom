#!/usr/bin/env bash

set -u

current="$(powerprofilesctl get 2>/dev/null || true)"
[ -n "$current" ] || current="balanced"

case "$current" in
    performance) selected=0 ;;
    balanced) selected=1 ;;
    power-saver) selected=2 ;;
    *) selected=1 ;;
esac

choice="$(
    printf '%s\n' \
        '󰓅  Performance' \
        '  Équilibré' \
        '  Économie' |
        rofi -dmenu -i -p 'Profil énergie' -selected-row "$selected" \
            -theme "$HOME/.config/rofi/DebianGlass.rasi"
)"

case "$choice" in
    *Performance) profile="performance"; label="Performance" ;;
    *Équilibré) profile="balanced"; label="Équilibré" ;;
    *Économie) profile="power-saver"; label="Économie" ;;
    *) exit 0 ;;
esac

if powerprofilesctl set "$profile" 2>/dev/null; then
    notify-send "Profil énergie" "$label activé"
else
    notify-send -u critical "Profil énergie" \
        "Le service power-profiles-daemon n’est pas disponible."
fi
