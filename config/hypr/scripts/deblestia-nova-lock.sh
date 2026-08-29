#!/usr/bin/env bash

set -u

# Le verrou intégré en amont dépend de PAM. Sur Debian, le paquet Hyprlock
# utilise la pile PAM du système et reste le chemin le plus fiable.
wallpaper_selector="$HOME/.config/hypr/UserScripts/RandomLockScreen.sh"

if [ -x /usr/bin/hyprlock ]; then
    if [ -x "$wallpaper_selector" ]; then
        "$wallpaper_selector" --select-only
    fi
    exec /usr/bin/hyprlock -q
fi

if command -v hyprlock >/dev/null 2>&1; then
    exec hyprlock -q
fi

if command -v loginctl >/dev/null 2>&1; then
    exec loginctl lock-session
fi

command -v notify-send >/dev/null 2>&1 && notify-send \
    "Deblestia Nova" "Hyprlock et loginctl sont introuvables."
exit 1
