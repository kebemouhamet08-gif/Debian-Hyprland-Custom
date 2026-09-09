#!/usr/bin/env bash

deblestia_repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
deblestia_state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/deblestia/setup"
deblestia_manifest="$deblestia_repo_dir/manifests/components.tsv"

deblestia_profile() {
    python3 "$deblestia_repo_dir/core/compatibility.py" --json | jq -r .profile
}

deblestia_compatibility() {
    python3 "$deblestia_repo_dir/core/compatibility.py" --json | jq -r .compatibility
}

deblestia_component_field() {
    awk -F '\t' -v id="$1" -v field="$2" \
        '$0 !~ /^#/ && $1 == id {print $field; exit}' "$deblestia_manifest"
}

deblestia_components_for_profile() {
    awk -F '\t' -v profile="$1" \
        '$0 !~ /^#/ && ("," $4 ",") ~ ("," profile ",") {print $1}' \
        "$deblestia_manifest"
}

deblestia_record_component() {
    mkdir -p "$deblestia_state_dir"
    touch "$deblestia_state_dir/components"
    grep -Fqx "$1" "$deblestia_state_dir/components" 2>/dev/null || \
        printf '%s\n' "$1" >>"$deblestia_state_dir/components"
}

deblestia_install_component() {
    local component="$1" installer label critical
    installer="$(deblestia_component_field "$component" 3)"
    label="$(deblestia_component_field "$component" 2)"
    critical="$(deblestia_component_field "$component" 5)"
    if [ -z "$installer" ] || [ ! -x "$deblestia_repo_dir/$installer" ]; then
        printf 'ERREUR   composant inconnu ou installateur absent : %s\n' "$component" >&2
        return 1
    fi
    printf '\nInstallation : %s\n' "$label"
    if "$deblestia_repo_dir/$installer" check && "$deblestia_repo_dir/$installer" install; then
        deblestia_record_component "$component"
        return 0
    fi
    if [ "$critical" = yes ]; then
        printf 'ÉCHEC critique : %s\n' "$label" >&2
        return 1
    fi
    printf 'OPTIONNEL indisponible : %s. Installation générale poursuivie.\n' "$label" >&2
}

deblestia_packages() {
    printf '%s\n' hyprland waybar kitty rofi jq playerctl cava pipewire wireplumber \
        python3 python3-gi gir1.2-gtk-3.0
}

deblestia_missing_packages() {
    local package
    while IFS= read -r package; do
        dpkg-query -W -f='${db:Status-Abbrev}' "$package" 2>/dev/null | grep -q '^ii ' || \
            printf '%s\n' "$package"
    done < <(deblestia_packages)
}
