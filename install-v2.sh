#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
caelestia_dir="$config_home/caelestia"
hypr_dir="$config_home/hypr"
hypr_main="$hypr_dir/hyprland.conf"
state_dir="$config_home/debian-immersive-v2"
state_file="$state_dir/state"
history_file="$state_dir/history.log"
backup_root="$config_home/debian-immersive-v2-backups"
component_manifest="$repo_dir/config/v2/components.tsv"
theme_manifest="$repo_dir/config/v2/themes.tsv"
theme_root="$config_home/debian-immersive-v2/themes"
theme_override="$hypr_dir/debian-immersive-v2-theme.conf"
source_line="source = $hypr_dir/caelestia-v2.conf"
theme_source_line="source = $theme_override"
dry_run=0

sources=(
    "$repo_dir/config/caelestia/shell.json"
    "$repo_dir/config/hypr/caelestia-v2.conf"
    "$repo_dir/config/hypr/scripts/caelestia-v2-launch.sh"
    "$repo_dir/config/hypr/scripts/caelestia-v2-lock.sh"
    "$repo_dir/config/hypr/scripts/caelestia-v2-display-profile.sh"
)
targets=(
    "$caelestia_dir/shell.json"
    "$hypr_dir/caelestia-v2.conf"
    "$hypr_dir/scripts/caelestia-v2-launch.sh"
    "$hypr_dir/scripts/caelestia-v2-lock.sh"
    "$hypr_dir/scripts/caelestia-v2-display-profile.sh"
)
modes=(0644 0644 0755 0755 0755)

usage() {
    cat <<'EOF'
Usage : ./install-v2.sh [check|install|status|restore|theme] [--dry-run] [sauvegarde]

  check              vérifie les prérequis et les fichiers source
  install            installe ou actualise uniquement la v2 (commande par défaut)
  status             compare la v2 installée avec le dépôt
  restore [chemin]   restaure une sauvegarde, ou la dernière sauvegarde connue
    theme list         affiche les thèmes HyDE suivis par la v2
    theme download ID  télécharge un thème, ou tous les thèmes avec ID=all
    theme apply ID     adapte et active un thème déjà téléchargé
  --dry-run           affiche les écritures prévues sans modifier le système
EOF
}

log_action() {
    printf '[simulation] %s\n' "$*"
}

make_directory() {
    if ((dry_run)); then
        log_action "mkdir -p $1"
    else
        mkdir -p "$1"
    fi
}

check_prerequisites() {
    local failed=0 source
    if command -v Hyprland >/dev/null 2>&1 || command -v hyprctl >/dev/null 2>&1; then
        printf 'OK       Hyprland\n'
    else
        printf 'MANQUANT Hyprland (commande Hyprland ou hyprctl)\n' >&2
        failed=1
    fi
    if command -v qs >/dev/null 2>&1; then
        printf 'OK       Quickshell git (qs)\n'
    else
        printf 'MANQUANT Quickshell git (qs)\n' >&2
        failed=1
    fi
    if [ -x "$HOME/.nix-profile/bin/caelestia" ] || command -v caelestia >/dev/null 2>&1; then
        printf 'OK       caelestia-cli\n'
    else
        printf 'MANQUANT caelestia-cli\n' >&2
        failed=1
    fi
    for source in "${sources[@]}"; do
        if [ ! -f "$source" ]; then
            printf 'MANQUANT fichier source : %s\n' "$source" >&2
            failed=1
        fi
    done
    if [ -f "$component_manifest" ]; then
        printf 'OK       manifeste des composants v2\n'
    else
        printf 'MANQUANT manifeste : %s\n' "$component_manifest" >&2
        failed=1
    fi
    if [ -f "$theme_manifest" ]; then
        printf 'OK       catalogue des thèmes v2\n'
    else
        printf 'MANQUANT catalogue : %s\n' "$theme_manifest" >&2
        failed=1
    fi
    return "$failed"
}

