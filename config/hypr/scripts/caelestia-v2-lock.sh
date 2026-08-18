#!/usr/bin/env bash

set -u

# Use the same systemd-logind path as the physical lock key. Hypridle listens
# for this event and starts the configured locker (hyprlock).
if command -v loginctl >/dev/null 2>&1; then
    exec loginctl lock-session
fi

if command -v hyprlock >/dev/null 2>&1; then
    exec hyprlock -q
fi

legacy_lock="$HOME/.config/hypr/scripts/LockScreen.sh"
if [ -x "$legacy_lock" ]; then
    exec "$legacy_lock"
fi

command -v notify-send >/dev/null 2>&1 && notify-send \
    "Verrouillage indisponible" \
    "loginctl, hyprlock et LockScreen.sh sont introuvables."
exit 1
