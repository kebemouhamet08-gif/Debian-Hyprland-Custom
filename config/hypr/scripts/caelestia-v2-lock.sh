#!/usr/bin/env bash

set -u

# Prefer Debian's packaged binary. A locally compiled copy in /usr/local/bin
# can otherwise shadow it and use a different PAM configuration.
debian_hyprlock="/usr/bin/hyprlock"
wallpaper_selector="$HOME/.config/hypr/UserScripts/RandomLockScreen.sh"

if [ -x "$debian_hyprlock" ]; then
    if [ -x "$wallpaper_selector" ]; then
        "$wallpaper_selector" --select-only
    fi
    exec "$debian_hyprlock" -q
fi

if command -v hyprlock >/dev/null 2>&1; then
    exec hyprlock -q
fi

# Let hypridle handle the lock event when hyprlock is managed elsewhere.
if command -v loginctl >/dev/null 2>&1; then
    exec loginctl lock-session
fi

legacy_lock="$HOME/.config/hypr/scripts/LockScreen.sh"
if [ -x "$legacy_lock" ]; then
    exec "$legacy_lock"
fi

command -v notify-send >/dev/null 2>&1 && notify-send \
    "Verrouillage indisponible" \
    "loginctl, hyprlock et LockScreen.sh sont introuvables."
exit 1
