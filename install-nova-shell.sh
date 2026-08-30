#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
action="${1:-install}"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
waybar_dir="$config_home/waybar"
selector_target="$waybar_dir/configs/[Deblestia] Nova"
target="$config_home/quickshell/deblestia-nova"
settings_dir="$config_home/illogical-impulse"
settings_file="$settings_dir/config.json"
hypr_dir="$config_home/hypr"
hypr_main="$hypr_dir/hyprland.conf"
hypr_include="$hypr_dir/deblestia-nova-shell.conf"
input_include="$hypr_dir/deblestia-input.conf"
launch_target="$hypr_dir/scripts/deblestia-nova-shell-launch.sh"
mode_target="$hypr_dir/scripts/desktop-shell-mode.sh"
lock_target="$hypr_dir/scripts/deblestia-nova-lock.sh"
backup_root="$config_home/deblestia-nova-backups"
state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/deblestia-nova"
state_file="$state_dir/last-backup"
source_url="${DEBLESTIA_NOVA_SOURCE:-https://github.com/pctrade/end4-pC.git}"
source_line="source = $hypr_include"
input_source_line="source = $input_include"

usage() {
    cat <<'EOF'
Usage : ./install-deblestia-nova.sh [action]

Actions :
  check       vérifier les dépendances sans modifier le système
  install     télécharger et installer Deblestia Nova
  update      sauvegarder puis installer la dernière version amont
  launch      remplacer la barre active par Nova dans la session courante
  status      afficher l'état de l'installation
  restore     restaurer la dernière sauvegarde
EOF
}

have() {
    command -v "$1" >/dev/null 2>&1
}

check_dependencies() {
    local missing=0 command_name
    for command_name in git qs python3 jq; do
        if have "$command_name"; then
            printf 'OK       %s\n' "$command_name"
        else
            printf 'MANQUANT %s\n' "$command_name"
            missing=1
        fi
    done

    for command_name in hyprctl hyprlock kitty btop pavucontrol blueman-manager \
        nmtui brightnessctl ddcutil cava cliphist wl-copy slurp swappy \
        wf-recorder tesseract hyprpicker playerctl qalc; do
        if have "$command_name"; then
            printf 'OK       %s\n' "$command_name"
        else
            printf 'OPTIONNEL %s (fonction associée indisponible)\n' "$command_name"
        fi
    done
    return "$missing"
}

record_file() {
    local path="$1" key="$2" backup_dir="$3"
    if [ -e "$path" ] || [ -L "$path" ]; then
        cp -a "$path" "$backup_dir/files/$key"
        printf 'present\t%s\tfiles/%s\n' "$path" "$key" >>"$backup_dir/manifest.tsv"
    else
        printf 'missing\t%s\t-\n' "$path" >>"$backup_dir/manifest.tsv"
    fi
}

merge_settings() {
    local preset="$repo_dir/config/nova-shell/debian-config.json" output
    mkdir -p "$settings_dir"
    if [ ! -f "$settings_file" ]; then
        install -m 0644 "$preset" "$settings_file"
        return
    fi

    output="$(mktemp "$settings_dir/.deblestia-config.XXXXXX")"
    jq -s '
      def merge($a; $b):
        if ($a | type) == "object" and ($b | type) == "object" then
          reduce ($b | keys_unsorted[]) as $key ($a;
            .[$key] = if (.[$key] | type) == "object" and ($b[$key] | type) == "object"
                     then merge(.[$key]; $b[$key]) else $b[$key] end)
        else $b end;
      merge(.[0]; .[1])
    ' "$settings_file" "$preset" >"$output"
    chmod 0644 "$output"
    mv "$output" "$settings_file"
}

disable_conflicting_shell_source() {
    local output

    [ -f "$hypr_main" ] || return 0
    output="$(mktemp "$hypr_dir/.deblestia-hyprland.XXXXXX")"
    sed -E \
        's|^[[:space:]]*source[[:space:]]*=[[:space:]]*(.*/caelestia-v2\.conf)[[:space:]]*$|# Désactivé par Deblestia Nova : source = \1|' \
        "$hypr_main" >"$output"
    chmod --reference="$hypr_main" "$output"
    mv "$output" "$hypr_main"
}

