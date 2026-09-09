#!/usr/bin/env bash

set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=core/setup.sh
source "$repo_dir/core/setup.sh"
action="${1:-uninstall}"

if [ ! -f "$deblestia_state_dir/components" ]; then
    deblestia_t no_installation; printf '\n'
    exit 0
fi
mapfile -t installed <"$deblestia_state_dir/components"
deblestia_t installed_components "${installed[*]}"; printf '\n'
if [ "$action" = uninstall ] && [ "${DEBLESTIA_ASSUME_YES:-0}" != 1 ]; then
    [ -t 0 ] || { deblestia_t confirmation_short >&2; printf '\n' >&2; exit 1; }
    read -r -p "$(deblestia_t restore_prompt)" answer
    case "$answer" in o|O|oui|OUI|y|Y|yes|YES) ;; *) exit 0;; esac
fi
remaining=()
for component_name in "${installed[@]}"; do
    installer="$(deblestia_component_field "$component_name" 3)"
    if "$repo_dir/$installer" restore; then
        deblestia_t restored "$component_name"; printf '\n'
    else
        deblestia_t restore_unavailable "$component_name" >&2; printf '\n' >&2
        remaining+=("$component_name")
    fi
done
if ((${#remaining[@]})); then
    printf '%s\n' "${remaining[@]}" >"$deblestia_state_dir/components"
    exit 1
fi
rm -f "$deblestia_state_dir/components" "$deblestia_state_dir/profile"
deblestia_t state_removed; printf '\n'