list_themes() {
    printf 'ID\tTHÈME\tMODE\tSOURCE\n'
    awk -F '\t' '$0 !~ /^#/ && NF >= 5 { printf "%s\t%s\t%s\t%s\n", $1, $3, $4, $5 }' \
        "$theme_manifest"
}

download_theme() {
    local requested="${1:-}" id branch name mode url downloaded=0
    if [ -z "$requested" ]; then
        usage >&2
        return 2
    fi
    make_directory "$theme_root"
    while IFS=$'\t' read -r id branch name mode url || [[ -n "$id" ]]; do
        [[ "$id" == \#* || -z "$id" ]] && continue
        if [ "$requested" != all ] && [ "$requested" != "$id" ]; then
            continue
        fi
        if [ -e "$theme_root/$id" ]; then
            printf 'EXISTE   %s\n' "$theme_root/$id"
        else
            git clone --depth 1 --branch "$branch" \
                https://github.com/HyDE-Project/hyde-themes.git "$theme_root/$id"
            printf 'TÉLÉCHARGÉ %s (%s)\n' "$name" "$branch"
        fi
        downloaded=1
        [ "$requested" != all ] && break
    done <"$theme_manifest"
    if [ "$downloaded" -eq 0 ]; then
        printf 'Thème inconnu : %s\n' "$requested" >&2
        return 1
    fi
}

theme_value() {
    local key="$1" file="$2"
    awk -v key="$key" '
        index($0, "$" key) == 1 {
            value = $0
            sub(/^[^=]*=[[:space:]]*/, "", value)
            sub(/[[:space:]]+$/, "", value)
            gsub(/^"|"$/, "", value)
            print value
            exit
        }
    ' "$file"
}

theme_color_line() {
    local key="$1" file="$2"
    awk -v key="$key" '
        $0 ~ "^[[:space:]]*" key "[[:space:]]*=" {
            value = $0
            sub(/^[^=]*=[[:space:]]*/, "", value)
            print value
            exit
        }
    ' "$file"
}

apply_theme() {
    local id="${1:-}" theme_dir theme_file gtk_theme icon_theme color_scheme
    local active_border inactive_border timestamp backup_dir
    if [ -z "$id" ]; then
        usage >&2
        return 2
    fi
    theme_dir="$theme_root/$id"
    if [ ! -d "$theme_dir" ]; then
        printf 'Thème non téléchargé : %s\n' "$id" >&2
        printf 'Utilisez : %s theme download %s\n' "$0" "$id" >&2
        return 1
    fi
    theme_file="$(find "$theme_dir" -type f -name hypr.theme -print -quit)"
    if [ -z "$theme_file" ]; then
        printf 'Fichier hypr.theme introuvable pour : %s\n' "$id" >&2
        return 1
    fi
    gtk_theme="$(theme_value GTK_THEME "$theme_file")"
    icon_theme="$(theme_value ICON_THEME "$theme_file")"
    color_scheme="$(theme_value COLOR_SCHEME "$theme_file")"
    active_border="$(theme_color_line 'col.active_border' "$theme_file")"
    inactive_border="$(theme_color_line 'col.inactive_border' "$theme_file")"
    if [ -z "$active_border" ] || [ -z "$inactive_border" ]; then
        printf 'Couleurs Hyprland incomplètes pour : %s\n' "$id" >&2
        return 1
    fi
    if printf '%s\n' "$active_border$inactive_border" \
        | grep -Eq '[^[:space:][:alnum:]_,.()#%+*/-]'; then
        printf 'Valeurs de couleur invalides pour : %s\n' "$id" >&2
        return 1
    fi
    timestamp="$(date +%Y%m%d-%H%M%S)-$$"
    backup_dir="$backup_root/$timestamp"
    make_directory "$backup_dir/files"
    make_directory "$state_dir"
    backup_target "$theme_override" "$backup_dir" theme-override
    backup_target "$hypr_main" "$backup_dir" hyprland.conf
    if ((dry_run)); then
        log_action "générer $theme_override depuis $theme_file"
        log_action "ajouter $theme_source_line à $hypr_main"
        log_action "activer GTK=$gtk_theme ICONS=$icon_theme SCHEME=$color_scheme"
    else
        make_directory "$hypr_dir"
        {
            printf '# Debian Immersive v2 — thème adapté depuis HyDE\n'
            printf '# Source : %s\n\n' "$id"
            printf 'general {\n'
            printf '    col.active_border = %s\n' "$active_border"
            printf '    col.inactive_border = %s\n' "$inactive_border"
            printf '}\n\n'
            printf 'group {\n'
            printf '    col.border_active = %s\n' "$active_border"
            printf '    col.border_inactive = %s\n' "$inactive_border"
            printf '}\n'
        } >"$theme_override"
        if [ ! -f "$hypr_main" ]; then
            printf '%s\n' "$theme_source_line" >"$hypr_main"
        elif ! grep -Fqx "$theme_source_line" "$hypr_main"; then
            printf '\n# Debian Immersive v2 theme\n%s\n' "$theme_source_line" >>"$hypr_main"
        fi
        if command -v gsettings >/dev/null 2>&1; then
            [ -n "$gtk_theme" ] && gsettings set org.gnome.desktop.interface gtk-theme "$gtk_theme" || true
            [ -n "$icon_theme" ] && gsettings set org.gnome.desktop.interface icon-theme "$icon_theme" || true
            [ -n "$color_scheme" ] && gsettings set org.gnome.desktop.interface color-scheme "$color_scheme" || true
        fi
        {
            printf 'installed_at=%s\n' "$timestamp"
            printf 'last_backup=%s\n' "$backup_dir"
            printf 'theme=%s\n' "$id"
        } >"$state_file"
        printf '%s\ttheme-apply\t%s\n' "$timestamp" "$backup_dir" >>"$history_file"
        hyprctl reload >/dev/null 2>&1 || true
        printf 'Thème activé : %s\n' "$id"
    fi
}

backup_target() {
    local target="$1" backup_dir="$2" key="$3" manifest="$backup_dir/manifest.tsv"
    if [ -e "$target" ] || [ -L "$target" ]; then
        if ((dry_run)); then
            log_action "sauvegarder $target"
        else
            cp -a "$target" "$backup_dir/files/$key"
            printf 'present\t%s\tfiles/%s\n' "$target" "$key" >>"$manifest"
        fi
    elif ! ((dry_run)); then
        printf 'missing\t%s\t-\n' "$target" >>"$manifest"
    fi
}

install_v2() {
    check_prerequisites
    local timestamp backup_dir index
    timestamp="$(date +%Y%m%d-%H%M%S)-$$"
    backup_dir="$backup_root/$timestamp"
    make_directory "$backup_dir/files"
    make_directory "$caelestia_dir"
    make_directory "$hypr_dir/scripts"
    make_directory "$state_dir"

    for index in "${!targets[@]}"; do
        backup_target "${targets[$index]}" "$backup_dir" "component-$index"
    done
    backup_target "$hypr_main" "$backup_dir" "hyprland.conf"

    for index in "${!targets[@]}"; do
        if ((dry_run)); then
            log_action "installer ${sources[$index]} vers ${targets[$index]} (mode ${modes[$index]})"
        else
            install -m "${modes[$index]}" "${sources[$index]}" "${targets[$index]}"
        fi
    done

    if [ ! -f "$hypr_main" ]; then
        if ((dry_run)); then
            log_action "créer $hypr_main avec l'inclusion v2"
        else
            printf '%s\n' "$source_line" >"$hypr_main"
        fi
    elif ! grep -Fqx "$source_line" "$hypr_main"; then
        if ((dry_run)); then
            log_action "ajouter l'inclusion v2 à $hypr_main"
        else
            printf '\n# Debian Immersive v2\n%s\n' "$source_line" >>"$hypr_main"
        fi
    fi

    make_directory "$HOME/Pictures/Wallpapers"
    if ((dry_run)); then
        log_action "enregistrer la sauvegarde $backup_dir et recharger Hyprland"
        return
    fi
    {
        printf 'installed_at=%s\n' "$timestamp"
        printf 'last_backup=%s\n' "$backup_dir"
    } >"$state_file"
    printf '%s\tinstall\t%s\n' "$timestamp" "$backup_dir" >>"$history_file"
    hyprctl reload >/dev/null 2>&1 || true
    printf 'Debian Immersive v2 installé. Sauvegarde : %s\n' "$backup_dir"
    printf 'Relancez la session, ou exécutez : %s\n' "$hypr_dir/scripts/caelestia-v2-launch.sh"
}

status_v2() {
    local index differences=0
    for index in "${!targets[@]}"; do
        if [ ! -e "${targets[$index]}" ]; then
            printf 'ABSENT   %s\n' "${targets[$index]}"
            differences=1
        elif cmp -s "${sources[$index]}" "${targets[$index]}"; then
            printf 'OK       %s\n' "${targets[$index]}"
        else
            printf 'MODIFIÉ  %s\n' "${targets[$index]}"
            differences=1
        fi
    done
    if [ -f "$hypr_main" ] && grep -Fqx "$source_line" "$hypr_main"; then
        printf 'OK       inclusion Hyprland v2\n'
    else
        printf 'ABSENT   inclusion Hyprland v2\n'
        differences=1
    fi
    if [ -f "$state_file" ]; then
        printf 'ÉTAT     %s\n' "$state_file"
    fi
    return "$differences"
}

last_backup_from_state() {
    [ -f "$state_file" ] || return 1
    sed -n 's/^last_backup=//p' "$state_file" | tail -n 1
}

restore_v2() {
    local backup_dir="${1:-}" status target relative
    if [ -z "$backup_dir" ]; then
        backup_dir="$(last_backup_from_state || true)"
    fi
    if [ -z "$backup_dir" ] || [ ! -f "$backup_dir/manifest.tsv" ]; then
        printf 'Sauvegarde v2 introuvable. Indiquez son chemin après restore.\n' >&2
        return 1
    fi
    while IFS=$'\t' read -r status target relative; do
        if ((dry_run)); then
            if [ "$status" = present ]; then
                log_action "restaurer $target depuis $backup_dir/$relative"
            else
                log_action "retirer le fichier v2 $target"
            fi
            continue
        fi
        if [ "$status" = present ]; then
            mkdir -p "$(dirname "$target")"
            cp -a "$backup_dir/$relative" "$target"
        else
            rm -f "$target"
        fi
    done <"$backup_dir/manifest.tsv"
    if ((dry_run)); then
        return
    fi
    rm -f "$state_file"
    printf '%s\trestore\t%s\n' "$(date +%Y%m%d-%H%M%S)" "$backup_dir" >>"$history_file"
    hyprctl reload >/dev/null 2>&1 || true
    printf 'Sauvegarde restaurée : %s\n' "$backup_dir"
}

action="${1:-install}"
if [ "$action" = --dry-run ]; then
    dry_run=1
    action="install"
    shift
elif (($#)); then
    shift
fi
if [ "${1:-}" = --dry-run ]; then
    dry_run=1
    shift
fi

case "$action" in
    check) check_prerequisites ;;
    install) install_v2 ;;
    status) status_v2 ;;
    restore) restore_v2 "${1:-}" ;;
    theme)
        if [ "${1:-}" = list ]; then
            list_themes
        elif [ "${1:-}" = download ]; then
            download_theme "${2:-}"
        elif [ "${1:-}" = apply ]; then
            [ "${3:-}" = --dry-run ] && dry_run=1
            apply_theme "${2:-}"
        else
            usage >&2
            exit 2
        fi
        ;;
    help|-h|--help) usage ;;
    *) usage >&2; exit 2 ;;
esac