install_shell() {
    local timestamp backup_dir staging revision
    check_dependencies || {
        printf '\nInstallez les dépendances obligatoires signalées puis recommencez.\n' >&2
        return 1
    }

    timestamp="$(date +%Y%m%d-%H%M%S)"
    backup_dir="$backup_root/$timestamp"
    staging="$(mktemp -d "${TMPDIR:-/tmp}/deblestia-nova.XXXXXX")"
    trap 'rm -rf "$staging"' RETURN

    printf '\nTéléchargement de la base end4-pC…\n'
    git clone --depth 1 "$source_url" "$staging/source"
    revision="$(git -C "$staging/source" rev-parse HEAD)"
    git -C "$staging/source" apply --whitespace=nowarn \
        "$repo_dir/config/nova-shell/qt68-compat.patch"

    mkdir -p "$backup_dir/files" "$state_dir" "$hypr_dir/scripts" \
        "$(dirname "$target")" "$waybar_dir/configs"
    : >"$backup_dir/manifest.tsv"
    record_file "$target" quickshell "$backup_dir"
    record_file "$settings_file" settings.json "$backup_dir"
    record_file "$hypr_include" hypr-include.conf "$backup_dir"
    record_file "$input_include" input-include.conf "$backup_dir"
    record_file "$launch_target" launch.sh "$backup_dir"
    record_file "$mode_target" desktop-shell-mode.sh "$backup_dir"
    record_file "$selector_target" nova-selector-entry "$backup_dir"
    record_file "$lock_target" lock.sh "$backup_dir"
    record_file "$hypr_main" hyprland.conf "$backup_dir"

    if [ -e "$target" ] || [ -L "$target" ]; then
        mv "$target" "$backup_dir/previous-quickshell"
    fi
    mv "$staging/source" "$target"

    install -m 0644 "$repo_dir/config/hypr/deblestia-nova-shell.conf" "$hypr_include"
    install -m 0644 "$repo_dir/config/hypr/deblestia-input.conf" "$input_include"
    install -m 0755 "$repo_dir/config/hypr/scripts/deblestia-nova-shell-launch.sh" "$launch_target"
    install -m 0755 "$repo_dir/config/hypr/scripts/desktop-shell-mode.sh" "$mode_target"
    install -m 0644 "$repo_dir/config/waybar/configs/[Deblestia] Nova" "$selector_target"
    install -m 0755 "$repo_dir/config/hypr/scripts/deblestia-nova-lock.sh" "$lock_target"
    merge_settings
    disable_conflicting_shell_source

    if [ ! -f "$hypr_main" ]; then
        printf '%s\n' "$source_line" >"$hypr_main"
    elif ! grep -Fqx "$source_line" "$hypr_main"; then
        printf '\n# Deblestia Nova — shell Quickshell\n%s\n' "$source_line" >>"$hypr_main"
    fi
    if ! grep -Fqx "$input_source_line" "$hypr_main"; then
        printf '\n# Navigation souris et pavé tactile Deblestia\n%s\n' \
            "$input_source_line" >>"$hypr_main"
    fi

    printf '%s\n' "$backup_dir" >"$state_file"
    printf '%s\n' "$revision" >"$target/.deblestia-upstream-revision"

    if have hyprctl; then
        hyprctl reload >/dev/null 2>&1 || true
    fi
    printf '\nDeblestia Nova installé.\nRévision amont : %s\nSauvegarde : %s\n' \
        "$revision" "$backup_dir"
    printf 'Démarrage : %s launch\n' "$repo_dir/install-deblestia-nova.sh"
}

launch_shell() {
    if [ ! -x "$launch_target" ]; then
        printf "Deblestia Nova n'est pas installé. Lancez d'abord install.\n" >&2
        return 1
    fi
    if [ -d "$waybar_dir/configs" ]; then
        ln -sfn "$selector_target" "$waybar_dir/config"
    fi
    if [ -x "$mode_target" ]; then
        "$mode_target" "[Deblestia] Nova"
    else
        "$launch_target" --force
    fi
    printf 'Deblestia Nova démarre en arrière-plan.\n'
}

status_shell() {
    if [ -f "$target/shell.qml" ]; then
        printf 'INSTALLÉ %s\n' "$target"
        [ -f "$target/.deblestia-upstream-revision" ] && \
            printf 'RÉVISION %s\n' "$(cat "$target/.deblestia-upstream-revision")"
    else
        printf 'ABSENT    %s\n' "$target"
    fi
    if [ -f "$hypr_main" ] && grep -Fqx "$source_line" "$hypr_main"; then
        printf 'HYPRLAND  inclusion active\n'
    else
        printf 'HYPRLAND  inclusion absente\n'
    fi
    pgrep -af 'qs.*deblestia-nova|quickshell.*deblestia-nova' || true
}

restore_shell() {
    local backup_dir status path relative rollback
    if [ ! -f "$state_file" ]; then
        printf 'Aucune sauvegarde Deblestia Nova enregistrée.\n' >&2
        return 1
    fi
    backup_dir="$(cat "$state_file")"
    if [ ! -f "$backup_dir/manifest.tsv" ]; then
        printf 'Manifest introuvable : %s\n' "$backup_dir" >&2
        return 1
    fi

    rollback="$backup_root/avant-restauration-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$rollback"
    while IFS=$'\t' read -r status path relative; do
        if [ -e "$path" ] || [ -L "$path" ]; then
            mv "$path" "$rollback/$(basename "$path")"
        fi
        if [ "$status" = present ]; then
            mkdir -p "$(dirname "$path")"
            cp -a "$backup_dir/$relative" "$path"
        fi
    done <"$backup_dir/manifest.tsv"

    if have hyprctl; then
        hyprctl reload >/dev/null 2>&1 || true
    fi
    printf 'Sauvegarde restaurée : %s\nÉtat remplacé conservé dans : %s\n' "$backup_dir" "$rollback"
}

case "$action" in
    check) check_dependencies ;;
    install|update) install_shell ;;
    launch) launch_shell ;;
    status) status_shell ;;
    restore) restore_shell ;;
    help|-h|--help) usage ;;
    *) printf 'Action inconnue : %s\n\n' "$action" >&2; usage >&2; exit 2 ;;
esac
