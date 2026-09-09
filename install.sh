#!/usr/bin/env bash

set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=core/setup.sh
source "$repo_dir/core/setup.sh"

usage() {
    deblestia_t usage "$0"; printf '\n'
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
    printf '\n'; deblestia_t analyzing; printf '\n\n'
    python3 "$repo_dir/core/hardware.py"
    printf '\n'
    python3 "$repo_dir/core/compatibility.py"
}

confirm() {
    [ "${DEBLESTIA_ASSUME_YES:-0}" = 1 ] && return 0
    [ -t 0 ] || {
        deblestia_t confirmation_required >&2; printf '\n' >&2
        return 1
    }
    local answer
    read -r -p "$(deblestia_t continue_plan)" answer
    case "$answer" in o|O|oui|OUI|y|Y|yes|YES) return 0;; *) return 1;; esac
}

install_dependencies() {
    local mode="$1"
    mapfile -t missing < <(deblestia_missing_packages)
    ((${#missing[@]})) || { deblestia_t deps_present; printf '\n'; return; }
    deblestia_t deps_needed "${missing[*]}"; printf '\n'
    case "$mode" in
        automatic)
            local package
            for package in "${missing[@]}"; do
                apt-cache show "$package" >/dev/null 2>&1 || {
                    deblestia_t package_missing "$package" >&2; printf '\n' >&2
                    return 1
                }
            done
            sudo apt-get install --no-install-recommends "${missing[@]}"
            ;;
        manual)
            deblestia_t manual_command; printf '\n  sudo apt-get install --no-install-recommends %s\n' "${missing[*]}"
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
        printf '\n' >&2; deblestia_t automatic_refused >&2; printf '\n' >&2
        return 1
    fi
    mapfile -t components < <(deblestia_components_for_profile "$profile")
    mapfile -t missing < <(deblestia_missing_packages)
    printf '\n'; deblestia_t profile "$profile"; printf '\n'; deblestia_t gnome_kept; printf '\n'
    deblestia_t components_proposed "${components[*]}"; printf '\n'
    deblestia_t dependencies_install "${missing[*]:-$(deblestia_t none)}"; printf '\n'
    if [ "${DEBLESTIA_PLAN_ONLY:-0}" = 1 ]; then
        deblestia_t dry_run_done; printf '\n'
        return 0
    fi
    if [ -t 0 ] && ((${#missing[@]})); then
        read -r -p "$(deblestia_t deps_prompt)" choice
        case "$choice" in m|M) dependency_mode=manual;; s|S) dependency_mode=skip;; esac
    fi
    confirm || { deblestia_t cancelled; printf '\n'; return 0; }
    if ! install_dependencies "$dependency_mode"; then
        [ "$dependency_mode" = automatic ] && return 1
        deblestia_t components_deferred; printf '\n'
        return 0
    fi
    mkdir -p "$deblestia_state_dir"
    printf '%s\n' "$profile" >"$deblestia_state_dir/profile"
    for component_name in "${components[@]}"; do
        deblestia_install_component "$component_name"
    done
    printf '\n'; deblestia_t install_done; printf '\n'
}

component() {
    local id="${1:-}" label
    label="$(deblestia_component_field "$id" 2)"
    [ -n "$label" ] || { deblestia_t unknown_component "$id" >&2; printf '\n' >&2; return 2; }
    deblestia_t component "$label"; printf '\n'
    confirm || { deblestia_t cancelled; printf '\n'; return 0; }
    deblestia_install_component "$id"
}

manual() {
    local choice id
    while true; do
        printf '\n%s\n' "$(deblestia_t manual_title)"
        cat <<'EOF'
  1) Deblestia Bar          5) MPVpaper Engine
  2) Deblestia Nova         6) PeriphX
  3) Deblestia Shell        7) MirrorBridge
  4) Deblestia Nova Lite
EOF
        printf '  0) %s\n' "$(deblestia_t back)"
        read -r -p "$(deblestia_t choice)" choice
        case "$choice" in
            1) id=deblestia-bar;; 2) id=deblestia-nova;; 3) id=deblestia-shell;;
            4) id=deblestia-nova-lite;; 5) id=mpvpaper-engine;;
            6) id=periphx;; 7) id=mirrorbridge;;
            0) return;; *) deblestia_t unknown_choice; printf '\n'; continue;;
        esac
        component "$id"
    done
}

menu() {
    local choice
    while true; do
        header
        printf '\n  1) %s\n  2) %s\n  3) %s\n  4) %s\n  5) %s\n  6) %s\n  0) %s\n' \
            "$(deblestia_t automatic_menu)" "$(deblestia_t manual_menu)" \
            "$(deblestia_t contribution_menu)" "$(deblestia_t diagnostic_menu)" \
            "$(deblestia_t restore_menu)" "$(deblestia_t uninstall_menu)" \
            "$(deblestia_t quit_menu)"
        read -r -p "$(deblestia_t choice)" choice
        case "$choice" in
            1) automatic;; 2) manual;; 3) "$repo_dir/contribute.sh";; 4) diagnostic;;
            5) "$repo_dir/uninstall.sh" restore;; 6) "$repo_dir/uninstall.sh";; 0) return;;
            *) deblestia_t unknown_choice; printf '\n';;
        esac
    done
}

if [[ "${1:-}" == --lang=* ]]; then
    deblestia_set_language "${1#*=}" || { deblestia_t bad_language "${1#*=}" >&2; printf '\n' >&2; exit 2; }
    shift
elif [ "${1:-}" = --lang ]; then
    [ -n "${2:-}" ] || { usage >&2; exit 2; }
    deblestia_set_language "$2" || { deblestia_t bad_language "$2" >&2; printf '\n' >&2; exit 2; }
    shift 2
fi
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
