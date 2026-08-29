#!/usr/bin/env bash

set -u

# Laisser finir les autres exec-once, puis garder un seul panneau principal.
sleep 2
pkill -x waybar 2>/dev/null || true

# Certaines configurations KooL lancent Waybar un peu après les autres
# applications de session. Un second passage empêche une barre concurrente.
(
    sleep 3
    pkill -x waybar 2>/dev/null || true
) &

if command -v caelestia >/dev/null 2>&1; then
    caelestia shell -k 2>/dev/null || true
elif [ -x "$HOME/.nix-profile/bin/caelestia" ]; then
    "$HOME/.nix-profile/bin/caelestia" shell -k 2>/dev/null || true
fi

if ! command -v qs >/dev/null 2>&1; then
    command -v notify-send >/dev/null 2>&1 && notify-send \
        "Deblestia Nova" "Quickshell (qs) est introuvable."
    exit 1
fi

exec qs -d -c deblestia-nova
