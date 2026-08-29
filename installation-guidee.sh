#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<'EOF'
Usage : ./installation-guidee.sh [composant]

Composants :
  deblestia-bar      barre Waybar verticale Deblestia Bar
  deblestia-nova     barre Waybar en îlots Deblestia Nova
  deblestia-shell    environnement Caelestia Deblestia Shell
  mpvpaper-engine    fonds d'écran vidéo MPVpaper Engine
  periphx            centre de contrôle matériel PeriphX
  mirrorbridge       miroir Android et iPhone MirrorBridge

Sans argument, un menu interactif guide l'installation.
EOF
}

component="${1:-}"
if [ -z "$component" ]; then
    cat <<'EOF'
Installation guidée — Deblestia

  1) Deblestia Bar
  2) Deblestia Nova
  3) Deblestia Shell
  4) MPVpaper Engine
  5) PeriphX
  6) MirrorBridge
  q) Quitter
EOF
    read -r -p "Votre choix : " choice
    case "$choice" in
        1) component=deblestia-bar ;;
        2) component=deblestia-nova ;;
        3) component=deblestia-shell ;;
        4) component=mpvpaper-engine ;;
        5) component=periphx ;;
        6) component=mirrorbridge ;;
        q|Q) exit 0 ;;
        *) printf 'Choix inconnu : %s\n' "$choice" >&2; exit 2 ;;
    esac
fi

case "$component" in
    deblestia-bar|debian-glass)
        name="Deblestia Bar"
        installer="$repo_dir/install-deblestia-bar.sh"
        check_command=("$installer" check)
        ;;
    deblestia-nova)
        name="Deblestia Nova"
        installer="$repo_dir/install-deblestia-nova.sh"
        check_command=("$installer" check)
        ;;
    deblestia-shell|debian-immersive)
        name="Deblestia Shell"
        installer="$repo_dir/install-deblestia-shell.sh"
        check_command=("$installer" check)
        ;;
    mpvpaper-engine)
        name="MPVpaper Engine"
        installer="$repo_dir/install-mpvpaper-engine.sh"
        check_command=("$installer" check)
        ;;
    periphx)
        name="PeriphX"
        installer="$repo_dir/install-periphx.sh"
        check_command=("$installer" check)
        ;;
    mirrorbridge)
        name="MirrorBridge"
        installer="$repo_dir/install-mirrorbridge.sh"
        check_command=("$installer" check)
        ;;
    help|-h|--help)
        usage
        exit 0
        ;;
    *)
        printf 'Composant inconnu : %s\n\n' "$component" >&2
        usage >&2
        exit 2
        ;;
esac

printf '\nComposant sélectionné : %s\n' "$name"
if ((${#check_command[@]})); then
    printf 'Vérification des prérequis…\n'
    if ! "${check_command[@]}"; then
        printf '\nInstallez les prérequis signalés, puis relancez cette commande.\n' >&2
        exit 1
    fi
fi

if [ -t 0 ]; then
    read -r -p "Installer $name maintenant ? [o/N] " answer
    case "$answer" in
        o|O|oui|OUI|y|Y|yes|YES) ;;
        *) printf 'Installation annulée.\n'; exit 0 ;;
    esac
fi

exec "$installer" install
