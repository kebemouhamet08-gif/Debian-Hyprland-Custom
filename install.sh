#!/usr/bin/env bash

set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=core/setup.sh
source "$repo_dir/core/setup.sh"

usage() {
    printf 'Usage : %s [menu|diagnostic|plan|automatic|manual|component ID|contribute|uninstall]\n' "$0"
}

header() {
    cat <<'EOF'
╭────────────────────────────────────╮
│          Deblestia Setup           │
│       Debian Custom Desktop        │
╰────────────────────────────────────╯
EOF
}

diagnostic() {
    header
    printf '\nAnalyse non destructive de la machine…\n\n'
    python3 "$repo_dir/core/hardware.py"
    printf '\n'
    python3 "$repo_dir/core/compatibility.py"
}

confirm() {
    [ "${DEBLESTIA_ASSUME_YES:-0}" = 1 ] && return 0
    [ -t 0 ] || {
        printf 'Confirmation interactive requise. Utilisez DEBLESTIA_ASSUME_YES=1 en automatisation.\n' >&2
        return 1
    }
    local answer
    read -r -p "Continuer avec ce plan ? [o/N] " answer
    case "$answer" in o|O|oui|OUI|y|Y|yes|YES) return 0;; *) return 1;; esac
}

install_dependencies() {
    local mode="$1"
    mapfile -t missing < <(deblestia_missing_packages)
    ((${#missing[@]})) || { printf 'Dépendances Debian déjà présentes.\n'; return; }
    printf 'Paquets Debian nécessaires : %s\n' "${missing[*]}"
    case "$mode" in
        automatic)
            local package
            for package in "${missing[@]}"; do
                apt-cache show "$package" >/dev/null 2>&1 || {
                    printf '%s est absent des dépôts configurés. Activez explicitement les backports Debian si nécessaire.\n' "$package" >&2
                    return 1
                }
            done
            sudo apt-get install --no-install-recommends "${missing[@]}"
            ;;
        manual)
            printf 'Commande manuelle :\n  sudo apt-get install --no-install-recommends %s\n' "${missing[*]}"
            return 1
            ;;
        skip) return 1 ;;
    esac
}

automatic() {
    diagnostic
    local compatibility profile dependency_mode=automatic choice
    compatibility="$(deblestia_compatibility)"
    profile="${DEBLESTIA_PROFILE:-$(deblestia_profile)}"
    if [ "$compatibility" = UNSUPPORTED ]; then
        printf '\nInstallation automatique refusée à cause du blocage indiqué.\n' >&2
        return 1
    fi
    mapfile -t components < <(deblestia_components_for_profile "$profile")
    mapfile -t missing < <(deblestia_missing_packages)
    printf '\nProfil : %s\nGNOME et le display manager actuel seront conservés.\n' "$profile"
    printf 'Composants proposés : %s\n' "${components[*]}"
    printf 'Dépendances à installer : %s\n' "${missing[*]:-aucune}"
    if [ "${DEBLESTIA_PLAN_ONLY:-0}" = 1 ]; then
        printf 'Simulation terminée : aucune modification effectuée.\n'
        return 0
    fi
    if [ -t 0 ] && ((${#missing[@]})); then
        read -r -p "Dépendances : [A] automatique, [M] commandes, [S] ignorer : " choice
        case "$choice" in m|M) dependency_mode=manual;; s|S) dependency_mode=skip;; esac
    fi
    confirm || { printf 'Installation annulée.\n'; return 0; }
    if ! install_dependencies "$dependency_mode"; then
        [ "$dependency_mode" = automatic ] && return 1
        printf "Composants reportés jusqu'à la présence des dépendances.\n"
        return 0
    fi
    mkdir -p "$deblestia_state_dir"
    printf '%s\n' "$profile" >"$deblestia_state_dir/profile"
    for component_name in "${components[@]}"; do
        deblestia_install_component "$component_name"
    done
    printf '\nInstallation terminée. GNOME reste disponible dans le gestionnaire de connexion.\n'
}

component() {
    local id="${1:-}" label
    label="$(deblestia_component_field "$id" 2)"
    [ -n "$label" ] || { printf 'Composant inconnu : %s\n' "$id" >&2; return 2; }
    printf 'Composant : %s\n' "$label"
    confirm || { printf 'Installation annulée.\n'; return 0; }
    deblestia_install_component "$id"
}

manual() {
    local choice id
    while true; do
        cat <<'EOF'

Installation manuelle
  1) Deblestia Bar          5) MPVpaper Engine
  2) Deblestia Nova         6) PeriphX
  3) Deblestia Shell        7) MirrorBridge
  4) Deblestia Nova Lite
  0) Retour
EOF
        read -r -p "Choix : " choice
        case "$choice" in
            1) id=deblestia-bar;; 2) id=deblestia-nova;; 3) id=deblestia-shell;;
            4) id=deblestia-nova-lite;; 5) id=mpvpaper-engine;;
            6) id=periphx;; 7) id=mirrorbridge;;
            0) return;; *) printf 'Choix inconnu.\n'; continue;;
        esac
        component "$id"
    done
}

menu() {
    local choice
    while true; do
        header
        cat <<'EOF'

  1) Installation automatique
  2) Installation manuelle
  3) Mode contribution
  4) Diagnostic matériel
  5) Réparation / restauration
  6) Désinstallation
  0) Quitter
EOF
        read -r -p "Choix : " choice
        case "$choice" in
            1) automatic;; 2) manual;; 3) "$repo_dir/contribute.sh";; 4) diagnostic;;
            5) "$repo_dir/uninstall.sh" restore;; 6) "$repo_dir/uninstall.sh";; 0) return;;
            *) printf 'Choix inconnu.\n';;
        esac
    done
}

action="${1:-menu}"
shift || true
case "$action" in
    menu) [ -t 0 ] || { usage; exit 2; }; menu ;;
    diagnostic|check) diagnostic;; plan|--dry-run) DEBLESTIA_PLAN_ONLY=1 automatic;;
    automatic|auto) automatic;; manual) manual ;;
    component) component "${1:-}";; contribute) exec "$repo_dir/contribute.sh" "$@" ;;
    uninstall|restore) exec "$repo_dir/uninstall.sh" "$action" "$@" ;;
    help|-h|--help) usage;; *) usage >&2; exit 2 ;;
esac
