#!/usr/bin/env bash

set -u

force_launch=false
[ "${1:-}" = "--force" ] && force_launch=true

# Au démarrage de Hyprland, Nova ne s'ouvre que s'il est le profil mémorisé.
# `--force` est utilisé par le sélecteur lors d'un changement explicite.
state_file="${XDG_STATE_HOME:-$HOME/.local/state}/deblestia/ui-mode"
active_mode="$(cat "$state_file" 2>/dev/null || true)"
if ! $force_launch && [ "$active_mode" != nova-shell ]; then
    exit 0
fi

stop_legacy_panels() {
    local suite="$HOME/.config/waybar/debian-glass-suite.sh" caelestia_pid

    # Arrêter les contrôleurs avant Waybar : ils peuvent sinon recréer le rail
    # latéral ou les panneaux auxiliaires après la fermeture du processus.
    if [ -x "$suite" ]; then
        "$suite" off >/dev/null 2>&1 || true
    fi
    if command -v caelestia >/dev/null 2>&1; then
        caelestia shell -k >/dev/null 2>&1 || true
    elif [ -x "$HOME/.nix-profile/bin/caelestia" ]; then
        "$HOME/.nix-profile/bin/caelestia" shell -k >/dev/null 2>&1 || true
    fi

    # Certaines installations Nix ignorent `caelestia shell -k`. Identifier
    # alors uniquement les instances dont le chemin de configuration contient
    # caelestia-shell, puis les arrêter par PID via Quickshell.
    if command -v qs >/dev/null 2>&1; then
        while read -r caelestia_pid; do
            [ -n "$caelestia_pid" ] || continue
            qs kill --pid "$caelestia_pid" >/dev/null 2>&1 || true
        done < <(
            qs list --all 2>/dev/null | awk '
                /Process ID:/ { pid = $3 }
                /Config path:.*caelestia-shell/ { print pid }
            '
        )
    fi

    pkill -x waybar 2>/dev/null || true
}

nova_is_running() {
    qs list --all 2>/dev/null | awk '
        /Config path:.*\/deblestia-nova\/shell\.qml/ { found = 1 }
        END { exit !found }
    '
}

# Laisser finir les autres exec-once, puis garder le shell Nova complet.
sleep 2
stop_legacy_panels

# Certaines configurations KooL lancent leur profil un peu après les autres
# applications de session. Un second passage ferme aussi leurs contrôleurs.
(
    sleep 3
    stop_legacy_panels
) &

if ! command -v qs >/dev/null 2>&1; then
    command -v notify-send >/dev/null 2>&1 && notify-send \
        "Deblestia Nova" "Quickshell (qs) est introuvable."
    exit 1
fi

# Quickshell peut conserver un démon de session même après la fermeture de sa
# fenêtre. Réutiliser son instance Nova au lieu d'empiler une seconde barre.
if ! nova_is_running; then
    qs -n -d -c deblestia-nova
fi

# Une ancienne session peut avoir laissé la barre QML fermée.
if command -v hyprctl >/dev/null 2>&1; then
    hyprctl dispatch global quickshell:barOpen >/dev/null 2>&1 || true
fi
