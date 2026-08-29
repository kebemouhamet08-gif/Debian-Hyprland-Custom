#!/usr/bin/env bash

set -u

# Prefer Caelestia's native lock when its Debian PAM compatibility file is
# available. If the shell is not running or IPC fails, keep Hyprlock as a
# secure fallback.
faillock_file="/run/faillock/$(id -un)"
caelestia_cli=""
debian_hyprlock="/usr/bin/hyprlock"
wallpaper_selector="$HOME/.config/hypr/UserScripts/RandomLockScreen.sh"

if [ -x "$HOME/.nix-profile/bin/caelestia" ]; then
    caelestia_cli="$HOME/.nix-profile/bin/caelestia"
elif command -v caelestia >/dev/null 2>&1; then
    caelestia_cli="$(command -v caelestia)"
fi

if [ -n "$caelestia_cli" ] && [ -r "$faillock_file" ] && [ -w "$faillock_file" ]; then
    if "$caelestia_cli" shell lock lock; then
        exit 0
    fi
fi

# Prefer Debian's packaged Hyprlock binary for the fallback. A locally
# compiled copy in /usr/local/bin can otherwise use a different PAM setup.
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
