#!/usr/bin/env bash

set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=core/setup.sh
source "$repo_dir/core/setup.sh"
action="${1:-uninstall}"

if [ ! -f "$deblestia_state_dir/components" ]; then
    printf 'Aucune installation unifiée enregistrée. Les anciens installateurs restent gérés par leur commande restore.\n'
    exit 0
fi
mapfile -t installed <"$deblestia_state_dir/components"
printf 'Composants enregistrés : %s\n' "${installed[*]}"
if [ "$action" = uninstall ] && [ "${DEBLESTIA_ASSUME_YES:-0}" != 1 ]; then
    [ -t 0 ] || { printf 'Confirmation interactive requise.\n' >&2; exit 1; }
    read -r -p "Restaurer sans supprimer GNOME ni les paquets système ? [o/N] " answer
    case "$answer" in o|O|oui|OUI|y|Y|yes|YES) ;; *) exit 0;; esac
fi
remaining=()
for component_name in "${installed[@]}"; do
    installer="$(deblestia_component_field "$component_name" 3)"
    if "$repo_dir/$installer" restore; then
        printf 'Restauré : %s\n' "$component_name"
    else
        printf 'Restauration non disponible : %s\n' "$component_name" >&2
        remaining+=("$component_name")
    fi
done
if ((${#remaining[@]})); then
    printf '%s\n' "${remaining[@]}" >"$deblestia_state_dir/components"
    exit 1
fi
rm -f "$deblestia_state_dir/components" "$deblestia_state_dir/profile"
printf 'État Deblestia retiré. GNOME, GDM et les paquets existants sont conservés.\n'
