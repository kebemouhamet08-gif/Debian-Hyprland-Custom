#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<'EOF'
Usage : ./installation-guidee.sh [composant]

Composants :
  custom-debian-v2   interface Caelestia Custom Debian V2 Immersive
  deblestia-nova2    barre Waybar multi-écran Deblestia Nova 2
  deblestia-nova-shell shell Quickshell Nova Shell Custom Debian
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

  1) Custom Debian V2 Immersive (Caelestia)
  2) Deblestia Nova 2 (Waybar multi-écran)
  3) Nova Shell Custom Debian (Quickshell)
  4) MPVpaper Engine
  5) PeriphX
  6) MirrorBridge
  q) Quitter
EOF
    read -r -p "Votre choix : " choice
    case "$choice" in
        1) component=custom-debian-v2 ;;
        2) component=deblestia-nova2 ;;
        3) component=deblestia-nova-shell ;;
        4) component=mpvpaper-engine ;;
        5) component=periphx ;;
        6) component=mirrorbridge ;;
        q|Q) exit 0 ;;
        *) printf 'Choix inconnu : %s\n' "$choice" >&2; exit 2 ;;
    esac
fi

case "$component" in
    deblestia-nova2)
        name="Deblestia Nova 2"
        installer="$repo_dir/install-deblestia-nova2.sh"
        check_command=("$installer" check)
        ;;
    deblestia-nova-shell)
        name="Nova Shell Custom Debian"
        installer="$repo_dir/install-deblestia-nova-shell.sh"
        check_command=("$installer" check)
        ;;
    custom-debian-v2)
        name="Custom Debian V2 Immersive"
        installer="$repo_dir/install-custom-debian-v2.sh"
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
